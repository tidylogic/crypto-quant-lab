#!/usr/bin/env python3
"""Fixed D-H indicator combinations; compare against C on the same data/costs."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ppp_backtest import (ROOT, START, END, MINUTE_START, Bars, crosses, indicator,
                         iso, load, resample, simulate, sma_alignment, smooth, summarize)

MODELS = ('C', 'D', 'E', 'F', 'G', 'H')
PINE_FILES = {
    'D':'ppp-d-adx-dmi-v6.pine', 'E':'ppp-e-macd-momentum-v6.pine',
    'F':'ppp-f-mfi-v6.pine', 'G':'ppp-g-mfi-rvol-v6.pine', 'H':'ppp-h-macd-rsi-v6.pine',
}
MODEL_RULES = {
    'C': 'Unfiltered nested Stochastic baseline',
    'D': 'C + ADX(14,14)>=20; +DI>-DI long, -DI>+DI short',
    'E': 'C + MACD(12,26,9) histogram positive and rising long, negative and falling short',
    'F': 'C + MFI(hlc3,14)>50 long, <50 short',
    'G': 'F + current volume / mean(previous 20 volumes)>=1.2',
    'H': 'MACD(12,26,9) cross + RSI(close,14)>=55 long, <=45 short; no Stochastic',
}


def rsi(close, length=14):
    delta=np.r_[np.nan,np.diff(close)]
    up=smooth(np.maximum(delta,0),length,'RMA')
    down=smooth(np.maximum(-delta,0),length,'RMA')
    result=np.full(len(close),np.nan)
    valid=np.isfinite(up)&np.isfinite(down)
    positive_down=valid&(np.round(down,9)>0)
    result[positive_down]=100-100/(1+up[positive_down]/down[positive_down])
    result[valid&(np.round(down,9)==0)&(np.round(up,9)>0)]=100
    # ta.rsi's flat zero/zero window is left unavailable; H rejects it.
    return result


def macd(close, fast=12, slow=26, signal_length=9):
    main=smooth(close,fast,'EMA')-smooth(close,slow,'EMA')
    signal=smooth(main,signal_length,'EMA')
    return main,signal,main-signal


def dmi(bars, length=14, adx_length=14):
    up=np.r_[np.nan,np.diff(bars.high)]
    down=np.r_[np.nan,-np.diff(bars.low)]
    plus=np.where((np.round(up,9)>np.round(down,9))&(np.round(up,9)>0),up,0.)
    minus=np.where((np.round(down,9)>np.round(up,9))&(np.round(down,9)>0),down,0.)
    plus[0]=minus[0]=np.nan
    prev_close=np.r_[np.nan,bars.close[:-1]]
    tr=np.maximum(bars.high-bars.low,np.maximum(np.abs(bars.high-prev_close),np.abs(bars.low-prev_close)))
    avg_tr=smooth(tr,length,'RMA')
    plus_avg=smooth(plus,length,'RMA')
    minus_avg=smooth(minus,length,'RMA')
    plus_di=np.full(len(tr),np.nan)
    minus_di=plus_di.copy()
    valid=np.isfinite(avg_tr)&(np.round(avg_tr,9)>0)
    plus_di[valid]=100*plus_avg[valid]/avg_tr[valid]
    minus_di[valid]=100*minus_avg[valid]/avg_tr[valid]
    total=plus_di+minus_di
    dx=np.full(len(tr),np.nan)
    valid=np.isfinite(total)
    zero=valid&(np.round(total,9)==0)
    dx[zero]=0
    nonzero=valid&~zero
    dx[nonzero]=100*np.abs(plus_di[nonzero]-minus_di[nonzero])/total[nonzero]
    return plus_di,minus_di,smooth(dx,adx_length,'RMA')


def money_flow(bars,length=14):
    typical=(bars.high+bars.low+bars.close)/3
    change=np.r_[np.nan,np.diff(typical)]
    amount=typical*bars.volume
    up=np.where(np.round(change,9)>0,amount,0.)
    down=np.where(np.round(change,9)<0,amount,0.)
    up[0]=down[0]=np.nan
    positive=smooth(up,length,'SMA')*length
    negative=smooth(down,length,'SMA')*length
    total=positive+negative
    result=np.full(len(total),np.nan)
    valid=np.isfinite(total)&(np.round(total,9)>0)
    result[valid]=100*positive[valid]/total[valid]
    return result


def relative_volume(volume,length=20):
    baseline=smooth(np.r_[np.nan,np.asarray(volume,dtype=float)[:-1]],length,'SMA')
    result=np.full(len(volume),np.nan)
    valid=np.isfinite(baseline)&(np.round(baseline,9)>0)
    result[valid]=np.asarray(volume)[valid]/baseline[valid]
    return result


def build_features(bars):
    main_c,signal_c=indicator(bars,'C')
    main_macd,signal_macd,hist=macd(bars.close)
    plus,minus,adx=dmi(bars)
    bull,bear=sma_alignment(bars.close)
    return dict(main_c=main_c,signal_c=signal_c,main_macd=main_macd,signal_macd=signal_macd,
                hist=hist,plus_di=plus,minus_di=minus,adx=adx,rsi=rsi(bars.close),
                mfi=money_flow(bars),rvol=relative_volume(bars.volume),bull=bull,bear=bear)


def direction_filters(model,f):
    q=lambda name:np.round(np.asarray(f[name],dtype=float),9)
    if model=='C':
        return np.ones(len(f['bull']),dtype=bool),np.ones(len(f['bear']),dtype=bool)
    if model=='D':
        strong=q('adx')>=20
        return strong&(q('plus_di')>q('minus_di')),strong&(q('minus_di')>q('plus_di'))
    if model=='E':
        h=q('hist');previous=np.r_[np.nan,h[:-1]]
        return (h>0)&(h>previous),(h<0)&(h<previous)
    if model in ('F','G'):
        flow=q('mfi');long=flow>50;short=flow<50
        if model=='G':
            liquid=q('rvol')>=1.2
            long &= liquid;short &= liquid
        return long,short
    if model=='H':
        return q('rsi')>=55,q('rsi')<=45
    raise ValueError(f'Unknown combination: {model}')


def model_signals(model,f):
    main=f['main_macd'] if model=='H' else f['main_c']
    signal=f['signal_macd'] if model=='H' else f['signal_c']
    up,down=crosses(main,signal)
    long,short=direction_filters(model,f)
    return dict(main=main,signal=signal,up=up,down=down,
                long_gate=f['bull']&long,short_gate=f['bear']&short,
                long_entry=up&f['bull']&long,short_entry=down&f['bear']&short)


def breakdown(trades):
    groups={}
    for trade in trades:
        key=datetime.fromtimestamp(trade['exit_time'],timezone.utc).strftime('%Y-%m')
        groups.setdefault(key,[]).append(trade)
    return {key:summarize(group) for key,group in groups.items()}


def dataset_cases(assets=('BTC','ZEC'), *, data_roots=None, start=START, end=END, minute_start=MINUTE_START):
    assets=tuple(assets)
    if not assets or len(set(assets))!=len(assets) or any(a not in ('BTC','ETH','ZEC') for a in assets):
        raise ValueError('Choose unique BTC, ETH or ZEC assets')
    if start>=end or start%900 or end%900 or minute_start%900:
        raise ValueError('Evaluation boundaries must be aligned UTC quarter-hours')
    for venue in ('binance_um','mexc'):
        for asset in assets:
            symbol=asset+('USDT' if venue=='binance_um' else '_USDT')
            default_root=ROOT/'user_data/data'/(('ppp-binance' if venue=='binance_um' else 'ppp-mexc')+('-eth' if asset=='ETH' else ''))
            data_root=Path(data_roots[venue]) if data_roots and venue in data_roots else default_root
            path=data_root/f'{symbol}-1m.csv' if venue=='binance_um' else data_root/f'{symbol}-Min1.csv'
            minutes=load(path,60)
            for tf in (1,3,5,15):
                data_path=data_root/f'{symbol}-Min{tf}.csv' if venue=='mexc' and tf in(5,15) else path
                bars=load(data_path,tf*60) if venue=='mexc' and tf in(5,15) else resample(minutes,tf*60)
                case_start=start
                if venue=='mexc' and tf in(1,3):
                    # New market requests may have a later native history boundary.
                    warm_start=(int(minutes.timestamp[0])+600*60+899)//900*900
                    case_start=max(minute_start,warm_start,start)
                mask=(bars.timestamp>=case_start)&(bars.timestamp<end)
                if case_start>=end or int(mask.sum())!=(end-case_start)//bars.seconds or bars.timestamp[-1]+bars.seconds!=end:
                    raise ValueError('Incomplete data coverage')
                yield venue,symbol,tf,bars,case_start,data_path


def run(output,fee=.0002):
    output.mkdir(parents=True,exist_ok=True)
    summaries=[];trade_rows=[];provenance=[]
    split=int(datetime(2026,8,13,15,tzinfo=timezone.utc).timestamp())
    original=json.loads((ROOT/'user_data/backtest_results/ppp-2026-10-14/results.json').read_text())
    old={(r['venue'],r['symbol'],r['timeframe_minutes']):r for r in original['summaries'] if r['model']=='C'}
    for venue,symbol,tf,bars,start,data_path in dataset_cases():
        f=build_features(bars)
        case_baseline=None
        for model in MODELS:
            signals=model_signals(model,f)
            # Entry gates change; raw opposite crosses remain untouched for exits.
            result=simulate(bars,signals['up'],signals['down'],signals['long_gate'],signals['short_gate'],start=start,end=END,fee=fee)
            trades=result['trades'];stats=summarize(trades)
            if model=='C':
                prior=old[(venue,symbol,tf)]
                if stats['trades']!=prior['trades'] or (fee==.0002 and stats['wins']!=prior['wins']):
                    raise ValueError('Original C baseline changed')
                case_baseline=stats
            # Both segments simulate independently; neither carries an old position.
            segments={}
            if start==START:
                for label,left,right in [('first_four_months',start,split),('last_two_months',split,END)]:
                    part=simulate(bars,signals['up'],signals['down'],signals['long_gate'],signals['short_gate'],start=left,end=right,fee=fee)
                    segments[label]=dict(start_utc=iso(left),end_utc_exclusive=iso(right),**summarize(part['trades']))
            record=dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,description=MODEL_RULES[model],
                        start_utc=iso(start),end_utc_exclusive=iso(END),six_months=start==START,**stats,
                        open_position=result['open_position'],temporal_segments=segments,monthly=breakdown(trades))
            record['delta_vs_C_win_rate_pp']=stats['win_rate_pct']-case_baseline['win_rate_pct'] if stats['trades'] else None
            # Relative count, not a claim that these are a subset of C trades.
            record['trade_count_vs_C_pct']=100*stats['trades']/case_baseline['trades'] if case_baseline['trades'] else None
            summaries.append(record)
            trade_rows.extend(dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,**trade) for trade in trades)
            wr='none' if stats['win_rate_pct'] is None else f'{stats["win_rate_pct"]:.2f}'
            pf='none' if stats['profit_factor'] is None else f'{stats["profit_factor"]:.3f}'
            print(f'{venue} {symbol} {tf}m {model}: n={stats["trades"]} win={wr}% PF={pf}',flush=True)
        provenance.append(dict(venue=venue,symbol=symbol,timeframe_minutes=tf,path=str(data_path),sha256=hashlib.sha256(data_path.read_bytes()).hexdigest()))
    hashes={model:hashlib.sha256((ROOT/'docs/tradingview/ppp-combinations'/name).read_bytes()).hexdigest() for model,name in PINE_FILES.items()}
    payload=dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),period_utc=[iso(START),iso(END)],
                 fee_each_side=fee,slippage=0,funding_included=False,model_rules=MODEL_RULES,parameters_fixed_before_run=True,
                 baseline='C recomputed at the requested fee; previous trade counts match, wins also match at fee=.0002',
                 fill='next open after confirmed signal',exit='unfiltered opposite cross; C for D-G and MACD for H',
                 position='one per model/asset/timeframe, qualified same-open reversal, no forced end exit',
                 split='first4months / last2months separately simulated; time comparison, not unseen holdout',
                 provenance=provenance,pine_sha256=hashes,
                 engine_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'scripts/ppp_backtest.py']},
                 summaries=summaries)
    (output/'results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    rows=[{k:v for k,v in r.items() if k not in('open_position','temporal_segments','monthly','win_rate_wilson95_pct')} for r in summaries]
    for name,items in [('summary.csv',rows),('trades.csv',trade_rows)]:
        with (output/name).open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(items[0]));writer.writeheader();writer.writerows(items)
    print(f'Saved {len(summaries)} combinations; {len(trade_rows)} closed trades: {output}',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-combinations-2026-10-14')
    parser.add_argument('--fee',type=float,default=.0002)
    args=parser.parse_args();run(args.output,args.fee)


if __name__=='__main__':main()
