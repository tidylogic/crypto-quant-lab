#!/usr/bin/env python3
"""Transfer a fixed entry-candle stop to an audited arbitrary-asset journal."""
from __future__ import annotations
import argparse
import base64
import gzip
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from ppp_backtest import ROOT
from ppp_combo_backtest import build_features, model_signals
from ppp_drawdown_backtest import validate_alternating_crosses
from ppp_selective_backtest import apply_policy, replay_selective
from ppp_asset_research import (KST, market_cases, encode, write_csv, export_reports, PROFILE_KO)
from datetime import datetime

COST_NOTE='일반 진입·청산 슬리피지는 제외합니다. 손절 비용 시나리오에서는 표시한 추가 비용을 S2 손절 체결에만 반영합니다(기본 0% 및 0.05%). 펀딩·공정가격 강제청산·계약 및 주문 수량 제한은 제외합니다.'


def selective_states(bars, signals, trades, opened, *, start, end, initial):
    """Close-known stop flags; cash is booked only at its availability time."""
    n=len(bars.timestamp)
    pos=np.zeros(n,dtype=np.int8);entered=pos.copy();queued=pos.copy();stops=np.zeros(n,bool)
    events=np.full(n,np.nan);terminal=None
    for t in trades:
        a=int(np.searchsorted(bars.timestamp,t['entry']));z=int(np.searchsorted(bars.timestamp,t['exit']))
        d=1 if t['side']=='long' else -1
        pos[a:z]=d;entered[a-1]=d
        if t['reason']=='S2':
            # The entry-candle stop has completed before this close's next
            # fresh signal. It is not a risk order queued for the next open.
            stops[z]=True
        else:
            queued[z-1]=1 if t['reason']=='opposite_cross' else 2
        available=t.get('exit_available_time',t['exit'])
        if t['cash'] is not None:
            if available==end:terminal=dict(time=end,cash=t['cash'])
            else:
                k=int(np.searchsorted(bars.timestamp,available))
                if k>=n or int(bars.timestamp[k])!=available:raise ValueError('Exit availability outside native candles')
                events[k]=t['cash']
    if opened:
        a=int(np.searchsorted(bars.timestamp,opened['entry_time']));d=1 if opened['side']=='long' else -1
        pos[a:]=d;entered[a-1]=d
    allowed=(pos==0)|(queued==1)
    expected=np.where(signals['long_entry'],1,np.where(signals['short_entry'],-1,0))*allowed
    eligible=(bars.timestamp>=start)&(bars.timestamp+bars.seconds<end)
    if not np.array_equal(expected[eligible],entered[eligible]):raise ValueError('Selective entry opportunities differ from confirmed native signals')
    masks=(128*allowed+256*(pos==1)+512*(pos==-1)+1024*(entered==1)+2048*(entered==-1)
           +4096*(queued==1)+8192*(queued==2)+65536*stops)
    last=np.maximum.accumulate(np.where(np.isfinite(events),np.arange(n),-1));cash=np.full(n,float(initial));known=last>=0;cash[known]=events[last[known]]
    return masks,cash,terminal


def run(input_dir, output, *, model='G', base_profile='R2', slippages=(0.,.0005)):
    source=json.loads((input_dir/'results.json').read_text())
    asset=source['asset'];fee=source['fee_each_side'];initial=source['initial_cash'];leverage=source['leverage']
    stamp=lambda s:int(datetime.strptime(s,'%Y-%m-%d %H:%M').replace(tzinfo=KST).timestamp())
    start,end=stamp(source['start_kst']),stamp(source['end_exclusive_kst'])
    directories={p['venue']:Path(p['source']).parent for p in source['provenance']}
    output.mkdir(parents=True,exist_ok=True)
    labels={base_profile:PROFILE_KO[base_profile]+' · 원래 청산(S0)'}
    ids={rate:base_profile+'-S2'+('' if rate==0 else '-slip'+format(rate*10000,'g')) for rate in slippages}
    labels.update({ids[rate]:PROFILE_KO[base_profile]+' + 진입 봉 1% 손절'+('' if rate==0 else f' · 손절 비용 +{rate*100:g}%') for rate in slippages})
    summaries=[];journal=[];packs={model:{}};exports={model:[]};provenance=[]
    for venue,symbol,tf,bars,case_start,path in market_cases(asset,directories.get('binance_um'),directories.get('mexc'),start,end):
        key=f'{venue}-{tf}';packed=json.loads(gzip.decompress((input_dir/f'{model}-{key}.json.gz').read_bytes()))
        baseline=next(p for p in packed['profiles'] if p['profile']==base_profile)
        old=next(p for p in source['provenance'] if p['venue']==venue and p['timeframe_minutes']==tf)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=old['sha256']:raise ValueError('Baseline source candles changed')
        if packed['start']!=case_start or packed['end']!=end:raise ValueError('Baseline period changed')
        f=build_features(bars);signals=model_signals(model,f)
        raw_events=validate_alternating_crosses(signals['up'],signals['down'])
        original=[]
        for t in baseline['trades']:
            original.append(dict(side=t['side'],entry_time=t['entry'],entry_signal_time=t['signal_time'],entry_price=t['ep'],
                                 exit_time=t['exit'],exit_signal_time=t['exit_signal_time'],exit_price=t['xp'],exit_reason=t['reason'],
                                 entry_atr=t['entry_atr'],break_even_armed=t['break_even_armed']))
        if baseline['open_position']:original.append(baseline['open_position'])
        take=np.flatnonzero((bars.timestamp>=case_start)&(bars.timestamp<end))
        configurations=[(base_profile,'S0',0.)]+[(ids[s],'S2',s) for s in slippages]
        profiles=[]
        for profile_id,policy,slip in configurations:
            positions=[apply_policy(bars,t,policy,fee=fee,stop_slippage=slip) for t in original]
            stats,points=replay_selective(bars,positions,fee=fee,initial=initial,leverage=leverage)
            if policy=='S0':
                for name in ['closed_cash_usdt','end_marked_equity_usdt','closed_drawdown_pct','ohlc_drawdown_upper_bound_pct']:
                    if not math.isclose(stats[name],baseline['summary'][name],rel_tol=1e-11,abs_tol=1e-24):raise ValueError(f'S0 baseline differs: {key} {name}')
                if stats['trades']!=baseline['summary']['trades']:raise ValueError('Baseline trade count differs')
            point_map={t['entry_time']:t for t in points};records=[];opened=None
            for n,t in enumerate(positions,1):
                if t['remaining_fraction']:
                    opened=baseline['open_position'];continue
                point=point_map.get(t['entry_time']);leg=t['legs'][-1]
                record=dict(n=n,side=t['side'],entry=t['entry_time'],exit=t['exit_time'],signal_time=t['entry_signal_time'],
                            exit_signal_time=None if leg['timing']=='intrabar' else t.get('exit_signal_time'),
                            exit_available_time=t['exit_available_time'],exit_timing=leg['timing'],ep=t['entry_price'],xp=t['exit_price'],
                            net_pct=t['net_return']*100,account_pct=point['account_return']*100 if point else None,
                            cash=point['closed_cash_usdt'] if point else None,capital_executed=point is not None,reason=t['exit_reason'],
                            entry_atr=t['entry_atr'],break_even_armed=t.get('break_even_armed',False),stop_triggered=t['stop_triggered'],
                            stop_price=leg['trigger_price'],original_exit=t['original_exit_time'],original_xp=t['original_exit_price'])
                records.append(record);journal.append(dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,profile=profile_id,policy=policy,stop_slippage=slip,**record))
            states,cash,terminal=selective_states(bars,signals,records,opened,start=case_start,end=end,initial=initial)
            summary=dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,profile=profile_id,base_profile=base_profile,
                         policy=policy,stop_slippage=slip,six_months=packed['six_months'],full_period=packed['full_period'],
                         start_kst=packed['start_kst'],end_exclusive_kst=packed['end_kst'],**stats)
            summaries.append(summary)
            from ppp_asset_research import loss_streaks
            profiles.append(dict(profile=profile_id,risk_profile=base_profile,policy=policy,label=labels[profile_id],summary=summary,
                                 trades=records,open_position=opened,streaks=loss_streaks(records),
                                 decision_states=states[take].tolist(),cash_at_bar_open=cash[take].tolist(),terminal_cash=terminal,
                                 audit=dict(entries=len(positions),entry_opportunities_preserved=True,raw_crosses_alternating=True,
                                            state_sha256=hashlib.sha256(states[take].astype('<i4').tobytes()).hexdigest(),last_cash=float(cash[take[-1]]),
                                            terminal_cash=terminal,final_closed_cash=stats['closed_cash_usdt'])))
            print(f'{key} {profile_id}: trades={stats["trades"]} stops={stats["stopped_trades"]} win={stats["win_rate_pct"]} payoff={stats["payoff_ratio"]} cash={stats["end_marked_equity_usdt"]:.8g}',flush=True)
        meta={k:v for k,v in packed.items() if k not in ('rows','profiles')}
        result_pack=dict(**meta,rows=packed['rows'],profiles=profiles)
        encoded=encode(result_pack);packs[model][key]=encoded;exports[model].append(meta)
        (output/f'{model}-{key}.json.gz').write_bytes(base64.b64decode(encoded))
        provenance.append(dict(old,raw_cross_events_verified=raw_events))
    all_profiles=[base_profile]+[ids[s] for s in slippages]
    result=dict(asset=asset,start_kst=source['start_kst'],end_exclusive_kst=source['end_exclusive_kst'],fee_each_side=fee,initial_cash=initial,leverage=leverage,
                models=[model],profiles=all_profiles,strategy_rules={model:source['strategy_rules'][model]},risk_rules=labels,
                reference='Fixed ZEC winner G/R2+S2 transferred without WLD parameter tuning',
                stop_rule='Only actual entry candle: long entry*0.99 / short entry*1.01. Cancel before next candle.',
                fill='Original confirmed-close next-open exits retained. S2 price stop executes intrabar; precise tick unknown. Cash availability is recorded at bar close.',
                position='Original audited entry opportunities retained; only subsequent fresh crosses can enter after stop.',
                excluded=[x if x!='slippage' else 'ordinary-fill slippage' for x in source['excluded']],
                stop_stress_included=list(slippages),cost_note=COST_NOTE,capital=source['capital'],provenance=provenance,summaries=summaries,
                source_results_sha256=hashlib.sha256((input_dir/'results.json').read_bytes()).hexdigest(),
                selective_engine_sha256={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in ['ppp_asset_selective.py','ppp_selective_backtest.py']})
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    write_csv(output/'summary.csv',[{k:v for k,v in r.items() if not isinstance(v,(list,dict,tuple))} for r in summaries]);write_csv(output/'trades.csv',journal)
    args=SimpleNamespace(asset=asset,models=[model],profiles=all_profiles,fee=fee,initial=initial,leverage=leverage,output=output,
                         profile_labels=labels,default_profile=ids[0.] if 0. in ids else ids[slippages[0]],slippage_note=COST_NOTE)
    export_reports(args,result,exports,packs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--model',choices=['C','E','G'],default='G');p.add_argument('--base-profile',choices=list(PROFILE_KO),default='R2')
    p.add_argument('--stop-slippage',type=float,nargs='+',default=[0.,.0005])
    a=p.parse_args()
    if len(set(a.stop_slippage))!=len(a.stop_slippage) or any(not 0<=s<1 for s in a.stop_slippage):p.error('Use unique valid stop slippage rates')
    if a.input.resolve()==a.output.resolve():p.error('Use a separate output directory to preserve the original research')
    run(a.input,a.output,model=a.model,base_profile=a.base_profile,slippages=tuple(a.stop_slippage))


if __name__=='__main__':main()
