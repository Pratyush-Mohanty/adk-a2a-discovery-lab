"""Chart generation for experiment summaries.

Uses constrained_layout so titles, legends, and value labels never overlap,
and a 200 dpi output for crisp Medium/blog embeds.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from .metrics import ExperimentSummary

PALETTE = ["#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3", "#937860"]
DPI = 200


def _tick(s: str) -> str:
    """Human-friendly tick label for a strategy/experiment name."""
    return s.replace("_", " ")


def plot_summary(summaries: list[ExperimentSummary], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = [_tick(s.experiment) for s in summaries]
    acc = [s.accuracy * 100 for s in summaries]
    disc = [s.mean_discovery_ms for s in summaries]
    total = [s.mean_total_ms for s in summaries]
    tokens = [s.total_tokens for s in summaries]

    # --- accuracy -----------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    bars = ax.bar(labels, acc, color="#4c72b0")
    ax.set_ylabel("selection accuracy (%)")
    ax.set_ylim(0, 108)
    ax.set_title("Master-agent discovery: selection accuracy by strategy")
    ax.tick_params(axis="x", rotation=30, labelsize=9)
    for b, v in zip(bars, acc):
        ax.annotate(
            f"{v:.0f}%",
            (b.get_x() + b.get_width() / 2, v),
            textcoords="offset points",
            xytext=(0, 4),
            ha="center",
            fontsize=8,
        )
    fig.savefig(out_dir / "accuracy.png", dpi=DPI)
    plt.close(fig)

    # --- latency (log scale so ms and s bars are both visible) --------
    import numpy as np

    x = np.arange(len(labels))
    w = 0.4
    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    ax.bar(x - w / 2, disc, w, label="discovery", color="#dd8452")
    ax.bar(x + w / 2, total, w, label="total (discover+select+route)", color="#55a868")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, fontsize=9)
    ax.set_yscale("log")
    ax.set_ylabel("mean ms (log scale)")
    ax.set_title("Master-agent discovery: latency (log scale)")
    ax.grid(axis="y", which="both", alpha=0.25)
    ax.legend(fontsize=9)
    fig.savefig(out_dir / "latency.png", dpi=DPI)
    plt.close(fig)

    # --- token cost -----------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 4.5), constrained_layout=True)
    bars = ax.bar(labels, tokens, color="#c44e52")
    ax.set_ylabel("total tokens used")
    ax.set_title("Master-agent discovery: LLM token cost")
    ax.tick_params(axis="x", rotation=30, labelsize=9)
    ax.margins(y=0.12)
    for b, v in zip(bars, tokens):
        if v > 0:
            ax.annotate(
                f"{v:,}",
                (b.get_x() + b.get_width() / 2, v),
                textcoords="offset points",
                xytext=(0, 4),
                ha="center",
                fontsize=8,
            )
    fig.savefig(out_dir / "tokens.png", dpi=DPI)
    plt.close(fig)

    print(f"  charts written to {out_dir}/*.png")


def plot_usecase_matrix(summaries: list[ExperimentSummary], out_dir: Path) -> None:
    """Grouped bar charts for the strategy x use-case matrix."""
    from collections import defaultdict

    import numpy as np

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    sets: dict[str, dict[str, float]] = defaultdict(dict)
    sel: dict[str, dict[str, float]] = defaultdict(dict)
    tok: dict[str, dict[str, int]] = defaultdict(dict)
    for s in summaries:
        _prefix, set_name, strat = s.experiment.split(":")
        sets[set_name][strat] = s.accuracy * 100
        sel[set_name][strat] = s.mean_selection_ms
        tok[set_name][strat] = s.total_tokens

    set_names = list(sets.keys())
    strat_names = list(next(iter(sets.values())).keys())
    cmap = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(strat_names)}

    x = np.arange(len(set_names))
    width = 0.8 / len(strat_names)

    def _bars(ax, data, fmt=None):
        for i, s in enumerate(strat_names):
            vals = [data[n].get(s, 0.0) for n in set_names]
            xs = x - 0.4 + (i + 0.5) * width
            bars = ax.bar(xs, vals, width, label=s, color=cmap[s])
            if fmt:
                for bx, v in zip(bars, vals):
                    ax.annotate(
                        fmt(v),
                        (bx.get_x() + bx.get_width() / 2, v),
                        textcoords="offset points",
                        xytext=(0, 3),
                        ha="center",
                        fontsize=7,
                    )

    # --- accuracy per use case ------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
    _bars(ax, sets, lambda v: f"{v:.0f}")
    ax.set_xticks(x)
    ax.set_xticklabels(set_names, fontsize=10)
    ax.set_ylabel("selection accuracy (%)")
    ax.set_ylim(0, 108)
    ax.set_title("Discovery accuracy by use case (strategy x task set)")
    ax.legend(ncol=len(strat_names), fontsize=8, loc="upper center")
    fig.savefig(out_dir / "accuracy_by_usecase.png", dpi=DPI)
    plt.close(fig)

    # --- selection latency per use case -----------------------------------
    fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
    _bars(ax, sel)
    ax.set_xticks(x)
    ax.set_xticklabels(set_names, fontsize=10)
    ax.set_yscale("log")
    ax.set_ylabel("mean selection time (ms, log scale)")
    ax.set_title("Selection latency by use case (log scale)")
    ax.grid(axis="y", which="both", alpha=0.25)
    ax.legend(ncol=len(strat_names), fontsize=8, loc="upper center")
    fig.savefig(out_dir / "selection_by_usecase.png", dpi=DPI)
    plt.close(fig)

    # --- token cost per use case -----------------------------------------
    fig, ax = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
    _bars(ax, tok)
    ax.set_xticks(x)
    ax.set_xticklabels(set_names, fontsize=10)
    ax.set_ylabel("total tokens used (12 tasks)")
    ax.set_title("Token cost by use case")
    ax.margins(y=0.12)
    ax.legend(ncol=len(strat_names), fontsize=8, loc="upper center")
    fig.savefig(out_dir / "tokens_by_usecase.png", dpi=DPI)
    plt.close(fig)

    print(f"  use-case matrix charts written to {out_dir}/*_by_usecase.png")