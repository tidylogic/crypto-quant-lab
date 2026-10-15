#!/usr/bin/env python3
"""Render the frozen SMA entry comparison and native minute review charts."""
from __future__ import annotations
import argparse
import hashlib
import json
from html import escape
from pathlib import Path
from types import SimpleNamespace
import numpy as np

from ppp_backtest import ROOT, START, END
from ppp_combo_backtest import build_features
from ppp_sma_entry_comparison import SETS, MODES, MODE_NAMES, DEFAULT_OUTPUT, digest
from ppp_support_ladder import market_cases, prepare, simulate_ladder
from ppp_largecap_research import TARGETS, COMPARISONS
from ppp_selective_backtest import replay_selective
from ppp_support_report import records_for
from ppp_asset_selective import selective_states
from ppp_asset_research import encode, export_reports, kst, loss_streaks

FILL_NOTE='신호와 SMA는 선택한 기준 타임프레임의 확정 봉으로 계산합니다. 즉시형은 신호 봉 마감 직후1분봉 시가, 확인형은 이후1분봉의 이평선 접촉·종가 회복을 확인한 다음1분봉 시가에 진입합니다. 두 방식의 일반 청산은 기준 봉 마감의 두 번째 SMA 실패 또는 반대 교차로 같습니다. S2는 실제 진입이 포함된 기준 봉의1% 장중 가격 손절입니다.'
COST_NOTE='편도0.02%, 초기$1000·10배 전액 복리. 각 코인·주기는 독립 계좌입니다. 펀딩·일반 슬리피지·공정가격 강제청산·최소 주문수량은 제외합니다. 비용 강화는 편도0.03%·S2 손절 추가0.05%입니다. 가격 자산0접촉 이후 계좌 경로는 실거래 가능 성과로 해석하지 않습니다.'


def charts(output,result):
    lookup={(r['asset'],r['venue'],r['timeframe_minutes'],r['sma_set'],r['mode']):r for r in result['rows'] if r['cost']=='nominal'}
    packs={(a,s):{'G':{}} for a in TARGETS+COMPARISONS for s in SETS}
    metas={key:{'G':[]} for key in packs};summaries={key:[] for key in packs};provenance={key:[] for key in packs};audit=[]
    for asset,venue,tf,m,parent,start,_,_ in market_cases(TARGETS+COMPARISONS):
        f=build_features(parent)
        for set_id,periods in SETS.items():
            b,d=prepare(m,parent,start,END,features=f,levels=periods);profiles=[]
            columns=['open','high','low','close',*['sma'+str(n) for n in periods],'main','signal','bits','atr','mfi','rvol']
            matrix=np.column_stack([b.open,b.high,b.low,b.close,*d['mas'].T,d['main'],d['signal'],d['base_bits'],d['atr'],d['mfi'],d['rvol']])
            if not np.isfinite(matrix).all():raise ValueError(f'Nonfinite chart input {asset} {venue} {tf} {set_id}')
            matrix[:,4:]=np.round(matrix[:,4:],8);native=matrix.tolist()
            for mode,cfg in MODES.items():
                sim=simulate_ladder(b,d,'B0',end=END,trace=True,config=cfg)
                stats,points=replay_selective(b,sim['positions'])
                expected=lookup[(asset,venue,tf,set_id,mode)]
                assert all(stats[k]==expected[k] for k in stats),'Chart and research statistics differ'
                records,opened=records_for(sim,points)
                actual=sim['states'];signals=dict(long_entry=(actual&1024)!=0,short_entry=(actual&2048)!=0)
                reconstructed,cash,terminal=selective_states(b,signals,records,opened,start=start,end=END,initial=1000.)
                mask=128|256|512|1024|2048|4096|8192|65536
                assert np.array_equal(actual&mask,reconstructed&mask),'Chart and journal states differ'
                summary=dict(expected,model='G',profile=mode,six_months=start==START);summaries[(asset,set_id)].append(summary)
                rule='SMA'+'/'.join(map(str,periods))+' 정·역배열 + 이중 Stochastic 새 교차 + MFI50 + RVOL1.2'
                if cfg['wait']:rule+=' → '+'→'.join(map(str,periods))+' 순차 접촉·1분 종가 회복 확인 (신호3봉 유효)'
                rule+=' · 공통 청산: 기준 봉 SMA'+str(periods[1])+' 실패 또는 반대 교차 + 첫 진입 봉1% 손절'
                profiles.append(dict(profile=mode,label=MODE_NAMES[mode],risk_profile='R2',policy='S2',summary=summary,trades=records,
                                     open_position=opened,streaks=loss_streaks(records),decision_states=actual.tolist(),cash_at_bar_open=cash.tolist(),
                                     terminal_cash=terminal,entry_mode='ladder' if cfg['wait'] else 'direct',entry_rule=rule,show_atr=True,show_protection=False,
                                     support_index=sim['support_index'].tolist(),margin=sim['margin'].tolist(),source_time=sim['source_time'].tolist(),
                                     protected_stop=sim['protected_stop'].tolist(),stop_minutes=tf))
                audit.append(dict(asset=asset,venue=venue,timeframe_minutes=tf,sma_set=set_id,mode=mode,stats_match=True,states_match=True))
            key=f'{venue}-{tf}';meta=dict(key=key,venue=venue,symbol=asset+('_USDT' if venue=='mexc' else 'USDT'),timeframe_minutes=tf,
                                        execution_timeframe_minutes=1,signal_step=parent.seconds,start=start,end=END,step=60,
                                        start_kst=kst(start),end_kst=kst(END),full_period=start==START,six_months=start==START,count=len(native),columns=columns)
            packs[(asset,set_id)]['G'][key]=encode(dict(**meta,rows=native,profiles=profiles));metas[(asset,set_id)]['G'].append(meta)
            provenance[(asset,set_id)].append(dict(venue=venue,timeframe_minutes=tf,full_period=start==START,start_kst=kst(start)))
        print('Chart payload ready:',asset,venue,tf,flush=True)
    files=[]
    for (asset,set_id),pack in packs.items():
        periods=SETS[set_id];dest=output/asset.lower()/('sma'+set_id);dest.mkdir(parents=True,exist_ok=True)
        args=SimpleNamespace(asset=asset,models=['G'],profiles=list(MODES),fee=.0002,initial=1000.,leverage=10.,output=dest,
                             ma_periods=periods,model_name='추세·거래량 · SMA'+'/'.join(map(str,periods)),
                             profile_labels=MODE_NAMES,default_profile='direct',experimental_profiles=list(MODES) if set_id=='30' else ['confirmed'],
                             native_execution=True,fill_note=FILL_NOTE,slippage_note=COST_NOTE,default_market='binance_um-5')
        export_reports(args,dict(start_kst=kst(START),end_exclusive_kst=kst(END),summaries=summaries[(asset,set_id)],provenance=provenance[(asset,set_id)]),metas[(asset,set_id)],pack)
        path=dest/(asset.lower()+'-g-strategy.html')
        files.append(dict(asset=asset,sma_set=set_id,file=path.relative_to(output).as_posix(),sha256=digest(path),bytes=path.stat().st_size))
    (output/'chart-manifest.json').write_text(json.dumps(files,ensure_ascii=False,indent=2))
    (output/'chart-validation.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2))


def figures(output,result):
    import os
    os.environ.setdefault('MPLCONFIGDIR',str(output/'plot-cache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    assets=TARGETS+COMPARISONS;keys=[(a,t) for a in assets for t in [1,3,5,15]]
    lookup={(r['asset'],r['timeframe_minutes'],r['sma_set'],r['mode']):r for r in result['rows'] if r['venue']=='binance_um' and r['cost']=='nominal'}
    variants=[('20','direct'),('20','confirmed'),('30','direct'),('30','confirmed')]
    labels=['20-set\nImmediate','20-set\nConfirmed','30-set\nImmediate','30-set\nConfirmed']
    def plot(specs,filename):
        fig,axes=plt.subplots(1,len(specs),figsize=(5*len(specs),13),layout='constrained')
        for ax,(key,title,vmin,vmax,cmap,log) in zip(np.atleast_1d(axes),specs):
            values=np.array([[lookup[(a,t,s,m)][key] if lookup[(a,t,s,m)][key] is not None else np.nan for s,m in variants] for a,t in keys])
            colors=np.log10(np.maximum(values,1e-15)) if log else values
            norm=TwoSlopeNorm(vmin=vmin,vcenter=1.,vmax=vmax) if key=='strategy_profit_factor' else None
            img=ax.imshow(np.ma.masked_invalid(colors),aspect='auto',cmap=cmap,norm=norm,**({} if norm else dict(vmin=vmin,vmax=vmax)))
            ax.set_xticks(range(4),labels,fontsize=9);ax.set_yticks(range(len(keys)),[a+' '+str(t)+'m' for a,t in keys],fontsize=9);ax.set_title(title,fontsize=12)
            for i in range(len(keys)):
                for j in range(4):
                    v=values[i,j];text='—' if not np.isfinite(v) else f'{v:.2g}' if log else f'{v:.2f}'
                    rgba=img.cmap(img.norm(colors[i,j])) if np.isfinite(v) else (1,1,1,1)
                    ink='white' if .3*rgba[0]+.6*rgba[1]+.1*rgba[2]<.45 else 'black'
                    ax.text(j,i,text,ha='center',va='center',fontsize=8,color=ink)
            fig.colorbar(img,ax=ax,shrink=.6)
        fig.suptitle('G trend/volume | Native Binance UM | 6 months | Fee 0.02% per side\n20/50/100/200 vs 30/60/120/240 | Identical source-close exits + entry-candle S2',fontsize=12)
        fig.savefig(output/filename,dpi=150);plt.close(fig)
    plot([('strategy_win_rate_pct','Net win rate (%)',0,65,'YlGnBu',False),('strategy_payoff_ratio','Average win / average loss',0,5,'YlOrRd',False),('strategy_profit_factor','Profit factor (1 = break-even)',0,3,'RdYlGn',False)],'sma-entry-win-payoff.png')
    plot([('end_marked_equity_usdt','Independent $1000 / 10x ending equity (log10 color)',-6,5,'RdYlGn',True),('closed_drawdown_pct','Closed account drawdown (%)',0,100,'YlOrRd',False)],'sma-entry-capital-drawdown.png')


def report(output,result):
    fmt=lambda v:'—' if v is None else f'{v:.3g}' if 0<abs(v)<.01 else f'{v:,.2f}'
    tr=lambda cells:'<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in cells)+'</tr>'
    summaries=[]
    for scope,title in [('highercap5','대형5코인: BTC·ETH·BNB·SOL·XRP'),('all7','전체7코인: 위5개 + WLD·ZEC')]:
        rows=[r for r in result['aggregates'] if r['scope']==scope and r['cost']=='nominal']
        summaries.append('<h2>'+title+'</h2><p>거래 수로 합산한 순승률·손익비·PF입니다. 공동 자금 포트폴리오 수익률이 아닙니다.</p><div class="scroll"><table><thead>'+tr(['분','SMA','진입','거래','승률 %','손익비','PF','평균 순손익 %'])+'</thead><tbody>'+''.join(tr([r['timeframe_minutes'],r['sma_set']+'세트',MODE_NAMES[r['mode']],r['trades'],fmt(r['win_rate_pct']),fmt(r['payoff_ratio']),fmt(r['profit_factor']),fmt(r['avg_net_return_pct'])]) for r in rows)+'</tbody></table></div>')
    chart_links=[]
    for asset in TARGETS+COMPARISONS:
        links=['<a href="'+asset.lower()+'/sma'+s+'/'+asset.lower()+'-g-strategy.html">SMA'+'/'.join(map(str,SETS[s]))+'</a>' for s in SETS]
        chart_links.append('<div class="card"><strong>'+asset+'</strong> · '+' · '.join(links)+'</div>')
    page='''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>추세·거래량 · SMA 세트와 두 진입 방식 비교</title><style>
:root{color-scheme:light dark}body{font:15px/1.7 system-ui;max-width:1400px;margin:24px auto;padding:0 16px}h1{font-size:27px}h2{font-size:22px;margin-top:30px}a{color:#328dc9}.notice{background:#2783a515;border-left:4px solid #328dc9;padding:14px 18px;margin:18px 0}.scroll{overflow:auto}table{border-collapse:collapse;min-width:100%;font-size:13px;white-space:nowrap}th,td{padding:8px;border:1px solid #9995;text-align:right}th{background:#8881}td.good{background:#259c381a}td.bad{background:#e34b3015}select{font:inherit;max-width:100%;padding:8px;margin:4px;border:1px solid #8886;border-radius:6px}img{display:block;width:min(100%,1100px);height:auto;margin:18px auto}.card{padding:10px;border:1px solid #8885;border-radius:8px;margin:7px 0}.filters{display:flex;flex-wrap:wrap;gap:8px}label{font-size:13px}@media(max-width:600px){body{padding:0 10px;font-size:14px}h1{font-size:23px}.filters label{flex:1 1 45%}select{display:block;width:100%;margin-left:0}}</style></head><body>
<h1>추세·거래량 전략 · SMA와 진입 확인 비교</h1><p>2026-04-14 00:00 → 2026-10-14 00:00 KST · 기존 G/R2+S2는 유지합니다.</p>
<div class="notice"><strong>사용자 지정 두 방식</strong><br>① 신호 타임프레임 봉 마감 직후 다음1분봉 시가 진입<br>② 같은 신호 이후 이평선 지지·저항을1분봉 접촉·종가 회복으로 확인한 다음1분봉 시가 진입<br>공통 청산: 신호 타임프레임 봉 마감의 두 번째 SMA 실패 또는 반대 교차. 20세트는 SMA50, 30세트는 SMA60입니다. 별도 첫 진입 기준 봉1% 손절(S2)은 장중 작동합니다.</div>
<p>진입 전 지지선 순서는20→50→100→200 또는30→60→120→240입니다. 허용 폭 ATR14×0.1, 신호 유효기간3개 기준 봉, 신호당1회 진입입니다. 롱은 접촉 뒤 선+허용 폭 이상 양봉 마감, 숏은 반대입니다. 실제 진입 시에도 완전 정·역배열이어야 합니다. 이평선과 원 지표는 마감한 기준 봉 값만 쓰며, 확인형의1분봉은 지지·저항 회복 판단용입니다. 손절 후 다음 선 재시도는 이번 비교에 추가하지 않았습니다.</p>
<p>승률·손익비·PF는 수수료 후 전체 전략의 종료 거래 기준입니다. 계좌 수익·낙폭은 실제 자금으로 실행 가능한 거래에 대한 별도10배 복리 모형입니다. 전체 거래 수와 자금 실행 거래 수, 미청산 포지션, 자산0접촉을 구분합니다. '''+escape(COST_NOTE)+'''</p>
<h2>코인별 전체 거래 차트</h2>'''+''.join(chart_links)+'''
<h2>통계·색상 비교</h2><p>색깔은 비교를 돕는 히트맵이며 정규분포 그림이 아닙니다. 원본 그림을 눌러 크게 보거나 자료실의 통계·그림 메뉴에서 확대할 수 있습니다. 무거래·정의되지 않는 값은 빈칸입니다.</p>
<a href="sma-entry-win-payoff.png"><img src="sma-entry-win-payoff.png" alt="이평선·진입 방식별 승률 손익비 PF 비교" loading="lazy"></a><a href="sma-entry-capital-drawdown.png"><img src="sma-entry-capital-drawdown.png" alt="종료 잔고·낙폭 비교" loading="lazy"></a>
'''+''.join(summaries)+'''
<h2>개별 결과 필터</h2><div class="filters"><label>코인<select id="asset"><option value="">전체</option>'''+''.join('<option>'+a+'</option>' for a in TARGETS+COMPARISONS)+'''</select></label><label>자료<select id="coverage"><option value="full">Binance 6개월</option><option value="short">MEXC 짧은 자료</option></select></label><label>신호 주기<select id="tf"><option value="">전체</option><option>1</option><option>3</option><option selected>5</option><option>15</option></select></label><label>SMA<select id="set"><option value="">모두</option><option value="20">20·50·100·200</option><option value="30" selected>30·60·120·240</option></select></label><label>비용<select id="cost"><option value="nominal">편도0.02%</option><option value="stress">편도0.03%·손절 추가0.05%</option></select></label></div><p id="row-count"></p>
<div class="scroll"><table id="results"><thead>'''+tr(['코인','분','SMA','진입','시작 KST','전략/자금 거래','순승률 %','손익비','PF','종료 자산 $','폐쇄 DD %','OHLC DD 상한 %','0접촉','노출 %','진입 대기 분','유효기간 취소'])+'''</thead><tbody></tbody></table></div>
<h2>해석과 검증</h2><div class="notice">지지 확인형은 거래 수가 크게 줄 수 있습니다. 잔고와 낙폭 개선을 타점 개선으로 단정하지 말고 거래 수·노출 시간·대기 만료와 함께 보세요. 이미 관측한 기간에 대한 소급 연구이며 코인별 최고값을 골라 공통 전략으로 승격하지 않습니다. MEXC 짧은 구간을6개월로 표시하거나 다른 거래소 가격으로 채우지 않습니다.</div>
<p>원본 기준형 재현 '''+str(result['validation']['historical_baseline_matches'])+'''개 일치 · 신호·체결·손절·비용·중복 포지션 검증 '''+str(result['validation']['journal_positions'])+'''개 기록 · 입력 '''+str(result['validation']['source_cases'])+'''개 시장·주기.</p>
<p><a href="summary.csv">전체 집계 CSV</a> · <a href="aggregate.csv">거래 수 가중 합산 CSV</a></p>
<script id="rows" type="application/json">'''+json.dumps(result['rows'],ensure_ascii=False).replace('<','\\u003c')+'''</script><script>
(()=>{const rows=JSON.parse(document.getElementById('rows').textContent),e=id=>document.getElementById(id),f=v=>v==null?'—':v!==0&&Math.abs(v)<.01?v.toPrecision(3):v.toLocaleString('ko-KR',{maximumFractionDigits:3}),names={direct:'즉시',confirmed:'1분 지지 확인'};
function render(){const group=rows.filter(r=>(!e('asset').value||r.asset===e('asset').value)&&r.full_period===(e('coverage').value==='full')&&r.cost===e('cost').value&&(!e('tf').value||r.timeframe_minutes===Number(e('tf').value))&&(!e('set').value||r.sma_set===e('set').value));e('row-count').textContent=group.length+'개 비교';e('results').querySelector('tbody').replaceChildren(...group.map(r=>{const tr=document.createElement('tr');[r.asset,r.timeframe_minutes,r.periods,names[r.mode],r.start_kst,r.strategy_trades+'/'+r.trades,f(r.strategy_win_rate_pct),f(r.strategy_payoff_ratio),f(r.strategy_profit_factor),f(r.end_marked_equity_usdt),f(r.closed_drawdown_pct),f(r.ohlc_drawdown_upper_bound_pct),r.price_zero_equity_events,f(r.exposure_pct),f(r.mean_entry_delay_minutes),r.expired_setups].forEach((v,i)=>{const td=document.createElement('td');td.textContent=v;if(i===8&&r.strategy_profit_factor!=null)td.className=r.strategy_profit_factor>=1?'good':'bad';tr.append(td)});return tr}));}for(const id of ['asset','coverage','tf','set','cost'])e(id).onchange=render;render();})();</script></body></html>'''
    (output/'index.html').write_text(page)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=DEFAULT_OUTPUT);parser.add_argument('--skip-charts',action='store_true')
    args=parser.parse_args();result=json.loads((args.output/'results.json').read_text())
    for name,sha in result['protocol']['dependencies'].items():assert digest(ROOT/'scripts'/name)==sha,'Frozen trading source changed: '+name
    if not args.skip_charts:charts(args.output,result)
    figures(args.output,result);report(args.output,result)


if __name__=='__main__':main()
