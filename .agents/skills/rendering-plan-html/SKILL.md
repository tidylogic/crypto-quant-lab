---
name: rendering-plan-html
description: Use when a long Markdown implementation plan, especially a superpowers:writing-plans output under docs/superpowers/plans, should be converted into a readable standalone HTML companion for human review.
---

# Rendering Plan HTML

## Overview

Convert long implementation plans from Markdown to a standalone HTML file that is easier to scan, review, and execute. Keep the Markdown as the source of truth; the HTML is a readable companion artifact.

## Workflow

1. Locate the plan Markdown file. Prefer the path the user gave; otherwise use the newest `docs/superpowers/plans/*.md`.
2. Run the bundled converter:

```bash
python3 skills/rendering-plan-html/scripts/render_plan_html.py docs/superpowers/plans/example-plan.md
```

3. Save the output next to the plan by default as `example-plan.html`.
4. Verify the command prints the output path and summary counts.
5. Report both files to the user:
   - Markdown source
   - HTML companion

## Output Rules

- Do not replace the Markdown plan.
- Do not hand-write one-off HTML when the script can run.
- Preserve headings, checkboxes, numbered steps, code blocks, inline code, links, and simple tables.
- Include a sticky table of contents, task summary, readable typography, and print-friendly styling.
- Keep generated HTML local and dependency-free.

For the expected HTML contract, read `references/html-output-contract.md` when changing the converter.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| Leaving only the long Markdown plan | Generate the HTML companion before final handoff. |
| Creating a custom HTML layout each time | Use the bundled script for consistent output. |
| Treating HTML as source of truth | Edit the Markdown, then regenerate HTML. |
| Dropping checkboxes or code fences | Verify the rendered summary and visually inspect unusual sections if needed. |

