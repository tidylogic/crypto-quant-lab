# Trading Experiment Template Library — Design

## Goal

Provide reusable, human-fillable modules for turning a trading idea into a
bounded Freqtrade experiment. The modules must support a small, explicit set
of interchangeable risk presets without turning a backtest into an unbounded
profit search.

## Location and boundaries

Store reusable agent-owned assets under
`.agents/templates/trading-experiments/`. The library is documentation only:
it does not add a strategy, change runtime configuration, or generate
backtest artifacts.

The existing `validate-freqtrade-strategy-idea` skill will point to the library
and require it when a user selects reusable presets.

## Modules

| File | Responsibility |
| --- | --- |
| `template-index.md` | Selection flow, hard limits, combination cap, and the evidence-based winner rule. |
| `risk-management-presets.md` | Hierarchical stop, profit-taking, and scale-in preset cards. |
| `strategy-idea-template.md` | Complete strategy contract plus permitted preset IDs. |
| `market-regime-template.md` | Tradeable and excluded regimes using observable trend, volatility, liquidity, and session rules. |
| `backtest-evaluation-template.md` | Development/evaluation split, cost assumptions, rejection gates, and comparison table. |
| `experiment-log-template.md` | Repeatable experiment record and promote/revise/reject decision. |

## Risk preset model

Presets are selected in three independent layers:

- **Stop layer:** fixed-percent, ATR volatility, market-structure, and ATR
  chandelier trail.
- **Profit-taking layer:** fixed-R partial exits, ATR target plus trail, and
  indicator-confirmed exit.
- **Scale-in layer:** no additional entry, conditional averaging-down, and
  confirmation-based pyramiding.

Every card specifies its ID, intended regime, inputs/formula, allowed
parameter range, trigger, explicit prohibition, cost/fill caveats, and
failure modes. A selected preset is a candidate rule, not permission to
optimize outside its declared range.

## Fixed risk controls

No template may override these existing ceilings:

- 5% account allocation per entry;
- three entries and 15% total allocation per trade;
- two concurrent positions and 30% aggregate allocation;
- 5% acceptance-backtest drawdown ceiling and runtime new-entry breaker; and
- 30% daily-loss emergency breaker.

No scale-in can occur after the declared invalidation condition. A candidate
with acceptance-backtest drawdown above 5% is rejected regardless of return.

## Experiment protocol

For each idea, select at most two IDs from each layer, yielding at most eight
candidate combinations. Predeclare non-risk parameters that may vary and keep
the risk ceilings fixed. Use the development period to narrow candidates and a
later untouched period for evaluation.

First reject candidates that breach a hard limit, lack an executable contract,
or have too few trades. Among remaining candidates, rank the evaluation period
by expectancy, profit factor, and sufficient trade count. Record win rate and
net return as secondary observations; neither selects a winner alone.

## Validation

Verify that every template exists, every preset ID referenced by the strategy
template exists in the preset catalog, all fixed limits appear in the index,
and the skill links to the index. Use a pressure scenario with an incomplete
idea to confirm the skill requests the missing module inputs rather than
inventing rules.
