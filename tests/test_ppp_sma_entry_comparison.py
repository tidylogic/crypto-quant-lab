"""Alternative SMA periods must affect gates and labels without changing fill clocks."""
import sys
import unittest
import tempfile
import json
import re
from types import SimpleNamespace
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from ppp_backtest import Bars, resample
from ppp_support_ladder import prepare, simulate_ladder
from ppp_asset_research import export_reports
try:
    from ppp_sma_entry_comparison import combine
except ImportError:
    combine=None
try:
    from ppp_sma_entry_comparison import capital_entries
except ImportError:
    capital_entries=None


class SmaEntryComparisonTests(unittest.TestCase):
    def test_funded_open_position_is_executed_but_unfunded_open_position_is_not(self):
        self.assertTrue(callable(capital_entries),'Open-position capital labeling is missing')
        positions=[dict(entry_time=60,remaining_fraction=0.),dict(entry_time=180,remaining_fraction=1.)]
        points=[dict(entry_time=60)]
        self.assertEqual(capital_entries(positions,points,dict(open_remaining_fraction=1.)),{60,180})
        self.assertEqual(capital_entries(positions,points,dict(open_remaining_fraction=0.)),{60})

    def test_exported_chart_keeps_requested_periods_and_separate_experiment_name(self):
        with tempfile.TemporaryDirectory() as directory:
            args=SimpleNamespace(asset='BTC',models=['G'],profiles=['direct'],fee=.0002,initial=1000.,leverage=10.,
                                 output=Path(directory),ma_periods=(30,60,120,240),model_name='추세·거래량 · SMA30/60/120/240')
            exports={'G':[dict(key='binance_um-5',venue='binance_um',timeframe_minutes=5)]}
            export_reports(args,dict(start_kst='start',end_exclusive_kst='end',summaries=[],provenance=[]),exports,{'G':{}})
            text=(Path(directory)/'btc-g-strategy.html').read_text()
            c=json.loads(re.search(r'<script id="configuration" type="application/json">(.*?)</script>',text,re.S)[1])
            self.assertEqual(c.get('ma_periods'),[30,60,120,240])
            self.assertEqual(c['model_name'],'추세·거래량 · SMA30/60/120/240')

    def test_alignment_gate_really_switches_to_the_requested_sma_periods(self):
        parent_closes=np.r_[np.full(180,90.),np.full(60,95.),np.full(30,100.),np.full(10,120.),np.full(20,101.),101.]
        c=np.repeat(parent_closes,5);n=len(c)
        b=Bars(np.arange(n)*60,c,c+.1,c-.1,c,np.ones(n),60);p=resample(b,300)
        _,old=prepare(b,p,1500*60,1501*60)
        _,new=prepare(b,p,1500*60,1501*60,levels=(30,60,120,240))
        self.assertFalse(old['bull'][0])
        self.assertTrue(new['bull'][0])
        self.assertFalse(new['bear'][0])

    def test_combined_win_rate_and_pf_weight_trades_instead_of_averaging_markets(self):
        self.assertTrue(callable(combine),'Comparison aggregation is missing')
        result=combine([dict(strategy_trades=1,strategy_wins=1,strategy_losses=0,gain_sum=1.,loss_sum=0.,net_sum=1.),
                        dict(strategy_trades=3,strategy_wins=0,strategy_losses=3,gain_sum=0.,loss_sum=3.,net_sum=-3.)])
        self.assertEqual(result['trades'],4)
        self.assertEqual(result['win_rate_pct'],25.)
        self.assertAlmostEqual(result['profit_factor'],1/3)
        self.assertAlmostEqual(result['payoff_ratio'],1.)
    def test_sma30_uses_only_closed_source_candles_and_does_not_read_future_close(self):
        prices=100+np.arange(2000)*.01
        bars=Bars(np.arange(2000)*60,prices,prices+.1,prices-.1,prices,np.ones(2000),60)
        _, data=prepare(bars,resample(bars,300),1500*60,1505*60,levels=(30,60,120,240))
        self.assertEqual(data['ma_periods'],(30,60,120,240))
        self.assertAlmostEqual(data['mas'][0,0],114.265)
        self.assertAlmostEqual(data['mas'][4,0],114.315)
        changed=prices.copy();changed[1504]=10000
        future=Bars(bars.timestamp,prices,np.maximum(prices+.1,changed),prices-.1,changed,bars.volume,60)
        _, later=prepare(future,resample(future,300),1500*60,1505*60,levels=(30,60,120,240))
        np.testing.assert_array_equal(data['mas'][:4],later['mas'][:4])

    def test_new_set_requires_240_candles_of_source_warmup(self):
        c=np.arange(1500,dtype=float)+100
        bars=Bars(np.arange(1500)*60,c,c+.1,c-.1,c,np.ones(1500),60)
        with self.assertRaisesRegex(ValueError,'warmup'):
            prepare(bars,resample(bars,300),1050*60,1055*60,levels=(30,60,120,240))

    def test_confirmation_waits_after_signal_but_both_modes_use_same_source_sma60_exit(self):
        close=np.array([100.3,100.4,99.7,100.2,99.7,99.7,99.8])
        b=Bars(np.arange(7)*60,close-.1,close+.15,close-.15,close,np.ones(7),60)
        b.low[1]=100.05
        d=dict(parent_seconds=300,ma_periods=(30,60,120,240),mas=np.tile([100.,99.9,99.,98.],(7,1)),atr=np.ones(7),
               bull=np.ones(7,bool),bear=np.zeros(7,bool),source_long=np.arange(7)==0,source_short=np.zeros(7,bool),
               up=np.arange(7)==0,down=np.zeros(7,bool),parent_event=np.isin(np.arange(7),[0,4]),
               source_time=np.zeros(7,dtype=int),base_bits=np.full(7,4,dtype=np.int32))
        direct=simulate_ladder(b,d,'B0',end=420)
        wait=simulate_ladder(b,d,'W0',end=420,config=dict(wait=True,retry=False,risk='baseline'))
        self.assertEqual(direct['positions'][0]['entry_time'],60)
        self.assertEqual(wait['positions'][0]['entry_time'],120)
        for result in [direct,wait]:
            self.assertEqual(result['positions'][0]['exit_time'],300)
            self.assertEqual(result['positions'][0]['exit_reason'],'sma60')


if __name__=='__main__':unittest.main()
