#!/usr/bin/env python3
"""Fixed exposure/feedback controls on verified C/E/G opportunity journals."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from ppp_backtest import ROOT, START, END, iso, indicator, crosses
from ppp_combo_backtest import dataset_cases
from ppp_risk_backtest import risk_features, risk_summary
from ppp_capital_replay import replay

POLICIES={
    'Q0':'100% cash allocation, 10x contract leverage',
    'Q1':'50% cash allocation, 10x contract leverage',
    'Q2':'25% cash allocation, 10x contract leverage',
    'Q3':'ATR14 reference risk 1% of equity, allocation cap50%',
    'Q4':'Q3 + after2 known consecutive losses pause signals for6 bars',
    'Q5':'Q3 + closed-equity DD>=10% half size / >=20% quarter size',
    'Q6':'Q3 + Q4 cooldown + Q5 drawdown scaling',
}
EXITS={'C':('R0','R4'),'E':('R0',),'G':('R0','R2')}
SOURCE=ROOT/'user_data/backtest_results/ppp-risk-eth-2026-10-14'


def validate_alternating_crosses(up,down):
    up=np.asarray(up,dtype=bool);down=np.asarray(down,dtype=bool)
    if len(up)!=len(down) or (up&down).any():
        raise ValueError('Invalid simultaneous or mismatched raw cross arrays')
    events=np.flatnonzero(up|down)
    if len(events)>1 and (up[events][1:]==up[events][:-1]).any():
        raise ValueError('Repeated raw cross direction: journal replay would omit entry opportunities; use event simulation')
    return len(events)


def window_trades(journal, final_open, left, right):
    closed=[];opened=None
    for t in journal:
        if left<=t['entry_signal_time'] and t['entry_time']<right:
            if t['exit_time']<right:
                closed.append(t)
            else:
                opened={k:v for k,v in t.items() if k not in ('exit_time','exit_price','exit_signal_time','exit_reason','gross_return','net_return','duration_minutes')}
    if final_open is not None and left<=final_open['entry_signal_time'] and final_open['entry_time']<right:
        opened=final_open
    return closed,opened


def manage(bars,journal,features,*,policy,open_position=None,fee=.0002,initial=1000.,leverage=10.):
    if policy not in POLICIES or initial<=0 or leverage<=0 or not 0<=fee<1:
        raise ValueError('Invalid management policy or cash assumptions')
    cash=initial;peak=initial;dd_bound=0.;curve=[initial];points=[];accepted=[]
    zero_events=0;first_zero=None;max_mae=0.;pending=deque()
    decision_cash=initial;decision_peak=initial;streak=0;pause_until=-1
    cooldown_events=skipped_cooldown=skipped_invalid=0
    last_exit=-1

    def allocation(t):
        nonlocal decision_cash,decision_peak,streak,pause_until,cooldown_events,skipped_cooldown,skipped_invalid
        # Feedback must be known by the SIGNAL BAR OPEN, before its close orders.
        # In particular, never use the future loss of a same-open reversal exit.
        signal_time=t['entry_signal_time']
        while pending and pending[0][0]<=signal_time:
            when,new_cash,ret=pending.popleft()
            decision_cash=new_cash;decision_peak=max(decision_peak,new_cash)
            streak=streak+1 if ret < -1e-12 else 0
            if policy in ('Q4','Q6') and streak>=2:
                pause_until=max(pause_until,when+6*bars.seconds)
                cooldown_events+=1;streak=0
        if policy in ('Q4','Q6') and signal_time<pause_until:
            skipped_cooldown+=1;return 0.,0.
        dd=max(0.,1-decision_cash/decision_peak)
        if policy in ('Q0','Q1','Q2'):
            return {'Q0':1.,'Q1':.5,'Q2':.25}[policy],dd
        i=int(np.searchsorted(bars.timestamp,signal_time))
        if i==len(bars.timestamp) or int(bars.timestamp[i])!=signal_time:
            raise ValueError('Entry signal is absent from source candles')
        atr=float(features['atr'][i]);p=float(bars.close[i])
        if not np.isfinite(atr) or atr<=0 or p<=0:
            skipped_invalid+=1;return 0.,dd
        d=1 if t['side']=='long' else -1
        distance=1.5*atr/p
        # Estimate using known signal close; actual gaps and E/G exits differ.
        reference_loss=distance+fee*(2-d*distance)
        fraction=min(.5,.01*(1+leverage*fee)/(leverage*reference_loss))
        if policy in ('Q5','Q6'):
            fraction*=.25 if dd>=.2-1e-12 else .5 if dd>=.1-1e-12 else 1.
        return fraction,dd

    def excursion(t,notional,account):
        nonlocal peak,dd_bound,zero_events,first_zero,max_mae
        a=int(np.searchsorted(bars.timestamp,t['entry_time']))
        z=int(np.searchsorted(bars.timestamp,t.get('exit_time',int(bars.timestamp[-1])+bars.seconds)))
        if a>=z or int(bars.timestamp[a])!=t['entry_time']:
            raise ValueError('Entry/exit timestamps do not match candle path')
        d=1 if t['side']=='long' else -1;p=t['entry_price']
        favorable=bars.high[a:z] if d==1 else bars.low[a:z]
        adverse=bars.low[a:z] if d==1 else bars.high[a:z]
        times=bars.timestamp[a:z]
        if 'exit_price' in t:
            favorable=np.r_[favorable,t['exit_price']];adverse=np.r_[adverse,t['exit_price']]
            times=np.r_[times,t['exit_time']]
        high=account-notional*fee+notional*d*(favorable/p-1)
        low=account-notional*fee+notional*d*(adverse/p-1)
        peaks=np.maximum.accumulate(np.r_[peak,high])[1:]
        dd_bound=max(dd_bound,float(np.max((peaks-np.maximum(low,0))/peaks)))
        peak=max(peak,float(high.max()))
        if (low<=0).any():
            zero_events+=1
            if first_zero is None:first_zero=int(times[np.flatnonzero(low<=0)[0]])
        max_mae=max(max_mae,float(np.maximum(-d*(adverse/p-1),0).max()))

    for t in journal:
        if t['entry_time']<last_exit or t['exit_time']<=t['entry_time']:
            raise ValueError('Overlapping or unordered opportunity journal')
        last_exit=t['exit_time']
        if cash<=0:break
        fraction,signal_dd=allocation(t)
        if not fraction:continue
        before=cash
        # Each allocated cash pool pays its own entry fee and initial margin.
        notional=before*fraction*leverage/(1+leverage*fee)
        excursion(t,notional,before)
        ratio=t['exit_price']/t['entry_price'];d=1 if t['side']=='long' else -1
        gross=d*(ratio-1);net=gross-fee*(1+ratio)
        cash=max(0.,before+notional*net);account_return=cash/before-1
        pending.append((t['exit_time'],cash,account_return))
        peak=max(peak,cash);dd_bound=max(dd_bound,1-cash/peak);curve.append(cash)
        points.append(dict(side=t['side'],entry_signal_time=t['entry_signal_time'],entry_time=t['entry_time'],exit_time=t['exit_time'],
                           entry_notional=notional,margin_fraction=fraction,decision_drawdown_pct=signal_dd*100,
                           entry_cash_usdt=before,closed_cash_usdt=cash,account_return=account_return,
                           unit_net_return=net))
        accepted.append(dict(side=t['side'],gross_return=gross,net_return=net,
                             duration_minutes=(t['exit_time']-t['entry_time'])/60,
                             exit_reason=t.get('exit_reason','opposite_cross')))
    marked=cash;open_taken=False;open_fraction=None
    if open_position is not None and cash>0:
        if open_position['entry_time']<last_exit:raise ValueError('Open position overlaps opportunity journal')
        fraction,_=allocation(open_position)
        if fraction:
            open_taken=True;open_fraction=fraction
            notional=cash*fraction*leverage/(1+leverage*fee)
            excursion(open_position,notional,cash)
            d=1 if open_position['side']=='long' else -1
            marked=cash-notional*fee+notional*d*(bars.close[-1]/open_position['entry_price']-1)
            dd_bound=max(dd_bound,1-max(marked,0)/peak)
    c=np.array(curve);dd=float(np.max(1-c/np.maximum.accumulate(c))*100)
    returns=np.array([p['account_return'] for p in points]);w=returns[returns>1e-12];l=-returns[returns<-1e-12]
    stats=risk_summary(accepted)
    result=dict(**stats,closed_cash_usdt=cash,end_marked_equity_usdt=marked,closed_drawdown_pct=dd,
                ohlc_drawdown_upper_bound_pct=dd_bound*100,price_zero_equity_events=zero_events,
                first_price_zero_equity_time=first_zero,maximum_adverse_price_pct=max_mae*100,
                minimum_closed_cash_usdt=float(c.min()),maximum_closed_cash_usdt=float(c.max()),
                closed_trades_processed=len(points),opportunities=len(journal),skipped_cooldown=skipped_cooldown,
                skipped_invalid=skipped_invalid,cooldown_events=cooldown_events,open_position_taken=open_taken,
                open_margin_fraction=open_fraction,
                account_payoff_ratio=float(w.mean()/l.mean()) if len(w) and len(l) else None,
                avg_account_return_pct=float(returns.mean()*100) if len(returns) else None,
                average_margin_fraction=float(np.mean([p['margin_fraction'] for p in points])) if points else None,
                maximum_margin_fraction=float(max(p['margin_fraction'] for p in points)) if points else None)
    return result,points


def run(output):
    output.mkdir(parents=True,exist_ok=True)
    source=json.loads((SOURCE/'results.json').read_text())
    old_cap=json.loads((SOURCE/'capital-10x.json').read_text())
    prior={(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile']):r for r in source['summaries']}
    caps={(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile']):r for r in old_cap['summaries']}
    groups=defaultdict(list)
    with (SOURCE/'trades.csv').open() as handle:
        for raw in csv.DictReader(handle):
            if raw['model'] not in EXITS or raw['profile'] not in EXITS[raw['model']]:continue
            key=(raw['venue'],raw['symbol'],int(raw['timeframe_minutes']),raw['model'],raw['profile'])
            t={k:(int(raw[k]) if k.endswith('_time') else float(raw[k]) if k in ('entry_price','exit_price','entry_atr') else raw[k])
               for k in ('side','entry_signal_time','entry_time','exit_time','entry_price','exit_price','entry_atr','exit_reason')}
            groups[key].append(t)
    summaries=[];journals=[];provenance=[]
    split=int(datetime(2026,8,13,15,tzinfo=timezone.utc).timestamp())
    for venue,symbol,tf,bars,start,path in dataset_cases(source['assets']):
        features=risk_features(bars)
        # Crosses need not alternate mathematically (equality touches can repeat).
        # Journal replay is permitted only after this FULL raw-array audit passes.
        raw_event_count=validate_alternating_crosses(*crosses(*indicator(bars,'C')))
        for model,profiles in EXITS.items():
            for profile in profiles:
                key=(venue,symbol,tf,model,profile);journal=groups[key];opened=prior[key]['open_position']
                for policy in POLICIES:
                    stats,points=manage(bars,journal,features,policy=policy,open_position=opened,fee=source['fee_each_side'])
                    if policy=='Q0':
                        expected,_=replay(bars,journal,open_position=opened,fee=source['fee_each_side'])
                        for k,v in expected.items():
                            assert stats[k]==v,f'Original capital replay changed: {key} {k}'
                        for k in ('closed_cash_usdt','end_marked_equity_usdt','closed_drawdown_pct','ohlc_drawdown_upper_bound_pct'):
                            assert stats[k]==caps[key][k],f'Previous stored capital differs: {key} {k}'
                    segments={}
                    if start==START:
                        for label,left,right in [('first_four_months',start,split),('last_two_months',split,END)]:
                            part,part_open=window_trades(journal,opened,left,right)
                            sliced=bars.subset(bars.timestamp<right)
                            sub,_=manage(sliced,part,features,policy=policy,open_position=part_open,fee=source['fee_each_side'])
                            segments[label]=dict(start_utc=iso(left),end_utc_exclusive=iso(right),**sub)
                    record=dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,profile=profile,policy=policy,
                                start_utc=iso(start),end_utc_exclusive=iso(END),six_months=start==START,**stats,temporal_segments=segments)
                    summaries.append(record)
                    journals.extend(dict(venue=venue,symbol=symbol,timeframe_minutes=tf,model=model,profile=profile,policy=policy,**p) for p in points)
                print(f'{venue} {symbol} {tf}m {model}/{profile}: Q0 matched; Q1-Q6 completed',flush=True)
        provenance.append(dict(venue=venue,symbol=symbol,timeframe_minutes=tf,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                               raw_cross_events=raw_event_count,raw_cross_repeated_direction=0))
    payload=dict(initial_cash_usdt=1000,leverage=10,fee_each_side=source['fee_each_side'],period_utc=source['period_utc'],
                 policies=POLICIES,exit_profiles=EXITS,parameters_fixed_before_run=True,
                 sizing='Fraction of cash allocated to margin plus entry fee; notional=cash*fraction*10/(1+10*fee)',
                 atr='ATR14 from entry signal candle; reference loss=1.5ATR/signalclose + fee*(2-direction*1.5ATR/signalclose); capallocation.5',
                 reference_risk='ATR target1% is a sizing estimate, not an enforced loss cap, especially R0/R2 or gap exits',
                 feedback='Only accepted closed trades with exit_time<=entry_signal_BAR_OPEN update streak and closed-equity DD',
                 cooldown='After2 known consecutive losses, block signal opens until actual exit_time+6bars; reset streak at trigger; wins do not cancel existing pause',
                 drawdown_scaling='Known closed-equity highwater DD>=10% halves ATR size; >=20% quarters; no guarantee maxDD<=20%',
                 opportunities='Journal replay only after full UNFILTERED raw-C arrays on every dataset have been verified to alternate; repeated directions reject the run. This is a dataset check, not a general crossover property',
                 metrics='Unit payoff on accepted price trades; account payoff on accepted trade return relative to entry cash, after variable sizing',
                 liquidation='Not simulated; funding/slippage/minimum lots/position limits excluded; zero-equity last-price screen only',
                 ohlc_drawdown='Pessimistic high-before-low upperbound, not exact intrabar path or fairprice account DD',
                 segments='Independent cash1000 and reset controls for first4months/last2months; interval-end open position marked, no fictional exit',
                 selection='Fixed small menu; same historical data previously seen, NOT unseen validation; report tradeoffs rather than maxprofit alone',
                 source_sha256={n:hashlib.sha256((SOURCE/n).read_bytes()).hexdigest() for n in ('results.json','trades.csv','capital-10x.json')},
                 engine_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),ROOT/'scripts/ppp_capital_replay.py')},
                 provenance=provenance,summaries=summaries)
    (output/'results.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    excluded=('temporal_segments','exit_reasons','win_rate_wilson95_pct')
    for name,rows in [('summary.csv',[{k:v for k,v in r.items() if k not in excluded} for r in summaries]),('managed-trades.csv',journals)]:
        with (output/name).open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(f'Saved {len(summaries)} management cases, {len(journals)} accepted closed trades: {output}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-drawdown-2026-10-14')
    run(parser.parse_args().output)
