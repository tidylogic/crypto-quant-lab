from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".agents/scripts/create-risk-preset.sh"


class CreateRiskPresetTests(unittest.TestCase):
    def run_generator(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_creates_korean_cards_for_each_risk_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for preset_id in (
                "STOP-VWAP-FAIL",
                "TP-VOLUME-EXIT",
                "SCALE-RECLAIM-PYRAMID",
            ):
                result = self.run_generator(preset_id, "--output-root", tmp)
                card = Path(tmp) / f"{preset_id}.md"
                self.assertEqual(result.returncode, 0, result.stderr)
                content = card.read_text()
                self.assertEqual(result.stderr, "")
                for required in ("# 리스크 프리셋 카드", preset_id, "## 적용 장세", "## 규칙", "## 비용과 실패 조건", "## 검토 확인"):
                    self.assertIn(required, content)

    def test_rejects_invalid_or_duplicate_id_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertNotEqual(
                self.run_generator("BAD-ID", "--output-root", tmp).returncode, 0
            )
            self.assertEqual(
                self.run_generator("STOP-TEST", "--output-root", tmp).returncode, 0
            )
            card = Path(tmp) / "STOP-TEST.md"
            original = card.read_text()
            self.assertNotEqual(
                self.run_generator("STOP-TEST", "--output-root", tmp).returncode, 0
            )
            self.assertEqual(original, card.read_text())


if __name__ == "__main__":
    unittest.main()
