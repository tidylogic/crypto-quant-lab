# Risk-Management Preset Catalog

Choose no more than two IDs in each layer for one experiment. Every numeric interval below is a bounded hypothesis to pre-register, not a profit-search space. Test only the values declared before reviewing the untouched evaluation period.

All presets obey the fixed account limits in the [template index](template-index.md): 5% per entry, at most three entries / 15% total per trade, at most two positions / 30% aggregate, 5% strategy drawdown breaker, and 30% daily-loss breaker. Long/short formulas must be mirrored correctly, and fees, spread, slippage, and funding belong in the evaluation assumptions.

## Stop layer

### STOP-FIXED-PCT — Fixed percentage stop

- **Purpose / regime:** Simple, liquid markets with a stable, pre-declared maximum price loss.
- **Inputs / formula:** `p`; long stop = `average_entry × (1 - p)`, short stop = `average_entry × (1 + p)`.
- **Allowed range:** `p` from 0.5% to 3.0%, selected before testing.
- **Trigger:** Submit or maintain the protective stop immediately after every fill, recalculated from average entry only when a permitted scale-in occurs.
- **Prohibition:** Do not widen the stop after entry or after a loss; do not place a scale-in at or beyond invalidation.
- **Order / exit behavior:** Close the remaining position when the stop is executable; model gap/slippage assumptions in the backtest.
- **Caveats:** A fixed percentage may be too tight in high volatility or too loose in low volatility; verify the actual account loss remains inside all hard limits.

### STOP-ATR — ATR volatility stop

- **Purpose / regime:** Markets whose ordinary movement is meaningfully represented by an ATR measured on the decision timeframe.
- **Inputs / formula:** ATR period `n`, multiplier `k`; long stop = `average_entry - k × ATR(n)`, short stop = `average_entry + k × ATR(n)`.
- **Allowed range:** `n` from 7 to 28 candles and `k` from 1.0 to 4.0, with values pre-declared.
- **Trigger:** Establish the stop from the last completed-candle ATR at entry; update only according to the declared rule after permitted entries.
- **Prohibition:** Do not use an intrabar ATR unavailable at the decision time, widen `k` after entry, or scale in after invalidation.
- **Order / exit behavior:** Execute a full protective exit when price reaches the stop; account for stop execution and funding assumptions.
- **Caveats:** ATR can expand sharply around news or liquidations; a stale or illiquid ATR must make the regime ineligible.

### STOP-STRUCTURE — Market-structure stop

- **Purpose / regime:** Trend or range setups with an objectively detectable recent swing high/low.
- **Inputs / formula:** Lookback `n`, buffer `b × ATR`; long stop = last confirmed swing low minus buffer, short stop = last confirmed swing high plus buffer.
- **Allowed range:** `n` from 5 to 50 candles and `b` from 0.1 to 0.5 ATR.
- **Trigger:** Use only a swing confirmed by the pre-declared pivot definition before the entry decision.
- **Prohibition:** Do not select a subjective pivot after seeing the outcome, move invalidation farther away, or scale in after invalidation.
- **Order / exit behavior:** Close the remaining position when the structural level fails; an unconfirmed or unavailable swing means no trade.
- **Caveats:** Pivot confirmation can delay entries and introduce look-ahead bias if not implemented from completed candles only.

### STOP-CHANDELIER — ATR chandelier trailing stop

- **Purpose / regime:** Established directional moves where a trailing exit may retain upside while protecting a reversal.
- **Inputs / formula:** ATR period `n`, multiplier `k`, highest/lowest completed close since entry; long stop = highest close minus `k × ATR(n)`, short stop = lowest close plus `k × ATR(n)`. Declare a protective initial stop from another selected stop rule.
- **Allowed range:** `n` from 7 to 28 candles and `k` from 1.5 to 5.0.
- **Trigger:** Ratchet only in the favorable direction from completed-candle data after entry.
- **Prohibition:** Do not loosen the trailing level, use future highs/lows, or add to a position after its invalidation level is reached.
- **Order / exit behavior:** Exit the remaining position at the trailing stop; the initial protective stop remains active until the trail is valid.
- **Caveats:** It is vulnerable to whipsaw in ranges and needs an explicit initial-stop companion; do not silently treat it as a complete entry-risk definition.

## Profit-taking layer

### TP-FIXED-R — Fixed R-multiple partial exit

- **Purpose / regime:** Setups with a well-defined initial risk `R` and a need to realize part of a move predictably.
- **Inputs / formula:** Initial `R = |average_entry - initial_stop|`; target multiples `r1`, `r2` and first-exit fraction `q`; long target = entry plus `r × R`, short target = entry minus `r × R`.
- **Allowed range:** `r1` from 0.5R to 2.0R, `r2` from 1.5R to 5.0R, and `q` from 25% to 75%.
- **Trigger:** Take the pre-declared partial amount at each target, then apply the declared rule to the remainder.
- **Prohibition:** Do not change targets after observing a move, exceed the filled position size, or remove the protective stop from the remainder.
- **Order / exit behavior:** Use reduce-only partial exits; remaining size keeps its stop and any pre-declared trailing rule.
- **Caveats:** Partial exits can improve realized win rate while lowering trend capture; evaluate expectancy and profit factor, not win rate alone.

### TP-ATR-TRAIL — ATR target then trailing exit

- **Purpose / regime:** Volatile trends where a first target can fund a trailing remainder.
- **Inputs / formula:** ATR period `n`, first target multiplier `m`, first-exit fraction `q`, trailing multiplier `k`; target uses entry plus/minus `m × ATR(n)` and the remainder uses the declared ATR trail.
- **Allowed range:** `n` from 7 to 28, `m` from 1.0 to 4.0 ATR, `q` from 25% to 75%, and `k` from 1.5 to 5.0 ATR.
- **Trigger:** Take the partial target using completed-candle ATR, then ratchet the remainder's trail only favorably.
- **Prohibition:** Do not recalculate the target from future volatility, loosen the trail, or delete the initial protective stop before a valid trail exists.
- **Order / exit behavior:** Use reduce-only partial exit followed by the trailing stop for the remainder.
- **Caveats:** Combined target/trail logic can overlap with STOP-CHANDELIER; document which stop governs when both are present.

### TP-INDICATOR — Indicator-defined exit

- **Purpose / regime:** Mean-reversion or momentum-decay setups with a causal, observable exit signal.
- **Inputs / formula:** Named indicator, timeframe, source, threshold/cross condition, and fraction or full-exit rule; for example, close a long when completed-candle RSI(14) crosses below a pre-declared level.
- **Allowed range:** Period from 5 to 50, threshold from 10 to 90, and partial fraction from 25% to 100%; exact values must be pre-declared and appropriate to the named indicator.
- **Trigger:** Act only when the complete, causal indicator condition occurs on the declared timeframe.
- **Prohibition:** Do not use a vague "momentum fades" rule, intrabar hindsight, or indicator exits to bypass the protective stop.
- **Order / exit behavior:** Execute a reduce-only partial or full exit as defined; remaining exposure keeps its protective stop.
- **Caveats:** Indicator exits are easy to overfit. Missing indicator construction details make this preset ineligible.

## Scale-in layer

### SCALE-NONE — Single-entry position

- **Purpose / regime:** Baseline for all setups and the default when evidence for scaling is absent.
- **Inputs / formula:** One 5%-of-equity entry allocation; no further entries.
- **Allowed range:** Exactly one entry.
- **Trigger:** Enter only on the initial rule in the strategy idea.
- **Prohibition:** No averaging down, pyramiding, or discretionary add.
- **Order / exit behavior:** Manage the one position with the selected stop and profit presets.
- **Caveats:** This baseline must be included whenever scaling is proposed, so scaling has a comparable control.

### SCALE-AVERAGE-DOWN — Conditional averaging-down

- **Purpose / regime:** Explicitly range-bound or mean-reverting setups where an adverse move remains inside the original invalidation level.
- **Inputs / formula:** Up to three 5%-of-equity entries; exact adverse-move trigger, minimum spacing, and recalculated average entry must be declared before testing.
- **Allowed range:** One or two additional entries; each is exactly 5% of account equity, total trade allocation no greater than 15%.
- **Trigger:** Add only after the pre-declared unfavorable-price condition occurs while the regime remains valid and price is strictly before invalidation.
- **Prohibition:** Never add after invalidation, after a stop trigger, when the regime is no longer valid, or to recover a loss. Do not exceed three entries or 15% total allocation.
- **Order / exit behavior:** Recalculate position average and maintain one protective exit for total remaining exposure; partial exits are reduce-only.
- **Caveats:** Averaging down can conceal a weak entry rule and amplify tail losses. It needs a clear baseline (`SCALE-NONE`) and acceptance drawdown at or below 5%.

### SCALE-PYRAMID — Confirmation pyramiding

- **Purpose / regime:** Strong, liquid trends where price first moves favorably and a confirmation rule supports adding exposure.
- **Inputs / formula:** Up to three 5%-of-equity entries; exact favorable-move threshold, confirmation signal, spacing, and stop-ratchet rule must be declared.
- **Allowed range:** One or two additional entries; each is exactly 5% of account equity, total trade allocation no greater than 15%.
- **Trigger:** Add only after the pre-declared favorable move and confirmation occur while the position has not reached invalidation.
- **Prohibition:** Do not add on an adverse move, after invalidation, after a stop trigger, or when aggregate position limits are reached. Do not widen the stop to accommodate an add.
- **Order / exit behavior:** Apply a declared ratcheted protective stop to the aggregate position and reduce-only exits to filled quantity.
- **Caveats:** Pyramiding increases exposure near later-stage trend risk. Verify actual concurrent aggregate allocation stays at or below 30%.

