# Backtest Evaluation Template

Complete this record after pre-registering the idea, regime, preset IDs, values, and combinations. Development data may narrow candidates; the later evaluation period is untouched until this review. Do not change a combination after viewing evaluation results.

## Evaluation setup

- **Experiment name / version:** `[name]`
- **Idea and regime records:** `[links or paths]`
- **Development date range:** `[YYYY-MM-DD to YYYY-MM-DD]`
- **Untouched evaluation date range:** `[YYYY-MM-DD to YYYY-MM-DD; later and not used for selection]`
- **Pairs / instruments / venue / market type:** `[list]`
- **Timeframe(s):** `[list]`
- **Fee assumption:** `[maker/taker rate and methodology]`
- **Spread and slippage assumption:** `[method and amount]`
- **Funding assumption:** `[source, frequency, and treatment; N/A if not applicable]`
- **Minimum evaluation trade count:** `[integer, pre-declared]`
- **Selected IDs per layer:** `Stops: [up to two]; profit-taking: [up to two]; scale-in: [up to two].`
- **Pre-registered combination count:** `[1–8; link/path to enumeration]`

## Hard rejection gates

Reject regardless of profit if any condition is true:

- An entry exceeds 5% of account equity, a trade exceeds three entries or 15% total allocation, or concurrent exposure exceeds two positions or 30% aggregate allocation.
- The 5% strategy drawdown breaker or 30% daily-loss breaker is absent, bypassed, or breached.
- Acceptance/evaluation maximum drawdown is **greater than 5%**.
- Evaluation trade count is below the pre-declared minimum.
- More than two IDs were selected in any layer, more than eight combinations were tested, or the configuration differs from pre-registration.
- Any idea, regime, entry, exit, invalidation, or execution assumption is missing, ambiguous, or contradictory.

## Combination score table

Mark a row `Rejected` when any hard gate fails. Apply all fixed risk gates first, including acceptance/evaluation maximum drawdown at or below 5%. Then rank only untouched-evaluation survivors by expectancy, profit factor, and sufficient trade count; win rate and net return are secondary observations.

| Combination ID | Stop ID | Profit-taking ID | Scale-in ID | Expectancy | Profit factor | Trade count | Max drawdown | Win rate | Net return | Status |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `[C-01]` | `[ID]` | `[ID]` | `[ID]` | `[value]` | `[value]` | `[count]` | `[percent]` | `[percent]` | `[percent]` | `[Rejected / Survivor]` |
| `[C-02]` | `[ID]` | `[ID]` | `[ID]` | `[value]` | `[value]` | `[count]` | `[percent]` | `[percent]` | `[percent]` | `[Rejected / Survivor]` |

## Gate review and ranking

- **Rejected candidates and failed gate(s):** `[combination ID: reason]`
- **Untouched-evaluation survivor ranking:** `[rank by expectancy, then profit factor, confirming sufficient trades]`
- **Execution/fill caveats:** `[fees, spread, slippage, funding, gaps, liquidity, or data-quality limitations]`

## Decision — choose exactly one

Mark one and only one checkbox below; leave the other two unchecked.

- [ ] `Accept [one combination ID] for the next pre-registered step.`
- [ ] `Reject the experiment; no candidate passed the gates.`
- [ ] `Inconclusive; do not promote a candidate and define a new pre-registered experiment.`

**Decision rationale:** `[state the gate result and survivor ranking; profit cannot override a rejection gate]`
