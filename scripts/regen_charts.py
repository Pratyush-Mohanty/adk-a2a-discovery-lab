"""Regenerate all charts from the saved experiment JSON (no lab re-run).

This keeps the charts in sync with docs/ numbers without re-running the
experiments (which would change latency measurements and break the article).

    py scripts/regen_charts.py            # charts only
    py scripts/regen_charts.py --all      # charts + architecture + table PNGs
"""
import json
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "experiments"

sys.path.insert(0, str(ROOT))

from discovery_lab.metrics import ExperimentSummary  # noqa: E402
from discovery_lab.plot import plot_summary, plot_usecase_matrix  # noqa: E402


def main() -> None:
    summary_path = OUT / "summary.json"
    matrix_path = OUT / "matrix_summary.json"

    summaries = [
        ExperimentSummary(**d)
        for d in json.loads(summary_path.read_text(encoding="utf-8"))
    ]
    matrix = [
        ExperimentSummary(**d)
        for d in json.loads(matrix_path.read_text(encoding="utf-8"))
    ]

    plot_summary(summaries, OUT)
    plot_usecase_matrix(matrix, OUT)
    print("charts regenerated from saved JSON")

    if "--all" in sys.argv:
        subprocess.run(
            [sys.executable, "scripts/draw_architecture.py"], cwd=ROOT, check=True
        )
        subprocess.run(
            [sys.executable, "scripts/tables_to_png.py"], cwd=ROOT, check=True
        )
        print("architecture + table PNGs regenerated")


if __name__ == "__main__":
    main()