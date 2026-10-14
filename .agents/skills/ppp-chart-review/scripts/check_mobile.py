#!/usr/bin/env python3
"""Regression-check PPP mobile journal navigation with actual Chrome touch input."""
import argparse
import sys
from pathlib import Path
import subprocess,time,json,urllib.request,urllib.error,base64,shutil

ROOT=Path(__file__).resolve().parents[4]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--url',default='http://127.0.0.1:8765/')
parser.add_argument('--output',type=Path,default=ROOT/'user_data/backtest_results/ppp-mobile-check')
parser.add_argument('--chromium',default=shutil.which('chromium') or shutil.which('chromium-browser'))
args=parser.parse_args()
if not args.chromium:parser.error('Chromium is required; pass --chromium /path/to/chromium')
try:
 import websocket
except ImportError:parser.error('Install websocket-client in the interpreter environment')
url=args.url
out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
profile=out/'chrome-qa-profile'
profile.mkdir(exist_ok=True)
(profile/'DevToolsActivePort').unlink(missing_ok=True)
log=(out/'browser.log').open('w')
proc=subprocess.Popen([args.chromium,'--headless','--disable-gpu','--disable-dev-shm-usage','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=log,stderr=log)
ws=None;seq=0;events=[];contexts={};audits=[];child_sessions={}
try:
 deadline=time.monotonic()+25
 while not (profile/'DevToolsActivePort').exists():
  if time.monotonic()>deadline:raise RuntimeError('Chrome startup timeout')
  time.sleep(.1)
 port=(profile/'DevToolsActivePort').read_text().splitlines()[0]
 pages=json.load(urllib.request.urlopen('http://127.0.0.1:'+port+'/json/list'))
 ws=websocket.create_connection(next(p for p in pages if p['type']=='page')['webSocketDebuggerUrl'],suppress_origin=True,timeout=60)
 def call(method,params=None,session=None):
  global seq
  seq+=1;n=seq;msg=dict(id=n,method=method,params=params or {})
  if session:msg['sessionId']=session
  ws.send(json.dumps(msg))
  while True:
   r=json.loads(ws.recv())
   if 'method' in r:
    events.append(r)
    if r['method']=='Runtime.executionContextCreated':
     c=r['params']['context'];contexts[c['id']]=c
    elif r['method']=='Runtime.executionContextDestroyed':contexts.pop(r['params']['executionContextId'],None)
    elif r['method']=='Runtime.executionContextsCleared':contexts.clear()
   if r.get('id')==n:
    if 'error' in r:raise RuntimeError(r['error'])
    return r.get('result',{})
 def evaluate(expr,child=False):
  args=dict(expression=expr,returnByValue=True,awaitPromise=True)
  session=None
  if child:
   targets=call('Target.getTargets')['targetInfos']
   target=next(t for t in targets if t['type']=='iframe')
   tid=target['targetId']
   if tid not in child_sessions:
    child_sessions[tid]=call('Target.attachToTarget',dict(targetId=tid,flatten=True))['sessionId']
    call('Runtime.enable',session=child_sessions[tid])
   session=child_sessions[tid]
  r=call('Runtime.evaluate',args,session=session)
  if 'exceptionDetails' in r:raise RuntimeError(r['exceptionDetails'])
  return r['result'].get('value')
 def settle():
  deadline=time.monotonic()+55
  while True:
   if '개 봉' in (evaluate('document.getElementById("status")?.textContent') or ''):break
   if time.monotonic()>deadline:raise RuntimeError('Chart never ready: '+str(evaluate('document.getElementById("status")?.textContent')))
   time.sleep(.1)
  assert evaluate('document.querySelectorAll("iframe").length')==1
  evaluate('new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(()=>r(true))))')
 def change(name,value,child=False):
  evaluate('document.getElementById('+json.dumps(name)+').value='+json.dumps(value)+';document.getElementById('+json.dumps(name)+').dispatchEvent(new Event("change",{bubbles:true}))',child);settle()
 def shot(name):
  (out/name).write_bytes(base64.b64decode(call('Page.captureScreenshot',dict(format='png',captureBeyondViewport=False))['data']))
 call('Page.enable');call('Runtime.enable');call('Emulation.setDeviceMetricsOverride',dict(width=390,height=844,deviceScaleFactor=1,mobile=True))
 call('Emulation.setTouchEmulationEnabled',dict(enabled=True,maxTouchPoints=1))
 call('Page.navigate',dict(url=url));settle()
 def coordinates(selector):
  r=evaluate('(()=>{const r=document.querySelector('+json.dumps(selector)+').getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};})()',True)
  f=evaluate('(()=>{const r=document.querySelector("iframe").getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};})()')
  return {'x':f['x']+r['x']+min(r['w']/2,25),'y':f['y']+r['y']+r['h']/2}
 def tap(selector):
  pt=coordinates(selector)
  call('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=[dict(x=pt['x'],y=pt['y'],radiusX=4,radiusY=4,force=1,id=1)]))
  call('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[]));time.sleep(.15)
 evaluate('document.getElementById("gallery-trades").scrollIntoView({block:"start",behavior:"instant"})',True)
 tap('#gallery-trades summary')
 assert evaluate('document.getElementById("gallery-trades").open',True),'Journal did not open on touch'
 first=evaluate('document.querySelector("#gallery-trades tbody tr[data-trade-index]").dataset.tradeIndex',True)
 tap('#gallery-trades tbody tr[data-trade-index] button')
 kept=evaluate('document.getElementById("gallery-trades").open',True)
 selected=evaluate('document.querySelector("#gallery-trades tr[aria-selected=true]")?.dataset.tradeIndex',True)
 assert selected==first,(selected,first)
 visibleSummary=evaluate('(()=>{const r=document.querySelector("#gallery-trades summary").getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight;})()',True)
 # Prepare an identical finger position on the price plot for both old/new behavior.
 evaluate('document.getElementById("chart").scrollIntoView({block:"start",behavior:"instant"})',True)
 def swipe():
  f=evaluate('(()=>{const r=document.querySelector("iframe").getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};})()')
  x=f['x']+min(130,f['w']/2);start=f['y']+f['h']-35;end=f['y']+40
  call('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=[dict(x=x,y=start,radiusX=4,radiusY=4,force=1,id=1)]))
  for k in range(1,13):
   call('Input.dispatchTouchEvent',dict(type='touchMove',touchPoints=[dict(x=x,y=start+(end-start)*k/12,radiusX=4,radiusY=4,force=1,id=1)]));time.sleep(.016)
  call('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[]));time.sleep(.4)
 before=evaluate('scrollY',True);swipe();after=evaluate('scrollY',True)
 evidence={'journal_remains_open':kept,'summary_remains_visible':visibleSummary,'selected_row':selected,'swipe_scroll_before':before,'swipe_scroll_after':after,'scroll_gain':after-before,'chart_options':evaluate('window.__pppResearchQA.chart.options().handleScroll',True)}
 print(json.dumps(evidence),flush=True)
 assert kept and visibleSummary,'Trade selection hid the journal: '+str(evidence)
 assert after-before>60,'Vertical swipe on plot cannot scroll to lower indicators: '+str(evidence)
 for k in range(4):
  if evaluate('document.getElementById("chart").getBoundingClientRect().bottom<=innerHeight+40',True):break
  swipe()
 assert evaluate('document.getElementById("chart").getBoundingClientRect().bottom<=innerHeight+40',True),'Lower indicator panes remain inaccessible'
 # Confirm horizontal time panning still works while vertical page scrolling is enabled.
 f=evaluate('(()=>{const r=document.querySelector("iframe").getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};})()')
 oldRange=evaluate('window.__pppResearchQA.chart.timeScale().getVisibleRange()',True)
 oldScroll=evaluate('scrollY',True)
 call('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=[dict(x=f['x']+40,y=f['y']+85,radiusX=4,radiusY=4,force=1,id=1)]))
 for k in range(1,13):
  call('Input.dispatchTouchEvent',dict(type='touchMove',touchPoints=[dict(x=f['x']+40+130*k/12,y=f['y']+85,radiusX=4,radiusY=4,force=1,id=1)]));time.sleep(.016)
 call('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[]));time.sleep(.3)
 newRange=evaluate('window.__pppResearchQA.chart.timeScale().getVisibleRange()',True)
 assert newRange!=oldRange,'Horizontal time panning stopped working'
 assert abs(evaluate('scrollY',True)-oldScroll)<2,'Horizontal swipe unexpectedly moved the page'
 evidence['horizontal_pan_preserved']=True
 evidence['pinch_zoom_enabled']=evaluate('window.__pppResearchQA.chart.options().handleScale.pinch',True)
 assert evidence['pinch_zoom_enabled']
 shot('gallery-scroll-lower-mobile.png')
 # Swipe back down over chart panes to return to the still-open journal.
 for turn in range(4):
  call('Input.dispatchTouchEvent',dict(type='touchStart',touchPoints=[dict(x=f['x']+130,y=f['y']+45,radiusX=4,radiusY=4,force=1,id=1)]))
  for k in range(1,13):
   call('Input.dispatchTouchEvent',dict(type='touchMove',touchPoints=[dict(x=f['x']+130,y=f['y']+45+(f['h']-90)*k/12,radiusX=4,radiusY=4,force=1,id=1)]));time.sleep(.016)
  call('Input.dispatchTouchEvent',dict(type='touchEnd',touchPoints=[]));time.sleep(.4)
  if evaluate('scrollY',True)<50:break
 assert evaluate('document.getElementById("gallery-trades").open',True)
 assert evaluate('(()=>{const r=document.querySelector("#gallery-trades summary").getBoundingClientRect();return r.bottom>0&&r.top<innerHeight;})()',True),'Cannot scroll back to the journal'
 evidence['return_to_open_journal']=True
 shot('gallery-scroll-journal-mobile.png')
 audits=[evidence]
 errors=[e for e in events if e.get('method')=='Runtime.exceptionThrown' or e.get('method')=='Runtime.consoleAPICalled' and e.get('params',{}).get('type')=='error']
 assert not errors,errors
 for route in ['/%2e%2e/.env','/browser.log','/charts/unknown.html','/../../AGENTS.md']:
  try:urllib.request.urlopen(url.rstrip('/')+route);raise AssertionError('Route should be denied: '+route)
  except urllib.error.HTTPError as e:assert e.code==404
 catalog=evaluate('window.__pppGalleryQA.catalog')
 result=dict(cases=len(audits),audits=audits,errors=errors,chart_records=len(catalog['charts']),server_url=url,route_rejections=4)
 (out/'mobile-scroll-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print('Mobile scroll browser QA passed',len(audits),flush=True)
finally:
 if ws:ws.close()
 proc.terminate()
 try:proc.wait(timeout=10)
 except subprocess.TimeoutExpired:proc.kill();proc.wait()
 log.close()
