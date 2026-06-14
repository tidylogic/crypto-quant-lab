#!/usr/bin/env bash
set -euo pipefail

STRATEGY="${STRATEGY:-ScalpingFreqaiStrategy}"
FREQAI_MODEL="${FREQAI_MODEL:-LightGBMRegressor}"
TIMERANGE="${BACKTEST_TIMERANGE:-20240301-20240415}"
TIMEFRAME="${BACKTEST_TIMEFRAME:-}"
RESULT_DIR="${BACKTEST_RESULT_DIR:-user_data/backtest_results/manual}"
EXTRA_CONFIGS="${FREQTRADE_EXTRA_CONFIGS:-}"
BTC_RANK_CONFIG="${BTC_RANK_CONFIG:-/freqtrade/user_data/configs/config.btc-rank-freqai.json}"

if [[ -z "${TIMEFRAME}" ]]; then
  if [[ "${STRATEGY}" == "BtcRankFreqaiStrategy" ]]; then
    TIMEFRAME="5m"
  else
    TIMEFRAME="1m"
  fi
fi

mkdir -p "${RESULT_DIR}"

CONFIG_ARGS=(
  --config /freqtrade/user_data/configs/config.dryrun.json
  --config /freqtrade/user_data/configs/config.freqai.json
)

append_config() {
  local config="$1"
  CONFIG_ARGS+=(--config "${config}")
}

for config in ${EXTRA_CONFIGS}; do
  append_config "${config}"
done

if [[ "${STRATEGY}" == "BtcRankFreqaiStrategy" && " ${EXTRA_CONFIGS} " != *" ${BTC_RANK_CONFIG} "* ]]; then
  append_config "${BTC_RANK_CONFIG}"
fi

docker compose run --rm freqtrade backtesting \
  "${CONFIG_ARGS[@]}" \
  --strategy "${STRATEGY}" \
  --freqaimodel "${FREQAI_MODEL}" \
  --timerange "${TIMERANGE}" \
  --timeframe "${TIMEFRAME}" \
  --export trades \
  --backtest-directory "/freqtrade/${RESULT_DIR}"
