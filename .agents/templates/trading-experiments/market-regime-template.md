# Market Regime Template

Use one completed record for each permitted and excluded regime. Conditions must be observable when the decision is made, use the declared data source/timeframe, and be assessed from completed data. If a required signal is unavailable or ambiguous, **do not trade**.

## Experiment and observation details

- **Experiment name / version:** `[name]`
- **Pairs / venue / market type:** `[list]`
- **Decision timestamp timezone:** `[timezone]`
- **Decision timeframe and data sources:** `[timeframe, exchange/indicator/funding sources]`

## Permitted regime

| Condition | Observable rule | Measurement timeframe / source | Required state |
| --- | --- | --- | --- |
| Trend | `[e.g., completed-candle MA relationship, slope, or structure rule]` | `[source]` | `[state]` |
| Volatility | `[e.g., ATR %, realized volatility, or range rule]` | `[source]` | `[state]` |
| Liquidity | `[e.g., volume, spread, depth, or order-book rule]` | `[source]` | `[state]` |
| Session | `[named session and UTC times]` | `[source]` | `[state]` |
| Funding | `[perpetual funding threshold/direction; N/A for non-perpetuals]` | `[source]` | `[state]` |

- **All permitted conditions must be true:** `[yes]`
- **Permitted-regime action:** `[allow only the pre-registered strategy entry]`

## Excluded regime

| Condition | Observable exclusion rule | Measurement timeframe / source | Exclusion action |
| --- | --- | --- | --- |
| Trend | `[rule]` | `[source]` | `Do not trade.` |
| Volatility | `[rule]` | `[source]` | `Do not trade.` |
| Liquidity | `[rule]` | `[source]` | `Do not trade.` |
| Session | `[rule]` | `[source]` | `Do not trade.` |
| Funding | `[rule]` | `[source]` | `Do not trade.` |

## Signal availability and conflicts

- **Unavailable required signal:** `Do not trade.`
- **Ambiguous, stale, inconsistent, or conflicting signal:** `Do not trade.`
- **Regime changes after entry:** `[pre-declared exit/hold rule; it cannot override protective stops or invalidation]`

## Fixed risk constraints that still apply

- Each entry is capped at 5% of account equity; no trade exceeds three entries or 15% total allocation.
- No more than two concurrent positions or 30% aggregate allocation may be open.
- Stop the strategy at a 5% strategy drawdown; stop opening positions for the day at a 30% daily loss.
