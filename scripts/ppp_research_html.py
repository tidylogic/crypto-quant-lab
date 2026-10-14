#!/usr/bin/env python3
"""Aggregate PPP research into one portable Korean HTML; never simulate trades."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import importlib.util
import json
import mimetypes
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path('user_data/backtest_results/ppp-selective-2026-10-14/ppp-research-report.html')
PARSER = ROOT/'.agents/skills/rendering-plan-html/scripts/render_plan_html.py'

# Source documents are included whole, including their caveats and detailed tables.
SOURCES = [
    ('selective', '새 선택적 손실 제어 연구', 'user_data/backtest_results/ppp-selective-2026-10-14/report.ko.md'),
    ('method-selective', '전액 10배 · 선택적 청산 규칙·계산법', 'docs/strategy-notes/ppp-selective-loss-controls.md'),
    ('drawdown', '이전 낙폭·배분 연구', 'user_data/backtest_results/ppp-drawdown-2026-10-14/report.ko.md'),
    ('method-drawdown', '낙폭·배분 제어 규칙·계산법', 'docs/strategy-notes/ppp-drawdown-management.md'),
    ('original', '원본 영상 추론 · A–C', 'docs/tradingview/ppp/README.ko.md'),
    ('indicators', '추가 지표 D–H', 'docs/tradingview/ppp-combinations/README.ko.md'),
    ('abc', 'A/B/C · 48개 백테스트', 'user_data/backtest_results/ppp-2026-10-14/report.ko.md'),
    ('combinations', 'D–H · 96개 백테스트', 'user_data/backtest_results/ppp-combinations-2026-10-14/report.ko.md'),
    ('method-risk', 'C/E/G 리스크 규칙·계산법', 'docs/strategy-notes/ppp-risk-controls.md'),
    ('risk', 'BTC/ETH/ZEC · 504개 리스크 비교', 'user_data/backtest_results/ppp-risk-eth-2026-10-14/report.ko.md'),
    ('capital', '$1,000 · 10배 · 504개 복리 계산', 'user_data/backtest_results/ppp-risk-eth-2026-10-14/capital-10x.ko.md'),
    ('method-abc', '초기 SMA 배열 연구 설계', 'docs/strategy-notes/ppp-sma-alignment.md'),
    ('method-combinations', 'D–H 조합 연구 설계', 'docs/strategy-notes/ppp-combinations.md'),
]
CHARTS = {
    'selective': [('selective-comparison.png', '선택적 손실 제어 청산 정책 전체 비교'), ('selective-curves-zec5m.png', 'ZEC 5분봉 선택적 손실 제어 자산 경로')],
    'drawdown': [('drawdown-comparison.png', '배분·낙폭 제어 전체 비교'), ('drawdown-curves-zec5m.png', 'ZEC 5분봉 배분별 자산 경로')],
    'risk': [('expectancy-comparison.png', '리스크 방식별 기대수익 비교'), ('win-payoff-zec5m.png', 'ZEC 5분봉 승률과 실현 손익비')],
    'capital': [('capital-zec5m.png', 'ZEC 5분봉 $1,000 · 10배 폐쇄 잔고 경로')],
}


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    if path.suffix in ('.pine', '.md'):
        mime = 'text/plain;charset=utf-8'
    return f'data:{mime};base64,{base64.b64encode(path.read_bytes()).decode("ascii")}'


class ReportRenderer:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.source = self.root
        self.key = ''
        self.source_keys = {(self.root/path).resolve(): key for key, _, path in SOURCES}
        self.images: set[Path] = set()
        self.downloads: set[Path] = set()
        self.supplements: set[Path] = set()
        self.missing_assets: set[Path] = set()
        self.tables = 0
        self.rows = 0
        spec = importlib.util.spec_from_file_location('_ppp_plan_renderer', PARSER)
        self.parser = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.parser
        spec.loader.exec_module(self.parser)
        self.parser.render_inline = self.inline
        self.parser.render_table = self.table

    def download(self, path: Path, label: str) -> str:
        self.downloads.add(path.resolve())
        return (f'<a class="download" href="{data_uri(path)}" '
                f'download="{html.escape(path.name, quote=True)}">{html.escape(label)}</a>')

    def image(self, path: Path, caption: str) -> str:
        if not path.is_file():
            self.missing_assets.add(path.resolve())
            return f'<span class="missing">그림 대기: {html.escape(caption)} ({html.escape(path.name)})</span>'
        self.images.add(path.resolve())
        return (f'<span class="image"><img src="{data_uri(path)}" '
                f'alt="{html.escape(caption, quote=True)}" loading="eager">'
                f'<small>{html.escape(caption)}</small></span>')

    def link(self, label: str, target: str) -> str:
        target = target.strip().strip('<>')
        parsed = urlsplit(target)
        content = self.inline(label)
        if parsed.scheme or target.startswith('//'):
            return f'<a href="{html.escape(target, quote=True)}" target="_blank" rel="noopener noreferrer">{content}</a>'
        if target.startswith('#'):
            href = '#' + self.key + '-' + target[1:]
            return f'<a href="{html.escape(href, quote=True)}">{content}</a>'
        path = (self.source.parent/unquote(parsed.path)).resolve()
        if path in self.source_keys:
            href = '#' + self.source_keys[path]
            if parsed.fragment:
                href += '-' + parsed.fragment
            return f'<a href="{html.escape(href, quote=True)}">{content}</a>'
        # Large trade logs/OHLCV remain supplementary links; only compact summaries
        # and small validation files travel inside the report.
        portable = path.suffix == '.pine' or path.name in {'summary.csv', 'capital-10x.csv', 'capital-zec5m-curves.csv'}
        portable |= path.suffix in {'.json', '.txt'} and path.is_file() and path.stat().st_size <= 200_000
        if portable and path.is_file() and path.stat().st_size <= 2_000_000:
            self.downloads.add(path)
            return f'<a href="{data_uri(path)}" download="{html.escape(path.name, quote=True)}">{content}</a>'
        self.supplements.add(path)
        return f'<a class="supplement" href="{html.escape(path.as_uri(), quote=True)}" title="작업 공간의 보조 파일">{content}<span aria-label="작업 공간 파일"> ↗</span></a>'

    def inline(self, text: str) -> str:
        # Tokenize before escaping so URL query ampersands are escaped exactly once,
        # code stays literal, and images are resolved relative to each source file.
        pattern = r'`[^`]+`|!?\[[^\]]*\]\([^\n)]+\)|\*\*[^*]+\*\*|(?<!\*)\*[^*]+\*(?!\*)'
        result, cursor = [], 0
        for match in re.finditer(pattern, text):
            result.append(html.escape(text[cursor:match.start()]))
            token = match.group()
            if token.startswith('`'):
                result.append('<code>' + html.escape(token[1:-1]) + '</code>')
            elif token.startswith('**'):
                result.append('<strong>' + self.inline(token[2:-2]) + '</strong>')
            elif token.startswith('*'):
                result.append('<em>' + self.inline(token[1:-1]) + '</em>')
            else:
                link = re.match(r'(!?)\[([^\]]*)\]\((.*)\)$', token)
                marker, label, target = link.groups()
                if marker:
                    parsed = urlsplit(target)
                    if parsed.scheme or target.startswith('//'):
                        # Remote graphics would violate offline portability; identify
                        # the source explicitly rather than silently require a network.
                        self.missing_assets.add(Path('remote-image')/label)
                        result.append('<span class="missing">외부 그림 미포함: ' + self.link(label, target) + '</span>')
                    else:
                        result.append(self.image((self.source.parent/unquote(parsed.path)).resolve(), label))
                else:
                    result.append(self.link(label, target))
            cursor = match.end()
        result.append(html.escape(text[cursor:]))
        return ''.join(result)

    def table(self, lines: list[str]) -> str:
        self.tables += 1
        rows = [self.parser.split_table_row(line) for line in lines[2:]]
        self.rows += len(rows)
        header = self.parser.split_table_row(lines[0])
        parts = [f'<div class="table-block"><div class="table-meta"><span>표 {self.tables:02d}</span><span class="row-count">{len(rows):,}행</span></div>',
                 '<div class="table-scroll" tabindex="0" role="region" aria-label="가로 스크롤 가능한 연구 표"><table><thead><tr>']
        parts.extend('<th scope="col">' + self.inline(cell) + '</th>' for cell in header)
        parts.append('</tr></thead><tbody>')
        for row in rows:
            parts.append('<tr>' + ''.join('<td>' + self.inline(cell) + '</td>' for cell in row) + '</tr>')
        parts.append('</tbody></table></div></div>')
        return ''.join(parts)

    def markdown(self, source: Path, key: str):
        self.source, self.key = source, key
        result = self.parser.render_markdown(source.read_text(encoding='utf-8'))
        for heading in result.headings:
            old = heading.slug
            heading.slug = f'{key}-{old}'
            result.body = result.body.replace(f'id="{old}"', f'id="{heading.slug}"').replace(f'href="#{old}"', f'href="#{heading.slug}"')
        # The outer chapter is h2; source headings are nested below it.
        result.body = re.sub(r'<(/?)h([1-6])\b', lambda m: f'<{m[1]}h{min(int(m[2])+2, 6)}', result.body)
        return result


CSS = r'''
:root{color-scheme:light;--ink:#182b36;--muted:#5a6d76;--line:#dbe4e4;--paper:#fff;--accent:#126f69;--bg:#f3f6f5}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:105px}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,-apple-system,"Noto Sans KR","Malgun Gothic",sans-serif;font-size:15px;line-height:1.8}a{color:var(--accent);text-underline-offset:3px;overflow-wrap:anywhere}button,input{font:inherit}button{cursor:pointer;border:1px solid var(--line);border-radius:7px;background:white;padding:7px 13px;color:var(--ink)}button:hover,.download:hover{background:#e8f1ee}a:focus-visible,button:focus-visible,input:focus-visible,.table-scroll:focus-visible{outline:3px solid #d38928;outline-offset:3px}.shell{max-width:1900px;margin:auto;display:grid;grid-template-columns:282px minmax(0,1fr)}nav{position:sticky;top:0;height:100vh;overflow-y:auto;padding:26px 20px;background:#edf2ef;border-right:1px solid var(--line)}.brand{font-size:22px;font-weight:800;color:var(--ink);text-decoration:none;letter-spacing:-.5px}.nav-kicker,.eyebrow{font-size:12px;font-weight:750;letter-spacing:1.8px;color:var(--accent)}nav ol{list-style:none;padding:0;margin:20px 0}nav li{margin:4px 0}nav a.chapter-link{display:block;padding:9px 10px;border-radius:6px;font-size:13px;text-decoration:none;color:var(--ink)}nav a.chapter-link:hover{background:#dce9e3}nav details{margin:0 0 12px 10px;font-size:12px;color:var(--muted)}nav details ol{margin:6px 0}nav details a{display:block;padding:3px 0;text-decoration:none}.toc-depth-3{padding-left:10px}.toc-depth-4{padding-left:18px}.nav-note{font-size:12px;color:var(--muted);border-top:1px solid var(--line);padding-top:18px}.content{min-width:0}.hero{padding:48px 48px 30px;background:linear-gradient(135deg,#e4ede6,#f7faf7);border-bottom:1px solid var(--line)}h1{font-size:clamp(28px,3vw,45px);line-height:1.35;margin:10px 0 14px;letter-spacing:-1.4px}.lede{max-width:920px;font-size:17px}.meta{color:var(--muted);font-size:12px}.pills{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0}.pill{padding:5px 12px;background:#fff;border:1px solid #cad9d1;border-radius:100px;font-size:12px}.notice{border-left:4px solid #c99030;background:#fff9ec;padding:14px 18px;font-size:14px;max-width:1100px}.notice p{margin:4px 0}.overview{padding:24px 48px}.overview-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.overview article{background:white;border:1px solid var(--line);border-radius:9px;padding:18px}.overview h2{font-size:15px;margin:0 0 7px}.overview p{font-size:13px;margin:0;color:var(--muted)}.toolbar{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:12px 32px;background:#ffffffed;border-block:1px solid var(--line);backdrop-filter:blur(8px)}.toolbar label{font-weight:700;font-size:13px}.toolbar input{padding:8px 11px;border:1px solid #b6c9c5;border-radius:7px;max-width:420px;width:35vw}.toolbar small{color:var(--muted);font-size:12px}.toolbar .print{margin-left:auto}.chapter{margin:24px 32px;padding:28px 30px;background:var(--paper);border:1px solid var(--line);border-radius:10px;min-width:0}.chapter-header{border-bottom:1px solid var(--line);padding-bottom:17px;margin-bottom:24px}.chapter h2{font-size:24px;margin:0 0 10px;line-height:1.5;letter-spacing:-.6px}.chapter h3{font-size:21px;margin-top:34px;line-height:1.5}.chapter h4{font-size:18px;margin-top:32px;border-left:3px solid #8bb7aa;padding-left:12px}.chapter h5{font-size:16px;margin-top:25px}p{margin:12px 0}li{margin:5px 0}.anchor{color:#83aaa0;text-decoration:none;font-weight:400}.source{font-size:11px;color:var(--muted);overflow-wrap:anywhere}.download{display:inline-block;font-size:12px;padding:4px 11px;margin-right:8px;border:1px solid #c9d8d3;border-radius:6px;text-decoration:none}.image{display:block;margin:24px 0}.image img{display:block;max-width:100%;height:auto;margin:auto;background:white;border:1px solid var(--line);border-radius:6px}.image small{display:block;text-align:center;color:var(--muted);font-size:12px;margin-top:8px}.table-block{margin:20px 0 28px;border:1px solid var(--line);border-radius:7px;overflow:hidden}.table-meta{display:flex;justify-content:space-between;background:#eef4f1;padding:6px 12px;font-size:11px;color:var(--muted)}.table-scroll{overflow-x:auto;overscroll-behavior-x:contain}table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.6}th,td{padding:10px 12px;text-align:left;vertical-align:top;border-bottom:1px solid #e7edeb;white-space:nowrap}th{background:#e2ede7;font-weight:750;color:#244537}tbody tr:nth-child(even){background:#f6f9f7}tbody tr:hover{background:#e8f4f0}td:first-child{font-weight:600}tr[hidden]{display:none}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.9em;padding:2px 5px;border-radius:4px;background:#eef3f1;overflow-wrap:anywhere}pre{overflow:auto;padding:18px;background:#152b32;color:#e8f2ee;border-radius:7px;font-size:12px;line-height:1.65}pre code{padding:0;background:none;color:inherit;white-space:pre}.pine{border:1px solid var(--line);border-radius:7px;margin:14px 0;padding:14px}.pine summary{cursor:pointer;font-weight:650;font-size:14px}.code-actions{margin:12px 0;display:flex;align-items:center;gap:8px}.copy-status{font-size:12px;color:var(--muted)}.missing{display:block;color:#80551a;background:#fff6df;padding:12px;border:1px solid #e7d6ac;border-radius:6px}.supplement{font-size:inherit}.footer{padding:15px 48px 35px;color:var(--muted);font-size:12px}noscript{display:block;padding:15px;background:#fff6df}
@media(min-width:1550px){.chapter{padding:34px 40px}.hero{padding-left:72px}.overview{padding-left:72px}}
@media(max-width:1050px){.shell{grid-template-columns:225px minmax(0,1fr)}nav{padding:20px 12px}.hero{padding:30px 24px}.overview{padding:20px 24px}.overview-grid{grid-template-columns:1fr}.chapter{margin:20px 18px;padding:22px}.toolbar{padding:10px 18px}.toolbar input{width:40vw}.toolbar small{flex-basis:100%}}
@media(max-width:720px){.shell{display:block}nav{position:static;height:auto;padding:15px 20px;border-bottom:1px solid var(--line)}nav ol{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0}nav li{margin:0}nav a.chapter-link{font-size:12px;padding:5px 7px}nav details,.nav-note{display:none}.brand{font-size:19px}.hero{padding:24px 20px}.hero h1{letter-spacing:-.6px}.lede{font-size:15px}.overview{padding:18px}.chapter{margin:16px 10px;padding:20px 15px}.chapter h2{font-size:21px}.toolbar{gap:7px;padding:10px}.toolbar input{flex:1;width:120px;min-width:110px}.toolbar .print{display:none}.toolbar small{font-size:11px}th,td{padding:8px 10px}.footer{padding:20px}}
@media print{@page{size:A4 landscape;margin:13mm}body{background:white;font-size:10pt}.shell{display:block;max-width:none}nav,.toolbar,.code-actions,.download,.anchor{display:none!important}.hero{padding:0 0 18px;background:white}.overview{padding:15px 0}.overview-grid{grid-template-columns:repeat(3,1fr)}.chapter{padding:12px 0;margin:18px 0;border:0;break-before:page}.chapter-header{margin-bottom:12px}.table-scroll{overflow:visible}.table-block{overflow:visible;border:0;break-inside:auto}table{font-size:7pt;table-layout:auto;width:100%}th,td{padding:4px;white-space:normal;overflow-wrap:anywhere}thead{display:table-header-group}tr{break-inside:avoid}tr[hidden]{display:table-row}.table-meta{display:none}.image{break-inside:avoid}.image img{max-height:175mm;object-fit:contain}h2,h3,h4,h5{break-after:avoid}a{color:inherit}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f2f2;color:#111;font-size:8pt}.footer{padding:10px 0}}
'''

JS = r'''
const search=document.querySelector('#table-search'), status=document.querySelector('#filter-status');
const blocks=[...document.querySelectorAll('.table-block')].map(block=>({block,rows:[...block.querySelectorAll('tbody tr')]}));
function filterRows(){const q=search.value.trim().toLocaleLowerCase();let visible=0,total=0;for(const item of blocks){let n=0;for(const row of item.rows){row.hidden=q&&!row.textContent.toLocaleLowerCase().includes(q);if(!row.hidden)n++;}visible+=n;total+=item.rows.length;item.block.querySelector('.row-count').textContent=q?`${n.toLocaleString()} / ${item.rows.length.toLocaleString()}행`:`${n.toLocaleString()}행`;}status.textContent=q?`${visible.toLocaleString()} / ${total.toLocaleString()}행 표시 · 본문과 그림은 그대로 표시`:`${blocks.length}개 표 · 전체 ${total.toLocaleString()}행`;}
search.addEventListener('input',filterRows);document.querySelector('#clear-search').addEventListener('click',()=>{search.value='';filterRows();search.focus();});filterRows();
document.querySelector('#print-report').addEventListener('click',()=>window.print());
for(const button of document.querySelectorAll('[data-copy]'))button.addEventListener('click',async()=>{const text=document.getElementById(button.dataset.copy).textContent;const result=button.parentElement.querySelector('.copy-status');try{if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(text);else{const box=document.createElement('textarea');box.value=text;box.style.position='fixed';box.style.opacity='0';document.body.append(box);box.select();const copied=document.execCommand('copy');box.remove();if(!copied)throw Error('copy');}result.textContent='전체 소스를 복사했습니다.';}catch(error){result.textContent='복사가 제한된 환경입니다. 파일 다운로드를 사용하세요.';}});
window.addEventListener('beforeprint',()=>{for(const details of document.querySelectorAll('.pine')){details.dataset.wasOpen=details.open?'1':'0';details.open=true;}});
window.addEventListener('afterprint',()=>{for(const details of document.querySelectorAll('.pine'))details.open=details.dataset.wasOpen==='1';});
'''


def build_report(root: Path = ROOT) -> tuple[str, dict]:
    renderer = ReportRenderer(root)
    root = renderer.root
    sections, toc, records, missing = [], [], [], []
    for key, label, relative in SOURCES:
        source = root/relative
        toc.append(f'<li><a class="chapter-link" href="#{key}">{html.escape(label)}</a></li>')
        prefix = (f'<section class="chapter" id="{key}"><header class="chapter-header">'
                  f'<span class="eyebrow">RESEARCH / {len(sections)+1:02d}</span><h2>{html.escape(label)}</h2>'
                  f'<div class="source">원문: {html.escape(relative)}</div>')
        if not source.is_file():
            missing.append(relative)
            message = {'selective': '새 선택적 손실 제어 결과 대기', 'drawdown': '새 낙폭 결과 대기'}.get(key, '원문 파일 대기')
            sections.append(prefix + '</header><p class="missing">' + message +
                            ' — 이 절은 초안입니다. 계산 보고서가 생성된 뒤 HTML을 다시 만들면 전체 결과가 포함됩니다.</p></section>')
            continue
        result = renderer.markdown(source, key)
        record = {'id': key, 'path': relative, 'bytes': source.stat().st_size,
                  'sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'headings': len(result.headings)}
        records.append(record)
        sublinks = ''.join(f'<li class="toc-depth-{min(h.level+1,4)}"><a href="#{h.slug}">{html.escape(h.text)}</a></li>' for h in result.headings if h.level <= 3)
        toc[-1] = toc[-1][:-5] + f'<details><summary>세부 목차</summary><ol>{sublinks}</ol></details></li>'
        body = prefix + renderer.download(source, '원문 Markdown 저장') + '</header>' + result.body
        for filename, caption in CHARTS.get(key, []):
            path = source.parent/filename
            if path.resolve() not in renderer.images:
                body += renderer.image(path, caption)
        # Keep compact result summaries portable even when the source omitted links.
        csv_name = 'capital-10x.csv' if key == 'capital' else 'summary.csv'
        csv = source.parent/csv_name
        if key in {'selective', 'drawdown', 'abc', 'combinations', 'risk', 'capital'} and csv.is_file() and csv.resolve() not in renderer.downloads:
            body += '<p>' + renderer.download(csv, '전체 요약 CSV 저장') + '</p>'
        sections.append(body + '</section>')

    pine_files = sorted((root/'docs/tradingview/ppp').glob('*.pine')) + sorted((root/'docs/tradingview/ppp-combinations').glob('*.pine'))
    pine = ['<section class="chapter" id="pine"><header class="chapter-header"><span class="eyebrow">SOURCE LIBRARY</span><h2>Pine Script A–H 전체 소스</h2><p>아래 파일은 주문을 실행하지 않는 독립 지표입니다. A–C의 SMA20/50/100/200 진입 배열은 Python 백테스트에 적용했고, D–H에는 기본 SMA 배열 게이트가 포함되어 있습니다. 원본 PPP 공식과 동일하다고 확인한 코드가 아닙니다.</p></header>']
    for index, path in enumerate(pine_files, 1):
        code_id = f'pine-code-{index}'
        pine.append(f'<details class="pine" id="pine-{html.escape(path.stem)}"><summary>{html.escape(path.name)}</summary><div class="code-actions">' +
                    renderer.download(path, 'Pine 파일 저장') + f'<button type="button" data-copy="{code_id}">전체 복사</button><span class="copy-status" role="status"></span></div>' +
                    f'<pre><code id="{code_id}">{html.escape(path.read_text(encoding="utf-8"))}</code></pre></details>')
    pine.append('</section>')
    sections.append(''.join(pine))
    toc.append('<li><a class="chapter-link" href="#pine">Pine A–H 소스 · 다운로드</a></li>')
    drawdown_dir = root/'user_data/backtest_results/ppp-drawdown-2026-10-14'
    drawdown_ready = (drawdown_dir/'report.ko.md').is_file() and all((drawdown_dir/name).is_file() for name, _ in CHARTS['drawdown'])
    selective_dir = root/'user_data/backtest_results/ppp-selective-2026-10-14'
    selective_ready = ((selective_dir/'report.ko.md').is_file()
                       and (root/'docs/strategy-notes/ppp-selective-loss-controls.md').is_file()
                       and all((selective_dir/name).is_file() for name, _ in CHARTS['selective']))
    draft = bool(missing or renderer.missing_assets or len(pine_files) != 8)
    created = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    manifest = {'generated_utc': created, 'draft': draft, 'drawdown_ready': drawdown_ready, 'selective_ready': selective_ready,
                'sources': records, 'missing_sources': missing,
                'missing_assets': sorted(str(p) for p in renderer.missing_assets),
                'images': sorted(str(p.relative_to(root)) for p in renderer.images),
                'downloads': sorted(str(p.relative_to(root)) for p in renderer.downloads),
                'supplementary_workspace_files': sorted(str(p) for p in renderer.supplements),
                'tables': renderer.tables, 'table_rows': renderer.rows, 'pine_files': len(pine_files)}
    state = '일부 자료 대기 · 초안' if draft else '전체 자료 통합 완료'
    draft_notice = '<p><strong>일부 자료가 아직 없습니다.</strong> 본문의 대기 표시는 계산 결과나 성과를 의미하지 않습니다.</p>' if draft else ''
    document = f'''<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PPP 통합 연구 · 전액 10배와 선택적 손실 제어</title><style>{CSS}</style></head>
<body><div class="shell"><nav aria-label="연구 목차"><a class="brand" href="#top">PPP Research</a><div class="nav-kicker">2026.10.14 / 통합 연구</div><ol>{''.join(toc)}</ol><p class="nav-note">모든 원문·표·차트·Pine 소스를 한 파일로 보관합니다. 세부 목차를 펼치면 각 표의 맥락으로 바로 이동할 수 있습니다.</p></nav>
<main class="content" id="top"><header class="hero"><div class="eyebrow">PPP / SELECTIVE LOSS CONTROL RESEARCH</div><h1>전액 10배 진입과<br>선택적 손실 제어</h1><p class="lede">진입 시 전액 10배 노출을 유지하면서 손실 진행 중 거래에 적용하는 다섯 청산 정책을 비교합니다. 새 계산 보고서와 규칙 원문을 먼저 배치하고, A–H 지표·기존 백테스트·복리·낙폭 연구를 함께 보관합니다.</p><div class="pills"><span class="pill">{state}</span><span class="pill">원문 {len(records)}개</span><span class="pill">Pine {len(pine_files)}개</span><span class="pill">표 {renderer.tables}개 · {renderer.rows:,}행</span><span class="pill">내장 그림 {len(renderer.images)}개</span></div><div class="notice"><p><strong>원본 PPP 계산식은 미확인입니다.</strong> 여기의 지표는 재현 가설이며 영상의 수익 주장을 입증하지 않습니다.</p><p>편도 수수료 0.02%. 최신 연구는 손절 체결에 추가 0.05% 슬리피지를 비교하며 펀딩·실제 강제청산은 제외합니다. 기존 복리·낙폭 연구의 기본 계산은 슬리피지를 제외합니다. 본문의 손익비·PF·폐쇄 거래 낙폭·OHLC 경로 낙폭을 각각 구분해 읽어야 합니다.</p>{draft_notice}</div><p class="meta">HTML 생성 {created} · 원문 SHA-256은 함께 생성한 매니페스트에 기록</p></header>
<section class="overview" aria-label="읽기 안내"><div class="overview-grid"><article><h2>01 / 먼저 선택적 손실 제어</h2><p><a href="#selective">전액 10배를 유지한 청산 정책 비교</a>와 <a href="#method-selective">관측 시점·선택 조건·계산 규칙</a>을 읽습니다. 성과와 결론은 새 계산 보고서 원문에서 확인합니다. <a href="#drawdown">기존 배분·낙폭 연구</a>도 함께 비교할 수 있습니다.</p></article><article><h2>02 / 기간과 계좌를 구분</h2><p>Binance BTC/ETH/ZEC 1·3·5·15분은 같은 6개월입니다. MEXC 5·15분의 6개월과 1·3분의 짧은 기간은 별도로 평가합니다. 각 조합은 독립 $1,000 계좌이며 합산 포트폴리오가 아닙니다.</p></article><article><h2>03 / 표와 소스를 보관</h2><p>표 검색은 모든 표의 데이터 행에 적용합니다. 각 원문, 요약 CSV와 Pine 파일은 보고서 안에서 다운로드할 수 있습니다. ↗ 표시의 큰 거래 기록은 작업 공간의 보조 파일입니다.</p></article></div></section>
<div class="toolbar" role="search" aria-label="표 행 검색"><label for="table-search">표 검색</label><input type="search" id="table-search" placeholder="예: ZEC · ETH · 선택적 · R4" autocomplete="off"><button id="clear-search" type="button">초기화</button><small id="filter-status" role="status"></small><button class="print" id="print-report" type="button">인쇄 / PDF</button></div><noscript>모든 표와 원문은 JavaScript 없이 읽을 수 있습니다. 검색·복사·인쇄 버튼은 JavaScript가 필요합니다.</noscript>
{''.join(sections)}<footer class="footer">한 파일로 이동해도 본문·표·그림·Pine 소스·내장 요약 파일을 읽을 수 있습니다. 외부 참고 링크는 인터넷 연결이 필요하고 ↗ 보조 링크는 원래 작업 공간에서만 열립니다. 원문 성과를 재계산하거나 새로운 통계를 추정하지 않는 집계 보고서입니다.</footer></main></div><script>{JS}</script></body></html>'''
    return document, manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=None)
    args = parser.parse_args()
    output = args.output or args.root/DEFAULT_OUTPUT
    output = output.resolve()
    document, manifest = build_report(args.root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding='utf-8')
    manifest_path = output.with_suffix('.manifest.json')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'html': str(output), 'manifest': str(manifest_path), 'bytes': output.stat().st_size,
                      'draft': manifest['draft'], 'drawdown_ready': manifest['drawdown_ready'], 'selective_ready': manifest['selective_ready'],
                      'sources': len(manifest['sources']), 'pine_files': manifest['pine_files'],
                      'tables': manifest['tables'], 'rows': manifest['table_rows'], 'images': len(manifest['images'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
