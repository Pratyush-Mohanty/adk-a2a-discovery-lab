"""Result types recorded for every task routed by the Master."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RunResult:
    experiment: str
    strategy: str
    task_id: str
    task_skill_tag: str
    expected_agent: str
    chosen_agent: str | None = None
    correct: bool | None = None
    discovery_ms: float = 0.0
    selection_ms: float = 0.0
    routing_ms: float = 0.0
    total_ms: float = 0.0
    candidates_found: int = 0
    tokens_used: int = 0
    cache_hit: bool = False
    fallback_used: bool = False
    llm_mode: str | None = None
    error: str | None = None
    reply: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class ExperimentSummary:
    experiment: str
    strategy: str
    n_tasks: int
    accuracy: float
    mean_discovery_ms: float
    mean_selection_ms: float
    mean_routing_ms: float
    mean_total_ms: float
    total_tokens: int
    cache_hits: int
    fallbacks: int
    errors: int
    llm_mode: str | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def summarize(experiment: str, results: list[RunResult]) -> ExperimentSummary:
    n = len(results)
    correct = sum(1 for r in results if r.correct)
    def mean(key: str) -> float:
        vals = [getattr(r, key) for r in results if getattr(r, key) is not None]
        return (sum(vals) / len(vals)) if vals else 0.0

    modes = {r.llm_mode for r in results if r.llm_mode}
    return ExperimentSummary(
        experiment=experiment,
        strategy=results[0].strategy if results else "?",
        n_tasks=n,
        accuracy=(correct / n) if n else 0.0,
        mean_discovery_ms=mean("discovery_ms"),
        mean_selection_ms=mean("selection_ms"),
        mean_routing_ms=mean("routing_ms"),
        mean_total_ms=mean("total_ms"),
        total_tokens=sum(r.tokens_used for r in results),
        cache_hits=sum(1 for r in results if r.cache_hit),
        fallbacks=sum(1 for r in results if r.fallback_used),
        errors=sum(1 for r in results if r.error),
        llm_mode=next(iter(modes), None),
    )