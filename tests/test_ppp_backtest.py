"""Hand-derived checks for the PPP research simulator, not source-text checks."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppp_backtest import Bars, crosses, resample, simulate, sma_alignment, smooth


def bars(prices, times=None):
    values = np.array(prices, dtype=float)
    timestamps = np.array(times if times is not None else np.arange(len(prices)) * 60, dtype=np.int64)
    return Bars(timestamps, values, values + 1, values - 1, values, np.ones(len(values)), 60)


class PPPBacktestTests(unittest.TestCase):
    def test_entry_and_opposite_exit_use_next_open_even_after_trend_disappears(self):
        # A signal at index 0 enters at 1 (110), the opposite at 2 exits at 3 (121).
        b = bars([100, 110, 115, 121, 130])
        result = simulate(b, [True, False, False, False, False], [False, False, True, False, False],
                          [True, False, False, False, False], [False]*5, start=0, end=300, fee=0.0002)
        self.assertEqual(len(result['trades']), 1)
        trade = result['trades'][0]
        self.assertEqual((trade['entry_time'], trade['exit_time'], trade['side']), (60, 180, 'long'))
        self.assertAlmostEqual(trade['gross_return'], 0.10)
        self.assertAlmostEqual(trade['net_return'], 0.09958)

    def test_short_fee_is_charged_on_both_actual_notionals(self):
        b = bars([105, 100, 99, 90, 90])
        result = simulate(b, [False, False, True, False, False], [True, False, False, False, False],
                          [False]*5, [True, False, False, False, False], start=0, end=300, fee=0.0002)
        trade = result['trades'][0]
        self.assertEqual(trade['side'], 'short')
        self.assertAlmostEqual(trade['gross_return'], 0.10)
        self.assertAlmostEqual(trade['net_return'], 0.09962)

    def test_mixed_sma_order_blocks_entry_but_does_not_block_exit(self):
        b = bars([100, 101, 102, 103])
        result = simulate(b, [True, False, False, False], [False]*4,
                          [False]*4, [False]*4, start=0, end=240, fee=0)
        self.assertEqual(result['trades'], [])

    def test_last_open_position_is_reported_without_fake_end_exit(self):
        result = simulate(bars([100, 110, 120]), [True, False, False], [False]*3,
                          [True, False, False], [False]*3, start=0, end=180, fee=0)
        self.assertEqual(result['trades'], [])
        self.assertEqual(result['open_position']['entry_time'], 60)

    def test_final_closed_bar_cross_is_counted_without_inventing_a_fill(self):
        result = simulate(bars([100, 110, 120]), [False, False, True], [False]*3,
                          [True]*3, [False]*3, start=0, end=180, fee=0)
        self.assertEqual(result['end_signals_without_fill'], 1)
        self.assertEqual(result['trades'], [])
        self.assertIsNone(result['open_position'])

    def test_same_open_reversal_requires_new_direction_alignment(self):
        b = bars([100, 100, 101, 102, 99, 98])
        result = simulate(b, [True, False, False, False, True, False], [False, False, True, False, False, False],
                          [True, False, False, False, False, False], [False, False, True, False, False, False],
                          start=0, end=360, fee=0)
        self.assertEqual([t['side'] for t in result['trades']], ['long', 'short'])
        self.assertEqual(result['trades'][0]['exit_time'], result['trades'][1]['entry_time'])
        self.assertEqual(result['trades'][1]['exit_time'], 300)

    def test_preperiod_signals_cannot_create_period_positions(self):
        result = simulate(bars([100, 101, 102, 103]), [True, False, False, False], [False]*4,
                          [True]*4, [False]*4, start=120, end=240, fee=0)
        self.assertEqual(result['trades'], [])
        self.assertIsNone(result['open_position'])

    def test_missing_minutes_are_not_upsampled(self):
        b = bars([10, 12, 20, 22, 24], [0, 60, 180, 240, 300])
        out = resample(b, 180)
        self.assertEqual(out.timestamp.tolist(), [180])
        self.assertEqual(out.open.tolist(), [20])
        self.assertEqual(out.close.tolist(), [24])
        self.assertEqual(out.high.tolist(), [25])
        self.assertEqual(out.low.tolist(), [19])

    def test_strict_sma_order_and_warmup(self):
        bull, bear = sma_alignment(np.arange(1, 241, dtype=float))
        self.assertFalse(bull[:199].any())
        self.assertTrue(bull[199:].all())
        self.assertFalse(bear.any())
        bull, bear = sma_alignment(np.full(240, 10.0))
        self.assertFalse(bull.any() or bear.any())

    def test_cross_uses_previous_lines_and_rejects_nan(self):
        up, down = crosses([math.nan, 20, 21, 19, 19], [math.nan, 20, 20, 20, 20])
        self.assertEqual(up.tolist(), [False, False, True, False, False])
        self.assertEqual(down.tolist(), [False, False, False, True, False])

    def test_smoothing_numeric_fixture(self):
        out = smooth(np.array([math.nan, 1., 2., 3., 4.]), 3, 'SMA')
        np.testing.assert_allclose(out, [math.nan, math.nan, math.nan, 2., 3.], equal_nan=True)
        out = smooth(np.array([1., 2., 3., 4., 5.]), 3, 'RMA')
        np.testing.assert_allclose(out, [math.nan, math.nan, 2., 8/3, 31/9], equal_nan=True)


if __name__ == '__main__':
    unittest.main()
