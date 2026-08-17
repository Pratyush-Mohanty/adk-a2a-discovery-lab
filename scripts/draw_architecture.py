"""Draw a simple architecture diagram for the article."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(figsize=(9, 5.2))
ax.set_xlim(0, 10)
ax.set_ylim(0, 5.6)
ax.axis("off")


def box(x, y, w, h, text, fc, ec, fs=10, tc="#111111", bold=False):
    p = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.08",
        fc=fc,
        ec=ec,
        lw=1.4,
        mutation_scale=14,
    )
    ax.add_patch(p)
    ax.text(
        x + w / 2,
        y + h / 2,
        text,
        ha="center",
        va="center",
        fontsize=fs,
        color=tc,
        fontweight="bold" if bold else "normal",
        linespacing=1.3,
    )


# Master
box(0.5, 4.4, 4.2, 0.9, "Master Agent\n(A2A client)", "#1f3b73", "#1f3b73", 11, "white", bold=True)

# Strategies under master
for i, s in enumerate(["static", "card_discovery", "cached", "llm_reasoned", "registry_skill"]):
    box(0.5 + i * 0.85, 3.15, 0.78, 0.55, s, "#dfe7f5", "#1f3b73", 8)

# Directory
box(7.0, 3.0, 2.6, 0.8, "Agent Directory\n(registry, port 9000)", "#f6e7b4", "#8a6d1a", 10, bold=True)
ax.annotate("", xy=(6.4, 3.4), xytext=(5.6, 3.4), arrowprops=dict(arrowstyle="-|>", color="#8a6d1a", lw=1.4))

# Agent cards
box(0.3, 1.9, 2.1, 0.6, "summarizer\n:8101  skills: summarize, tldr", "#eaf4ea", "#2e6b2e", 8.5)
box(2.75, 1.9, 2.1, 0.6, "translator\n:8102  skills: translate, multiling", "#eaf4ea", "#2e6b2e", 8.5)
box(5.2, 1.9, 2.1, 0.6, "extractor\n:8103  skills: extract, pii", "#eaf4ea", "#2e6b2e", 8.5)
box(7.65, 1.9, 2.1, 0.6, "classifier\n:8104  skills: classify, label", "#eaf4ea", "#2e6b2e", 8.5)

# card well-known note
box(2.5, 0.55, 5.0, 0.6, 'Agent Card at /.well-known/agent-card.json\n(discovery: fetch card -> index skills -> rank)', "#f7f7f7", "#999999", 8.5)

# arrows: master -> agents
for x in [1.35, 3.8, 6.25, 8.7]:
    ax.annotate("", xy=(x, 2.05), xytext=(x, 3.15), arrowprops=dict(arrowstyle="-|>", color="#2e6b2e", lw=1.4))

ax.set_title("A2A discovery lab architecture", fontsize=12, color="#333333", fontweight="bold", pad=10)
plt.tight_layout()
plt.savefig("experiments/architecture.png", dpi=150, bbox_inches="tight", facecolor="white")
print("architecture written to experiments/architecture.png")