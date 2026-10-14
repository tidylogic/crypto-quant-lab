#!/usr/bin/env python3
"""Fixed early-entry hypotheses, BTC/ETH training and new-asset validation."""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,inspect
from pathlib import Path
import numpy as np
from ppp_backtest import ROOT,START,END,load,resample,smooth,crosses
from ppp_combo_backtest import build_features,direction_filters
from ppp_risk_backtest import risk_features,simulate_risk
from ppp_selective_backtest import apply_policy,replay_selective
from ppp_asset_research import kst,write_csv
from ppp_drawdown_backtest import validate_alternating_crosses

SPLIT=1786633200  # 2026-08-14 00:00 KST; four months then two months.
TARGETS=('BTC','ETH','BNB','SOL','XRP')
COMPARISONS=('WLD','ZEC')
FEE=.0002
ENTRY_NAMES={'B0':'기준형','T1':'초입 교차','T2':'초입·이격 제한','T3':'초입·추세 강도',
             'T4':'초입·첫 정렬','T5':'초입·중간 교차','T6':'초입·모멘텀 회복'}
CONFIGS=[dict(id='B0',entry='B0',risk='R2',label='기준형 · SMA50 청산 + 첫 봉 1% 손절')]+[
    dict(id=f'{entry}-{risk}',entry=entry,risk=risk,label=ENTRY_NAMES[entry]+' · '+{'R1':'SMA20 청산','R2':'SMA50 청산','R4':'ATR 종가 손절'}[risk]+' + 첫 봉 1% 손절')
    for entry in ['T1','T2','T3','T4','T5','T6'] for risk in ['R1','R2','R4']]
COSTS={'nominal':dict(fee=.0002,stop_slippage=0.),'stress':dict(fee=.0003,stop_slippage=.0005)}
DATA_ROOTS={a:(ROOT/'user_data/data'/('ppp-binance' if a in ('BTC','ZEC') else 'ppp-binance-eth' if a=='ETH' else 'ppp-binance-wld' if a=='WLD' else 'ppp-binance-largecap'),
               ROOT/'user_data/data'/('ppp-mexc' if a in ('BTC','ZEC') else 'ppp-mexc-eth' if a=='ETH' else 'ppp-mexc-wld' if a=='WLD' else 'ppp-mexc-largecap'))
            for a in TARGETS+COMPARISONS}


def frozen_contract():
    """Bind selection to signal, replay and cost implementation, not just labels."""
    sources={name:hashlib.sha256((ROOT/'scripts'/name).read_bytes()).hexdigest() for name in
             ['ppp_backtest.py','ppp_combo_backtest.py','ppp_risk_backtest.py','ppp_selective_backtest.py','ppp_drawdown_backtest.py']}
    code=''.join(inspect.getsource(fn) for fn in [age,extra_features,entry_gates,evaluate])
    return dict(configs=CONFIGS,costs=COSTS,fee_gate=FEE,start=START,end=END,split=SPLIT,
                signal_replay_sha256=hashlib.sha256(code.encode()).hexdigest(),dependencies=sources)


def verify_frozen(output):
    selection=json.loads((output/'selection-frozen.json').read_text())
    hypothesis=output/'fixed-hypotheses.json'
    if hashlib.sha256(hypothesis.read_bytes()).hexdigest()!=selection['hypotheses_sha256']:
        raise ValueError('Frozen hypotheses changed since selection')
    universe=json.loads(hypothesis.read_text())
    if universe['targets']!=list(TARGETS) or universe['comparisons']!=list(COMPARISONS):
        raise ValueError('Frozen evaluation universe changed since selection')
    if selection.get('contract')!=frozen_contract():raise ValueError('Frozen strategy or costs changed since selection; retrain explicitly')
    if selection['chosen'] not in CONFIGS:raise ValueError('Unknown frozen configuration')
    return selection


def age(flags):
    starts=np.where(flags&~np.r_[False,flags[:-1]],np.arange(len(flags)),-1)
    return np.where(flags,np.arange(len(flags))-np.maximum.accumulate(starts),-1)


def extra_features(bars,f,fee):
    rf=risk_features(bars);ma=rf['sma20'];atr=rf['atr']
    with np.errstate(divide='ignore',invalid='ignore'):
        distance=(bars.close-ma)/atr
        slope=(ma-np.r_[np.full(3,np.nan),ma[:-3]])/atr
        cost=(atr/bars.close)/max(2*fee,1e-12)
    return dict(**rf,distance=distance,slope=slope,age_long=age(f['bull']),age_short=age(f['bear']),atr_fee_ratio=cost)


def entry_gates(name,f,x):
    """All comparisons are close-known, with common thresholds for every coin."""
    if name=='B0':
        long,short=direction_filters('G',f)
        return long,short,np.zeros(len(long),dtype=np.int64)
    q=lambda v:np.round(v,9)
    mfi,rv,phase=q(f['mfi']),q(f['rvol']),q(f['main_c'])
    flow_l=(mfi>=30)&(mfi<=80);flow_s=(mfi>=20)&(mfi<=70);volume=(rv>=.5)&(rv<=3)
    limit=50 if name=='T5' else 35
    phase_l=phase<=limit;phase_s=phase>=100-limit
    d,s=q(x['distance']),q(x['slope'])
    price_l=(d>=-.25)&(d<=1.25);price_s=(-d>=-.25)&(-d<=1.25)
    trend_l=(q(f['adx'])>=20)&(q(f['plus_di'])>q(f['minus_di']))
    trend_s=(q(f['adx'])>=20)&(q(f['minus_di'])>q(f['plus_di']))
    slope_l=s>0;slope_s=s<0
    age_l=(x['age_long']>=0)&(x['age_long']<=48);age_s=(x['age_short']>=0)&(x['age_short']<=48)
    affordable=q(x['atr_fee_ratio'])>=3
    hist=q(f['hist']);previous=np.r_[np.nan,hist[:-1]];mom_l=hist>previous;mom_s=hist<previous
    long=flow_l&volume&phase_l;short=flow_s&volume&phase_s
    if name!='T1':long&=price_l&affordable;short&=price_s&affordable
    if name in ('T3','T4','T5','T6'):long&=trend_l&slope_l;short&=trend_s&slope_s
    if name=='T4':long&=age_l;short&=age_s
    if name=='T6':long&=mom_l;short&=mom_s
    if name not in ENTRY_NAMES:raise ValueError('Unknown fixed entry hypothesis')
    # Bits 0..16 retain the old cross/position/price-stop contract. New
    # conditions get separate bits, so old MFI flags cannot overwrite them.
    bits=(131072*flow_l+262144*flow_s+524288*volume+1048576*phase_l+2097152*phase_s
          +4194304*price_l+8388608*price_s+16777216*trend_l+33554432*trend_s
          +67108864*slope_l+134217728*slope_s+268435456*age_l+536870912*age_s
          +1073741824*affordable+16384*mom_l+32768*mom_s)
    return long,short,bits


def cases(assets,timeframes=(1,3,5,15)):
    for asset in assets:
        binance,mexc=DATA_ROOTS[asset]
        minutes=load(binance/f'{asset}USDT-1m.csv',60)
        for venue in ['binance_um','mexc']:
            for tf in timeframes:
                if venue=='mexc' and tf not in (5,15):continue
                path=binance/f'{asset}USDT-1m.csv' if venue=='binance_um' else mexc/f'{asset}_USDT-Min{tf}.csv'
                b=resample(minutes,tf*60) if venue=='binance_um' else load(path,tf*60)
                take=(b.timestamp>=START)&(b.timestamp<END)
                if take.sum()!=(END-START)//b.seconds or b.timestamp[-1]+b.seconds!=END or (b.timestamp<START).sum()<200:raise ValueError('Incomplete native coverage or warmup')
                yield asset,venue,tf,b,path


def evaluate(b,f,x,cfg,start,end,*,cost='nominal'):
    # Trim future candles before journal replay: an unfinished training
    # position must never be valued using a later validation close.
    n=int(np.searchsorted(b.timestamp,end));bar=b.subset(np.arange(len(b.timestamp))<n)
    ff={k:v[:n] for k,v in f.items()};xx={k:v[:n] for k,v in x.items()}
    up,down=crosses(ff['main_c'],ff['signal_c']);long,short,bits=entry_gates(cfg['entry'],ff,xx)
    signals=dict(up=up,down=down,long_entry=up&ff['bull']&long,short_entry=down&ff['bear']&short)
    assumed=COSTS[cost]
    sim=simulate_risk(bar,up,down,ff['bull']&long,ff['bear']&short,xx,profile=cfg['risk'],start=start,end=end,fee=assumed['fee'])
    validate_alternating_crosses(up,down)
    raw=sim['trades']+([sim['open_position']] if sim['open_position'] else [])
    positions=[apply_policy(bar,t,'S2',fee=assumed['fee'],stop_slippage=assumed['stop_slippage']) for t in raw]
    stats,points=replay_selective(bar,positions,fee=assumed['fee'],initial=1000.,leverage=10.)
    return stats,positions,points,signals,bits,bar


def provenance(asset,venue,tf,path):
    return dict(asset=asset,venue=venue,timeframe_minutes=tf,path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def train(output):
    output.mkdir(parents=True,exist_ok=True);rows=[];sources=[]
    frozen=dict(configs=CONFIGS,costs=COSTS,targets=TARGETS,comparisons=COMPARISONS,
                selection_assets=['BTC','ETH'],selection_timeframes=[5,15],train_start=START,train_end=SPLIT,
                new_asset_validation=['BNB','SOL','XRP'],validation_start=SPLIT,validation_end=END,
                note='Existing assets/date history were previously observed. Later two months are retrospective time validation, not an unseen holdout. New assets are not inspected for strategy choice.',
                contract=frozen_contract(),entry_rules_source=inspect.getsource(entry_gates),
                rule='Select once on equal-weight BTC/ETH first4-month cases, then freeze before evaluating BNB/SOL/XRP performance.')
    (output/'fixed-hypotheses.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n')
    for asset,venue,tf,b,path in cases(['BTC','ETH'],(5,15)):
        f=build_features(b);x=extra_features(b,f,FEE);sources.append(provenance(asset,venue,tf,path))
        for cfg in CONFIGS:
            for cost in COSTS:
                stats,*_=evaluate(b,f,x,cfg,START,SPLIT,cost=cost)
                rows.append(dict(asset=asset,venue=venue,timeframe_minutes=tf,variant=cfg['id'],label=cfg['label'],cost=cost,**stats))
        print(f'Train complete: {asset} {venue} {tf}m',flush=True)
    scores=[]
    for cfg in CONFIGS:
        group=[r for r in rows if r['variant']==cfg['id']];nom=[r for r in group if r['cost']=='nominal'];stress=[r for r in group if r['cost']=='stress']
        sufficient=all(r['trades']>=30 for r in nom)
        positive=sum(r['avg_net_return_pct'] is not None and r['avg_net_return_pct']>0 and r['profit_factor'] is not None and r['profit_factor']>1 for r in nom)
        stress_positive=sum(r['avg_net_return_pct'] is not None and r['avg_net_return_pct']>0 and r['profit_factor'] is not None and r['profit_factor']>1 for r in stress)
        median_pf=float(np.median([r['profit_factor'] or 0 for r in nom]))
        median_seed=float(np.median([r['end_marked_equity_usdt'] for r in nom]))
        score=(int(sufficient),positive,stress_positive,median_pf,median_seed)
        scores.append(dict(variant=cfg['id'],label=cfg['label'],sufficient_samples=sufficient,positive_cases=positive,stress_positive_cases=stress_positive,median_pf=median_pf,median_seed=median_seed,score=list(score)))
    chosen=max(scores,key=lambda r:r['score']);cfg=next(c for c in CONFIGS if c['id']==chosen['variant'])
    selection=dict(chosen=cfg,training_score=chosen,qualified_training=chosen['sufficient_samples'] and chosen['positive_cases']>=6 and chosen['stress_positive_cases']>=5 and chosen['median_pf']>=1.1,
                   all_scores=scores,selection_rules='Sufficient >=30 trades each; positive-case count, stress positive-case count, medianPF, medianseed; cases equal weight. Qualification6/8 nominal,5/8 stress, medianPF>=1.1.',
                   contract=frozen_contract(),hypotheses_sha256=hashlib.sha256((output/'fixed-hypotheses.json').read_bytes()).hexdigest(),performance_of_new_assets_used_for_choice=False)
    (output/'selection-frozen.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2)+'\n')
    (output/'training.json').write_text(json.dumps(dict(rows=rows,sources=sources),ensure_ascii=False,indent=2)+'\n')
    write_csv(output/'training.csv',[{k:v for k,v in r.items() if not isinstance(v,(list,dict))} for r in rows])
    print('Frozen selection:',json.dumps(selection['chosen'],ensure_ascii=False),'qualified=',selection['qualified_training'],flush=True)


def validate(output):
    selection=verify_frozen(output);cfg=selection['chosen'];baseline=CONFIGS[0]
    rows=[];sources=[];journals=[]
    for asset,venue,tf,b,path in cases(TARGETS+COMPARISONS):
        f=build_features(b);x=extra_features(b,f,FEE);sources.append(provenance(asset,venue,tf,path))
        for variant in [baseline,cfg] if cfg['id']!='B0' else [baseline]:
            for segment,start,end in [('full',START,END),('first4',START,SPLIT),('last2',SPLIT,END)]:
                for cost in COSTS:
                    stats,positions,points,_,_,_=evaluate(b,f,x,variant,start,end,cost=cost)
                    rows.append(dict(asset=asset,role='target' if asset in TARGETS else 'comparison',venue=venue,timeframe_minutes=tf,variant=variant['id'],label=variant['label'],segment=segment,cost=cost,start_kst=kst(start),end_kst=kst(end),**stats))
                    if segment=='full' and cost=='nominal':
                        for p in points:journals.append(dict(asset=asset,venue=venue,timeframe_minutes=tf,variant=variant['id'],**{k:v for k,v in p.items() if k!='legs'}))
        print(f'Validation complete: {asset} {venue} {tf}m',flush=True)
    result=dict(selection=selection,targets=TARGETS,comparisons=COMPARISONS,start_kst=kst(START),end_kst=kst(END),rows=rows,sources=sources,
                costs=COSTS,accounts='Separate $1000 fullmargin10x accounts. No funding/fairprice liquidation/lot constraints. Stress adds .01%eachside to totalcost and .05%onS2stopfills.',
                limitations='Five high-cap coins and six months cannot establish a universal live trading indicator; crossasset results are correlated and target universe chosen retrospectively by current marketcap.')
    (output/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    write_csv(output/'validation.csv',[{k:v for k,v in r.items() if not isinstance(v,(dict,list))} for r in rows]);write_csv(output/'trades.csv',journals)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage',choices=['train','validate','all'],default='all');p.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-largecap-2026-10-14');a=p.parse_args()
    if a.stage in ('train','all'):train(a.output)
    if a.stage in ('validate','all'):validate(a.output)


if __name__=='__main__':main()
