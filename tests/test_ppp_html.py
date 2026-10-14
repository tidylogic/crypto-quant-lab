"""Portable report behavior: assets, links, completeness and source changes."""
import base64
import importlib.util
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Elements(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.elements = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('ppp_research_html', ROOT/'scripts/ppp_research_html.py')
        cls.mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.mod
        spec.loader.exec_module(cls.mod)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.add('docs/tradingview/ppp/README.ko.md', '# 같은 제목\n\n내용 전체\n\n![기준 화면](reference.png)\n\n[영상](https://example.test/watch?v=a&t=408)\n\n[방법](../../strategy-notes/ppp-risk-controls.md)\n\n| 자산 | 값 |\n|---|---|\n| ZEC | 3.25 |\n')
        self.add('docs/strategy-notes/ppp-risk-controls.md', '# 같은 제목\n\n규칙 전체\n')
        self.add('docs/strategy-notes/ppp-drawdown-management.md', '# 배분 연구 규칙\n\n확정된 자기 계좌 상태만 사용\n')
        self.add('docs/tradingview/ppp/reference.png', b'\x89PNG\r\n\x1a\nfixture')
        self.add('docs/tradingview/ppp/ppp-a-stoch-rsi-v6.pine', '//@version=6\nindicator("<PPP>")\n')
        self.add('user_data/backtest_results/ppp-2026-10-14/report.ko.md', '# 기존 결과\n\n48개 비교 기록\n')
        self.add('user_data/backtest_results/ppp-2026-10-14/summary.csv', 'asset,value\nZEC,3.25\n')
        self.add('user_data/backtest_results/ppp-2026-10-14/trades.csv', 'SECRET_RAW_TRADE_ROWS')

    def tearDown(self):
        self.temp.cleanup()

    def add(self, name, value):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value if isinstance(value, bytes) else value.encode())

    def build(self):
        document, manifest = self.mod.build_report(self.root)
        return document, manifest, Elements(document).elements

    def test_source_image_is_embedded_and_content_survives(self):
        document, _, elements = self.build()
        images = [a['src'] for t, a in elements if t == 'img']
        self.assertEqual(len(images), 1)
        self.assertEqual(base64.b64decode(images[0].split(',')[1]), b'\x89PNG\r\n\x1a\nfixture')
        self.assertIn('내용 전체', document)
        self.assertIn('규칙 전체', document)
        self.assertIn('확정된 자기 계좌 상태만 사용', document)
        self.assertIn('3.25', document)

    def test_unique_ids_and_links_resolve_inside_report(self):
        _, _, elements = self.build()
        ids = [a['id'] for _, a in elements if 'id' in a]
        self.assertEqual(len(ids), len(set(ids)))
        fragments = [a['href'][1:] for t, a in elements if t == 'a' and a.get('href', '').startswith('#')]
        self.assertTrue(set(fragments).issubset(set(ids)))
        method = [a['href'] for t, a in elements if t == 'a' and a.get('href', '').startswith('#method-risk')]
        self.assertTrue(method)

    def test_external_ampersand_is_escaped_once(self):
        document, _, elements = self.build()
        self.assertIn('https://example.test/watch?v=a&amp;t=408', document)
        self.assertNotIn('https://example.test/watch?v=a&amp;amp;t=408', document)
        self.assertIn('https://example.test/watch?v=a&t=408', [a.get('href') for t, a in elements if t == 'a'])

    def test_downloads_embed_pine_and_summary_but_not_raw_trades(self):
        document, _, elements = self.build()
        downloads = {a['download']: a['href'] for t, a in elements if t == 'a' and 'download' in a}
        self.assertIn('ppp-a-stoch-rsi-v6.pine', downloads)
        self.assertEqual(base64.b64decode(downloads['ppp-a-stoch-rsi-v6.pine'].split(',')[1]).decode(), '//@version=6\nindicator("<PPP>")\n')
        self.assertIn('summary.csv', downloads)
        self.assertNotIn('SECRET_RAW_TRADE_ROWS', document)

    def test_drawdown_draft_becomes_complete_when_results_arrive(self):
        document, manifest, _ = self.build()
        self.assertTrue(manifest['draft'])
        self.assertIn('새 낙폭 결과 대기', document)
        self.add('user_data/backtest_results/ppp-drawdown-2026-10-14/report.ko.md', '# 새 낙폭 결과\n\n새로 계산한 결론 9.87\n')
        self.add('user_data/backtest_results/ppp-drawdown-2026-10-14/drawdown-comparison.png', b'comparison')
        self.add('user_data/backtest_results/ppp-drawdown-2026-10-14/drawdown-curves-zec5m.png', b'curves')
        document, manifest, _ = self.build()
        # Missing required older sources still keep a partial fixture in draft.
        self.assertTrue(manifest['draft'])
        self.assertNotIn('새 낙폭 결과 대기', document)
        self.assertIn('새로 계산한 결론 9.87', document)
        self.assertEqual(manifest['drawdown_ready'], True)

    def test_selective_study_waits_for_results_without_inventing_performance(self):
        document, manifest, elements = self.build()
        self.assertIn('새 선택적 손실 제어 결과 대기', document)
        self.assertFalse(manifest['selective_ready'])
        chapters = [a['id'] for t, a in elements if t == 'section' and a.get('class') == 'chapter']
        self.assertEqual(chapters[:3], ['selective', 'method-selective', 'drawdown'])
        self.assertEqual(self.mod.DEFAULT_OUTPUT.parent.name, 'ppp-selective-2026-10-14')

    def test_selective_results_and_charts_join_history_portably(self):
        study = 'user_data/backtest_results/ppp-selective-2026-10-14/'
        self.add(study + 'report.ko.md', '# 선택적 손실 제어\n\n보고서 원문 결론 7.654321\n\n[규칙](../../../docs/strategy-notes/ppp-selective-loss-controls.md)\n')
        self.add('docs/strategy-notes/ppp-selective-loss-controls.md', '# 선택적 손실 규칙\n\n전액 10배 진입을 유지하는 다섯 청산 정책\n')
        self.add(study + 'selective-comparison.png', b'selective comparison')
        self.add(study + 'selective-curves-zec5m.png', b'selective curves')
        self.add(study + 'summary.csv', 'policy,return\nS1,7.654321\n')
        document, manifest, elements = self.build()
        self.assertTrue(manifest['selective_ready'])
        self.assertTrue(manifest['draft'])  # The older partial fixture is still incomplete.
        self.assertNotIn('새 선택적 손실 제어 결과 대기', document)
        self.assertIn('보고서 원문 결론 7.654321', document)
        self.assertIn('전액 10배 진입을 유지하는 다섯 청산 정책', document)
        self.assertIn('48개 비교 기록', document)
        self.assertIn('내용 전체', document)
        image_bytes = [base64.b64decode(a['src'].split(',')[1]) for t, a in elements if t == 'img']
        self.assertIn(b'selective comparison', image_bytes)
        self.assertIn(b'selective curves', image_bytes)
        self.assertIn('#method-selective', [a.get('href') for t, a in elements if t == 'a'])
        summaries = [base64.b64decode(a['href'].split(',')[1]).decode() for t, a in elements if t == 'a' and a.get('download') == 'summary.csv']
        self.assertIn('policy,return\nS1,7.654321\n', summaries)
        self.assertIn('selective', [source['id'] for source in manifest['sources']])
        self.assertIn('method-selective', [source['id'] for source in manifest['sources']])


if __name__ == '__main__':
    unittest.main()
