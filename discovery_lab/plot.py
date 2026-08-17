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