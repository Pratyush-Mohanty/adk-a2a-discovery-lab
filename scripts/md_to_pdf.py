"""Render a Markdown file to a styled standalone HTML (or PDF via Chrome).

Usage:
    py scripts/md_to_pdf.py docs/REPORT.md docs/REPORT.html          # HTML (default)
    py scripts/md_to_pdf.py docs/REPORT.md docs/REPORT.pdf --pdf     # PDF via Chrome

Requires: markdown (pip); PDF additionally needs Chrome or Edge installed.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Calibri, Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.5; color: #1f2430; margin: 0; }
h1 { font-size: 20pt; color: #0b3d91; border-bottom: 3px solid #0b3d91;
     padding-bottom: 6px; page-break-before: always; margin-top: 0; }
h1:first-of-type { page-break-before: avoid; }
h2 { font-size: 14pt; color: #0b3d91; border-bottom: 1px solid #cfd8ea;
     padding-bottom: 3px; margin-top: 20px; }
h3 { font-size: 12pt; color: #17408a; margin-top: 16px; }
h4 { font-size: 10.5pt; color: #17408a; }
p { margin: 6px 0; }
ul, ol { margin: 6px 0; padding-left: 22px; }
li { margin: 2px 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0;
        font-size: 8.8pt; page-break-inside: avoid; }
th { background: #0b3d91; color: #fff; text-align: left; padding: 5px 7px; }
td { border: 1px solid #c9d2e6; padding: 4px 7px; vertical-align: top; }
tr:nth-child(even) td { background: #f2f5fc; }
code { font-family: Consolas, 'Cascadia Mono', monospace; font-size: 8.8pt;
       background: #eef1f8; padding: 1px 4px; border-radius: 3px; }
pre { background: #0f172a; color: #e2e8f0; padding: 10px 12px; border-radius: 6px;
      overflow-x: auto; font-size: 8.6pt; line-height: 1.35; page-break-inside: avoid; }
pre code { background: none; color: inherit; padding: 0; }
blockquote { border-left: 4px solid #0b3d91; margin: 8px 0; padding: 4px 12px;
             background: #f2f5fc; color: #333; }
a { color: #0b3d91; text-decoration: none; }
strong { color: #0b3d91; }
hr { border: none; border-top: 1px solid #cfd8ea; margin: 16px 0; }
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown -> standalone HTML (default) or PDF")
    parser.add_argument("src", type=Path)
    parser.add_argument("dst", type=Path)
    parser.add_argument("--pdf", action="store_true", help="render PDF via headless Chrome instead of HTML")
    args = parser.parse_args()

    src = Path(args.src).resolve()
    dst = Path(args.dst).resolve()
    md_text = src.read_text(encoding="utf-8")

    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
    )
    html = f"<!doctype html><html><head><meta charset='utf-8'><title>{src.stem}</title><style>{CSS}</style></head><body>{body}</body></html>"

    if not args.pdf:
        dst.write_text(html, encoding="utf-8")
        print(f"HTML written: {dst} ({dst.stat().st_size / 1024:.1f} KB)")
        return

    chrome_candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    chrome = next((c for c in chrome_candidates if Path(c).exists()), None)
    if chrome is None:
        sys.exit("Chrome/Edge not found; install Chrome or use the default HTML output")

    with tempfile.TemporaryDirectory() as tmp:
        html_path = Path(tmp) / "report.html"
        html_path.write_text(html, encoding="utf-8")
        cmd = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={dst}",
            html_path.as_uri(),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            sys.exit(f"chrome failed: {result.stderr[:500]}")

    print(f"PDF written: {dst} ({dst.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()