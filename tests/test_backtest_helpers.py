from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


detect_changed_strategies = load_script(
    "detect_changed_strategies", "scripts/detect_changed_strategies.py"
)
summarize_backtest = load_script("summarize_backtest", "scripts/summarize-backtest.py")


class SummarizeBacktestTests(unittest.TestCase):
    def test_strategy_table_formats_fraction_fields_as_percentages(self) -> None:
        table = summarize_backtest.format_strategy_table(
            {
                "ScalpingFreqaiStrategy": {
                    "total_trades": 998,
                    "profit_total": -0.03870807016,
                    "profit_total_abs": -38.70807016,
                    "max_drawdown_account": 0.039180243,
                    "wins": 416,
                    "draws": 0,
                    "losses": 582,
                    "profit_factor": 0.522018,
                }
            }
        )

        self.assertIn("-3.87%", table)
        self.assertIn("3.92%", table)
        self.assertIn("-38.708", table)
        self.assertIn("0.52", table)
        self.assertNotIn("-0.03870807016", table)

    def test_strategy_table_preserves_existing_percent_fields(self) -> None:
        table = summarize_backtest.format_strategy_table(
            {
                "ScalpingFreqaiStrategy": {
                    "total_trades": 10,
                    "profit_total_pct": 1.25,
                    "profit_total_abs": 12.5,
                    "max_drawdown_pct": 0.75,
                    "wins": 6,
                    "draws": 0,
                    "losses": 4,
                    "profit_factor": 1.2,
                }
            }
        )

        self.assertIn("1.25%", table)
        self.assertIn("0.75%", table)

    def test_newest_result_file_ignores_helper_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_dir = Path(tmp)
            result = results_dir / "backtest-result-2026-06-12_16-03-45.json"
            helper = results_dir / ".last_result.json"
            result.write_text("{}", encoding="utf-8")
            helper.write_text("{}", encoding="utf-8")
            os.utime(helper, (result.stat().st_mtime + 10, result.stat().st_mtime + 10))

            self.assertEqual(summarize_backtest.newest_result_file(results_dir), result)


class DetectChangedStrategiesTests(unittest.TestCase):
    def test_deleted_strategy_file_reports_error(self) -> None:
        payload = detect_changed_strategies.detect(
            ["user_data/strategies/DeletedStrategy.py"]
        )

        self.assertFalse(payload["needs_backtest"])
        self.assertIn(
            "Changed strategy file does not exist: user_data/strategies/DeletedStrategy.py",
            payload["errors"],
        )

    def test_config_change_falls_back_to_existing_strategy(self) -> None:
        payload = detect_changed_strategies.detect(
            ["user_data/configs/config.freqai.example.json"]
        )

        self.assertTrue(payload["needs_backtest"])
        self.assertEqual(payload["errors"], [])
        self.assertIn("ScalpingFreqaiStrategy", payload["strategies"])


if __name__ == "__main__":
    unittest.main()
