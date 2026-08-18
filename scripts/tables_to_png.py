"""Render every markdown table in the Medium article to a standalone PNG.

Outputs PNGs into docs/medium_assets so each table can be pasted into
Medium separately (Medium mangles pasted markdown tables).
"""
import re
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
MD = ROOT / "docs" / "MEDIUM_ARTICLE.md"
OUT = ROOT / "docs" / "medium_assets"

SEP = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")


def clean(cell: str) -> str:
    cell = cell.strip()
    cell = re.sub(r"[*`]", "", cell)
    return cell


def parse_tables(text: str):
    tables = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if "|" in lines[i]:
            block = []
            while i < len(lines) and "|" in lines[i]:
                block.append(lines[i])
                i += 1
            rows = []
            for j, ln in enumerate(block):
                if j == 1 and SEP.match(ln):
                    continue
                cells = [clean(c) for c in ln.strip().strip("|").split("|")]
                rows.append(cells)
            if rows:
                tables.append(rows)
        else:
            i += 1
    return tables


def wrap(text: str, width: int) -> str:
    words = text.split()
    if not words:
        return ""
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = f"{cur} {w}".strip()
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def render(rows, title: str, out_path: Path):
    header = rows[0]
    data = rows[1:]
    ncols = len(header)
    nrows = len(data)

    col_widths = [len(h) for h in header]
    for row in data:
        for c, cell in enumerate(row):
            col_widths[c] = max(col_widths[c], len(cell))
    for c in range(ncols):
        col_widths[c] = min(max(col_widths[c], 10), 30)

    wrapped_header = [wrap(h, 26) for h in header]
    wrapped_rows = [
        [wrap(cell, col_widths[c]) for c, cell in enumerate(row)] for row in data
    ]

    fig, ax = plt.subplots(
        figsize=(max(7.0, ncols * 2.8), max(2.2, (nrows + 1) * 0.62))
    )
    ax.axis("off")
    ax.set_title(title, fontsize=13, fontweight="bold", color="#1f3864", pad=14)

    table = ax.table(
        cellText=wrapped_rows,
        colLabels=wrapped_header,
        loc="center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 1.7)

    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#c9d3e0")
        cell.set_linewidth(0.8)
        if r == 0:
            cell.set_facecolor("#1f3864")
            cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor("#ffffff" if r % 2 else "#eef3fb")
            cell.set_text_props(color="#1a1a2e")

    plt.savefig(out_path, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    text = MD.read_text(encoding="utf-8")
    tables = parse_tables(text)

    titles = {
        "assistant": ("The four assistants in the lab", "table_assistants.png"),
        "experiment": ("Experiment ladder: what we measured", "table_ladder.png"),
        "your situation": ("The cheat sheet: your situation to method", "table_cheatsheet.png"),
    }

    for rows in tables:
        key = rows[0][0]
        if key == "" and rows[0][1].startswith("neat"):
            title, name = ("Routing accuracy by request type", "table_matrix.png")
        elif key in titles:
            title, name = titles[key]
        else:
            title, name = (f"Table: {rows[0][0]}", "table_extra.png")
        render(rows, title, OUT / name)

    for chart in ["architecture", "accuracy", "latency", "tokens", "accuracy_by_usecase"]:
        src = ROOT / "experiments" / f"{chart}.png"
        if src.exists():
            shutil.copy2(src, OUT / f"{chart}.png")

    for p in sorted(OUT.glob("*.png")):
        print(f"{p.name}  ({p.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()