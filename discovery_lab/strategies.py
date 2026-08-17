"""Pluggable discovery strategies for the Master agent.

Each strategy answers one question: given a task, which sub-agent should
handle it, and *how expensive was finding that answer*?

Strategies:
  static            hardcoded skill-tag -> agent map (no network discovery)
  card_discovery    fetch Agent Cards from known endpoints at startup
  registry_skill    query a central Agent Directory by skill tag (per request)
  cached            card discovery behind a TTL cache (latency vs staleness)
  llm_reasoned      gather candidates, then let a free LLM pick (or mock)
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import httpx

from .a2a_client import fetch_card
from .config import CARD_CACHE_TTL_S, HTTP_TIMEOUT_S, TaskSpec
from .fleet import build_fleet
from .llm_client import LLMClient, keyword_score_candidates, slim_cards_from_specs
from .registry_server import _card_json

logger = logging.getLogger("discovery_lab.strategies")


@dataclass
class AgentInfo:
    name: str
    description: str
    card_url: str
    url: str
    card: dict = field(default_factory=dict)

    def slim(self) -> dict:
        return _card_json(self.card) if self.card else {"name": self.name, "description": self.description}


@dataclass
class Resolution:
    strategy: str
    task_id: str
    agent: AgentInfo | None
    candidates: list[AgentInfo] = field(default_factory=list)
    discovery_ms: float = 0.0
    selection_ms: float = 0.0
    cache_hit: bool = False
    tokens: int = 0
    llm_mode: str | None = None
    notes: list[str] = field(default_factory=list)


class DiscoveryStrategy(ABC):
    name = "abstract"

    @abstractmethod
    async def setup(self) -> None: ...

    @abstractmethod
    async def resolve(self, task: TaskSpec, *, exclude: set[str] | None = None) -> Resolution: ...


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
def _index_by_tag(cards: list[dict]) -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = {}
    for card in cards:
        for skill in card.get("skills", []):
            for tag in skill.get("tags", []):
                index.setdefault(tag, []).append(card)
    return index


def _to_agent_info(card: dict) -> AgentInfo:
    from urllib.parse import urlsplit, urlunsplit

    interfaces = card.get("supportedInterfaces") or card.get("supported_interfaces") or []
    rpc_url = interfaces[0].get("url", "") if interfaces else card.get("url", "")
    parts = urlsplit(rpc_url)
    base = urlunsplit((parts.scheme, parts.netloc, "/", "", ""))
    card_url = f"{base}.well-known/agent-card.json"
    return AgentInfo(
        name=card["name"],
        description=card.get("description", ""),
        card_url=card_url,
        url=base,
        card=card,
    )


def _rank(task: TaskSpec, cards: list[dict]) -> list[AgentInfo]:
    """Rank candidate cards by skill-tag relevance to the task."""
    scored = keyword_score_candidates(task.text, cards)
    # tie-break on explicit skill_tag exact match
    def sort_key(c: dict) -> float:
        tags = [t.lower() for s in c.get("skills", []) for t in s.get("tags", [])]
        return 2.0 if task.skill_tag in tags else (1.0 if any(t in task.skill_tag for t in tags) else 0.0)

    scored.sort(key=lambda c: sort_key(c), reverse=True)
    return [_to_agent_info(c) for c in scored]


def _pick(ranked: list[AgentInfo]) -> AgentInfo | None:
    return ranked[0] if ranked else None


# --------------------------------------------------------------------------
# 1. Static
# --------------------------------------------------------------------------
class StaticStrategy(DiscoveryStrategy):
    """Compile-time knowledge: skill tag -> agent. Zero discovery cost."""

    name = "static"

    def __init__(self) -> None:
        self._map: dict[str, AgentInfo] = {}

    async def setup(self) -> None:
        for spec in build_fleet():
            info = AgentInfo(spec.name, spec.description, spec.card_url, spec.url)
            for tag in spec.skill_tags():
                self._map[tag] = info

    async def resolve(self, task: TaskSpec, *, exclude: set[str] | None = None) -> Resolution:
        start = time.perf_counter()
        seen: dict[str, AgentInfo] = {i.name: i for i in self._map.values()}
        candidates = list(seen.values())
        if exclude:
            candidates = [c for c in candidates if c.name not in exclude]
        discovery_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        agent = self._map.get(task.skill_tag)
        if exclude and agent and agent.name in exclude:
            agent = None
        if not agent and candidates:
            agent = _pick(_rank(task, [c.slim() for c in candidates]))
        selection_ms = (time.perf_counter() - start) * 1000
        return Resolution(self.name, task.id, agent, candidates, discovery_ms, selection_ms)


# --------------------------------------------------------------------------
# 2. Card discovery
# --------------------------------------------------------------------------
class CardDiscoveryStrategy(DiscoveryStrategy):
    """Fetch every known endpoint's Agent Card once, build a skill index.

    Real-world analogue: an orchestrator that fetches agent.json from the
    endpoints it is pointed at (like a WebFinger / well-known lookup).
    """

    name = "card_discovery"

    def __init__(self, base_urls: list[str] | None = None) -> None:
        self._base_urls = base_urls or [s.url for s in build_fleet()]
        self._cards: list[dict] = []
        self._tag_index: dict[str, list[dict]] = {}

    async def setup(self) -> None:
        for url in self._base_urls:
            try:
                card = await fetch_card(url)
                self._cards.append(card)
            except Exception as exc:
                logger.warning("card fetch failed for %s: %s", url, exc)
        self._tag_index = _index_by_tag(self._cards)

    async def resolve(self, task: TaskSpec, *, exclude: set[str] | None = None) -> Resolution:
        start = time.perf_counter()
        cards = list(self._cards)
        if exclude:
            cards = [c for c in cards if c["name"] not in exclude]
        discovery_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        ranked = _rank(task, cards)
        agent = _pick(ranked)
        selection_ms = (time.perf_counter() - start) * 1000
        return Resolution(self.name, task.id, agent, ranked, discovery_ms, selection_ms)


# --------------------------------------------------------------------------
# 3. Registry / skill search
# --------------------------------------------------------------------------
class RegistrySkillStrategy(DiscoveryStrategy):
    """Query a central Agent Directory per request (network discovery).

    Real-world analogue: Google Cloud Agent Registry skill-tag search.
    """

    name = "registry_skill"

    def __init__(self, registry_base: str, fallback_base_urls: list[str] | None = None) -> None:
        self._base = registry_base.rstrip("/")
        self._fallback_base_urls = fallback_base_urls or [s.url for s in build_fleet()]

    async def setup(self) -> None:
        # nothing local to prepare; the directory is populated externally
        return None

    async def _search(self, tag: str) -> list[dict]:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as hc:
            r = await hc.get(f"{self._base}/agents/search", params={"skill": tag})
            r.raise_for_status()
            return r.json().get("agents", [])

    async def resolve(self, task: TaskSpec, *, exclude: set[str] | None = None) -> Resolution:
        notes: list[str] = []
        start = time.perf_counter()
        cards: list[dict] = []
        try:
            cards = await self._search(task.skill_tag)
        except Exception as exc:
            notes.append(f"registry search failed ({exc}); falling back to full listing")
            try:
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as hc:
                    r = await hc.get(f"{self._base}/agents")
                    r.raise_for_status()
                    cards = r.json().get("agents", [])
            except Exception as exc2:
                notes.append(f"registry listing also failed ({exc2})")
                cards = []
        discovery_ms = (time.perf_counter() - start) * 1000
        if exclude:
            cards = [c for c in cards if c["name"] not in exclude]
        start = time.perf_counter()
        ranked = _rank(task, cards)
        agent = _pick(ranked)
        selection_ms = (time.perf_counter() - start) * 1000
        return Resolution(self.name, task.id, agent, ranked, discovery_ms, selection_ms, notes=notes)


# --------------------------------------------------------------------------
# 4. Cached discovery
# --------------------------------------------------------------------------
class CachedDiscoveryStrategy(CardDiscoveryStrategy):
    """Card discovery behind a TTL cache: miss=refetch, hit=near-zero cost.

    Demonstrates the latency-vs-staleness tradeoff: a cached card keeps
    pointing at an old endpoint until the TTL expires.
    """

    name = "cached"

    def __init__(self, base_urls: list[str] | None = None, ttl_s: float = CARD_CACHE_TTL_S) -> None:
        super().__init__(base_urls)
        self._ttl = ttl_s
        self._cache: dict[str, tuple[float, dict]] = {}  # base_url -> (ts, card)

    async def setup(self) -> None:
        # warm the cache
        for url in self._base_urls:
            try:
                card = await fetch_card(url)
                self._cache[url] = (time.time(), card)
                self._cards.append(card)
            except Exception as exc:
                logger.warning("warmup card fetch failed for %s: %s", url, exc)
        self._tag_index = _index_by_tag(self._cards)

    async def _refresh(self) -> bool:
        """Refetch cards whose TTL has expired. Returns True if anything changed."""
        changed = False
        now = time.time()
        for url in self._base_urls:
            ts, card = self._cache.get(url, (0.0, None))
            if now - ts >= self._ttl or card is None:
                try:
                    fresh = await fetch_card(url)
                    self._cache[url] = (time.time(), fresh)
                    self._cards = [c for c in self._cards if c.get("name") != fresh.get("name")]
                    self._cards.append(fresh)
                    changed = True
                except Exception as exc:
                    logger.warning("cache refresh failed for %s: %s", url, exc)
        self._tag_index = _index_by_tag(self._cards)
        return changed

    async def resolve(self, task: TaskSpec, *, exclude: set[str] | None = None) -> Resolution:
        cache_hit = all(
            (time.time() - ts) < self._ttl for ts, _ in self._cache.values()
        ) and bool(self._cards)
        start = time.perf_counter()
        await self._refresh()
        cards = list(self._cards)
        if exclude:
            cards = [c for c in cards if c["name"] not in exclude]
        discovery_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        ranked = _rank(task, cards)
        agent = _pick(ranked)
        selection_ms = (time.perf_counter() - start) * 1000
        return Resolution(self.name, task.id, agent, ranked, discovery_ms, selection_ms, cache_hit=cache_hit)


# --------------------------------------------------------------------------
# 5. LLM-reasoned routing
# --------------------------------------------------------------------------
class LLMReasonedStrategy(CardDiscoveryStrategy):
    """Use a free LLM (or mock) to pick the best agent from discovered cards."""

    name = "llm_reasoned"

    def __init__(
        self,
        llm: LLMClient | None = None,
        base_urls: list[str] | None = None,
    ) -> None:
        super().__init__(base_urls)
        self._llm = llm or LLMClient()

    async def resolve(self, task: TaskSpec, *, exclude: set[str] | None = None) -> Resolution:
        start = time.perf_counter()
        cards = list(self._cards)
        if exclude:
            cards = [c for c in cards if c["name"] not in exclude]
        discovery_ms = (time.perf_counter() - start) * 1000
        start = time.perf_counter()
        ranked = _rank(task, cards)
        # give the LLM the full card set (not pre-filtered), like a real dispatcher
        name, llm_result = await self._llm.pick_agent(task.text, [_card_json(c) for c in self._cards])
        selection_ms = (time.perf_counter() - start) * 1000
        agent = next((c for c in ranked if c.name == name), None)
        notes = [f"llm_mode={llm_result.mode}"]
        if llm_result.mode == "mock":
            # no live LLM -> the dispatcher falls back to the deterministic scorer
            agent = ranked[0] if ranked else None
            notes.append("scorer_fallback=keyword")
        elif agent is None:
            # LLM answered but with a name we don't recognise -> refuse
            agent = None
            notes.append("llm_reply_unmatched")
        return Resolution(
            self.name, task.id, agent, ranked, discovery_ms, selection_ms,
            tokens=llm_result.tokens, llm_mode=llm_result.mode, notes=notes,
        )


STRATEGIES = {
    "static": StaticStrategy,
    "card_discovery": CardDiscoveryStrategy,
    "registry_skill": RegistrySkillStrategy,
    "cached": CachedDiscoveryStrategy,
    "llm_reasoned": LLMReasonedStrategy,
}


def build_strategy(
    name: str, *, registry_base: str = "", llm: LLMClient | None = None
) -> DiscoveryStrategy:
    if name == "registry_skill":
        return RegistrySkillStrategy(registry_base)
    if name == "llm_reasoned":
        return LLMReasonedStrategy(llm=llm)
    return STRATEGIES[name]()