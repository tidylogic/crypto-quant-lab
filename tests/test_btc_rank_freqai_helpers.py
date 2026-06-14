from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_helpers():
    path = ROOT / "user_data/strategies/btc_rank_freqai_helpers.py"
    spec = importlib.util.spec_from_file_location("btc_rank_freqai_helpers", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


helpers = load_helpers()


class BtcRankFreqaiHelperTests(unittest.TestCase):
    def test_helper_loads_when_importlib_loader_does_not_register_module(self) -> None:
        path = ROOT / "user_data/strategies/btc_rank_freqai_helpers.py"
        spec = importlib.util.spec_from_file_location("freqtrade_loader_probe", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to import {path}")
        module = importlib.util.module_from_spec(spec)

        spec.loader.exec_module(module)

        self.assertTrue(hasattr(module, "decide_rank_signal"))

    def test_scalping_targets_label_tp_before_sl_by_side(self) -> None:
        long_target, short_target = helpers.create_scalping_targets_from_ohlc(
            close=[100.0, 100.0, 100.0, 100.0],
            high=[100.0, 100.7, 100.2, 100.1],
            low=[100.0, 99.9, 99.3, 99.8],
            take_profit_pct=0.005,
            stop_loss_pct=0.005,
            window=2,
        )

        self.assertEqual(long_target[:2], [1, 0])
        self.assertEqual(short_target[:2], [0, 1])
        self.assertIsNone(long_target[2])
        self.assertIsNone(short_target[2])

    def test_scalping_targets_treat_same_candle_tp_sl_as_stop_first(self) -> None:
        long_target, short_target = helpers.create_scalping_targets_from_ohlc(
            close=[100.0, 100.0, 100.0],
            high=[100.0, 100.7, 100.0],
            low=[100.0, 99.3, 100.0],
            take_profit_pct=0.005,
            stop_loss_pct=0.005,
            window=1,
        )

        self.assertEqual(long_target[0], 0)
        self.assertEqual(short_target[0], 0)

    def test_scalping_signal_score_combines_long_short_into_one_label(self) -> None:
        score = helpers.combine_scalping_targets(
            long_targets=[1, 0, 0, None],
            short_targets=[0, 1, 0, None],
        )

        self.assertEqual(score, [1.0, -1.0, 0.0, None])

    def test_rank_feature_builder_does_not_backfill_future_values(self) -> None:
        source = (ROOT / "user_data/strategies/btc_rank_freqai_helpers.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(".bfill(", source)

    def test_feature_column_list_includes_original_signal_families(self) -> None:
        self.assertIn("%-rank-ma3-distance", helpers.BASE_FEATURE_COLUMNS)
        self.assertIn("%-rank-rsi", helpers.BASE_FEATURE_COLUMNS)
        self.assertIn("%-rank-m5-trend-fast", helpers.MTF_FEATURE_COLUMNS)
        self.assertIn("%-rank-v3-close-pos", helpers.V3_FEATURE_COLUMNS)

    def test_decision_gate_accepts_high_rank_positive_ev_long(self) -> None:
        row = {
            "%-rank-m5-trend-fast": 0.0015,
            "%-rank-h1-trend-fast": 0.0010,
            "%-rank-m5-volume-ratio": 1.2,
            "%-rank-volatility": 0.001,
        }

        decision = helpers.decide_rank_signal(
            row,
            long_prob=0.12,
            short_prob=0.03,
            long_rank=0.93,
            short_rank=0.65,
            config=helpers.DecisionConfig(),
        )

        self.assertEqual(decision.signal, "long")
        self.assertEqual(decision.reason, "rank_entry_candidate")
        self.assertGreater(decision.expected_value, 0)

    def test_decision_gate_blocks_weak_edge_candidate(self) -> None:
        decision = helpers.decide_rank_signal(
            {},
            long_prob=0.12,
            short_prob=0.10,
            long_rank=0.81,
            short_rank=0.80,
            config=helpers.DecisionConfig(
                min_rank=0.75,
                min_edge_rank=0.03,
                long_min_rank=0.75,
            ),
        )

        self.assertEqual(decision.signal, "none")
        self.assertEqual(decision.reason, "edge_below_min")

    def test_rolling_percentile_rank_uses_current_window_distribution(self) -> None:
        ranks = helpers.rolling_percentile_rank_values(
            [0.5, 0.1, 0.4, 0.2],
            window=3,
            min_periods=1,
        )

        self.assertEqual(ranks, [1.0, 0.5, 2 / 3, 2 / 3])

    def test_local_gate_blocks_chasing_after_signal_candle(self) -> None:
        decision = helpers.DecisionResult(
            signal="long",
            reason="rank_entry_candidate",
            score=0.80,
            expected_value=0.001,
            effective_win_prob=0.70,
            confidence=0.93,
            edge_rank=0.16,
            regime="normal",
            side_rank=0.93,
            other_rank=0.77,
        )

        gate = helpers.evaluate_local_trade_gate(
            row={},
            decision=decision,
            current_price=100.20,
            signal_price=100.00,
            config=helpers.LocalTradeGateConfig(max_chase_pct=0.0015),
        )

        self.assertFalse(gate.allow)
        self.assertEqual(gate.reason, "local_gate_price_chase")

    def test_local_gate_blocks_low_volume_when_edge_is_weak(self) -> None:
        decision = helpers.DecisionResult(
            signal="short",
            reason="rank_entry_candidate",
            score=0.70,
            expected_value=0.0008,
            effective_win_prob=0.66,
            confidence=0.82,
            edge_rank=0.04,
            regime="normal",
            side_rank=0.82,
            other_rank=0.78,
        )

        gate = helpers.evaluate_local_trade_gate(
            row={"%-rank-m5-volume-ratio": 0.50},
            decision=decision,
            current_price=99.95,
            signal_price=100.00,
            config=helpers.LocalTradeGateConfig(
                min_volume_ratio=0.65,
                low_volume_min_edge=0.10,
            ),
        )

        self.assertFalse(gate.allow)
        self.assertEqual(gate.reason, "local_gate_low_volume_weak_edge")

    def test_local_gate_blocks_weak_safety_candidate_from_decision_gate(self) -> None:
        row = {
            "%-rank-volatility": 0.002,
            "%-rank-m5-volume-ratio": 1.2,
        }
        decision = helpers.decide_rank_signal(
            row,
            long_prob=0.02,
            short_prob=0.04,
            long_rank=0.76,
            short_rank=0.82,
            config=helpers.DecisionConfig(),
        )

        self.assertEqual(decision.signal, "short")

        gate = helpers.evaluate_local_trade_gate(
            row=row,
            decision=decision,
            current_price=100.00,
            signal_price=100.00,
            config=helpers.LocalTradeGateConfig(),
        )

        self.assertFalse(gate.allow)
        self.assertEqual(gate.reason, "local_gate_weak_safety_edge")

    def test_local_gate_blocks_low_safety_shock_candidate(self) -> None:
        decision = helpers.DecisionResult(
            signal="long",
            reason="rank_entry_candidate",
            score=0.64,
            expected_value=0.0005,
            effective_win_prob=0.66,
            confidence=0.70,
            edge_rank=0.10,
            regime="shock",
            side_rank=0.70,
            other_rank=0.60,
        )

        gate = helpers.evaluate_local_trade_gate(
            row={"%-rank-volatility": 0.007, "%-rank-m5-volume-ratio": 1.1},
            decision=decision,
            current_price=100.00,
            signal_price=100.00,
            config=helpers.LocalTradeGateConfig(),
        )

        self.assertFalse(gate.allow)
        self.assertEqual(gate.reason, "local_gate_shock_safety_low")

    def test_runtime_sizing_matches_source_defaults(self) -> None:
        self.assertEqual(helpers.position_fraction(0.91, fixed_leverage=100.0), 0.18)
        self.assertEqual(
            helpers.dynamic_leverage(0.91, 0.09, min_leverage=1.0, max_leverage=100.0),
            2.0,
        )


if __name__ == "__main__":
    unittest.main()
