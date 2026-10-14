"""Numeric fixtures and causal entry-filter checks for the new hypotheses."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ppp_backtest import Bars, simulate
from ppp_combo_backtest import build_features, direction_filters, dmi, macd, money_flow, relative_volume


def bars(prices, volume=None):
    close=np.array(prices,dtype=float)
    v=np.ones(len(close)) if volume is None else np.array(volume,dtype=float)
    return Bars(np.arange(len(close))*60,close,close+1,close-1,close,v,60)


class ComboTests(unittest.TestCase):
    def test_mfi_weights_price_changes_by_money_flow(self):
        # At index 3: up-money 11+12, down-money 9. Index4: up12, down9+8.
        actual=money_flow(bars([10,11,9,12,8]),3)
        self.assertAlmostEqual(actual[3],71.875)
        self.assertAlmostEqual(actual[4],100*12/29)

    def test_relative_volume_uses_previous_bars_not_current_spike(self):
        actual=relative_volume(np.array([10.]*20+[100.]),20)
        self.assertTrue(np.isnan(actual[19]))
        self.assertEqual(actual[20],10.)
        self.assertTrue(np.isnan(relative_volume(np.zeros(25),20)[-1]))

    def test_constant_macd_never_creates_momentum(self):
        main,signal,hist=macd(np.full(80,100.))
        np.testing.assert_allclose(main[np.isfinite(main)],0,atol=1e-12)
        np.testing.assert_allclose(signal[np.isfinite(signal)],0,atol=1e-12)
        np.testing.assert_allclose(hist[np.isfinite(hist)],0,atol=1e-12)

    def test_monotonic_dmi_has_only_positive_direction_and_adx100(self):
        plus,minus,adx=dmi(bars(np.arange(10.,40.)),2,2)
        self.assertGreater(plus[-1],0)
        self.assertEqual(minus[-1],0)
        self.assertAlmostEqual(adx[-1],100)

    def test_adx_threshold_and_direction_both_required(self):
        long,short=direction_filters('D',dict(adx=np.array([19.99,20,30,30]),plus_di=np.array([30,30,10,20]),minus_di=np.array([10,10,30,20])))
        self.assertEqual(long.tolist(),[False,True,False,False])
        self.assertEqual(short.tolist(),[False,False,True,False])

    def test_macd_filter_requires_sign_and_strengthening(self):
        long,short=direction_filters('E',dict(hist=np.array([1.,.5,.8,-.2,-.8])))
        self.assertEqual(long.tolist(),[False,False,True,False,False])
        self.assertEqual(short.tolist(),[False,False,False,True,True])

    def test_money_flow_and_relative_volume_do_not_create_direction_at50(self):
        f=dict(mfi=np.array([50.,60.,40.,60.]),rvol=np.array([2.,1.19,1.2,1.2]))
        long,short=direction_filters('F',f)
        self.assertEqual(long.tolist(),[False,True,False,True])
        self.assertEqual(short.tolist(),[False,False,True,False])
        long,short=direction_filters('G',f)
        self.assertEqual(long.tolist(),[False,False,False,True])
        self.assertEqual(short.tolist(),[False,False,True,False])

    def test_rsi_filter_includes55_and45_but_rejects_midzone(self):
        long,short=direction_filters('H',dict(rsi=np.array([55.,45.,50.,np.nan])))
        self.assertEqual(long.tolist(),[True,False,False,False])
        self.assertEqual(short.tolist(),[False,True,False,False])

    def test_false_new_entry_filter_never_suppresses_opposite_exit(self):
        b=bars([100,110,115,121,125])
        long,short=direction_filters('F',dict(mfi=np.array([60.,50,50,50,50])))
        result=simulate(b,[True,False,False,False,False],[False,False,True,False,False],
                        long,short,start=0,end=300,fee=.0002)
        self.assertEqual(len(result['trades']),1)
        self.assertEqual(result['trades'][0]['exit_time'],180)

    def test_appending_future_bars_preserves_all_past_features(self):
        close=100+np.sin(np.arange(800)/7)+.003*np.arange(800)
        whole=build_features(bars(close,100+np.arange(800)%31))
        prefix=build_features(bars(close[:600],100+np.arange(600)%31))
        for key in prefix:
            np.testing.assert_allclose(prefix[key],whole[key][:600],rtol=0,atol=1e-10,equal_nan=True,err_msg=key)


if __name__=='__main__':unittest.main()
