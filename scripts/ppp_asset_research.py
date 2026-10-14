#!/usr/bin/env python3
"""Reusable C/E/G research runner and independent strategy HTML exports.

Downloads remain separate: supply audited native CSV directories. Existing
indicator, close-confirmed risk and capital engines are used without changes.
"""
from __future__ import annotations
import argparse
import base64
import calendar
import csv
import gzip
import hashlib
import json
from datetime import datetime, timezone, timedelta
from html import escape
from pathlib import Path
import numpy as np
from ppp_backtest import ROOT, START, END, load, resample, smooth, iso, simulate
from ppp_combo_backtest import build_features, model_signals, MODEL_RULES
from ppp_risk_backtest import PROFILES, risk_features, simulate_risk, risk_summary
from ppp_capital_replay import replay

KST = timezone(timedelta(hours=9))
PROFILE_KO = {'R0':'반대 교차만', 'R1':'SMA20 종가 이탈', 'R2':'SMA50 종가 이탈',
              'R3':'진입 봉 고·저점 종가 이탈', 'R4':'신호 ATR × 1.5 종가 손절',
              'R5':'SMA50 또는 진입 봉 이탈', 'R6':'R5 + 수수료 반영 본전 청산'}
DEFAULT_PROFILE = {'C':'R4', 'E':'R0', 'G':'R2'}


def strategy_catalog():
    return json.loads((ROOT/'docs/strategy-notes/ppp-strategy-catalog.json').read_text())['strategies']


def kst(t):
    return datetime.fromtimestamp(int(t), KST).strftime('%Y-%m-%d %H:%M')


def six_month_period(start, end):
    left = datetime.fromtimestamp(start, KST)
    month_index = left.year*12+left.month-1+6
    year, month0 = divmod(month_index, 12)
    day = min(left.day, calendar.monthrange(year, month0+1)[1])
    right = left.replace(year=year, month=month0+1, day=day)
    return int(right.timestamp()) == end


def evaluation_start(bars, start, end, *, short_history=False):
    actual = max(start, ((int(bars.timestamp[0])+600*60+899)//900)*900) if short_history else start
    selected = (bars.timestamp >= actual) & (bars.timestamp < end)
    if actual >= end or selected.sum() != (end-actual)//bars.seconds or bars.timestamp[-1]+bars.seconds != end:
        raise ValueError('Incomplete data coverage')
    return actual


def decision_states(bars, signals, simulation, points, *, start, end, initial):
    """Reconstruct gates from actual fills, protecting risk-only exit bars."""
    n = len(bars.timestamp)
    pos = np.zeros(n, dtype=np.int8)
    entered = np.zeros(n, dtype=np.int8)
    queued = np.zeros(n, dtype=np.int8)
    events = np.full(n, np.nan)
    for t in simulation['trades']:
        a = int(np.searchsorted(bars.timestamp, t['entry_time']))
        z = int(np.searchsorted(bars.timestamp, t['exit_time']))
        d = 1 if t['side'] == 'long' else -1
        pos[a:z] = d
        entered[a-1] = d
        queued[z-1] = 1 if t['exit_reason'] == 'opposite_cross' else 2
    opened = simulation['open_position']
    if opened:
        a = int(np.searchsorted(bars.timestamp, opened['entry_time']))
        d = 1 if opened['side'] == 'long' else -1
        pos[a:] = d
        entered[a-1] = d
    for p in points:
        z = int(np.searchsorted(bars.timestamp, p['exit_time']))
        events[z] = p['closed_cash_usdt']
    allowed = (pos == 0) | (queued == 1)
    expected = np.where(signals['long_entry'], 1, np.where(signals['short_entry'], -1, 0))*allowed
    eligible = (bars.timestamp >= start) & (bars.timestamp+bars.seconds < end)
    if not np.array_equal(expected[eligible], entered[eligible]):
        raise ValueError('Original entry journal and diagnostic gates differ')
    masks = (128*allowed + 256*(pos == 1) + 512*(pos == -1) + 1024*(entered == 1)
             + 2048*(entered == -1) + 4096*(queued == 1) + 8192*(queued == 2))
    # Absolute snapshots avoid cancellation when a positive account dwindles
    # to much less than the initial balance. Never round it into bankruptcy.
    last = np.maximum.accumulate(np.where(np.isfinite(events), np.arange(n), -1))
    cash = np.full(n, float(initial))
    recorded = last >= 0
    cash[recorded] = events[last[recorded]]
    return masks, cash


def loss_streaks(trades):
    result = []
    run = []
    for i, t in enumerate(trades):
        if t['net_pct'] < -1e-10:
            run.append(i)
        else:
            if len(run) >= 2:
                result.append(run)
            run = []
    if len(run) >= 2:
        result.append(run)
    return sorted(result, key=lambda a: (-len(a), a[0]))[:10]


def market_cases(asset, binance_data, mexc_data, start, end):
    for venue, directory, symbol in [('binance_um', binance_data, asset+'USDT'), ('mexc', mexc_data, asset+'_USDT')]:
        if directory is None:
            continue
        path = directory/(symbol+('-1m.csv' if venue == 'binance_um' else '-Min1.csv'))
        minutes = load(path, 60)
        for tf in (1, 3, 5, 15):
            source = directory/f'{symbol}-Min{tf}.csv' if venue == 'mexc' and tf in (5, 15) else path
            bars = load(source, tf*60) if source != path else resample(minutes, tf*60)
            case_start = evaluation_start(bars, start, end, short_history=venue == 'mexc' and tf in (1, 3))
            warm = int(np.count_nonzero(bars.timestamp < case_start))
            if warm < 200:
                raise ValueError(f'{venue} {symbol} {tf}m needs at least 200 warmup bars')
            yield venue, symbol, tf, bars, case_start, source


def encode(value):
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    return base64.b64encode(gzip.compress(raw, compresslevel=9, mtime=0)).decode()


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(args):
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    summaries, all_trades, provenance = [], [], []
    exports = {m: [] for m in args.models}
    packs = {m: {} for m in args.models}
    six_months = six_month_period(args.start, args.end)
    for venue, symbol, tf, bars, start, source in market_cases(args.asset, args.binance_data, args.mexc_data, args.start, args.end):
        f, rf = build_features(bars), risk_features(bars)
        smas = [smooth(bars.close, n) for n in (20, 50, 100, 200)]
        take = np.flatnonzero((bars.timestamp >= start) & (bars.timestamp < args.end))
        provenance.append(dict(venue=venue, symbol=symbol, timeframe_minutes=tf, source=str(source.resolve()),
                               sha256=hashlib.sha256(source.read_bytes()).hexdigest(), start_kst=kst(start), end_exclusive_kst=kst(args.end),
                               candles=len(take), full_period=start == args.start, six_months=start == args.start and six_months))
        for model in args.models:
            g = model_signals(model, f)
            bits = (g['up'].astype(int)+2*g['down'].astype(int)+4*f['bull'].astype(int)+8*f['bear'].astype(int))
            columns = ['open','high','low','close','sma20','sma50','sma100','sma200','main','signal','bits','atr']
            fields = [bars.open,bars.high,bars.low,bars.close,*smas,f['main_c'],f['signal_c'],bits,rf['atr']]
            if model == 'E':
                h = np.round(f['hist'], 9)
                p = np.r_[np.nan, h[:-1]]
                bits += 16384*((h > 0) & (h > p))+32768*((h < 0) & (h < p))
                columns += ['macd','macd_signal','hist','hist_previous']
                fields += [f['main_macd'],f['signal_macd'],f['hist'],np.r_[np.nan,f['hist'][:-1]]]
            elif model == 'G':
                bits += 16*(np.round(f['mfi'],9)>50)+32*(np.round(f['mfi'],9)<50)+64*(np.round(f['rvol'],9)>=1.2)
                columns += ['mfi','rvol']
                fields += [f['mfi'], f['rvol']]
            # Native OHLC are untouched; indicator precision is display-only.
            rows = [[int(v[i]) if j == 10 else float(v[i]) if j < 4 else round(float(v[i]), 8) for j,v in enumerate(fields)] for i in take]
            if any(not np.isfinite(r).all() for r in rows):
                raise ValueError('Unavailable indicators inside evaluation period')
            key = f'{venue}-{tf}'
            meta = dict(key=key,venue=venue,symbol=symbol,timeframe_minutes=tf,start=start,end=args.end,step=bars.seconds,
                        start_kst=kst(start),end_kst=kst(args.end),full_period=start == args.start,six_months=start == args.start and six_months,count=len(rows),columns=columns)
            profile_data = []
            for profile in args.profiles:
                simulation = simulate_risk(bars,g['up'],g['down'],g['long_gate'],g['short_gate'],rf,
                                           profile=profile,start=start,end=args.end,fee=args.fee)
                trades = simulation['trades']
                if profile == 'R0':
                    baseline = simulate(bars,g['up'],g['down'],g['long_gate'],g['short_gate'],start=start,end=args.end,fee=args.fee)
                    common = [{k:t[k] for k in baseline['trades'][0]} for t in trades] if baseline['trades'] else trades
                    if common != baseline['trades']:
                        raise ValueError('R0 differs from original simulator')
                stats = risk_summary(trades)
                capital, points = replay(bars,trades,open_position=simulation['open_position'],fee=args.fee,initial=args.initial,leverage=args.leverage)
                state, cash = decision_states(bars,g,simulation,points,start=start,end=args.end,initial=args.initial)
                point_map = {p['exit_time']:p for p in points}
                previous_cash = args.initial
                records = []
                for n, t in enumerate(trades, 1):
                    p = point_map.get(t['exit_time'])
                    account_pct = (p['closed_cash_usdt']/previous_cash-1)*100 if p and previous_cash > 0 else None
                    if p:
                        previous_cash = p['closed_cash_usdt']
                    record = dict(n=n,side=t['side'],entry=t['entry_time'],exit=t['exit_time'],signal_time=t['entry_signal_time'],
                                  exit_signal_time=t['exit_signal_time'],ep=t['entry_price'],xp=t['exit_price'],net_pct=t['net_return']*100,
                                  account_pct=account_pct,cash=p['closed_cash_usdt'] if p else None,capital_executed=p is not None,
                                  reason=t['exit_reason'],entry_atr=t['entry_atr'],break_even_armed=t['break_even_armed'])
                    records.append(record)
                    all_trades.append(dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,profile=profile,**t,
                                           account_pct=account_pct,closed_cash_usdt=record['cash'],capital_executed=record['capital_executed']))
                summary = dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,profile=profile,
                               full_period=start == args.start,six_months=start == args.start and six_months,start_kst=kst(start),end_exclusive_kst=kst(args.end),**stats,**capital)
                summaries.append(summary)
                # The account cash and position masks are reconstructed lazily from
                # this exact journal in the browser, instead of duplicating bars 7x.
                profile_data.append(dict(profile=profile,label=PROFILE_KO[profile],summary=summary,trades=records,
                                         open_position=simulation['open_position'],streaks=loss_streaks(records),
                                         audit=dict(entries=len(trades)+bool(simulation['open_position']),eligible_bars=len(take)-1,
                                                    state_sha256=hashlib.sha256(state[take].tobytes()).hexdigest(),last_cash=float(cash[take[-1]]))))
                print(f'{venue} {symbol} {tf}m {model}/{profile}: n={stats["trades"]} win={stats["win_rate_pct"]} payoff={stats["payoff_ratio"]} cash={capital["end_marked_equity_usdt"]:.2f}',flush=True)
            packed = dict(**meta,rows=rows,profiles=profile_data)
            compressed = encode(packed)
            packs[model][key] = compressed
            exports[model].append(meta)
            (output/f'{model}-{key}.json.gz').write_bytes(base64.b64decode(compressed))
    results = dict(asset=args.asset,start_kst=kst(args.start),end_exclusive_kst=kst(args.end),fee_each_side=args.fee,
                   initial_cash=args.initial,leverage=args.leverage,models=args.models,profiles=args.profiles,
                   strategy_rules={m:MODEL_RULES[m] for m in args.models},risk_rules={p:PROFILES[p] for p in args.profiles},
                   fill='Confirmed close; next native candle open. Risk-only exits cannot reenter on the same signal bar.',
                   excluded=['funding','slippage','fair-price liquidation','lot/order-size constraints'],
                   capital='Independent full-margin compound accounts; zero-equity OHLC touches invalidate interpretation as a live continuation.',
                   provenance=provenance,summaries=summaries)
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
    write_csv(output/'summary.csv',[{k:v for k,v in r.items() if not isinstance(v,(dict,list,tuple))} for r in summaries])
    write_csv(output/'trades.csv',all_trades)
    export_reports(args, results, exports, packs)


def export_reports(args, results, exports, packs):
    template = (ROOT/'scripts/templates/ppp-strategy-chart.html').read_text()
    vendor = (ROOT/'scripts/vendor/lightweight-charts-5.0.9.js').read_text()
    license_text = (ROOT/'scripts/vendor/APACHE-2.0.txt').read_text()
    catalog = strategy_catalog()
    files = []
    for model in args.models:
        markets = exports[model]
        default_market = getattr(args,'default_market',None) or next((c['key'] for c in markets if c['venue']=='mexc' and c['timeframe_minutes']==5),markets[0]['key'])
        preferred = getattr(args, 'default_profile', None) or DEFAULT_PROFILE[model]
        configuration = dict(asset=args.asset,model=model,model_name=catalog[model]['name'],strategy_status=catalog[model]['status'],model_rule=MODEL_RULES[model],initial=args.initial,leverage=args.leverage,fee=args.fee,
                             markets=markets,default_market=default_market,default_profile=preferred if preferred in args.profiles else args.profiles[0],
                             summaries=[r for r in results['summaries'] if r['model']==model],
                             profile_labels=getattr(args, 'profile_labels', {}),
                             model_rule_override=getattr(args, 'model_rule_override', None),
                             experimental_profiles=getattr(args, 'experimental_profiles', []),
                             qualified_training=getattr(args, 'qualified_training', None),
                             native_execution=getattr(args, 'native_execution', False),
                             fill_note=getattr(args, 'fill_note', None),
                             slippage_note=getattr(args, 'slippage_note', None))
        blocks = '\n'.join(f'<script type="application/octet-stream" id="data-{key}">{value}</script>' for key,value in packs[model].items())
        title = f'{args.asset} · {catalog[model]["name"]}'+(' · 초안' if catalog[model]['status']=='draft' else '')
        document = template.replace('@@TITLE@@',escape(title)).replace('@@CONFIG@@',json.dumps(configuration,ensure_ascii=False).replace('<','\\u003c')).replace('@@PAYLOADS@@',blocks).replace('@@VENDOR@@',vendor).replace('@@LICENSE@@',license_text)
        filename = f'{args.asset.lower()}-{model.lower()}-strategy.html'
        path = args.output/filename
        path.write_text(document)
        files.append(dict(model=model,name=catalog[model]['name'],status=catalog[model]['status'],file=filename,bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    full_sources = ' · '.join(f'{p["venue"]} {p["timeframe_minutes"]}분' for p in results['provenance'] if p['full_period'])
    short_sources = ' · '.join(f'{p["venue"]} {p["timeframe_minutes"]}분 ({p["start_kst"]} 이후)' for p in results['provenance'] if not p['full_period'])
    lines = ['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<style>body{font:16px system-ui;max-width:1100px;margin:24px auto;padding:0 16px}table{border-collapse:collapse;width:100%}td,th{padding:9px;border-bottom:1px solid #aaa;text-align:left}.scroll{overflow:auto}</style>',
             f'<title>{escape(args.asset)} 전략별 백테스트</title><h1>{escape(args.asset)} · 전략별 백테스트</h1>',
             f'<p>{results["start_kst"]} → {results["end_exclusive_kst"]} KST (종료 시각 미포함). 편도 수수료 {args.fee*100:g}%, 초기 ${args.initial:g} · {args.leverage:g}배 전액 재투자.</p>',
             f'<p>요청 기간 전체: {escape(full_sources)}. 짧은 자료: {escape(short_sources) or "없음"}. {escape(getattr(args,"slippage_note",None) or "이론 자산 모형에서 펀딩·슬리피지·실제 강제청산·주문 수량 제한은 제외합니다.")}</p>',
             '<ul>'+''.join(f'<li><a href="{f["file"]}">{f["name"]} · {"활성" if f["status"]=="active" else "초안(draft)"}</a></li>' for f in sorted(files,key=lambda f:f['status']!='active'))+'</ul>',
             '<p>손익비 = 평균 수익 거래 수익률 ÷ 평균 손실 거래 손실률(수수료 포함, 1배 기준). 최대 낙폭은 거래 종료 잔고와 OHLC 상한을 구분합니다. 각 조합은 독립 계좌입니다.</p>',
             '<div class="scroll"><table><thead><tr><th>거래소</th><th>분</th><th>전략</th><th>청산</th><th>6개월</th><th>거래</th><th>승률 %</th><th>손익비</th><th>종료 자산 $</th><th>폐쇄 낙폭 %</th><th>OHLC 상한 %</th><th>0접촉</th></tr></thead><tbody>']
    fmt=lambda v: '—' if v is None else f'{v:.3g}' if 0 < v < .01 else f'{v:,.2f}'
    for r in results['summaries']:
        values=[r['venue'],r['timeframe_minutes'],catalog[r['model']]['name']+(' (초안)' if catalog[r['model']]['status']=='draft' else ''),r['profile'],'예' if r['six_months'] else '요청 기간' if r['full_period'] else '짧은 기간',r['trades'],fmt(r['win_rate_pct']),fmt(r['payoff_ratio']),fmt(r['end_marked_equity_usdt']),fmt(r['closed_drawdown_pct']),fmt(r['ohlc_drawdown_upper_bound_pct']),r['price_zero_equity_events']]
        lines.append('<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in values)+'</tr>')
    lines.append('</tbody></table></div></html>')
    (args.output/'index.html').write_text('\n'.join(lines))
    (args.output/'html-manifest.json').write_text(json.dumps(dict(files=files,engine_sha256={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in ['ppp_asset_research.py','ppp_backtest.py','ppp_combo_backtest.py','ppp_risk_backtest.py','ppp_capital_replay.py']}),indent=2)+'\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asset',required=True)
    parser.add_argument('--binance-data',type=Path)
    parser.add_argument('--mexc-data',type=Path)
    parser.add_argument('--start',default=iso(START))
    parser.add_argument('--end',default=iso(END))
    parser.add_argument('--models',nargs='+',choices=['C','E','G'],default=['G'])
    parser.add_argument('--profiles',nargs='+',choices=list(PROFILES),default=list(PROFILES))
    parser.add_argument('--fee',type=float,default=.0002)
    parser.add_argument('--initial',type=float,default=1000.)
    parser.add_argument('--leverage',type=float,default=10.)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.asset=args.asset.upper()
    if not args.asset.isalnum() or not (args.binance_data or args.mexc_data):
        parser.error('Supply an alphanumeric asset and at least one native data directory')
    args.start=int(datetime.fromisoformat(args.start.replace('Z','+00:00')).timestamp())
    args.end=int(datetime.fromisoformat(args.end.replace('Z','+00:00')).timestamp())
    if args.start>=args.end or args.start%900 or args.end%900 or not 0<=args.fee<1 or args.initial<=0 or args.leverage<=0:
        parser.error('Use aligned closed periods and valid costs/capital')
    if len(set(args.models))!=len(args.models) or len(set(args.profiles))!=len(args.profiles):
        parser.error('Models and profiles must be unique')
    run(args)


if __name__=='__main__':
    main()
