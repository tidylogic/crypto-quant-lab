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
    return sorted(str(path) for path in Path("user_data/strategies").glob("*.py"))


def detect(changed_files: list[str]) -> dict:
    watched_changes = [path for path in changed_files if path_is_watched(path)]
    changed_strategy_files = strategy_files_from_changes(changed_files)
    strategy_files = changed_strategy_files

    if watched_changes and not strategy_files:
        strategy_files = all_strategy_files()

    strategies: list[str] = []
    for file_name in strategy_files:
        strategies.extend(strategy_classes(Path(file_name)))

    return {
        "needs_backtest": bool(watched_changes and strategies),
        "changed_files": changed_files,
        "watched_changes": watched_changes,
        "strategy_files": strategy_files,
        "strategies": sorted(set(strategies)),
    }


def write_github_output(path: Path, payload: dict) -> None:
    strategies = " ".join(payload["strategies"])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"needs_backtest={str(payload['needs_backtest']).lower()}\n")
        handle.write(f"strategies={strategies}\n")
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
