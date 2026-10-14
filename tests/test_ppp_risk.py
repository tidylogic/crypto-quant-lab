"""Hand-calculated exit fixtures protect risk research from optimistic fills."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppp_backtest import Bars, simulate
try:
    from ppp_risk_backtest import simulate_risk, risk_features, risk_summary, path_diagnostics
except ModuleNotFoundError:
    simulate_risk = risk_features = risk_summary = None


def candles(opens, closes=None, lows=None, highs=None):
    o = np.array(opens, dtype=float)
    c = np.array(closes if closes is not None else opens, dtype=float)
    l = np.array(lows, dtype=float) if lows is not None else np.minimum(o, c)-1
    h = np.array(highs, dtype=float) if highs is not None else np.maximum(o, c)+1
    return Bars(np.arange(len(o), dtype=np.int64)*60, o, h, l, c, np.ones(len(o)), 60)


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(simulate_risk), 'Risk simulation has not been implemented')

    def run_case(self, b, profile, *, up=(0,), down=(), long=None, short=(),
                 sma20=0., sma50=0., atr=2., fee=0.):
        n = len(b.close)
        flags = lambda indexes: np.isin(np.arange(n), indexes)
        features = {key: np.broadcast_to(np.asarray(value, dtype=float), (n,))
                    for key, value in [('sma20', sma20), ('sma50', sma50), ('atr', atr)]}
        return simulate_risk(b, flags(up), flags(down), flags(up if long is None else long),
                             flags(short), features, profile=profile, start=0, end=n*60, fee=fee)

    def test_sma_close_stop_fills_next_open_and_ignores_entry_gate(self):
        b = candles([100, 100, 97, 90, 95], [100, 101, 96, 90, 95])
        result = self.run_case(b, 'R1', sma20=98, long=(0,))
        t = result['trades'][0]
        self.assertEqual((t['entry_price'], t['exit_price'], t['exit_time']), (100, 90, 180))
        self.assertEqual(t['exit_reason'], 'sma20')
        self.assertAlmostEqual(t['net_return'], -.10)

    def test_sma50_does_not_exit_on_equal_close(self):
        b = candles([100, 100, 100, 99, 90], [100, 100, 100, 98, 90])
        t = self.run_case(b, 'R2', sma50=100)['trades'][0]
        self.assertEqual(t['exit_time'], 240)

    def test_entry_candle_extreme_uses_later_close_not_intrabar_wick(self):
        b = candles([100, 100, 98, 95, 85, 90], [100, 101, 95, 89, 85, 90],
                    lows=[99, 90, 80, 88, 84, 89], highs=[101, 110, 99, 96, 86, 91])
        t = self.run_case(b, 'R3')['trades'][0]
        self.assertEqual((t['exit_signal_time'], t['exit_price']), (180, 85))
        self.assertEqual(t['exit_reason'], 'entry_candle')

    def test_short_entry_candle_stop_is_above_its_high(self):
        b = candles([100, 100, 103, 107, 115], [100, 99, 105, 111, 115],
                    lows=[99, 90, 102, 106, 114], highs=[101, 110, 120, 112, 116])
        t = self.run_case(b, 'R3', up=(), down=(0,), short=(0,))['trades'][0]
        self.assertEqual((t['side'], t['exit_price']), ('short', 115))
        self.assertAlmostEqual(t['net_return'], -.15)

    def test_atr_stop_freezes_signal_bar_atr_and_allows_gap_loss(self):
        b = candles([100, 100, 98, 95, 100], [100, 100, 96, 95, 100])
        t = self.run_case(b, 'R4', atr=[2, 100, 100, 100, 100])['trades'][0]
        self.assertEqual((t['entry_atr'], t['exit_price']), (2, 95))
        self.assertEqual(t['exit_reason'], 'atr_1_5')

    def test_combined_stop_uses_first_trigger(self):
        b = candles([100, 100, 100, 94, 100], [100, 101, 98, 94, 100],
                    lows=[99, 90, 97, 93, 99], highs=[101, 110, 101, 95, 101])
        t = self.run_case(b, 'R5', sma50=99)['trades'][0]
        self.assertEqual((t['exit_time'], t['exit_reason']), (180, 'sma50'))

    def test_fee_aware_break_even_does_not_arm_on_gross_one_atr(self):
        b = candles([100, 100, 101, 100, 104, 104], [100, 103, 100, 101, 104, 104],
                    lows=[99, 80, 99, 99, 103, 103])
        t = self.run_case(b, 'R6', fee=.01, down=(3,))['trades'][0]
        self.assertEqual((t['exit_time'], t['exit_reason']), (240, 'opposite_cross'))
        self.assertFalse(t['break_even_armed'])

    def test_break_even_uses_net_activation_and_later_close_gap(self):
        b = candles([100, 100, 104, 101, 100], [100, 105, 102, 101, 100],
                    lows=[99, 80, 101, 100, 99])
        t = self.run_case(b, 'R6', fee=.01)['trades'][0]
        self.assertEqual((t['exit_time'], t['exit_reason']), (180, 'break_even'))
        self.assertTrue(t['break_even_armed'])
        self.assertAlmostEqual(t['net_return'], -.0101)

    def test_short_break_even_accounts_for_exit_notional(self):
        b = candles([100, 100, 96, 100, 100], [100, 95, 99, 100, 100],
                    highs=[101, 120, 100, 101, 101])
        t = self.run_case(b, 'R6', up=(), down=(0,), short=(0,), fee=.01, sma50=200)['trades'][0]
        self.assertEqual((t['side'], t['exit_time'], t['exit_reason']), ('short', 180, 'break_even'))
        self.assertAlmostEqual(t['net_return'], -.02)

    def test_risk_only_exit_cannot_reopen_on_same_bar_cross(self):
        b = candles([100, 100, 97, 90, 91, 92], [100, 101, 96, 90, 91, 92])
        r = self.run_case(b, 'R1', sma20=98, up=(0, 2))
        self.assertEqual(len(r['trades']), 1)
        self.assertIsNone(r['open_position'])

    def test_opposite_cross_has_priority_and_qualified_reversal(self):
        b = candles([100, 100, 97, 90, 80, 80], [100, 101, 96, 90, 80, 80])
        r = self.run_case(b, 'R1', sma20=98, up=(0, 3), down=(2,), long=(0,), short=(2,))
        self.assertEqual([t['side'] for t in r['trades']], ['long', 'short'])
        self.assertEqual(r['trades'][0]['exit_reason'], 'opposite_cross')
        self.assertEqual(r['trades'][0]['exit_time'], r['trades'][1]['entry_time'])

    def test_r0_matches_original_simulator(self):
        b = candles([100, 101, 102, 99, 97, 98, 103, 101])
        n = len(b.close); f = lambda a: np.isin(np.arange(n), a)
        original = simulate(b, f([0, 4, 6]), f([2, 5]), f([0, 4, 6]), f([2]),
                            start=0, end=n*60, fee=.0002)
        r = self.run_case(b, 'R0', up=(0, 4, 6), down=(2, 5), short=(2,), fee=.0002)
        self.assertEqual(len(r['trades']), len(original['trades']))
        for got, want in zip(r['trades'], original['trades']):
            self.assertEqual({k: got[k] for k in want}, want)

    def test_payoff_is_average_win_over_average_loss_not_profit_factor(self):
        t = [dict(gross_return=x, net_return=x, side='long', duration_minutes=1, exit_reason='opposite_cross')
             for x in [.04, .02, -.01, -.03, -.02]]
        r = risk_summary(t)
        self.assertAlmostEqual(r['win_rate_pct'], 40)
        self.assertAlmostEqual(r['payoff_ratio'], 1.5)
        self.assertAlmostEqual(r['profit_factor'], 1)
        self.assertAlmostEqual(r['avg_win_pct'], 3)
        self.assertAlmostEqual(r['avg_loss_pct'], 2)
        self.assertAlmostEqual(r['closed_equity_max_drawdown_pct'], 5.8906)

    def test_atr_includes_gaps_and_first_bar_range(self):
        b = candles(np.arange(20)*10+100)
        f = risk_features(b)
        self.assertTrue(np.isnan(f['atr'][:13]).all())
        self.assertAlmostEqual(f['atr'][13], 145/14)

    def test_appending_future_candles_cannot_change_completed_exits(self):
        b = candles([100, 100, 97, 90, 120, 80, 100])
        full = self.run_case(b, 'R1', sma20=98)
        prefix = candles([100, 100, 97, 90])
        early = self.run_case(prefix, 'R1', sma20=98)
        self.assertEqual(full['trades'], early['trades'])

    def test_loss_excursion_includes_exit_open_gap_but_not_exit_bar_wick(self):
        b = candles([100, 100, 99, 80], lows=[99, 99, 98, 1], highs=[101, 101, 100, 200])
        t = dict(side='long', entry_price=100., exit_price=80., entry_time=60, exit_time=180,
                 gross_return=-.2, net_return=-.20036, duration_minutes=2.,
                 exit_reason='opposite_cross', entry_atr=2.)
        features = dict(sma20=np.zeros(4), sma50=np.zeros(4))
        _, paths = path_diagnostics(b, [t], features)
        self.assertAlmostEqual(paths[0]['mae_pct'], 20.)
        self.assertAlmostEqual(paths[0]['mfe_pct'], 1.)


if __name__ == '__main__':
    unittest.main()
