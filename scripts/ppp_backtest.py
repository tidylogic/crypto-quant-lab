#!/usr/bin/env python3
"""PPP A/B/C hypothesis research: strict SMA alignment, next-open crosses.

All inputs are genuine venue OHLCV. Closed trades only determine win rates.
No stop, profit target, leverage, funding, padding, or parameter optimization.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
START = int(datetime(2026, 4, 13, 15, tzinfo=timezone.utc).timestamp())
END = int(datetime(2026, 10, 13, 15, tzinfo=timezone.utc).timestamp())
MINUTE_START = 1789359300
PINE_FILES = {
    'A': 'ppp-a-stoch-rsi-v6.pine',
    'B': 'ppp-b-stochastic-v6.pine',
    'C': 'ppp-c-nested-stochastic-v6.pine',
}


@dataclass(frozen=True)
class Bars:
    timestamp: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    seconds: int

    def subset(self, indices):
        return Bars(*(getattr(self, key)[indices] for key in ('timestamp', 'open', 'high', 'low', 'close', 'volume')), self.seconds)


def iso(t):
    return datetime.fromtimestamp(int(t), timezone.utc).isoformat().replace('+00:00', 'Z')


def load(path: Path, seconds: int):
    values = np.loadtxt(path, delimiter=',', skiprows=1)
    if values.ndim != 2 or values.shape[1] != 6 or not np.isfinite(values).all():
        raise ValueError(f'Invalid data shape/values: {path}')
    timestamps = values[:, 0].astype(np.int64)
    if not np.array_equal(timestamps, values[:, 0]) or np.any(timestamps % seconds) or np.any(np.diff(timestamps) != seconds):
        raise ValueError(f'Unaligned timestamps or data gaps: {path}')
    o, h, l, c, v = values[:, 1:].T
    if np.any(values[:, 1:5] <= 0) or np.any(v < 0) or np.any(l > np.minimum(o, c)) or np.any(h < np.maximum(o, c)):
        raise ValueError(f'Invalid OHLCV bounds: {path}')
    return Bars(timestamps, o, h, l, c, v, seconds)


def resample(bars: Bars, seconds: int):
    if seconds < bars.seconds or seconds % bars.seconds:
        raise ValueError('Only whole multiples of the genuine base timeframe are allowed')
    if seconds == bars.seconds:
        return bars
    factor = seconds // bars.seconds
    if np.all(np.diff(bars.timestamp) == bars.seconds):
        aligned = np.flatnonzero(bars.timestamp % seconds == 0)
        if len(aligned):
            first = aligned[0]
            count = (len(bars.timestamp) - first) // factor
            take = slice(first, first + count * factor)
            arrays = [getattr(bars, name)[take].reshape(count, factor) for name in ('timestamp', 'open', 'high', 'low', 'close', 'volume')]
            t, o, h, l, c, v = arrays
            return Bars(t[:, 0], o[:, 0], h.max(axis=1), l.min(axis=1), c[:, -1], v.sum(axis=1), seconds)
    # Incomplete buckets are discarded, never upsampled or filled.
    boundaries = np.r_[0, np.flatnonzero(np.diff(bars.timestamp // seconds)) + 1, len(bars.timestamp)]
    rows = []
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        t = bars.timestamp[left:right]
        if len(t) == factor and t[0] % seconds == 0 and np.all(np.diff(t) == bars.seconds):
            rows.append((t[0], bars.open[left], bars.high[left:right].max(), bars.low[left:right].min(), bars.close[right-1], bars.volume[left:right].sum()))
    data = np.array(rows, dtype=float).reshape(-1, 6)
    return Bars(data[:, 0].astype(np.int64), *data[:, 1:].T, seconds)


def smooth(values, length, method='SMA'):
    values = np.asarray(values, dtype=float)
    result = np.full(len(values), np.nan)
    if length < 1:
        raise ValueError('Smoothing length must be positive')
    if length == 1:
        return values.copy()
    if len(values) < length:
        return result
    if method == 'SMA':
        windows = np.lib.stride_tricks.sliding_window_view(values, length)
        # Local means avoid a large cumulative-sum cancellation at 0/100 plateaus.
        result[length-1:] = windows.mean(axis=1)
        return result
    if method not in ('EMA', 'RMA'):
        raise ValueError(f'Unknown smoothing method: {method}')
    alpha = 2.0 / (length + 1) if method == 'EMA' else 1.0 / length
    seed = []
    previous = None
    for i, value in enumerate(values):
        if not np.isfinite(value):
            if previous is not None:
                result[i] = previous
            continue
        if previous is None:
            seed.append(value)
            if len(seed) == length:
                previous = float(np.mean(seed))
                result[i] = previous
        else:
            previous = alpha * value + (1-alpha) * previous
            result[i] = previous
    return result


def normalize(values, floor, ceiling):
    span = ceiling - floor
    result = np.full(len(values), np.nan)
    valid = np.isfinite(values) & np.isfinite(span)
    positive = valid & (np.round(span, 9) > 0)
    result[valid & ~positive] = 50.0
    result[positive] = np.clip(100 * (values[positive] - floor[positive]) / span[positive], 0, 100)
    return result


def rolling_range(values, length):
    floor = np.full(len(values), np.nan)
    ceiling = floor.copy()
    if len(values) >= length:
        windows = np.lib.stride_tricks.sliding_window_view(values, length)
        floor[length-1:] = windows.min(axis=1)
        ceiling[length-1:] = windows.max(axis=1)
    return floor, ceiling


def indicator(bars: Bars, model: str):
    """Mirror the committed prototype default formulas, without optimizing them."""
    if model == 'A':
        delta = np.r_[np.nan, np.diff(bars.close)]
        gain = smooth(np.maximum(delta, 0), 14, 'RMA')
        loss = smooth(np.maximum(-delta, 0), 14, 'RMA')
        rsi = np.full(len(delta), np.nan)
        valid = np.isfinite(gain) & np.isfinite(loss)
        zero_loss = np.round(loss, 9) == 0
        rsi[valid & zero_loss] = np.where(np.round(gain[valid & zero_loss], 9) == 0, 50, 100)
        nonzero = valid & ~zero_loss
        rsi[nonzero] = 100 - 100 / (1 + gain[nonzero] / loss[nonzero])
        floor, ceiling = rolling_range(rsi, 14)
        main = smooth(normalize(rsi, floor, ceiling), 3, 'SMA')
        signal = smooth(main, 3, 'SMA')
    elif model in ('B', 'C'):
        floor, _ = rolling_range(bars.low, 14)
        _, ceiling = rolling_range(bars.high, 14)
        raw = normalize(bars.close, floor, ceiling)
        if model == 'B':
            main = smooth(raw, 3, 'SMA')
            signal = smooth(main, 3, 'SMA')
        else:
            first = smooth(raw, 5, 'EMA')
            floor, ceiling = rolling_range(first, 14)
            main = smooth(normalize(first, floor, ceiling), 3, 'EMA')
            signal = smooth(main, 3, 'EMA')
    else:
        raise ValueError(f'Unknown model: {model}')
    return main, signal


def crosses(main, signal):
    # Pine float comparison operators round operands to 9 fractional digits.
    main = np.round(np.asarray(main, dtype=float), 9)
    signal = np.round(np.asarray(signal, dtype=float), 9)
    valid = np.isfinite(main) & np.isfinite(signal)
    previous = np.r_[False, valid[:-1]]
    previous_main = np.r_[np.nan, main[:-1]]
    previous_signal = np.r_[np.nan, signal[:-1]]
    up = valid & previous & (main > signal) & (previous_main <= previous_signal)
    down = valid & previous & (main < signal) & (previous_main >= previous_signal)
    return up, down


def sma_alignment(close):
    averages = [np.round(smooth(close, length, 'SMA'), 9) for length in (20, 50, 100, 200)]
    a, b, c, d = averages
    return (a > b) & (b > c) & (c > d), (a < b) & (b < c) & (c < d)


def simulate(bars: Bars, up, down, bull, bear, *, start, end, fee):
    if not 0 <= fee < 1 or start >= end:
        raise ValueError('Invalid evaluation period or fee')
    up, down, bull, bear = (np.asarray(values, dtype=bool) for values in (up, down, bull, bear))
    if any(len(values) != len(bars.timestamp) for values in (up, down, bull, bear)):
        raise ValueError('Signal and candle lengths differ')
    position = None
    trades = []
    missed_end_signals = 0
    # State changes based on close i fill at open i+1. Warm-up never opens trades.
    for i in range(len(bars.timestamp)):
        signal_open = int(bars.timestamp[i])
        signal_close = signal_open + bars.seconds
        if signal_open < start or signal_close > end:
            continue
        if i+1 == len(bars.timestamp):
            if up[i] or down[i]:
                missed_end_signals += 1
            continue
        fill_time = int(bars.timestamp[i+1])
        if fill_time != signal_close:
            raise ValueError('Cannot execute across a missing candle')
        if fill_time >= end:
            if up[i] or down[i]:
                missed_end_signals += 1
            continue
        price = float(bars.open[i+1])
        if position is not None:
            opposite = down[i] if position['direction'] == 1 else up[i]
            if opposite:
                ratio = price / position['entry_price']
                gross = position['direction'] * (ratio-1)
                net = gross - fee * (1+ratio)
                trades.append(dict(side=position['side'], entry_signal_time=position['entry_signal_time'],
                                   entry_time=position['entry_time'], exit_signal_time=signal_open,
                                   exit_time=fill_time, entry_price=position['entry_price'], exit_price=price,
                                   gross_return=gross, net_return=net, duration_minutes=(fill_time-position['entry_time'])/60))
                position = None
        if position is None:
            direction = 1 if up[i] and bull[i] else -1 if down[i] and bear[i] else 0
            if direction:
                position = dict(direction=direction, side='long' if direction == 1 else 'short',
                                entry_signal_time=signal_open, entry_time=fill_time, entry_price=price)
    # Last closed bar has no eligible next-open fill inside this half-open window.
    return dict(trades=trades, open_position=position, end_signals_without_fill=missed_end_signals)


def summarize(trades):
    n = len(trades)
    gross = np.array([trade['gross_return'] for trade in trades])
    net = np.array([trade['net_return'] for trade in trades])
    wins = int(np.count_nonzero(net > 1e-12))
    gross_wins = int(np.count_nonzero(gross > 1e-12))
    breakeven = int(np.count_nonzero(np.abs(net) <= 1e-12))
    gains = net[net > 0].sum()
    losses = -net[net < 0].sum()
    # Wilson 95% interval describes this sample; trades are not IID guarantees.
    if n:
        z = 1.959963984540054
        p = wins/n
        center = (p+z*z/(2*n))/(1+z*z/n)
        half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/(1+z*z/n)
        interval = [100*(center-half), 100*(center+half)]
    else:
        interval = None
    return dict(trades=n, wins=wins, losses=n-wins-breakeven, breakeven=breakeven,
                win_rate_pct=100*wins/n if n else None, gross_win_rate_pct=100*gross_wins/n if n else None,
                win_rate_wilson95_pct=interval, profit_factor=float(gains/losses) if losses else None,
                avg_net_return_pct=float(net.mean()*100) if n else None,
                avg_gross_return_pct=float(gross.mean()*100) if n else None,
                avg_duration_minutes=float(np.mean([t['duration_minutes'] for t in trades])) if n else None,
                long_trades=sum(t['side']=='long' for t in trades), short_trades=sum(t['side']=='short' for t in trades))


def run(output: Path, fee: float):
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    all_trades = []
    monthly = []
    provenance = []
    for venue, symbols in [('binance_um', ('BTCUSDT', 'ZECUSDT')), ('mexc', ('BTC_USDT', 'ZEC_USDT'))]:
        data_root = ROOT/'user_data/data'/('ppp-binance' if venue=='binance_um' else 'ppp-mexc')
        for symbol in symbols:
            minute_path = data_root/f'{symbol}-1m.csv' if venue=='binance_um' else data_root/f'{symbol}-Min1.csv'
            minutes = load(minute_path, 60)
            for tf in (1, 3, 5, 15):
                if venue=='mexc' and tf in (5, 15):
                    data_path = data_root/f'{symbol}-Min{tf}.csv'
                    bars = load(data_path, tf*60)
                else:
                    data_path = minute_path
                    bars = resample(minutes, tf*60)
                start = MINUTE_START if venue=='mexc' and tf in (1, 3) else START
                if not np.any(bars.timestamp == start) or int(bars.timestamp[-1])+bars.seconds != END:
                    raise ValueError(f'Incomplete evaluation boundary: {venue} {symbol} {tf}')
                mask = (bars.timestamp >= start) & (bars.timestamp < END)
                if np.count_nonzero(mask) != (END-start)//bars.seconds:
                    raise ValueError(f'Missing evaluation bars: {venue} {symbol} {tf}')
                bull, bear = sma_alignment(bars.close)
                for model in ('A', 'B', 'C'):
                    main, signal = indicator(bars, model)
                    up, down = crosses(main, signal)
                    result = simulate(bars, up, down, bull, bear, start=start, end=END, fee=fee)
                    trades = result['trades']
                    info = dict(venue=venue, symbol=symbol, timeframe_minutes=tf, model=model,
                                start_utc=iso(start), end_utc_exclusive=iso(END), six_months=start==START,
                                evaluation_bars=int(mask.sum()), **summarize(trades),
                                open_position=result['open_position'], end_signals_without_fill=result['end_signals_without_fill'])
                    summaries.append(info)
                    by_month = {}
                    for trade in trades:
                        record = dict(venue=venue, symbol=symbol, timeframe_minutes=tf, model=model, **trade)
                        all_trades.append(record)
                        month = datetime.fromtimestamp(trade['exit_time'], timezone.utc).strftime('%Y-%m')
                        by_month.setdefault(month, []).append(trade)
                    for month, group in by_month.items():
                        monthly.append(dict(venue=venue, symbol=symbol, timeframe_minutes=tf, model=model, exit_month_utc=month, **summarize(group)))
                    print(f'{venue} {symbol} {tf}m {model}: {info["trades"]} trades, net win {info["win_rate_pct"]:.2f}%, gross {info["gross_win_rate_pct"]:.2f}%', flush=True)
                provenance.append(dict(venue=venue, symbol=symbol, timeframe_minutes=tf, csv=str(data_path), sha256=hashlib.sha256(data_path.read_bytes()).hexdigest()))
    pine_hashes = {model: hashlib.sha256((ROOT/'docs/tradingview/ppp'/name).read_bytes()).hexdigest() for model, name in PINE_FILES.items()}
    report = dict(generated_at_utc=datetime.now(timezone.utc).isoformat(), period_utc=[iso(START), iso(END)],
                  fee_each_side=fee, leverage=1, slippage=0, funding_included=False,
                  rules={'long':'SMA20>SMA50>SMA100>SMA200 and golden cross', 'short':'SMA20<SMA50<SMA100<SMA200 and dead cross',
                         'exit':'opposite crossover regardless of current SMA alignment', 'fill':'next candle open',
                         'position':'one per model/symbol/timeframe; same-open reversal allowed only with alignment',
                         'unfinished':'excluded from closed-trade metrics, reported separately', 'cross_comparison':'round float operands to 9 fractional digits'},
                  defaults={'A':{'rsi':14,'range':14,'main':3,'signal':3,'ma':'SMA'},
                            'B':{'range':14,'main':3,'signal':3,'ma':'SMA'},
                            'C':{'range':14,'first':5,'second_range':14,'main':3,'signal':3,'ma':'EMA'}, 'extreme_filter':False},
                  pine_sha256=pine_hashes, engine_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  input_provenance=provenance, summaries=summaries, monthly=monthly)
    (output/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    scalar_rows = [{key:value for key,value in r.items() if key not in ('open_position','win_rate_wilson95_pct')} for r in summaries]
    for name, rows in [('summary.csv', scalar_rows), ('trades.csv', all_trades)]:
        with (output/name).open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    print(f'Wrote {len(summaries)} combinations and {len(all_trades)} closed trades to {output}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'user_data/backtest_results/ppp-2026-10-14')
    parser.add_argument('--fee', type=float, default=.0002)
    args = parser.parse_args()
    run(args.output, args.fee)


if __name__ == '__main__':
    main()
