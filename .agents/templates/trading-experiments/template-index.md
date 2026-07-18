# Trading Experiment Template Library

Use these templates to turn an algorithmic-trading idea into a bounded, auditable experiment. They help compare defined hypotheses; they do not authorize a search for the most profitable parameters.

## Workflow

1. Complete the [strategy idea template](strategy-idea-template.md) and [market-regime template](market-regime-template.md). An absent, ambiguous, or conflicting rule means **do not trade** until it is resolved.
2. Choose at most two IDs from each layer in the [risk-management preset catalog](risk-management-presets.md): stop, profit-taking, and scale-in.
3. Pre-register the allowed values and enumerate no more than eight total combinations. Do not add combinations after viewing evaluation-period results.
4. Use development data only to narrow candidates. Evaluate survivors once on a later, untouched period with the [evaluation template](backtest-evaluation-template.md).
5. Record every result and rejection in the [experiment log](experiment-log-template.md).

## Non-negotiable account limits

| Control | Fixed limit | Effect |
| --- | ---: | --- |
| Initial entry allocation | 5% of total account equity | Each entry order is capped at 5%. |
| Entries per trade | 3; 15% total account equity | No fourth entry or total trade allocation above 15%. |
| Concurrent positions | 2; 30% total account equity | Reject new entries once either concurrent-position or aggregate-allocation ceiling is reached. |
| Strategy drawdown breaker | 5% | Stop the strategy and investigate before any new allocation. |
| Daily-loss breaker | 30% | Stop opening positions for the rest of the day. |

These ceilings remain fixed for every preset and every test. A preset can only make exposure smaller or exits earlier; it cannot relax a ceiling.

## Candidate selection and decision gates

| Condition | Decision |
| --- | --- |
| Idea, regime, order trigger, exit, or invalidation is missing, ambiguous, or contradictory | Reject before backtest. |
| More than two IDs selected in any layer, or more than eight combinations | Reject the experiment definition. |
| Any candidate breaches an account limit or has acceptance/evaluation backtest max drawdown above **5%** | Reject, regardless of profit. |
| Evaluation trade count is below the pre-declared minimum | Reject as insufficient evidence. |
| Candidate passes all gates | Only after applying the account limits and 5% drawdown hard gate first, rank untouched evaluation survivors by expectancy, profit factor, and sufficient trade count. |

Win rate and net return are secondary observations; they never override the gates or the primary ranking criteria.
