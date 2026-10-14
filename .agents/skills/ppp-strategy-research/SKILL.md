---
name: ppp-strategy-research
description: Use when continuing PPP or trend-volume indicator research, testing a new coin, changing PPP entry/exit/risk rules, or interpreting this repository's PPP backtests.
---

# PPP strategy research

Read [continuation state](../../rules/ppp-research-continuation.md), the strategy catalog, and the relevant hypothesis note before choosing a model. Current defaults belong in that state, not in a new optimization. Repository commands are in the [research guide](../../../docs/research/ppp/README.ko.md).

## Contracts that change decisions

- Preserve the user's active baseline and archive drafts. A coin's highest observed profit does not select a universal model. Freeze hypotheses/costs before evaluation; existing large-cap validation checks source hashes and selection state.
- Signal and execution prices use the **same venue**. A different venue can be its own benchmark; do not splice Binance minute fills under MEXC signals. Short native coverage stays short, with timestamps, warmup and gaps checked.
- Higher-timeframe indicators become available only after their candle closes. Entry confirmation cannot reuse that candle's earlier minute wick. Close decisions fill at the next actual open, including the final-period boundary.
- Strict SMA alignment gates entries. Raw opposite indicator crosses still exit. Signal-timeframe MAs and 1-minute entry confirmation are separate clocks; MA-stop confirmation follows the chosen 1-minute or source-timeframe clock, not a fixed 5 minutes.
- For the support ladder, check the previously protected MA before replacing it; never loosen protection to evade failure. Deeper reentry requires a fresh qualified source signal. S2 applies to the **source candle containing actual entry**, with gap price and cash-availability time handled separately.
- Distinguish 1x net trade return, compounded leveraged equity, closed drawdown, intrabar drawdown bound, and zero-equity touches. Report costs, execution exclusions, trade count, and exposure. Low drawdown from sparse trades is not proof of better entries.
- Keep source data/results ignored. Preserve old journals and protocol hashes; compare like venue, period, timeframe, costs and capital. Observed-market reselection is not untouched validation.

For Freqtrade strategy/FreqAI edits, also use the existing `freqtrade-strategy-work` skill. Run custom backtests when requested; that does not authorize live orders. Python equivalence checks do not establish Pine compilation or reconstruction of the original video's undisclosed formula.
