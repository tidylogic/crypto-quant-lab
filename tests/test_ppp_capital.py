"""Independent cash fixtures for full-margin compounding."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppp_backtest import Bars
try:
    from ppp_capital_replay import replay
except ModuleNotFoundError:
    replay=None


class CapitalTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(replay),'Capital replay is missing')
        a=np.array([100.,100.,110.,100.,80.])
        self.b=Bars(np.arange(5)*60,a,a+1,a-1,a,np.ones(5),60)

    def test_two_trades_reinvest_actual_new_balance(self):
        t=[dict(side='long',entry_time=60,exit_time=120,entry_price=100.,exit_price=110.),
           dict(side='short',entry_time=180,exit_time=240,entry_price=100.,exit_price=80.)]
        r,_=replay(self.b,t,fee=0,initial=1000,leverage=10)
        self.assertAlmostEqual(r['closed_cash_usdt'],6000.)

    def test_entry_fee_is_reserved_before_full_margin_position(self):
        t=[dict(side='long',entry_time=60,exit_time=120,entry_price=100.,exit_price=110.)]
        r,points=replay(self.b,t,fee=.0002,initial=1000,leverage=10)
        self.assertAlmostEqual(r['closed_cash_usdt'],1993.812375249501)
        self.assertAlmostEqual(points[0]['entry_notional'],9980.03992015968)

    def test_unfinished_position_has_entry_fee_and_mark_pnl_no_exit_fee(self):
        b=Bars(self.b.timestamp,self.b.open,self.b.high,self.b.low,np.array([100.,100.,100.,100.,105.]),self.b.volume,60)
        opened=dict(side='long',entry_time=180,entry_price=100.)
        r,_=replay(b,[],open_position=opened,fee=.0002,initial=1000,leverage=10)
        self.assertAlmostEqual(r['closed_cash_usdt'],1000.)
        self.assertAlmostEqual(r['end_marked_equity_usdt'],1497.005988023952)

    def test_intrabar_zero_equity_is_flagged_despite_profitable_exit(self):
        b=Bars(self.b.timestamp,self.b.open,self.b.high,np.array([99.,80.,109.,99.,79.]),self.b.close,self.b.volume,60)
        t=[dict(side='long',entry_time=60,exit_time=120,entry_price=100.,exit_price=110.)]
        r,_=replay(b,t,fee=0,initial=1000,leverage=10)
        self.assertEqual(r['price_zero_equity_events'],1)
        self.assertEqual(r['first_price_zero_equity_time'],60)
        self.assertEqual(r['ohlc_drawdown_upper_bound_pct'],100.)

    def test_overlapping_trades_are_not_treated_as_separate_full_balance_bets(self):
        t=[dict(side='long',entry_time=60,exit_time=240,entry_price=100.,exit_price=80.),
           dict(side='short',entry_time=180,exit_time=240,entry_price=100.,exit_price=80.)]
        with self.assertRaises(ValueError):
            replay(self.b,t,fee=0,initial=1000,leverage=10)

    def test_zero_equity_screen_includes_exit_open_gap(self):
        t=[dict(side='long',entry_time=60,exit_time=240,entry_price=100.,exit_price=80.)]
        b=Bars(self.b.timestamp,self.b.open,np.full(5,101.),np.full(5,99.),np.full(5,100.),self.b.volume,60)
        r,_=replay(b,t,fee=0,initial=1000,leverage=10)
        self.assertEqual(r['closed_cash_usdt'],0.)
        self.assertEqual(r['price_zero_equity_events'],1)
        self.assertEqual(r['first_price_zero_equity_time'],240)

    def test_favorable_exit_gap_peak_is_counted_before_exit_fee(self):
        t=[dict(side='long',entry_time=60,exit_time=240,entry_price=100.,exit_price=200.)]
        b=Bars(self.b.timestamp,self.b.open,np.full(5,100.),np.full(5,100.),np.full(5,100.),self.b.volume,60)
        r,_=replay(b,t,fee=.1,initial=1000,leverage=1)
        self.assertAlmostEqual(r['ohlc_drawdown_upper_bound_pct'],10.)


if __name__=='__main__':
    unittest.main()
