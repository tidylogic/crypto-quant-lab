#!/usr/bin/env python3
"""Collect existing portable charts; optionally serve only gallery artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CONFIG = re.compile(r'(<script id="configuration" type="application/json">)(.*?)(</script>)', re.S)
ASSETS = ['BTC', 'ETH', 'BNB', 'SOL', 'XRP', 'WLD', 'ZEC']
GROUPS = {'ppp-support': '지지·저항 확인 / 손절 주기 비교',
          'ppp-largecap': '진입 시점 개선 연구',
          'ppp-wld-s2': 'WLD · 최고 수익 기준형 비교',
          'ppp-wld': 'WLD · 초기 전략 비교'}

CHART_STYLE = '''<style id="gallery-chart-style">
body{padding:12px 18px}main{max-width:none}
#heading,#strategy-status,#rules,#assumptions,main>details,main>p.muted:not(#navigation):not(#panes):not(#fill-note){display:none}
#fill-note{font-size:12px}#chart{height:900px}.controls{margin:8px 0;gap:8px}
.controls label{flex-basis:180px}.controls .date{flex-basis:210px}
#checks,#inspected,#risk-detail,#trade-detail{display:none}
body.inspect-open #checks{display:table}body.inspect-open #inspected,body.inspect-open #risk-detail,body.inspect-open #trade-detail{display:block}
#gallery-inspect{margin:10px 0}#gallery-nav{display:none}#period,#stats{font-size:13px}#decision{font-size:13px}
#gallery-trades{display:block;border:1px solid var(--grid);border-radius:7px;margin:8px 0;font-size:13px}#gallery-trades summary{padding:6px 9px;font-weight:600}.journal-filters{display:flex;align-items:end;flex-wrap:wrap;gap:10px;padding:8px}.journal-filters label{display:flex;flex-direction:column;font-size:12px;gap:3px}.journal-filters select{min-height:34px;padding:5px}.journal-scroll{max-height:250px;overflow:auto}#gallery-trades table{width:100%;min-width:1000px;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}#gallery-trades th{position:sticky;top:0;background:var(--bg);z-index:1;white-space:nowrap}#gallery-trades td{white-space:nowrap;padding:6px 8px}#gallery-trades tr[data-trade-index]{cursor:pointer}#gallery-trades tr[aria-selected=true]{background:color-mix(in srgb,var(--s1) 15%,var(--bg))}#gallery-trades td button{min-height:32px;padding:4px 7px;font-size:12px}.journal-win{color:var(--up)}.journal-loss{color:var(--down)}.journal-note{font-size:11px;color:var(--muted);padding:0 8px}.journal-filters span{font-size:12px;color:var(--muted)}
@media(max-width:500px){body{padding:8px}.controls label{flex-basis:45%}.controls .date{flex-basis:100%}.controls select{font-size:13px}.controls button{font-size:13px}.controls{gap:6px}#market,#profile{max-width:100%}#gallery-nav{display:block;padding:6px;min-height:34px;font-size:12px}body:not(.nav-open) .controls:first-of-type label:nth-child(3),body:not(.nav-open) .controls:nth-of-type(2),body:not(.nav-open) #navigation,body:not(.nav-open) #period,body:not(.nav-open) #panes,body:not(.nav-open) #decision{display:none}#stats{font-size:12px;margin:6px 0}.legend{font-size:12px}}
</style>'''

CHART_BOOT = '''<script id="gallery-chart-selection">
(()=>{const e=document.getElementById('configuration'),c=JSON.parse(e.textContent),q=new URLSearchParams(location.hash.slice(1));
if(c.markets.some(m=>m.key===q.get('market')))c.default_market=q.get('market');
if(c.summaries.some(s=>s.profile===q.get('profile')))c.default_profile=q.get('profile');
e.textContent=JSON.stringify(c);})();
</script>'''

CHART_BRIDGE = '''<script id="gallery-chart-bridge">
(()=>{const root=document.getElementById('research'),c=JSON.parse(document.getElementById('configuration').textContent);
const button=document.createElement('button');button.id='gallery-inspect';button.type='button';button.textContent='진입·청산 판단 펼치기';button.setAttribute('aria-expanded','false');
const checks=document.getElementById('checks');checks?.before(button);button.onclick=()=>{const open=document.body.classList.toggle('inspect-open');button.setAttribute('aria-expanded',String(open));button.textContent=open?'진입·청산 판단 접기':'진입·청산 판단 펼치기';};
const nav=document.createElement('button');nav.id='gallery-nav';nav.type='button';nav.textContent='날짜·거래 탐색 펼치기';nav.setAttribute('aria-expanded','false');document.querySelector('.controls')?.after(nav);nav.onclick=()=>{const open=document.body.classList.toggle('nav-open');nav.setAttribute('aria-expanded',String(open));nav.textContent=open?'날짜·거래 탐색 접기':'날짜·거래 탐색 펼치기';};
function send(){if(!root||root.dataset.ready!=='true')return;parent.postMessage({type:'ppp-chart-ready',asset:c.asset,market:root.dataset.market,profile:root.dataset.profile,candles:Number(root.dataset.candles),stats:document.getElementById('stats')?.textContent,status:document.getElementById('strategy-status')?.textContent},'*');}
if(root)new MutationObserver(send).observe(root,{attributes:true,attributeFilter:['data-ready','data-market','data-profile']});send();
})();
</script>'''


def chart_document(text: str) -> str:
    """Only presentation/initial selection changes; all chart payloads stay intact."""
    match = CONFIG.search(text)
    if match is None:
        raise ValueError('Not a supported strategy chart')
    # Narrow the first viewport without dropping candles or changing trades.
    recent = " const visibleBars=matchMedia('(max-width:500px)').matches?120:240;setRange({from:Math.max(current.start,current.end-(visibleBars+1)*current.step),to:current.end-current.step});\n}\nfunction verdict"
    text = text.replace(' fullRange();\n}\nfunction verdict', recent, 1)
    # Let a vertical finger swipe scroll the page to the lower indicator panes.
    # Horizontal chart panning and pinch zoom retain the library defaults.
    text = text.replace('chart=L.createChart(box,{width:', 'chart=L.createChart(box,{handleScroll:{vertTouchDrag:false},width:', 1)
    text = text.replace('draw,inspect,focusTrade,verdict,jump};', 'draw,inspect,focusTrade,verdict,jump,setRange};', 1)
    text = text.replace('inspect(profile.trades.length?profile.trades[0].signal_time:current.start);', 'inspect(current.end-current.step);', 1)
    text = text.replace("el('date').value=el('date').min;", "el('date').value=kst(current.end-current.step).replace(' ','T');", 1)
    match = CONFIG.search(text)
    # Bootstrap runs before the existing chart's async initialization.
    text = text[:match.end()] + CHART_BOOT + text[match.end():]
    trade_script = (ROOT/'scripts/templates/ppp-chart-trades.js').read_text()
    return text.replace('</head>', CHART_STYLE+'</head>', 1).replace('</body>', CHART_BRIDGE+'<script>'+trade_script+'</script></body>', 1)


def group_name(group: str) -> str:
    for prefix, name in GROUPS.items():
        if group.startswith(prefix+'-'):
            return name
    return group


def build_gallery(source_root: Path, output: Path) -> dict:
    source_root, output = source_root.resolve(), output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output/'charts').mkdir(exist_ok=True)
    charts = []
    for path in sorted(source_root.rglob('*.html')):
        if path.is_symlink() or output in path.resolve().parents:
            continue
        # Configuration precedes the large base64 data and bundled library.
        with path.open() as stream:
            header = stream.read(150000)
        if 'id="gallery-chart-style"' in header:
            continue
        match = CONFIG.search(header)
        if not match:
            continue
        c = json.loads(match.group(2))
        if not c.get('markets') or not c.get('summaries'):
            continue
        relative = path.relative_to(source_root).as_posix()
        group = relative.split('/')[0]
        key = hashlib.sha256(relative.encode()).hexdigest()[:16]
        filename = 'charts/'+key+'.html'
        text = path.read_text()
        (output/filename).write_text(chart_document(text))
        charts.append(dict(id=key, file=filename, asset=c['asset'], model=c['model'],
                           name=c.get('model_name', c['model']), status=c.get('strategy_status', 'draft'),
                           group=group, group_name=group_name(group), source=relative,
                           source_sha256=hashlib.sha256(text.encode()).hexdigest(),
                           markets=c['markets'], default_market=c['default_market'], default_profile=c['default_profile'],
                           execution_minutes=1 if c.get('native_execution') else None,
                           profiles=list(dict.fromkeys(s['profile'] for s in c['summaries'])),
                           experimental_profiles=c.get('experimental_profiles', [])))
    def order(c):
        date = re.search(r'\d{4}-\d{2}-\d{2}', c['group'])
        return (c['status']=='draft', -(int(date[0].replace('-', '')) if date else 0),
                0 if c['group'].startswith('ppp-support-') else 1,
                ASSETS.index(c['asset']) if c['asset'] in ASSETS else len(ASSETS), c['source'])
    charts.sort(key=order)
    manifest = dict(generated_utc=datetime.now(timezone.utc).isoformat(), charts=charts,
                    default_id=charts[0]['id'] if charts else None)
    template = (ROOT/'scripts/templates/ppp-chart-gallery.html').read_text()
    safe_json = json.dumps(manifest, ensure_ascii=False).replace('<', '\\u003c')
    (output/'index.html').write_text(template.replace('@@CATALOG@@', safe_json))
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    return manifest


def route_path(url: str, output: Path, manifest: dict | None = None) -> Path | None:
    """No directory listing, runtime/config files, or traversal through symlinks."""
    if manifest is None:
        try:
            manifest = json.loads((output/'manifest.json').read_text())
        except (OSError, json.JSONDecodeError):
            return None
    name = unquote(urlsplit(url).path)
    routes = {'/': 'index.html', '/index.html': 'index.html', '/manifest.json': 'manifest.json'}
    routes.update({'/'+c['file']: c['file'] for c in manifest['charts']})
    relative = routes.get(name)
    if relative is None:
        return None
    path = output/relative
    if output.resolve() not in path.resolve().parents:
        return None
    return path


class GalleryHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, output: Path, manifest: dict, **kwargs):
        self.output, self.manifest = output, manifest
        super().__init__(*args, **kwargs)

    def do_GET(self):
        self.respond(True)

    def do_HEAD(self):
        self.respond(False)

    def respond(self, body):
        path = route_path(self.path, self.output)
        if path is None or not path.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8' if path.suffix=='.json' else 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(path.stat().st_size))
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if body:
            with path.open('rb') as stream:
                while chunk := stream.read(256*1024):
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'user_data/backtest_results')
    parser.add_argument('--output', type=Path, default=ROOT/'user_data/backtest_results/ppp-chart-gallery')
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    manifest = build_gallery(args.source, args.output)
    print(f"Gallery: {len(manifest['charts'])} charts, {args.output/'index.html'}", flush=True)
    if args.serve:
        handler = partial(GalleryHandler, output=args.output.resolve(), manifest=manifest)
        with ThreadingHTTPServer((args.host, args.port), handler) as server:
            print(f'Chart gallery: http://{args.host}:{server.server_port}/', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass


if __name__=='__main__':
    main()
