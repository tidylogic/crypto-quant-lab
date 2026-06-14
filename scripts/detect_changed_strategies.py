#!/usr/bin/env python3
"""Detect Freqtrade strategy work that should trigger a PR backtest."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
from pathlib import Path
from typing import Iterable


WATCHED_PREFIXES = (
    "user_data/strategies/",
    "user_data/freqaimodels/",
    "user_data/configs/",
    "scripts/",
    "docker-compose.yml",
)

SCOPED_STRATEGY_FILES = {
    "user_data/strategies/btc_rank_freqai_helpers.py": [
        "user_data/strategies/BtcRankFreqaiStrategy.py"
    ],
    "user_data/configs/config.btc-rank-freqai.example.json": [
        "user_data/strategies/BtcRankFreqaiStrategy.py"
    ],
}

GLOBAL_BACKTEST_FILES = {
    "docker-compose.yml",
    "scripts/download-data.sh",
    "user_data/configs/config.ci.example.json",
    "user_data/configs/config.dryrun.example.json",
    "user_data/configs/config.freqai.example.json",
    "user_data/configs/config.private.example.json",
}

SCOPED_BACKTEST_SCRIPT_FILES = {
    "scripts/backtest.sh",
    "scripts/pr-backtest.sh",
}

GLOBAL_BACKTEST_PREFIXES = (
    "user_data/freqaimodels/",
)

STRATEGY_TIMEFRAMES = {
    "BtcRankFreqaiStrategy": "5m",
    "ScalpingFreqaiStrategy": "1m",
}

STRATEGY_EXTRA_CONFIGS = {
    "BtcRankFreqaiStrategy": [
        "/freqtrade/user_data/configs/config.btc-rank-freqai.json",
    ],
}


def run_git_diff(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True,
        text=True,
        capture_output=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def path_is_watched(path: str) -> bool:
    return path.endswith(".py") and path.startswith("user_data/strategies/") or any(
        path.startswith(prefix) or path == prefix for prefix in WATCHED_PREFIXES
    )


def strategy_files_from_changes(changed_files: Iterable[str]) -> list[str]:
    return sorted(
        path
        for path in changed_files
        if path.startswith("user_data/strategies/")
        and path.endswith(".py")
        and not path.endswith("__init__.py")
    )


def global_backtest_changes(changed_files: Iterable[str]) -> list[str]:
    return [
        path
        for path in changed_files
        if path in GLOBAL_BACKTEST_FILES
        or any(path.startswith(prefix) for prefix in GLOBAL_BACKTEST_PREFIXES)
    ]


def scoped_backtest_script_changes(changed_files: Iterable[str]) -> list[str]:
    return [
        path
        for path in changed_files
        if path in SCOPED_BACKTEST_SCRIPT_FILES
    ]


def strategy_classes(path: Path) -> list[str]:
    if not path.exists():
        return []
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = {
            base.id if isinstance(base, ast.Name) else base.attr
            for base in node.bases
            if isinstance(base, (ast.Name, ast.Attribute))
        }
        if "IStrategy" in base_names or node.name.endswith("Strategy"):
            classes.append(node.name)
    return classes


def all_strategy_files() -> list[str]:
    return sorted(
        str(path)
        for path in Path("user_data/strategies").glob("*.py")
        if strategy_classes(path)
    )


def recommended_timeframe(strategies: Iterable[str]) -> str:
    timeframes = {
        STRATEGY_TIMEFRAMES.get(strategy, "1m")
        for strategy in strategies
    }
    if len(timeframes) == 1:
        return timeframes.pop()
    return "1m"


def recommended_extra_configs(strategies: Iterable[str]) -> list[str]:
    unique_strategies = sorted(set(strategies))
    if unique_strategies == ["BtcRankFreqaiStrategy"]:
        return STRATEGY_EXTRA_CONFIGS["BtcRankFreqaiStrategy"]
    return []


def detect(changed_files: list[str]) -> dict:
    watched_changes = [path for path in changed_files if path_is_watched(path)]
    broad_changes = global_backtest_changes(changed_files)
    scoped_script_changes = scoped_backtest_script_changes(changed_files)
    candidate_strategy_files = strategy_files_from_changes(changed_files)
    changed_strategy_files: list[str] = []
    mapped_helper_strategy_files: list[str] = []
    unmapped_helper_files: list[str] = []
    errors: list[str] = []

    for file_name in changed_files:
        mapped_helper_strategy_files.extend(SCOPED_STRATEGY_FILES.get(file_name, []))

    for file_name in candidate_strategy_files:
        path = Path(file_name)
        if not path.exists() or strategy_classes(path):
            changed_strategy_files.append(file_name)
        elif file_name in SCOPED_STRATEGY_FILES:
            continue
        else:
            unmapped_helper_files.append(file_name)

    strategy_files = sorted(set(changed_strategy_files + mapped_helper_strategy_files))
    if broad_changes:
        strategy_files = all_strategy_files()
    elif scoped_script_changes and not strategy_files:
        strategy_files = all_strategy_files()
    elif watched_changes and not strategy_files:
        strategy_files = all_strategy_files()
    elif unmapped_helper_files:
        strategy_files = sorted(set(strategy_files + all_strategy_files()))

    strategies: list[str] = []
    for file_name in strategy_files:
        path = Path(file_name)
        classes = strategy_classes(path)
        if file_name in changed_strategy_files:
            if not path.exists():
                errors.append(f"Changed strategy file does not exist: {file_name}")
            elif not classes:
                errors.append(f"No strategy class found in changed strategy file: {file_name}")
        strategies.extend(classes)

    if watched_changes and not changed_strategy_files and not strategies:
        errors.append("No strategy classes found under user_data/strategies")

    unique_strategies = sorted(set(strategies))

    return {
        "needs_backtest": bool(watched_changes and strategies and not errors),
        "changed_files": changed_files,
        "errors": errors,
        "watched_changes": watched_changes,
        "strategy_files": strategy_files,
        "strategies": unique_strategies,
        "recommended_timeframe": recommended_timeframe(unique_strategies),
        "recommended_extra_configs": recommended_extra_configs(unique_strategies),
    }


def write_github_output(path: Path, payload: dict) -> None:
    strategies = " ".join(payload["strategies"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"needs_backtest={str(payload['needs_backtest']).lower()}\n")
        handle.write(f"strategies={strategies}\n")
        handle.write(f"recommended_timeframe={payload['recommended_timeframe']}\n")
        handle.write(
            f"recommended_extra_configs={' '.join(payload['recommended_extra_configs'])}\n"
        )
        handle.write("detection_json<<EOF\n")
        handle.write(json.dumps(payload, indent=2, sort_keys=True))
        handle.write("\nEOF\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", help="Base git ref for diff detection")
    parser.add_argument("--head", default="HEAD", help="Head git ref for diff detection")
    parser.add_argument("--files", nargs="*", help="Explicit changed file list")
    parser.add_argument("--output", type=Path, help="Write detection JSON to this file")
    parser.add_argument("--github-output", type=Path, help="Append GitHub Actions outputs")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.files is not None:
        changed_files = args.files
    elif args.base:
        changed_files = run_git_diff(args.base, args.head)
    else:
        raise SystemExit("Provide --files or --base")

    payload = detect(changed_files)
    encoded = json.dumps(payload, indent=2, sort_keys=True)
    print(encoded)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    if args.github_output:
        write_github_output(args.github_output, payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
