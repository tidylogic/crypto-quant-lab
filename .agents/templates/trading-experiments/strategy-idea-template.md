# Strategy Idea Template

Use this template before development testing. A missing, ambiguous, or conflicting rule makes the idea ineligible: **do not trade**. Fill every bracketed field with a causal, completed-candle rule; do not use evaluation-period results to change it.

## Experiment identity

- **Experiment name / version:** `[name]`
- **Author and date pre-registered:** `[name, YYYY-MM-DD]`
- **Hypothesis:** `[If observable condition X occurs in market scope Y, then entry rule Z is expected to produce the stated risk-adjusted behaviour because ...]`
- **Direction:** `[long / short / both with separately stated rules]`
- **Decision timeframe / informative timeframes:** `[timeframe(s)]`

## Market scope

- **Pairs / instruments and venue:** `[list]`
- **Market type:** `[spot / perpetual / other]`
- **Permitted regime reference:** `[link or path to completed market-regime template]`
- **Excluded regime reference:** `[link or path to completed market-regime template]`
- **Trading session / timezone:** `[rule]`

## Exact initial entry

- **Data available at decision time:** `[completed-candle indicators, order-book/liquidity data, funding data, etc.]`
- **Long entry rule:** `[exact boolean condition, order type, and trigger timing]`
- **Short entry rule:** `[exact boolean condition, order type, and trigger timing, or N/A]`
- **Initial entry allocation:** `Exactly 5% of total account equity.`
- **Initial-entry cancellation rule:** `[condition that cancels an unfilled order]`

## No-trade rules and invalidation

- **No-trade rules:** `[each observable condition that blocks entry, including unavailable/ambiguous regime signals]`
- **In-position invalidation:** `[objective condition that proves the thesis wrong]`
- **Response to invalidation:** `[protective exit; no scale-in at or after invalidation]`
- **Conflicting signal rule:** `Do not trade.`

## Permitted risk-management preset IDs

Select at most two IDs in each layer from the [risk-management preset catalog](risk-management-presets.md). Leave unused fields as `N/A`. Select no more than eight total stop × profit-taking × scale-in combinations.

| Layer | First permitted ID | Second permitted ID | Exact pre-declared inputs / non-risk ranges |
| --- | --- | --- | --- |
| Stop | `[STOP-FIXED-PCT / STOP-ATR / STOP-STRUCTURE / STOP-CHANDELIER]` | `[ID or N/A]` | `[only catalog-permitted values]` |
| Profit-taking | `[TP-FIXED-R / TP-ATR-TRAIL / TP-INDICATOR]` | `[ID or N/A]` | `[only catalog-permitted values]` |
| Scale-in | `[SCALE-NONE / SCALE-AVERAGE-DOWN / SCALE-PYRAMID]` | `[ID or N/A]` | `[only catalog-permitted values]` |

### Non-risk parameter ranges

| Parameter | Pre-declared range or exact value | Rationale | Fixed before evaluation? |
| --- | --- | --- | --- |
| `[indicator / lookback / threshold / entry timing]` | `[bounded range]` | `[hypothesis rationale]` | `[yes]` |
| `[parameter]` | `[bounded range]` | `[hypothesis rationale]` | `[yes]` |

### Forbidden parameters and behaviours

- `[parameter or behaviour excluded from this experiment]`
- No retrospective parameter changes after viewing untouched evaluation results.
- No discretionary entries, exits, pivots, or regime overrides.
- No stop widening and no scale-in after invalidation or a stop trigger.

## Fixed account limits (not tunable)

- Every entry is exactly 5% of account equity.
- A trade has at most three entries and 15% total account allocation.
- At most two concurrent positions and 30% aggregate account allocation are allowed.
- A 5% strategy drawdown breaker stops the strategy for investigation before new allocation.
- A 30% daily-loss breaker stops opening positions for the rest of that day.

## Pre-registration acknowledgement

- **Development range:** `[start date to end date]`
- **Untouched evaluation range:** `[start date to end date; later than development]`
- **Combination count (maximum eight):** `[count and enumeration reference]`
- **Prepared by / date:** `[name, YYYY-MM-DD]`
