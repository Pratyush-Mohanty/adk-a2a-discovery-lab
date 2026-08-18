"""Draw a clean architecture diagram for the article as SVG (vector/editable).

The SVG is the source of truth; convert it to PNG with:
    py scripts/svg_to_png.py experiments/architecture.svg experiments/architecture.png

Layout (clean grid, no overlaps):
    top      -> title
    upper    -> MASTER AGENT + discovery strategy pills
    right    -> AGENT DIRECTORY (registry)
    middle   -> arrows (master->agents, pills->directory, directory->cards)
    lower    -> four worker Agent Cards
    bottom   -> card-serving note strip
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

matplotlib.rcParams["svg.fonttype"] = "none"

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "experiments"
SVG = EXP / "architecture.svg"

NAVY = "#1f3b73"
TEAL = "#2e6b2e"
LIGHT = "#dfe7f5"
DIR_FILL = "#f6e7b4"
DIR_EDGE = "#8a6d1a"

fig, ax = plt.subplots(figsize=(12.8, 7.2))
ax.set_xlim(0, 12.8)
ax.set_ylim(0, 7.2)
ax.axis("off")


def box(x, y, w, h, text, fc, ec, fs=10, tc="#111111", bold=False):
    p = FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.06", fc=fc, ec=ec, lw=1.5,
        mutation_scale=12,
    )
    ax.add_patch(p)
    ax.text(
        x + w / 2, y + h / 2, text, ha="center", va="center",
        fontsize=fs, color=tc, fontweight="bold" if bold else "normal",
        linespacing=1.45,
    )


def arrow(xy1, xy2, color, lw=1.7, dashed=False, rad=0.12):
    ax.add_patch(
        FancyArrowPatch(
            xy1, xy2, connectionstyle=f"arc3,rad={rad}", arrowstyle="-|>",
            color=color, lw=lw, linestyle=(0, (4, 3)) if dashed else "-",
        )
    )


# title
ax.text(6.4, 6.92, "A2A discovery lab architecture", ha="center", va="center",
        fontsize=13, color="#333333", fontweight="bold")

# master agent
box(0.8, 5.9, 4.6, 0.85, "MASTER AGENT\n(A2A client)", NAVY, NAVY, 11.5, "white", True)

# discovery strategy pills
pills = ["static", "card_discovery", "cached", "registry_skill", "llm_reasoned"]
pw, ph, gap = 1.28, 0.5, 0.1
for i, s in enumerate(pills):
    box(0.8 + i * (pw + gap), 5.1, pw, ph, s, LIGHT, NAVY, 8.5, NAVY)

# agent directory
box(8.7, 5.1, 3.7, 1.0, "AGENT DIRECTORY\n(registry · port 9000)", DIR_FILL, DIR_EDGE, 10.5, DIR_EDGE, True)

# four worker agent cards
agents = [
    ("summarizer", ":8101  skills: summarize, tldr"),
    ("translator", ":8102  skills: translate, multiling"),
    ("extractor", ":8103  skills: extract, pii"),
    ("classifier", ":8104  skills: classify, label"),
]
cw, ch = 2.7, 1.15
x0 = 0.6
for i, (name, detail) in enumerate(agents):
    x = x0 + i * (cw + 0.32)
    box(x, 1.1, cw, ch, f"{name}\n{detail}", "#eaf4ea", TEAL, 8.5, "#1e4d1e", True)

# note strip
box(2.3, 0.15, 8.2, 0.55,
    "Each agent serves its Agent Card at /.well-known/agent-card.json  —  discovery: fetch card -> index skills -> rank",
    "#f7f7f7", "#999999", 8.5)

# arrows: master -> agents (route)
for i, (name, _) in enumerate(agents):
    cx = x0 + i * (cw + 0.32) + cw / 2
    arrow((3.1, 5.9), (cx, 2.25), TEAL, rad=0.10)

# arrows: strategy pills -> directory (skill search)
arrow((5.4, 5.35), (8.7, 5.55), DIR_EDGE, lw=1.5, dashed=True, rad=0.0)

# arrows: directory -> agent cards (registration / serving)
arrow((10.55, 5.1), (8.4, 2.35), DIR_EDGE, lw=1.5, dashed=True, rad=-0.08)

# labels on the dashed arrows
ax.text(7.15, 5.62, "skill search", ha="center", va="bottom", fontsize=8.5, color=DIR_EDGE)
ax.text(9.85, 3.55, "register / serve Agent Cards", ha="center", va="center", fontsize=8.5, color=DIR_EDGE)

SVG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(SVG, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"architecture svg written: {SVG}")