# HTML Output Contract

The converter should produce a single standalone HTML file with no external assets.

Required sections:

- Header with the plan title and source filename.
- Summary showing total tasks, checked tasks, and unchecked tasks.
- Sticky table of contents built from Markdown headings.
- Main article content.

Rendering expectations:

- `#`, `##`, `###`, and deeper headings become linked headings with stable slug ids.
- `- [ ]` and `- [x]` become disabled checkbox task rows.
- Fenced code blocks become `<pre><code>` blocks with escaped content.
- Inline code, links, bold, and italic text are preserved for common Markdown syntax.
- Simple pipe tables render as HTML tables.
- The generated page works offline and is readable on desktop and mobile.

File naming:

- Default output path is the source filename with `.html`.
- A custom output path may be passed with `--output`.

