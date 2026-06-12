#!/usr/bin/env python3
"""Create or update a marker-based GitHub PR comment."""

from __future__ import annotations

import argparse
import json
import os
import urllib.request
from pathlib import Path


def request(method: str, url: str, token: str, payload: dict | None = None) -> dict | list:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body", type=Path, required=True)
    parser.add_argument("--marker", default="<!-- freqtrade-pr-backtest -->")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--pr-number", default=os.environ.get("PR_NUMBER"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.repo or not args.pr_number or not args.token:
        raise SystemExit("GITHUB_REPOSITORY, PR_NUMBER, and GITHUB_TOKEN are required")

    body = args.body.read_text(encoding="utf-8")
    if args.marker not in body:
        body = f"{args.marker}\n{body}"

    base_url = f"https://api.github.com/repos/{args.repo}/issues/{args.pr_number}/comments"
    comments = request("GET", base_url, args.token)
    existing = next(
        (
            comment
            for comment in comments
            if isinstance(comment, dict) and args.marker in str(comment.get("body", ""))
        ),
        None,
    )

    if existing:
        request("PATCH", existing["url"], args.token, {"body": body})
        print(f"Updated PR comment {existing['id']}")
    else:
        created = request("POST", base_url, args.token, {"body": body})
        print(f"Created PR comment {created.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

