---
name: validate-freqtrade-strategy-idea
description: Use when a user wants to turn an algorithmic trading idea into a Freqtrade strategy, backtest it, or judge whether the hypothesis has enough evidence in this repository.
---

# Validate Freqtrade Strategy Idea

Turn a trading idea into a reproducible experiment, not a promise of live profitability. A profitable backtest is evidence to inspect; it is never proof.

## Required context

Before strategy edits, read `AGENTS.md`, `docs/architecture.md`, `docs/backtest-policy.md`, and `docs/strategy-workflow.md`. **REQUIRED SUB-SKILL:** Use `freqtrade-strategy-work` for strategy, FreqAI, and strategy-note changes.

## Idea contract

Request clarification for every missing, ambiguous, or conflicting required field. Do not infer a trading rule or proceed to code until every required rule is executable.

```markdown
## Strategy idea

- **Hypothesis:** Why should this setup have an edge?
- **Market scope:** Exchange; spot/futures; pairs; long/short; base timeframe.
- **Initial entry:** Exact inputs and boolean trigger, including when it is evaluated.
- **Scale-ins:** None, averaging down, or pyramiding. For entries 2 and 3: trigger and prohibition.
- **Invalidation / stop:** Exact price, indicator, or time condition for closing the trade.
- **Profit-taking:** Target risk/reward or exit condition; each partial-exit proportion; final-exit rule.
- **No-trade conditions:** Filters that block entry, or `none`.
- **Backtest scope:** Historical date range and pairs.
- **Reusable presets:** `none`, or the selected stop, profit-taking, and scale-in preset IDs.

## Optional context

- **Leverage / margin / maximum holding time:**
- **Fee, slippage, and funding assumptions:**
- **Session, news, liquidity, or volume filters:**
- **Baseline and minimum trade-count target:**
- **Parameters permitted for exploration, with ranges:**
- **References:** Pine script, chart, or existing strategy.
```

If an optional item is absent, use the relevant repository configuration where possible and name the assumption in the final report. If the evaluation range or meaningful trade count is absent, complete the experiment if otherwise possible but never return `candidate`; return `needs more validation`.

## Reusable trading-experiment presets

When reusable presets are selected, first read `.agents/templates/trading-experiments/template-index.md` and use its linked templates. The strategy idea must name every selected stop, profit-taking, and scale-in ID; an absent, ambiguous, conflicting, or unknown ID fails the complete-contract gate.

- Select no more than two IDs per layer: stop, profit-taking, and scale-in.
- Pre-register allowed values and enumerate no more than eight total combinations before viewing the untouched evaluation period. Do not add or change a combination after viewing evaluation results.
- Complete the evaluation record and log each result and rejection using the library templates.
- Apply its rejection protocol before ranking: reject any hard-gate failure, including any acceptance or evaluation maximum drawdown above 5%, regardless of profit.
- Rank only untouched-evaluation survivors by expectancy, profit factor, and sufficient pre-declared trade count. Treat win rate and net return as secondary observations; do not introduce undefined risk-adjusted metrics.

The preset library can only make exposure smaller or exits earlier; it cannot relax the risk profile below.

## Immutable conservative risk profile

Treat these as hard ceilings, not tunable parameters:

| Control | Limit |
| --- | --- |
| Allocation per entry | 5% of account equity |
| Scale-ins | Three entries maximum: initial plus two additions |
| Per-trade allocation | 15% of account equity maximum |
| Concurrent positions | Two maximum |
| Aggregate allocation | 30% of account equity maximum |
| Acceptance drawdown | 5% maximum |
| Drawdown circuit breaker | At 5% strategy equity drawdown, stop new entries until explicit human review/reset |
| Daily-loss circuit breaker | At 30% daily loss, stop new entries; this is an emergency backstop |

Do not alter these limits to make a backtest profitable. Map them to the current Freqtrade strategy/configuration capabilities after verifying the installed version and official local references. Keep entry sizing, maximum position adjustments, concurrent-trade controls, and runtime protections consistent with the profile. Never add a position once its declared invalidation condition has occurred.

When collecting clarification, restate every numeric limit in this table; do not substitute or omit one.

## Experiment workflow

1. Restate the complete contract, hypothesis, assumptions, and risk profile. Obtain approval if the user changed any rule after supplying the template.
2. Write or update `docs/strategy-notes/<strategy-name>.md` with the hypothesis, entries, exits, scale-ins, risk controls, and acceptance criteria.
3. Implement the smallest rule-based strategy change. Do not introduce FreqAI unless the idea requires a learned feature/target; if it does, document its target and model namespace.
4. Run static checks and strategy discovery first. Because the user explicitly requested evaluation, run the local backtest as a separate verification phase after the strategy edit. Use a closed date range and keep generated artifacts ignored.
5. Reserve a later untouched period for evaluation when data permits. Run `lookahead-analysis` after signal or feature changes and `recursive-analysis` after recursive or window-sensitive indicator changes when the data supports them.
6. Do not use a profit-only optimizer. Explore only user-authorized non-risk parameters and compare the untouched evaluation period with the development period.

## Decision and report

Report the exact dates, pairs, timeframe, configuration assumptions, fees/slippage/funding assumptions, return, trade count, win rate, profit factor, maximum drawdown, maximum exposure, average duration, and development-versus-evaluation results. Call out fill assumptions, sparse samples, regime concentration, and any unavailable bias check.

Reject an acceptance backtest with maximum drawdown above 5%, regardless of profit.

Select exactly one decision:

- **candidate:** Every hard limit passes and the result has sufficient trade count and later-period evidence to justify broader testing and dry-run observation.
- **needs more validation:** No hard-limit breach, but insufficient data, trade count, evaluation evidence, or execution realism.
- **rejected:** A hard limit is breached, the hypothesis is unsupported, or results depend on brittle/overfit behavior.

Never claim that the idea is proven or safe for live capital. Do not commit data, models, logs, result exports, private configs, or credentials.
