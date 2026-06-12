#!/usr/bin/env bash
set -euo pipefail

TIMERANGE="${DATA_TIMERANGE:-${BACKTEST_TIMERANGE:-20240101-20240415}}"
TIMEFRAMES="${BACKTEST_TIMEFRAMES:-1m 5m 15m}"
EXTRA_CONFIGS="${FREQTRADE_EXTRA_CONFIGS:-}"

CONFIG_ARGS=(
  --config /freqtrade/user_data/configs/config.dryrun.json
  --config /freqtrade/user_data/configs/config.freqai.json
)

for config in ${EXTRA_CONFIGS}; do
  CONFIG_ARGS+=(--config "${config}")
done

docker compose run --rm freqtrade download-data \
  "${CONFIG_ARGS[@]}" \
  --timerange "${TIMERANGE}" \
  --prepend \
  --timeframes ${TIMEFRAMES}
