"""Convert markdown tables in the Medium article into ASCII box tables.

Medium has no native table support; a monospaced pre/code block keeps the
table aligned on every device (the approach used in the published article
"The Agent That Got Tricked by Data").

Writes the Medium-ready variant of the article:
    docs/MEDIUM_ARTICLE.md          -> source (markdown tables, for GitHub)
    docs/MEDIUM_ARTICLE_medium.md   -> paste-ready (ASCII code-block tables)
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "MEDIUM_ARTICLE.md"
DST = ROOT / "docs" / "MEDIUM_ARTICLE_medium.md"

SEP = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
MAX_COL = 26


def clean(cell: str) -> str:
    cell = cell.strip()
    cell = re.sub(r"[*`]", "", cell)
    return cell


def parse_table(lines: list[str]) -> list[list[str]]:
    rows = []
    for j, ln in enumerate(lines):
        if j == 1 and SEP.match(ln):
            continue
        rows.append([clean(c) for c in ln.strip().strip("|").split("|")])
    return rows


def wrap(text: str, width: int) -> list[str]:
    """Greedy word-wrap to <= width chars; hard-breaks over-long words."""
    lines = []
    cur = ""
    for word in text.split():
        while len(word) > width:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[:width])
            word = word[width:]
        trial = f"{cur} {word}".strip()
        if len(trial) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def ascii_table(rows: list[list[str]]) -> str:
    header, data = rows[0], rows[1:]
    ncols = len(header)

    targets = []
    for c in range(ncols):
        raw = max([len(r[c]) for r in rows] + [1])
        targets.append(min(raw, MAX_COL))

    wrapped = []
    widths = []
    for c in range(ncols):
        col_lines = []
        for r in rows:
            col_lines.append(wrap(r[c], targets[c]))
        # column width = longest wrapped line in the column
        widths.append(max(len(line) for cell in col_lines for line in cell))
        wrapped.append(col_lines)

    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(row_idx: int) -> list[str]:
        lines_per_cell = [wrapped[c][row_idx] for c in range(ncols)]
        n = max(len(c) for c in lines_per_cell)
        out = []
        for i in range(n):
            cells = []
            for c in range(ncols):
                line = lines_per_cell[c][i] if i < len(lines_per_cell[c]) else ""
                cells.append(line.ljust(widths[c]))
            out.append("| " + " | ".join(cells) + " |")
        return out

    out = [border]
    out += fmt(0)
    for r in range(1, len(rows)):
        out.append(border)
        out += fmt(r)
    out.append(border)
    return "\n".join(out)


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        is_table = "|" in line and i + 1 < n and SEP.match(lines[i + 1])
        if not is_table:
            out.append(line)
            i += 1
            continue
        block = []
        while i < n and "|" in lines[i]:
            block.append(lines[i])
            i += 1
        table = ascii_table(parse_table(block))
        out.append("```text")
        out.append(table)
        out.append("```")
    DST.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"medium-ready article written: {DST}")


if __name__ == "__main__":
    main()