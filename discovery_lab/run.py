"""CLI entry point.

Usage (from the project root, venv active):

  py -m discovery_lab.run                  # full experiment ladder
  py -m discovery_lab.run --strategy llm_reasoned
  py -m discovery_lab.run --no-plot
  py -m discovery_lab.run --out experiments/run_2026

`--strategy X` runs one strategy over all 12 tasks and skips the ladder.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .config import TASKS
from .experiments import ALL_TASKS, run_experiments, run_single
from .launch import FleetRuntime
from .llm_client import LLMClient
from .metrics import ExperimentSummary, RunResult, summarize
from .plot import plot_summary, plot_usecase_matrix
from .usecases import matrix_report, run_matrix

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _save(out_dir: Path, name: str, data) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  saved {path}")


async def _main(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    llm = LLMClient()

    runtime = FleetRuntime()
    await runtime.start_fleet()
    await runtime.start_registry()
    try:
        if args.strategy:
            runs = await run_single(args.strategy, llm=llm)
            summary = summarize(f"cli_{args.strategy}", runs)
            _save(out_dir, "summary", summary.to_dict())
            _save(out_dir, "runs", [r.to_dict() for r in runs])
            print(summary.to_dict())
            if args.plot and runs:
                plot_summary([summary], out_dir)
            return

        summaries, all_runs = await run_experiments(runtime, llm=llm)
        _save(out_dir, "summary", [s.to_dict() for s in summaries])
        _save(out_dir, "runs", [r.to_dict() for r in all_runs])
        for s in summaries:
            print(s.to_dict())
        if args.plot and summaries:
            plot_summary(summaries, out_dir)

        # Use-case matrix: strategy x task set (well-tagged / paraphrased / noisy)
        matrix_summaries, matrix_runs = await run_matrix(llm=llm)
        _save(out_dir, "matrix_summary", [s.to_dict() for s in matrix_summaries])
        _save(out_dir, "matrix_runs", [r.to_dict() for r in matrix_runs])
        print("\n--- use-case matrix (accuracy % by task set) ---")
        print(matrix_report(matrix_summaries))
        if args.plot and matrix_summaries:
            plot_usecase_matrix(matrix_summaries, out_dir)
    finally:
        await runtime.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="ADK/A2A master-agent discovery lab")
    parser.add_argument("--strategy", default=None, help="run a single strategy instead of the full ladder")
    parser.add_argument("--out", default="experiments", help="output directory for JSON + charts")
    parser.add_argument("--no-plot", action="store_true", help="skip chart generation")
    args = parser.parse_args()
    args.plot = not args.no_plot
    asyncio.run(_main(args))


if __name__ == "__main__":
    main()