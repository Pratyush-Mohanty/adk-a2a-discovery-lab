"""The experiment ladder. Each experiment isolates ONE discovery question.

  ex1_static        baseline: compile-time knowledge, no discovery cost
  ex2_card_discovery  runtime Agent Card fetches -> skill index
  ex3_registry_skill  per-request skill-tag search against a directory
  ex4_cached          TTL cache: hit vs miss latency, amortized cost
  ex5_failure         agent down / stale card -> fallback + recovery
  ex6_llm_reasoned    free-LLM routing vs deterministic scoring + cost
"""

from __future__ import annotations

import asyncio
import logging
import time

from .config import REGISTRY_URL, TASKS, TaskSpec
from .fleet import build_fleet
from .launch import FleetRuntime
from .llm_client import LLMClient
from .master import MasterAgent
from .metrics import ExperimentSummary, RunResult, summarize
from .strategies import (
    CachedDiscoveryStrategy,
    CardDiscoveryStrategy,
    DiscoveryStrategy,
    LLMReasonedStrategy,
    RegistrySkillStrategy,
    StaticStrategy,
)

logger = logging.getLogger("discovery_lab.experiments")

ALL_TASKS = list(TASKS)


def tasks_for(agent: str) -> list[TaskSpec]:
    return [t for t in ALL_TASKS if t.expected_agent == agent]


async def _run(strategy: DiscoveryStrategy, tasks: list[TaskSpec], experiment: str) -> list[RunResult]:
    await strategy.setup()
    master = MasterAgent(strategy)
    return await master.run_all(tasks, experiment)


async def run_experiments(
    runtime: FleetRuntime, *, llm: LLMClient | None = None
) -> tuple[list[ExperimentSummary], list[RunResult]]:
    summaries: list[ExperimentSummary] = []
    all_runs: list[RunResult] = []

    # --- ex1: static ----------------------------------------------------
    res = await _run(StaticStrategy(), ALL_TASKS, "ex1_static")
    all_runs += res
    summaries.append(summarize("ex1_static", res))

    # --- ex2: card discovery --------------------------------------------
    res = await _run(CardDiscoveryStrategy(), ALL_TASKS, "ex2_card_discovery")
    all_runs += res
    summaries.append(summarize("ex2_card_discovery", res))

    # --- ex3: registry skill search --------------------------------------
    res = await _run(RegistrySkillStrategy(REGISTRY_URL), ALL_TASKS, "ex3_registry_skill")
    all_runs += res
    summaries.append(summarize("ex3_registry_skill", res))

    # --- ex4: cached (two passes to see miss -> hit amortization) --------
    cached = CachedDiscoveryStrategy()
    await cached.setup()
    master = MasterAgent(cached)
    pass1 = await master.run_all(ALL_TASKS, "ex4_cached")
    pass2 = await master.run_all(ALL_TASKS, "ex4_cached")
    all_runs += pass1 + pass2
    summaries.append(summarize("ex4_cached", pass1))
    summaries.append(summarize("ex4_cached_pass2", pass2))

    # --- ex5: failure (translator goes down, then recovers) --------------
    # 5a: card was known before the outage -> route fails -> fallback
    strat_known = CardDiscoveryStrategy()
    await strat_known.setup()
    await runtime.stop_agent("translator")
    await asyncio.sleep(0.3)
    master = MasterAgent(strat_known)
    res_down = await master.run_all(tasks_for("translator"), "ex5_failure_down")
    all_runs += res_down
    summaries.append(summarize("ex5_failure_down", res_down))

    # 5b: discovery starts fresh -> the directory never sees the translator
    #     -> master silently routes to a wrong agent (no error raised)
    res_vanished = await _run(CardDiscoveryStrategy(), tasks_for("translator"), "ex5_failure_vanished")
    all_runs += res_vanished
    summaries.append(summarize("ex5_failure_vanished", res_vanished))

    await runtime.start_agent(next(s for s in build_fleet() if s.name == "translator"))
    await asyncio.sleep(0.3)
    res_back = await _run(CardDiscoveryStrategy(), tasks_for("translator"), "ex5_recovery")
    all_runs += res_back
    summaries.append(summarize("ex5_recovery", res_back))

    # --- ex6: LLM-reasoned routing ---------------------------------------
    llm = llm or LLMClient()
    res = await _run(LLMReasonedStrategy(llm=llm), ALL_TASKS, "ex6_llm_reasoned")
    all_runs += res
    summaries.append(summarize("ex6_llm_reasoned", res))

    return summaries, all_runs


async def run_single(name: str, *, llm: LLMClient | None = None) -> list[RunResult]:
    """Run one strategy over all tasks (for `--strategy X`)."""
    from .strategies import build_strategy

    strategy = build_strategy(name, registry_base=REGISTRY_URL, llm=llm)
    return await _run(strategy, ALL_TASKS, f"cli_{name}")