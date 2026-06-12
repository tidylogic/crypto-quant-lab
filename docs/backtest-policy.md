# Backtest Policy

Backtests are evidence, not proof. Use them to reject weak ideas quickly and to compare changes under repeatable assumptions.

## PR Backtests

PR backtests are automatic, short-horizon checks for changed strategy work.

Watched paths:

- `user_data/strategies/**`
- `user_data/freqaimodels/**`
- `user_data/configs/**`
- `scripts/**`
- `docker-compose.yml`

Default PR settings:

- Data timerange: `20250101-20250415`
- Backtest timerange: `20250301-20250415`
- Timeframe: `1m`
- FreqAI model: `LightGBMRegressor`
- Result directory: `user_data/backtest_results/pr-<github-run-id>`

Override these with GitHub repository variables:

- `PR_BACKTEST_TIMERANGE`
- `PR_DATA_TIMERANGE`
- `PR_BACKTEST_TIMEFRAME`
- `PR_BACKTEST_TIMEFRAMES`
- `PR_FREQAI_MODEL`
- `PR_FREQTRADE_EXTRA_CONFIGS`

The default PR workflow appends `/freqtrade/user_data/configs/config.ci.json`. That CI override uses Binance US because GitHub-hosted runner locations can be blocked by Binance.com even when local development works. `PR_FREQTRADE_EXTRA_CONFIGS` can append additional config paths after the CI override.

## Required Review Questions

- Are there enough trades for the result to mean anything?
- Did profit survive fees?
- Is drawdown acceptable relative to expected capital?
- Did trade duration match the intended scalping behavior?
- Did the strategy rely on limit-fill assumptions that may not hold live?
- Did a FreqAI feature/model change also change `freqai.identifier`?

## Bias Checks

Run `lookahead-analysis` when entry/exit signal logic or features change. Run `recursive-analysis` when indicator windows, startup candle count, or recursive indicators change.

These checks require historical data. They are not part of the default PR workflow because they can be slower and may need a wider timerange to produce meaningful signal coverage.

FreqAI backtesting requires a closed timerange with both start and end dates. Do not use open-ended values such as `20250101-` for FreqAI PR or manual backtests. Downloaded data must start before the backtest start date so FreqAI has enough training and startup candles.

## Longer Research Runs

Use longer scheduled or manual backtests before promoting a strategy:

- Wider timeranges across market regimes.
- More pairs.
- `--timeframe-detail` when evaluating higher-timeframe entries or exits.
- Separate dry-run observation before live capital.
