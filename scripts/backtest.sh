#!/usr/bin/env bash
set -euo pipefail

STRATEGY="${STRATEGY:-ScalpingFreqaiStrategy}"
FREQAI_MODEL="${FREQAI_MODEL:-LightGBMRegressor}"
TIMERANGE="${BACKTEST_TIMERANGE:-20240301-20240415}"
TIMEFRAME="${BACKTEST_TIMEFRAME:-1m}"
RESULT_DIR="${BACKTEST_RESULT_DIR:-user_data/backtest_results/manual}"
EXTRA_CONFIGS="${FREQTRADE_EXTRA_CONFIGS:-}"

mkdir -p "${RESULT_DIR}"

CONFIG_ARGS=(
  --config /freqtrade/user_data/configs/config.dryrun.json
  --config /freqtrade/user_data/configs/config.freqai.json
)

for config in ${EXTRA_CONFIGS}; do
  CONFIG_ARGS+=(--config "${config}")
done

docker compose run --rm freqtrade backtesting \
  "${CONFIG_ARGS[@]}" \
  --strategy "${STRATEGY}" \
  --freqaimodel "${FREQAI_MODEL}" \
  --timerange "${TIMERANGE}" \
  --timeframe "${TIMEFRAME}" \
  --export trades \
  --backtest-directory "/freqtrade/${RESULT_DIR}"
