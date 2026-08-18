"""Chart generation for experiment summaries."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from .metrics import ExperimentSummary
def plot_summary(summaries: list[ExperimentSummary], out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = [s.experiment for s in summaries]
    acc = [s.accuracy * 100 for s in summaries]
    disc = [s.mean_discovery_ms for s in summaries]
    total = [s.mean_total_ms for s in summaries]
    tokens = [s.total_tokens for s in summaries]

    # --- accuracy -----------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(labels, acc, color="#4c72b0")
    ax.set_ylabel("selection accuracy (%)")
    ax.set_ylim(0, 105)
    ax.set_title("Master-agent discovery: selection accuracy by strategy")
    ax.tick_params(axis="x", rotation=30)
    for i, v in enumerate(acc):
        ax.text(i, v + 1, f"{v:.0f}%", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "accuracy.png", dpi=120)
    plt.close(fig)

    # --- latency -------------------------------------------------------
    import numpy as np

    x = np.arange(len(labels))
    w = 0.4
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(x - w / 2, disc, w, label="discovery", color="#dd8452")
    ax.bar(x + w / 2, total, w, label="total (discover+select+route)", color="#55a868")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30)
    ax.set_ylabel("mean ms")
    ax.set_title("Master-agent discovery: latency")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "latency.png", dpi=120)
    plt.close(fig)

    # --- token cost -----------------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(labels, tokens, color="#c44e52")
    ax.set_ylabel("total tokens used")
    ax.set_title("Master-agent discovery: LLM token cost")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(out_dir / "tokens.png", dpi=120)
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
        _set, _, strat = s.experiment.split(":")
        sets[_set][strat] = s.accuracy * 100
        sel[_set][strat] = s.mean_selection_ms
        tok[_set][strat] = s.total_tokens

    set_names = list(sets.keys())
    strat_names = list(next(iter(sets.values())).keys())
    colors = ["#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3", "#937860"]
    cmap = {s: colors[i % len(colors)] for i, s in enumerate(strat_names)}

    x = np.arange(len(set_names))
    width = 0.8 / len(strat_names)

    # --- accuracy per use case ------------------------------------------
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for i, s in enumerate(strat_names):
        vals = [sets[n].get(s, 0.0) for n in set_names]
        ax.bar(x - 0.4 + (i + 0.5) * width, vals, width, label=s, color=cmap[s])
        for xi, v in zip(x - 0.4 + (i + 0.5) * width, vals):
            ax.text(xi, v + 1, f"{v:.0f}", ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(set_names)
    ax.set_ylabel("selection accuracy (%)")
    ax.set_ylim(0, 108)
    ax.set_title("Discovery accuracy by use case (strategy x task set)")
    ax.legend(ncol=len(strat_names), fontsize=8, loc="upper center", bbox_to_anchor=(0.5, 1.13))
    fig.tight_layout()
    fig.savefig(out_dir / "accuracy_by_usecase.png", dpi=120)
    plt.close(fig)

    # --- selection latency per use case -----------------------------------
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for i, s in enumerate(strat_names):
        vals = [sel[n].get(s, 0.0) for n in set_names]
        ax.bar(x - 0.4 + (i + 0.5) * width, vals, width, label=s, color=cmap[s])
    ax.set_xticks(x)
    ax.set_xticklabels(set_names)
    ax.set_yscale("log")
    ax.set_ylabel("mean selection time (ms, log scale)")
    ax.set_title("Selection latency by use case")
    ax.legend(ncol=len(strat_names), fontsize=8, loc="upper center", bbox_to_anchor=(0.5, 1.13))
    fig.tight_layout()
    fig.savefig(out_dir / "selection_by_usecase.png", dpi=120)
    plt.close(fig)

    # --- token cost per use case -----------------------------------------
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for i, s in enumerate(strat_names):
        vals = [tok[n].get(s, 0) for n in set_names]
        ax.bar(x - 0.4 + (i + 0.5) * width, vals, width, label=s, color=cmap[s])
    ax.set_xticks(x)
    ax.set_xticklabels(set_names)
    ax.set_ylabel("total tokens used (12 tasks)")
    ax.set_title("Token cost by use case")
    ax.legend(ncol=len(strat_names), fontsize=8, loc="upper center", bbox_to_anchor=(0.5, 1.13))
    fig.tight_layout()
    fig.savefig(out_dir / "tokens_by_usecase.png", dpi=120)
    plt.close(fig)

    print(f"  use-case matrix charts written to {out_dir}/*_by_usecase.png")