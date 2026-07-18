from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ShellScriptLineEndingsTests(unittest.TestCase):
    def test_risk_preset_generator_is_forced_to_lf_on_checkout(self) -> None:
        attributes = (REPO_ROOT / ".gitattributes").read_text()
        script = (REPO_ROOT / ".agents/scripts/create-risk-preset.sh").read_bytes()

        self.assertIn("*.sh text eol=lf", attributes)
        self.assertNotIn(b"\r\n", script)


if __name__ == "__main__":
    unittest.main()
