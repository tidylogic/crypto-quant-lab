#!/usr/bin/env python3
"""Summarize fixed drawdown-control tradeoffs without fitting parameters."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np
from ppp_backtest import ROOT

LABELS={'Q0':'전액','Q1':'50% 배정','Q2':'25% 배정','Q3':'ATR 크기 조절',
        'Q4':'ATR + 2연패 6봉 대기','Q5':'ATR + 낙폭별 축소','Q6':'ATR + 연패 대기 + 낙폭 축소'}


def f(v,n=2):return '—' if v is None else f'{v:,.{n}f}'


def render(output):
    payload=json.loads((output/'results.json').read_text());rows=payload['summaries']
    selected={(r['model'],r['profile'],r['policy']):r for r in rows if r['venue']=='mexc' and r['symbol']=='ZEC_USDT' and r['timeframe_minutes']==5}
    lines=['# 낙폭·손실 최적화 백테스트','',
        '**계약 레버리지 10배는 유지하고 계좌 노출을 조절**했다. 각 조합은 $1,000의 독립 계좌로 시작하고, '
        '편도 수수료 0.02%, 출금·추가 입금 없이 재투자한다. SMA 정·역배열과 기존 모델 필터는 유지한다.','',
        f'BTC/ETH/ZEC, 1·3·5·15분의 **{len(rows)}개 비교**다. Binance 6개월 420개, MEXC 5·15분 6개월 210개, '
        'MEXC 1·3분 짧은 기간 210개를 구분했다. KST 2026-04-14 00:00–2026-10-14 00:00 직전. '
        'C는 R0/R4, E는 R0, G는 R0/R2 청산을 비교해 리스크 없는 경우도 포함했다.','',
        '## 핵심 결과: MEXC ZEC 5분봉 G + SMA50','',
        '성과가 좋았던 기존 G/R2에 모든 방식을 적용했다. 아래 낙폭은 반드시 두 종류를 함께 읽는다. '
        '**폐쇄 낙폭**은 종료된 거래의 잔고 기준이고, **OHLC 낙폭 상한**은 보유 중 고·저점 순서를 '
        '보수적으로 가정한 가격 평가자산 낙폭이다. 거래가격 기반이며 실제 공정가격 강제청산 모형이 아니다.','',
        '| 방식 | 거래 | 승률 % | 계좌 손익비 | 종료 잔고 $ | 폐쇄 낙폭 % | OHLC 낙폭 상한 % | 평균 잔고 배정 % |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for q,label in LABELS.items():
        r=selected[('G','R2',q)]
        lines.append(f'| {q} {label} | {r["trades"]} | {f(r["win_rate_pct"])} | {f(r["account_payoff_ratio"],3)} | '
                     f'{f(r["end_marked_equity_usdt"])} | {f(r["closed_drawdown_pct"])} | {f(r["ohlc_drawdown_upper_bound_pct"])} | {f(r["average_margin_fraction"]*100)} |')
    lines+=['',
        '낙폭 축소를 우선하면 **Q6**, 조금 더 높은 수익과 단순한 규칙을 원하면 **Q4**가 비교 후보다. '
        '전액 Q0의 높은 수익을 그대로 유지하면서 낙폭만 줄인 결과는 아니다. '
        'Q2는 폐쇄 낙폭이 비교적 낮아도 보유 중 낙폭 상한이 훨씬 높으므로 폐쇄 지표만 보고 선택하지 않는다.','',
        '## 왜 크기 관리가 필요한가','',
        '직전 MEXC ZEC 5분봉 기록에서 C/R4는 최대 17연패, E/R0는 22연패, G/R2는 11연패였다. '
        '세 방식 모두 전액 10배 모형의 최악 거래가 약 −35.45% 계좌 수익률이었다. '
        '가격 손절을 추가하는 것만으로 큰 계좌 낙폭이 해소되지 않았으므로 매 거래의 노출과 연속 손실 대응을 비교했다.','',
        '## 고정한 관리 규칙','',
        '| 방식 | 규칙 |','|---|---|',
        '| Q0 | 잔고 전액을 증거금과 진입 수수료에 배정 |',
        '| Q1 | 잔고 50%를 증거금과 진입 수수료에 배정 |',
        '| Q2 | 잔고 25%를 증거금과 진입 수수료에 배정 |',
        '| Q3 | 신호 봉 ATR14로 크기 조절: 1.5 ATR 이동·수수료의 예상 손실이 계좌 1%가 되도록 산정, 배정 비율 상한 50% |',
        '| Q4 | Q3 + 확정된 자기 거래 2연패 후 6개 신호 봉 신규 진입 대기 |',
        '| Q5 | Q3 + 확정 폐쇄 잔고 고점 대비 낙폭 10% 이상이면 크기 절반, 20% 이상이면 4분의 1 |',
        '| Q6 | Q3·Q4·Q5 조합 |','',
        'ATR 1%는 **예상 크기 산정 기준**이며 확정 손실 상한이 아니다. R0/R2의 실제 청산은 ATR 손절이 아니고, '
        'R4도 종가 확인 후 다음 시가 청산이라 갭으로 초과 손실이 발생한다. Q5/Q6 역시 최대 낙폭을 20% 이하로 '
        '강제 제한하는 방식이 아니다. 계약 레버리지가 10배여도 배정 비율이 25%이면 계좌 노출은 약 2.5배다.','',
        '## 미래 정보를 사용하지 않는 처리','',
        '크기 산정의 ATR·가격은 해당 **진입 신호 봉의 확정값**이다. 연패·낙폭 상태는 새 신호 봉이 시작되기 전에 '
        '실제 청산된 자기 거래만 반영한다. 따라서 이전 봉에서 주문한 같은 시가 반전을 '
        '그 시가의 미래 손실을 미리 알고 취소하지 않는다. 미체결·건너뛴 가상 거래의 손익은 상태에 반영하지 않는다.','',
        '2연패가 확인되면 실제 청산 시각부터 6봉 구간의 신호를 막고 연패 카운터를 초기화한다. '
        '대기가 이미 시작됐으면 이후 이익이 확인돼도 예정된 종료 시각을 앞당기지 않는다. '
        '낙폭별 크기는 폐쇄 잔고의 자기 고점으로 계산하며 잔고 회복 시 다시 늘어날 수 있다.','',
        '기존 거래 기회 재생은 실제 데이터의 **필터 없는 C 교차가 번갈아 발생했음을 24개 전체 봉 배열에서 검사**한 뒤 허용한다. '
        '일반 교차가 항상 번갈아 발생한다는 가정은 하지 않는다. 같은 방향 교차가 연속되면 실행을 거부해 누락된 진입 '
        '기회가 생기는 것을 막는다. 기준 Q0의 120개 조합은 이전 복리 결과와 정확히 같음을 검사했다.','',
        '## 시기에 따른 비교','',
        '앞 4개월과 뒤 2개월은 각각 $1,000에서 시작하고 연패·낙폭 상태를 초기화한다. '
        '구간 경계의 보유 포지션을 이월하지 않고, 구간 마지막에 열린 포지션은 마지막 종가로 평가하되 가상 청산 수수료는 차감하지 않는다. '
        '앞선 연구에서 전체 기간을 이미 살펴봤으므로 뒤 2개월을 미관측 홀드아웃이라고 부르지 않는다.','',
        '| 모델·청산 | 방식 | 전체 잔고 $ | 전체 OHLC 낙폭 상한 % | 앞 4개월 잔고 $ | 앞 4개월 상한 % | 뒤 2개월 잔고 $ | 뒤 2개월 상한 % |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for model,profile in [('C','R4'),('E','R0'),('G','R2')]:
        for q in LABELS:
            r=selected[(model,profile,q)];a=r['temporal_segments']['first_four_months'];b=r['temporal_segments']['last_two_months']
            lines.append(f'| {model}/{profile} | {q} | {f(r["end_marked_equity_usdt"])} | {f(r["ohlc_drawdown_upper_bound_pct"])} | '
                         f'{f(a["end_marked_equity_usdt"])} | {f(a["ohlc_drawdown_upper_bound_pct"])} | {f(b["end_marked_equity_usdt"])} | {f(b["ohlc_drawdown_upper_bound_pct"])} |')
    lines+=['','## 전체 자산·주기의 수익과 손실','',
        '다음 표는 6개월 비교 90개 기준 조합에서 방식별 결과를 세어 보여준다. '
        '자산·주기·청산이 겹치므로 이 개수를 독립적인 성공 확률로 읽지 않는다. '
        '거래 크기만 줄여 음수 전략의 잔고를 보존한 경우는 수익성 개선과 구분한다.','',
        '| 방식 | 종료 잔고 $1,000 초과 | 종료 잔고 중앙값 $ | OHLC 낙폭 상한 중앙값 % | Q0 대비 낙폭 감소 |',
        '|---|---:|---:|---:|---:|']
    idx={(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'],r['policy']):r for r in rows}
    for q in LABELS:
        group=[r for r in rows if r['six_months'] and r['policy']==q]
        lower=sum(r['ohlc_drawdown_upper_bound_pct']<idx[(r['venue'],r['symbol'],r['timeframe_minutes'],r['model'],r['profile'],'Q0')]['ohlc_drawdown_upper_bound_pct']-1e-12 for r in group)
        lines.append(f'| {q} | {sum(r["end_marked_equity_usdt"]>1000 for r in group)}/{len(group)} | '
                     f'{f(float(np.median([r["end_marked_equity_usdt"] for r in group])))} | '
                     f'{f(float(np.median([r["ohlc_drawdown_upper_bound_pct"] for r in group])))} | {lower}/{len(group)} |')
    lines+=['','## 전체 결과 상세','',
        '**단위 손익비**는 수수료 후 가격 거래의 평균 수익률/평균 손실률 절댓값이다. '
        '**계좌 손익비**는 크기 조절 후 각 거래 시작 잔고 대비 수익률로 같은 비율을 계산한다. '
        '변동 크기를 적용하면 두 손익비가 다를 수 있다. 모든 승률은 실제 진입한 폐쇄 거래만 대상으로 한다.','']
    for venue,title in [('binance_um','Binance 전체 6개월'),('mexc','MEXC — 5/15분 6개월, 1/3분 짧은 기간')]:
        lines+=['### '+title,'']
        for symbol in sorted({r['symbol'] for r in rows if r['venue']==venue}):
            for tf in (1,3,5,15):
                group=[r for r in rows if r['venue']==venue and r['symbol']==symbol and r['timeframe_minutes']==tf]
                lines+=[f'#### {symbol} {tf}분', '', f'UTC 평가 시작: {group[0]["start_utc"]}; 6개월: {"예" if group[0]["six_months"] else "아니오"}.','',
                    '| 모델 | 청산 | 관리 | 거래 | 승률 % | 단위 손익비 | 계좌 손익비 | 종료 잔고 $ | 폐쇄 낙폭 % | OHLC 낙폭 상한 % | 대기 건너뜀 |',
                    '|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|']
                for r in group:
                    lines.append(f'| {r["model"]} | {r["profile"]} | {r["policy"]} | {r["trades"]} | {f(r["win_rate_pct"])} | '
                        f'{f(r["payoff_ratio"],3)} | {f(r["account_payoff_ratio"],3)} | {f(r["end_marked_equity_usdt"])} | '
                        f'{f(r["closed_drawdown_pct"])} | {f(r["ohlc_drawdown_upper_bound_pct"])} | {r["skipped_cooldown"]} |')
                lines.append('')
    lines+=['## 한계와 재현','',
        '여섯 관리 방식·1% ATR 기준·대기 길이·낙폭 임계값은 실행 전에 고정했다. '
        '동일한 과거 데이터에서 후보를 비교한 사후 연구이며 실거래 성과나 미래 수익의 확정값이 아니다. '
        '펀딩·슬리피지·공정가격 기반 강제청산·최소 주문량·계약 수량 한도는 제외했다. '
        '가격 평가자산 0 이하 접촉은 별도 저장하며 해당 이론 경로를 실제 계좌의 지속 가능한 수익으로 보지 않는다.','',
        '[전체 숫자 CSV](summary.csv) · [관리 적용 거래 기록](managed-trades.csv) · [조건·구간별 숫자·입력 해시](results.json) · [검증 기록](test-verification.txt)','',
        '실행 코드: scripts/ppp_drawdown_backtest.py, scripts/ppp_drawdown_report.py. 방법론: docs/strategy-notes/ppp-drawdown-management.md.','']
    (output/'report.ko.md').write_text('\n'.join(lines))
    print(f'Wrote drawdown report: {len(rows)} detailed cases')


def plot(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.dates as md
    from datetime import datetime,timezone
    rows=json.loads((output/'results.json').read_text())['summaries']
    fig,axes=plt.subplots(1,3,figsize=(14,4.5))
    for ax,(model,profile) in zip(axes,[('C','R4'),('E','R0'),('G','R2')]):
        group=[r for r in rows if r['venue']=='mexc' and r['symbol']=='ZEC_USDT' and r['timeframe_minutes']==5 and r['model']==model and r['profile']==profile]
        for r in group:
            ax.scatter(r['ohlc_drawdown_upper_bound_pct'],r['end_marked_equity_usdt'],s=50)
            ax.annotate(r['policy'],(r['ohlc_drawdown_upper_bound_pct'],r['end_marked_equity_usdt']),xytext=(4,4),textcoords='offset points',fontsize=8)
        ax.axhline(1000,color='gray',linestyle='--',linewidth=1);ax.set_yscale('log');ax.set_title(f'ZEC 5m - {model}/{profile}')
        ax.set_xlabel('Pessimistic OHLC drawdown bound (%)');ax.set_ylabel('Final account equity (USDT)');ax.grid(alpha=.2)
    fig.suptitle('Fixed 10x contract leverage, different account exposures\nMEXC six months; $1,000 initial, fees included; liquidation/funding/slippage excluded')
    fig.tight_layout();fig.savefig(output/'drawdown-comparison.png',dpi=160);plt.close(fig)
    curves={q:[] for q in LABELS}
    with (output/'managed-trades.csv').open() as handle:
        for r in csv.DictReader(handle):
            if r['venue']=='mexc' and r['symbol']=='ZEC_USDT' and r['timeframe_minutes']=='5' and r['model']=='G' and r['profile']=='R2':
                curves[r['policy']].append((int(r['exit_time']),float(r['closed_cash_usdt'])))
    start=datetime(2026,4,13,15,tzinfo=timezone.utc)
    fig,axes=plt.subplots(2,1,figsize=(11,7),sharex=True)
    for q,points in curves.items():
        dates=[start]+[datetime.fromtimestamp(t,timezone.utc) for t,c in points];cash=np.r_[1000.,[c for t,c in points]]
        axes[0].step(dates,cash,where='post',label=q,linewidth=1.2)
        if q in ('Q0','Q2','Q4','Q6'):
            dd=100*(1-cash/np.maximum.accumulate(cash));axes[1].step(dates,dd,where='post',label=q)
    axes[0].set_yscale('log');axes[0].axhline(1000,color='gray',linestyle='--',linewidth=1);axes[0].set_ylabel('Closed cash (USDT, log scale)');axes[0].legend(ncol=7)
    axes[1].set_ylabel('Closed-trade drawdown (%)');axes[1].invert_yaxis();axes[1].legend(ncol=4);axes[1].xaxis.set_major_formatter(md.DateFormatter('%b %d'));axes[1].set_xlabel('2026 date (UTC)')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('MEXC ZEC 5m G/SMA50: cash versus drawdown tradeoff\n10x leverage remains fixed; allocated account fraction varies')
    fig.tight_layout();fig.savefig(output/'drawdown-curves-zec5m.png',dpi=160);plt.close(fig)
    print('Wrote two drawdown charts')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-drawdown-2026-10-14');parser.add_argument('--plots',action='store_true')
    a=parser.parse_args();render(a.output)
    if a.plots:plot(a.output)
