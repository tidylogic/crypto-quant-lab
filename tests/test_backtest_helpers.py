from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
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

    def test_summarize_backtest_fails_when_no_result_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            detection = tmp_path / "detection.json"
            output = tmp_path / "comment.md"
            detection.write_text(
                json.dumps(
                    {
                        "strategies": ["BtcRankFreqaiStrategy"],
                        "watched_changes": ["user_data/strategies/BtcRankFreqaiStrategy.py"],
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/summarize-backtest.py",
                    "--results-dir",
                    str(tmp_path / "missing-results"),
                    "--detection",
                    str(detection),
                    "--output",
                    str(output),
                    "--command",
                    "freqtrade backtesting",
                    "--timerange",
                    "20250301-20250415",
                    "--timeframe",
                    "5m",
                    "--freqai-model",
                    "LightGBMRegressor",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn(
                "No exported backtest result file was found.",
                output.read_text(encoding="utf-8"),
            )


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
        self.assertIn("BtcRankFreqaiStrategy", payload["strategies"])

    def test_strategy_helper_change_falls_back_to_existing_strategy(self) -> None:
        payload = detect_changed_strategies.detect(
            ["user_data/strategies/btc_rank_freqai_helpers.py"]
        )

        self.assertTrue(payload["needs_backtest"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["strategies"], ["BtcRankFreqaiStrategy"])

    def test_global_config_change_with_scoped_helper_backtests_all_strategies(self) -> None:
        payload = detect_changed_strategies.detect(
            [
                "user_data/strategies/btc_rank_freqai_helpers.py",
                "user_data/configs/config.freqai.example.json",
            ]
        )

        self.assertTrue(payload["needs_backtest"])
        self.assertEqual(payload["errors"], [])
        self.assertIn("BtcRankFreqaiStrategy", payload["strategies"])
        self.assertIn("ScalpingFreqaiStrategy", payload["strategies"])

    def test_backtest_script_only_change_backtests_all_strategies(self) -> None:
        payload = detect_changed_strategies.detect(["scripts/pr-backtest.sh"])

        self.assertTrue(payload["needs_backtest"])
        self.assertEqual(payload["errors"], [])
        self.assertIn("BtcRankFreqaiStrategy", payload["strategies"])
        self.assertIn("ScalpingFreqaiStrategy", payload["strategies"])
        self.assertEqual(payload["recommended_timeframe"], "1m")
        self.assertEqual(payload["recommended_extra_configs"], [])

    def test_btc_rank_scoped_change_with_script_change_uses_btc_runtime(self) -> None:
        payload = detect_changed_strategies.detect(
            [
                "scripts/pr-backtest.sh",
                "user_data/configs/config.btc-rank-freqai.example.json",
            ]
        )

        self.assertTrue(payload["needs_backtest"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["strategies"], ["BtcRankFreqaiStrategy"])
        self.assertEqual(payload["recommended_timeframe"], "5m")
        self.assertEqual(
            payload["recommended_extra_configs"],
            ["/freqtrade/user_data/configs/config.btc-rank-freqai.json"],
        )

    def test_btc_rank_config_change_backtests_only_btc_rank_strategy(self) -> None:
        payload = detect_changed_strategies.detect(
            ["user_data/configs/config.btc-rank-freqai.example.json"]
        )

        self.assertTrue(payload["needs_backtest"])
        self.assertEqual(payload["errors"], [])
        self.assertEqual(payload["strategies"], ["BtcRankFreqaiStrategy"])
        self.assertEqual(payload["recommended_timeframe"], "5m")
        self.assertEqual(
            payload["recommended_extra_configs"],
            ["/freqtrade/user_data/configs/config.btc-rank-freqai.json"],
        )

    def test_mixed_strategy_detection_keeps_generic_one_minute_timeframe(self) -> None:
        payload = detect_changed_strategies.detect(
            ["user_data/configs/config.freqai.example.json"]
        )

        self.assertTrue(payload["needs_backtest"])
        self.assertIn("BtcRankFreqaiStrategy", payload["strategies"])
        self.assertIn("ScalpingFreqaiStrategy", payload["strategies"])
        self.assertEqual(payload["recommended_timeframe"], "1m")
        self.assertEqual(payload["recommended_extra_configs"], [])

    def test_pr_backtest_workflow_lets_detection_choose_btc_timeframe(self) -> None:
        workflow = (ROOT / ".github/workflows/pr-backtest.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("BACKTEST_TIMEFRAME: ${{ vars.PR_BACKTEST_TIMEFRAME }}", workflow)
        self.assertIn("1m 5m 15m 1h 1d", workflow)
        self.assertIn("config.btc-rank-freqai.json", workflow)

    def test_manual_btc_backtest_appends_btc_overlay_and_five_minute_timeframe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docker_log = tmp_path / "docker-args.txt"
            fake_docker = tmp_path / "docker"
            fake_docker.write_text(
                "#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"${FAKE_DOCKER_LOG}\"\n",
                encoding="utf-8",
            )
            os.chmod(fake_docker, 0o755)

            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{tmp_path}:{env['PATH']}",
                    "FAKE_DOCKER_LOG": str(docker_log),
                    "STRATEGY": "BtcRankFreqaiStrategy",
                    "BACKTEST_RESULT_DIR": str(tmp_path / "results"),
                }
            )
            env.pop("BACKTEST_TIMEFRAME", None)
            env.pop("FREQTRADE_EXTRA_CONFIGS", None)

            subprocess.run(
                ["bash", "scripts/backtest.sh"],
                cwd=ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            args = docker_log.read_text(encoding="utf-8").splitlines()
            self.assertIn(
                "/freqtrade/user_data/configs/config.btc-rank-freqai.json",
                args,
            )
            self.assertEqual(args[args.index("--timeframe") + 1], "5m")

    def test_btc_rank_overlay_is_btc_only(self) -> None:
        config = json.loads(
            (ROOT / "user_data/configs/config.btc-rank-freqai.example.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(config["exchange"]["pair_whitelist"], ["BTC/USDT"])
        self.assertEqual(config["exchange"]["pair_blacklist"], [])
        self.assertEqual(
            config["freqai"]["feature_parameters"]["include_corr_pairlist"],
            ["BTC/USDT"],
        )
        self.assertEqual(
            config["freqai"]["feature_parameters"]["include_timeframes"],
            ["5m", "1h", "1d"],
        )


if __name__ == "__main__":
    unittest.main()
