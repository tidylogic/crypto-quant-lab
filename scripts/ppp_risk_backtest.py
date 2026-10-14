#!/usr/bin/env python3
"""Close-confirmed risk exits for C/E/G; fixed rules, unchanged entry gates."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ppp_backtest import ROOT, START, END, iso, simulate, smooth, summarize
from ppp_combo_backtest import build_features, dataset_cases, model_signals, MODEL_RULES

MODELS = ('C', 'E', 'G')
PROFILES = {
    'R0': 'Original opposite-cross exit only',
    'R1': 'Close below SMA20 long / above SMA20 short',
    'R2': 'Close below SMA50 long / above SMA50 short',
    'R3': 'Later close below actual entry candle low long / above its high short',
    'R4': 'Close exceeds adverse 1.5 ATR(14), frozen at entry signal candle',
    'R5': 'R2 OR R3; first close trigger',
    'R6': 'R5 + fee-aware break-even after a close reaches net +1 entry ATR',
}


def risk_features(bars):
    previous = np.r_[np.nan, bars.close[:-1]]
    tr = np.fmax(bars.high-bars.low,
                 np.maximum(np.abs(bars.high-previous), np.abs(bars.low-previous)))
    return dict(sma20=smooth(bars.close, 20, 'SMA'), sma50=smooth(bars.close, 50, 'SMA'),
                atr=smooth(tr, 14, 'RMA'))


def simulate_risk(bars, up, down, bull, bear, features, *, profile, start, end, fee):
    if profile not in PROFILES or not 0 <= fee < 1 or start >= end:
        raise ValueError('Invalid risk profile, fee or evaluation period')
    up, down, bull, bear = (np.asarray(a, dtype=bool) for a in (up, down, bull, bear))
    n = len(bars.timestamp)
    if any(len(a) != n for a in (up, down, bull, bear)) or any(len(features[k]) != n for k in ('sma20', 'sma50', 'atr')):
        raise ValueError('Signal, risk feature and candle lengths differ')
    # Rounded comparisons follow the Pine contract of the existing indicator.
    sma20, sma50 = (np.round(features[k], 9) for k in ('sma20', 'sma50'))
    closes = np.round(bars.close, 9)
    position = None
    trades = []
    missed_end_signals = 0
    for i in range(n):
        signal_time = int(bars.timestamp[i])
        signal_close = signal_time + bars.seconds
        if signal_time < start or signal_close > end:
            continue
        if i+1 == n or int(bars.timestamp[i+1]) >= end:
            missed_end_signals += int(up[i] or down[i])
            continue
        fill_time = int(bars.timestamp[i+1])
        if fill_time != signal_close:
            raise ValueError('Cannot execute across a missing candle')
        fill_price = float(bars.open[i+1])
        exit_reason = None
        if position is not None:
            d = position['direction']
            entry = position['entry_price']
            adverse = lambda level: np.isfinite(level) and (closes[i] < np.round(level, 9) if d == 1 else closes[i] > np.round(level, 9))
            # The original raw opposite cross has priority, even if its entry gate fails.
            if down[i] if d == 1 else up[i]:
                exit_reason = 'opposite_cross'
            elif profile == 'R1' and adverse(sma20[i]):
                exit_reason = 'sma20'
            elif profile in ('R2', 'R5', 'R6') and adverse(sma50[i]):
                exit_reason = 'sma50'
            elif profile in ('R3', 'R5', 'R6') and i > position['entry_index']:
                # Never use the final entry candle's extrema before that candle closes.
                entry_level = bars.low[position['entry_index']] if d == 1 else bars.high[position['entry_index']]
                if adverse(entry_level):
                    exit_reason = 'entry_candle'
            if exit_reason is None and profile == 'R4' and adverse(entry-d*1.5*position['entry_atr']):
                exit_reason = 'atr_1_5'
            if exit_reason is None and profile == 'R6' and position['break_even_armed']:
                # d*(exit-entry) - fee*(entry+exit) = 0, on actual notionals.
                level = entry*(1+d*fee)/(1-d*fee)
                if adverse(level):
                    exit_reason = 'break_even'
            if exit_reason is not None:
                ratio = fill_price/entry
                gross = d*(ratio-1)
                trades.append(dict(side=position['side'], entry_signal_time=position['entry_signal_time'],
                                   entry_time=position['entry_time'], exit_signal_time=signal_time,
                                   exit_time=fill_time, entry_price=entry, exit_price=fill_price,
                                   gross_return=gross, net_return=gross-fee*(1+ratio),
                                   duration_minutes=(fill_time-position['entry_time'])/60,
                                   exit_reason=exit_reason, entry_atr=position['entry_atr'],
                                   break_even_armed=position['break_even_armed']))
                position = None
            elif profile == 'R6':
                # Activation is known only at this close; it applies to later closes.
                ratio = float(bars.close[i])/entry
                net_mark = d*(ratio-1)-fee*(1+ratio)
                if net_mark >= position['entry_atr']/entry:
                    position['break_even_armed'] = True
        if position is None and exit_reason in (None, 'opposite_cross'):
            # A risk-only exit waits for a new signal on a later candle.
            d = 1 if up[i] and bull[i] else -1 if down[i] and bear[i] else 0
            if d:
                atr = float(features['atr'][i])
                if profile in ('R4', 'R6') and (not np.isfinite(atr) or atr <= 0):
                    continue
                position = dict(direction=d, side='long' if d == 1 else 'short', entry_index=i+1,
                                entry_signal_time=signal_time, entry_time=fill_time,
                                entry_price=fill_price, entry_atr=atr, break_even_armed=False)
    return dict(trades=trades, open_position=position, end_signals_without_fill=missed_end_signals)


def risk_summary(trades):
    stats = summarize(trades)
    net = np.array([t['net_return'] for t in trades], dtype=float)
    winners, losers = net[net > 1e-12], -net[net < -1e-12]
    avg_win = float(winners.mean()) if len(winners) else None
    avg_loss = float(losers.mean()) if len(losers) else None
    # This is a closed-trade, 1x compounded equity model, not intrabar account DD.
    equity = np.r_[1., np.cumprod(1+net)]
    peaks = np.maximum.accumulate(equity)
    dd = float(np.max((peaks-equity)/peaks)*100)
    stats.update(avg_win_pct=avg_win*100 if avg_win is not None else None,
                 avg_loss_pct=avg_loss*100 if avg_loss is not None else None,
                 payoff_ratio=avg_win/avg_loss if avg_win is not None and avg_loss else None,
                 p95_loss_pct=float(np.percentile(losers, 95)*100) if len(losers) else None,
                 worst_trade_pct=float(net.min()*100) if len(net) else None,
                 closed_equity_max_drawdown_pct=dd,
                 exit_reasons=dict(Counter(t['exit_reason'] for t in trades)))
    return stats


def path_diagnostics(bars, trades, features):
    """Retrospective losers AND winners; no hypothetical stop-fill profits."""
    paths = []
    for t in trades:
        first = int(np.searchsorted(bars.timestamp, t['entry_time']))
        last = int(np.searchsorted(bars.timestamp, t['exit_time']))
        indexes = np.arange(first, last)
        d = 1 if t['side'] == 'long' else -1
        entry = t['entry_price']
        c = bars.close[indexes]
        # Include the actual exit-open fill, but no later exit-candle extrema.
        low = min(float(bars.low[indexes].min()), t['exit_price'])
        high = max(float(bars.high[indexes].max()), t['exit_price'])
        mae = max(0., (entry-low)/entry if d == 1 else (high-entry)/entry)
        mfe = max(0., (high-entry)/entry if d == 1 else (entry-low)/entry)
        wrong = lambda level: c < level if d == 1 else c > level
        conditions = dict(sma20=wrong(features['sma20'][indexes]), sma50=wrong(features['sma50'][indexes]),
                          entry_bar=wrong(bars.low[first] if d == 1 else bars.high[first]) & (indexes > first),
                          atr_1_5=wrong(entry-d*1.5*t['entry_atr']))
        hits = {k: int(np.flatnonzero(a)[0]+1) if a.any() else None for k, a in conditions.items()}
        paths.append(dict(side=t['side'], entry_time=t['entry_time'], exit_time=t['exit_time'],
                          net_return=t['net_return'], hold_bars=last-first, mae_pct=mae*100, mfe_pct=mfe*100,
                          risk_first_hits=hits))
    losing = [p for p in paths if p['net_return'] < -1e-12]
    winning = [p for p in paths if p['net_return'] > 1e-12]
    losses = sorted([-p['net_return'] for p in losing], reverse=True)
    count = max(1, int(np.ceil(len(losses)*.1)))
    stats = risk_summary(trades)
    stats.update(top10pct_loss_share_pct=100*sum(losses[:count])/sum(losses) if losses else None,
                 loss_median_bars=float(np.median([p['hold_bars'] for p in losing])) if losing else None,
                 win_median_bars=float(np.median([p['hold_bars'] for p in winning])) if winning else None,
                 candidates={k: dict(loss_hit_pct=100*sum(p['risk_first_hits'][k] is not None for p in losing)/len(losing) if losing else None,
                                     win_hit_pct=100*sum(p['risk_first_hits'][k] is not None for p in winning)/len(winning) if winning else None)
                             for k in ('sma20', 'sma50', 'entry_bar', 'atr_1_5')})
    return stats, paths


def run(output, fee=.0002, assets=('BTC','ZEC')):
    output.mkdir(parents=True, exist_ok=True)
    old = json.loads((ROOT/'user_data/backtest_results/ppp-combinations-2026-10-14/results.json').read_text())
    prior = {(r['venue'], r['symbol'], r['timeframe_minutes'], r['model']): r for r in old['summaries']}
    summaries, rows, diagnostics, paths, provenance = [], [], [], [], []
    split = int(datetime(2026, 8, 13, 15, tzinfo=timezone.utc).timestamp())
    for venue, symbol, tf, bars, start, data_path in dataset_cases(assets):
        f = build_features(bars)
        rf = risk_features(bars)
        for model in MODELS:
            sig = model_signals(model, f)
            args = (bars, sig['up'], sig['down'], sig['long_gate'], sig['short_gate'], rf)
            baseline = None
            for profile in PROFILES:
                result = simulate_risk(*args, profile=profile, start=start, end=END, fee=fee)
                trades = result['trades']
                stats = risk_summary(trades)
                if profile == 'R0':
                    baseline = stats
                    original = simulate(*args[:-1], start=start, end=END, fee=fee)
                    assert len(trades) == len(original['trades']), 'Baseline trade count changed'
                    for got, want in zip(trades, original['trades']):
                        assert {k: got[k] for k in want} == want, 'Baseline journal changed'
                    previous = prior.get((venue, symbol, tf, model))
                    if previous is not None:
                        assert stats['trades'] == previous['trades']
                        if fee == old['fee_each_side']:
                            assert stats['wins'] == previous['wins']
                    diagnostic, detail = path_diagnostics(bars, trades, rf)
                    identity = dict(venue=venue, symbol=symbol, timeframe_minutes=tf, model=model, six_months=start == START)
                    diagnostics.append(dict(**identity, **diagnostic))
                    paths.extend(dict(**identity, **p) for p in detail)
                segments = {}
                if start == START:
                    for label, left, right in [('first_four_months', start, split), ('last_two_months', split, END)]:
                        part = simulate_risk(*args, profile=profile, start=left, end=right, fee=fee)
                        segments[label] = dict(start_utc=iso(left), end_utc_exclusive=iso(right), **risk_summary(part['trades']))
                monthly = {}
                for t in trades:
                    key = datetime.fromtimestamp(t['exit_time'], timezone.utc).strftime('%Y-%m')
                    monthly.setdefault(key, []).append(t)
                record = dict(venue=venue, symbol=symbol, timeframe_minutes=tf, model=model, profile=profile,
                              start_utc=iso(start), end_utc_exclusive=iso(END), six_months=start == START, **stats,
                              delta_win_rate_pp=stats['win_rate_pct']-baseline['win_rate_pct'] if stats['trades'] else None,
                              delta_payoff=stats['payoff_ratio']-baseline['payoff_ratio'] if stats['payoff_ratio'] is not None and baseline['payoff_ratio'] is not None else None,
                              delta_expectancy_pp=stats['avg_net_return_pct']-baseline['avg_net_return_pct'] if stats['trades'] else None,
                              open_position=result['open_position'], end_signals_without_fill=result['end_signals_without_fill'],
                              temporal_segments=segments, monthly={k: risk_summary(v) for k, v in monthly.items()})
                summaries.append(record)
                rows.extend(dict(venue=venue, symbol=symbol, timeframe_minutes=tf, model=model, profile=profile, **t) for t in trades)
            print(f'{venue} {symbol} {tf}m {model}: baseline verified; six risk profiles completed', flush=True)
        provenance.append(dict(venue=venue, symbol=symbol, timeframe_minutes=tf, path=str(data_path),
                               sha256=hashlib.sha256(data_path.read_bytes()).hexdigest()))
    payload = dict(generated_at_utc=datetime.now(timezone.utc).isoformat(), period_utc=[iso(START), iso(END)],
                   assets=list(assets),
                   fee_each_side=fee, slippage=0, funding_included=False, leverage=1,
                   profiles=PROFILES, model_rules={m: MODEL_RULES[m] for m in MODELS},
                   parameters_fixed_before_run=True, selection='Retrospective baseline loss paths AND winner controls; no parameter grid search',
                   fill='Every cross/risk exit: confirmed close -> next open; gaps can exceed stop threshold',
                   entries='Unchanged strict SMA20/50/100/200 alignment + original model filter + C raw cross',
                   exit='Raw opposite C cross always exits; priority over risk; qualified reversal allowed',
                   risk_reentry='Risk-only exit cannot re-enter on that signal candle; wait for later new qualified cross',
                   entry_candle='Actual fill candle; its extrema available after close, breach evaluated on later closes only',
                   atr='Wilder ATR14 frozen on the signal candle preceding actual fill',
                   break_even='Net mark-to-close >=1 frozen ATR/entry arms from next candle; price=entry*(1+d*fee)/(1-d*fee)',
                   unfinished='No forced end exit; incomplete positions excluded from closed metrics',
                   payoff='Mean positive net return / abs(mean negative net return); distinct from profit factor',
                   drawdown='Closed-trade 1x compounded equity model; excludes intrabar drawdown and open position',
                   split='Independent first4month/last2month simulations; not an unseen holdout: full data used for diagnostic selection',
                   provenance=provenance,
                   engine_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), ROOT/'scripts/ppp_backtest.py', ROOT/'scripts/ppp_combo_backtest.py']},
                   summaries=summaries)
    (output/'results.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n')
    (output/'loss-diagnostics.json').write_text(json.dumps(dict(note='Retrospective path hit rates, not avoided losses; winner controls included', summaries=diagnostics), ensure_ascii=False, indent=2)+'\n')
    (output/'loss-paths.json').write_text(json.dumps(paths, ensure_ascii=False)+'\n')
    excluded = ('open_position', 'temporal_segments', 'monthly', 'exit_reasons', 'win_rate_wilson95_pct')
    for name, records in [('summary.csv', [{k: v for k, v in r.items() if k not in excluded} for r in summaries]), ('trades.csv', rows)]:
        with (output/name).open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]))
            writer.writeheader(); writer.writerows(records)
    print(f'Saved {len(summaries)} cases, {len(rows)} closed trades to {output}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'user_data/backtest_results/ppp-risk-2026-10-14')
    parser.add_argument('--fee', type=float, default=.0002)
    parser.add_argument('--assets', nargs='+', choices=['BTC','ETH','ZEC'], default=['BTC','ZEC'])
    options = parser.parse_args()
    run(options.output, options.fee, options.assets)
