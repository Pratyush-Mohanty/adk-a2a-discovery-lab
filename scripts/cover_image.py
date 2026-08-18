"""Generate the Medium cover image for the agent-routing article.

Simple + artistic + cartoon style. Layout is split into two clean bands
so no figure ever overlaps text:
  top band    -> kicker / title / subtitle (text only)
  bottom band -> the routing illustration (master robot + 4 agents)

Medium cover ratio ~1.91:1 (rendered 3200x1680).
"""
import matplotlib

matplotlib.use("Agg")
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch, Ellipse

OUT = "docs/medium_assets/cover.png"
OUT_SVG = "docs/medium_assets/cover.svg"

matplotlib.rcParams["svg.fonttype"] = "none"  # keep text as editable SVG text

FONTS = {f.name for f in font_manager.fontManager.ttflist}
COMIC = "Comic Sans MS" if "Comic Sans MS" in FONTS else "DejaVu Sans"
HAND = "Segoe Print" if "Segoe Print" in FONTS else COMIC

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

# soft cream wash
grad = np.linspace(1.0, 0.94, 256).reshape(-1, 1)
bg = np.stack([grad, grad * 0.985, grad * 0.95], axis=-1)
ax.imshow(bg, extent=(0, 16, 0, 8.4), aspect="auto", zorder=0)


def shadow(cx, cy, rx, ry):
    ax.add_patch(Ellipse((cx, cy), rx, ry, fc="#000000", ec="none", alpha=0.06, zorder=1))


def robot(cx, cy, s, body, face):
    """Simple chibi robot: antenna + rounded head + screen + eyes + smile."""
    shadow(cx, cy - 0.6 * s, 1.0 * s, 0.2 * s)
    ax.plot([cx, cx], [cy + 0.5 * s, cy + 0.85 * s], color=INK,
            lw=0.13 * s, solid_capstyle="round", zorder=2)
    ax.add_patch(Circle((cx, cy + 0.92 * s), 0.12 * s, fc=INK, ec="none", zorder=2))
    ax.add_patch(
        FancyBboxPatch(
            (cx - 0.78 * s, cy - 0.5 * s), 1.56 * s, 1.0 * s,
            boxstyle="round,pad=0.04,rounding_size=0.28", fc=body, ec=INK,
            lw=0.1 * s, zorder=3,
        )
    )
    ax.add_patch(
        FancyBboxPatch(
            (cx - 0.55 * s, cy - 0.32 * s), 1.10 * s, 0.64 * s,
            boxstyle="round,pad=0.02,rounding_size=0.2", fc=face, ec="none", zorder=4,
        )
    )
    for ex in (cx - 0.26 * s, cx + 0.26 * s):
        ax.add_patch(Circle((ex, cy + 0.08 * s), 0.08 * s, fc=INK, ec="none", zorder=5))
    ax.plot(
        [cx - 0.20 * s, cx, cx + 0.20 * s], [cy - 0.16 * s, cy - 0.08 * s, cy - 0.16 * s],
        color=INK, lw=0.06 * s, zorder=5, solid_capstyle="round",
    )


def bubble(cx, cy, w, h, text, fs):
    ax.add_patch(
        FancyBboxPatch(
            (cx - w / 2, cy - h / 2), w, h,
            boxstyle="round,pad=0.06,rounding_size=0.35", fc="#ffffff", ec=INK,
            lw=3, zorder=6,
        )
    )
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs,
            color=INK, fontfamily=COMIC, fontweight="bold", zorder=7)


# ---------------- top band: text only (y 5.6 .. 8.0) ----------------
ax.text(8, 7.75, "ADK  ·  A2A  ·  AGENT ROUTING", ha="center", va="center",
        fontsize=14, color=LILAC, fontfamily=COMIC, fontweight="bold", zorder=3)
ax.text(8, 6.85, "How Does One AI Agent Know\nWhich Other AI Agent To Call?",
        ha="center", va="center", fontsize=31, color=INK,
        fontfamily=COMIC, fontweight="bold", linespacing=1.2, zorder=3)
ax.text(8, 5.55, "a little field guide to routing tasks to the right assistant",
        ha="center", va="center", fontsize=17, color="#8a7f98",
        fontfamily=HAND, zorder=3)

# ---------------- bottom band: illustration only (y 0.3 .. 5.0) ----------------
# master robot + bubble (kept below the subtitle's clearance line y=5.0)
robot(8, 3.15, 1.0, LAVENDER, "#e7e3ff")
bubble(10.7, 3.55, 3.2, 1.05, "who handles this?", 15)

agents = [
    (2.3, "summarizer", PEACH, "#fff1dc"),
    (6.1, "translator", SKY, "#e2edff"),
    (9.9, "extractor", MINT, "#edffe6"),
    (13.7, "classifier", PINK, "#ffe9ff"),
]
for cx, name, body, face in agents:
    robot(cx, 1.2, 0.72, body, face)
    ax.text(cx, 0.3, name, ha="center", va="center", fontsize=14,
            color=INK, fontfamily=COMIC, fontweight="bold", zorder=3)

for cx, *_ in agents:
    ax.add_patch(
        FancyArrowPatch(
            (8.35, 2.35), (cx, 1.85),
            connectionstyle="arc3,rad=0.15",
            arrowstyle="-|>", color=INK, lw=2.0,
            linestyle=(0, (4, 3)), zorder=2,
        )
    )

plt.savefig(OUT, dpi=200, bbox_inches="tight", facecolor="white")
plt.savefig(OUT_SVG, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"cover image written: {OUT}")
print(f"cover svg written: {OUT_SVG}")