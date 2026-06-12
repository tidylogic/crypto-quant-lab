#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${BASE_REF:-origin/${GITHUB_BASE_REF:-main}}"
HEAD_REF="${HEAD_REF:-HEAD}"
TIMERANGE="${BACKTEST_TIMERANGE:-20250301-20250415}"
TIMEFRAME="${BACKTEST_TIMEFRAME:-1m}"
FREQAI_MODEL="${FREQAI_MODEL:-LightGBMRegressor}"
RUN_ID="${GITHUB_RUN_ID:-local}"
RESULT_DIR="${BACKTEST_RESULT_DIR:-user_data/backtest_results/pr-${RUN_ID}}"
DETECTION_JSON="${RESULT_DIR}/detection.json"
COMMENT_BODY="${RESULT_DIR}/comment.md"
EXTRA_CONFIGS="${FREQTRADE_EXTRA_CONFIGS:-}"

mkdir -p "${RESULT_DIR}"
chmod a+rwx "${RESULT_DIR}"

python3 scripts/detect_changed_strategies.py \
  --base "${BASE_REF}" \
  --head "${HEAD_REF}" \
  --output "${DETECTION_JSON}"

NEEDS_BACKTEST="$(python3 -c "import json; print(str(json.load(open('${DETECTION_JSON}'))['needs_backtest']).lower())")"

if [[ "${NEEDS_BACKTEST}" != "true" ]]; then
  cat > "${COMMENT_BODY}" <<'COMMENT'
<!-- freqtrade-pr-backtest -->
## Freqtrade PR Backtest

No watched Freqtrade strategy, FreqAI model, config, or backtest script changes were detected.
COMMENT
  echo "No watched changes detected."
  exit 0
fi

STRATEGIES="$(python3 -c "import json; print(' '.join(json.load(open('${DETECTION_JSON}'))['strategies']))")"
if [[ -z "${STRATEGIES}" ]]; then
  echo "No strategy classes detected."
  exit 1
fi

CONFIG_ARGS=(
  --config /freqtrade/user_data/configs/config.dryrun.json
  --config /freqtrade/user_data/configs/config.freqai.json
)

CONFIG_COMMAND="--config /freqtrade/user_data/configs/config.dryrun.json --config /freqtrade/user_data/configs/config.freqai.json"
for config in ${EXTRA_CONFIGS}; do
  CONFIG_ARGS+=(--config "${config}")
  CONFIG_COMMAND="${CONFIG_COMMAND} --config ${config}"
done

COMMAND="docker compose run --rm freqtrade backtesting ${CONFIG_COMMAND} --strategy-list ${STRATEGIES} --freqaimodel ${FREQAI_MODEL} --timerange ${TIMERANGE} --timeframe ${TIMEFRAME} --export trades --backtest-directory /freqtrade/${RESULT_DIR}"

echo "${COMMAND}"
docker compose run --rm freqtrade backtesting \
  "${CONFIG_ARGS[@]}" \
  --strategy-list ${STRATEGIES} \
  --freqaimodel "${FREQAI_MODEL}" \
  --timerange "${TIMERANGE}" \
  --timeframe "${TIMEFRAME}" \
  --export trades \
  --backtest-directory "/freqtrade/${RESULT_DIR}"

python3 scripts/summarize-backtest.py \
  --results-dir "${RESULT_DIR}" \
  --detection "${DETECTION_JSON}" \
  --output "${COMMENT_BODY}" \
  --command "${COMMAND}" \
  --timerange "${TIMERANGE}" \
  --timeframe "${TIMEFRAME}" \
  --freqai-model "${FREQAI_MODEL}"

echo "PR comment body: ${COMMENT_BODY}"
