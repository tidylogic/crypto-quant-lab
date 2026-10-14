"""Intrabar exit diagnostics must respect information availability."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppp_backtest import Bars
try:
    from ppp_asset_selective import selective_states
except ModuleNotFoundError:
    selective_states=None


class SelectiveAssetTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(callable(selective_states),'Selective diagnostics are missing')

    def test_intrabar_stop_is_booked_at_close_and_allows_a_later_fresh_cross(self):
        a=np.full(6,100.)
        b=Bars(np.arange(6)*300,a,a+1,a-2,a,np.ones(6),300)
        g=dict(up=np.isin(np.arange(6),[0,3]),down=np.isin(np.arange(6),[1]),
               long_entry=np.isin(np.arange(6),[0]),short_entry=np.isin(np.arange(6),[1]))
        trades=[dict(side='long',entry=300,exit=300,exit_available_time=600,reason='S2',cash=900.),
                dict(side='short',entry=600,exit=1200,exit_available_time=1200,reason='opposite_cross',cash=1030.)]
        state,cash,terminal=selective_states(b,g,trades,None,start=0,end=1800,initial=1000.)
        self.assertTrue(state[0]&1024)
        self.assertTrue(state[1]&65536)
        self.assertTrue(state[1]&128)
        self.assertTrue(state[1]&2048)
        self.assertFalse(state[1]&8192)  # Not a queued next-open risk exit.
        self.assertEqual(cash[1],1000.)
        self.assertEqual(cash[2],900.)
        self.assertEqual(cash[4],1030.)
        self.assertIsNone(terminal)

    def test_final_bar_stop_has_a_terminal_close_point_not_a_fabricated_next_candle(self):
        a=np.full(3,100.)
        b=Bars(np.arange(3)*300,a,a+1,a-2,a,np.ones(3),300)
        g=dict(up=np.array([False,True,False]),down=np.zeros(3,bool),
               long_entry=np.array([False,True,False]),short_entry=np.zeros(3,bool))
        t=[dict(side='long',entry=600,exit=600,exit_available_time=900,reason='S2',cash=1e-20)]
        state,cash,terminal=selective_states(b,g,t,None,start=0,end=900,initial=1000.)
        self.assertTrue(state[1]&1024)
        np.testing.assert_array_equal(cash,[1000.,1000.,1000.])
        self.assertEqual(terminal,dict(time=900,cash=1e-20))


if __name__=='__main__':unittest.main()
