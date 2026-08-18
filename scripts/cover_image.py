"""Generate the Medium cover image for the agent-routing article.

Medium cover ratio ~1.91:1 (1400x800 minimum; we render 3200x1680).
"""
import matplotlib

matplotlib.use("Agg")
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = "docs/medium_assets/cover.png"

fig, ax = plt.subplots(figsize=(16, 8.4), dpi=200)
ax.set_xlim(0, 16)
ax.set_ylim(0, 8.4)
ax.axis("off")

# soft vertical gradient background
grad = np.linspace(0.94, 0.86, 256).reshape(-1, 1)
bg = np.ones((256, 1, 3)) * 1.0
bg[..., 0] *= grad
bg[..., 1] *= grad
bg[..., 2] *= grad + (1 - grad) * 0.06
ax.imshow(bg, extent=(0, 16, 0, 8.4), aspect="auto", zorder=0)

NAVY = "#1f3b73"
TEAL = "#2e6b2e"
ORANGE = "#b2572c"
LIGHT = "#dfe7f5"


def box(x, y, w, h, text, fc, ec, fs, tc="#111111", bold=False):
    p = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.08",
        fc=fc, ec=ec, lw=1.6, mutation_scale=16,
    )
    ax.add_patch(p)
    ax.text(
        x + w / 2, y + h / 2, text, ha="center", va="center",
        fontsize=fs, color=tc, fontweight="bold" if bold else "normal",
        linespacing=1.4,
    )


# kicker
ax.text(8, 7.35, "ADK  ·  A2A  ·  AGENT ROUTING", ha="center", va="center",
        fontsize=13, color=ORANGE, fontweight="bold", zorder=3)

# title (two lines)
ax.text(8, 6.35, "How Does One AI Agent Know\nWhich Other AI Agent To Call?",
        ha="center", va="center", fontsize=33, color=NAVY,
        fontweight="bold", linespacing=1.25, zorder=3)

# subtitle
ax.text(8, 5.15, "A beginner-friendly, measurement-backed tour of 8 ways to route\n"
        "tasks to the right AI assistant — and which one to pick for your situation.",
        ha="center", va="center", fontsize=15, color="#555555", linespacing=1.5, zorder=3)

# routing diagram
box(5.0, 4.0, 6.0, 0.85, "MASTER AGENT\nwho should handle this request?",
    NAVY, NAVY, 13, "white", bold=True)
for i, name in enumerate(["summarizer", "translator", "extractor", "classifier"]):
    x = 1.6 + i * 3.55
    box(x, 1.35, 2.7, 0.85, name, LIGHT, NAVY, 13, NAVY, bold=True)
    ax.annotate(
        "", xy=(x + 1.35, 2.2), xytext=(8, 4.0),
        arrowprops=dict(arrowstyle="-|>", color=TEAL, lw=2.2),
    )

# footer tagline
ax.text(8, 0.5, "Agent discovery: 8 strategies measured on a real A2A fleet",
        ha="center", va="center", fontsize=13, color="#777777", zorder=3)

plt.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"cover image written: {OUT}")