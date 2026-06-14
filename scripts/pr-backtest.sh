#!/usr/bin/env bash
set -euo pipefail

BASE_REF="${BASE_REF:-origin/${GITHUB_BASE_REF:-main}}"
HEAD_REF="${HEAD_REF:-HEAD}"
TIMERANGE="${BACKTEST_TIMERANGE:-20250301-20250415}"
TIMEFRAME="${BACKTEST_TIMEFRAME:-}"
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

ERRORS="$(python3 -c "import json; print('\n'.join(json.load(open('${DETECTION_JSON}')).get('errors', [])))")"
if [[ -n "${ERRORS}" ]]; then
  {
    printf '%s\n' '<!-- freqtrade-pr-backtest -->'
    printf '%s\n\n' '## Freqtrade PR Backtest'
    printf '%s\n\n' 'Changed strategy detection failed.'
    while IFS= read -r error; do
      printf -- '- `%s`\n' "${error}"
    done <<< "${ERRORS}"
  } > "${COMMENT_BODY}"
  echo "${ERRORS}"
  exit 1
fi

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
if [[ -z "${TIMEFRAME}" ]]; then
  TIMEFRAME="$(python3 -c "import json; print(json.load(open('${DETECTION_JSON}')).get('recommended_timeframe', '1m'))")"
fi
RECOMMENDED_EXTRA_CONFIGS="$(python3 -c "import json; print(' '.join(json.load(open('${DETECTION_JSON}')).get('recommended_extra_configs', [])))")"

CONFIG_ARGS=(
  --config /freqtrade/user_data/configs/config.dryrun.json
  --config /freqtrade/user_data/configs/config.freqai.json
)

CONFIG_COMMAND="--config /freqtrade/user_data/configs/config.dryrun.json --config /freqtrade/user_data/configs/config.freqai.json"
append_config() {
  local config="$1"
  CONFIG_ARGS+=(--config "${config}")
  CONFIG_COMMAND="${CONFIG_COMMAND} --config ${config}"
}

for config in ${EXTRA_CONFIGS}; do
  append_config "${config}"
done
for config in ${RECOMMENDED_EXTRA_CONFIGS}; do
  append_config "${config}"
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
