/* Trade journal UI. The strategy's existing focusTrade performs closed-trade zooms. */
(()=>{
'use strict';
const el=id=>document.getElementById(id),root=el('research');
if(!root)return;
const journal=document.createElement('details');journal.id='gallery-trades';
journal.innerHTML='<summary>거래 목록</summary><div class="journal-filters"><label>방향<select id="gallery-side"><option value="all">롱·숏 전체</option><option value="long">롱</option><option value="short">숏</option></select></label><label>결과<select id="gallery-result"><option value="all">수익·손실 전체</option><option value="wins">수익</option><option value="losses">손실</option><option value="open">미청산</option></select></label><span id="gallery-trade-count" role="status"></span></div><div class="journal-scroll"><table aria-label="포지션 진입 내역"><thead><tr><th>거래 / 집행</th><th>방향</th><th>진입 시각 (KST)</th><th>진입 가격</th><th>청산 시각 (KST)</th><th>청산 가격</th><th>순수익률 (1배)</th><th>계좌 수익률</th><th>청산 이유</th></tr></thead><tbody></tbody></table></div><p class="journal-note">거래 행을 누르면 진입 1시간 전부터 청산 1시간 후까지 확대합니다. 미집행은 자금 소진 이후의 전략 기록이며 실제 계좌 거래와 구분합니다. 미청산 기록은 수익률을 확정하지 않습니다.</p>';
el('legend')?.before(journal);
const formatter=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
const time=t=>Number.isFinite(t)?formatter.format(new Date(t*1000)):'—';
const number=(n,d=6)=>Number.isFinite(n)?n.toLocaleString('ko-KR',{maximumFractionDigits:d}):'—';
const percent=n=>Number.isFinite(n)?number(n,2)+'%':'—';
const reasons={opposite_cross:'반대 지표 교차',sma20:'SMA20 종가 이탈',sma50:'SMA50 종가 이탈',entry_candle:'진입 봉 고·저점 이탈',atr_1_5:'ATR × 1.5 손절',break_even:'본전 기준 이탈',S2:'첫 진입 봉 1% 가격 손절'};
for(const n of [20,50,100,200]){reasons['nearest_ma'+n]='최근접 SMA'+n+' 보호 실패';reasons['support_ma'+n]='진입 근거 SMA'+n+' 보호 실패';}
let seenChart=null,selected=null,records=[];
function highlight(){for(const tr of journal.querySelectorAll('tbody tr[data-trade-index]'))tr.setAttribute('aria-selected',String(tr.dataset.tradeIndex===selected));}
function choose(record){
 const q=window.__pppResearchQA;if(!q||root.dataset.ready!=='true')return;
 el('streak').value='all';
 if(record.index==='open'){
  const t=q.profile.open_position;
  el('trade').value='all';
  q.focusTrade('all');
  q.setRange({from:Math.max(q.current.start,t.entry_time-3600),to:q.current.end-q.current.step});
  q.inspect(t.entry_signal_time??Math.max(q.current.start,t.entry_time-q.current.step));
 }else q.focusTrade(record.index);
 selected=String(record.index);highlight();
}
function render(){
 const side=el('gallery-side').value,result=el('gallery-result').value;
 const filtered=records.filter(r=>(side==='all'||r.side===side)&&(result==='all'||result==='open'&&r.open||result==='wins'&&!r.open&&r.net_pct>0||result==='losses'&&!r.open&&r.net_pct<0));
 journal.querySelector('summary').textContent='거래 목록 · '+records.length.toLocaleString('ko-KR')+'건';
 el('gallery-trade-count').textContent=filtered.length.toLocaleString('ko-KR')+' / '+records.length.toLocaleString('ko-KR')+'건';
 const rows=filtered.map(record=>{
  const tr=document.createElement('tr');tr.dataset.tradeIndex=String(record.index);tr.setAttribute('aria-selected',String(record.index)===selected?'true':'false');
  const title=record.open?'미청산':('#'+record.n+(record.capital_executed===false?' · 미집행':''));
  const values=[title,record.side==='long'?'롱':'숏',time(record.entry),number(record.ep),record.open?'미청산':time(record.exit),number(record.xp),percent(record.net_pct),percent(record.account_pct),record.open?'기간 종료 시 보유':reasons[record.reason]||record.reason];
  values.forEach((value,i)=>{const td=document.createElement('td');if(i===0){const button=document.createElement('button');button.type='button';button.textContent=value;button.setAttribute('aria-label',title+' '+time(record.entry)+' 차트로 이동');button.onclick=()=>choose(record);td.append(button);}else td.textContent=value;
   if((i===6||i===7)&&Number.isFinite(i===6?record.net_pct:record.account_pct)){const v=i===6?record.net_pct:record.account_pct;td.className=v>0?'journal-win':v<0?'journal-loss':'';}tr.append(td);});
  tr.addEventListener('click',event=>{if(!event.target.closest('button'))choose(record);});return tr;
 });
 if(!rows.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=9;td.textContent='조건에 맞는 거래가 없습니다.';tr.append(td);rows.push(tr);}
 journal.querySelector('tbody').replaceChildren(...rows);
}
function update(){
 const q=window.__pppResearchQA;
 if(root.dataset.ready!=='true'||!q?.profile||seenChart===q.chart)return;
 seenChart=q.chart;selected=null;el('gallery-side').value=el('gallery-result').value='all';
 records=q.profile.trades.map((t,index)=>({...t,index,open:false}));
 if(q.profile.open_position){const p=q.profile.open_position;records.push({index:'open',open:true,side:p.side,entry:p.entry_time,ep:p.entry_price});}
 records.reverse();render();
}
el('gallery-side').onchange=render;el('gallery-result').onchange=render;
el('trade').addEventListener('change',()=>{selected=el('trade').value==='all'?null:el('trade').value;highlight();});
const clear=()=>{selected=null;highlight();};for(const id of ['full','jump','streak'])el(id).addEventListener(id==='streak'?'change':'click',clear);
new MutationObserver(update).observe(root,{attributes:true,attributeFilter:['data-ready','data-market','data-profile']});update();
})();
