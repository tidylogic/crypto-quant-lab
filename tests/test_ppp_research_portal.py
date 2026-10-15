"""Research publishing preserves sources and repairs links without exposing runtime files."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import ppp_chart_gallery as gallery
from ppp_research_portal import markdown


class ResearchPortalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name)
        self.out = self.source / 'gallery'
        self.study = self.source / 'ppp-support-2026-10-14'
        self.study.mkdir()

    def test_portal_publishes_pine_bytes_and_readable_explanations_without_charts(self):
        manifest = gallery.build_gallery(self.source, self.out)
        self.assertIn('resources', manifest, 'The gallery does not yet publish research materials')
        pine = next(r for r in manifest['resources'] if r.get('source') ==
                    'docs/tradingview/ppp-trend-volume/trend-volume-baseline-v6.pine')
        original = ROOT / pine['source']
        self.assertEqual(hashlib.sha256((self.out / pine['file']).read_bytes()).hexdigest(),
                         hashlib.sha256(original.read_bytes()).hexdigest())
        self.assertEqual(gallery.route_path('/' + pine['file'], self.out), self.out / pine['file'])
        self.assertEqual(gallery.route_path('/research.html', self.out), self.out / 'research.html')
        explanation = next(r for r in manifest['resources'] if r.get('source') ==
                           'docs/strategy-notes/ppp-support-ladder.md')
        self.assertIn('<table>', (self.out / explanation['file']).read_text())
        self.assertEqual(manifest['charts'], [])

    def test_reports_relink_declared_figures_and_stats_and_disable_local_private_links(self):
        report = self.study / 'index.html'
        report.write_text('<html><body><h1>Fixture</h1><img src="comparison.png">'
                          '<a href="summary.csv">Stats</a><a href="trades.csv">Journal</a>'
                          '<a href="file:///private/config.json">Private</a></body></html>')
        (self.study / 'comparison.png').write_bytes(b'PNG fixture')
        (self.study / 'summary.csv').write_text('symbol,win_rate_pct\nBTC,40\n')
        (self.study / 'trades.csv').write_text('private journal')
        before = report.read_bytes()
        manifest = gallery.build_gallery(self.source, self.out)
        self.assertIn('resources', manifest)
        resources = {r['source']: r for r in manifest['resources']}
        page = resources['ppp-support-2026-10-14/index.html']
        text = (self.out / page['file']).read_text()
        for name in ['comparison.png', 'summary.csv']:
            r = resources['ppp-support-2026-10-14/' + name]
            self.assertIn('../' + r['file'], text)
            self.assertIsNotNone(gallery.route_path('/' + r['file'], self.out))
        self.assertNotIn('file:///private', text)
        self.assertNotIn('href="trades.csv"', text)
        self.assertNotIn('ppp-support-2026-10-14/trades.csv', resources)
        self.assertEqual(report.read_bytes(), before)

    def test_unknown_outputs_and_symlinked_artifacts_do_not_become_public_routes(self):
        (self.study / 'browser.log').write_text('private log')
        (self.study / 'credentials.json').write_text('{"secret":"private"}')
        (self.study / 'unrelated.html').write_text('not a report')
        (self.source / 'private.png').write_bytes(b'private')
        (self.study / 'comparison.png').symlink_to(self.source / 'private.png')
        manifest = gallery.build_gallery(self.source, self.out)
        self.assertIn('resources', manifest)
        sources = {r['source'] for r in manifest['resources']}
        for name in ['browser.log', 'credentials.json', 'unrelated.html', 'comparison.png']:
            self.assertNotIn('ppp-support-2026-10-14/' + name, sources)
        self.assertIsNone(gallery.route_path('/../private.png', self.out))

    def test_markdown_images_render_with_escaped_alt_and_no_raw_html(self):
        rendered = markdown('![A < B](comparison.png)\n\n<script>alert(1)</script>',
                            lambda href: '../figures/published.png' if href=='comparison.png' else None)
        self.assertIn('<img src="../figures/published.png"', rendered)
        self.assertIn('alt="A &lt; B"', rendered)
        self.assertNotIn('<script>', rendered)

    def test_legacy_report_with_implicit_body_has_navigation_back_to_research(self):
        (self.study / 'index.html').write_text('<!doctype html><html><meta charset="utf-8">'
                                              '<style>h1{color:red}</style><h1>Legacy report</h1><table></table></html>')
        manifest = gallery.build_gallery(self.source, self.out)
        report = next(r for r in manifest['resources'] if r['kind']=='report')
        text = (self.out / report['file']).read_text()
        self.assertIn('href="../research.html#experiments"', text)
        self.assertIn('<h1>Legacy report</h1>', text)

    def test_sma_entry_comparison_report_and_aggregate_csv_are_available(self):
        folder=self.source/'ppp-sma-entry-2026-10-15';folder.mkdir()
        (folder/'index.html').write_text('<html><body>SMA comparison</body></html>')
        (folder/'aggregate.csv').write_text('sma_set,win_rate_pct\n30,40\n')
        manifest=gallery.build_gallery(self.source,self.out)
        published={r['source'] for r in manifest['resources']}
        self.assertIn('ppp-sma-entry-2026-10-15/index.html',published)
        self.assertIn('ppp-sma-entry-2026-10-15/aggregate.csv',published)


if __name__ == '__main__':
    unittest.main()
