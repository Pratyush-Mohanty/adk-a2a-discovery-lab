"""Convert the cover SVG to a PNG (Medium cover size, 1600x840).

Uses resvg (Rust) which renders the vector SVG with system fonts, so the
PNG matches the SVG exactly — text included.

    py scripts/svg_to_png.py            # cover.svg -> cover.png
"""
import re
from pathlib import Path

import resvg_py

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "medium_assets"
SVG = ASSETS / "cover.svg"
PNG = ASSETS / "cover.png"

WIDTH, HEIGHT = 1600, 840


def main() -> None:
    text = SVG.read_text(encoding="utf-8")
    # matplotlib writes sizes in pt; resvg only accepts pixel units
    text = re.sub(r'width="[\d.]+pt"', f'width="{WIDTH}"', text)
    text = re.sub(r'height="[\d.]+pt"', f'height="{HEIGHT}"', text)
    data = resvg_py.svg_to_bytes(
        svg_string=text,
        width=WIDTH,
        height=HEIGHT,
        background="#ffffff",
    )
    PNG.write_bytes(data)
    print(f"converted {SVG.name} -> {PNG.name} ({len(data)} bytes)")


if __name__ == "__main__":
    main()