"""Draw a clean architecture diagram for the article as SVG (vector/editable).

Three horizontal lanes (routing / discovery / workers) with subtle lane
backgrounds; all arrows fan down the left-centre so nothing crosses the
directory box or the text.

    SVG is the source of truth; convert to PNG with:
        py scripts/svg_to_png.py experiments/architecture.svg experiments/architecture.png
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
LANE_FILL = "#f7f9fc"
LANE_EDGE = "#e3e9f2"

fig, ax = plt.subplots(figsize=(12.8, 7.2))
ax.set_xlim(0, 12.8)
ax.set_ylim(0, 7.2)
ax.axis("off")


def lane(x, y, w, h, label):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.05", fc=LANE_FILL,
            ec=LANE_EDGE, lw=1.2, mutation_scale=12,
        )
    )
    ax.text(x + 0.3, y + h - 0.28, label, ha="left", va="center",
            fontsize=9, color="#9aa0a6", fontweight="bold")


def box(x, y, w, h, text, fc, ec, fs=10, tc="#111111", bold=False):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.06", fc=fc, ec=ec, lw=1.5,
            mutation_scale=12,
        )
    )
    ax.text(
        x + w / 2, y + h / 2, text, ha="center", va="center",
        fontsize=fs, color=tc, fontweight="bold" if bold else "normal",
        linespacing=1.45,
    )


def arrow(xy1, xy2, color, lw=1.7, dashed=False):
    ax.add_patch(
        FancyArrowPatch(
            xy1, xy2, connectionstyle="arc3,rad=0", arrowstyle="-|>",
            color=color, lw=lw, linestyle=(0, (4, 3)) if dashed else "-",
        )
    )


# --- lanes ---------------------------------------------------------
lane(0.3, 5.6, 12.2, 1.45, "1 · routing")
lane(0.3, 3.9, 12.2, 1.45, "2 · discovery")
lane(0.3, 1.3, 12.2, 2.0, "3 · workers")

# --- routing lane ----------------------------------------------------
box(4.1, 6.1, 4.6, 0.8, "MASTER AGENT\n(A2A client)", NAVY, NAVY, 11.5, "white", True)

# discovery strategy chips, centered under the master
chips = ["static", "card_discovery", "cached", "registry_skill", "llm_reasoned"]
cw, chh, gap = 1.25, 0.44, 0.08
total = len(chips) * cw + (len(chips) - 1) * gap
start = 6.4 - total / 2
for i, s in enumerate(chips):
    box(start + i * (cw + gap), 5.62, cw, chh, s, LIGHT, NAVY, 8.5, NAVY)

# --- discovery lane ----------------------------------------------------
box(8.9, 4.35, 3.3, 0.9, "AGENT DIRECTORY\n(registry · port 9000)", DIR_FILL, DIR_EDGE, 10.5, DIR_EDGE, True)

# --- workers lane ------------------------------------------------------
agents = [
    ("summarizer", ":8101  skills: summarize, tldr"),
    ("translator", ":8102  skills: translate, multiling"),
    ("extractor", ":8103  skills: extract, pii"),
    ("classifier", ":8104  skills: classify, label"),
]
aw, ah = 2.7, 1.0
x0 = 0.6
for i, (name, detail) in enumerate(agents):
    x = x0 + i * (aw + 0.32)
    box(x, 1.55, aw, ah, f"{name}\n{detail}", "#eaf4ea", TEAL, 8.5, "#1e4d1e", True)

# --- arrows -------------------------------------------------------------
# master -> workers (route), fanning down the left/centre
for i, (name, _) in enumerate(agents):
    cx = x0 + i * (aw + 0.32) + aw / 2
    arrow((6.4, 6.1), (cx, 2.55), TEAL, lw=1.8)

# chips -> directory (skill search)
arrow((7.6, 5.62), (8.9, 4.8), DIR_EDGE, lw=1.5, dashed=True)
ax.text(8.35, 5.42, "skill search", ha="center", va="center", fontsize=8.5, color=DIR_EDGE)

# directory -> workers (serves cards)
arrow((10.55, 4.35), (10.55, 3.3), DIR_EDGE, lw=1.5, dashed=True)
ax.text(10.85, 3.83, "serves Agent Cards", ha="left", va="center", fontsize=8.5, color=DIR_EDGE)

# --- footer caption ------------------------------------------------------
ax.text(6.4, 0.45, "Each agent serves its Agent Card at /.well-known/agent-card.json",
        ha="center", va="center", fontsize=9, color="#888888")

SVG.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(SVG, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"architecture svg written: {SVG}")