# BtcRankFreqaiStrategy Migration Result

## What Was Migrated

`../btc-rank-scalper`의 독립 실행형 rank scalper를 FreqAI 전략 실험으로 재구성했다.

Included:

- TP-before-SL long/short target logic.
- Single scalar FreqAI target compatible with the default `LightGBMRegressor`.
- Rank-style long/short decision gate.
- Original feature families: moving-average distance, RSI, volatility, volume ratio, order-block/FVG markers, long-range position, V3 chart-context features, and FreqAI-expanded multi-timeframe features.
- Expected-value filter using fee/slippage assumptions.
- Strategy adapter at `user_data/strategies/BtcRankFreqaiStrategy.py`.
- Testable pure helper module at `user_data/strategies/btc_rank_freqai_helpers.py`.

Excluded:

- Existing XGBoost model JSON files.
- BTC CSV market data.
- FastAPI prediction server.
- Windows supervisor scripts.
- .NET runner.
- OpenAI trade gate.
- Logs, runtime state, deployment env files, and credentials.

## Important Behavior Difference

This is not a byte-for-byte clone of the source bot.

The source bot loads trained XGBoost JSON models and calibrates predictions against a local historical distribution. This strategy lets FreqAI train models from the migrated targets and features. The trading idea is preserved, but model outputs, rank calibration, and signal timing can differ.

That difference is intentional for this repository. It keeps the strategy compatible with Freqtrade backtests, PR automation, and dry-run workflows, and avoids committing trained model artifacts.

The source bot also used explicit 1m, 5m, 1h, and 1d context. The BTC-rank overlay sets FreqAI `include_timeframes` to those values so the model can train on expanded features from the same timeframes. The post-prediction decision gate only uses direct `%-rank-m5-*` and `%-rank-h1-*` columns if FreqAI returns those names on the strategy dataframe; otherwise it falls back to the migrated 1m V3 MA slope features. Treat this as a known behavior difference when comparing against the standalone bot.

## FreqAI Target Shape

The strategy exposes one FreqAI label:

```text
&-rank-signal-score
```

It encodes the source bot's directional target as:

- `+1`: long TP is reached before long SL.
- `-1`: short TP is reached before short SL.
- `0`: neither side wins inside the target window.

This single-label shape is required for the repository's default `LightGBMRegressor` PR workflow.

## Default Long-Only Mode

The source bot evaluates both long and short candidates. This migration computes both long and short targets/ranks, but the strategy default is:

```python
can_short = False
```

Reason: the repository's default config is spot-oriented. A strategy with `can_short=True` can require futures-compatible Freqtrade configuration and pair formatting. The first migration keeps PR backtests and dry-runs from breaking by default.

To test source-like short behavior later:

1. Create a futures-specific config.
2. Confirm pair format and exchange support in Freqtrade.
3. Set `can_short = True`.
4. Run a short dedicated backtest before combining with other changes.

## What To Test First

Start with static and short-horizon checks:

```bash
python3 -m unittest tests.test_btc_rank_freqai_helpers
python3 -m unittest discover -s tests
python3 -m compileall user_data/strategies tests
```

Then use Freqtrade backtesting through the existing scripts or PR automation:

```bash
cp user_data/configs/config.btc-rank-freqai.example.json user_data/configs/config.btc-rank-freqai.json
STRATEGY=BtcRankFreqaiStrategy \
FREQAI_MODEL=LightGBMRegressor \
FREQTRADE_EXTRA_CONFIGS=/freqtrade/user_data/configs/config.btc-rank-freqai.json \
BACKTEST_TIMEFRAMES="1m 5m 1h 1d" \
BACKTEST_TIMERANGE=20250301-20250415 \
BACKTEST_TIMEFRAME=1m \
bash scripts/backtest.sh
```

Do not judge the strategy by profit alone. Review:

- Trade count.
- Profit after fees.
- Max drawdown.
- Average trade duration.
- Exit reason distribution.
- Signal frequency by market regime.
- Whether many entries come from the warmup/rank calibration boundary.
- Whether long-only mode misses most of the source bot's edge.

## Lookahead And Recursive Checks

The target intentionally uses future candles, but only inside `set_freqai_targets`. Feature functions must not use future data.

Prioritize:

- Freqtrade `lookahead-analysis` after any entry, exit, feature, or target change.
- Freqtrade `recursive-analysis` after changing rolling windows, MA periods, RSI periods, startup candle count, or rank windows.

## Tuning Knobs

Start with these before changing model type:

- `label_period_candles`: default `8`. Lower values make the scalp more immediate; higher values usually increase signal count but may lengthen trade duration.
- `include_timeframes`: BTC-rank overlay default `1m`, `5m`, `1h`, `1d`. Keep downloaded data aligned with this list.
- `minimal_roi["0"]`: default `0.0055`, matching the source TP.
- `stoploss`: default `-0.0045`, matching the source SL.
- `rank_window`: default `720`. Larger windows stabilize rank calibration; smaller windows adapt faster but overfit local regimes.
- `rank_min_periods`: default `120`. Increasing it avoids early noisy entries.
- `DecisionConfig.min_rank`: default `0.78`. Raise to reduce trades.
- `DecisionConfig.long_min_rank`: default `0.84`. Raise if long entries are too frequent or weak.
- `DecisionConfig.min_edge_rank`: default `0.03`. Raise to demand clearer long-vs-short separation.
- `DecisionConfig.min_expected_value`: default `0.00030`. Raise when fees/slippage erase edge.
- `DecisionConfig.long_min_trend`: default `-0.004`. Raise toward zero to avoid more counter-trend longs.

Tune one group at a time. After each change, compare trade count, drawdown, fees, and rejected signal reasons before looking at final profit.

## Suggested Iteration Order

1. Validate helper tests and compile checks.
2. Run a short PR-style backtest with default long-only behavior.
3. Inspect whether enough trades occur for the result to mean anything.
4. Tune `min_rank`, `long_min_rank`, and `min_edge_rank` for signal quality.
5. Tune `label_period_candles`, ROI, and stoploss together because they define the target.
6. Only after long-only behavior is understood, create a futures branch for short entries.
