#!/usr/bin/env python3
"""Standalone support/rejection reports with native minute execution charts."""
from __future__ import annotations
import argparse,base64,gzip,hashlib,json
from html import escape
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from ppp_backtest import ROOT,END
from ppp_asset_research import encode,export_reports,kst,loss_streaks
from ppp_asset_selective import selective_states
from ppp_largecap_report import journal
from ppp_support_ladder import CONFIGS,VARIANTS,TARGETS,COMPARISONS,market_cases,prepare,simulate_ladder
from ppp_selective_backtest import replay_selective

FILL_NOTE='▲ 롱 · ▼ 숏 · ● 청산 · ■ 원 지표 교차(확대 시). 신호와 이평선은 표시한 기준 주기, 실제 캔들과 확인·체결은1분입니다. 지지 확인형은 유효 신호를 기다렸다가 이평선 접촉·1분 종가 회복·양봉/음봉 확인 후 다음1분봉 시가 진입합니다. 청산 주기는 선택한 방식의1분/기준 주기입니다. 첫 진입이 포함된 기준 주기 봉에만1% 가격 손절(S2)을 적용하고 종료하면 취소합니다. 봉 내 정확한 초단위 체결은 알 수 없습니다. 갭 손절은 시가, 봉 내부 손절은 해당1분봉 마감부터 현금에 반영합니다.'
COST_NOTE='편도 수수료0.02%·초기$1000·10배 전액 복리의 이론 모형입니다. 일반 체결 슬리피지·펀딩·공정가격 강제청산·최소 계약수량은 제외합니다. 보수적 비용 표만 편도 총0.03%·S2 손절 추가0.05%를 반영합니다. MEXC와 Binance 가격을 섞지 않습니다.'


def records_for(sim,points):
    records,opened=journal(sim['positions'],points)
    by_entry={t['entry_time']:t for t in sim['positions']}
    for r in records:
        t=by_entry[r['entry']]
        if r['exit_timing']=='open':r['exit_signal_time']=r['exit']-60
        for k in ['entry_support_index','parent_signal_time','setup_available_time','tolerance','protected_index','protected_stop','guard_end']:r[k]=t[k]
    return records,opened


def export_charts(output,result):
    packs={a:{'G':{}} for a in TARGETS+COMPARISONS};exports={a:{'G':[]} for a in packs};summaries={a:[] for a in packs};sources={a:[] for a in packs}
    rows_lookup={(r['asset'],r['venue'],r['timeframe_minutes'],r['variant']):r for r in result['rows'] if r['cost']=='nominal'}
    examples=[]
    for asset,venue,tf,m,parent,start,_,_ in market_cases(TARGETS+COMPARISONS):
        if tf not in (5,15):continue
        b,d=prepare(m,parent,start,END);dest=output/asset.lower();dest.mkdir(exist_ok=True);profiles=[]
        columns=['open','high','low','close','sma20','sma50','sma100','sma200','main','signal','bits','atr','mfi','rvol']
        fields=[b.open,b.high,b.low,b.close,*d['mas'].T,d['main'],d['signal'],d['base_bits'],d['atr'],d['mfi'],d['rvol']]
        native=[[int(v[i]) if j==10 else float(v[i]) if j<4 else round(float(v[i]),8) for j,v in enumerate(fields)] for i in range(len(b.timestamp))]
        journals={}
        for spec in VARIANTS:
            seconds=60 if spec['stop_clock']=='minute' else parent.seconds
            sim=simulate_ladder(b,d,spec['base'],end=END,trace=True,risk_seconds=seconds)
            stats,points=replay_selective(b,sim['positions']);record,opened=records_for(sim,points);journals[spec['id']]=record
            expected=rows_lookup[(asset,venue,tf,spec['id'])]
            for k in stats:
                if stats[k]!=expected[k]:raise ValueError('Chart result changed: '+k)
            actual=sim['states'];signals=dict(long_entry=(actual&1024)!=0,short_entry=(actual&2048)!=0)
            reconstructed,cash,terminal=selective_states(b,signals,record,opened,start=start,end=END,initial=1000.)
            mask=128|256|512|1024|2048|4096|8192|65536
            if not np.array_equal(actual&mask,reconstructed&mask):raise ValueError('Minute state disagrees with exact journal')
            summary=dict(expected,model='G',profile=spec['id'],six_months=expected['full_period']);summaries[asset].append(summary)
            cfg=CONFIGS[spec['base']];rule='기존 지표 신호 + SMA20/50/100/200 정·역배열 + MFI50·RVOL1.2'
            if cfg['wait']:rule+=' → 신호 주기3봉 이내20→50→100→200 접촉·1분 종가 회복 확인'+(' · 손절 후 다음 선에서 새 신호 필요' if cfg['retry'] else ' · 신호당1회 진입')
            rule+=' · 이평선 청산 확인: '+('기존 기준 주기' if spec['base']=='B0' else '1분' if seconds==60 else str(tf)+'분')
            profile=dict(profile=spec['id'],label=spec['label'],risk_profile='R2' if spec['base']=='B0' else 'MA',policy='S2',summary=summary,trades=record,open_position=opened,streaks=loss_streaks(record),
                decision_states=actual.tolist(),cash_at_bar_open=cash.tolist(),terminal_cash=terminal,entry_mode='ladder' if cfg['wait'] else 'direct',
                entry_rule=rule,show_atr=True,show_protection=spec['base']!='B0',support_index=sim['support_index'].tolist(),margin=sim['margin'].tolist(),
                source_time=sim['source_time'].tolist(),protected_stop=sim['protected_stop'].tolist(),stop_minutes=seconds//60,
                audit=dict(state_sha256=hashlib.sha256(actual.astype('<i4').tobytes()).hexdigest(),last_cash=float(cash[-1]),journal_state_matches=True))
            profiles.append(profile)
        for base in ('N0','W0','W1','R0','R1'):
            slow={r['entry']:r for r in journals[base+'-signal']}
            for fast in journals[base+'-minute']:
                other=slow.get(fast['entry'])
                if not other or other['side']!=fast['side'] or not fast['reason'].startswith(('nearest_','support_')):continue
                if fast['exit']<other['exit']:
                    examples.append(dict(asset=asset,venue=venue,signal_minutes=tf,base=base,entry_kst=kst(fast['entry']),fast_profile=base+'-minute',slow_profile=base+'-signal',fast_n=fast['n'],slow_n=other['n'],
                        fast_exit_kst=kst(fast['exit']),slow_exit_kst=kst(other['exit']),fast_net_pct=fast['net_pct'],slow_net_pct=other['net_pct'],
                        improved_pct=other['net_pct']-fast['net_pct'],recovered=fast['net_pct']<0 and other['net_pct']>0,source='Same entry timestamp/side; later trade paths can diverge.'))
        key=f'{venue}-{tf}';meta=dict(key=key,venue=venue,symbol=asset+('_USDT' if venue=='mexc' else 'USDT'),timeframe_minutes=tf,execution_timeframe_minutes=1,signal_step=parent.seconds,
            start=start,end=END,step=60,start_kst=kst(start),end_kst=kst(END),full_period=start==result['protocol']['start'],six_months=start==result['protocol']['start'],count=len(native),columns=columns)
        packed=dict(**meta,rows=native,profiles=profiles);encoded=encode(packed);packs[asset]['G'][key]=encoded;exports[asset]['G'].append(meta)
        (dest/f'G-{key}.json.gz').write_bytes(base64.b64decode(encoded));sources[asset].append(dict(venue=venue,timeframe_minutes=tf,full_period=meta['full_period'],start_kst=kst(start)))
        print('Native minute chart data:',asset,venue,tf,'profiles',len(profiles),flush=True)
    files=[]
    for asset in packs:
        dest=output/asset.lower();args=SimpleNamespace(asset=asset,models=['G'],profiles=[s['id'] for s in VARIANTS],fee=.0002,initial=1000.,leverage=10.,output=dest,
            profile_labels={s['id']:s['label'] for s in VARIANTS},default_profile='B0',experimental_profiles=[s['id'] for s in VARIANTS if s['id']!='B0'],
            native_execution=True,fill_note=FILL_NOTE,slippage_note=COST_NOTE,default_market='binance_um-5')
        export_reports(args,dict(start_kst=kst(result['protocol']['start']),end_exclusive_kst=kst(END),summaries=summaries[asset],provenance=sources[asset]),exports[asset],packs[asset])
        old=dest/f'{asset.lower()}-g-strategy.html';path=dest/f'{asset.lower()}-support-ladder.html';old.rename(path)
        p=dest/'index.html';p.write_text(p.read_text().replace(old.name,path.name))
        p=dest/'html-manifest.json';meta=json.loads(p.read_text());meta['files'][0]['file']=path.name;p.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
        files.append(dict(asset=asset,file=str(path.relative_to(output)),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (output/'chart-manifest.json').write_text(json.dumps(files,ensure_ascii=False,indent=2)+'\n')
    examples.sort(key=lambda e:e['improved_pct'],reverse=True);(output/'clock-examples.json').write_text(json.dumps(examples,ensure_ascii=False,indent=2)+'\n')


def report(output,result):
    rows=result['rows'];fmt=lambda x:'—' if x is None else f'{x:,.2f}' if abs(x)>=.01 else f'{x:.3g}'
    tr=lambda xs:'<tr>'+''.join('<td>'+escape(str(x))+'</td>' for x in xs)+'</tr>'
    table=lambda headers,rs:'<div class="scroll"><table><thead>'+tr(headers)+'</thead><tbody>'+''.join(rs)+'</tbody></table></div>'
    target=[r for r in rows if r['role']=='target' and r['full_period']];overview=[]
    for spec in VARIANTS:
        g=[r for r in target if r['variant']==spec['id'] and r['cost']=='nominal'];stress=[r for r in target if r['variant']==spec['id'] and r['cost']=='stress']
        def med(key):
            values=[r[key] for r in g if r[key] is not None]
            return float(np.median(values)) if values else None
        overview.append(tr([spec['label'],f'{sum((r["profit_factor"] or 0)>1 for r in g)}/{len(g)}',f'{sum((r["profit_factor"] or 0)>1 for r in stress)}/{len(stress)}',fmt(med('trades')),fmt(med('win_rate_pct')),fmt(med('payoff_ratio')),fmt(med('end_marked_equity_usdt')),fmt(med('closed_drawdown_pct')),sum(r['trades']<30 for r in g)]))
    examples=json.loads((output/'clock-examples.json').read_text());recovered=[e for e in examples if e['recovered']];worsened=[e for e in examples if e['improved_pct']<0]
    examples_show=(recovered[:5]+sorted(worsened,key=lambda e:e['improved_pct'])[:5])
    diagnostic=[]
    for r in rows:
        if r['venue']=='binance_um' and r['timeframe_minutes']==5 and r['variant']=='W1-minute' and r['cost']=='nominal':
            d=r['diagnostics'];diagnostic.append(tr([r['asset'],d.get('qualified_source_signals',0),r['trades'],*[d.get('entry_ma'+str(n),0) for n in (20,50,100,200)],d.get('wait_cancel_opposite_cross',0),d.get('wait_cancel_expired',0),d.get('wait_cancel_array_broken',0)]))
    page=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>추세·거래량 전략 · 지지 확인·청산 주기 비교</title>',
      '<style>:root{color-scheme:light dark}body{font:16px/1.65 system-ui;max-width:1400px;margin:24px auto;padding:0 18px}h1{font-size:28px}h2{font-size:22px;margin-top:32px}a{color:#2694bb}.scroll{overflow:auto}table{border-collapse:collapse;font-size:14px;white-space:nowrap;width:100%}td,th{padding:8px;border-bottom:1px solid #9995;text-align:left}.notice{padding:12px 18px;border-left:4px solid #c79335;background:#c7933511}select{font:inherit;padding:8px;border:1px solid #9995;margin:4px}.cards{display:flex;flex-wrap:wrap;gap:10px}.cards a{border:1px solid #9995;padding:12px 18px;border-radius:8px}</style>',
      '<h1>추세·거래량 전략 · 순차 지지·저항 확인</h1><p>신호 주기의 SMA20→50→100→200을 보고, 진입 확인은1분봉으로 합니다. 이평선 청산은1분 마감과 **신호·이평선 기준 주기 마감**을 비교했습니다. 3분 전략은3분, 5분은5분, 15분은15분입니다. 고정5분 청산이 아닙니다.</p>',
      '<div class="notice">지지 확인 대기는 낙폭을 줄였지만 대부분의 대형 코인에서 수익성을 확보하지 못했습니다. 거래 수 감소로 낙폭이 줄어든 효과가 크고 일부 조합의 표본도 적습니다. 기존 기준형을 교체하지 않으며 변형들은 실험으로 보관합니다.</div>',
      '<p>2026-04-14 00:00→2026-10-14 00:00 KST 직전 · Binance7코인×신호1/3/5/15분=28개6개월 자료. MEXC는 BTC/ETH/WLD/ZEC의 확보된1분 구간을 사용한5/15분 신호8개 짧은 비교이며, BNB/SOL/XRP의 MEXC1분 자료는 이번에 없어 제외했습니다. 다른 거래소 가격을 혼합하지 않았습니다.</p>',
      '<p>기준형1개 + 진입·청산5가지×확인주기2개=11가지, 비용2개로 총'+str(len(rows))+'결과입니다. 명목 편도0.02%, 보수적 편도 총0.03%·첫 봉 가격 손절 추가0.05%. 독립 초기$1000·10배 전액 복리입니다. 승률·손익비·PF는 자금이 남아 집행된 종료 거래 기준이며 미청산은 종료 평가자산에만 포함합니다. 손익비는 수수료 포함1배 수익률의 평균 수익÷평균 손실, PF는 수익 합÷손실 합입니다.</p>',
      '<h2>실제 전체1분봉으로 검토</h2><p>각 코인에서 신호5분/15분을 선택하고 실제 체결1분봉 전체를 볼 수 있습니다. 수익·손실 거래, 원 신호, 대기 중 선택 선, 미진입 사유, 실제 보호가(점선)를 표시합니다. 아래 표에는 신호1분/3분 결과도 모두 있습니다.</p><div class="cards">'+''.join(f'<a href="{a.lower()}/{a.lower()}-support-ladder.html">{a}'+(' · 비교용' if a in COMPARISONS else '')+'</a>' for a in TARGETS+COMPARISONS)+'</div>',
      '<h2>고정한 규칙</h2><p>기존 G의 이중 Stochastic 새 교차·완전 SMA 정/역배열·MFI50·RVOL1.2를 유지합니다. 대기 신호는 기준 주기3봉까지 유효하며, 진입 때도 완전 배열이어야 합니다. 허용 폭은 신호 당시 ATR14의0.1배입니다. 이 숫자는 성과를 보기 전에 고정한 검증 시작값이며 최적값이라는 뜻은 아닙니다.</p>',
      table(['비교군','진입','이평선 청산'],[tr([v['label'],'원 신호 다음 시가' if not v['wait'] else '20→50→100→200 접촉·1분 종가 회복·양봉/음봉'+(' · 손절 후 더 깊은 선에서 새 신호' if v['retry'] else ''),'기존 SMA50' if v['risk']=='baseline' else '진입 근거 선' if v['risk']=='anchor' else '가격의 지지/저항 쪽 최근접 선']) for v in CONFIGS.values()]),
      '<p>롱 지지 회복은1분봉 고저가가 선±허용 폭과 겹치고 종가≥선+폭·양봉입니다. 숏은 대칭입니다. 실패는 롱 종가&lt;선−폭/숏 종가&gt;선+폭입니다. 한 봉이 여러 선을 통과해도 그 봉의 과거 저가·고가를 다음 선 확인에 재사용하지 않습니다. 보호 선 실패를 먼저 검사한 뒤 더 가까운 선으로 보호를 올리며, 보호가를 불리하게 완화하지 않습니다. 손절 후 재시도는 **새 원 지표 신호**가 있어야 하며 동일 신호 재사용만으로 들어가지 않습니다.</p>',
      '<p>반대 지표 교차는 신호 주기 마감으로 계속 청산합니다. 이평선 실패 확인 주기를 길게 해도 첫 진입이 포함된 기준 주기 봉의1% 가격 손절(S2)은 봉 내부에 적용됩니다. 따라서 큰 꼬리가 S2에 닿으면 기준 주기 청산형도 손절됩니다. 나머지는 확인 종가 다음1분봉 시가 체결입니다. '+COST_NOTE+'</p>',
      '<h2>대형 코인20조합 공통성</h2><p>BTC/ETH/BNB/SOL/XRP × 신호1/3/5/15분의20개 독립 계좌를 동일 비중으로 비교했습니다. 1분 전략은 두 확인 주기가 같아 결과도 중복됩니다. 서로 다른 주기는 서로 다른 표본이며 아래 중앙값은 하나의 합산 계좌 수익이 아닙니다. 승률·손익비 중앙값은 값이 정의되는 조합만 사용합니다(무거래 또는 평균 수익/손실을 정의할 수 없는 조합은 제외). 표본30거래 미만도 표시합니다.</p>',
      table(['방식','명목 PF>1','비용 강화 PF>1','거래 중앙','승률 중앙 %','손익비 중앙','종료 자산 중앙 $','폐쇄 DD 중앙 %','30거래 미만 조합'],overview),
      '<p>기준형의 낮은 자산에 비해 대기형의 자산이 덜 줄어든 것은 대부분 거래를 하지 않은 효과도 포함합니다. 승률이0%인15거래와 손익비가 큰1회 승리 결과를 같은 신뢰도로 해석하면 안 됩니다. 기준형 전체56개6개월 비용별 조합의 거래 수·종료 자산·폐쇄 낙폭은 이전 계산과 재현되었고, OHLC 낙폭 상한은 더 세밀한1분 경로로 다시 평가했습니다.</p>',
      '<h2>짧은 확인 뒤 회복·더 큰 손실 사례</h2><p>동일 진입 시각·방향인 거래를 짝지었습니다. 긴 확인형이 수익으로 회복한 경우와, 더 크게 손실 난 경우를 함께 표시합니다. 이후 재진입 경로는 달라질 수 있어 전체 결과의 원인을 이 사례만으로 단정하지 않습니다.</p>',
      table(['코인·거래소','신호 분','방식','진입 KST','1분 확인 순손익 %','기준 주기 확인 순손익 %','확인형 종료 KST','거래 번호'],[tr([e['asset']+' '+e['venue'],e['signal_minutes'],CONFIGS[e['base']]['label'],e['entry_kst'],fmt(e['fast_net_pct']),fmt(e['slow_net_pct']),e['slow_exit_kst'],f'1분#{e["fast_n"]} / 기준#{e["slow_n"]}']) for e in examples_show]),
      '<p>각 코인 차트에서 해당 거래소·신호 주기를 선택하고, 방식을1분/기준 주기로 바꾼 뒤 위 거래 번호를 선택하면 같은 구간을 확대할 수 있습니다.</p>',
      '<h2>왜 진입이 줄었나</h2><p>신호5분·1분 확인·최근접 청산 대기형의 원 신호와 실제 진입입니다. 원 신호가 반대로 바뀌거나 배열이 깨지면 대기를 취소합니다. 기존 완전 배열 조건을 유지하므로100·200까지 내려가는 후보는 진입 전에 취소될 수 있습니다. 재시도형과 대기형이 같은 결과인 코인은 새 신호·더 깊은 선을 함께 만족하는 추가 타점이 거의 없었던 것입니다.</p>',
      table(['코인','원 신호','종료 거래','20진입','50진입','100진입','200진입','반대 교차 취소','유효기간 취소','배열 취소'],diagnostic),
      '<h2>전체 결과</h2><label>코인<select id="asset"><option value="">전체</option>'+''.join('<option>'+a+'</option>' for a in TARGETS+COMPARISONS)+'</select></label><label>자료<select id="coverage"><option value="full">6개월 Binance</option><option value="short">짧은 MEXC</option></select></label><label>비용<select id="cost"><option value="nominal">편도0.02%</option><option value="stress">비용 강화</option></select></label><div class="scroll"><table id="results"><thead>'+tr(['코인','거래소','신호 분','방식','거래','승률 %','손익비','PF','순기대값 %','종료 자산 $','폐쇄 DD %','OHLC DD상한 %','0접촉'])+'</thead><tbody></tbody></table></div>',
      '<h2>기록·제약</h2><p><a href="summary.csv">전체 결과 CSV</a> · <a href="trades.csv">거래 CSV</a> · <a href="diagnostics.csv">대기·실패 집계</a> · <a href="clock-examples.json">같은 진입의 확인주기 비교</a> · <a href="fixed-protocol.json">고정 규칙·소스 해시</a> · <a href="baseline-audit.json">기준형 재현 비교</a> · <a href="../ppp-largecap-2026-10-14/index.html">기존 추세·거래량 연구 및 draft 보관</a></p>',
      '<p>이미 관측한6개월 시장의 소급 연구이며 독립적인 미래 검증 결과가 아닙니다. 적은 거래·다중 비교·코인 상관관계를 고려해야 합니다. 현재 이평선은 해당1분봉 마감 시점에 이미 마감된 기준 주기 값만 사용합니다. 초단위 가격 경로는 복원하지 않았고, 봉 내부 고저가 순서의 불확실성은 OHLC 낙폭 상한으로 표시합니다. 가격 평가자산0접촉 이후 경로를 실제 계좌 지속 결과로 해석할 수 없습니다. 확정된 상위 주기 값을 쓰는 접근은 <a href="https://www.tradingview.com/pine-script-docs/concepts/other-timeframes-and-data/">TradingView 공식 문서</a>에도 설명되어 있습니다.</p>',
      '<script id="rows" type="application/json">'+json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')+'</script><script>const rows=JSON.parse(document.getElementById("rows").textContent),e=id=>document.getElementById(id),f=v=>v==null?"—":v>0&&v<.01?v.toPrecision(3):v.toLocaleString("ko-KR",{maximumFractionDigits:3});function render(){e("results").querySelector("tbody").replaceChildren(...rows.filter(r=>(!e("asset").value||r.asset===e("asset").value)&&r.cost===e("cost").value&&r.full_period===(e("coverage").value==="full")).map(r=>{const tr=document.createElement("tr");[r.asset,r.venue,r.timeframe_minutes,r.label,r.trades,f(r.win_rate_pct),f(r.payoff_ratio),f(r.profit_factor),f(r.avg_net_return_pct),f(r.end_marked_equity_usdt),f(r.closed_drawdown_pct),f(r.ohlc_drawdown_upper_bound_pct),r.price_zero_equity_events].forEach(v=>{const td=document.createElement("td");td.textContent=v;tr.append(td)});return tr}))}for(const id of ["asset","coverage","cost"])e(id).addEventListener("change",render);render();</script></html>']
    (output/'index.html').write_text('\n'.join(page))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-support-2026-10-14');a=p.parse_args();r=json.loads((a.output/'results.json').read_text())
    if r['protocol']['source_sha256']!=hashlib.sha256((ROOT/'scripts/ppp_support_ladder.py').read_bytes()).hexdigest():raise ValueError('Frozen simulation source changed')
    export_charts(a.output,r);report(a.output,r)


if __name__=='__main__':main()
