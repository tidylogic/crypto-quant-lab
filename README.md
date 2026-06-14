# crypto-quant-lab

Freqtrade-based crypto quant research lab for rule-based scalping strategies and FreqAI experiments.

## Structure

```text
.
├── .agents/
│   ├── rules/
│   └── skills/
├── .github/workflows/
│   └── pr-backtest.yml
├── docker-compose.yml
├── docs/
│   ├── architecture.md
│   ├── backtest-policy.md
│   ├── freqtrade-references.md
│   ├── setup.md
│   ├── strategy-workflow.md
│   ├── research/
│   └── strategy-notes/
├── scripts/
│   ├── backtest.sh
│   ├── detect_changed_strategies.py
│   ├── download-data.sh
│   ├── dry-run.sh
│   ├── pr-backtest.sh
│   ├── summarize-backtest.py
│   └── upsert-pr-comment.py
└── user_data/
    ├── backtest_results/
    ├── configs/
    │   ├── config.dryrun.example.json
    │   ├── config.freqai.example.json
    │   └── config.private.example.json
    ├── data/
    ├── freqaimodels/
    ├── hyperopt_results/
    ├── hyperopts/
    ├── logs/
    ├── models/
    ├── notebooks/
    ├── plot/
    └── strategies/
        └── ScalpingFreqaiStrategy.py
```

## Setup

Read [docs/strategy-workflow.md](docs/strategy-workflow.md) for the end-to-end human workflow, and [docs/setup.md](docs/setup.md) for the full environment setup.

Quick start:

```bash
cp user_data/configs/config.dryrun.example.json user_data/configs/config.dryrun.json
cp user_data/configs/config.freqai.example.json user_data/configs/config.freqai.json
cp user_data/configs/config.private.example.json user_data/configs/config.private.json
docker compose pull
bash scripts/download-data.sh
bash scripts/backtest.sh
```

## Research Workflow

For the full step-by-step process, use [docs/strategy-workflow.md](docs/strategy-workflow.md).

1. Write the strategy hypothesis in `docs/strategy-notes/`.
2. Implement strategy code in `user_data/strategies`.
3. Use FreqAI feature and target changes intentionally; change `freqai.identifier` for new feature/model experiments.
4. Open a PR. The PR workflow detects relevant strategy/config changes, runs a Freqtrade backtest with a closed timerange, summarizes the result, and writes a PR comment.
5. Promote only after backtest review and dry-run observation.

## Notes

- Keep strategies in `user_data/strategies`.
- Keep custom FreqAI model classes in `user_data/freqaimodels`.
- Keep trained FreqAI artifacts in `user_data/models`; this directory is ignored by git.
- Keep exchange keys in `user_data/configs/config.private.json` or environment variables, never in tracked config files.
- Start with dry-run and backtesting before live capital.
- Freqtrade docs are linked from [docs/freqtrade-references.md](docs/freqtrade-references.md).
