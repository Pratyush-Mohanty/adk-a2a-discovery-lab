"""Central configuration: hosts, ports, fleet catalog, benchmark task set."""

from __future__ import annotations

from dataclasses import dataclass, field

HOST = "127.0.0.1"

REGISTRY_PORT = 9000
REGISTRY_URL = f"http://{HOST}:{REGISTRY_PORT}"

# Base latency (ms) each skill agent simulates before replying. Keeps
# routing/discovery timings meaningful instead of ~0.
AGENT_BASE_LATENCY_MS = 8.0

# Card fetch timeout + per-request timeout for A2A RPC calls.
HTTP_TIMEOUT_S = 15.0

# How long a cached agent card is trusted before it must be re-fetched.
CARD_CACHE_TTL_S = 30.0


@dataclass(frozen=True)
class SkillSpec:
    id: str
    name: str
    description: str
    tags: tuple[str, ...]
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentSpec:
    name: str
    description: str
    port: int
    skills: tuple[SkillSpec, ...]
    handler: object = None  # callable text -> text, injected in fleet.py

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}/"

    @property
    def card_url(self) -> str:
        return f"{self.url}.well-known/agent-card.json"

    def skill_tags(self) -> list[str]:
        out: list[str] = []
        for s in self.skills:
            out.extend(s.tags)
        return out


@dataclass(frozen=True)
class TaskSpec:
    id: str
    text: str
    expected_agent: str  # agent name that SHOULD handle this task
    skill_tag: str       # the skill tag the task maps to
    note: str = ""


# --------------------------------------------------------------------------
# The benchmark task set: 12 tasks, 3 per agent. expected_agent drives the
# accuracy metric — did the master route to the right sub-agent?
# --------------------------------------------------------------------------
TASKS: tuple[TaskSpec, ...] = (
    TaskSpec("t01", "the cat sat on the mat and the dog barked loudly while the neighbors watched", "summarizer", "summarize", "long sentence -> summarize"),
    TaskSpec("t02", "quantum computing uses qubits that can be in superposition states enabling parallel computation across many dimensions", "summarizer", "tl;dr", "dense -> tl;dr"),
    TaskSpec("t03", "distributed systems sacrifice consistency for availability under the cap theorem when networks partition", "summarizer", "concise", "dense -> concise"),
    TaskSpec("t04", "translate this greeting to spanish: hello good morning", "translator", "translate", "en->es"),
    TaskSpec("t05", "please translate the following to french: thank you very much", "translator", "language", "en->fr"),
    TaskSpec("t06", "convert to hindi: where is the nearest railway station", "translator", "multilingual", "en->hi"),
    TaskSpec("t07", "extract emails dates and money from: contact jane.doe@example.com by 2026-12-31 and pay $1,299.50", "extractor", "extract", "entities"),
    TaskSpec("t08", "find phone numbers and emails in: call +91-98765-43210 or write info@acme.io today", "extractor", "structured", "PII"),
    TaskSpec("t09", "pull out all named entities and dates: Dr. Reyes reviewed the MRI on April 3rd at St. Mary's hospital", "extractor", "json", "NER"),
    TaskSpec("t10", "classify the sentiment of this review: the service was awful and the food arrived cold", "classifier", "sentiment", "negative"),
    TaskSpec("t11", "classify urgency: the production database is down and customers are blocked from paying", "classifier", "urgency", "high urgency"),
    TaskSpec("t12", "tag this ticket: server keeps crashing after the new deploy at midnight", "classifier", "label", "ops ticket"),
)

# Skill tags we expect to see in the fleet. Used by strategies as the
# vocabulary for keyword matching.
KNOWN_SKILL_TAGS = (
    "summarize", "tl;dr", "concise",
    "translate", "language", "multilingual",
    "extract", "structured", "json",
    "sentiment", "urgency", "label",
)