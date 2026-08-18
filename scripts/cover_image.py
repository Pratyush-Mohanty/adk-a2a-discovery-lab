"""Generate the Medium cover image for the agent-routing article.

Simple, artistic, cartoon-style: pastel palette, hand-drawn-ish rounded
robots, playful Comic Sans typography. Medium cover ratio ~1.91:1
(rendered 3200x1680).
"""
import matplotlib

matplotlib.use("Agg")
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch, Ellipse

OUT = "docs/medium_assets/cover.png"

FONTS = {f.name for f in font_manager.fontManager.ttflist}
COMIC = "Comic Sans MS" if "Comic Sans MS" in FONTS else "DejaVu Sans"
HAND = "Segoe Print" if "Segoe Print" in FONTS else COMIC

# pastel palette
CREAM = "#fdf6ec"
PEACH = "#ffd6a5"
LAVENDER = "#bdb2ff"
SKY = "#a0c4ff"
MINT = "#caffbf"
PINK = "#ffc6ff"
INK = "#5b4a6e"
LILAC = "#8a7fc0"

fig, ax = plt.subplots(figsize=(16, 8.4), dpi=200)
ax.set_xlim(0, 16)
ax.set_ylim(0, 8.4)
ax.axis("off")

# soft vertical wash
grad = np.linspace(1.0, 0.94, 256).reshape(-1, 1)
bg = np.stack([grad, grad * 0.985, grad * 0.95], axis=-1)
ax.imshow(bg, extent=(0, 16, 0, 8.4), aspect="auto", zorder=0)

# floating pastel dots / bubbles (artistic confetti)
rng = np.random.default_rng(7)
for _ in range(34):
    x, y = rng.uniform(0.4, 15.6), rng.uniform(0.3, 8.0)
    r = rng.uniform(0.05, 0.22)
    c = rng.choice([PEACH, LAVENDER, SKY, MINT, PINK])
    ax.add_patch(Circle((x, y), r, fc=c, ec="none", alpha=0.55, zorder=1))


def shadow(cx, cy, rx, ry):
    ax.add_patch(Ellipse((cx, cy), rx, ry, fc="#000000", ec="none", alpha=0.06, zorder=1))


def robot(cx, cy, s, body, face):
    """A simple chibi robot head + antenna + smile."""
    shadow(cx, cy - 0.62 * s, 1.05 * s, 0.22 * s)
    # antenna
    ax.plot([cx, cx], [cy + 0.55 * s, cy + 0.95 * s], color=INK, lw=0.14 * s, solid_capstyle="round", zorder=2)
    ax.add_patch(Circle((cx, cy + 1.02 * s), 0.13 * s, fc=INK, ec="none", zorder=2))
    # head
    ax.add_patch(
        FancyBboxPatch(
            (cx - 0.78 * s, cy - 0.55 * s), 1.56 * s, 1.1 * s,
            boxstyle="round,pad=0.04,rounding_size=0.28", fc=body, ec=INK,
            lw=0.11 * s, zorder=3,
        )
    )
    # screen
    ax.add_patch(
        FancyBboxPatch(
            (cx - 0.55 * s, cy - 0.35 * s), 1.10 * s, 0.7 * s,
            boxstyle="round,pad=0.02,rounding_size=0.2", fc=face, ec="none", zorder=4,
        )
    )
    # eyes
    for ex in (cx - 0.26 * s, cx + 0.26 * s):
        ax.add_patch(Circle((ex, cy + 0.10 * s), 0.085 * s, fc=INK, ec="none", zorder=5))
    # smile
    ax.plot(
        [cx - 0.20 * s, cx, cx + 0.20 * s], [cy - 0.18 * s, cy - 0.10 * s, cy - 0.18 * s],
        color=INK, lw=0.07 * s, zorder=5, solid_capstyle="round",
    )


def bubble(cx, cy, w, h, text, fs):
    """Rounded speech bubble with a tail."""
    ax.add_patch(
        FancyBboxPatch(
            (cx - w / 2, cy - h / 2), w, h,
            boxstyle="round,pad=0.06,rounding_size=0.35", fc="#ffffff", ec=INK,
            lw=3, zorder=6,
        )
    )
    ax.add_patch(
        FancyArrowPatch(
            (cx + 0.28 * w, cy - h / 2), (cx + 0.10 * w, cy - h / 2 - 0.42),
            arrowstyle="-", color=INK, lw=3, zorder=6,
        )
    )
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            color=INK, fontfamily=COMIC, fontweight="bold", zorder=7)


# kicker
ax.text(8, 7.75, "ADK  ·  A2A  ·  AGENT ROUTING", ha="center", va="center",
        fontsize=14, color=LILAC, fontfamily=COMIC, fontweight="bold", zorder=3)

# title
ax.text(8, 6.95, "How Does One AI Agent Know\nWhich Other AI Agent To Call?",
        ha="center", va="center", fontsize=32, color=INK,
        fontfamily=COMIC, fontweight="bold", linespacing=1.2, zorder=3)

# subtitle (handwritten accent)
ax.text(8, 5.6, "a little field guide to routing tasks to the right assistant",
        ha="center", va="center", fontsize=18, color="#8a7f98",
        fontfamily=HAND, zorder=3)

# master robot + its bubble
robot(8, 3.6, 1.15, LAVENDER, "#e7e3ff")
bubble(10.4, 4.4, 3.4, 1.15, "who handles this?", 16)

# the four little agents
agents = [
    (2.2, "summarizer", PEACH, "#fff1dc"),
    (6.0, "translator", SKY, "#e2edff"),
    (10.0, "extractor", MINT, "#edffe6"),
    (13.8, "classifier", PINK, "#ffe9ff"),
]
for cx, name, body, face in agents:
    robot(cx, 1.35, 0.8, body, face)
    ax.text(cx, 0.35, name, ha="center", va="center", fontsize=15,
            color=INK, fontfamily=COMIC, fontweight="bold", zorder=3)

# dashed routes from master to each agent
for cx, *_ in agents:
    ax.add_patch(
        FancyArrowPatch(
            (8.4, 2.55), (cx, 1.95),
            connectionstyle="arc3,rad=0.18",
            arrowstyle="-|>", color=INK, lw=2.2,
            linestyle=(0, (4, 3)), zorder=2,
        )
    )

plt.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"cover image written: {OUT}")