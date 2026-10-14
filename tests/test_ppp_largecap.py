"""Causal entry gates: early phase, extension and trading-cost budget."""
import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    from ppp_largecap_research import entry_gates, extra_features
except ModuleNotFoundError:
    entry_gates=extra_features=None
from ppp_backtest import Bars
from ppp_combo_backtest import build_features


class LargecapTests(unittest.TestCase):
    def setUp(self):self.assertTrue(callable(entry_gates),'Early entry gates missing')

    def fixture(self):
        # Genuine early cross: MFI40 and RVOL.8 fails the old G confirmation,
        # but should be accepted by the declared early setup. Phase80 and
        # extension2ATR are separate late setups to reject.
        f=dict(main_c=np.array([10.,80.,10.,10.]),mfi=np.full(4,40.),rvol=np.full(4,.8),
               adx=np.full(4,25.),plus_di=np.full(4,30.),minus_di=np.full(4,10.),
               hist=np.array([-.1,-.05,0,.05]),bull=np.ones(4,bool),bear=np.zeros(4,bool))
        x=dict(distance=np.array([.5,.5,2.,.5]),slope=np.full(4,.2),age_long=np.full(4,10),
               age_short=np.full(4,-1),atr_fee_ratio=np.array([4.,4.,4.,1.]))
        return f,x

    def test_early_quality_accepts_unconfirmed_flow_but_rejects_late_and_cost_thin_setups(self):
        f,x=self.fixture();long,short,bits=entry_gates('T2',f,x)
        np.testing.assert_array_equal(long,[True,False,False,False])
        self.assertFalse(short.any())

    def test_first_alignment_filter_rejects_mature_trends_without_lookahead(self):
        f,x=self.fixture();x['age_long']=np.array([49,10,10,10]);x['atr_fee_ratio'][:]=4
        long,_,_=entry_gates('T4',f,x)
        self.assertFalse(long[0])

    def test_appending_future_prices_cannot_change_earlier_metrics_or_gates(self):
        rng=np.random.default_rng(15);close=100+np.cumsum(rng.normal(.03,.2,900));t=np.arange(900)*300
        b=Bars(t,close,close+.25,close-.25,close,np.ones(900),300)
        part=b.subset(np.arange(900)<700)
        full_f,part_f=build_features(b),build_features(part)
        full_x,part_x=extra_features(b,full_f,.0002),extra_features(part,part_f,.0002)
        for key in part_x:np.testing.assert_allclose(full_x[key][:700],part_x[key],rtol=0,atol=0,equal_nan=True)
        for name in ['T1','T2','T3','T4','T5','T6']:
            a,c,bit=entry_gates(name,full_f,full_x);p,q,pbit=entry_gates(name,part_f,part_x)
            np.testing.assert_array_equal(a[:700],p);np.testing.assert_array_equal(c[:700],q);np.testing.assert_array_equal(bit[:700],pbit)


if __name__=='__main__':unittest.main()
