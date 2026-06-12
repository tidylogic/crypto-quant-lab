#!/usr/bin/env bash
set -euo pipefail

TIMERANGE="${DATA_TIMERANGE:-${BACKTEST_TIMERANGE:-20240101-20240415}}"
TIMEFRAMES="${BACKTEST_TIMEFRAMES:-1m 5m 15m}"

docker compose run --rm freqtrade download-data \
  --config /freqtrade/user_data/configs/config.dryrun.json \
  --config /freqtrade/user_data/configs/config.freqai.json \
  --timerange "${TIMERANGE}" \
  --timeframes ${TIMEFRAMES}
