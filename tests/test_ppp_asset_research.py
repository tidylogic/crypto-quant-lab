"""Protect arbitrary-timeframe signal diagnostics and short-history labeling."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
try:
    from ppp_asset_research import decision_states, evaluation_start
except ModuleNotFoundError:
    decision_states = evaluation_start = None
from ppp_backtest import Bars
try:
    from ppp_asset_research import six_month_period
except ImportError:
    six_month_period = None


class AssetResearchTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(decision_states), 'Reusable diagnostics are missing')

    def test_three_minute_signal_and_risk_exit_block_same_candle_reentry(self):
        a = np.full(6, 100.)
        b = Bars(np.arange(6)*180, a, a+1, a-1, a, np.ones(6), 180)
        signals = dict(up=np.isin(np.arange(6), [0, 2]), down=np.isin(np.arange(6), [3]),
                       long_entry=np.isin(np.arange(6), [0, 2]), short_entry=np.isin(np.arange(6), [3]))
        t = dict(side='long', entry_time=180, exit_time=540, exit_reason='sma50')
        simulation = dict(trades=[t], open_position=dict(side='short', entry_time=720))
        masks, cash = decision_states(b, signals, simulation, [dict(exit_time=540, closed_cash_usdt=900.)], start=0, end=1080, initial=1000.)
        self.assertTrue(masks[0] & 1024)  # Entry is decided one real bar before fill.
        self.assertTrue(masks[1] & 256)
        self.assertTrue(masks[2] & 8192)
        self.assertFalse(masks[2] & (128 | 1024))
        self.assertTrue(masks[3] & 128)
        self.assertTrue(masks[3] & 2048)
        self.assertTrue(masks[4] & 512)
        np.testing.assert_array_equal(cash, [1000., 1000., 1000., 900., 900., 900.])

    def test_diagnostics_reject_a_journal_that_missed_an_eligible_entry(self):
        a = np.full(4, 100.)
        b = Bars(np.arange(4)*300, a, a+1, a-1, a, np.ones(4), 300)
        signals = dict(up=np.array([True, False, False, False]), down=np.zeros(4, bool),
                       long_entry=np.array([True, False, False, False]), short_entry=np.zeros(4, bool))
        with self.assertRaisesRegex(ValueError, 'entry'):
            decision_states(b, signals, dict(trades=[], open_position=None), [], start=0, end=1200, initial=1000.)

    def test_tiny_positive_account_cash_is_preserved_without_false_bankruptcy(self):
        a = np.full(6, 100.)
        b = Bars(np.arange(6)*60, a, a+1, a-1, a, np.ones(6), 60)
        signals = dict(up=np.isin(np.arange(6), [0, 3]), down=np.isin(np.arange(6), [2, 4]),
                       long_entry=np.isin(np.arange(6), [0, 3]), short_entry=np.zeros(6, bool))
        journal = [dict(side='long',entry_time=60,exit_time=180,exit_reason='opposite_cross'),
                   dict(side='long',entry_time=240,exit_time=300,exit_reason='opposite_cross')]
        _, cash = decision_states(b, signals, dict(trades=journal,open_position=None),
                                  [dict(exit_time=180,closed_cash_usdt=1e-20),dict(exit_time=300,closed_cash_usdt=5e-21)],
                                  start=0,end=360,initial=1000.)
        self.assertEqual(cash[3], 1e-20)
        self.assertEqual(cash[5], 5e-21)

    def test_short_minute_history_starts_after_warmup_instead_of_faking_six_months(self):
        a = np.full(1000, 100.)
        b = Bars(90000 + np.arange(1000)*60, a, a+1, a-1, a, np.ones(1000), 60)
        self.assertEqual(evaluation_start(b, 0, 150000, short_history=True), 126000)
        with self.assertRaisesRegex(ValueError, 'coverage'):
            evaluation_start(b, 0, 150000, short_history=False)

    def test_custom_short_full_period_is_not_labeled_six_months(self):
        self.assertTrue(callable(six_month_period), 'Calendar period classification is missing')
        self.assertTrue(six_month_period(1776092400, 1791903600))
        self.assertFalse(six_month_period(1776092400, 1777302000))


if __name__ == '__main__':
    unittest.main()
