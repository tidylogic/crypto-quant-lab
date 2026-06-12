# Environment Setup

This project uses Freqtrade through Docker Compose.

## Prerequisites

- Docker with the Compose plugin.
- Git.
- Python 3 for local helper scripts.

Freqtrade's Docker docs assume commands run from the directory containing `docker-compose.yml`.

## 1. Create Local Config Files

Tracked files are examples. Local config files are ignored by git.

```bash
cp user_data/configs/config.dryrun.example.json user_data/configs/config.dryrun.json
cp user_data/configs/config.freqai.example.json user_data/configs/config.freqai.json
cp user_data/configs/config.private.example.json user_data/configs/config.private.json
```

Edit `user_data/configs/config.private.json` only for local secrets. Keep it out of git.

`user_data/configs/config.ci.example.json` is only for GitHub-hosted PR backtests. It overrides the exchange to Binance US because hosted runner locations can be blocked by Binance.com even when local development works.

## 2. Pull The Freqtrade Image

```bash
docker compose pull
```

This repo uses `freqtradeorg/freqtrade:stable_freqai` in `docker-compose.yml` because FreqAI is part of the intended workflow.

## 3. Download Historical Data

```bash
bash scripts/download-data.sh
```

The script uses Freqtrade's `--prepend` option so reruns can fill older candles when a shorter local dataset already exists.

Optional overrides:

```bash
DATA_TIMERANGE=20240101-20240415 BACKTEST_TIMEFRAMES="1m 5m 15m" bash scripts/download-data.sh
```

## 4. Run A Manual Backtest

```bash
bash scripts/backtest.sh
```

Optional overrides:

```bash
STRATEGY=ScalpingFreqaiStrategy \
FREQAI_MODEL=LightGBMRegressor \
BACKTEST_TIMERANGE=20240301-20240415 \
BACKTEST_TIMEFRAME=1m \
BACKTEST_RESULT_DIR=user_data/backtest_results/manual \
bash scripts/backtest.sh
```

FreqAI backtesting requires a closed timerange. Use values like `20240301-20240415`, not `20240301-`. Downloaded data must start earlier than the backtest start date for FreqAI training and startup candles. Use a wider override for research runs after the environment smoke test passes.

## 5. Run Dry Mode

```bash
bash scripts/dry-run.sh
```

FreqUI is exposed on `127.0.0.1:8080` by `docker-compose.yml`.

## 6. PR Backtest Automation

The GitHub Actions workflow `.github/workflows/pr-backtest.yml` runs on strategy, FreqAI, config, script, and compose changes.

The workflow:

1. Copies example configs to local ignored config files.
2. Appends `config.ci.json` as a CI-only exchange override.
3. Pulls the Freqtrade Docker image.
4. Downloads data for the PR timerange.
5. Detects changed strategies.
6. Runs `freqtrade backtesting`.
7. Creates or updates a PR comment.

Repository variables can tune runtime:

- `PR_BACKTEST_TIMERANGE`
- `PR_DATA_TIMERANGE`
- `PR_BACKTEST_TIMEFRAME`
- `PR_BACKTEST_TIMEFRAMES`
- `PR_FREQAI_MODEL`
- `PR_FREQTRADE_EXTRA_CONFIGS`

## Safety

- Start with dry-run.
- Do not commit exchange keys.
- Backtests include assumptions and cannot replace dry-run or live forward testing.
