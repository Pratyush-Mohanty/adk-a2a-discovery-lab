"""Convert an SVG (e.g. from matplotlib) to a PNG via resvg.

Resvg renders vector SVG with system fonts so text matches exactly.
matplotlib writes sizes in `pt`; resvg only accepts pixel units, so the
width/height attributes are normalized before rendering.

    py scripts/svg_to_png.py <in.svg> [out.png] [--width 1600] [--height 840]
"""
import argparse
import re
from pathlib import Path

import resvg_py


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("svg", help="input SVG path")
    ap.add_argument("png", nargs="?", default=None, help="output PNG path")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=0, help="0 = keep SVG aspect ratio")
    args = ap.parse_args()

    svg_path = Path(args.svg).resolve()
    png_path = Path(args.png).resolve() if args.png else svg_path.with_suffix(".png")

    text = svg_path.read_text(encoding="utf-8")

    vb = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', text)
    if args.height == 0 and vb:
        args.height = round(args.width * float(vb.group(2)) / float(vb.group(1)))

    text = re.sub(r'width="[\d.]+pt"', f'width="{args.width}"', text)
    text = re.sub(r'height="[\d.]+pt"', f'height="{args.height}"', text)

    data = resvg_py.svg_to_bytes(
        svg_string=text,
        width=args.width,
        height=args.height,
        background="#ffffff",
    )
    png_path.write_bytes(data)
    print(f"converted {svg_path.name} -> {png_path.name} ({len(data)} bytes, {args.width}x{args.height})")


if __name__ == "__main__":
    main()