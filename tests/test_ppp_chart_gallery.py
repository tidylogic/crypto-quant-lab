"""A gallery must preserve result data and expose only its declared routes."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'scripts/ppp_chart_gallery.py'
sys.path.insert(0, str(MODULE.parent))


class GalleryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(MODULE.exists(), 'Reusable chart gallery is missing')
        spec = importlib.util.spec_from_file_location('ppp_chart_gallery', MODULE)
        self.mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.mod
        spec.loader.exec_module(self.mod)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'gallery'

    def add_chart(self, folder, asset='BTC', status='active', model='G'):
        p = self.root / folder / (asset.lower() + '.html')
        p.parent.mkdir(parents=True, exist_ok=True)
        config = dict(asset=asset, model=model, model_name='추세·거래량 전략', strategy_status=status,
                      fee=.0002, initial=1000, leverage=10, native_execution=True,
                      default_market='binance_um-5', default_profile='B0',
                      markets=[dict(key='binance_um-5', venue='binance_um', timeframe_minutes=5, six_months=True)],
                      summaries=[dict(profile='B0')])
        p.write_text('<!doctype html><html><head><title>fixture</title></head><body><main id="research">'
                     '<div id="chart"></div><table id="checks"></table></main>'
                     '<script id="configuration" type="application/json">'+json.dumps(config)+'</script>'
                     '<script id="data-binance_um-5" type="application/octet-stream">UNCHANGED_PAYLOAD</script>'
                     '</body></html>')
        return p

    def test_default_selects_latest_support_btc_instead_of_old_or_draft(self):
        self.add_chart('ppp-wld-2026-10-14', 'WLD', 'draft', 'C')
        self.add_chart('ppp-support-2026-10-14', 'ZEC')
        self.add_chart('ppp-support-2026-10-14', 'BTC')
        manifest = self.mod.build_gallery(self.root, self.out)
        selected = next(x for x in manifest['charts'] if x['id']==manifest['default_id'])
        self.assertEqual((selected['asset'], selected['group']), ('BTC', 'ppp-support-2026-10-14'))

    def test_chart_copy_preserves_market_payload_and_original_bytes(self):
        p = self.add_chart('ppp-support-2026-10-14')
        original = p.read_bytes()
        m = self.mod.build_gallery(self.root, self.out)
        c = m['charts'][0]
        copy = (self.out / c['file']).read_text()
        self.assertIn('UNCHANGED_PAYLOAD', copy)
        self.assertEqual(p.read_bytes(), original)
        self.assertEqual(c['markets'][0]['timeframe_minutes'], 5)
        self.assertEqual(c['execution_minutes'], 1)
        self.assertEqual(c['status'], 'active')

    def test_rebuild_discovers_new_coins_without_recataloguing_generated_copies(self):
        self.add_chart('ppp-support-2026-10-14')
        self.mod.build_gallery(self.root, self.out)
        self.add_chart('ppp-support-2026-10-14', 'SOL')
        m = self.mod.build_gallery(self.root, self.out)
        self.assertEqual(sorted(x['asset'] for x in m['charts']), ['BTC', 'SOL'])

    def test_plain_reports_are_not_mistaken_for_chart_pages(self):
        self.add_chart('ppp-support-2026-10-14')
        (self.root/'report.html').write_text('<html><h1>Report</h1></html>')
        m = self.mod.build_gallery(self.root, self.out)
        self.assertEqual(len(m['charts']), 1)

    def test_exporting_to_another_folder_does_not_duplicate_previously_built_charts(self):
        self.add_chart('ppp-support-2026-10-14')
        self.mod.build_gallery(self.root, self.out)
        second = self.mod.build_gallery(self.root, self.root/'another-export')
        self.assertEqual(len(second['charts']), 1)

    def test_server_routes_follow_rebuilt_catalog_without_restarting(self):
        self.add_chart('ppp-support-2026-10-14')
        self.mod.build_gallery(self.root, self.out)
        self.add_chart('ppp-support-2026-10-14', 'SOL')
        rebuilt = self.mod.build_gallery(self.root, self.out)
        sol = next(x for x in rebuilt['charts'] if x['asset']=='SOL')
        self.assertEqual(self.mod.route_path('/'+sol['file'], self.out), self.out/sol['file'])

    def test_archived_draft_keeps_its_status_and_model(self):
        self.add_chart('ppp-wld-2026-10-14', 'WLD', 'draft', 'E')
        m = self.mod.build_gallery(self.root, self.out)
        self.assertEqual((m['charts'][0]['status'], m['charts'][0]['model']), ('draft', 'E'))

    def test_server_rejects_traversal_and_undeclared_runtime_files(self):
        self.add_chart('ppp-support-2026-10-14')
        m = self.mod.build_gallery(self.root, self.out)
        self.assertEqual(self.mod.route_path('/', self.out, m), self.out/'index.html')
        self.assertIsNone(self.mod.route_path('/%2e%2e/secrets.json', self.out, m))
        self.assertIsNone(self.mod.route_path('/browser-profile/Cookies', self.out, m))
        c = m['charts'][0]
        self.assertEqual(self.mod.route_path('/'+c['file'], self.out, m), self.out/c['file'])


if __name__ == '__main__':
    unittest.main()
