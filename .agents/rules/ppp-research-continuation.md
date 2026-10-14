# PPP research continuation

Start by reading `docs/research/ppp/README.ko.md`, `docs/strategy-notes/ppp-research-findings.md`, and `docs/strategy-notes/ppp-strategy-catalog.json`. Do not restart the video reconstruction or rerun completed grids solely because a new session began.

## User intent and current choice

The target is a strategy that generalizes to reasonably liquid, higher-cap coins. The user observed late entries near trend endings and wants earlier, confirmed support/resistance entries. Coin selection is also a research direction.

G is named **추세·거래량 전략** and is the active research basis. A/B/C/D/E/F/H are drafts that remain readable. The active baseline is G/R2+S2, not the unqualified T2-R4 early-entry candidate. A user's naming choice does not assert G wins across coins.

Common entry prerequisite: SMA20>50>100>200 for longs, reverse order for shorts. G additionally uses nested Stochastic new cross, MFI14 >50/<50, and RVOL >=1.2. The raw opposite indicator cross exits even when entry filters fail.

Support ladder experiments use MAs from the **signal/source timeframe**, entry confirmation on 1-minute candles, and 20→50→100→200. Compare pre-entry waiting and deeper-line reentry after stops; reentry needs a fresh qualified signal. Compare MA-stop confirmation on 1 minute vs the source timeframe (3/5/15 respectively), not a universal fixed 5 minutes. S2 is a separate first-entry-source-candle 1% price stop. Fixed initial values are ATR tolerance 0.1 and signal validity 3 source candles; these are not established optima.

Historical fee assumption is MEXC user-specified 0.02% per side. Later same-venue Binance comparisons retained that common cost assumption. Initial capital $1,000, leverage 10, full net compounding are explicit theoretical comparisons, not a live sizing recommendation. Funding and fair-price liquidation are not modeled.

## Local evidence and source map

- `user_data/backtest_results/ppp-support-2026-10-14`: 792 rows, 28 full Binance six-month cases and 8 short native MEXC cases. Includes protocol, baseline/source/chart/browser audits and journals.
- `user_data/backtest_results/ppp-largecap-2026-10-14`: earlier-entry selection/validation and preserved baseline/drafts.
- Earlier risk/drawdown/selective/WLD grids remain under `user_data/backtest_results/ppp-*`.
- `user_data/backtest_results/ppp-chart-gallery`: 20 chart records at handoff, generated snapshots and mobile regression evidence. New results are discovered on regeneration; the historical number is not a fixed assertion for future tests.
- Pine: `docs/tradingview/ppp*`. Latest support-ladder rules exist in Python/HTML, not as a completed Pine port. Pine compile validation has not been performed in TradingView.

Runtime outputs and market data are intentionally not in Git. Check local artifacts first; a fresh clone needs market data and regenerated charts. Core research dates are frozen to April–October 2026. The generic asset CLI accepts explicit dates; fixed research grids require deliberate updates, not an implicit rolling period.

## Chart behavior and deployed service

The existing chart gallery now links to `research.html`: overview, strategies, experiments/results, statistics/figures, Pine view/copy/download and document library. `ppp_chart_gallery.py` regenerates both through `ppp_research_portal.py`. Curated reports, notes, figures/captures and aggregate CSVs are declared in manifest resources; original market data, trade CSVs, logs, profiles and configs remain unavailable. Code-copy uses a fallback on private HTTP, and images open in a zoom dialog. Original chart deep links and mobile journal behavior are preserved.

Initial viewport is about 240 execution candles on desktop / 120 on mobile. The journal includes closed strategy records and marks capital-unexecuted records. Sorting/filtering does not change underlying trade indices. A row selects the exact trade range with an hour's context at each end; it keeps the journal open and does not force page scrolling.

Vertical chart touch scrolls the document to lower panes; horizontal touch pans the time scale. Real-touch browser evidence covers bottom indicators and returning to the still-open journal. Do not restore auto-fold/`scrollIntoView` on row selection or vertical chart touch capture merely to make desktop tests pass.

The current host uses an enabled user service `ppp-chart-gallery.service`. The user authorized internal Tailscale sharing of the chart collection and included trades/indicators. Current deployment addresses are deliberately omitted from this public record; read `systemctl --user cat ppp-chart-gallery.service` and the node's own Tailscale status locally. The checked-in service is a portable, loopback-default template, separate from the installed unit. Do not overwrite the installed unit or publish a new endpoint just to continue research.

## Next meaningful work

1. Preserve baseline and compare entry timing/confirmation hypotheses using losing and missed-entry records, with trade count and exposure alongside drawdown.
2. Investigate support validity/ATR tolerance as explicit hypotheses. Do not tune each coin then call the result universal.
3. Test the **proposed**, unimplemented rolling coin selector: past 60-day evidence → next 7-day trading, fixed candidate membership as of that time, separate long/short ranking, same total portfolio capital/risk, no-trade option. Include untouched/new assets and costs. Seven observed assets are not broad validation.
4. Port the finally accepted support/reentry implementation into Pine only after defining its source/1-minute availability and execution differences. Preserve all draft sources.

Use `ppp-strategy-research` for research and `ppp-chart-review` for chart/server work. Update this handoff and the human findings when hypotheses, source periods or active choices change.
