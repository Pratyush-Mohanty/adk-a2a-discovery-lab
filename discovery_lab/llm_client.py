"""Free-LLM client for the "LLM-reasoned routing" experiment.

Works with any OpenAI-compatible chat endpoint:
  * Ollama (default, 100% free, local, no key)   http://127.0.0.1:11434/v1
  * LM Studio / vLLM local servers
  * Groq / OpenRouter free-tier keys via FREE_LLM_API_KEY

If no endpoint is reachable it transparently falls back to a deterministic
keyword scorer (`mode="mock"`) so experiments still run offline.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import httpx

from .config import HTTP_TIMEOUT_S
from .fleet import AgentSpec
from .registry_server import _card_json

logger = logging.getLogger("discovery_lab.llm")

DEFAULT_BASE_URL = os.environ.get("FREE_LLM_BASE_URL", "http://127.0.0.1:11434/v1")
DEFAULT_MODEL = os.environ.get("FREE_LLM_MODEL", "llama3.2")
DEFAULT_API_KEY = os.environ.get("FREE_LLM_API_KEY", "ollama")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class LLMResult:
    text: str | None
    tokens: int
    mode: str  # "ollama" | "openai" | "mock"


class LLMClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str | None = DEFAULT_API_KEY,
        *,
        probe: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.mode = self._probe() if probe else ("openai" if base_url != DEFAULT_BASE_URL else "mock")
        if self.mode == "mock":
            logger.info("No reachable LLM endpoint -> falling back to mock scorer (mode='mock').")

    def _probe(self) -> str:
        try:
            with httpx.Client(timeout=2.0) as hc:
                headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
                r = hc.get(f"{self.base_url}/models", headers=headers)
                if r.status_code < 400:
                    return "ollama" if "11434" in self.base_url else "openai"
        except Exception:
            pass
        return "mock"

    async def complete(
        self, system: str, user: str, *, timeout: float = HTTP_TIMEOUT_S
    ) -> LLMResult:
        if self.mode == "mock":
            return LLMResult(text=None, tokens=_estimate_tokens(system) + _estimate_tokens(user), mode="mock")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as hc:
                r = await hc.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
            usage = data.get("usage") or {}
            tokens = int(usage.get("total_tokens") or (_estimate_tokens(system) + _estimate_tokens(user)))
            text = (data["choices"][0]["message"]["content"] or "").strip()
            return LLMResult(text=text or None, tokens=tokens, mode=self.mode)
        except Exception as exc:
            logger.warning("LLM call failed (%s) -> mock fallback for this request", exc)
            return LLMResult(text=None, tokens=_estimate_tokens(system) + _estimate_tokens(user), mode="mock")

    async def pick_agent(
        self, task_text: str, candidates: list[dict], *, expected_hint: str | None = None
    ) -> tuple[str | None, LLMResult]:
        """Ask the LLM which candidate agent should handle `task_text`.

        Returns (agent_name | None, LLMResult).
        """
        listing = "\n".join(
            f"- {c['name']}: {c['description']} (skills: {', '.join(t for s in c['skills'] for t in s.get('tags', []))})"
            for c in candidates
        )
        system = (
            "You are a routing dispatcher. Choose the single best agent for the task. "
            "Reply with ONLY the agent name, nothing else. If none fit, reply 'NONE'."
        )
        user = f"Task: {task_text}\n\nAvailable agents:\n{listing}"
        result = await self.complete(system, user)
        if not result.text:
            return None, result
        reply = result.text.strip()
        for c in candidates:
            if c["name"] in reply:
                return c["name"], result
        return None, result


def keyword_score_candidates(task_text: str, candidates: list[dict]) -> list[dict]:
    """Deterministic fallback scorer: overlap between task tokens and skill tags/descriptions."""
    import re

    task_tokens = set(re.findall(r"[a-z]+", task_text.lower()))
    scored = []
    for c in candidates:
        score = 0.0
        for s in c.get("skills", []):
            tags = [t.lower() for t in s.get("tags", [])]
            desc = (s.get("description") or "").lower()
            overlap = len(task_tokens & set(tags))
            score += overlap * 2.0
            score += sum(1 for t in tags if t in task_tokens) * 1.0
            score += 0.25 if any(t in desc for t in task_tokens) else 0.0
        scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored]


def slim_cards_from_specs(specs: list[AgentSpec]) -> list[dict]:
    """Build the slim public card shape directly from fleet specs."""
    from .server import build_agent_card
    from google.protobuf.json_format import MessageToDict

    out = []
    for spec in specs:
        card = build_agent_card(spec)
        out.append(_card_json(MessageToDict(card, preserving_proto_field_name=False)))
    return out