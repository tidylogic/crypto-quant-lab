"""Time causality, sequential failures and risk stops for MA support entries."""
import sys,unittest,tempfile
from unittest.mock import patch
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ppp_backtest import Bars,resample,smooth
try:
    from ppp_support_ladder import simulate_ladder,prepare
except ImportError:
    simulate_ladder=prepare=None


def fixture(close,source_indices=(0,),opposite_indices=(),seconds=300):
    c=np.array(close,float);n=len(c);b=Bars(np.arange(n)*60,c-.1,c+.15,c-.15,c,np.ones(n),60)
    d=dict(parent_seconds=seconds,mas=np.tile([100.,99.,98.,97.],(n,1)),atr=np.ones(n),
        bull=np.ones(n,bool),bear=np.zeros(n,bool),source_long=np.isin(np.arange(n),source_indices),source_short=np.zeros(n,bool),
        up=np.isin(np.arange(n),source_indices),down=np.isin(np.arange(n),opposite_indices),
        parent_event=np.isin(np.arange(n),source_indices+opposite_indices),source_time=np.arange(n)*60,
        base_bits=np.full(n,4,dtype=np.int32))
    return b,d


class SupportTests(unittest.TestCase):
    def setUp(self):self.assertTrue(callable(simulate_ladder),'Support ladder engine missing')

    def test_cannot_use_pre_signal_candle_low_as_support(self):
        b,d=fixture([100.1,101.,101.]);r=simulate_ladder(b,d,'W0',end=180)
        self.assertFalse(r['positions'])

    def test_failed20_then50_requires_a_new_confirmation_candle(self):
        b,d=fixture([100.3,99.1,99.1,99.3,99.4]);r=simulate_ladder(b,d,'W0',end=300)
        p=r['positions'][0];self.assertEqual(p['entry_time'],180);self.assertEqual(p['entry_support_index'],1)

    def test_raw_opposite_cross_cancels_waiting_even_when_new_entry_filters_fail(self):
        b,d=fixture([101.,100.1,100.2,100.3],opposite_indices=(1,));r=simulate_ladder(b,d,'W0',end=240)
        self.assertFalse(r['positions'])

    def test_failed_nearest_support_cannot_be_replaced_with_a_lower_line_to_avoid_exit(self):
        b,d=fixture([100.3,100.4,99.8,99.7]);r=simulate_ladder(b,d,'N0',end=240)
        p=r['positions'][0];self.assertEqual(p['exit_time'],180);self.assertEqual(p['exit_reason'],'nearest_ma20')

    def test_retry_requires_fresh_signal_and_deeper_support(self):
        b,d=fixture([100.2,100.1,99.8,99.1,99.1,99.1,99.2,99.3],source_indices=(0,4));r=simulate_ladder(b,d,'R0',end=480)
        self.assertEqual(len(r['positions']),2)
        self.assertEqual(r['positions'][0]['exit_time'],180)
        self.assertEqual(r['positions'][1]['entry_time'],360)
        self.assertEqual(r['positions'][1]['entry_support_index'],1)
        b,d=fixture([100.2,100.1,99.8,99.1,99.1,99.1,99.2,99.3]);r=simulate_ladder(b,d,'R0',end=480)
        self.assertEqual(len(r['positions']),1)

    def test_short_is_price_mirror_of_long(self):
        b,d=fixture([100.3,99.1,99.1,99.3,99.4]);long=simulate_ladder(b,d,'W0',end=300)
        mirrored=Bars(b.timestamp,200-b.open,200-b.low,200-b.high,200-b.close,b.volume,60)
        d['mas']=200-d['mas'];d['bull'],d['bear']=d['bear'],d['bull'];d['source_long'],d['source_short']=d['source_short'],d['source_long'];d['up'],d['down']=d['down'],d['up']
        short=simulate_ladder(mirrored,d,'W0',end=300)
        self.assertEqual(long['positions'][0]['entry_time'],short['positions'][0]['entry_time'])
        self.assertEqual(short['positions'][0]['side'],'short')

    def test_last_minute_has_no_next_open_entry(self):
        b,d=fixture([100.3,100.1]);r=simulate_ladder(b,d,'W0',end=120)
        self.assertFalse(r['positions'])

    def test_parent_final_close_cannot_be_seen_in_earlier_minutes(self):
        c=100+np.arange(1800)*.01;b=Bars(np.arange(1800)*60,c,c+.1,c-.1,c,np.ones(1800),60)
        parent=resample(b,300);minute,data=prepare(b,parent,1050*60,1055*60)
        expected=smooth(parent.close,20)
        np.testing.assert_allclose(data['mas'][:4,0],round(expected[209],9),rtol=0,atol=0)
        self.assertEqual(data['mas'][4,0],round(expected[210],9))
        altered=c.copy();altered[1054]=10000
        future=Bars(b.timestamp,c,np.maximum(c+.1,altered),c-.1,altered,b.volume,60)
        _,later=prepare(future,resample(future,300),1050*60,1055*60)
        np.testing.assert_array_equal(data['mas'][:4],later['mas'][:4])

    def test_entry_parent_candle_stop_remains_active_after_first_minute(self):
        b,d=fixture([100.3,100.1,100.2,100.3,100.4,100.5])
        b.low[3]=98.5
        r=simulate_ladder(b,d,'W0',end=360)
        p=r['positions'][0]
        self.assertEqual(p['entry_time'],120);self.assertEqual(p['exit_time'],180)
        self.assertEqual(p['exit_available_time'],240);self.assertEqual(p['exit_reason'],'S2')
        self.assertAlmostEqual(p['exit_price'],p['entry_price']*.99)

    def test_five_minute_stop_ignores_a_recovered_one_minute_failure(self):
        b,d=fixture([100.3,100.4,99.8,100.2,100.3,100.4])
        fast=simulate_ladder(b,d,'N0',end=360,risk_seconds=60)
        slow=simulate_ladder(b,d,'N0',end=360,risk_seconds=300)
        self.assertEqual(fast['positions'][0]['exit_time'],180)
        self.assertEqual(slow['positions'][0]['remaining_fraction'],1.)

    def test_opposite_new_signal_does_not_inherit_failed_long_rung(self):
        b,d=fixture([100.3,100.1,99.8,99.7,99.7,99.7],source_indices=(0,),opposite_indices=(2,))
        d['source_short'][2]=True;d['bull'][2:]=False;d['bear'][2:]=True
        d['mas'][2:]=[100.,101.,102.,103.]
        r=simulate_ladder(b,d,'R0',end=360,trace=True)
        self.assertEqual(r['positions'][0]['entry_time'],120)
        self.assertEqual(r['support_index'][2],0)

    def test_s2_stop_advances_retry_even_if_close_recovers(self):
        b,d=fixture([100.2,100.1,100.2,100.3,99.1,99.1,99.2,99.3],source_indices=(0,3))
        b.low[2]=98.
        r=simulate_ladder(b,d,'R0',end=480,trace=True)
        self.assertEqual(r['support_index'][3],1)

    def test_array_break_resets_retry_even_when_s2_stops_on_that_minute(self):
        b,d=fixture([100.2,100.1,99.8,100.3,100.1,100.1,100.2],source_indices=(0,3))
        b.low[2]=98.;d['bull'][2]=False
        r=simulate_ladder(b,d,'R0',end=420,trace=True)
        self.assertEqual(r['support_index'][3],0)

    def test_diagnostic_export_accepts_heterogeneous_variant_counters(self):
        import ppp_support_ladder as module
        b,d=fixture([100.3,100.1,99.8,99.1,99.1,99.1,99.2,99.3],source_indices=(0,4))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.csv';path.write_text('fixture')
            case=('BTC','binance_um',5,b,None,0,path,None)
            with patch.object(module,'market_cases',return_value=[case]),patch.object(module,'prepare',return_value=(b,d)):
                module.run(Path(tmp)/'out')
            self.assertTrue((Path(tmp)/'out/diagnostics.csv').exists())


if __name__=='__main__':unittest.main()
