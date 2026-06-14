from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_strategy_module():
    path = ROOT / "user_data/strategies/BtcRankFreqaiStrategy.py"
    spec = importlib.util.spec_from_file_location("btc_rank_strategy_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import {path}")

    freqtrade_module = types.ModuleType("freqtrade")
    strategy_module = types.ModuleType("freqtrade.strategy")
    pandas_module = types.ModuleType("pandas")

    class IStrategy:
        pass

    class DataFrame:
        pass

    pandas_module.DataFrame = DataFrame
    pandas_module.Timestamp = lambda value: value
    pandas_module.Timedelta = lambda **kwargs: timedelta(**kwargs)
    pandas_module.isna = lambda value: value is None
    strategy_module.IStrategy = IStrategy
    module = importlib.util.module_from_spec(spec)

    with patch.dict(
        sys.modules,
        {
            "freqtrade": freqtrade_module,
            "freqtrade.strategy": strategy_module,
            "pandas": pandas_module,
        },
    ):
        sys.path.insert(0, str(ROOT))
        try:
            spec.loader.exec_module(module)
        finally:
            try:
                sys.path.remove(str(ROOT))
            except ValueError:
                pass

    return module


strategy_module = load_strategy_module()


class FakeRow(dict):
    def squeeze(self):
        return self


class FakeILoc:
    def __init__(self, row: dict) -> None:
        self.row = FakeRow(row)

    def __getitem__(self, index: int):
        return self.row


class FakeDataFrame:
    def __init__(self, row: dict) -> None:
        self.empty = False
        self.iloc = FakeILoc(row)


class FakeDataProvider:
    def __init__(self, dataframe: FakeDataFrame) -> None:
        self.dataframe = dataframe

    def get_analyzed_dataframe(self, pair: str, timeframe: str):
        return self.dataframe, None


class BtcRankFreqaiStrategyCallbackTests(unittest.TestCase):
    def strategy_with_row(self, row: dict):
        strategy = strategy_module.BtcRankFreqaiStrategy()
        strategy.dp = FakeDataProvider(FakeDataFrame(row))
        return strategy

    def candidate_row(self, signal: str = "long") -> dict:
        return {
            "date": datetime(2026, 6, 14, 1, tzinfo=timezone.utc),
            "open": 100.0,
            "close": 100.0,
            "rank_signal": signal,
            "rank_reason": "rank_entry_candidate",
            "rank_score": 0.82,
            "rank_expected_value": 0.0012,
            "rank_confidence": 0.94,
            "rank_long_rank": 0.94 if signal == "long" else 0.72,
            "rank_short_rank": 0.72 if signal == "long" else 0.94,
            "rank_regime": "normal",
            "%-rank-m5-volume-ratio": 1.2,
            "%-rank-m5-trend-fast": 0.001,
            "%-rank-h1-trend-fast": 0.001,
        }

    def test_confirm_trade_entry_blocks_current_blocked_kst_hour(self) -> None:
        strategy = self.strategy_with_row(self.candidate_row())

        allowed = strategy.confirm_trade_entry(
            pair="BTC/USDT",
            order_type="limit",
            amount=1.0,
            rate=100.0,
            time_in_force="gtc",
            current_time=datetime(2026, 6, 14, 3, tzinfo=timezone.utc),
            entry_tag="btc_rank_freqai_long",
            side="long",
        )

        self.assertFalse(allowed)

    def test_confirm_trade_entry_blocks_side_mismatch(self) -> None:
        strategy = self.strategy_with_row(self.candidate_row(signal="long"))

        allowed = strategy.confirm_trade_entry(
            pair="BTC/USDT",
            order_type="limit",
            amount=1.0,
            rate=100.0,
            time_in_force="gtc",
            current_time=datetime(2026, 6, 14, 1, tzinfo=timezone.utc),
            entry_tag="btc_rank_freqai_short",
            side="short",
        )

        self.assertFalse(allowed)

    def test_confirm_trade_entry_allows_matching_side_during_allowed_hour(self) -> None:
        strategy = self.strategy_with_row(self.candidate_row(signal="long"))

        allowed = strategy.confirm_trade_entry(
            pair="BTC/USDT",
            order_type="limit",
            amount=1.0,
            rate=100.0,
            time_in_force="gtc",
            current_time=datetime(2026, 6, 14, 1, tzinfo=timezone.utc),
            entry_tag="btc_rank_freqai_long",
            side="long",
        )

        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()
