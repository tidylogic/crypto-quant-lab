#!/usr/bin/env python3
"""Freeze two SMA sets and two entry modes with a shared source-close exit."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

from ppp_backtest import ROOT, START, END
from ppp_combo_backtest import build_features
from ppp_support_ladder import market_cases, prepare, simulate_ladder
from ppp_largecap_research import TARGETS, COMPARISONS, COSTS
from ppp_risk_backtest import risk_summary
from ppp_selective_backtest import replay_selective
from ppp_asset_research import kst, write_csv

SETS={'20':(20,50,100,200),'30':(30,60,120,240)}
MODES={'direct':dict(wait=False,retry=False,risk='baseline'),
       'confirmed':dict(wait=True,retry=False,risk='baseline')}
MODE_NAMES={'direct':'신호 봉 마감 직후 진입','confirmed':'1분봉 지지·저항 확인 후 진입'}
DEFAULT_OUTPUT=ROOT/'user_data/backtest_results/ppp-sma-entry-2026-10-15'
DEPENDENCIES=['ppp_sma_entry_comparison.py','ppp_support_ladder.py','ppp_backtest.py',
              'ppp_combo_backtest.py','ppp_risk_backtest.py','ppp_selective_backtest.py','ppp_largecap_research.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def combine(rows):
    n=sum(r['strategy_trades'] for r in rows);w=sum(r['strategy_wins'] for r in rows);l=sum(r['strategy_losses'] for r in rows)
    gain=sum(r['gain_sum'] for r in rows);loss=sum(r['loss_sum'] for r in rows);net=sum(r['net_sum'] for r in rows)
    return dict(trades=n,wins=w,losses=l,win_rate_pct=100*w/n if n else None,
                profit_factor=gain/loss if loss else None,payoff_ratio=(gain/w)/(loss/l) if w and l and loss else None,
                avg_net_return_pct=100*net/n if n else None)


def capital_entries(positions,points,stats):
    executed={p['entry_time'] for p in points}
    if stats['open_remaining_fraction']>0 and positions and positions[-1]['remaining_fraction']>0:
        executed.add(positions[-1]['entry_time'])
    return executed


def audit_positions(b,d,positions,mode,fee,slippage,end):
    """Independent journal invariants use observed bars, not replay summaries."""
    last_available=-1;checks=0
    for p in positions:
        a=int(np.searchsorted(b.timestamp,p['entry_time']));direction=p['direction']
        assert int(b.timestamp[a])==p['entry_time'] and p['entry_time']>=last_available
        assert p['entry_price']==float(b.open[a])
        assert p['parent_signal_time']+d['parent_seconds']==p['setup_available_time']<=p['entry_time']
        assert bool(d['bull'][a-1] if direction==1 else d['bear'][a-1])
        if mode=='direct':
            assert p['entry_time']==p['setup_available_time']
        else:
            assert p['entry_time']-60>=p['setup_available_time']
            assert p['entry_time']<p['setup_available_time']+3*d['parent_seconds']
            level=float(d['mas'][a-1,p['entry_support_index']]);margin=p['tolerance']
            assert round(float(b.low[a-1]),9)<=round(level+margin,9) and round(float(b.high[a-1]),9)>=round(level-margin,9)
            assert direction*(round(float(b.close[a-1]),9)-round(level+direction*margin,9))>=0
            assert direction*(round(float(b.close[a-1]),9)-round(float(b.open[a-1]),9))>0
        if not p['remaining_fraction']:
            z=int(np.searchsorted(b.timestamp,p['exit_time']));leg=p['legs'][-1]
            assert p['entry_time']<=p['exit_time']<end
            ratio=p['exit_price']/p['entry_price']
            assert abs(p['net_return']-(direction*(ratio-1)-fee*(1+ratio)))<1e-12
            if p['exit_reason']=='S2':
                level=p['entry_price']*(1-direction*.01)
                gap=direction*(float(b.open[z])-level)<=0
                expected=(float(b.open[z]) if gap else level)*(1-direction*slippage)
                assert p['exit_price']==expected and p['exit_time']<p['guard_end']
                assert (b.low[z]<=level if direction==1 else b.high[z]>=level)
                assert p['exit_available_time']==int(b.timestamp[z])+(0 if gap else 60)
            else:
                assert p['exit_price']==float(b.open[z]) and p['exit_available_time']==p['exit_time']
                assert d['parent_event'][z-1]
                if p['exit_reason']=='opposite_cross':assert bool(d['down'][z-1] if direction==1 else d['up'][z-1])
                else:
                    assert p['exit_reason']=='sma'+str(d['ma_periods'][1])
                    assert direction*(round(float(b.close[z-1]),9)-float(d['mas'][z-1,1]))<0
            last_available=p['exit_available_time']
        else:last_available=end
        checks+=1
    return checks


def run(output):
    output.mkdir(parents=True,exist_ok=True)
    protocol=dict(strategy='G: nested Stochastic + MFI14 directional50 + RVOL1.2',sets=SETS,modes=MODES,
                  start=START,end=END,assets=TARGETS+COMPARISONS,timeframes=[1,3,5,15],costs=COSTS,
                  exits='Both modes: source-close opposite cross OR second SMA failure; next actual minute open. Separate S2 intrabar first-entry-source-candle stop.',
                  wait='Sequential selected periods, ATR14*0.1, 3 source candles, one fill per fresh G setup; no deeper-line retry after fill.',
                  capital='Independent $1000 10x full compounding; no funding, fair-price liquidation, lot constraints or general slippage.',
                  end_boundary='No new fills at end; unfinished positions marked at last close and excluded from closed-trade win rate.',
                  dependencies={name:digest(ROOT/'scripts'/name) for name in DEPENDENCIES})
    (output/'fixed-protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2))
    old_path=ROOT/'user_data/backtest_results/ppp-support-2026-10-14/results.json'
    old=json.loads(old_path.read_text()) if old_path.exists() else None
    prior={(r['asset'],r['venue'],r['timeframe_minutes'],r['cost']):r for r in old['rows'] if r['variant']=='B0'} if old else {}
    rows=[];sources=[];source_hashes={};baseline=[];checked=0
    fields=['asset','venue','timeframe_minutes','sma_set','mode','cost','side','entry_time','entry_price','parent_signal_time','setup_available_time',
            'entry_support_index','exit_time','exit_available_time','exit_price','exit_reason','net_return','capital_executed','open_position']
    with (output/'trades.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for asset,venue,tf,minutes,parent,start,mp,pp in market_cases(TARGETS+COMPARISONS):
            paths=[mp]+([pp] if pp else [])
            for p in paths:
                if str(p) not in source_hashes:source_hashes[str(p)]=digest(p)
            f=build_features(parent)
            sources.append(dict(asset=asset,venue=venue,timeframe_minutes=tf,start=start,end=END,full_period=start==START,
                                paths={str(p):source_hashes[str(p)] for p in paths}))
            for set_id,periods in SETS.items():
                b,d=prepare(minutes,parent,start,END,features=f,levels=periods)
                for mode,cfg in MODES.items():
                    for cost,assumed in COSTS.items():
                        sim=simulate_ladder(b,d,'B0',end=END,fee=assumed['fee'],stop_slippage=assumed['stop_slippage'],config=cfg)
                        checked+=audit_positions(b,d,sim['positions'],mode,assumed['fee'],assumed['stop_slippage'],END)
                        stats,points=replay_selective(b,sim['positions'],fee=assumed['fee'])
                        closed=[t for t in sim['positions'] if not t['remaining_fraction']];unit=risk_summary(closed)
                        net=np.array([t['net_return'] for t in closed]);positive=net[net>1e-12];negative=net[net<-1e-12]
                        delays=[(t['entry_time']-t['setup_available_time'])/60 for t in sim['positions']]
                        exposure=sum((t.get('exit_available_time',END)-t['entry_time']) for t in sim['positions'])/(END-start)*100
                        row=dict(asset=asset,role='target' if asset in TARGETS else 'comparison',venue=venue,timeframe_minutes=tf,
                                 sma_set=set_id,periods='/'.join(map(str,periods)),mode=mode,label=MODE_NAMES[mode],cost=cost,full_period=start==START,
                                 start_kst=kst(start),end_kst=kst(END),**stats,strategy_trades=unit['trades'],strategy_wins=unit['wins'],strategy_losses=unit['losses'],
                                 strategy_win_rate_pct=unit['win_rate_pct'],strategy_payoff_ratio=unit['payoff_ratio'],strategy_profit_factor=unit['profit_factor'],
                                 gain_sum=float(positive.sum()),loss_sum=float(-negative.sum()),net_sum=float(net.sum()),
                                 exposure_pct=exposure,mean_entry_delay_minutes=float(np.mean(delays)) if delays else None,
                                 expired_setups=sim['diagnostics'].get('wait_cancel_expired',0),qualified_setups=sim['diagnostics'].get('qualified_source_signals',0),
                                 diagnostics=sim['diagnostics'])
                        rows.append(row)
                        if set_id=='20' and mode=='direct' and (asset,venue,tf,cost) in prior:
                            ref=prior[(asset,venue,tf,cost)]
                            assert all(stats[key]==ref[key] for key in stats),f'Historical baseline changed: {asset} {venue} {tf} {cost}'
                            assert unit['trades']==ref['strategy_trades']
                            baseline.append(dict(asset=asset,venue=venue,timeframe_minutes=tf,cost=cost,matches=True))
                        executed=capital_entries(sim['positions'],points,stats)
                        for t in sim['positions']:
                            writer.writerow(dict(asset=asset,venue=venue,timeframe_minutes=tf,sma_set=set_id,mode=mode,cost=cost,
                                                 **{k:t.get(k) for k in fields if k in t},capital_executed=t['entry_time'] in executed,
                                                 open_position=bool(t['remaining_fraction'])))
            print(f'Completed {asset} {venue} {tf}m: two SMA sets × two entry modes × two costs',flush=True)
    for p,sha in source_hashes.items():assert digest(Path(p))==sha,'Source file changed during run'
    for name,sha in protocol['dependencies'].items():assert digest(ROOT/'scripts'/name)==sha,'Trading implementation changed during run'
    aggregates=[]
    for scope,assets in [('highercap5',TARGETS),('all7',TARGETS+COMPARISONS)]:
        for tf in [1,3,5,15]:
            for set_id in SETS:
                for mode in MODES:
                    for cost in COSTS:
                        group=[r for r in rows if r['asset'] in assets and r['venue']=='binance_um' and r['full_period'] and r['timeframe_minutes']==tf and r['sma_set']==set_id and r['mode']==mode and r['cost']==cost]
                        aggregates.append(dict(scope=scope,timeframe_minutes=tf,sma_set=set_id,mode=mode,cost=cost,**combine(group)))
    result=dict(protocol=protocol,rows=rows,aggregates=aggregates,sources=sources,
                validation=dict(journal_positions=checked,historical_baseline_matches=len(baseline),expected_historical_baselines=len(prior),source_hashes_verified=len(source_hashes),source_cases=len(sources)))
    assert not prior or len(baseline)==len(prior)
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    (output/'baseline-audit.json').write_text(json.dumps(baseline,ensure_ascii=False,indent=2))
    (output/'validation.json').write_text(json.dumps(result['validation'],indent=2))
    write_csv(output/'summary.csv',[{k:v for k,v in r.items() if k!='diagnostics'} for r in rows])
    write_csv(output/'aggregate.csv',aggregates)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args();run(args.output)
