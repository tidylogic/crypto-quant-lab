import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents/scripts/create-trading-experiment.sh"
TEMPLATE_ROOT = REPO_ROOT / ".agents/templates/trading-experiments"
TEMPLATE_OUTPUT_FILES = {
    "strategy-idea-template.md": "strategy-idea.md",
    "market-regime-template.md": "market-regime.md",
    "backtest-evaluation-template.md": "backtest-evaluation.md",
    "experiment-log-template.md": "experiment-log.md",
}


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
                set(TEMPLATE_OUTPUT_FILES.values()),
            )
            for source_name, output_name in TEMPLATE_OUTPUT_FILES.items():
                self.assertEqual(
                    (target / output_name).read_text(),
                    (TEMPLATE_ROOT / source_name).read_text(),
                )

    def test_rejects_invalid_or_existing_slug_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotEqual(
                self.run_generator("bad/name", "--output-root", tmp).returncode, 0
            )
            self.assertEqual(self.run_generator("demo", "--output-root", tmp).returncode, 0)
            target = Path(tmp) / "demo"
            original_files = {
                output_name: (target / output_name).read_text()
                for output_name in TEMPLATE_OUTPUT_FILES.values()
            }
            self.assertNotEqual(
                self.run_generator("demo", "--output-root", tmp).returncode, 0
            )
            self.assertEqual(
                original_files,
                {
                    output_name: (target / output_name).read_text()
                    for output_name in TEMPLATE_OUTPUT_FILES.values()
                },
            )


if __name__ == "__main__":
    unittest.main()
