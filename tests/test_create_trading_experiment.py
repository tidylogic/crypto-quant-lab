import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents/scripts/create-trading-experiment.sh"


class CreateTradingExperimentTests(unittest.TestCase):
    def run_generator(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_creates_four_korean_template_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator("ema-bollinger-retest", "--output-root", tmp)
            target = Path(tmp) / "ema-bollinger-retest"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                {path.name for path in target.iterdir()},
                {
                    "strategy-idea.md",
                    "market-regime.md",
                    "backtest-evaluation.md",
                    "experiment-log.md",
                },
            )
            self.assertIn("전략 아이디어", (target / "strategy-idea.md").read_text())

    def test_rejects_invalid_or_existing_slug_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotEqual(
                self.run_generator("bad/name", "--output-root", tmp).returncode, 0
            )
            self.assertEqual(self.run_generator("demo", "--output-root", tmp).returncode, 0)
            original = (Path(tmp) / "demo" / "strategy-idea.md").read_text()
            self.assertNotEqual(
                self.run_generator("demo", "--output-root", tmp).returncode, 0
            )
            self.assertEqual(original, (Path(tmp) / "demo" / "strategy-idea.md").read_text())


if __name__ == "__main__":
    unittest.main()
