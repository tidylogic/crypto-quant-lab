"""Market selection and genuine UTC aggregation using small local datasets."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from ppp_combo_backtest import dataset_cases


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.roots = {v: self.root/v for v in ('binance_um', 'mexc')}
        for root in self.roots.values():
            root.mkdir()
        for venue, symbol, filename, step in [
            ('binance_um','ETHUSDT','ETHUSDT-1m.csv',60),
            ('mexc','ETH_USDT','ETH_USDT-Min1.csv',60),
            ('mexc','ETH_USDT','ETH_USDT-Min5.csv',300),
            ('mexc','ETH_USDT','ETH_USDT-Min15.csv',900),
        ]:
            times=np.arange(0,90000,step,dtype=np.int64)
            rows=np.column_stack([times,np.full((len(times),4),100.),np.ones(len(times))])
            np.savetxt(self.roots[venue]/filename,rows,delimiter=',',header='timestamp,open,high,low,close,volume',comments='')

    def test_eth_selection_does_not_load_absent_btc_or_zec(self):
        cases=list(dataset_cases(assets=('ETH',),data_roots=self.roots,start=45000,end=90000,minute_start=45000))
        self.assertEqual(len(cases),8)
        self.assertEqual({(v,s) for v,s,*_ in cases},{('binance_um','ETHUSDT'),('mexc','ETH_USDT')})
        self.assertEqual({tf for _,_,tf,*_ in cases},{1,3,5,15})
        for _,_,_,b,start,_ in cases:
            self.assertEqual(start,45000)
            self.assertEqual(b.timestamp[-1]+b.seconds,90000)

    def test_three_minute_eth_uses_three_real_minute_volumes(self):
        cases=list(dataset_cases(assets=('ETH',),data_roots=self.roots,start=45000,end=90000,minute_start=45000))
        for _,_,tf,b,*_ in cases:
            if tf==3:
                self.assertTrue((b.volume==3).all())
                self.assertTrue((np.diff(b.timestamp)==180).all())

    def test_partial_mexc_window_waits_for_600_real_warmup_minutes(self):
        cases=list(dataset_cases(assets=('ETH',),data_roots=self.roots,start=0,end=90000,minute_start=0))
        for venue,_,tf,_,start,_ in cases:
            expected=36000 if venue=='mexc' and tf in(1,3) else 0
            self.assertEqual(start,expected)

    def test_invalid_or_duplicate_assets_are_rejected(self):
        for assets in [('ETH/USDT',),('ETH','ETH'),()]:
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                list(dataset_cases(assets=assets,data_roots=self.roots,start=0,end=90000,minute_start=0))


if __name__=='__main__':
    unittest.main()
