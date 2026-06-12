#!/usr/bin/env bash
set -euo pipefail

STRATEGY="${STRATEGY:-ScalpingFreqaiStrategy}"
FREQAI_MODEL="${FREQAI_MODEL:-LightGBMRegressor}"
TIMERANGE="${BACKTEST_TIMERANGE:-20240301-20240415}"
TIMEFRAME="${BACKTEST_TIMEFRAME:-1m}"
RESULT_DIR="${BACKTEST_RESULT_DIR:-user_data/backtest_results/manual}"

mkdir -p "${RESULT_DIR}"

docker compose run --rm freqtrade backtesting \
  --config /freqtrade/user_data/configs/config.dryrun.json \
  --config /freqtrade/user_data/configs/config.freqai.json \
  --strategy "${STRATEGY}" \
  --freqaimodel "${FREQAI_MODEL}" \
  --timerange "${TIMERANGE}" \
  --timeframe "${TIMEFRAME}" \
  --export trades \
  --backtest-directory "/freqtrade/${RESULT_DIR}"
