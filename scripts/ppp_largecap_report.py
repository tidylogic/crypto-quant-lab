#!/usr/bin/env python3
"""Export frozen trend/volume research and full native 5/15m review charts."""
from __future__ import annotations
import argparse,base64,hashlib,json,shutil,os
from html import escape
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from ppp_backtest import ROOT,START,END,smooth
from ppp_combo_backtest import build_features
from ppp_asset_research import encode,export_reports,kst,loss_streaks
from ppp_asset_selective import selective_states
from ppp_largecap_research import TARGETS,COMPARISONS,CONFIGS,FEE,cases,evaluate,extra_features,verify_frozen

BASE_RULE='이중 Stochastic 새 교차 + SMA20/50/100/200 정배열 롱·역배열 숏 + MFI 롱>50/숏<50 + RVOL≥1.2'
COST_NOTE='편도 수수료0.02%. 기본 차트의 일반 체결 슬리피지와 펀딩·공정가격 강제청산·계약 및 주문 수량 제한은 제외합니다. 보고서의 보수적 비용 표는 편도 총비용0.03%와 첫 봉 가격 손절 추가0.05%를 반영하며 진입 신호는 고정합니다.'


def checks(name):
    if name=='B0':return []
    def c(l,s,lb,sb,cols,unit='',precision=3):return dict(long_label=l,short_label=s,long_bit=lb,short_bit=sb,columns=cols,unit=unit,precision=precision)
    limit=50 if name=='T5' else 35
    out=[c('MFI14 30–80','MFI14 20–70',131072,262144,['mfi']),c('RVOL 0.5–3배','RVOL 0.5–3배',524288,524288,['rvol'],'배'),
         c(f'본선≤{limit}',f'본선≥{100-limit}',1048576,2097152,['main'])]
    if name!='T1':
        distance=c('SMA20 이격 −0.25–1.25 ATR','숏 방향 SMA20 이격 −0.25–1.25 ATR',4194304,8388608,['distance'],' ATR');distance['short_multiplier']=-1
        out += [distance,c('ATR/명목 왕복비용≥3','ATR/명목 왕복비용≥3',1073741824,1073741824,['atr_fee_ratio'],'배')]
    if name in ('T3','T4','T5','T6'):out += [c('ADX≥20·+DI>−DI','ADX≥20·−DI>+DI',16777216,33554432,['adx','plus_di','minus_di']),c('SMA20 3봉 기울기>0','SMA20 3봉 기울기<0',67108864,134217728,['slope'],' ATR')]
    if name=='T4':
        a=c('정배열 시작0–48봉','역배열 시작0–48봉',268435456,536870912,['age_long'],precision=0);a['short_columns']=['age_short'];out.append(a)
    if name=='T6':out.append(c('히스토그램 전봉보다 상승','히스토그램 전봉보다 하락',16384,32768,['hist','hist_previous']))
    return out


def journal(positions,points):
    pm={p['entry_time']:p for p in points};records=[];opened=None
    for t in positions:
        if t['remaining_fraction']:
            opened={k:v for k,v in t.items() if k not in ('legs','remaining_fraction')};continue
        p=pm.get(t['entry_time']);leg=t['legs'][-1]
        records.append(dict(n=len(records)+1,side=t['side'],entry=t['entry_time'],exit=t['exit_time'],signal_time=t['entry_signal_time'],
            exit_signal_time=None if leg['timing']=='intrabar' else t.get('exit_signal_time'),exit_available_time=t['exit_available_time'],exit_timing=leg['timing'],
            ep=t['entry_price'],xp=t['exit_price'],net_pct=t['net_return']*100,account_pct=p['account_return']*100 if p else None,
            cash=p['closed_cash_usdt'] if p else None,capital_executed=p is not None,reason=t['exit_reason'],entry_atr=t['entry_atr'],
            break_even_armed=t.get('break_even_armed',False),stop_triggered=t['stop_triggered'],stop_price=leg['trigger_price']))
    return records,opened


def chart_exports(output,result):
    cfg=verify_frozen(output)['chosen'];variants=[CONFIGS[0]]+([cfg] if cfg['id']!='B0' else [])
    manifests=[];prices={}
    for asset in TARGETS+COMPARISONS:
        dest=output/asset.lower();dest.mkdir(exist_ok=True);packs={'G':{}};exports={'G':[]};summaries=[];sources=[]
        for _,venue,tf,b,path in cases([asset],(5,15)):
            f=build_features(b);x=extra_features(b,f,FEE);take=np.flatnonzero((b.timestamp>=START)&(b.timestamp<END))
            if venue=='mexc' and tf==5:prices[asset]=[float(v) for v in b.close[take][::288]]
            # Base bits contain only original close-known cross/array/filter flags.
            from ppp_backtest import crosses
            up,down=crosses(f['main_c'],f['signal_c'])
            bits=up.astype(np.int64)+2*down+4*f['bull']+8*f['bear']+16*(np.round(f['mfi'],9)>50)+32*(np.round(f['mfi'],9)<50)+64*(np.round(f['rvol'],9)>=1.2)
            columns=['open','high','low','close','sma20','sma50','sma100','sma200','main','signal','bits','atr','mfi','rvol','adx','plus_di','minus_di','distance','slope','age_long','age_short','atr_fee_ratio','hist','hist_previous']
            fields=[b.open,b.high,b.low,b.close,*[smooth(b.close,n) for n in (20,50,100,200)],f['main_c'],f['signal_c'],bits,x['atr'],f['mfi'],f['rvol'],f['adx'],f['plus_di'],f['minus_di'],x['distance'],x['slope'],x['age_long'],x['age_short'],x['atr_fee_ratio'],f['hist'],np.r_[np.nan,f['hist'][:-1]]]
            rows=[[int(v[i]) if j==10 else float(v[i]) if j<4 else round(float(v[i]),8) for j,v in enumerate(fields)] for i in take]
            if not np.isfinite(rows).all():raise ValueError('Unavailable warmup indicator')
            profiles=[]
            for variant in variants:
                stats,pos,points,signals,conditions,_=evaluate(b,f,x,variant,START,END)
                records,opened=journal(pos,points);state,cash,terminal=selective_states(b,signals,records,opened,start=START,end=END,initial=1000.)
                summary=dict(model='G',profile=variant['id'],venue=venue,timeframe_minutes=tf,six_months=True,full_period=True,**stats);summaries.append(summary)
                exact=next(r for r in result['rows'] if r['asset']==asset and r['venue']==venue and r['timeframe_minutes']==tf and r['variant']==variant['id'] and r['segment']=='full' and r['cost']=='nominal')
                for k in stats:
                    if stats[k]!=exact[k]:raise ValueError('Chart recomputation differs: '+k)
                masks=(state|conditions|bits)[take].astype('<i4')
                pp=dict(profile=variant['id'],risk_profile=variant['risk'],policy='S2',label=variant['label'],summary=summary,trades=records,open_position=opened,streaks=loss_streaks(records),
                        decision_states=masks.tolist(),cash_at_bar_open=cash[take].tolist(),terminal_cash=terminal,
                        entry_rule=BASE_RULE if variant['entry']=='B0' else '새 이중 Stochastic 교차 + SMA 정·역배열 유지 · '+ ' / '.join(c['long_label']+'(롱)' if c['long_label']!=c['short_label'] else c['long_label'] for c in checks(variant['entry']))+' · 숏은 아래 판정표 기준',
                        audit=dict(state_sha256=hashlib.sha256(masks.tobytes()).hexdigest(),last_cash=float(cash[take[-1]]),entry_opportunities_preserved=True))
                if variant['entry']!='B0':pp.update(entry_checks=checks(variant['entry']),rvol_limits=[.5,3],mfi_limits=[20,30,70,80],show_adx=variant['entry'] in ('T3','T4','T5','T6'))
                profiles.append(pp)
            key=f'{venue}-{tf}';meta=dict(key=key,venue=venue,symbol=asset+('_USDT' if venue=='mexc' else 'USDT'),timeframe_minutes=tf,start=START,end=END,step=b.seconds,start_kst=kst(START),end_kst=kst(END),full_period=True,six_months=True,count=len(rows),columns=columns)
            packed=dict(**meta,rows=rows,profiles=profiles);encoded=encode(packed);packs['G'][key]=encoded;exports['G'].append(meta)
            (dest/f'G-{key}.json.gz').write_bytes(base64.b64decode(encoded));sources.append(dict(venue=venue,timeframe_minutes=tf,full_period=True,start_kst=kst(START)))
        args=SimpleNamespace(asset=asset,models=['G'],profiles=[v['id'] for v in variants],fee=FEE,initial=1000.,leverage=10.,output=dest,
            profile_labels={v['id']:v['label'] for v in variants},default_profile='B0',slippage_note=COST_NOTE,
            experimental_profiles=[cfg['id']] if cfg['id']!='B0' else [],qualified_training=result['selection']['qualified_training'])
        export_reports(args,dict(start_kst=kst(START),end_exclusive_kst=kst(END),summaries=summaries,provenance=sources),exports,packs)
        old=dest/f'{asset.lower()}-g-strategy.html';new=dest/f'{asset.lower()}-trend-volume.html';old.rename(new)
        page=dest/'index.html';page.write_text(page.read_text().replace(old.name,new.name))
        manifest=dest/'html-manifest.json';meta_manifest=json.loads(manifest.read_text());meta_manifest['files'][0]['file']=new.name;manifest.write_text(json.dumps(meta_manifest,ensure_ascii=False,indent=2)+'\n')
        manifests.append(dict(asset=asset,file=str(new.relative_to(output)),sha256=hashlib.sha256(new.read_bytes()).hexdigest(),bytes=new.stat().st_size))
        print('Chart complete:',asset,flush=True)
    (output/'chart-manifest.json').write_text(json.dumps(manifests,ensure_ascii=False,indent=2)+'\n')
    return prices


def normalized_plot(prices,output):
    # Daily observations are for this normalized overview only. Review charts
    # retain every native 5/15-minute candle.
    os.environ.setdefault('MPLCONFIGDIR',str((output/'matplotlib-cache').resolve()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from datetime import datetime,timedelta
    colors={'WLD':'#d75e50','ZEC':'#29a7ae'};fig,ax=plt.subplots(figsize=(11,3.8),layout='constrained')
    for a,color in colors.items():
        v=np.array(prices[a])/prices[a][0]*100;t=[datetime(2026,4,14)+timedelta(days=i) for i in range(len(v))]
        ax.plot(t,v,label=a,color=color,linewidth=1.8)
    ax.axhline(100,color='#77818c',linestyle='--',linewidth=.8);ax.set_ylabel('First observation = 100');ax.set_title('MEXC 5m: daily first-candle close (KST)');ax.legend();ax.grid(alpha=.2)
    p=output/'wld-zec-normalized.png';fig.savefig(p,dpi=150);plt.close(fig)
    return '<img style="width:100%;height:auto" alt="WLD ZEC 시작가격100 일별 비교" src="data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()+'">'


def summary_html(output,result,prices):
    chosen=result['selection']['chosen'];vid=chosen['id'];rows=result['rows'];diag=json.loads((output/'entry-diagnostics.json').read_text());score=result['selection']['training_score']
    fmt=lambda v:'—' if v is None else f'{v:,.2f}' if abs(v)>=.01 else f'{v:.3g}'
    tr=lambda values:'<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in values)+'</tr>'
    table=lambda headers,body:'<div class="scroll"><table><thead>'+tr(headers)+'</thead><tbody>'+''.join(body)+'</tbody></table></div>'
    full=[r for r in rows if r['segment']=='full' and r['cost']=='nominal']
    target=[r for r in full if r['role']=='target'];new=[r for r in target if r['variant']==vid];old=[r for r in target if r['variant']=='B0']
    p=[r for r in new if r['avg_net_return_pct'] is not None and r['avg_net_return_pct']>0 and (r['profit_factor'] or 0)>1]
    archive=ROOT/'user_data/backtest_results/ppp-selective-2026-10-14/ppp-research-report.html'
    original=archive.read_text();banner='<aside style="padding:18px;border:2px solid #e5ab50">초안 기록 보관 · A/B/C/D/E/F/H는 draft입니다. 이전 G 결과는 현재의 추세·거래량 전략 기준 기록입니다. <a href="index.html">활성 연구로 돌아가기</a></aside>'
    original=original.replace('<body>', '<body>'+banner,1);(output/'draft-history.html').write_text(original)
    model_archive=ROOT/'user_data/backtest_results/ppp-wld-2026-10-14'
    for m in ['c','e']:shutil.copy2(model_archive/f'wld-{m}-strategy.html',output/f'draft-wld-{m}.html')
    sections=['<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>추세·거래량 전략 연구</title>',
        '<style>:root{color-scheme:light dark}body{font:16px/1.65 system-ui;max-width:1250px;margin:30px auto;padding:0 18px}h1{font-size:30px}h2{font-size:22px;margin-top:32px}a{color:#268fb5}.scroll{overflow:auto}table{border-collapse:collapse;white-space:nowrap;width:100%;font-size:14px}td,th{padding:9px;border-bottom:1px solid #8885;text-align:left}svg{width:100%;max-height:360px}svg text{fill:currentColor;font:14px system-ui}.notice{border-left:4px solid #c89134;padding:10px 18px;background:#b98b2411}select,input{font:inherit;padding:8px;border:1px solid #8885;margin:4px;border-radius:6px}.cards{display:flex;flex-wrap:wrap;gap:12px}.cards a{padding:12px 18px;border:1px solid #8885;border-radius:8px}</style>',
        '<h1>추세·거래량 전략</h1><p>기존 G를 이 이름으로 통일했습니다. 기준형과 초입 개선형을 비교하며, 다른 지표 시안은 삭제하지 않고 draft로 보관합니다.</p>',
        '<div class="notice">기존 기준형을 활성 기준으로 유지합니다. 초입 개선형은 비교용 연구 후보이며, 여러 코인에 안정적으로 맞는 지표로 확정하지 않았습니다. '+('선택 기준을 통과했습니다.' if result['selection']['qualified_training'] else 'BTC·ETH 선택 기준에도 불합격했습니다.')+'</div>',
        '<p>2026-04-14 00:00 → 2026-10-14 00:00 KST 직전 · 6개월 · 명목 편도0.02% · 독립 초기$1000·10배 전액 복리. 손익비는 평균 수익÷평균 손실(수수료 포함,1배 거래 수익률), PF는 수익 합÷손실 합입니다. 종료 자산은 미청산 평가를 포함합니다.</p>',
        '<h2>전체 차트로 검토</h2><p>각 코인의 6개월 전체 5·15분봉을 MEXC와 Binance에서 볼 수 있습니다. 기준형/초입 개선형 선택, 모든 수익·손실 거래, 미진입 교차 및 그 이유, SMA·이중 Stochastic·MFI·거래량·ATR를 표시합니다. 아래 백테스트 표에는 Binance1·3분도 포함됩니다.</p>',
        '<div class="cards">'+''.join(f'<a href="{a.lower()}/{a.lower()}-trend-volume.html">{a}'+(' · 비교용' if a in COMPARISONS else '')+'</a>' for a in TARGETS+COMPARISONS)+'</div>',
        '<h2>어디가 문제였나</h2><p>기존 MFI50·거래량1.2 확인과 이평선 완전 정렬이 성립할 때는 이미 가격이 진행된 경우가 많았습니다. 그러나 WLD가 ZEC보다 늦은 진입 비중이 높지는 않았습니다. 늦은 진입 하나만으로 차이를 설명할 수 없습니다. 아래는 첫 봉 가격 손절을 적용하기 전 MEXC5분 기준형 거래의 진단입니다.</p>',
        table(['코인','거래','SMA20≥1.5ATR 이격 %','본선 진행≥65 %','평균 수익 %','평균 손실 %','거래당 순기대값 %','승리거래 MFE 중앙 %'],[tr([d['asset'],d['baseline_stats']['trades'],fmt(d['groups']['all']['rates']['extended']),fmt(d['groups']['all']['rates']['late_c_phase']),fmt(d['baseline_stats']['avg_win_pct']),fmt(d['baseline_stats']['avg_loss_pct']),fmt(d['baseline_stats']['avg_net_return_pct']),fmt(d['groups']['winners']['medians']['mfe_pct'])]) for d in diag]),
        '<p>본선 진행도는 롱 본선값·숏100−본선값입니다. MFE는 보유 구간에서 유리하게 움직인 최대 폭으로 사후 진단용이며 신호 계산에는 쓰지 않습니다. ZEC는 승리 거래의 평균 수익이 더 컸고 평균 손실은 WLD보다 작았습니다. 두 코인의 승리 거래 MFE 중앙값은 비슷해, 단순히 변동폭이 크다는 사실만으로 차이를 설명할 수 없습니다. 아래 가격 비교는 각 날짜의 첫5분봉 종가 표본입니다. 실제 캔들 차트에는 전체 원본 봉을 유지합니다.</p>'+normalized_plot(prices,output),
        '<h2>고정한 개선 규칙</h2><p>'+escape(chosen['label'])+'입니다. 완전 SMA 정·역배열과 새 교차를 유지하며 추가 조건은 '+escape(' / '.join(c['long_label']+'(롱)·'+c['short_label']+'(숏)' for c in checks(chosen['entry'])))+'입니다. 청산은 선택형 이름의 규칙과 반대 교차를 유지합니다. 종가 청산은 다음 봉 시가, 첫 진입 봉만1% 가격 손절입니다. 정렬 이전으로 신호를 앞당기는 실험은 하지 않았습니다.</p>',
        '<p>19개 고정 시안을 BTC·ETH 첫4개월 8조합으로 비교하고 후보를1개 고정한 뒤 BNB·SOL·XRP에 적용했습니다. '+f'선택형은 명목{score["positive_cases"]}/8조합 양수, 보수적 비용{score["stress_positive_cases"]}/8조합 양수·중앙PF{score["median_pf"]:.3f}입니다. '+('합격 기준을 통과했습니다.' if result['selection']['qualified_training'] else '합격 기준(6/8·5/8·PF1.1)에 못 미쳤습니다.')+' 이전에 본 코인·기간이므로 마지막2개월은 소급 시간 분할 비교입니다. 현재 시총 중심으로 대상을 정했으며 과거 구성종목·상장폐지 전체 검증은 아닙니다.</p>',
        '<h2>대형 코인 공통성 확인</h2><p>'+f'고정 후보의 명목6개월 순기대값 양수·PF&gt;1은 대상30조합 중{len(p)}개입니다. '+f'종료 자산 중앙값 기준형${fmt(float(np.median([r["end_marked_equity_usdt"] for r in old])))} → 개선형${fmt(float(np.median([r["end_marked_equity_usdt"] for r in new])))}. '+'승률만 높이는 것으로는 충분하지 않으며 손익비·거래 수·낙폭·비용을 함께 확인해야 합니다.</p>',
        '<p>거래소·주기마다 독립 계좌입니다. 아래 MEXC5분은 사용자가 요청한 거래소의 대표 비교이며 최고 결과만 고르지 않았습니다.</p>',
        table(['코인','방식','거래','승률 %','손익비','PF','종료 자산 $','폐쇄 DD %','OHLC DD 상한 %','가격자산0접촉'],[tr([r['asset'],'기준형' if r['variant']=='B0' else '초입 개선형',r['trades'],fmt(r['win_rate_pct']),fmt(r['payoff_ratio']),fmt(r['profit_factor']),fmt(r['end_marked_equity_usdt']),fmt(r['closed_drawdown_pct']),fmt(r['ohlc_drawdown_upper_bound_pct']),r['price_zero_equity_events']]) for r in full if r['venue']=='mexc' and r['timeframe_minutes']==5]),
        '<p>PF가1을 넘더라도10배 복리 자산이 감소할 수 있습니다. 평균 거래 수익은 산술값이지만 계좌는 각 거래 손익을 곱해 누적하므로 큰 손실과 변동성이 자산을 깎습니다. 기준형의 ZEC 고수익을 개선형이 유지하는지도 아래 표에서 확인해야 합니다.</p><h2>전체 결과 비교</h2><label>코인<select id="asset"><option value="">전체</option>'+''.join(f'<option>{a}</option>' for a in TARGETS+COMPARISONS)+'</select></label><label>기간<select id="segment"><option value="full">6개월</option><option value="first4">첫4개월</option><option value="last2">마지막2개월</option></select></label><label>비용<select id="cost"><option value="nominal">편도0.02%</option><option value="stress">편도 총0.03%·손절+0.05%</option></select></label>',
        '<div class="scroll"><table id="results"><thead>'+tr(['코인','거래소','분','방식','거래','승률 %','손익비','PF','거래당 순기대값 %','종료 자산 $','폐쇄 DD %','OHLC DD 상한 %','0접촉'])+'</thead><tbody></tbody></table></div>',
        '<h2>초안과 원본 기록</h2><p><a href="draft-history.html">전체 이전 연구 보관(A–H·리스크·복리)</a> · <a href="draft-wld-c.html">이중 Stochastic 시안·WLD(draft)</a> · <a href="draft-wld-e.html">MACD 결합 시안·WLD(draft)</a> · <a href="validation.csv">전체 결과 CSV</a> · <a href="trades.csv">거래 기록 CSV</a> · <a href="training.csv">19시안 선택 비교</a> · <a href="selection-frozen.json">고정 후보·선택 기준</a> · <a href="entry-diagnostics.csv">진입 진단</a></p>',
        '<p>데이터는 Binance 공식 USDT 선물 자료와 MEXC 공개 계약 캔들입니다. 1·3분은 Binance 원본1분을 집계했고 MEXC5·15분은 해당 거래소 원본입니다. 모든 사례가 6개월 연속 자료와 지표 준비 구간을 갖습니다. 펀딩·강제청산·최소 계약수량·일반 체결 슬리피지는 제외합니다. 자산0접촉 이후 자산은 실거래 지속 가능 결과가 아닙니다. 큰 수익 숫자도 동일하게 이론 모형입니다.</p>',
        '<script id="rows" type="application/json">'+json.dumps(rows,ensure_ascii=False).replace('<','\\u003c')+'</script><script>const rows=JSON.parse(document.getElementById("rows").textContent),e=id=>document.getElementById(id),f=v=>v==null?"—":v>0&&v<.01?v.toPrecision(3):v.toLocaleString("ko-KR",{maximumFractionDigits:3});function render(){const filtered=rows.filter(r=>(!e("asset").value||r.asset===e("asset").value)&&r.segment===e("segment").value&&r.cost===e("cost").value);e("results").querySelector("tbody").replaceChildren(...filtered.map(r=>{const tr=document.createElement("tr");[r.asset,r.venue,r.timeframe_minutes,r.variant==="B0"?"기준형":"초입 개선형",r.trades,f(r.win_rate_pct),f(r.payoff_ratio),f(r.profit_factor),f(r.avg_net_return_pct),f(r.end_marked_equity_usdt),f(r.closed_drawdown_pct),f(r.ohlc_drawdown_upper_bound_pct),r.price_zero_equity_events].forEach(v=>{const td=document.createElement("td");td.textContent=v;tr.append(td)});return tr}))}for(const id of ["asset","segment","cost"])e(id).addEventListener("change",render);render();</script></html>']
    (output/'index.html').write_text('\n'.join(sections))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-largecap-2026-10-14');a=p.parse_args()
    result=json.loads((a.output/'validation.json').read_text());prices=chart_exports(a.output,result);summary_html(a.output,result,prices)
    for name in ['trend-volume-baseline-v6.pine','trend-volume-early-experimental-v6.pine']:
        shutil.copy2(ROOT/'docs/tradingview/ppp-trend-volume'/name,a.output/name)
    page=a.output/'index.html';s=page.read_text().replace('<h2>초안과 원본 기록</h2>','<h2>Pine Script</h2><p><a href="trend-volume-baseline-v6.pine" download>추세·거래량 기준형</a> · <a href="trend-volume-early-experimental-v6.pine" download>초입·이격 제한 실험형</a>. 진입 후보 표시용 지표이며 실제 주문·포지션을 추적하지 않습니다. TradingView 컴파일 실행은 확인하지 않았습니다.</p><h2>초안과 원본 기록</h2>')
    page.write_text(s)


if __name__=='__main__':main()
