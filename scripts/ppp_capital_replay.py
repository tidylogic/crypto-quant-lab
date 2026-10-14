#!/usr/bin/env python3
"""Hypothetical full-margin cash replay; NOT an exchange liquidation simulator."""
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ppp_backtest import ROOT
from ppp_combo_backtest import dataset_cases


def replay(bars, trades, *, open_position=None, fee=.0002, initial=1000., leverage=10.):
    if initial<=0 or leverage<=0 or not 0<=fee<1:
        raise ValueError('Invalid capital, leverage or fee')
    cash=initial; peak=initial; dd_bound=0.; zero_events=0; first_zero=None
    last_exit=-1; points=[]; curve=[initial]; max_mae=0.

    def excursion(t, notional, account):
        nonlocal peak,dd_bound,zero_events,first_zero,max_mae
        a=int(np.searchsorted(bars.timestamp,t['entry_time']))
        z=int(np.searchsorted(bars.timestamp,t.get('exit_time',int(bars.timestamp[-1])+bars.seconds)))
        if a>=z or a==len(bars.timestamp) or int(bars.timestamp[a])!=t['entry_time']:
            raise ValueError('Position timestamps do not match candles')
        d=1 if t['side']=='long' else -1; p=t['entry_price']
        favorable=bars.high[a:z] if d==1 else bars.low[a:z]
        adverse=bars.low[a:z] if d==1 else bars.high[a:z]
        times=bars.timestamp[a:z]
        if 'exit_price' in t:
            # The actual exit-open gap belongs to this trade, later wicks do not.
            favorable=np.r_[favorable,t['exit_price']]
            adverse=np.r_[adverse,t['exit_price']]
            times=np.r_[times,t['exit_time']]
        high_equity=account-notional*fee+notional*d*(favorable/p-1)
        low_equity=account-notional*fee+notional*d*(adverse/p-1)
        # High then low is the pessimistic ordering for an unknown OHLC bar path.
        peaks=np.maximum.accumulate(np.r_[peak,high_equity])[1:]
        dd_bound=max(dd_bound,float(np.max((peaks-np.maximum(low_equity,0))/peaks)))
        peak=max(peak,float(high_equity.max()))
        if (low_equity<=0).any():
            zero_events+=1
            if first_zero is None:
                first_zero=int(times[np.flatnonzero(low_equity<=0)[0]])
        max_mae=max(max_mae,float(np.maximum(-d*(adverse/p-1),0).max()))

    for t in trades:
        if t['entry_time']<last_exit or t['exit_time']<=t['entry_time']:
            raise ValueError('Unordered or overlapping full-margin positions')
        last_exit=t['exit_time']
        if cash<=0:
            break
        # Initial margin plus entry fee must fit the available account cash.
        notional=cash*leverage/(1+leverage*fee)
        excursion(t,notional,cash)
        d=1 if t['side']=='long' else -1
        ratio=t['exit_price']/t['entry_price']
        net=d*(ratio-1)-fee*(1+ratio)
        cash=max(0.,cash+notional*net)
        peak=max(peak,cash)
        dd_bound=max(dd_bound,1-cash/peak)
        curve.append(cash)
        points.append(dict(entry_time=t['entry_time'],exit_time=t['exit_time'],
                           entry_notional=notional,closed_cash_usdt=cash))
    marked=cash
    if open_position is not None and cash>0:
        if open_position['entry_time']<last_exit:
            raise ValueError('Final open position overlaps a closed position')
        notional=cash*leverage/(1+leverage*fee)
        excursion(open_position,notional,cash)
        d=1 if open_position['side']=='long' else -1
        marked=cash-notional*fee+notional*d*(bars.close[-1]/open_position['entry_price']-1)
        dd_bound=max(dd_bound,1-max(marked,0)/peak)
    c=np.array(curve)
    dd=float(np.max(1-c/np.maximum.accumulate(c))*100)
    return dict(closed_cash_usdt=cash,end_marked_equity_usdt=marked,
                closed_drawdown_pct=dd,ohlc_drawdown_upper_bound_pct=dd_bound*100,
                price_zero_equity_events=zero_events,first_price_zero_equity_time=first_zero,
                maximum_adverse_price_pct=max_mae*100,
                minimum_closed_cash_usdt=float(c.min()),maximum_closed_cash_usdt=float(c.max()),
                closed_trades_processed=len(points)),points


def run(output, initial=1000., leverage=10.):
    payload=json.loads((output/'results.json').read_text())
    groups=defaultdict(list)
    with (output/'trades.csv').open() as handle:
        for raw in csv.DictReader(handle):
            key=(raw['venue'],raw['symbol'],int(raw['timeframe_minutes']),raw['model'],raw['profile'])
            groups[key].append(dict(side=raw['side'],entry_time=int(raw['entry_time']),exit_time=int(raw['exit_time']),
                                    entry_price=float(raw['entry_price']),exit_price=float(raw['exit_price'])))
    bars_lookup={(v,s,tf):b for v,s,tf,b,*_ in dataset_cases(payload.get('assets',('BTC','ZEC')))}
    summaries=[];selected=[]
    examples={('mexc','ZEC_USDT',5,'C','R4'),('mexc','ZEC_USDT',5,'E','R0'),('mexc','ZEC_USDT',5,'G','R2')}
    for r in payload['summaries']:
        key=(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'])
        summary,points=replay(bars_lookup[key[:3]],groups[key],open_position=r['open_position'],
                              fee=payload['fee_each_side'],initial=initial,leverage=leverage)
        summaries.append(dict(venue=key[0],symbol=key[1],timeframe_minutes=key[2],model=key[3],profile=key[4],
                              six_months=r['six_months'],**summary))
        if key in examples:
            selected.extend(dict(model=key[3],profile=key[4],**p) for p in points)
    result=dict(initial_cash_usdt=initial,leverage=leverage,margin_allocation='100% less entry fee reserve',
                entry_notional='cash*leverage/(1+leverage*fee)',fee_each_side=payload['fee_each_side'],
                accounts='Each asset/timeframe/model/profile starts with an independent account; not a shared portfolio',
                marked_equity='Final open position: entry fee and mark-to-last-close PNL included, no fictional exit fee',
                liquidation='Not simulated: historical fair prices, margin tiers, liquidation fees and rules unavailable',
                zero_equity='Last-price OHLC screen only. A touch invalidates continuation as a live account; not an actual liquidation count',
                drawdown='Closed-trade DD and pessimistic last-price OHLC DD bound; within-bar high/low order is unknown',
                excluded='Funding, slippage, order size/lot constraints, liquidity and liquidation',
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                input_sha256={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ('results.json','trades.csv')},
                summaries=summaries)
    (output/'capital-10x.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    for filename,records in [('capital-10x.csv',summaries),('capital-zec5m-curves.csv',selected)]:
        if records:
            with (output/filename).open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
    lines=['# 초기 $1,000 · 10배 · 전액 재투자 모형','',
           '각 전략을 **별도 계좌**로 평가한다. 매 진입마다 현재 잔고에서 진입 수수료를 확보하고 나머지 전액을 증거금으로 사용한다. '
           '종료된 거래의 실제 순손익을 시간순으로 복리 적용하며, 평균 수익률에 거래 수를 곱하지 않는다. 출금·추가 입금은 없다.','',
           '기본 편도 수수료 0.02%. 초기 주문 명목가치 = `1000 × 10 / (1 + 10 × 0.0002)` = $9,980.04. '
           '10배 선택만으로 전액 포지션을 의미하는 것은 아니지만, 이번 표는 전액 사용을 명시적으로 가정한다.','',
           '**실제 강제청산을 재현한 잔고가 아니다.** MEXC 강제청산은 공정가격과 유지증거금·청산 수수료로 판정되므로 '
           '거래가격 OHLC만으로 확정할 수 없다. [MEXC 공식 설명](https://www.mexc.com/support/article/faq-on-liquidation-for-futures-trading-8123281969561). '
           '펀딩·슬리피지·최소 주문 및 계약 수량 한도도 제외한 이론 모형이다.','',
           '폐쇄 잔고는 종료된 거래만, 종료 평가자산은 최종 미청산 포지션의 진입 수수료와 평가손익까지 포함한다. '
           'OHLC 낙폭 상한은 각 봉의 유리한 극값이 불리한 극값보다 먼저 나온 것으로 보는 보수적 추정이며 정확한 봉 내부 경로는 아니다. '
           '가격 평가자산 0 이하 접촉이 있으면 그 뒤 수익을 실제 계좌에서 지속할 수 있다고 해석해서는 안 된다.','',
           '## 직전 MEXC ZEC 5분 비교 방식','',
           '| 모델 | 방식 | 폐쇄 잔고 $ | 종료 평가자산 $ | 폐쇄 최대 낙폭 % | OHLC 낙폭 상한 % | 최대 가격 역행 % |',
           '|---|---|---:|---:|---:|---:|---:|']
    for r in summaries:
        key=(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'])
        if key in examples:
            lines.append(f'| {r["model"]} | {r["profile"]} | {r["closed_cash_usdt"]:,.2f} | {r["end_marked_equity_usdt"]:,.2f} | '
                         f'{r["closed_drawdown_pct"]:.2f} | {r["ohlc_drawdown_upper_bound_pct"]:.2f} | {r["maximum_adverse_price_pct"]:.2f} |')
    lines+=['','## 전체 모형 결과','',
            '| 거래소 | 자산 | 분 | 모델 | 방식 | 6개월 | 종료 평가자산 $ | 폐쇄 낙폭 % | OHLC 낙폭 상한 % | 가격 평가자산 0 접촉 거래 |',
            '|---|---|---:|---|---|---|---:|---:|---:|---:|']
    for r in summaries:
        lines.append(f'| {r["venue"]} | {r["symbol"]} | {r["timeframe_minutes"]} | {r["model"]} | {r["profile"]} | '
                     f'{"예" if r["six_months"] else "아니오"} | {r["end_marked_equity_usdt"]:,.2f} | {r["closed_drawdown_pct"]:.2f} | '
                     f'{r["ohlc_drawdown_upper_bound_pct"]:.2f} | {r["price_zero_equity_events"]} |')
    lines+=['','[전체 숫자 CSV](capital-10x.csv) · [계산 조건 JSON](capital-10x.json) · [ZEC 5분 폐쇄 잔고 경로](capital-zec5m-curves.csv)','']
    (output/'capital-10x.ko.md').write_text('\n'.join(lines))
    print(f'Capital replay completed: {len(summaries)} independent scenarios')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-risk-eth-2026-10-14')
    parser.add_argument('--initial',type=float,default=1000.)
    parser.add_argument('--leverage',type=float,default=10.)
    a=parser.parse_args();run(a.output,a.initial,a.leverage)
