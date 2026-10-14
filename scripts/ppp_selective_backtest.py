#!/usr/bin/env python3
"""Five fixed loss exits on audited entry opportunities, full-account 10x."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from ppp_backtest import ROOT, START, END, iso, indicator, crosses
from ppp_combo_backtest import dataset_cases
from ppp_risk_backtest import risk_summary
from ppp_capital_replay import replay
from ppp_drawdown_backtest import EXITS, SOURCE, validate_alternating_crosses, window_trades

POLICIES={
    'S0':'Original exit, full-account 10x',
    'S1':'1.5% price stop throughout holding; full exit',
    'S2':'1.0% price stop on actual entry candle only; full exit',
    'S3':'1.5% price stop on actual entry candle only; full exit',
    'S4':'1.0% price stop on actual entry candle only; exit half, original exit for remainder',
    'S5':'First two holding closes beyond pre-entry signal low/high; full exit next open',
}


def apply_policy(bars,t,policy,*,fee=.0002,stop_slippage=0.):
    if policy not in POLICIES or not 0<=fee<1 or not 0<=stop_slippage<1:
        raise ValueError('Invalid selective policy or costs')
    a=int(np.searchsorted(bars.timestamp,t['entry_time']))
    z=int(np.searchsorted(bars.timestamp,t.get('exit_time',int(bars.timestamp[-1])+bars.seconds)))
    if a>=len(bars.timestamp) or int(bars.timestamp[a])!=t['entry_time'] or z<a:
        raise ValueError('Invalid entry path')
    d=1 if t['side']=='long' else -1;p=t['entry_price']
    result=dict(t,policy=policy,legs=[],remaining_fraction=1.,stop_triggered=False,
                original_exit_time=t.get('exit_time'),original_exit_price=t.get('exit_price'),
                original_net_return=(d*(t['exit_price']/p-1)-fee*(1+t['exit_price']/p)) if 'exit_price' in t else None)
    if policy in ('S1','S2','S3','S4'):
        distance=.015 if policy in ('S1','S3') else .01
        level=p*(1-d*distance)
        stop_end=z if policy=='S1' else min(z,a+1)
        adverse=bars.low[a:stop_end] if d==1 else bars.high[a:stop_end]
        hits=np.flatnonzero(adverse<=level if d==1 else adverse>=level)
        if len(hits):
            k=a+int(hits[0]);o=float(bars.open[k])
            gap=d*(o-level)<=0
            base=o if gap else level
            price=base*(1-d*stop_slippage)
            fraction=.5 if policy=='S4' else 1.
            result['legs'].append(dict(index=k,time=int(bars.timestamp[k]),
                available_time=int(bars.timestamp[k])+(0 if gap else bars.seconds),
                timing='open_gap' if gap else 'intrabar',price=price,fraction=fraction,
                reason=policy,trigger_price=level))
            result['remaining_fraction']-=fraction;result['stop_triggered']=True
    elif policy=='S5':
        s=int(np.searchsorted(bars.timestamp,t['entry_signal_time']))
        if s>=a or int(bars.timestamp[s])!=t['entry_signal_time']:
            raise ValueError('Pre-entry signal candle missing')
        level=float(bars.low[s] if d==1 else bars.high[s])
        for k in range(a,min(a+2,z,len(bars.timestamp)-1)):
            # If the original order already exits at the next open, it has priority.
            if d*(bars.close[k]-level)<0 and k+1<z:
                price=float(bars.open[k+1])*(1-d*stop_slippage)
                result['legs'].append(dict(index=k+1,time=int(bars.timestamp[k+1]),
                    available_time=int(bars.timestamp[k+1]),timing='open',price=price,
                    fraction=1.,reason=policy,trigger_price=level))
                result['remaining_fraction']=0.;result['stop_triggered']=True;break
    if result['remaining_fraction'] and 'exit_price' in t:
        result['legs'].append(dict(index=z,time=t['exit_time'],available_time=t['exit_time'],
            timing='open',price=t['exit_price'],fraction=result['remaining_fraction'],
            reason=t.get('exit_reason','original_exit'),trigger_price=None))
        result['remaining_fraction']=0.
    if not result['remaining_fraction']:
        legs=result['legs'];weighted=sum(l['fraction']*l['price'] for l in legs)
        final=legs[-1]
        result.update(exit_time=final['time'],exit_available_time=final['available_time'],
            exit_price=weighted,exit_reason=policy if result['stop_triggered'] else t.get('exit_reason','original_exit'),
            gross_return=d*(weighted/p-1),net_return=d*(weighted/p-1)-fee*(1+weighted/p),
            duration_minutes=(final['available_time']-t['entry_time'])/60)
    return result


def replay_selective(bars,positions,*,fee=.0002,initial=1000.,leverage=10.):
    if initial<=0 or leverage<=0 or not 0<=fee<1:
        raise ValueError('Invalid account assumptions')
    cash=initial;peak=initial;dd_bound=0.;curve=[initial];points=[];accepted=[]
    max_mae=0.;zero_events=0;first_zero=None;last_available=-1;marked=initial

    def path(t,notional,before):
        nonlocal peak,dd_bound,max_mae,zero_events,first_zero
        a=int(np.searchsorted(bars.timestamp,t['entry_time']))
        d=1 if t['side']=='long' else -1;p=t['entry_price']
        active=1.;realized=-notional*fee;cursor=a
        highs=[];lows=[];times=[];adverses=[]

        def segment(left,right):
            if right<=left:return
            f=bars.high[left:right] if d==1 else bars.low[left:right]
            x=bars.low[left:right] if d==1 else bars.high[left:right]
            highs.extend(before+realized+notional*active*d*(f/p-1))
            lows.extend(before+realized+notional*active*d*(x/p-1))
            times.extend(bars.timestamp[left:right]);adverses.extend(x)

        for leg in t['legs']:
            k=leg['index'];segment(cursor,k)
            x=leg['price'];q=leg['fraction']
            at_fill=before+realized+notional*active*d*(x/p-1)
            if leg['timing']=='intrabar':
                # Favorable-before-stop is a possible order and conservative DD bound.
                # An adverse wick past a full stop does not belong to the exited position.
                f=float(bars.high[k] if d==1 else bars.low[k])
                highs.append(before+realized+notional*active*d*(f/p-1))
            else:
                highs.append(at_fill)
            realized+=notional*q*(d*(x/p-1)-fee*x/p);active-=q
            post=before+realized+notional*active*d*(x/p-1)
            low=min(at_fill,post);adverse=x
            if leg['timing']=='intrabar' and active>0:
                wick=float(bars.low[k] if d==1 else bars.high[k])
                adverse=min(x,wick) if d==1 else max(x,wick)
                low=min(low,before+realized+notional*active*d*(adverse/p-1))
            lows.append(low);times.append(leg['time']);adverses.append(adverse)
            cursor=k+1 if leg['timing']=='intrabar' else k
        if active>0:segment(cursor,len(bars.timestamp))
        h=np.asarray(highs);l=np.asarray(lows)
        if len(h):
            peaks=np.maximum.accumulate(np.r_[peak,h])[1:]
            dd_bound=max(dd_bound,float(np.max((peaks-np.maximum(l,0))/peaks)))
            peak=max(peak,float(h.max()))
            if (l<=0).any():
                zero_events+=1
                if first_zero is None:first_zero=int(times[np.flatnonzero(l<=0)[0]])
            max_mae=max(max_mae,float(np.maximum(-d*(np.asarray(adverses)/p-1),0).max()))
        return before+realized+notional*active*d*(float(bars.close[-1])/p-1)

    for t in positions:
        if cash<=0:break
        if t['entry_time']<last_available:
            raise ValueError('New entry precedes previous exit availability')
        before=cash;notional=before*leverage/(1+leverage*fee)
        end=path(t,notional,before)
        if t['remaining_fraction']:
            marked=end;break
        # Same algebra as verified original replay; no extra roundoff for S0.
        cash=max(0.,before+notional*t['net_return']);marked=cash
        last_available=t['exit_available_time'];peak=max(peak,cash)
        dd_bound=max(dd_bound,1-cash/peak);curve.append(cash);accepted.append(t)
        points.append(dict(side=t['side'],entry_signal_time=t['entry_signal_time'],entry_time=t['entry_time'],
            exit_time=t['exit_time'],exit_available_time=t['exit_available_time'],entry_price=t['entry_price'],
            exit_price=t['exit_price'],entry_notional=notional,entry_cash_usdt=before,closed_cash_usdt=cash,
            account_return=cash/before-1,unit_net_return=t['net_return'],original_net_return=t['original_net_return'],
            stop_triggered=t['stop_triggered'],exit_reason=t['exit_reason'],legs=t['legs']))
    c=np.array(curve);dd=float(np.max(1-c/np.maximum.accumulate(c))*100)
    dd_bound=max(dd_bound,1-max(marked,0)/peak)
    returns=np.array([p['account_return'] for p in points]);w=returns[returns>1e-12];l=-returns[returns<-1e-12]
    stats=risk_summary(accepted)
    changed=[t for t in accepted if t['stop_triggered'] and t['original_net_return'] is not None]
    old_winners=[t for t in changed if t['original_net_return']>1e-12]
    old_losers=[t for t in changed if t['original_net_return']<-1e-12]
    stats.update(closed_cash_usdt=cash,end_marked_equity_usdt=marked,closed_drawdown_pct=dd,
        ohlc_drawdown_upper_bound_pct=dd_bound*100,price_zero_equity_events=zero_events,first_price_zero_equity_time=first_zero,
        maximum_adverse_price_pct=max_mae*100,minimum_closed_cash_usdt=float(c.min()),maximum_closed_cash_usdt=float(c.max()),
        closed_trades_processed=len(points),account_payoff_ratio=float(w.mean()/l.mean()) if len(w) and len(l) else None,
        stopped_trades=sum(t['stop_triggered'] for t in accepted),original_winners_touched=len(old_winners),
        original_winners_now_loss=sum(t['net_return']<-1e-12 for t in old_winners),original_losers_touched=len(old_losers),
        original_losers_improved=sum(t['net_return']>t['original_net_return']+1e-12 for t in old_losers),
        original_losers_worsened=sum(t['net_return']<t['original_net_return']-1e-12 for t in old_losers),
        open_remaining_fraction=positions[-1]['remaining_fraction'] if positions and positions[-1]['remaining_fraction'] and cash>0 else 0.)
    return stats,points


def load_journals():
    source=json.loads((SOURCE/'results.json').read_text())
    groups=defaultdict(list)
    with (SOURCE/'trades.csv').open() as handle:
        for raw in csv.DictReader(handle):
            if raw['model'] not in EXITS or raw['profile'] not in EXITS[raw['model']]:continue
            key=(raw['venue'],raw['symbol'],int(raw['timeframe_minutes']),raw['model'],raw['profile'])
            groups[key].append({k:int(raw[k]) if k.endswith('_time') else float(raw[k]) if k in ('entry_price','exit_price','entry_atr') else raw[k]
                for k in ('side','entry_signal_time','entry_time','exit_time','entry_price','exit_price','entry_atr','exit_reason')})
    return source,groups


def evaluate(bars,journal,opened,policy,fee,slip):
    source=journal+([opened] if opened is not None else [])
    positions=[apply_policy(bars,t,policy,fee=fee,stop_slippage=slip) for t in source]
    return replay_selective(bars,positions,fee=fee)


def run(output):
    output.mkdir(parents=True,exist_ok=True)
    source,groups=load_journals();fee=source['fee_each_side']
    prior={(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile']):r for r in source['summaries']}
    caps=json.loads((SOURCE/'capital-10x.json').read_text())['summaries']
    caps={(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile']):r for r in caps}
    summaries=[];provenance=[];count=0;writer=None
    split=int(datetime(2026,8,13,15,tzinfo=timezone.utc).timestamp())
    with (output/'trades.csv').open('w',newline='') as log:
        for venue,symbol,tf,bars,start,path in dataset_cases(source['assets']):
            events=validate_alternating_crosses(*crosses(*indicator(bars,'C')))
            for model,profiles in EXITS.items():
                for profile in profiles:
                    key=(venue,symbol,tf,model,profile);journal=groups[key];opened=prior[key]['open_position']
                    for slip in (0.,.0005):
                        baseline=None
                        for policy in POLICIES:
                            stats,points=evaluate(bars,journal,opened,policy,fee,slip)
                            if policy=='S0':
                                expected,_=replay(bars,journal,open_position=opened,fee=fee)
                                for k,v in expected.items():
                                    if isinstance(v,float):assert abs(stats[k]-v)<=max(1e-9,abs(v)*1e-12),(key,k,stats[k],v)
                                    else:assert stats[k]==v,(key,k)
                                for k in ('closed_cash_usdt','end_marked_equity_usdt','closed_drawdown_pct'):
                                    assert stats[k]==caps[key][k],(key,k,'Stored baseline changed')
                                baseline=stats
                            profit=baseline['end_marked_equity_usdt']-1000
                            retention=(stats['end_marked_equity_usdt']-1000)/profit if profit>0 else None
                            qualified=bool(policy!='S0' and retention is not None and retention>=.8
                                and stats['closed_drawdown_pct']<baseline['closed_drawdown_pct']-1e-9
                                and stats['ohlc_drawdown_upper_bound_pct']<baseline['ohlc_drawdown_upper_bound_pct']-1e-9
                                and stats['price_zero_equity_events']==0)
                            segments={}
                            if start==START:
                                for label,left,right in [('first_four_months',start,split),('last_two_months',split,END)]:
                                    part,part_open=window_trades(journal,opened,left,right)
                                    sliced=bars.subset(bars.timestamp<right)
                                    sub,_=evaluate(sliced,part,part_open,policy,fee,slip)
                                    segments[label]=dict(start_utc=iso(left),end_utc_exclusive=iso(right),**sub)
                            tags=dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,profile=profile,policy=policy,stop_slippage=slip)
                            summaries.append(dict(**tags,start_utc=iso(start),end_utc_exclusive=iso(END),six_months=start==START,
                                **stats,baseline_profit_retention=retention,qualified=qualified,temporal_segments=segments))
                            for p in points:
                                record=dict(**tags,**p);record['legs']=json.dumps(record['legs'],separators=(',',':'))
                                if writer is None:writer=csv.DictWriter(log,fieldnames=list(record));writer.writeheader()
                                writer.writerow(record);count+=1
                    print(f'{venue} {symbol} {tf}m {model}/{profile}: baseline verified; S1-S5 × 2 cost scenarios complete',flush=True)
            provenance.append(dict(venue=venue,symbol=symbol,timeframe_minutes=tf,path=str(path),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),raw_cross_events=events,raw_cross_repeated_direction=0))
    payload=dict(initial_cash_usdt=1000,leverage=10,fee_each_side=fee,assets=source['assets'],period_utc=source['period_utc'],
        policies=POLICIES,exit_profiles=EXITS,slippage_scenarios=[0.,.0005],parameters_fixed_before_run=True,
        trades_written=count,account='Independent full-account 10x; notional=cash*10/(1+10*fee)',
        partial='S4 closes half original quantity, no resizing/reinvestment until fully flat; aggregate legs as one trade',
        fills='Touch at stop price or adverse gap open, then adverse stop-only slippage; original orders at next open have priority',
        stop_time='Intrabar event has bar-open timestamp and availability at bar close; exact tick time unknown',
        drawdown='Conservative possible favorable-before-stop OHLC upper bound; gap/full-stop excludes post-exit wicks; half-stop remaining quantity retains wicks',
        selection='>=80% original NET profit AND both drawdowns lower AND no last-price zero-equity touches; baseline profit must be positive',
        limitations='Retrospective observed data, not unseen holdout. Funding, fair-price liquidation, maintenance margin, lot limits, liquidity excluded',
        temporal_segments='Independent $1000 accounts, no boundary position carry, final positions marked without fictitious exit fee',
        source_sha256={name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in ('results.json','trades.csv','capital-10x.json')},
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),provenance=provenance,summaries=summaries)
    (output/'results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    flat=[{k:v for k,v in r.items() if k not in ('temporal_segments','exit_reasons')} for r in summaries]
    with (output/'summary.csv').open('w',newline='') as handle:
        w=csv.DictWriter(handle,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    print(f'Completed {len(summaries)} scenarios and {count} closed position records',flush=True)


def refresh_diagnostics(output):
    """Recheck affected half-stop diagnostics; assert all other results unchanged."""
    payload=json.loads((output/'results.json').read_text())
    source,groups=load_journals();fee=source['fee_each_side']
    prior={(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile']):r for r in source['summaries']}
    rows={(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'],r['stop_slippage']):r
        for r in payload['summaries'] if r['policy']=='S4'}
    split=int(datetime(2026,8,13,15,tzinfo=timezone.utc).timestamp());changes=0

    def checked_update(old,new):
        nonlocal changes
        for k,v in new.items():
            if k!='maximum_adverse_price_pct':assert old[k]==v,(k,old[k],v,'Diagnostic correction altered other result')
        if old['maximum_adverse_price_pct']!=new['maximum_adverse_price_pct']:changes+=1
        old['maximum_adverse_price_pct']=new['maximum_adverse_price_pct']

    for venue,symbol,tf,bars,start,path in dataset_cases(source['assets']):
        assert hashlib.sha256(path.read_bytes()).hexdigest()==next(p['sha256'] for p in payload['provenance']
            if (p['venue'],p['symbol'],p['timeframe_minutes'])==(venue,symbol,tf))
        for model,profiles in EXITS.items():
            for profile in profiles:
                key=(venue,symbol,tf,model,profile);journal=groups[key];opened=prior[key]['open_position']
                for slip in (0.,.0005):
                    old=rows[(*key,slip)];new,_=evaluate(bars,journal,opened,'S4',fee,slip);checked_update(old,new)
                    if start==START:
                        for label,left,right in [('first_four_months',start,split),('last_two_months',split,END)]:
                            part,part_open=window_trades(journal,opened,left,right)
                            sliced=bars.subset(bars.timestamp<right)
                            sub,_=evaluate(sliced,part,part_open,'S4',fee,slip)
                            checked_update(old['temporal_segments'][label],sub)
        print(f'Rechecked half-stop path diagnostics {venue} {symbol} {tf}m',flush=True)
    payload['original_run_script_sha256']=payload['script_sha256']
    payload['original_run_script_file']='engine-before-mae-correction.py'
    assert hashlib.sha256((output/payload['original_run_script_file']).read_bytes()).hexdigest()==payload['original_run_script_sha256']
    payload['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    payload['diagnostic_refresh']=dict(fields=['maximum_adverse_price_pct'],changed_records_including_segments=changes,
        unchanged_verified='All other complete-period and subperiod statistics, including every cash and drawdown value',
        command='python scripts/ppp_selective_backtest.py --refresh-diagnostics')
    (output/'results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    flat=[{k:v for k,v in r.items() if k not in ('temporal_segments','exit_reasons')} for r in payload['summaries']]
    with (output/'summary.csv').open('w',newline='') as handle:
        w=csv.DictWriter(handle,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
    print(f'Diagnostic correction completed: {changes} MAE values updated; all cash/drawdown values unchanged',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-selective-2026-10-14')
    parser.add_argument('--refresh-diagnostics',action='store_true')
    a=parser.parse_args()
    (refresh_diagnostics if a.refresh_diagnostics else run)(a.output)
