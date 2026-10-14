#!/usr/bin/env python3
"""Report the fixed five-exit comparison and profit-retention constraint."""
import argparse
import csv
import json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from ppp_backtest import ROOT

LABELS={'S0':'기존 전액 10배','S1':'항상 1.5% 전량 손절','S2':'첫 봉 1% 전량 손절',
        'S3':'첫 봉 1.5% 전량 손절','S4':'첫 봉 1% 절반 손절','S5':'첫 두 봉 신호 범위 종가 손절'}

def f(v,n=2):return '—' if v is None else f'{v:,.{n}f}'
def yes(v):return '예' if v else '아니오'


def drawdown_diagnostic(output):
    baseline=[];s3={}
    with (output/'trades.csv').open() as handle:
        for r in csv.DictReader(handle):
            if (r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'])!=('mexc','ZEC_USDT','5','G','R2') or float(r['stop_slippage'])!=0:continue
            if r['policy']=='S0':baseline.append(r)
            elif r['policy']=='S3':s3[int(r['entry_time'])]=r['stop_triggered']=='True'
    c=np.r_[1000.,[float(r['closed_cash_usdt']) for r in baseline]]
    z=int(np.argmax(1-c/np.maximum.accumulate(c)));a=int(np.argmax(c[:z+1]));window=baseline[a:z]
    result=dict(peak_time=datetime.fromtimestamp(int(baseline[a-1]['exit_time']),timezone.utc).isoformat() if a else 'initial',
        trough_time=datetime.fromtimestamp(int(baseline[z-1]['exit_time']),timezone.utc).isoformat(),
        peak_cash=float(c[a]),trough_cash=float(c[z]),closed_drawdown_pct=float((1-c[z]/c[a])*100),
        trades=len(window),losses=sum(float(r['unit_net_return'])<0 for r in window),
        s3_stops_in_interval=sum(s3[int(r['entry_time'])] for r in window))
    (output/'largest-drawdown-diagnostic.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def render(output):
    payload=json.loads((output/'results.json').read_text());rows=payload['summaries']
    primary=[r for r in rows if (r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'])==('mexc','ZEC_USDT',5,'G','R2')]
    idx={(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'],r['policy'],r['stop_slippage']):r for r in rows}
    zero={r['policy']:r for r in primary if r['stop_slippage']==0}
    stress={r['policy']:r for r in primary if r['stop_slippage']==.0005}
    base=zero['S0'];minimum=1000+.8*(base['end_marked_equity_usdt']-1000)
    robust=[r for r in primary if r['stop_slippage']==0 and r['qualified'] and stress[r['policy']]['qualified']]
    robust.sort(key=lambda r:(r['ohlc_drawdown_upper_bound_pct'],-r['end_marked_equity_usdt']))
    lines=['# 전액 10배를 유지한 선별 손실 청산 백테스트','',
        '**진입 크기는 전액 10배로 유지**하고, 손실이 진행되는 일부 거래를 추가 청산하는 다섯 방식을 비교했다. '
        '각 조합은 $1,000에서 시작한 독립 계좌이며 출금·추가 입금 없이 실제 순손익을 시간순으로 재투자한다. '
        'SMA20/50/100/200 정배열 롱·역배열 숏 조건과 기존 C/E/G 지표 진입 필터를 모두 유지했다.','',
        f'총 **{len(rows):,}개 비교**: 고정 5개 추가 청산과 기준 S0 × 손절 슬리피지 0%/0.05%. '
        f'완결 거래 기록 {payload["trades_written"]:,}행을 저장했다. '
        '편도 수수료는 모든 거래 0.02%. 가격 손절은 봉 안에서 체결되고 S5의 종가 판단은 다음 시가에 체결된다.','',
        'Binance BTC/ETH/ZEC 1·3·5·15분은 KST 2026-04-14 00:00부터 2026-10-14 00:00 직전까지의 6개월이다. '
        'MEXC 5·15분도 같은 6개월이며, MEXC 1·3분은 KST 2026-09-14 13:15 이후의 짧은 자료로 별도 표시한다. '
        '전체 비교 중 6개월은 1,080개, MEXC 짧은 기간은 360개다. C는 R0/R4, E는 R0, G는 R0/R2를 비교했다.','',
        '## 핵심 결과: MEXC ZEC 5분 G + SMA50','',
        f'기존 종료 잔고는 **${f(base["end_marked_equity_usdt"])}**다. '
        f'기존 **순이익** 80% 보존의 하한은 **${f(minimum)}**다. '
        '잔고 80%를 비교하는 기준이 아니다. 기준 순이익이 양수일 때만 이 조건을 정의한다.','',
        '| 방식 | 승률 % | 손익비 | 종료 자산 $ | 기존 순이익 유지 % | 폐쇄 낙폭 % | OHLC 낙폭 상한 % | 합격 |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for policy in LABELS:
        r=zero[policy]
        lines.append(f'| {policy} {LABELS[policy]} | {f(r["win_rate_pct"])} | {f(r["payoff_ratio"],3)} | {f(r["end_marked_equity_usdt"])} | '
            f'{f(r["baseline_profit_retention"]*100 if r["baseline_profit_retention"] is not None else None)} | '
            f'{f(r["closed_drawdown_pct"])} | {f(r["ohlc_drawdown_upper_bound_pct"])} | {yes(r["qualified"]) if policy!="S0" else "기준"} |')
    lines+=['',
        '합격은 **순이익 80% 이상 보존 + 폐쇄 낙폭 감소 + OHLC 낙폭 상한 감소 + 거래가격 평가자산 0 이하 접촉 없음**을 모두 요구한다. '
        'OHLC 상한은 봉 내부 고·저점 순서를 알 수 없어 보수적으로 산정한 값이며 실제 낙폭 확정값이 아니다.','']
    if robust:
        best=robust[0];s=stress[best['policy']]
        lines+=[f'두 비용 시나리오를 모두 통과한 비교 후보 중 OHLC 낙폭 상한이 가장 낮은 것은 **{best["policy"]} {LABELS[best["policy"]]}**다. '
            f'종료 자산 ${f(best["end_marked_equity_usdt"])} / 손절 0.05% 추가 슬리피지 시 ${f(s["end_marked_equity_usdt"])}. '
            '이는 해당 과거 표본의 후보 선택이며 다른 코인·주기에서 같은 개선을 보장하는 최종 실거래 전략이 아니다.','']
    else:
        lines+=['**MEXC ZEC 5분 G/R2에서는 두 비용 시나리오 모두에서 위 조건을 통과한 후보가 없다.** 잔고를 크게 포기하면서 낙폭만 줄인 결과를 합격으로 처리하지 않았다.','']
        unchanged_or_better=[r for r in zero.values() if r['policy']!='S0'
            and r['closed_drawdown_pct']<=base['closed_drawdown_pct']+1e-9
            and r['ohlc_drawdown_upper_bound_pct']<base['ohlc_drawdown_upper_bound_pct']-1e-9
            and r['baseline_profit_retention']>=.8]
        if unchanged_or_better:
            closest=max(unchanged_or_better,key=lambda r:r['end_marked_equity_usdt']);s=stress[closest['policy']]
            lines+=[f'조건에 가까운 비교 후보는 **{closest["policy"]} {LABELS[closest["policy"]]}**다. '
                f'종료 자산 ${f(closest["end_marked_equity_usdt"])}로 수익을 보존·확대했고, '
                f'OHLC 낙폭 상한은 {f(base["ohlc_drawdown_upper_bound_pct"])}% → {f(closest["ohlc_drawdown_upper_bound_pct"])}%다. '
                f'**폐쇄 최대 낙폭은 {f(closest["closed_drawdown_pct"])}%로 줄지 않았다.** '
                f'손절 0.05% 추가 슬리피지 시 종료 자산은 ${f(s["end_marked_equity_usdt"])}다. '
                '손실만 완전히 골라 제거한 결과가 아니며 이 과거 표본에서의 작은 개선으로 해석한다.','']
    lines+=['### 손절 체결에만 추가 0.05% 슬리피지','',
        '| 방식 | 종료 자산 $ | 순이익 유지 % | 승률 % | 손익비 | 폐쇄 낙폭 % | OHLC 상한 % | 합격 |',
        '|---|---:|---:|---:|---:|---:|---:|---|']
    for policy in LABELS:
        r=stress[policy]
        lines.append(f'| {policy} | {f(r["end_marked_equity_usdt"])} | {f(r["baseline_profit_retention"]*100)} | '
            f'{f(r["win_rate_pct"])} | {f(r["payoff_ratio"],3)} | {f(r["closed_drawdown_pct"])} | '
            f'{f(r["ohlc_drawdown_upper_bound_pct"])} | {yes(r["qualified"]) if policy!="S0" else "기준"} |')
    lines+=['','### 기존 승자와 패자는 어떻게 바뀌었나','',
        '아래는 추가 슬리피지 없는 기준이다. 기존 패자의 손실을 줄인 경우와 오히려 더 큰 손실에 청산한 경우를 나눴다. '
        '봉 중간에 크게 역행한 뒤 회복했던 거래는 손절을 추가하면 최종 손실이 늘 수도 있다. '
        '절반 청산도 원래 한 거래로 집계하며 승률은 전체 청산이 끝난 거래만 대상으로 한다.','',
        '| 방식 | 거래 | 추가 청산 거래 | 기존 승자 접촉 | 승자→패자 | 기존 패자 접촉 | 패자 개선 | 패자 악화 | 최악 계좌 거래 % |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for policy in LABELS:
        r=zero[policy]
        worst=r['worst_trade_pct']*10/1.002 if r['worst_trade_pct'] is not None else None
        lines.append(f'| {policy} | {r["trades"]} | {r["stopped_trades"]} | {r["original_winners_touched"]} | '
            f'{r["original_winners_now_loss"]} | {r["original_losers_touched"]} | {r["original_losers_improved"]} | '
            f'{r["original_losers_worsened"]} | {f(worst)} |')
    diagnostic=drawdown_diagnostic(output)
    lines+=['','### 큰 개별 손실을 줄여도 최대 낙폭이 남는 이유','',
        f'기준 폐쇄 잔고의 최대 낙폭 구간은 UTC {diagnostic["peak_time"]}부터 {diagnostic["trough_time"]}까지다. '
        f'잔고 ${f(diagnostic["peak_cash"])} → ${f(diagnostic["trough_cash"])}이며, '
        f'{diagnostic["trades"]}거래 중 {diagnostic["losses"]}거래가 순손실이다. '
        f'이 구간에서 S3 첫 봉 1.5% 손절은 **{diagnostic["s3_stops_in_interval"]}번** 발생했다. '
        '따라서 가장 큰 개별 손실을 줄여 전체 잔고가 늘어도, 여러 손실이 누적된 이 구간의 낙폭 비율은 그대로 남는다. '
        '[최대 낙폭 구간 진단](largest-drawdown-diagnostic.json).','']
    lines+=['','## 이번 청산 방식','',
        '| 코드 | 고정한 규칙 |','|---|---|',
        '| S0 | 기존 청산만 유지 |',
        '| S1 | 실제 진입가에서 1.5% 역행하면 보유 내내 전량 손절 |',
        '| S2 | 실제 진입 봉에서만 1% 역행에 전량 손절 |',
        '| S3 | 실제 진입 봉에서만 1.5% 역행에 전량 손절 |',
        '| S4 | 실제 진입 봉에서만 1% 역행에 최초 수량 절반 청산, 남은 수량은 기존 청산 |',
        '| S5 | 최초 두 보유 봉 종가가 진입 전 신호 봉 저점(롱)/고점(숏)을 넘어서면 다음 시가 청산 |','',
        'S2–S4는 진입 봉이 끝나면 취소한다. 모든 추가 청산 후 재진입은 이후 새 지표 교차가 있을 때만 허용한다. '
        'S4는 남은 수량이 모두 청산되기 전까지 추가 진입하지 않는다. '
        'S5는 진입 전 이미 확정된 신호 봉 범위를 사용한다. 익절·추적 익절은 추가하지 않았다.','',
        '손절가는 가격 역행 기준이며 수수료 후 계좌 손실 한도가 아니다. 1.5% 가격 역행은 전액 10배 계좌에서 '
        '대략 15% 이상 손실이 된다. 갭으로 손절가를 넘으면 더 불리한 시가로 체결하고, 0.05% 시나리오는 여기에 '
        '추가 슬리피지를 적용한다. [TradingView 공식 체결 모형](https://www.tradingview.com/pine-script-docs/concepts/strategies/).','',
        '## 거래소와 시기별 재현성','',
        '아래는 같은 ZEC 5분 G/R2 후보의 거래소별 6개월과 앞 4개월·뒤 2개월 비교다. '
        '두 구간은 각각 $1,000에서 시작하고, 구간 경계 포지션은 이월하지 않는다. '
        '이미 전체 이력을 살펴본 사후 연구이므로 뒤 2개월은 미관측 홀드아웃이 아니다.','',
        '| 거래소 | 방식 | 손절 슬립 % | 전체 잔고 $ | 앞 4개월 $ | 뒤 2개월 $ | 뒤 2개월 OHLC 상한 % | 합격 |',
        '|---|---|---:|---:|---:|---:|---:|---|']
    for r in rows:
        if r['symbol'] not in ('ZECUSDT','ZEC_USDT') or r['timeframe_minutes']!=5 or r['model']!='G' or r['profile']!='R2':continue
        a=r['temporal_segments']['first_four_months'];b=r['temporal_segments']['last_two_months']
        lines.append(f'| {r["venue"]} | {r["policy"]} | {f(r["stop_slippage"]*100)} | {f(r["end_marked_equity_usdt"])} | '
            f'{f(a["end_marked_equity_usdt"])} | {f(b["end_marked_equity_usdt"])} | {f(b["ohlc_drawdown_upper_bound_pct"])} | '
            f'{yes(r["qualified"]) if r["policy"]!="S0" else "기준"} |')
    recent_base=zero['S0']['temporal_segments']['last_two_months']
    recent_s3=zero['S3']['temporal_segments']['last_two_months']
    lines+=['',f'MEXC G/R2의 S3를 뒤 2개월에만 적용하면 종료 자산 ${f(recent_s3["end_marked_equity_usdt"])} '
        f'(기준 ${f(recent_base["end_marked_equity_usdt"])})이며, OHLC 상한은 '
        f'{f(recent_s3["ohlc_drawdown_upper_bound_pct"])}% (기준 {f(recent_base["ohlc_drawdown_upper_bound_pct"])}%)다. '
        '**전체 6개월의 개선이 뒤 2개월에 재현되지는 않았다.**','',
        '## 같은 MEXC ZEC 5분에서 C/E/G 비교','',
        'G의 합격 여부와 다른 모델의 합격 여부는 구분한다. 아래는 전체 6개월이며 S0·S2·S3·S4를 보여준다. '
        '낙폭이 약 80–90%인 결과는 합격 여부와 별개로 절대 손실 수준이 여전히 크다.','',
        '| 모델·기존 청산 | 방식 | 손절 슬립 % | 종료 자산 $ | 승률 % | 손익비 | 폐쇄 낙폭 % | OHLC 상한 % | 합격 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---|']
    for r in rows:
        if (r['venue'],r['symbol'],r['timeframe_minutes'])!=('mexc','ZEC_USDT',5):continue
        if (r['model'],r['profile']) not in (('C','R4'),('E','R0'),('G','R2')) or r['policy'] not in ('S0','S2','S3','S4'):continue
        lines.append(f'| {r["model"]}/{r["profile"]} | {r["policy"]} | {f(r["stop_slippage"]*100)} | '
            f'{f(r["end_marked_equity_usdt"])} | {f(r["win_rate_pct"])} | {f(r["payoff_ratio"],3)} | '
            f'{f(r["closed_drawdown_pct"])} | {f(r["ohlc_drawdown_upper_bound_pct"])} | {yes(r["qualified"]) if r["policy"]!="S0" else "기준"} |')
    lines+=['','## C/E/G와 ETH도 같은 방식으로 비교','',
        'BTC·ETH·ZEC 각각 1·3·5·15분을 모두 계산했다. 아래 집계는 6개월 90개 기준 조합에 대한 것으로, '
        '겹치는 자산·주기·청산 결과를 독립적인 성공 확률로 해석하지 않는다. '
        '원래 손실인 전략에는 순이익 유지율을 정의하지 않으며 잔고 보존과 수익 창출을 구분한다.','',
        '| 방식 | 손절 슬립 % | 잔고 $1,000 초과 | 두 낙폭 모두 감소 | 80% 유지·낙폭 합격 | 잔고 중앙값 $ |',
        '|---|---:|---:|---:|---:|---:|']
    for slip in (0.,.0005):
        for policy in LABELS:
            group=[r for r in rows if r['six_months'] and r['policy']==policy and r['stop_slippage']==slip]
            lower=0
            for r in group:
                b=idx[(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'],'S0',slip)]
                lower+=r['closed_drawdown_pct']<b['closed_drawdown_pct']-1e-9 and r['ohlc_drawdown_upper_bound_pct']<b['ohlc_drawdown_upper_bound_pct']-1e-9
            lines.append(f'| {policy} | {f(slip*100)} | {sum(r["end_marked_equity_usdt"]>1000 for r in group)}/{len(group)} | '
                f'{lower}/{len(group)} | {sum(r["qualified"] for r in group)}/{len(group)} | '
                f'{f(float(np.median([r["end_marked_equity_usdt"] for r in group])))} |')
    eth=[r for r in rows if r['six_months'] and r['symbol'].startswith('ETH')]
    lines+=['',f'ETH의 6개월 비교 {len(eth)}개 중 종료 자산 $1,000 초과는 {sum(r["end_marked_equity_usdt"]>1000 for r in eth)}개다. '
        '규칙이 일부 ZEC 결과에서 개선돼도 ETH 전반에 일반화되는지 별도로 확인해야 한다.','',
        '## 전체 상세 결과','',
        '손익비는 평균 순이익률 / 평균 순손실률의 절댓값이며 PF와 다른 수치다. '
        '종료 자산은 미청산 잔여 포지션의 실제 수수료와 종가 평가손익을 포함한다. '
        '폐쇄 잔고·실제 완결 거래만 승률과 폐쇄 낙폭에 반영한다. 각 계좌는 별도이며 합산 포트폴리오가 아니다.','']
    for venue,title in [('binance_um','Binance 전체 6개월'),('mexc','MEXC 5/15분 6개월 · 1/3분 짧은 기간')]:
        lines+=['### '+title,'']
        for symbol in sorted({r['symbol'] for r in rows if r['venue']==venue}):
            for tf in (1,3,5,15):
                group=[r for r in rows if r['venue']==venue and r['symbol']==symbol and r['timeframe_minutes']==tf]
                lines += [f'#### {symbol} {tf}분','',f'UTC 시작 {group[0]["start_utc"]}; 6개월: {yes(group[0]["six_months"])}.','',
                    '| 모델 | 기존 청산 | 방식 | 슬립 % | 승률 % | 손익비 | 종료 자산 $ | 순이익 유지 % | 폐쇄 낙폭 % | OHLC 상한 % | 합격 |',
                    '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
                for r in group:
                    retention=r['baseline_profit_retention']*100 if r['baseline_profit_retention'] is not None else None
                    lines.append(f'| {r["model"]} | {r["profile"]} | {r["policy"]} | {f(r["stop_slippage"]*100)} | '
                        f'{f(r["win_rate_pct"])} | {f(r["payoff_ratio"],3)} | {f(r["end_marked_equity_usdt"])} | {f(retention)} | '
                        f'{f(r["closed_drawdown_pct"])} | {f(r["ohlc_drawdown_upper_bound_pct"])} | {yes(r["qualified"]) if r["policy"]!="S0" else "기준"} |')
                lines.append('')
    lines+=['## 계산상 한계와 재현','',
        '전액 10배 진입의 모든 120개 기준 조합이 직전 복리 잔고·폐쇄 낙폭과 동일함을 검사했다. '
        '새 추가 청산은 앞으로 알 수 있는 가격 수준·종가만 사용하며 이전 승패를 미리 보고 적용하지 않았다. '
        '교차 방향이 실제 24개 전체 데이터에서 번갈아 발생함을 확인한 경우에만 기존 진입 저널을 재생한다. '
        '다른 데이터에 연속 같은 방향 교차가 있으면 실행을 거부한다.','',
        '봉 내부 시각은 정확히 알 수 없어 손절 봉 시작 시각과 이용 가능 시각을 둘 다 기록한다. '
        'OHLC 상한은 가능한 유리한 극값→손절 순서로 계산하며 전량 손절 뒤의 고·저점은 제외한다. '
        '절반 손절 후에는 나머지 수량의 실제 고·저점 노출이 남는다. '
        '원래 시가 청산은 해당 봉의 이후 고·저점을 사용하지 않는다.','',
        '수수료와 손절 추가 슬리피지 이외에 펀딩·유동성·공정가격 기반 강제청산·유지증거금·최소 주문량·수량 한도는 제외했다. '
        '거래가격 평가자산 0 이하 접촉은 별도 기록하며 실제 강제청산 횟수가 아니다. '
        '이런 접촉이 있는 가상 경로를 실제로 지속 가능한 계좌 수익으로 해석하지 않는다. '
        '[MEXC 공식 강제청산 설명](https://www.mexc.com/support/article/faq-on-liquidation-for-futures-trading-8123281969561).','',
        '[전체 숫자 CSV](summary.csv) · [청산별 수량·수수료 재계산용 거래 기록](trades.csv) · '
        '[조건·구간별 숫자·입력 해시](results.json) · [검증 기록](test-verification.txt)','',
        '실행 코드: scripts/ppp_selective_backtest.py, scripts/ppp_selective_report.py. '
        '방법론: docs/strategy-notes/ppp-selective-loss-controls.md.','']
    (output/'report.ko.md').write_text('\n'.join(lines))
    print(f'Wrote selective report: {len(rows)} detailed scenarios; primary robust candidates {[r["policy"] for r in robust]}')


def plot(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as md
    rows=json.loads((output/'results.json').read_text())['summaries']
    fig,axes=plt.subplots(1,3,figsize=(15,4.8))
    colors=dict(zip(LABELS,plt.cm.tab10.colors))
    for ax,(model,profile) in zip(axes,[('C','R4'),('E','R0'),('G','R2')]):
        for r in rows:
            if (r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'])!=('mexc','ZEC_USDT',5,model,profile):continue
            ax.scatter(r['ohlc_drawdown_upper_bound_pct'],r['end_marked_equity_usdt'],s=65 if r['stop_slippage']==0 else 35,
                color=colors[r['policy']],marker='o' if r['stop_slippage']==0 else 'x')
            if r['stop_slippage']==0:ax.annotate(r['policy'],(r['ohlc_drawdown_upper_bound_pct'],r['end_marked_equity_usdt']),xytext=(4,4),textcoords='offset points',fontsize=8)
        ax.set_yscale('log');ax.axhline(1000,color='gray',linestyle='--',linewidth=.8)
        ax.set_title(f'MEXC ZEC 5m {model}/{profile}');ax.set_xlabel('OHLC drawdown upper bound (%)');ax.set_ylabel('Final equity (USDT, log)');ax.grid(alpha=.2)
    fig.suptitle('Selective exits with full-account 10x entries\n6 months; $1,000 initial; circle: fees only / cross: stops +5bp slippage')
    fig.tight_layout();fig.savefig(output/'selective-comparison.png',dpi=160);plt.close(fig)
    curves={p:[] for p in LABELS}
    with (output/'trades.csv').open() as handle:
        for r in csv.DictReader(handle):
            if (r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'])==('mexc','ZEC_USDT','5','G','R2') and float(r['stop_slippage'])==0:
                curves[r['policy']].append((int(r['exit_available_time']),float(r['closed_cash_usdt'])))
    start=datetime(2026,4,13,15,tzinfo=timezone.utc)
    fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True)
    for policy,pts in curves.items():
        dates=[start]+[datetime.fromtimestamp(t,timezone.utc) for t,c in pts];cash=np.r_[1000.,[c for t,c in pts]]
        axes[0].step(dates,cash,where='post',label=policy,color=colors[policy],linewidth=1.3)
        axes[1].step(dates,100*(1-cash/np.maximum.accumulate(cash)),where='post',label=policy,color=colors[policy],linewidth=1.2)
    axes[0].set_yscale('log');axes[0].set_ylabel('Closed equity (USDT, log)');axes[0].legend(ncol=6)
    axes[1].set_ylabel('Closed-trade drawdown (%)');axes[1].invert_yaxis();axes[1].xaxis.set_major_formatter(md.DateFormatter('%b %d'));axes[1].set_xlabel('2026 date (UTC)')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('MEXC ZEC 5m G/SMA50: selective loss exits\nFull-account 10x retained; fees included; liquidation/funding excluded')
    fig.tight_layout();fig.savefig(output/'selective-curves-zec5m.png',dpi=160);plt.close(fig)
    print('Wrote both selective-study charts')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-selective-2026-10-14')
    p.add_argument('--plots',action='store_true')
    a=p.parse_args();render(a.output)
    if a.plots:plot(a.output)
