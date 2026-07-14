# Freqtrade Strategy Idea Validation Skill — Design

## Purpose

Create a reusable project skill, `validate-freqtrade-strategy-idea`, for turning a
user's algorithmic-trading idea into a scoped Freqtrade strategy experiment and
reporting whether the hypothesis is supported by backtest evidence. A positive
backtest is not proof that a strategy will work live.

## Skill boundary

The skill applies when a user asks to implement, backtest, or evaluate a
rule-based Freqtrade strategy idea in this repository. It will:

1. collect a complete idea contract before code changes;
2. state the falsifiable hypothesis and write a strategy note;
3. implement only the stated rules and conservative account controls;
4. run the appropriate local backtest when the user has requested it;
5. assess out-of-sample behavior, implementation bias, realistic costs, trade
   count, and drawdown; and
6. report `candidate`, `needs more validation`, or `rejected`.

The skill does not enable live trading, loosen fixed risk limits to improve a
result, or commit private configuration, market data, models, logs, or result
artifacts.

## Idea contract

### Required to implement

| Field | Required detail |
| --- | --- |
| Hypothesis | Why the defined setup should have an edge. |
| Market scope | Exchange, spot or futures, pairs, long/short direction, and base timeframe. |
| Initial entry | Exact data/indicator inputs and boolean trigger evaluated at a defined candle event. |
| Scale-in rules | Whether averaging down or pyramiding is used; the trigger and prohibition for each of the second and third entries. |
| Invalidation/stop | Exact price, indicator, or time condition that closes the trade. |
| Profit-taking | Target risk/reward or price/indicator conditions, partial-exit proportions, and final-exit rule. |
| No-trade conditions | Filters that prevent entry; explicitly write `none` if there are no filters. |
| Backtest scope | Historical period and pairs to test. |

Missing required fields cause the agent to ask targeted questions, not infer
trading rules. A strategy cannot be called a candidate without a separate
evaluation period and a meaningful trade count; if either is missing, its
outcome is `needs more validation`.

### Optional inputs

- leverage, margin mode, and maximum holding time;
- explicit fee, slippage, and funding assumptions;
- session, news, liquidity, or volume filters;
- baseline strategy and minimum trade-count target;
- parameters that may be explored and their allowed ranges; and
- TradingView/Pine source, chart image, or existing-strategy references.

When an optional item is absent, use the repository's relevant configuration
where possible and record the assumption. Do not silently optimize a missing
rule.

## Fixed conservative risk profile

The user-selected profile is a hard ceiling, not an optimization search space.

| Control | Rule |
| --- | --- |
| Entry allocation | 5% of account equity for each entry. |
| Scale-ins | At most three entries per trade: initial plus two additions. |
| Per-trade allocation | At most 15% of account equity across all entries. |
| Concurrent positions | At most two open positions. |
| Aggregate allocation | At most 30% of account equity. |
| Strategy drawdown | Must remain at or below 5% in acceptance backtests. |
| Drawdown circuit breaker | Stop new entries when live/dry-run strategy equity drawdown reaches 5%; require explicit human reset/review. |
| Daily-loss circuit breaker | Stop new entries when daily loss reaches 30%. This is a secondary emergency limit because the 5% drawdown control acts first. |

Partial exits and stop rules are required per idea; the skill supplies no
implicit profit targets or stops. The implementation must make scale-ins
conditional on the declared plan and must never add a position after the
declared invalidation condition is met.

## Workflow and outputs

1. Render the idea template and collect missing required fields.
2. Restate the hypothesis, rules, assumptions, and risk profile for approval.
3. Add a hypothesis-focused note in `docs/strategy-notes/` and implement the
   smallest strategy/configuration changes required.
4. Run static strategy checks, then the requested backtest. Use a closed date
   range; reserve a later, untouched period for evaluation when data permits.
5. Run relevant bias checks (`lookahead-analysis` for signal changes and
   `recursive-analysis` for recursive/window-sensitive indicators) when
   historical data supports them.
6. Report the return, trade count, win rate, profit factor, maximum drawdown,
   exposure, fees/slippage assumptions, duration, in-sample versus evaluation
   results, and limitations.
7. Make one of three evidence-based decisions:
   - `candidate`: complies with every fixed limit and is robust enough for
     broader historical testing and dry-run observation;
   - `needs more validation`: no disqualifying breach, but insufficient data,
     trades, out-of-sample evidence, or execution realism; or
   - `rejected`: violates a fixed control, lacks robustness, or does not
     support the hypothesis.

The skill keeps generated market data, trained models, logs, and backtest
exports out of Git. Its reusable artifact is the input template embedded in
`SKILL.md`; no separate automation script is needed in the first version.

## Testing

The skill itself will be pressure-tested with a realistic incomplete trading
idea before release. The test must show that it requests missing exit and
scale-in rules, preserves hard limits under a request to optimize profit, and
does not label a short or sparse result as a validated strategy. Basic skill
metadata validation must also pass.
