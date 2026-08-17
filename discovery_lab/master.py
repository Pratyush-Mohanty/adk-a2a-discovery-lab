"""The Master agent: discover -> select -> route, recording metrics.

Handles network failures with a single retry against a different candidate
(strategy re-resolves excluding the failed agent) — this is the "stale card
/ agent down" behaviour studied in the failure experiment.
"""

from __future__ import annotations

import logging
import time

from .a2a_client import send_text
from .config import TaskSpec
from .metrics import RunResult
from .strategies import DiscoveryStrategy

logger = logging.getLogger("discovery_lab.master")


class MasterAgent:
    def __init__(self, strategy: DiscoveryStrategy, *, name: str = "master") -> None:
        self.strategy = strategy
        self.name = name
        self.results: list[RunResult] = []

    async def handle(self, task: TaskSpec, experiment: str = "exp") -> RunResult:
        t_start = time.perf_counter()

        resolution = await self.strategy.resolve(task)
        chosen = resolution.agent
        result = RunResult(
            experiment=experiment,
            strategy=resolution.strategy,
            task_id=task.id,
            task_skill_tag=task.skill_tag,
            expected_agent=task.expected_agent,
            chosen_agent=chosen.name if chosen else None,
            discovery_ms=resolution.discovery_ms,
            selection_ms=resolution.selection_ms,
            candidates_found=len(resolution.candidates),
            tokens_used=resolution.tokens,
            cache_hit=resolution.cache_hit,
            llm_mode=resolution.llm_mode,
            notes="; ".join(resolution.notes),
        )

        if chosen is None:
            result.error = "no candidate selected"
            result.total_ms = (time.perf_counter() - t_start) * 1000
            result.correct = False
            self.results.append(result)
            return result

        # ---- route ------------------------------------------------------
        t_r = time.perf_counter()
        try:
            reply, _elapsed = await send_text(chosen.url, task.text)
            result.routing_ms = (time.perf_counter() - t_r) * 1000
            result.reply = reply[:120]
        except Exception as exc:
            logger.warning("routing to %s failed: %s", chosen.name, exc)
            # ---- failure: re-discover excluding the dead agent -----------
            retry = await self.strategy.resolve(task, exclude={chosen.name})
            alt = retry.agent
            result.fallback_used = True
            if alt is None:
                result.error = f"route failed ({exc}) and no fallback candidate"
                result.total_ms = (time.perf_counter() - t_start) * 1000
                result.correct = False
                self.results.append(result)
                return result
            try:
                reply, _elapsed = await send_text(alt.url, task.text)
                result.routing_ms = (time.perf_counter() - t_r) * 1000
                result.chosen_agent = alt.name
                result.reply = reply[:120]
                result.discovery_ms = retry.discovery_ms
                result.selection_ms = retry.selection_ms
            except Exception as exc2:
                result.error = f"route + fallback failed ({exc}; {exc2})"
                result.routing_ms = (time.perf_counter() - t_r) * 1000
                result.total_ms = (time.perf_counter() - t_start) * 1000
                result.correct = False
                self.results.append(result)
                return result

        result.total_ms = (time.perf_counter() - t_start) * 1000
        result.correct = result.chosen_agent == task.expected_agent
        self.results.append(result)
        return result

    async def run_all(self, tasks: list[TaskSpec], experiment: str) -> list[RunResult]:
        for task in tasks:
            await self.handle(task, experiment=experiment)
        return list(self.results)