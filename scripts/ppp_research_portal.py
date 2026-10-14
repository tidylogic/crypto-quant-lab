"""Publish curated PPP explanations, reports, figures and Pine beside the gallery."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
STUDIES = {
    'ppp-support': ('지지·저항 확인 / 손절 주기 비교', '신호 주기의 20→50→100→200 지지·저항을 1분봉으로 확인합니다. 손절은 1분 마감과 신호 주기 마감을 비교합니다. 기존 기준형을 함께 보존합니다.', 'ppp-support-ladder.md'),
    'ppp-largecap': ('진입 시점 개선 연구', 'BTC·ETH·BNB·SOL·XRP와 WLD·ZEC에서 초입 진입과 이격 제한을 비교했습니다. T2-R4는 공통성·비용 기준을 통과하지 못한 실험형입니다.', 'ppp-largecap-entry-refinement.md'),
    'ppp-wld-s2': ('WLD · ZEC 고수익 기준형 이전', 'ZEC의 G/R2+S2 조건을 WLD에 그대로 적용한 비교입니다. WLD에 맞춘 재최적화 결과와 구분합니다.', 'ppp-asset-research.md'),
    'ppp-wld': ('WLD · 초기 전략 비교', 'WLD에서 C/E/G와 기존 리스크 방식을 비교했습니다. G 이외의 시안은 draft로 보관합니다.', 'ppp-asset-research.md'),
    'ppp-selective': ('선택적 손실 관리 / 연속 손절 분석', '첫 봉 손절 등으로 손실을 줄이면서 기존 수익 거래를 얼마나 유지하는지 비교했습니다. 연속 손절과 놓친 진입을 차트로 검토합니다.', 'ppp-selective-loss-controls.md'),
    'ppp-drawdown': ('낙폭 최적화', '포지션 크기·중단·손절 정책의 잔고와 최대 낙폭을 비교했습니다. 거래가 적어져 낙폭이 낮아진 경우도 구분합니다.', 'ppp-drawdown-management.md'),
    'ppp-risk-eth': ('ETH 추가 / 복리·리스크 비교', 'BTC·ETH·ZEC의 C/E/G에 리스크 관리를 적용하고 $1,000·10배 복리 계좌를 계산했습니다.', 'ppp-risk-controls.md'),
    'ppp-risk': ('손실 거래 분석 / 리스크 관리', 'C/E/G의 손실 경로를 분석하고 이평선 실패·진입 봉·ATR 등 손절 후보를 비교했습니다.', 'ppp-risk-controls.md'),
    'ppp-combinations': ('보조지표 조합 D–H', 'ADX·DMI, MACD, MFI, 상대 거래량, RSI를 추가한 후보들을 같은 SMA 배열 조건에서 비교했습니다.', 'ppp-combinations.md'),
    'ppp': ('PPP 시안 A–C', '영상의 0–100 본선·시그널선에서 추론한 Stoch RSI·Stochastic·이중 Stochastic 시안입니다. 원본 계산식이 입증된 것은 아닙니다.', 'ppp-sma-alignment.md'),
}
FIGURES = {
    'reference-06m48s': ('PPP 영상 · 6분 48초 관찰 화면', '초기 지표 추론에 사용한 영상 화면입니다. 원본 지표의 계산식이 입증된 것은 아닙니다.'),
    'synthetic-comparison': ('PPP 시안 · 합성 입력 비교', '초기 세 시안의 형태를 합성 가격으로 비교한 그림입니다. 실제 코인 수익률과 구분합니다.'),
    'comparison-6m': ('6개월 보조지표 조합 비교', '코인·주기·조합별 성과를 비교한 통계 그림입니다.'),
    'expectancy-comparison': ('리스크 방식별 순기대값 비교', '수수료 후 평균 거래 수익을 비교합니다. 승률만 높아진 후보와 구분해서 보세요.'),
    'win-payoff-zec5m': ('ZEC 5분 · 승률과 손익비', '승률과 평균 이익/평균 손실의 관계를 비교합니다. 정규분포 그래프는 아닙니다.'),
    'capital-zec5m': ('ZEC 5분 · 복리 잔고 비교', '초기 $1,000·10배 계좌의 리스크 방식별 결과입니다.'),
    'drawdown-comparison': ('종료 잔고와 낙폭 비교', '잔고를 얼마나 유지하면서 낙폭을 줄였는지 함께 확인합니다.'),
    'drawdown-curves-zec5m': ('ZEC 5분 · 잔고와 낙폭 곡선', '시간에 따른 계좌와 낙폭 변화입니다.'),
    'selective-comparison': ('선택적 손절 · 잔고와 낙폭 비교', '수익 거래 보존과 손실 개선 사이의 결과를 비교합니다.'),
    'selective-curves-zec5m': ('ZEC 5분 · 선택적 손절 계좌 곡선', '같은 진입 전략에 손절 정책을 바꿨을 때의 계좌 경로입니다.'),
    'wld-zec-normalized': ('WLD–ZEC 가격 변화 비교', '동일 출발값으로 맞춘 가격 변화입니다. 전략 수익률 그래프와 구분합니다.'),
}
REPORT_NAMES = {'index.html', 'draft-history.html', 'ppp-research-report.html',
                'entry-diagnostics-chart.html', 'entry-diagnostics-full-chart.html', 'streak-chart-preview.html'}
SUMMARY_NAMES = {'summary.csv', 'capital-10x.csv', 'training.csv', 'validation.csv', 'diagnostics.csv', 'loss-streaks-all.csv'}


def study_info(group):
    for prefix, value in STUDIES.items():
        if group.startswith(prefix + '-'):
            return value
    return (group, '기존 연구 기록', '')


def safe_file(path, base):
    return path.is_file() and not path.is_symlink() and base.resolve() in path.resolve().parents and not any(
        p.is_symlink() for p in path.parents if p != base.parent)


def inline(text, resolve):
    """Render the subset used by these notes; never pass raw HTML through."""
    pattern = re.compile(r'(`[^`]+`|!?\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)')
    result = []
    for part in pattern.split(text):
        if part.startswith('`') and part.endswith('`'):
            result.append('<code>' + html.escape(part[1:-1]) + '</code>')
        elif part.startswith('**') and part.endswith('**'):
            result.append('<strong>' + html.escape(part[2:-2]) + '</strong>')
        elif match := re.fullmatch(r'(!?)\[([^\]]+)\]\(([^)]+)\)', part):
            target = resolve(match[3])
            if match[1]:
                result.append('<img src="' + html.escape(target, quote=True) + '" alt="' + html.escape(match[2], quote=True) + '" loading="lazy">'
                              if target else html.escape(match[2]) + ' <small>(로컬 그림)</small>')
            else:
                result.append('<a href="' + html.escape(target, quote=True) + '">' + html.escape(match[2]) + '</a>'
                              if target else html.escape(match[2]) + ' <small>(로컬 자료)</small>')
        else:
            result.append(html.escape(part))
    return ''.join(result)


def markdown(text, resolve):
    lines = text.splitlines(); result = []; i = 0
    while i < len(lines):
        line = lines[i]; i += 1
        if not line.strip():
            continue
        if line.startswith('```'):
            code = []
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]); i += 1
            i += 1
            result.append('<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>'); continue
        if match := re.match(r'^(#{1,6})\s+(.+)', line):
            level = len(match[1]); result.append(f'<h{level}>' + inline(match[2], resolve) + f'</h{level}>'); continue
        if line.lstrip().startswith('|') and i < len(lines) and re.fullmatch(r'[\s|:\-]+', lines[i]):
            cells = lambda row: row.strip().strip('|').split('|')
            result.append('<div class="table-scroll"><table><thead><tr>' + ''.join('<th>' + inline(c.strip(), resolve) + '</th>' for c in cells(line)) + '</tr></thead><tbody>'); i += 1
            while i < len(lines) and lines[i].lstrip().startswith('|'):
                result.append('<tr>' + ''.join('<td>' + inline(c.strip(), resolve) + '</td>' for c in cells(lines[i])) + '</tr>'); i += 1
            result.append('</tbody></table></div>'); continue
        if re.match(r'^\s*(?:[-*]|\d+\.)\s+', line):
            result.append('<ul>')
            while True:
                result.append('<li>' + inline(re.sub(r'^\s*(?:[-*]|\d+\.)\s+', '', line), resolve) + '</li>')
                if i >= len(lines) or not re.match(r'^\s*(?:[-*]|\d+\.)\s+', lines[i]): break
                line = lines[i]; i += 1
            result.append('</ul>'); continue
        paragraph = [line]
        while i < len(lines) and lines[i].strip() and not re.match(r'^(?:#|```|\||[-*] |\d+\. )', lines[i]):
            paragraph.append(lines[i]); i += 1
        result.append('<p>' + inline(' '.join(paragraph), resolve) + '</p>')
    return '\n'.join(result)


def build_research(source_root, output, charts):
    resources = []; originals = {}; mapping = {}
    def register(path, base, kind, title=None, group='', description=''):
        if not safe_file(path, base): return
        source = path.relative_to(base).as_posix()
        key = hashlib.sha256((kind + ':' + source).encode()).hexdigest()[:16]
        extension = '.html' if kind == 'document' else path.suffix
        folder = {'document':'notes', 'pine':'pine', 'report':'reports', 'figure':'figures', 'summary':'statistics'}[kind]
        file = folder + '/' + key + extension
        text = path.read_text() if kind in ('document', 'pine') else ''
        title = title or (next((s.lstrip('# ').strip() for s in text.splitlines() if s.startswith('# ')), path.stem) if kind=='document' else path.stem)
        r = dict(id=key, file=file, source=source, kind=kind, title=title, group=group, description=description)
        if kind == 'pine':
            r['code'] = text
            r['filename'] = path.name
            r['status'] = '기준형' if path.name=='trend-volume-baseline-v6.pine' else '실험형' if 'experimental' in path.name else '기존 G' if 'ppp-g-' in path.name else 'draft'
        if kind == 'figure':
            r['capture'] = path.stem not in FIGURES or path.stem=='reference-06m48s'
        resources.append(r); originals[key] = path; mapping[path.resolve()] = file

    for path in sorted((ROOT/'docs/strategy-notes').glob('ppp*.md')):
        register(path, ROOT, 'document')
    for directory in ['ppp', 'ppp-combinations', 'ppp-trend-volume']:
        folder = ROOT/'docs/tradingview'/directory
        register(folder/'README.ko.md', ROOT, 'document', 'Pine 안내 · ' + directory)
        for path in sorted(folder.glob('*.pine')):
            register(path, ROOT, 'pine')
    register(ROOT/'docs/research/ppp/README.ko.md', ROOT, 'document', '연구 실행·재현 안내')
    for name in ['reference-06m48s', 'synthetic-comparison']:
        title, description = FIGURES[name]
        register(ROOT/'docs/tradingview/ppp'/f'{name}.png', ROOT, 'figure', title,
                 description=description)
    groups = []
    for folder in sorted(source_root.glob('ppp-*'), reverse=True):
        if not folder.is_dir() or folder.is_symlink() or folder.resolve()==output.resolve() or re.fullmatch(r'ppp-(?:risk-eth|risk|combinations|support|largecap|selective|drawdown|wld-s2|wld)?-?\d{4}-\d{2}-\d{2}', folder.name) is None:
            continue
        name, description, note = study_info(folder.name)
        groups.append(dict(id=folder.name, title=name, description=description, note=note))
        for path in sorted(folder.iterdir()):
            if path.name in REPORT_NAMES:
                if safe_file(path, source_root) and 'id="gallery-chart-style"' not in path.read_text()[:150000]:
                    register(path, source_root, 'report', name + (' · draft 보관' if path.name=='draft-history.html' else ' · 전체 보고서' if path.name in ('index.html','ppp-research-report.html') else ' · '+path.stem), folder.name)
            elif path.name in ('report.ko.md', 'capital-10x.ko.md'):
                register(path, source_root, 'document', name + (' · 복리 계산' if path.name.startswith('capital') else ' · 통계와 설명'), folder.name)
            elif path.name in SUMMARY_NAMES:
                register(path, source_root, 'summary', name + ' · ' + path.stem, folder.name, '집계 통계 CSV. 거래 원장과 시세 원본은 포함하지 않습니다.')
            elif path.suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
                title, desc = FIGURES.get(path.stem, (path.stem, '이 실험에서 검토한 화면 캡처입니다. 전체 조건과 수치는 관련 보고서에서 확인하세요.'))
                register(path, source_root, 'figure', title, folder.name, desc)
    for c in charts:
        mapping[(source_root/c['source']).resolve()] = 'index.html#chart=' + c['id']

    def target(href, original, prefix):
        parsed = urlsplit(href)
        if href.startswith('#'): return href
        if parsed.scheme in ('http','https'): return href
        if parsed.scheme and parsed.scheme != 'file': return None
        path = Path(unquote(parsed.path)) if parsed.scheme=='file' else original.parent/unquote(parsed.path)
        resolved = mapping.get(path.resolve())
        # Reports may carry a copied canonical Pine file instead of the docs path.
        if not resolved and path.suffix=='.pine':
            resolved = next((r['file'] for r in resources if r['kind']=='pine' and r['filename']==path.name), None)
        if resolved:
            return prefix + resolved + ('#'+parsed.fragment if parsed.fragment and '#' not in resolved else '')
        return None

    page_template = (ROOT/'scripts/templates/ppp-research-document.html').read_text()
    for r in resources:
        dest = output/r['file']; dest.parent.mkdir(parents=True, exist_ok=True); original = originals[r['id']]
        if r['kind']=='document':
            body = markdown(original.read_text(), lambda href:target(href, original, '../'))
            dest.write_text(page_template.replace('@@TITLE@@', html.escape(r['title'])).replace('@@BODY@@', body))
        elif r['kind']=='report':
            text = original.read_text()
            def replace_link(match):
                attr, quote, href = match.groups()
                if href.startswith('data:'): return match[0]
                resolved = target(html.unescape(href), original, '../')
                if not resolved:
                    return 'data-unavailable="true" title="이 로컬 원본 파일은 자료실에 게시하지 않았습니다"' if attr=='href' else ''
                return attr+'='+quote+html.escape(resolved, quote=True)+quote
            text = re.sub(r'\b(href|src)=(["\'])(.*?)\2', replace_link, text)
            toolbar = '<div style="padding:12px;background:#182131;color:#e5ecf6;font:14px system-ui"><a style="color:#9cc4ff" href="../research.html#experiments">← 실험·결과 자료실</a> · '+html.escape(r['title'])+'</div>'
            if re.search(r'<body\b', text, re.I):
                text = re.sub(r'(<body\b[^>]*>)', lambda m:m[0]+toolbar, text, count=1, flags=re.I)
            else:
                # Several original reports rely on HTML's implicit body element.
                boundary = re.search(r'</head>', text, re.I) or re.search(r'</style>', text, re.I)
                at = boundary.end() if boundary else 0
                text = text[:at] + toolbar + text[at:]
            dest.write_text(text)
        else:
            dest.write_bytes(original.read_bytes())
    for g in groups:
        g['note_file'] = next((r['file'] for r in resources if r['source']=='docs/strategy-notes/'+g['note']), None)
    library = dict(resources=resources, groups=groups, chart_count=len(charts),
                   chart_links=[dict(id=c['id'], asset=c['asset'], group=c['group'], name=c['name']) for c in charts])
    template = (ROOT/'scripts/templates/ppp-research-portal.html').read_text()
    (output/'research.html').write_text(template.replace('@@LIBRARY@@', json.dumps(library, ensure_ascii=False).replace('<', '\\u003c')))
    return resources
