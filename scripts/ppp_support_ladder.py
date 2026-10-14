#!/usr/bin/env python3
"""Minute execution of fixed parent-timeframe MA support/rejection hypotheses."""
from __future__ import annotations
import argparse,hashlib,json,math
from collections import Counter
from pathlib import Path
import numpy as np
from ppp_backtest import ROOT,START,END,Bars,load,resample,smooth
from ppp_combo_backtest import build_features,model_signals
from ppp_risk_backtest import risk_features,risk_summary
from ppp_selective_backtest import replay_selective
from ppp_asset_research import kst,write_csv
from ppp_largecap_research import DATA_ROOTS,TARGETS,COMPARISONS,COSTS

LEVELS=(20,50,100,200)
CONFIGS={
 'B0':dict(label='기준형 · 원 신호 진입·SMA50 청산',wait=False,retry=False,risk='baseline'),
 'N0':dict(label='원 신호 진입·최근접 이평선 청산',wait=False,retry=False,risk='nearest'),
 'W0':dict(label='순차 지지 확인·진입 근거 이평선 청산',wait=True,retry=False,risk='anchor'),
 'W1':dict(label='순차 지지 확인·최근접 이평선 청산',wait=True,retry=False,risk='nearest'),
 'R0':dict(label='다음 선·새 신호 재시도·진입 근거선 청산',wait=True,retry=True,risk='anchor'),
 'R1':dict(label='다음 선·새 신호 재시도·최근접선 청산',wait=True,retry=True,risk='nearest'),
}
BAND_ATR=.1
WAIT_BARS=3
VARIANTS=[dict(id='B0',base='B0',stop_clock='signal',label=CONFIGS['B0']['label'])]+[
    dict(id=f'{base}-{clock}',base=base,stop_clock=clock,label=CONFIGS[base]['label']+' · '+('1분' if clock=='minute' else '기준 주기')+' 마감 확인')
    for base in ('N0','W0','W1','R0','R1') for clock in ('minute','signal')]


def prepare(minutes,parent,start,end,features=None):
    """Each minute close can see only parent candles closed by that instant."""
    f=features if features is not None else build_features(parent);g=model_signals('G',f);rf=risk_features(parent)
    take=(minutes.timestamp>=start)&(minutes.timestamp<end);b=minutes.subset(take)
    if len(b.timestamp)==0 or np.any(np.diff(b.timestamp)!=60) or b.timestamp[-1]+60!=end:raise ValueError('Incomplete minute execution coverage')
    close_time=b.timestamp+60;k=np.searchsorted(parent.timestamp+parent.seconds,close_time,side='right')-1
    if (k<200).any():raise ValueError('Unavailable confirmed parent warmup')
    event=(parent.timestamp[k]+parent.seconds==close_time)&(parent.timestamp[k]>=start)
    q=lambda v:np.round(v,9)
    mas=np.column_stack([q(smooth(parent.close,n))[k] for n in LEVELS]);atr=rf['atr'][k]
    d=dict(parent_seconds=parent.seconds,mas=mas,atr=atr,bull=f['bull'][k],bear=f['bear'][k],
           source_long=event&g['long_entry'][k],source_short=event&g['short_entry'][k],
           up=event&g['up'][k],down=event&g['down'][k],parent_event=event,source_time=parent.timestamp[k],
           main=f['main_c'][k],signal=f['signal_c'][k],mfi=f['mfi'][k],rvol=f['rvol'][k],parent_index=k)
    d['base_bits']=(d['up'].astype(np.int32)+2*d['down']+4*d['bull']+8*d['bear']
                    +16*(q(d['mfi'])>50)+32*(q(d['mfi'])<50)+64*(q(d['rvol'])>=1.2)).astype(np.int32)
    if not np.isfinite(mas).all() or not np.isfinite(atr).all():raise ValueError('Unprepared parent indicators')
    return b,d


def simulate_ladder(b,d,variant,*,end,fee=.0002,stop_slippage=0.,trace=False,risk_seconds=60):
    cfg=CONFIGS[variant];n=len(b.timestamp);step=int(d['parent_seconds']);positions=[];counts=Counter()
    p=None;pending=None;exit_order=None;entry_order=None;retry={1:(0,0),-1:(0,0)}
    masks=np.array(d['base_bits'],dtype=np.int32,copy=True) if trace else None
    stages=np.full(n,-1,np.int8) if trace else None;margins=np.zeros(n) if trace else None
    origins=np.zeros(n,np.int64) if trace else None;protect=np.zeros(n) if trace else None
    q=lambda x:round(float(x),9)

    def finalize(pos,index,price,reason,available,timing,trigger=None):
        ratio=price/pos['entry_price'];direction=pos['direction']
        leg=dict(index=index,time=int(b.timestamp[index]),available_time=int(available),timing=timing,price=float(price),fraction=1.,reason=reason,trigger_price=trigger)
        t=dict(pos,legs=[leg],remaining_fraction=0.,exit_time=int(b.timestamp[index]),exit_available_time=int(available),exit_price=float(price),exit_reason=reason,
               gross_return=direction*(ratio-1),net_return=direction*(ratio-1)-fee*(1+ratio),duration_minutes=(available-pos['entry_time'])/60,
               stop_triggered=reason=='S2',original_net_return=None)
        positions.append(t);counts['closed_'+reason]+=1

    def remember_failure(pos,now,index):
        if cfg['retry'] and (d['bull'][j] if pos['direction']==1 else d['bear'][j]):
            retry[pos['direction']]=(index+1,now+WAIT_BARS*step);counts['retry_chain_advanced']+=1

    for j in range(n):
        if (p is None and pending is None and exit_order is None and entry_order is None
            and not d['source_long'][j] and not d['source_short'][j] and not retry[1][1] and not retry[-1][1]):
            if trace:masks[j]|=128
            continue
        time=int(b.timestamp[j]);now=time+60;close=q(b.close[j]);ma=d['mas'][j]
        if exit_order:
            reason,failed_index=exit_order
            finalize(p,j,float(b.open[j]),reason,time,'open')
            if failed_index is not None:remember_failure(p,time,failed_index)
            p=None;exit_order=None
        if entry_order:
            order=entry_order;entry_order=None;direction=order['direction'];ep=float(b.open[j]);idx=order['support_index']
            p=dict(side='long' if direction==1 else 'short',direction=direction,entry_time=time,entry_signal_time=time-60,
                   entry_price=ep,entry_atr=order['atr'],entry_support_index=idx,protected_index=idx,
                   parent_signal_time=order['source_time'],setup_available_time=order['source_available'],tolerance=order['margin'],
                   protected_stop=order['level']-direction*order['margin'],guard_end=(time//step+1)*step,
                   break_even_armed=False,original_net_return=None,stop_triggered=False,legs=[],remaining_fraction=1.)
            pending=None;counts['entry_ma'+str(LEVELS[idx])]+=1
        stopped=False;stop_context=None
        if p is not None and time<p['guard_end']:
            direction=p['direction'];level=p['entry_price']*(1-direction*.01)
            if b.low[j]<=level if direction==1 else b.high[j]>=level:
                gap=direction*(float(b.open[j])-level)<=0;base=float(b.open[j]) if gap else level
                xp=base*(1-direction*stop_slippage);available=time if gap else now
                finalize(p,j,xp,'S2',available,'open_gap' if gap else 'intrabar',level)
                stop_context=p;p=None;stopped=True;counts['gap_price_stops']+=int(gap)
        if not d['bull'][j]:retry[1]=(0,0)
        if not d['bear'][j]:retry[-1]=(0,0)
        for direction in (1,-1):
            if retry[direction][1] and now>=retry[direction][1]:retry[direction]=(0,0)
        if stop_context:
            remember_failure(stop_context,now,stop_context['protected_index'])
        if pending is not None:
            direction=pending['direction'];cancel=None
            if now>=pending['expires']:cancel='expired'
            elif not(d['bull'][j] if direction==1 else d['bear'][j]):cancel='array_broken'
            elif d['down'][j] if direction==1 else d['up'][j]:cancel='opposite_cross'
            if cancel:counts['wait_cancel_'+cancel]+=1;pending=None
        can_fill=j+1<n and int(b.timestamp[j+1])==now and now<end
        failed_index=None
        if p is not None and can_fill:
            direction=p['direction'];opposite=bool(d['down'][j] if direction==1 else d['up'][j]);reason=None
            if cfg['risk']=='baseline':
                if d['parent_event'][j] and direction*(close-q(ma[1]))<0:reason='sma50'
            elif now%risk_seconds==0:
                idx=p['protected_index'];candidate=q(ma[idx]-direction*p['tolerance'])
                p['protected_stop']=max(p['protected_stop'],candidate) if direction==1 else min(p['protected_stop'],candidate)
                if direction*(close-q(p['protected_stop']))<0:
                    reason=('nearest_' if cfg['risk']=='nearest' else 'support_')+'ma'+str(LEVELS[idx]);failed_index=idx
                elif cfg['risk']=='nearest':
                    eligible=np.flatnonzero(direction*(close-ma)>=p['tolerance'])
                    if len(eligible):
                        idx=int(eligible[np.argmin(np.abs(close-ma[eligible]))]);candidate=q(ma[idx]-direction*p['tolerance'])
                        if direction*(candidate-p['protected_stop'])>0:p['protected_index']=idx;p['protected_stop']=candidate;counts['protect_upgrades']+=1
            if opposite:reason='opposite_cross'
            if reason:exit_order=(reason,failed_index)
        source=1 if d['source_long'][j] else -1 if d['source_short'][j] else 0
        # A fresh source arms a wait. It can never reuse this same minute's
        # already-observed wick as post-signal support.
        if source and can_fill:
            counts['qualified_source_signals']+=1
            if not cfg['wait']:
                if p is None or(exit_order and exit_order[0]=='opposite_cross'):
                    margin=BAND_ATR*float(d['atr'][j]);eligible=np.flatnonzero(source*(close-ma)>=margin)
                    idx=int(eligible[np.argmin(np.abs(close-ma[eligible]))]) if len(eligible) else 3
                    counts['no_initial_support']+=int(len(eligible)==0)
                    entry_order=dict(direction=source,support_index=idx,atr=float(d['atr'][j]),margin=margin,level=float(ma[idx]),
                                     source_time=int(d['source_time'][j]),source_available=now)
            elif p is None or exit_order:
                idx=retry[source][0] if cfg['retry'] else 0
                if exit_order and cfg['retry'] and failed_index is not None and source==p['direction']:idx=failed_index+1
                margin=BAND_ATR*float(d['atr'][j])
                while idx<4 and source*(close-q(ma[idx]-source*margin))<0:idx+=1
                if idx<4:
                    pending=dict(direction=source,index=idx,armed=now,ready_after=now,expires=now+WAIT_BARS*step,
                                 source_time=int(d['source_time'][j]),source_available=now,atr=float(d['atr'][j]),margin=margin)
                    counts['wait_armed']+=1
                else:counts['wait_cancel_no_support']+=1
        touched=False;reclaimed=False
        if pending is not None and can_fill and time>=pending['ready_after'] and p is None:
            direction=pending['direction'];idx=pending['index'];margin=pending['margin'];level=float(ma[idx])
            if direction*(close-q(level-direction*margin))<0:
                counts['failed_ma'+str(LEVELS[idx])]+=1;idx+=1
                while idx<4 and direction*(close-q(ma[idx]-direction*margin))<0:counts['failed_ma'+str(LEVELS[idx])]+=1;idx+=1
                if idx>=4:counts['wait_cancel_200_failed']+=1;pending=None
                else:pending['index']=idx;pending['ready_after']=now
            else:
                touched=q(b.low[j])<=q(level+margin) and q(b.high[j])>=q(level-margin)
                reclaimed=direction*(close-q(level+direction*margin))>=0 and direction*(close-q(b.open[j]))>0
                if touched and reclaimed:
                    entry_order=dict(direction=direction,support_index=idx,atr=pending['atr'],margin=margin,level=level,
                                     source_time=pending['source_time'],source_available=pending['source_available'])
        if trace:
            allowed=p is None or bool(exit_order and exit_order[0]=='opposite_cross');state=int(masks[j])
            state|=128*allowed+256*(p is not None and p['direction']==1)+512*(p is not None and p['direction']==-1)
            if entry_order:state|=1024 if entry_order['direction']==1 else 2048
            if exit_order:state|=4096 if exit_order[0]=='opposite_cross' else 8192
            if stopped:state|=65536
            if pending:
                direction=pending['direction'];state|=131072 if direction==1 else 262144
                state|=4194304;stages[j]=pending['index'];margins[j]=pending['margin'];origins[j]=pending['source_time']
            elif p:stages[j]=p['protected_index'];margins[j]=p['tolerance'];origins[j]=p['parent_signal_time'];protect[j]=p['protected_stop']
            if touched:state|=524288
            if reclaimed:state|=1048576 if pending['direction']==1 else 2097152
            masks[j]=state
    if p is not None:positions.append(dict(p,remaining_fraction=1.,legs=[]))
    return dict(positions=positions,diagnostics=dict(counts),states=masks,support_index=stages,margin=margins,source_time=origins,protected_stop=protect)


def market_cases(assets):
    for asset in assets:
        binance,mexc=DATA_ROOTS[asset];minutes=load(binance/f'{asset}USDT-1m.csv',60)
        for tf in (1,3,5,15):
            parent=resample(minutes,tf*60);yield asset,'binance_um',tf,minutes,parent,START,binance/f'{asset}USDT-1m.csv',None
        mp=mexc/f'{asset}_USDT-Min1.csv'
        if not mp.exists():continue
        minutes=load(mp,60)
        for tf in (5,15):
            path=mexc/f'{asset}_USDT-Min{tf}.csv';parent=load(path,tf*60)
            start=max(START,int(math.ceil(minutes.timestamp[0]/parent.seconds)*parent.seconds))
            yield asset,'mexc',tf,minutes,parent,start,mp,path


def run(output):
    output.mkdir(parents=True,exist_ok=True);rows=[];sources=[];journals=[];diagnostics=[]
    protocol=dict(configs=CONFIGS,variants=VARIANTS,band_atr=BAND_ATR,wait_bars=WAIT_BARS,fee=.0002,costs=COSTS,start=START,end=END,
                  targets=TARGETS,comparisons=COMPARISONS,reentry='Fresh qualified G source required; never reuse old source after fill.',
                  protection='Check previous selected MA before choosing another. Ratchet, never loosen.',
                  source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output/'fixed-protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    for asset,venue,tf,minutes,parent,start,mp,pp in market_cases(TARGETS+COMPARISONS):
        b,d=prepare(minutes,parent,start,END)
        sources.append(dict(asset=asset,venue=venue,timeframe_minutes=tf,execution_timeframe_minutes=1,start_kst=kst(start),end_kst=kst(END),full_period=start==START,
                            minute_path=str(mp),minute_sha256=hashlib.sha256(mp.read_bytes()).hexdigest(),parent_path=str(pp) if pp else None,
                            parent_sha256=hashlib.sha256(pp.read_bytes()).hexdigest() if pp else None,candles=len(b.timestamp)))
        for spec in VARIANTS:
            variant=spec['id'];cfg=CONFIGS[spec['base']];risk_seconds=60 if spec['stop_clock']=='minute' else parent.seconds if parent is not None else d['parent_seconds']
            for cost,assumed in COSTS.items():
                sim=simulate_ladder(b,d,spec['base'],end=END,fee=assumed['fee'],stop_slippage=assumed['stop_slippage'],risk_seconds=risk_seconds)
                stats,points=replay_selective(b,sim['positions'],fee=assumed['fee'],initial=1000.,leverage=10.)
                # Strategy statistics also retain theoretical signals after
                # capital depletion; the capital series records actual execution.
                strategy=risk_summary([p for p in sim['positions'] if p['remaining_fraction']==0])
                rows.append(dict(asset=asset,role='target' if asset in TARGETS else 'comparison',venue=venue,timeframe_minutes=tf,
                                 execution_timeframe_minutes=1,variant=variant,label=spec['label'],stop_clock=spec['stop_clock'],cost=cost,full_period=start==START,
                                 start_kst=kst(start),end_kst=kst(END),**stats,strategy_trades=strategy['trades'],diagnostics=sim['diagnostics']))
                if cost=='nominal':
                    for t in sim['positions']:
                        record=dict(asset=asset,venue=venue,timeframe_minutes=tf,variant=variant,
                                    **{k:v for k,v in t.items() if k not in ('legs','remaining_fraction')},open_position=bool(t['remaining_fraction']))
                        journals.append(record)
                    diagnostics.append(dict(asset=asset,venue=venue,timeframe_minutes=tf,variant=variant,full_period=start==START,**sim['diagnostics']))
        print('Support comparison complete:',asset,venue,tf,'minute executions',len(b.timestamp),flush=True)
    result=dict(protocol=protocol,rows=rows,sources=sources,capital='$1000 separate fullmargin10x accounts; entry fee reserve; net compounding; no funding/fairprice liquidation/lot constraints.',
                baseline_note='Baseline uses the same G/R2+S2 rules but minute stop timing/gap prices and minute OHLC drawdown bounds. Original coarser results remain preserved.',
                limitations='Retrospective observed markets, fixed rule hypotheses, no universal/live trading claim. MEXC minute history is short and never merged with Binance prices.')
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    keys=sorted({k for r in diagnostics for k in r})
    write_csv(output/'summary.csv',[{k:v for k,v in r.items() if k!='diagnostics'} for r in rows]);write_csv(output/'trades.csv',journals)
    write_csv(output/'diagnostics.csv',[{k:r.get(k,0) for k in keys} for r in diagnostics])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-support-2026-10-14');a=p.parse_args();run(a.output)


if __name__=='__main__':main()
