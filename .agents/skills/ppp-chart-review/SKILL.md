---
name: ppp-chart-review
description: Use when building or maintaining the PPP backtest chart gallery, keeping its server available across sessions, or diagnosing mobile trade navigation and scrolling in generated PPP charts.
---

# PPP chart review

Use the existing renderer/server contract rather than serving the whole repository. Read the [research guide](../../../docs/research/ppp/README.ko.md) for commands and the [continuation state](../../rules/ppp-research-continuation.md) for current UI behavior.

## Rendering and navigation

- `python3 scripts/ppp_chart_gallery.py` discovers supported configuration-bearing chart pages. Exclude generated gallery copies by marker, even when exporting into a different folder. Preserve original HTML, payloads, strategy status, venue and coverage labels.
- Default to recent candles while keeping full-history navigation. Trade rows retain their original indices through reverse sorting and filtering; invoke the existing trade-focus function for exact entry/exit ranges.
- Row selection changes the chart's time range, not the page position or journal visibility. Vertical finger gestures scroll the page; horizontal gestures pan the chart. Apply touch options when creating each chart so profile/theme rebuilds retain them.
- The HTTP server exposes only manifest-declared pages. Browser profiles, logs, configs and directory listings are not routes.

## Operations and actual mobile evidence

Use a persistent user service for ongoing access; a tool-session process is not a server-lifetime guarantee. Check enabled/active state, listening address, HTTP response and narrowly scoped restart recovery. Read live host settings locally; publish templates and placeholders, not deployment addresses or account data.

Default new servers to loopback. Existing sharing permission does not authorize a new public endpoint. Keep a requested private service on the node's confirmed private interface; diagnose process, port and peer connectivity before changing access policy.

Run the reusable helper when verifying this gallery:

```sh
python3 .agents/skills/ppp-chart-review/scripts/check_mobile.py --url http://127.0.0.1:8765/
```

It needs `websocket-client` and Chromium; the gallery/server itself does not. Native headless testing still follows host escalation rules. With Snap Chromium, place its profile under the ignored output directory in the checkout, not host `/tmp`; do not add `--no-sandbox`. A DevTools URL is startup evidence, not page-load verification.

Desktop clicks and viewport emulation alone are insufficient. Verify **real touch events**: row selection keeps the list; vertical swipes reach the bottom pane and return to the list; horizontal panning still works. Retain exact range/filter/profile regressions, screenshots and source hashes in ignored output.
