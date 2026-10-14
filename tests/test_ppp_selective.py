"""Hand-calculated intrabar stops, partial exits, and causal boundaries."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppp_backtest import Bars
from ppp_capital_replay import replay
try:
    from ppp_selective_backtest import apply_policy, replay_selective
except ModuleNotFoundError:
    apply_policy=replay_selective=None


def bars():
    o=np.full(7,100.);h=o+1;l=o-0.5;c=o.copy()
    return Bars(np.arange(7)*60,o,h,l,c,np.ones(7),60)


def trade(side='long',opened=False):
    t=dict(side=side,entry_signal_time=0,entry_time=60,entry_price=100.,
           exit_time=240,exit_price=104.,exit_reason='opposite_cross')
    if opened:
        t.pop('exit_time');t.pop('exit_price');t.pop('exit_reason')
    return t


class SelectiveTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(apply_policy),'Selective engine missing')
        self.b=bars()

    def go(self,policy,fee=0.,slip=0.,t=None):
        p=apply_policy(self.b,trade() if t is None else t,policy,fee=fee,stop_slippage=slip)
        r,points=replay_selective(self.b,[p],fee=fee)
        return p,r,points

    def test_baseline_matches_previous_replay(self):
        p,r,_=self.go('S0',fee=.0002)
        old,_=replay(self.b,[trade()],fee=.0002)
        for key,value in old.items():self.assertEqual(r[key],value)

    def test_long_stop_on_entry_candle_is_not_a_next_open_exit(self):
        self.b.low[1]=97.
        p,r,_=self.go('S1')
        self.assertEqual(p['exit_time'],60)
        self.assertEqual(p['exit_available_time'],120)
        self.assertEqual(p['exit_price'],98.5)
        self.assertAlmostEqual(r['closed_cash_usdt'],850.)
        self.assertAlmostEqual(r['maximum_adverse_price_pct'],1.5)

    def test_short_stop_slippage_and_both_fees(self):
        self.b.high[1]=103.
        p,r,_=self.go('S1',fee=.0002,slip=.0005,t=trade('short'))
        x=101.5*1.0005
        self.assertAlmostEqual(p['exit_price'],x)
        self.assertAlmostEqual(r['closed_cash_usdt'],1000+10000/1.002*((1-x/100)-.0002*(1+x/100)))

    def test_gap_uses_adverse_open_and_excludes_later_wicks(self):
        self.b.open[2]=95.;self.b.low[2]=20.;self.b.high[2]=200.
        p,r,_=self.go('S1')
        self.assertEqual(p['exit_price'],95.)
        self.assertAlmostEqual(r['maximum_adverse_price_pct'],5.)
        self.assertLess(r['ohlc_drawdown_upper_bound_pct'],60.)

    def test_first_candle_policy_preserves_second_candle_recovery(self):
        self.b.low[2]=95.
        p,r,_=self.go('S3')
        self.assertEqual(p['exit_price'],104.)
        self.assertAlmostEqual(r['closed_cash_usdt'],1400.)
        self.assertEqual(self.go('S1')[0]['exit_price'],98.5)

    def test_first_candle_one_and_one_half_percent_differ(self):
        self.b.low[1]=98.8
        self.assertEqual(self.go('S2')[0]['exit_price'],99.)
        self.assertEqual(self.go('S3')[0]['exit_price'],104.)

    def test_partial_exit_keeps_remaining_quantity_and_charges_exact_fees(self):
        self.b.low[1]=98.
        p,r,_=self.go('S4',fee=.0002)
        net=.5*(.99-1)+.5*(1.04-1)-.0002*(1+.5*.99+.5*1.04)
        self.assertAlmostEqual(p['net_return'],net)
        self.assertAlmostEqual(r['closed_cash_usdt'],1000+10000/1.002*net)
        self.assertEqual(r['trades'],1)
        self.assertEqual(p['legs'][0]['fraction'],.5)

    def test_open_remainder_has_no_fictional_exit_fee(self):
        self.b.low[1]=98.;self.b.close[-1]=103.
        p,r,_=self.go('S4',fee=.0002,t=trade(opened=True))
        net=-.0002+.5*(-.01-.0002*.99)+.5*.03
        self.assertEqual(r['closed_cash_usdt'],1000.)
        self.assertAlmostEqual(r['end_marked_equity_usdt'],1000+10000/1.002*net)
        self.assertEqual(r['trades'],0)
        self.assertEqual(p['remaining_fraction'],.5)

    def test_stop_closes_previously_open_position(self):
        self.b.low[1]=97.
        p,r,_=self.go('S3',t=trade(opened=True))
        self.assertEqual(r['trades'],1)
        self.assertAlmostEqual(r['end_marked_equity_usdt'],850.)

    def test_signal_range_uses_known_signal_bar_and_next_open(self):
        self.b.low[0]=99.;self.b.close[1]=98.;self.b.open[2]=97.
        p,r,_=self.go('S5')
        self.assertEqual(p['exit_time'],120)
        self.assertEqual(p['exit_price'],97.)
        self.assertAlmostEqual(r['closed_cash_usdt'],700.)

    def test_signal_range_does_not_inspect_entry_bar_future_extrema(self):
        self.b.low[1]=90.;self.b.close[1]=99.25
        self.assertEqual(self.go('S5')[0]['exit_time'],120)
        self.b.low[1]=80.
        self.assertEqual(self.go('S5')[0]['exit_time'],120)

    def test_original_exit_open_precedes_stop_inside_exit_bar(self):
        self.b.low[4]=1.
        self.assertEqual(self.go('S1')[0]['exit_price'],104.)

    def test_append_future_candles_does_not_change_closed_trade(self):
        self.b.low[1]=97.
        a=apply_policy(self.b,trade(),'S3')
        short=self.b.subset(np.arange(3))
        b=apply_policy(short,trade(opened=True),'S3')
        for k in ('legs','net_return','exit_price','exit_time'):self.assertEqual(a[k],b[k])

    def test_half_stop_retains_exposure_to_later_adverse_prices(self):
        self.b.low[1]=98.;self.b.low[2]=95.
        _,r,_=self.go('S4')
        self.assertGreater(r['ohlc_drawdown_upper_bound_pct'],25.)

    def test_half_stop_adverse_metric_includes_slipped_execution_price(self):
        self.b.low[1]=98.99
        _,r,_=self.go('S4',slip=.0005)
        self.assertAlmostEqual(r['maximum_adverse_price_pct'],1.0495)


if __name__=='__main__':unittest.main()
