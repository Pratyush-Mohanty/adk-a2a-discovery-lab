"""ADK demo: the Master as a real ADK `LlmAgent` driven by a FREE local LLM.

This mirrors the official "Multi-Agent Systems with Agent2Agent" codelab host
pattern, but discovery is DYNAMIC: the host uses two tools —
`list_remote_agents()` (fed by our card-discovery strategy) and
`delegate(...)` — so it discovers sub-agents from their Agent Cards instead
of having them hardcoded.

Requires (optional):
  pip install -r requirements-llm.txt
  Ollama running locally with a model, e.g. `ollama pull llama3.2`
     (or point FREE_LLM_BASE_URL / FREE_LLM_MODEL at any OpenAI-compatible
      endpoint — Groq / OpenRouter / LM Studio — via env vars).

Run:
  py -m discovery_lab.adk_demo
"""

from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("discovery_lab.adk_demo")

FLEET_HOST = "127.0.0.1"
OLLAMA_MODEL = os.environ.get("FREE_LLM_MODEL", "llama3.2")


def _ollama_available() -> bool:
    import httpx

    base = os.environ.get("FREE_LLM_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    try:
        with httpx.Client(timeout=2.0) as hc:
            r = hc.get(f"{base}/api/tags")
            return r.status_code < 400
    except Exception:
        return False


async def run_demo(task_text: str) -> str:
    from google.adk import Agent
    from google.adk.models.lite_llm import LiteLlm
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.utils.content_utils import types as T

    from discovery_lab.a2a_client import send_text
    from discovery_lab.launch import FleetRuntime
    from discovery_lab.strategies import CardDiscoveryStrategy

    class Discoverer:
        def __init__(self) -> None:
            self.strategy = CardDiscoveryStrategy()
            self._agents: dict[str, str] = {}

        async def setup(self) -> None:
            await self.strategy.setup()
            self._agents = {c["name"]: c["url"] for c in self.strategy._cards}

        async def list_remote_agents(self) -> list[dict]:
            return [
                {"name": c["name"], "description": c["description"]}
                for c in self.strategy._cards
            ]

        async def delegate(self, agent_name: str, message: str) -> str:
            if agent_name not in self._agents:
                raise ValueError(f"unknown agent {agent_name}")
            reply, _el = await send_text(self._agents[agent_name], message)
            return reply

    runtime = FleetRuntime()
    await runtime.start_fleet()
    await runtime.start_registry()
    try:
        discoverer = Discoverer()
        await discoverer.setup()

        host_agent = Agent(
            name="host",
            model=LiteLlm(model=f"ollama/{OLLAMA_MODEL}"),
            instruction=(
                "You are a coordinator. Fulfill user requests by delegating to "
                "specialized sub-agents. First call list_remote_agents() to see what is "
                "available, then call delegate(agent_name, message) with the full task. "
                "Choose the agent whose description best matches the request."
            ),
            description="Orchestrates discovery + delegation over A2A",
            tools=[discoverer.list_remote_agents, discoverer.delegate],
        )

        session_service = InMemorySessionService()
        runner = Runner(
            agent=host_agent,
            app_name="adk_host",
            session_service=session_service,
        )
        session_service.create_session(
            app_name="adk_host", user_id="demo", session_id="s1"
        )

        chunks: list[str] = []
        async for event in runner.run_async(
            user_id="demo",
            session_id="s1",
            new_message=T.Content(role="user", parts=[T.Part(text=task_text)]),
        ):
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        chunks.append(part.text)
        return "\n".join(chunks)
    finally:
        await runtime.stop()


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not _ollama_available():
        print(
            "Ollama not reachable. Install it (https://ollama.com), run `ollama pull "
            "llama3.2`, then re-run this demo.\n"
            "Any OpenAI-compatible endpoint works too: set FREE_LLM_BASE_URL / "
            "FREE_LLM_MODEL / FREE_LLM_API_KEY."
        )
        return
    task_text = "summarize: distributed systems sacrifice consistency for availability under the cap theorem when networks partition"
    print(f"task: {task_text}\n--- ADK host agent thinking... ---")
    out = await run_demo(task_text)
    print("--- host reply ---")
    print(out)


if __name__ == "__main__":
    asyncio.run(main())