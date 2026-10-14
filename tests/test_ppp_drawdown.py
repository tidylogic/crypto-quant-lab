"""Hand-derived sizing and feedback chronology for drawdown controls."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppp_backtest import Bars
from ppp_capital_replay import replay
try:
    from ppp_drawdown_backtest import manage, window_trades, validate_alternating_crosses
except ModuleNotFoundError:
    manage=window_trades=None


def trade(signal,entry,exit,p=100.,x=110.):
    return dict(side='long',entry_signal_time=signal,entry_time=entry,exit_time=exit,
                entry_price=p,exit_price=x,entry_atr=2.)


class DrawdownTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(manage),'Drawdown management is missing')
        p=np.full(30,100.)
        self.b=Bars(np.arange(30)*60,p,p+1,p-1,p,np.ones(30),60)
        self.f=dict(atr=np.full(30,.01))

    def go(self,trades,mode,**kwargs):
        return manage(self.b,trades,self.f,policy=mode,fee=kwargs.pop('fee',0.),**kwargs)

    def test_baseline_matches_existing_full_margin_cash_replay(self):
        t=[trade(0,60,120),trade(120,180,240,x=98.)]
        expected,_=replay(self.b,t,fee=.0002)
        got,_=self.go(t,'Q0',fee=.0002)
        for key in expected:self.assertAlmostEqual(got[key],expected[key]) if isinstance(expected[key],float) else self.assertEqual(got[key],expected[key])

    def test_half_and_quarter_allocation_scale_exposure(self):
        for mode,cash,notional in [('Q1',1500.,5000.),('Q2',1250.,2500.)]:
            with self.subTest(mode=mode):
                r,points=self.go([trade(0,60,120)],mode)
                self.assertAlmostEqual(r['closed_cash_usdt'],cash)
                self.assertAlmostEqual(points[0]['entry_notional'],notional)

    def test_fraction_pool_reserves_its_entry_fee(self):
        r,points=self.go([trade(0,60,120)],'Q1',fee=.0002)
        self.assertAlmostEqual(points[0]['entry_notional'],4990.01996007984)
        self.assertAlmostEqual(r['closed_cash_usdt'],1496.9061876247505)

    def test_atr_size_uses_signal_bar_not_later_volatility(self):
        self.f['atr']=np.r_[2.,np.full(29,200.)]
        r,points=self.go([trade(0,60,120)],'Q3')
        self.assertAlmostEqual(points[0]['margin_fraction'],1/30)
        self.assertAlmostEqual(r['closed_cash_usdt'],1033.3333333333333)

    def test_small_atr_cannot_allocate_more_than_half_the_account(self):
        _,points=self.go([trade(0,60,120)],'Q3')
        self.assertAlmostEqual(points[0]['margin_fraction'],.5)

    def test_two_loss_pause_does_not_know_same_open_reversal_loss(self):
        t=[trade(0,60,120,x=99.),trade(120,180,240,x=99.),
           trade(180,240,300,p=99.,x=100.),trade(300,360,420,x=99.),
           trade(600,660,720)]
        r,points=self.go(t,'Q4')
        self.assertEqual([p['entry_time'] for p in points],[60,180,240,660])
        self.assertEqual(r['skipped_cooldown'],1)
        self.assertEqual(r['cooldown_events'],1)

    def test_drawdown_shrink_uses_only_known_closed_results(self):
        t=[trade(0,60,120,x=90.),trade(120,180,240)]
        r,points=self.go(t,'Q5')
        self.assertAlmostEqual(points[1]['margin_fraction'],.125)
        self.assertAlmostEqual(r['closed_cash_usdt'],562.5)

    def test_drawdown_feedback_waits_until_after_exit_fill(self):
        t=[trade(0,60,120,x=90.),trade(60,120,180,p=90.,x=99.)]
        _,points=self.go(t,'Q5')
        self.assertAlmostEqual(points[1]['margin_fraction'],.5)

    def test_future_trades_cannot_change_past_size_and_cash(self):
        first=[trade(0,60,120,x=99.),trade(120,180,240,x=99.)]
        _,short=self.go(first,'Q6')
        _,long=self.go(first+[trade(600,660,720,x=200.)],'Q6')
        self.assertEqual(short,long[:2])

    def test_open_position_is_marked_with_its_allocated_size(self):
        c=self.b.close.copy();c[-1]=105.
        self.b=Bars(self.b.timestamp,self.b.open,self.b.high,self.b.low,c,self.b.volume,60)
        opened=trade(180,240,1800);opened.pop('exit_time');opened.pop('exit_price')
        r,_=self.go([],'Q1',open_position=opened)
        self.assertAlmostEqual(r['closed_cash_usdt'],1000.)
        self.assertAlmostEqual(r['end_marked_equity_usdt'],1250.)

    def test_interval_excludes_carried_trade_and_marks_cross_boundary_trade(self):
        journal=[trade(0,60,180),trade(180,240,600)]
        closed,opened=window_trades(journal,None,120,300)
        self.assertEqual(closed,[])
        self.assertEqual(opened['entry_time'],240)
        self.assertNotIn('exit_price',opened)

    def test_journal_replay_rejects_equality_touch_repeated_cross_direction(self):
        with self.assertRaises(ValueError):
            validate_alternating_crosses([False,True,False,True,False],[False,False,False,False,True])


if __name__=='__main__':unittest.main()
