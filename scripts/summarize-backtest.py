#!/usr/bin/env python3
"""Summarize exported Freqtrade backtest results as a PR comment body."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any


MARKER = "<!-- freqtrade-pr-backtest -->"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def newest_result_file(results_dir: Path) -> Path | None:
    candidates = [
        path
        for path in results_dir.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".json", ".zip"}
        and path.name.startswith("backtest-result")
        and not path.name.endswith(".meta.json")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def load_result(path: Path) -> Any:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            json_names = [
                name
                for name in archive.namelist()
                if name.endswith(".json") and not name.endswith(".meta.json")
            ]
            if not json_names:
                raise ValueError(f"No result JSON found inside {path}")
            with archive.open(sorted(json_names)[0]) as handle:
                return json.loads(handle.read().decode("utf-8"))
    return load_json(path)


def pick(mapping: dict, *names: str) -> Any:
    for name in names:
        if name in mapping and mapping[name] not in (None, ""):
            return mapping[name]
    return "n/a"


def format_count(value: Any) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def format_number(value: Any, decimals: int = 3) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.{decimals}f}"
    return str(value)


def format_ratio_percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value * 100:.2f}%"
    return str(value)


def format_plain_percent(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.2f}%"
    return str(value)


def strategy_payloads(result: Any) -> dict[str, dict]:
    if not isinstance(result, dict):
        return {}
    strategies = result.get("strategy")
    if isinstance(strategies, dict):
        return {name: value for name, value in strategies.items() if isinstance(value, dict)}
    if all(key in result for key in ("total_trades", "profit_total_abs")):
        return {"strategy": result}
    return {}


def format_strategy_table(strategies: dict[str, dict]) -> str:
    if not strategies:
        return "No parseable strategy metrics found in the exported result."

    lines = [
        "| Strategy | Trades | Total Profit % | Absolute Profit | Max Drawdown % | Wins | Draws | Losses | Profit Factor |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, data in strategies.items():
        profit_ratio = pick(data, "profit_total", "total_profit")
        profit_pct = (
            format_plain_percent(pick(data, "profit_total_pct"))
            if profit_ratio == "n/a"
            else format_ratio_percent(profit_ratio)
        )
        drawdown_ratio = pick(data, "max_drawdown_account", "max_relative_drawdown")
        drawdown_pct = (
            format_plain_percent(pick(data, "max_drawdown_pct"))
            if drawdown_ratio == "n/a"
            else format_ratio_percent(drawdown_ratio)
        )
        lines.append(
            "| {name} | {trades} | {profit_pct} | {profit_abs} | {drawdown} | {wins} | {draws} | {losses} | {pf} |".format(
                name=name,
                trades=format_count(pick(data, "total_trades", "trades")),
                profit_pct=profit_pct,
                profit_abs=format_number(pick(data, "profit_total_abs", "profit_abs", "total_profit_abs")),
                drawdown=drawdown_pct,
                wins=format_count(pick(data, "wins", "winning_trades")),
                draws=format_count(pick(data, "draws", "draw_trades")),
                losses=format_count(pick(data, "losses", "losing_trades")),
                pf=format_number(pick(data, "profit_factor"), decimals=2),
            )
        )
    return "\n".join(lines)


def build_comment(args: argparse.Namespace) -> str:
    detection = load_json(args.detection) if args.detection and args.detection.exists() else {}
    result_file = newest_result_file(args.results_dir)

    sections = [
        MARKER,
        "## Freqtrade PR Backtest",
        "",
        f"- Strategies: `{', '.join(detection.get('strategies', [])) or 'n/a'}`",
        f"- Timerange: `{args.timerange}`",
        f"- Timeframe: `{args.timeframe}`",
        f"- FreqAI model: `{args.freqai_model}`",
        f"- Result directory: `{args.results_dir}`",
        "",
        "### Changed Files",
    ]
    changed = detection.get("watched_changes") or detection.get("changed_files") or []
    sections.extend(f"- `{path}`" for path in changed)
    if not changed:
        sections.append("- No watched strategy/config changes detected.")

    sections.extend(["", "### Command", "", "```bash", args.command, "```", "", "### Result"])

    if result_file is None:
        sections.append("No exported backtest result file was found.")
    else:
        result = load_result(result_file)
        sections.append(f"Result file: `{result_file}`")
        sections.append("")
        sections.append(format_strategy_table(strategy_payloads(result)))

    sections.extend(
        [
            "",
            "### Review Notes",
            "",
            "- Backtesting includes Freqtrade's fee assumptions, but it does not prove live profitability.",
            "- For scalping strategies, review spread, slippage, fill quality, and dry-run behavior before live trading.",
        ]
    )
    return "\n".join(sections) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--detection", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--timerange", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--freqai-model", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_comment(args), encoding="utf-8")
    print(f"Wrote PR comment body: {args.output}")
    if newest_result_file(args.results_dir) is None:
        print(f"No exported backtest result file was found in {args.results_dir}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
