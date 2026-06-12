# Project Architecture

This repository is structured around Freqtrade's `user_data` convention and adds research, automation, and agent-supporting files around it.

```text
.
├── .agents/                  # Agent skills and rules, source of truth
├── .github/workflows/         # PR automation
├── docs/                      # Human-readable research and operations docs
├── scripts/                   # Local and CI automation
├── user_data/                 # Freqtrade user directory
│   ├── configs/               # Tracked example configs and ignored local configs
│   ├── strategies/            # Freqtrade strategies
│   ├── freqaimodels/          # Custom FreqAI model classes
│   ├── models/                # Ignored trained model artifacts
│   ├── data/                  # Ignored downloaded OHLCV data
│   └── backtest_results/      # Ignored backtest exports
└── docker-compose.yml         # Freqtrade runtime entrypoint
```

## Boundaries

- `user_data` is for Freqtrade runtime files and follows Freqtrade conventions.
- `docs` is for research process, setup, and interpretation policy.
- `scripts` is for deterministic commands used locally and in CI.
- `.agents` is for agent-owned rules and reusable skills. Do not duplicate those files in root-level `skills`.

## Strategy Change Flow

1. Edit `user_data/strategies` or FreqAI-related files.
2. Open a PR.
3. `.github/workflows/pr-backtest.yml` detects watched changes.
4. `scripts/pr-backtest.sh` runs Freqtrade backtesting with changed strategy classes.
5. `scripts/summarize-backtest.py` writes a markdown summary.
6. `scripts/upsert-pr-comment.py` creates or updates the PR comment.

