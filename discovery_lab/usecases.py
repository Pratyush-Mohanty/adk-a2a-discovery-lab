"""Use-case matrix: every strategy x every task set.

Turns the "accuracy is a tie" claim into a test. On well-tagged tasks all
methods should tie at 100%; on paraphrased and noisy tasks the deterministic
methods should degrade while semantic retrieval holds up.

Strategies compared here are the card-fetching ones (no per-request registry
network cost) plus static: static, card_discovery, bm25, semantic, hybrid.
llm_reasoned is only added when a live LLM endpoint is reachable (mock mode
falls back to the same keyword scorer as card_discovery, so it would be a
duplicate column).
"""

from __future__ import annotations

import asyncio
import logging

from .config import TASK_SETS, TASK_SET_DESCRIPTIONS, TaskSpec
from .llm_client import LLMClient
from .master import MasterAgent
from .metrics import ExperimentSummary, RunResult, summarize
from .strategies import (
    BM25Strategy,
    CardDiscoveryStrategy,
    DiscoveryStrategy,
    HybridStrategy,
    SemanticStrategy,
    StaticStrategy,
)

logger = logging.getLogger("discovery_lab.usecases")

MATRIX_STRATEGIES: list[tuple[str, type[DiscoveryStrategy]]] = [
    ("static", StaticStrategy),
    ("card_discovery", CardDiscoveryStrategy),
    ("bm25", BM25Strategy),
    ("semantic", SemanticStrategy),
    ("hybrid", HybridStrategy),
]


async def _run(strategy: DiscoveryStrategy, tasks: list[TaskSpec], experiment: str) -> list[RunResult]:
    await strategy.setup()
    master = MasterAgent(strategy)
    return await master.run_all(tasks, experiment)


async def run_matrix(llm: LLMClient | None = None) -> tuple[list[ExperimentSummary], list[RunResult]]:
    summaries: list[ExperimentSummary] = []
    all_runs: list[RunResult] = []

    strategies = list(MATRIX_STRATEGIES)
    llm = llm or LLMClient()
    if llm.mode != "mock":
        from .strategies import LLMReasonedStrategy

        strategies.append(("llm_reasoned", LLMReasonedStrategy))

    for set_name, tasks in TASK_SETS.items():
        for strat_name, cls in strategies:
            if strat_name == "llm_reasoned":
                strat = cls(llm=llm)
            else:
                strat = cls()
            experiment = f"matrix:{set_name}:{strat_name}"
            res = await _run(strat, list(tasks), experiment)
            all_runs += res
            summaries.append(summarize(experiment, res))

    return summaries, all_runs


def matrix_report(summaries: list[ExperimentSummary]) -> str:
    """Compact text table of the matrix for quick terminal inspection."""
    from collections import defaultdict

    rows: dict[str, dict[str, float]] = defaultdict(dict)
    for s in summaries:
        _prefix, set_name, strat = s.experiment.split(":")
        rows[set_name][strat] = s.accuracy * 100

    set_names = [name for name, _ in TASK_SETS.items()]
    strat_names = [name for name, _ in MATRIX_STRATEGIES]
    lines = []
    header = f"{'task set':<12}" + "".join(f"{s:>14}" for s in strat_names)
    lines.append(header)
    for name in set_names:
        lines.append(
            f"{name:<12}" + "".join(f"{rows[name].get(s, 0.0):>12.0f}%  " for s in strat_names)
        )
    lines.append("")
    for name in set_names:
        lines.append(f"  {name}: {TASK_SET_DESCRIPTIONS[name]}")
    return "\n".join(lines)


async def main_matrix() -> tuple[list[ExperimentSummary], list[RunResult]]:
    return await run_matrix()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    summaries, _ = asyncio.run(main_matrix())
    print(matrix_report(summaries))