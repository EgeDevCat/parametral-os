#!/usr/bin/env python3
"""Generate shell/Theme.js from branding/tokens.json.

Why a JS library and not a QML singleton: a real singleton needs a qmldir in the config
directory, and Quickshell synthesises that file itself — shipping our own is fragile across
versions. A `.pragma library` module is imported once per engine and shared by every file that
imports it, which is the property we actually want: one place to change a colour.

    python3 scripts/gen_theme.py        # rewrite shell/Theme.js
    python3 scripts/gen_theme.py --check  # exit 1 if the checked-in file is stale
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "branding" / "tokens.json"
OUTPUT = ROOT / "shell" / "Theme.js"

HEADER = """// GENERATED FILE — do not edit. Source: branding/tokens.json, generator: scripts/gen_theme.py
.pragma library

"""


def render(tokens: dict) -> str:
    colour = tokens["colour"]
    metric = tokens["metric"]
    lines = [HEADER]

    for name, value in colour.items():
        if isinstance(value, str):
            lines.append(f'var {name} = "{value}"')
        else:
            lines.append(f"var {name} = {value}")

    lines.append("")
    for name, value in metric.items():
        lines.append(f"var {name} = {value}")

    lines.append("")
    lines.append("// derived: the two translucent strokes the shell uses everywhere")
    lines.append('var edge = "rgba(224, 169, 59, " + edgeAlpha + ")"')
    lines.append('var hairline = "rgba(154, 164, 178, " + hairlineAlpha + ")"')
    lines.append('var selection = "rgba(224, 169, 59, " + selectionTint + ")"')
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    tokens = json.loads(TOKENS.read_text())
    rendered = render(tokens)

    if "--check" in sys.argv:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != rendered:
            print(f"{OUTPUT.relative_to(ROOT)} is stale — run scripts/gen_theme.py")
            return 1
        print("Theme.js is up to date")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered)
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
