"""The sub-agent fleet.

Four deterministic "skill workers". Each is served as a real A2A server with
its own Agent Card. The handler functions are pure Python (no LLM) so the
whole lab runs offline and results are reproducible.
"""

from __future__ import annotations

import asyncio
import json
import re

from .config import AGENT_BASE_LATENCY_MS, AgentSpec, SkillSpec


# --------------------------------------------------------------------------
# Handlers (deterministic, no LLM). text -> text
# --------------------------------------------------------------------------
def _summarize(text: str) -> str:
    words = text.split()
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    head = " ".join(sentences[:2]) or text.strip()
    total = len(words)
    return (
        f"[summary] Word count: {total}. Key points: {head} "
        f"(kept the leading {len(sentences[:2])} of {len(sentences)} sentences)."
    )


_WORD_MAP = {
    "hello": {"spanish": "hola", "french": "bonjour", "hindi": "namaste"},
    "good": {"spanish": "bueno", "french": "bon", "hindi": "achha"},
    "morning": {"spanish": "manana", "french": "matin", "hindi": "subah"},
    "thank": {"spanish": "gracias", "french": "merci", "hindi": "dhanyavaad"},
    "you": {"spanish": "tu", "french": "vous", "hindi": "aap"},
    "very": {"spanish": "muy", "french": "tres", "hindi": "bahut"},
    "much": {"spanish": "mucho", "french": "beaucoup", "hindi": "zyada"},
    "where": {"spanish": "donde", "french": "ou", "hindi": "kahan"},
    "is": {"spanish": "es", "french": "est", "hindi": "hai"},
    "nearest": {"spanish": "mas cercano", "french": "le plus proche", "hindi": "sabse nazdeek"},
    "railway": {"spanish": "ferrocarril", "french": "chemin de fer", "hindi": "rail"},
    "station": {"spanish": "estacion", "french": "gare", "hindi": "station"},
}


def _translate(text: str) -> str:
    low = text.lower()
    target = "spanish"
    for lang in ("spanish", "french", "hindi"):
        if lang in low:
            target = lang
            break
    tokens = re.findall(r"[\w']+", low)
    translated = " ".join(_WORD_MAP.get(w, {}).get(target, w) for w in tokens)
    return f"[translated -> {target}] {translated}"


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(r"\+?[\d-]{7,}")
_DATE_RE = re.compile(r"(?:19|20)\d{2}[-/]\d{1,2}[-/]\d{1,2}|\b\d{1,2}(?:st|nd|rd|th)?\s+\w+\s+\d{4}\b", re.I)
_MONEY_RE = re.compile(r"[$]\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?")


def _extract(text: str) -> str:
    return json.dumps(
        {
            "emails": _EMAIL_RE.findall(text),
            "phones": [p for p in _PHONE_RE.findall(text) if len(re.sub(r"\D", "", p)) >= 7],
            "dates": _DATE_RE.findall(text),
            "money": _MONEY_RE.findall(text),
        },
        indent=2,
    )


_POSITIVE = ("great", "awesome", "good", "delicious", "fast", "clean", "loved", "amazing")
_NEGATIVE = ("awful", "cold", "bad", "slow", "dirty", "hated", "terrible", "broken")
_URGENT = ("down", "crash", "blocked", "urgent", "outage", "p0", "emergency", "failed", "paying")
_OPS = ("server", "deploy", "ticket", "log", "db", "crash", "outage", "restart")


def _classify(text: str) -> str:
    low = text.lower()
    sentiment = "positive" if any(w in low for w in _POSITIVE) else (
        "negative" if any(w in low for w in _NEGATIVE) else "neutral"
    )
    urgency = "high" if any(w in low for w in _URGENT) else "low"
    topic = "ops" if any(w in low for w in _OPS) else "general"
    return json.dumps({"sentiment": sentiment, "urgency": urgency, "topic": topic}, indent=2)


# --------------------------------------------------------------------------
# Fleet catalog
# --------------------------------------------------------------------------
def build_fleet() -> tuple[AgentSpec, ...]:
    return (
        AgentSpec(
            name="summarizer",
            description="Produces concise summaries and tl;dr versions of long text.",
            port=8101,
            skills=(
                SkillSpec("summarize", "Text Summarization", "Condenses long text into key points", ("summarize", "summary")),
                SkillSpec("tldr", "TL;DR", "One-line tl;dr of a document", ("tl;dr", "concise")),
            ),
            handler=_summarize,
        ),
        AgentSpec(
            name="translator",
            description="Translates text between English, Spanish, French and Hindi.",
            port=8102,
            skills=(
                SkillSpec("translate", "Translation", "Translates text to a requested language", ("translate", "language")),
                SkillSpec("multiling", "Multilingual", "Handles es/fr/hi input and output", ("multilingual", "i18n")),
            ),
            handler=_translate,
        ),
        AgentSpec(
            name="extractor",
            description="Extracts structured data (emails, phones, dates, money, entities) from text.",
            port=8103,
            skills=(
                SkillSpec("extract", "Data Extraction", "Pulls entities and fields into JSON", ("extract", "structured", "json")),
                SkillSpec("pii", "PII Detection", "Finds contact info and identifiers", ("pii", "entities")),
            ),
            handler=_extract,
        ),
        AgentSpec(
            name="classifier",
            description="Classifies text: sentiment, urgency and topic labeling.",
            port=8104,
            skills=(
                SkillSpec("classify", "Classification", "Sentiment / urgency / topic classification", ("sentiment", "classify")),
                SkillSpec("label", "Ticket Labeling", "Tags support tickets with categories", ("label", "urgency", "ops")),
            ),
            handler=_classify,
        ),
    )


def agent_by_name(name: str) -> AgentSpec:
    for a in build_fleet():
        if a.name == name:
            return a
    raise KeyError(f"unknown agent {name!r}")


async def simulate_work(base_ms: float = AGENT_BASE_LATENCY_MS) -> None:
    """Small artificial delay so discovery/routing timings are measurable."""
    await asyncio.sleep(base_ms / 1000.0)