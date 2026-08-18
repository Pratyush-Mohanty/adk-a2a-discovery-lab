# Medium Publishing Rules

**Applies to:** every article in `docs/` that gets published on Medium.

Medium's editor does **not** render Markdown, and (as of 2026) it still has
**no table support**. Pasting a `.md` written for GitHub produces broken pipe
walls, stripped `<table>` HTML, and lost formatting. These rules keep an
article publishable on first paste.

---

## The hard rules

### 1. No raw Markdown tables in the pasted body

Medium strips table syntax; the result is a run-on paragraph of pipe
characters.

**Instead, per table, pick one:**
- **Bold-key bullet list** — best for simple 2–4 row comparisons (survives
  paste as normal text).
- **PNG image insert** — best for dense, visually-aligned data (render to PNG,
  upload as an image; it looks identical on every device).
- **Inline prose** — best for 2–3 row comparisons.

For this article's tables:
| table | publish as |
|---|---|
| The four assistants | bold-key bullet list |
| Experiment ladder | bold-key bullet list |
| Routing accuracy by request type (scoreboard) | PNG — `docs/medium_assets/table_matrix.png` |
| Cheat sheet: situation → method | PNG — `docs/medium_assets/table_cheatsheet.png` |

The PNGs are regenerated with `py scripts/tables_to_png.py` (auto-fitted, no
overflow).

### 2. Headings

Medium collapses `####` and deeper to `###`. Keep article headings at `##` /
`###`.

### 3. Nested lists

Medium supports only single-level lists. Flatten anything deeper into
`- **bold label** — text` lines.

### 4. Code blocks

No syntax highlighting in Medium; a bare ```` ``` ```` block pastes fine but
drop language labels if they cause issues.

### 5. Images

Charts and diagrams are fine as images. Insert them at the same spots as in
the source (`docs/medium_assets/architecture.png`, `accuracy.png`,
`latency.png`, `tokens.png`, `accuracy_by_usecase.png`).

### 6. Footnotes, LaTeX math, raw HTML widgets, anchor links, ToC

Not supported by Medium at all — remove or rewrite.

---

## The copy-paste workflow (the acceptance test)

Before publishing:

1. Convert/adapt the article per the rules above (tables → bullets or PNGs).
2. Paste the full text into a blank Medium draft.
3. Preview and find every section that got mangled.
4. Fix it in the **source** `.md` (not just in Medium) so the fix is permanent.
5. Re-paste into the same draft and verify.

If a draft needs manual fix-up after every paste, it's not Medium-ready.

---

## Architect's rule

When building the HTML preview of an article, treat it as a simulation of what
Medium will show. If the preview contains tables or features that won't survive
Medium's paste, the draft is wrong — fix the draft, not the workflow.

Generated: 2026-08-18