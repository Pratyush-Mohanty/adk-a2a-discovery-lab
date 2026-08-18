"""Build a self-contained, Medium-style HTML article from ARTICLE.md.

Images referenced in the markdown are base64-embedded so the HTML is a single
portable file. Usage:
    py scripts/build_article.py docs/ARTICLE.md docs/ARTICLE.html
"""
import argparse
import base64
import re
import sys
from pathlib import Path

import markdown

MEDIUM_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: #ffffff;
  color: #242424;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 19px;
  line-height: 1.58;
  letter-spacing: -0.003em;
  -webkit-font-smoothing: antialiased;
}
.topbar {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-size: 14px;
  font-weight: 600;
  color: #6b6b6b;
  border-bottom: 1px solid #f2f2f2;
  padding: 14px 24px;
}
.topbar .dot { color: #1a8917; }
.article { max-width: 680px; margin: 0 auto; padding: 40px 24px 80px; }
h1, h2, h3, h4 {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-weight: 800;
  color: #0f0f0f;
  letter-spacing: -0.01em;
  line-height: 1.12;
  margin: 1.6em 0 0.6em;
}
h1 { font-size: 40px; margin-top: 0.4em; }
h2 { font-size: 30px; }
h3 { font-size: 24px; }
p { margin: 1.25em 0; }
a { color: #1a8917; text-decoration: none; }
a:hover { text-decoration: underline; }
strong { color: #0f0f0f; font-weight: 700; }
blockquote {
  margin: 1.6em 0;
  padding: 0.2em 0 0.2em 1.2em;
  border-left: 3px solid #c9c9c9;
  color: #6b6b6b;
  font-style: italic;
}
code {
  font-family: 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace;
  font-size: 0.85em;
  background: #f4f4f4;
  padding: 2px 6px;
  border-radius: 4px;
}
pre {
  background: #f7f7f7;
  padding: 18px 20px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 15px;
  line-height: 1.5;
}
pre code { background: none; padding: 0; font-size: 15px; }
figure { margin: 2.4em 0; text-align: center; }
figure img {
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  border: 1px solid #efefef;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04);
}
figcaption {
  margin-top: 12px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-size: 15px;
  color: #6b6b6b;
  line-height: 1.4;
}
table {
  border-collapse: collapse;
  margin: 1.6em 0;
  width: 100%;
  font-size: 16px;
  line-height: 1.45;
}
th, td { border: 1px solid #e0e0e0; padding: 8px 12px; text-align: left; vertical-align: top; }
th {
  background: #f7f7f7;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-weight: 700;
  font-size: 15px;
  color: #0f0f0f;
}
tr:nth-child(even) td { background: #fafafa; }
hr { border: none; border-top: 1px solid #f0f0f0; margin: 2em 0; }
ul, ol { margin: 1.25em 0; padding-left: 1.6em; }
li { margin: 0.5em 0; }
.footer {
  max-width: 680px;
  margin: 0 auto;
  padding: 0 24px 60px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
  font-size: 14px;
  color: #6b6b6b;
}
.footer .tags { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 24px; }
.footer .tag {
  font-size: 14px;
  color: #1a8917;
  background: #f2f2f2;
  border-radius: 99px;
  padding: 5px 14px;
}
.footer .tag:hover { background: #e6e6e6; }
@media (max-width: 720px) {
  h1 { font-size: 32px; }
  h2 { font-size: 26px; }
  body { font-size: 18px; }
}
"""


def embed_images(html: str, base_dir: Path) -> str:
    """Replace markdown-generated <img src="relative/path.png"> with base64 data URIs."""

    def repl(m: re.Match) -> str:
        alt, src, extra = m.group(1), m.group(2), m.group(3) or ""
        path = (base_dir / src).resolve()
        if not path.exists():
            print(f"  [warn] missing image: {path}", file=sys.stderr)
            return m.group(0)
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        ext = path.suffix.lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif"}.get(ext, "application/octet-stream")
        caption = f'<figcaption>{alt}</figcaption>' if alt else ""
        return f'<figure><img alt="{alt}" src="data:{mime};base64,{b64}"{extra}>{caption}</figure>'

    return re.sub(r'<img alt="([^"]*)" src="([^"]+)"([^>]*)?>', repl, html)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build a Medium-style self-contained HTML article.")
    ap.add_argument("md", help="path to the article markdown")
    ap.add_argument("html", help="output html path")
    ap.add_argument("--title", default="Agent discovery in A2A", help="title shown in the top bar / <title>")
    ap.add_argument("--tags", default="AI,Agentic AI,Google ADK,A2A,Machine Learning", help="comma-separated tags")
    args = ap.parse_args()

    md_path = Path(args.md).resolve()
    out_path = Path(args.html).resolve()
    base_dir = md_path.parent

    raw = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(
        raw,
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    body = embed_images(body, base_dir)

    tags_html = "".join(f'<a class="tag" href="#">{t.strip()}</a>' for t in args.tags.split(","))

    title = md_path.name.replace(".md", "")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — ADK/A2A Discovery Lab</title>
<style>{MEDIUM_CSS}</style>
</head>
<body>
<div class="topbar">ADK · A2A Discovery Lab</div>
<article class="article">
{body}
</article>
<div class="footer">
  <div class="tags">{tags_html}</div>
  <div>Open-source project — <a href="https://github.com/Pratyush-Mohanty/adk-a2a-discovery-lab">adk-a2a-discovery-lab</a>. Powered by Google ADK + A2A (a2a-sdk 1.1.2).</div>
</div>
</body>
</html>"""
    out_path.write_text(page, encoding="utf-8")
    print(f"ARTICLE written: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()