"""Theme.js must be exactly what branding/tokens.json says.

The three QML surfaces read their colours from one generated file; if someone edits a hex value
in Theme.js by hand, this test fails instead of letting the palette drift.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "gen_theme.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_theme", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["gen_theme"] = module
    spec.loader.exec_module(module)
    return module


class ThemeTokens(unittest.TestCase):
    def setUp(self):
        self.gen = load_generator()
        self.tokens = json.loads((ROOT / "branding" / "tokens.json").read_text())
        self.theme = (ROOT / "shell" / "Theme.js").read_text()

    def test_generated_file_matches_tokens(self):
        expected = self.gen.render(self.tokens)
        self.assertEqual(self.theme, expected, "shell/Theme.js is stale — run scripts/gen_theme.py")

    def test_every_colour_is_present(self):
        for name, value in self.tokens["colour"].items():
            if isinstance(value, str):
                self.assertIn(f'var {name} = "{value}"', self.theme)

    def test_no_hex_literals_in_qml(self):
        """A hex colour in a QML file means someone bypassed the tokens."""
        offenders = []
        for qml in (ROOT / "shell").glob("*.qml"):
            for number, line in enumerate(qml.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("//"):
                    continue
                if "#" in line and any(
                    c.isdigit() or c in "abcdefABCDEF" for c in line.split("#", 1)[1][:6]
                ) and len(line.split("#", 1)[1]) >= 6:
                    # file:// URLs and other non-colour hashes are not what this guards
                    if "file://" in line or '"#"' in line:
                        continue
                    offenders.append(f"{qml.name}:{number}: {stripped}")
        self.assertEqual(offenders, [], "hex colours belong in branding/tokens.json:\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
