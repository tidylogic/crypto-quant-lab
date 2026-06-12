#!/usr/bin/env python3
"""Render a long Markdown implementation plan to a readable standalone HTML file."""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Heading:
    level: int
    text: str
    slug: str


@dataclass
class RenderResult:
    body: str
    headings: list[Heading]
    total_tasks: int
    completed_tasks: int


def slugify(text: str, used: set[str]) -> str:
    base = re.sub(r"[^a-zA-Z0-9가-힣]+", "-", text.strip().lower()).strip("-")
    slug = base or "section"
    counter = 2
    while slug in used:
        slug = f"{base}-{counter}" if base else f"section-{counter}"
        counter += 1
    used.add(slug)
    return slug


def render_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f'<a href="{html.escape(match.group(2), quote=True)}">{match.group(1)}</a>',
        escaped,
    )
    return escaped


def is_table_delimiter(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_table(lines: list[str]) -> str:
    header = split_table_row(lines[0])
    rows = [split_table_row(line) for line in lines[2:]]
    parts = ["<table>", "<thead><tr>"]
    parts.extend(f"<th>{render_inline(cell)}</th>" for cell in header)
    parts.append("</tr></thead>")
    parts.append("<tbody>")
    for row in rows:
        parts.append("<tr>")
        parts.extend(f"<td>{render_inline(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "\n".join(parts)


def render_markdown(markdown: str) -> RenderResult:
    lines = markdown.splitlines()
    headings: list[Heading] = []
    used_slugs: set[str] = set()
    total_tasks = 0
    completed_tasks = 0
    parts: list[str] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    code_lang = ""
    list_stack: list[str] = []

    def close_paragraph() -> None:
        if paragraph:
            parts.append(f"<p>{render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_lists() -> None:
        while list_stack:
            parts.append(f"</{list_stack.pop()}>")

    index = 0
    while index < len(lines):
        line = lines[index]

        if line.startswith("```"):
            if in_code:
                parts.append(
                    f'<pre><code class="language-{html.escape(code_lang)}">'
                    + html.escape("\n".join(code_lines))
                    + "</code></pre>"
                )
                in_code = False
                code_lines = []
                code_lang = ""
            else:
                close_paragraph()
                close_lists()
                in_code = True
                code_lang = line[3:].strip()
            index += 1
            continue

        if in_code:
            code_lines.append(line)
            index += 1
            continue

        if not line.strip():
            close_paragraph()
            close_lists()
            index += 1
            continue

        if (
            "|" in line
            and index + 1 < len(lines)
            and "|" in lines[index + 1]
            and is_table_delimiter(lines[index + 1])
        ):
            close_paragraph()
            close_lists()
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            parts.append(render_table(table_lines))
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            close_paragraph()
            close_lists()
            level = len(heading_match.group(1))
            text = heading_match.group(2).strip()
            slug = slugify(re.sub(r"`([^`]+)`", r"\1", text), used_slugs)
            headings.append(Heading(level=level, text=text, slug=slug))
            parts.append(
                f'<h{level} id="{slug}"><a class="anchor" href="#{slug}">#</a> '
                f"{render_inline(text)}</h{level}>"
            )
            index += 1
            continue

        task_match = re.match(r"^(\s*)-\s+\[([ xX])\]\s+(.+)$", line)
        if task_match:
            close_paragraph()
            close_lists()
            total_tasks += 1
            checked = task_match.group(2).lower() == "x"
            completed_tasks += 1 if checked else 0
            checked_attr = " checked" if checked else ""
            parts.append(
                '<div class="task-row">'
                f'<input type="checkbox" disabled{checked_attr}>'
                f"<span>{render_inline(task_match.group(3))}</span>"
                "</div>"
            )
            index += 1
            continue

        unordered_match = re.match(r"^\s*[-*]\s+(.+)$", line)
        if unordered_match:
            close_paragraph()
            if list_stack != ["ul"]:
                close_lists()
                parts.append("<ul>")
                list_stack.append("ul")
            parts.append(f"<li>{render_inline(unordered_match.group(1))}</li>")
            index += 1
            continue

        ordered_match = re.match(r"^\s*\d+\.\s+(.+)$", line)
        if ordered_match:
            close_paragraph()
            if list_stack != ["ol"]:
                close_lists()
                parts.append("<ol>")
                list_stack.append("ol")
            parts.append(f"<li>{render_inline(ordered_match.group(1))}</li>")
            index += 1
            continue

        close_lists()
        paragraph.append(line.strip())
        index += 1

    close_paragraph()
    close_lists()
    if in_code:
        parts.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")

    return RenderResult(
        body="\n".join(parts),
        headings=headings,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
    )


def build_toc(headings: list[Heading]) -> str:
    if not headings:
        return '<p class="muted">No headings found.</p>'
    items = [
        f'<li class="toc-level-{heading.level}"><a href="#{heading.slug}">{render_inline(heading.text)}</a></li>'
        for heading in headings
    ]
    return "<ol>" + "\n".join(items) + "</ol>"


def build_html(source: Path, result: RenderResult) -> str:
    title = result.headings[0].text if result.headings else source.stem
    incomplete = result.total_tasks - result.completed_tasks
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #1f2933;
      --muted: #667085;
      --line: #d8dee4;
      --accent: #0f766e;
      --code-bg: #101828;
      --code-ink: #f8fafc;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 16px/1.62 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .shell {{
      display: grid;
      grid-template-columns: minmax(220px, 300px) minmax(0, 1fr);
      gap: 28px;
      max-width: 1320px;
      margin: 0 auto;
      padding: 28px;
    }}
    aside {{
      position: sticky;
      top: 18px;
      align-self: start;
      max-height: calc(100vh - 36px);
      overflow: auto;
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 18px;
    }}
    main {{
      min-width: 0;
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 28px 34px;
    }}
    h1, h2, h3, h4, h5, h6 {{ line-height: 1.25; margin: 1.65em 0 0.55em; }}
    h1 {{ margin-top: 0; font-size: 2rem; }}
    h2 {{ border-top: 1px solid var(--line); padding-top: 1.1em; }}
    a {{ color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }}
    .anchor {{ color: var(--muted); text-decoration: none; margin-right: 0.25rem; }}
    .source, .muted {{ color: var(--muted); }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin: 16px 0 22px;
    }}
    .metric {{ border: 1px solid var(--line); padding: 12px; background: #fbfcfc; }}
    .metric strong {{ display: block; font-size: 1.35rem; }}
    .toc-title {{ margin: 0 0 8px; font-weight: 700; }}
    aside ol {{ list-style: none; margin: 0; padding: 0; }}
    aside li {{ margin: 6px 0; }}
    .toc-level-3 {{ padding-left: 14px; }}
    .toc-level-4, .toc-level-5, .toc-level-6 {{ padding-left: 28px; font-size: 0.95rem; }}
    code {{
      background: #eef2f6;
      padding: 0.12rem 0.3rem;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
    }}
    pre {{
      overflow: auto;
      background: var(--code-bg);
      color: var(--code-ink);
      padding: 16px;
      border-radius: 6px;
    }}
    pre code {{ background: transparent; color: inherit; padding: 0; }}
    table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
    th, td {{ border: 1px solid var(--line); padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f1f5f9; }}
    .task-row {{
      display: flex;
      gap: 10px;
      align-items: flex-start;
      border: 1px solid var(--line);
      padding: 9px 10px;
      margin: 7px 0;
      background: #fcfdfd;
    }}
    .task-row input {{ margin-top: 0.35rem; }}
    @media (max-width: 860px) {{
      .shell {{ display: block; padding: 14px; }}
      aside {{ position: static; max-height: none; margin-bottom: 14px; }}
      main {{ padding: 20px; }}
      .summary {{ grid-template-columns: 1fr; }}
    }}
    @media print {{
      body {{ background: white; }}
      .shell {{ display: block; padding: 0; }}
      aside {{ display: none; }}
      main {{ border: 0; padding: 0; }}
      a {{ color: inherit; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside>
      <p class="toc-title">Contents</p>
      {build_toc(result.headings)}
    </aside>
    <main>
      <p class="source">Source: {html.escape(str(source))}</p>
      <section class="summary" aria-label="Task summary">
        <div class="metric"><span>Total tasks</span><strong>{result.total_tasks}</strong></div>
        <div class="metric"><span>Completed</span><strong>{result.completed_tasks}</strong></div>
        <div class="metric"><span>Open</span><strong>{incomplete}</strong></div>
      </section>
      {result.body}
    </main>
  </div>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path, help="Markdown plan file to render")
    parser.add_argument("--output", type=Path, help="HTML output path. Defaults next to source.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.plan
    if not source.exists():
        raise SystemExit(f"Plan file not found: {source}")
    if source.suffix.lower() != ".md":
        raise SystemExit(f"Expected a Markdown .md file, got: {source}")

    output = args.output or source.with_suffix(".html")
    markdown = source.read_text(encoding="utf-8")
    result = render_markdown(markdown)
    output.write_text(build_html(source, result), encoding="utf-8")

    print(f"Rendered: {output}")
    print(
        "Summary: "
        f"{result.total_tasks} tasks, "
        f"{result.completed_tasks} completed, "
        f"{result.total_tasks - result.completed_tasks} open"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
