#!/usr/bin/env python3
"""Render the complete C/E/G risk comparison; no simulation or tuning here."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ppp_backtest import ROOT

LABELS = {
    'R0': '기존 반대 크로스', 'R1': 'SMA20', 'R2': 'SMA50',
    'R3': '진입 봉 저·고점', 'R4': '1.5 ATR',
    'R5': 'SMA50 또는 진입 봉', 'R6': 'R5 + 수수료 포함 본전',
}


def fmt(value, digits=2):
    return '—' if value is None else f'{value:.{digits}f}'


def render(output):
    payload = json.loads((output/'results.json').read_text())
    rows = payload['summaries']
    index = {(r['venue'], r['symbol'], r['timeframe_minutes'], r['model'], r['profile']): r for r in rows}
    original = lambda r: index[(r['venue'], r['symbol'], r['timeframe_minutes'], r['model'], 'R0')]
    main = [r for r in rows if r['venue'] == 'binance_um']
    diagnostics = json.loads((output/'loss-diagnostics.json').read_text())['summaries']
    assets = sorted({r['symbol'].replace('_','').replace('USDT','') for r in main})
    ncases = len([r for r in main if r['model']=='C' and r['profile']=='R0'])
    main_count=len(main)
    mexc_full=sum(r['venue']=='mexc' and r['six_months'] for r in rows)
    mexc_short=sum(r['venue']=='mexc' and not r['six_months'] for r in rows)
    text = [
        '# PPP C/E/G 리스크 관리 백테스트', '',
        'KST **2026-04-14 00:00–2026-10-14 00:00 직전**. 편도 수수료 **0.02%** 반영. '
        '같은 봉의 엄격한 SMA20/50/100/200 정·역배열과 기존 C/E/G 진입 필터를 모두 유지했다.', '',
        '1·3·5·15분의 동일한 6개월 비교는 **Binance USD-M** 시세를 사용했다. '
        '**MEXC 선물 5·15분은 별도의 6개월 비교**이고, MEXC 1·3분은 '
        '**자산별 API 가용 범위 이후의 짧은 기간**으로 따로 표시했다. '
        f'{len(rows)}개 중 Binance 6개월 {main_count}개, MEXC 6개월 {mexc_full}개, MEXC 짧은 기간 {mexc_short}개다. '
        f'대상 자산: {", ".join(assets)}.', '',
        f'기존 R0와 리스크 6개를 합쳐 **{len(rows)}개 조합**, 폐쇄 거래 **{sum(r["trades"] for r in rows):,}건**을 계산했다. '
        '거래 건수는 서로 겹치는 전략 결과의 합이며 독립적인 시장 표본 수가 아니다. '
        '모든 R0 거래 기록은 기존 엔진에서 같은 비용으로 재계산한 기록과 정확히 일치했다.', '',
        '**손익비 = 평균 순수익률 / 평균 순손실률 절댓값**. '
        '승률은 수수료 후 양수인 거래의 비율이다. PF는 이익 합/손실 합으로 손익비와 다르다. '
        '기대수익은 거래당 평균 순수익률이며 아래 % 수치는 진입 명목가치 대비다.', '',
        '## 리스크 규칙', '', '| 코드 | 조건 |', '|---|---|',
    ]
    text.extend(f'| {p} | {label} |' for p, label in LABELS.items())
    text += ['',
        'R1/R2는 롱이 해당 SMA 아래, 숏이 위에서 마감하면 청산한다. R3는 실제 진입 봉보다 '
        '나중 봉에서 롱 종가가 진입 봉 저점 아래 / 숏 종가가 진입 봉 고점 위면 청산한다. '
        'R4는 진입 직전 확정 ATR14의 1.5배를 진입가에서 불리한 방향으로 넘긴 종가를 사용한다. '
        'R5는 둘 중 먼저 발생한 조건이며, R6는 수수료 후 1 ATR 수익에 도달하면 다음 봉부터 본전을 보호한다.', '',
        '원래 반대 크로스는 항상 청산한다. 모든 청산은 **종가 확인 → 다음 시가**이며 꼬리 접촉으로 '
        '손절했다고 가정하지 않는다. 갭 때문에 기준 손실을 초과하거나 본전 보호에서도 순손실이 날 수 있다. '
        '반대 크로스의 적격 반전은 허용하되, 리스크만 발동한 봉에서는 즉시 재진입하지 않는다.', '',
        '## 패배 기록에서 선택한 근거', '',
        '기존 폐쇄 거래의 경로를 분석했고 승리 거래도 대조군으로 사용했다. 아래는 Binance 6개월의 '
        f'{ncases}개 자산·주기 조합을 거래 수로 가중한 발동 비율이다. 이는 사후 경로 통계이며 실제로 '
        '회피한 손실의 비율이 아니다.', '',
        '| 모델 | 조건 | 패배 거래에서 발동 | 승리 거래에서 발동 |', '|---|---|---:|---:|',
    ]
    for model in ('C', 'E', 'G'):
        cases = [r for r in diagnostics if r['venue'] == 'binance_um' and r['model'] == model]
        for key, label in [('sma20', 'SMA20'), ('sma50', 'SMA50'), ('entry_bar', '진입 봉'), ('atr_1_5', '1.5 ATR')]:
            loss_count = sum(r['losses'] for r in cases)
            win_count = sum(r['wins'] for r in cases)
            bad = sum(r['losses']*r['candidates'][key]['loss_hit_pct'] for r in cases)/loss_count
            good = sum(r['wins']*r['candidates'][key]['win_hit_pct'] for r in cases)/win_count
            text.append(f'| {model} | {label} | {bad:.2f}% | {good:.2f}% |')
    text += ['',
        'SMA20는 C의 기존 승리 거래도 자주 끊었다. 진입 봉 기준은 상대적으로 선택적이고, '
        '1.5 ATR은 발동 빈도가 낮지만 큰 역행에 집중한다. 따라서 평균 손실 감소뿐 아니라 '
        '잘린 수익과 승률 감소를 함께 비교해야 한다.', '',
        '## 전체 6개월: 방식별 개선 빈도', '',
        f'각 모델의 {"/".join(assets)} × 1/3/5/15분, 총 {ncases}개 조합에서 R0보다 개선된 개수다. '
        '승률·손익비 중 하나만 높아진 것을 수익 개선이라고 부르지 않는다.', '',
        '| 모델 | 방식 | 승률 개선 | 손익비 개선 | 기대수익 개선 | 폐쇄 거래 낙폭 감소 |',
        '|---|---|---:|---:|---:|---:|',
    ]
    for model in ('C', 'E', 'G'):
        for profile in LABELS:
            if profile == 'R0':
                continue
            group = [r for r in main if r['model'] == model and r['profile'] == profile]
            better = lambda key: sum(r[key] > original(r)[key]+1e-12 for r in group)
            lower_dd = sum(r['closed_equity_max_drawdown_pct'] < original(r)['closed_equity_max_drawdown_pct']-1e-12 for r in group)
            text.append(f'| {model} | {profile} {LABELS[profile]} | {better("win_rate_pct")}/{len(group)} | {better("payoff_ratio")}/{len(group)} | {better("avg_net_return_pct")}/{len(group)} | {lower_dd}/{len(group)} |')
    text += ['', '## 자산·주기별 비교 요약', '',
        '아래 후보는 **리스크 없는 R0를 포함한 R0–R6 중 전체 6개월 기대수익이 가장 높은 시안**이다. 같은 표본에서 '
        '선정한 값이므로 추천 확정이나 미관측 성과가 아니다. R0가 최고면 기존 유지로 표시한다. '
        '뒤 2개월은 독립 시뮬레이션이며 앞 기간의 포지션을 이어받지 않는다.', '',
        '| 자산 | 분 | 모델 | 후보 | 거래 | 승률 기존→후보 % | 손익비 기존→후보 | 기대수익 기존→후보 % | 뒤 2개월 기대수익 % | 기존 대비 |',
        '|---|---:|---|---|---:|---:|---:|---:|---:|---|',
    ]
    for r in main:
        if r['profile'] != 'R0':
            continue
        candidates = [index[(r['venue'], r['symbol'], r['timeframe_minutes'], r['model'], p)] for p in LABELS]
        b = max(candidates, key=lambda x: x['avg_net_return_pct'])
        last = b['temporal_segments']['last_two_months']['avg_net_return_pct']
        verdict = '개선' if b['profile']!='R0' and b['avg_net_return_pct'] > r['avg_net_return_pct']+1e-12 else '기존 유지'
        text.append(f'| {r["symbol"]} | {r["timeframe_minutes"]} | {r["model"]} | {b["profile"]} | {b["trades"]} | '
                    f'{fmt(r["win_rate_pct"])}→{fmt(b["win_rate_pct"])} | {fmt(r["payoff_ratio"])}→{fmt(b["payoff_ratio"])} | '
                    f'{fmt(r["avg_net_return_pct"],4)}→{fmt(b["avg_net_return_pct"],4)} | {fmt(last,4)} | {verdict} |')
    text += ['', '## ZEC 5분봉: 두 거래소와 시기별 비교', '',
        '기존 연구의 비교 지점이므로 모든 방식의 시기별 기대수익을 함께 표시한다. '
        '거래소별 캔들 차이로 같은 방식의 성과 방향이 다를 수 있다.', '',
        '| 거래소 | 모델 | 방식 | 거래 | 승률 % | 손익비 | 기대수익 % | PF | 앞 4개월 기대수익 % | 뒤 2개월 기대수익 % |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for r in rows:
        if r['symbol'].startswith('ZEC') and r['timeframe_minutes'] == 5:
            a = r['temporal_segments']['first_four_months']; b = r['temporal_segments']['last_two_months']
            text.append(f'| {r["venue"]} | {r["model"]} | {r["profile"]} | {r["trades"]} | {fmt(r["win_rate_pct"])} | '
                        f'{fmt(r["payoff_ratio"],3)} | {fmt(r["avg_net_return_pct"],4)} | {fmt(r["profit_factor"],3)} | '
                        f'{fmt(a["avg_net_return_pct"],4)} | {fmt(b["avg_net_return_pct"],4)} |')
    for title, group in [
        ('Binance USD-M 전체 6개월 상세 (1/3/5/15분)', main),
        ('MEXC 선물 전체 6개월 상세 (5/15분)', [r for r in rows if r['venue']=='mexc' and r['six_months']]),
        ('MEXC 선물 짧은 기간 상세 (1/3분)', [r for r in rows if r['venue']=='mexc' and not r['six_months']]),
    ]:
        text += ['', f'## {title}', '']
        if '짧은' in title:
            windows=sorted({r['start_utc'] for r in group})
            text += [f'평가 시작(UTC): {", ".join(windows)}. KST 2026-10-14 00:00 직전까지. 6개월 결과와 직접 합치지 않는다.', '']
        text += ['낙폭은 폐쇄 거래의 1배 복리 모델이며, 봉 내부·미청산 평가손실을 포함하지 않는다. '
                 '평균 손실은 절댓값으로 표시한다.', '']
        for symbol in sorted({r['symbol'] for r in group}):
            for tf in sorted({r['timeframe_minutes'] for r in group if r['symbol']==symbol}):
                text += [f'### {symbol} {tf}분', '',
                    '| 모델 | 방식 | 거래 | 승률 % | 손익비 | 평균 수익 % | 평균 손실 % | 기대수익 % | PF | 손실 p95 % | 최악 거래 % | 낙폭 % |',
                    '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
                for r in group:
                    if r['symbol']==symbol and r['timeframe_minutes']==tf:
                        keys = ['win_rate_pct', 'payoff_ratio', 'avg_win_pct', 'avg_loss_pct',
                                'avg_net_return_pct', 'profit_factor', 'p95_loss_pct', 'worst_trade_pct', 'closed_equity_max_drawdown_pct']
                        values = ' | '.join(fmt(r[k], 4 if k=='avg_net_return_pct' else 3 if k in ('payoff_ratio','profit_factor') else 2) for k in keys)
                        text.append(f'| {r["model"]} | {r["profile"]} | {r["trades"]} | {values} |')
                text.append('')
    text += ['## 리스크를 추가하지 않는 선택', '',
        '리스크 관리가 평균 손실을 줄여도 평균 수익을 더 많이 줄이면 기존 반대 크로스만 사용하는 R0가 낫다. '
        '이번 비교는 사용자의 요청에 따라 R0도 선택 후보에 포함한다. 선택 기준은 거래당 기대수익이며, '
        '레버리지 복리의 최종 잔고를 최대화하는 선정과는 다르다.', '',
        '## 해석과 재현', '',
        '승률이 내려가도 평균 손실이 더 크게 줄면 손익비가 높아진다. 그러나 손익비 상승만으로 '
        '기대수익이 좋아지는 것은 아니다. R6도 수익을 일찍 끊는 비용이 있으므로 항상 유리하지 않다. '
        '음수 기대수익을 작은 손절만으로 양수로 만들 수 있다고 가정하지 않는다.', '',
        '후보는 기존 전체 기록을 분석해 결정했으므로 사후 선정이다. 앞 4개월/뒤 2개월 비교도 '
        '미관측 검증은 아니다. 펀딩·슬리피지·증거금 청산은 제외했다. 기간 말 미청산 포지션은 '
        'results.json에 별도 기록했다. 주문은 실제로 전송하지 않았다.', '',
        '[전체 지표 CSV](summary.csv), [전체 거래 기록](trades.csv), [상세 결과·입력 해시](results.json), '
        '[기존 거래 경로 진단](loss-diagnostics.json), [테스트 실행 기록](test-verification.txt).', '',
        '코드: scripts/ppp_risk_backtest.py, scripts/ppp_risk_report.py. 방법론: docs/strategy-notes/ppp-risk-controls.md.', '',
    ]
    (output/'report.ko.md').write_text('\n'.join(text), encoding='utf-8')
    print(f'Wrote complete report: {output/"report.ko.md"}')


def plot(output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np

    rows = json.loads((output/'results.json').read_text())['summaries']
    main = [r for r in rows if r['venue']=='binance_um' and r['profile']!='R0']
    cases = sorted({(r['symbol'], r['timeframe_minutes'], r['model']) for r in main})
    lookup = {(r['symbol'], r['timeframe_minutes'], r['model'], r['profile']): r for r in main}
    data = np.array([[lookup[(*c, f'R{p}')]['delta_expectancy_pp'] for p in range(1,7)] for c in cases])
    limit = max(float(np.abs(data).max()), .0001)
    fig, ax = plt.subplots(figsize=(11, 10))
    pic = ax.imshow(data, cmap='RdBu', vmin=-limit, vmax=limit, aspect='auto')
    ax.set_xticks(range(6), ['R1\nSMA20', 'R2\nSMA50', 'R3\nEntry bar', 'R4\n1.5 ATR', 'R5\nR2 OR R3', 'R6\nR5 + BE'])
    ax.set_yticks(range(len(cases)), [f'{s.replace("USDT", "")} {t:2}m {m}' for s,t,m in cases])
    ax.set_title('C/E/G risk exits: change in net expectancy versus original\nBinance USD-M, six months; 0.02% fee per side')
    for i in range(len(cases)):
        for j in range(6):
            ax.text(j,i,f'{data[i,j]:+.4f}', ha='center', va='center', fontsize=8,
                    color='white' if abs(data[i,j])>limit*.6 else 'black')
    fig.colorbar(pic, ax=ax, label='Percentage points of entry notional per trade')
    fig.tight_layout(); fig.savefig(output/'expectancy-comparison.png', dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1,3,figsize=(13,4))
    for ax, model in zip(axes, ('C','E','G')):
        for venue, color, marker in [('binance_um','tab:blue','o'), ('mexc','tab:orange','^')]:
            group=[r for r in rows if r['venue']==venue and r['symbol'].startswith('ZEC') and r['timeframe_minutes']==5 and r['model']==model]
            ax.scatter([r['win_rate_pct'] for r in group], [r['payoff_ratio'] for r in group], color=color, marker=marker, label=venue)
            for r in group:
                ax.annotate(r['profile'], (r['win_rate_pct'],r['payoff_ratio']), xytext=(4,4), textcoords='offset points', fontsize=7, color=color)
        ax.set_title(f'ZEC 5m - {model}');ax.set_xlabel('Net win rate (%)');ax.set_ylabel('Mean net win / mean net loss')
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    fig.suptitle('Six months, fixed risk profiles; higher payoff can come with lower win rate')
    fig.tight_layout(); fig.savefig(output/'win-payoff-zec5m.png',dpi=170);plt.close(fig)
    print('Wrote expectancy-comparison.png and win-payoff-zec5m.png')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'user_data/backtest_results/ppp-risk-2026-10-14')
    parser.add_argument('--plots', action='store_true')
    args = parser.parse_args()
    render(args.output)
    if args.plots:
        plot(args.output)
