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


# --------------------------------------------------------------------------
# Use-case task sets. Each set stresses a different routing condition.
#
#   well_tagged : task text + declared skill tag align with the fleet's cards.
#                 The "easy" case where every method reaches 100%.
#   paraphrased : same intents, reworded so the request shares no vocabulary
#                 with the skill tags, and skill_tag is empty ("sparse
#                 metadata"). Lexical methods degrade; semantic methods win.
#   noisy       : compound tasks whose text also contains keywords from the
#                 WRONG agents (distractors), skill_tag empty. Tests ranking
#                 robustness against multi-intent / overlapping vocabulary.
#
# skill_tag="" means "the orchestrator could not map this request to a tag"
# -- a realistic scenario the tool-retrieval literature (e.g. ToolDreamer,
# Tool-to-Agent Retrieval) calls out: user requests rarely align with the
# tag vocabulary.
# --------------------------------------------------------------------------
def _ts(id: str, text: str, agent: str, tag: str, note: str = "") -> TaskSpec:
    return TaskSpec(id, text, agent, tag, note)


PARAPHRASED_TASKS: tuple[TaskSpec, ...] = (
    _ts("p01", "condense this scene into its essentials: a cat sat on a mat, a dog barked, and the neighbors watched", "summarizer", "", "no tag vocab"),
    _ts("p02", "give me the short version of how quantum computers use superposition to process many states at once", "summarizer", "", "no tag vocab"),
    _ts("p03", "tighten this up for a tweet: under the cap theorem distributed systems trade consistency for availability when networks split", "summarizer", "", "no tag vocab"),
    _ts("p04", "say this greeting in the language spoken in madrid: hello good morning", "translator", "", "no tag vocab"),
    _ts("p05", "rewrite this in the tongue of paris: thank you very much", "translator", "", "no tag vocab"),
    _ts("p06", "how would you voice this in the dialect used around mumbai: where is the nearest railway station", "translator", "", "no tag vocab"),
    _ts("p07", "pull the contact details and the sum out of this note: reach jane.doe@example.com before 2026-12-31 and send $1,299.50", "extractor", "", "no tag vocab"),
    _ts("p08", "what identifiers are buried in this message: call +91-98765-43210 or write info@acme.io", "extractor", "", "no tag vocab"),
    _ts("p09", "enumerate the people, places, and dates mentioned: Dr. Reyes reviewed the MRI on April 3rd at St. Mary's hospital", "extractor", "", "no tag vocab"),
    _ts("p10", "read the mood in this review: the service was awful and the food arrived cold", "classifier", "", "no tag vocab"),
    _ts("p11", "judge how time-sensitive this is: the production database is down and customers cannot complete payments", "classifier", "", "no tag vocab"),
    _ts("p12", "categorize what happened here: the server keeps crashing right after the midnight deploy", "classifier", "", "no tag vocab"),
)

NOISY_TASKS: tuple[TaskSpec, ...] = (
    _ts("n01", "summarize the email thread and also check the dates: the meeting moved and several deadlines slipped like 2026-12-31", "summarizer", "", "distractor: extract dates"),
    _ts("n02", "summarize this for the ticket: the build server crashed at midnight and the mood in the chat turned negative", "summarizer", "", "distractors: crash/mood/sentiment"),
    _ts("n03", "give a tl;dr and also flag the sentiment: the outage lasted hours and users were very angry", "summarizer", "", "distractor: sentiment"),
    _ts("n04", "translate this to spanish and also pull out the phone number: call +91-98765-43210 hello good morning", "translator", "", "distractor: phone"),
    _ts("n05", "translate to french and then classify the topic: the deploy failed again, thank you very much", "translator", "", "distractor: ops topic"),
    _ts("n06", "convert to hindi and extract the money amounts: pay $1,299.50 for the rail tickets, where is the nearest station", "translator", "", "distractor: money"),
    _ts("n07", "extract the pii and then summarize the story: jane.doe@example.com paid the bill, the dog barked loudly", "extractor", "", "distractor: summarize"),
    _ts("n08", "find the emails and dates, and tell me the sentiment: info@acme.io was delayed until April 3rd which made everyone angry", "extractor", "", "distractor: sentiment"),
    _ts("n09", "pull the entities and translate the greeting: Dr. Reyes is at St. Mary's hospital, hello good morning", "extractor", "", "distractor: translate"),
    _ts("n10", "classify the sentiment and then summarize the review: the service was awful and the food arrived cold", "classifier", "", "distractor: summarize"),
    _ts("n11", "classify the urgency and extract the dates: the db is down until 2026-12-31 and paying is blocked", "classifier", "", "distractor: extract dates"),
    _ts("n12", "tag this ticket and translate the phrase: server crashing after the deploy, thank you very much", "classifier", "", "distractor: translate"),
)

TASK_SETS: dict[str, tuple[TaskSpec, ...]] = {
    "well_tagged": TASKS,
    "paraphrased": PARAPHRASED_TASKS,
    "noisy": NOISY_TASKS,
}

TASK_SET_DESCRIPTIONS = {
    "well_tagged": "task text + skill tag align with the fleet cards (easy case)",
    "paraphrased": "reworded requests, no shared vocabulary, no usable tag",
    "noisy": "compound requests with wrong-agent keywords (distractors)",
}