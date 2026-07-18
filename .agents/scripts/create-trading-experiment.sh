#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: bash .agents/scripts/create-trading-experiment.sh <experiment-slug> [--output-root DIR]

Create a trading experiment from the Korean Markdown templates.
Default output root: docs/strategy-notes/experiments
EOF
}

if [[ "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if [[ $# -lt 1 ]]; then
    usage >&2
    exit 1
fi

slug=$1
shift

if [[ ! $slug =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "Invalid experiment slug: $slug" >&2
    exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/../.." && pwd)
output_root="$repo_root/docs/strategy-notes/experiments"

if [[ $# -gt 0 ]]; then
    if [[ $1 != "--output-root" || $# -ne 2 || -z ${2:-} ]]; then
        usage >&2
        exit 1
    fi
    output_root=$2
fi

target="$output_root/$slug"
if [[ -e $target ]]; then
    echo "Refusing to overwrite existing experiment: $target" >&2
    exit 1
fi

template_root="$repo_root/.agents/templates/trading-experiments"
sources=(
    "strategy-idea-template.md:strategy-idea.md"
    "market-regime-template.md:market-regime.md"
    "backtest-evaluation-template.md:backtest-evaluation.md"
    "experiment-log-template.md:experiment-log.md"
)

for mapping in "${sources[@]}"; do
    source_file="$template_root/${mapping%%:*}"
    if [[ ! -f $source_file ]]; then
        echo "Missing source template: $source_file" >&2
        exit 1
    fi
done

mkdir -p -- "$target"
for mapping in "${sources[@]}"; do
    cp -- "$template_root/${mapping%%:*}" "$target/${mapping##*:}"
done

echo "Created trading experiment: $target"
