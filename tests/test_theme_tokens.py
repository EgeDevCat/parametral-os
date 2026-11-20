"""The design system must be one measured source of truth.

`branding/tokens.json` is the source; `shell/Theme.js` is generated from it; the Noctalia palette
is a projection of it. These tests fail when any of the three drifts, when a contrast pair drops
below WCAG AA, or when a scale value outside the art direction sneaks in.

Art direction: Ölçüm Plakası — docs/DESIGN.md.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "gen_theme.py"
TOKENS_PATH = ROOT / "branding" / "tokens.json"
THEME_PATH = ROOT / "shell" / "Theme.js"
PALETTE_PATH = ROOT / "branding" / "noctalia" / "palettes" / "Parametral.json"

SPACING_SCALE = {4, 8, 12, 16, 24, 32, 48}
RADIUS_SCALE = {1, 8, 12, 999}
TYPE_SCALE = {11, 13, 17, 26}
LINE_SCALE = {16, 20, 24, 32}


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_theme", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["gen_theme"] = module
    spec.loader.exec_module(module)
    return module


def channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(foreground: str, background: str) -> float:
    a, b = luminance(foreground), luminance(background)
    high, low = max(a, b), min(a, b)
    return (high + 0.05) / (low + 0.05)


class ThemeTokens(unittest.TestCase):
    def setUp(self):
        self.gen = load_generator()
        self.tokens = json.loads(TOKENS_PATH.read_text())
        self.theme = THEME_PATH.read_text()

    def test_generated_file_matches_tokens(self):
        expected = self.gen.render(self.tokens)
        self.assertEqual(self.theme, expected, "shell/Theme.js is stale — run scripts/gen_theme.py")

    def test_every_colour_is_present(self):
        for name, value in self.tokens["colour"].items():
            if isinstance(value, str):
                self.assertIn(f'var {name} = "{value}"', self.theme)
        for name, value in self.tokens["light"].items():
            suffix = name[0].upper() + name[1:]
            if isinstance(value, str):
                self.assertIn(f'var light{suffix} = "{value}"', self.theme)

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
                    if "file://" in line or '"#"' in line:
                        continue
                    offenders.append(f"{qml.name}:{number}: {stripped}")
        self.assertEqual(offenders, [], "hex colours belong in branding/tokens.json:\n" + "\n".join(offenders))


class Contrast(unittest.TestCase):
    """Measured WCAG 2.x ratios. A failing pair is a design bug, not a taste question."""

    def setUp(self):
        tokens = json.loads(TOKENS_PATH.read_text())
        self.dark = tokens["colour"]
        self.light = tokens["light"]

    def assert_pair(self, palette, fg, bg, minimum, label):
        ratio = contrast(palette[fg], palette[bg])
        self.assertGreaterEqual(
            ratio, minimum, f"{label}: {fg} on {bg} = {ratio:.2f}:1, needs {minimum}:1"
        )

    def test_dark_pairs(self):
        pairs = [
            ("text", "bg", 7.0),
            ("text", "surface", 7.0),
            ("muted", "surface", 4.5),
            ("faint", "surface", 4.5),
            ("amber", "surface", 4.5),
            ("primaryText", "surface", 4.5),
            ("danger", "surface", 4.5),
            ("ok", "surface", 4.5),
            ("onPrimary", "amber", 4.5),
            ("dangerInk", "danger", 4.5),
            ("okInk", "ok", 4.5),
        ]
        for fg, bg, minimum in pairs:
            self.assert_pair(self.dark, fg, bg, minimum, "dark")

    def test_light_pairs(self):
        pairs = [
            ("text", "surface", 7.0),
            ("text", "card", 7.0),
            ("muted", "surface", 4.5),
            ("faint", "surface", 4.5),
            ("primaryText", "surface", 4.5),
            ("primaryTextStrong", "card", 4.5),
            ("danger", "surface", 4.5),
            ("onPrimary", "primary", 4.5),
            ("dangerInk", "danger", 4.5),
            ("okInk", "ok", 4.5),
        ]
        for fg, bg, minimum in pairs:
            self.assert_pair(self.light, fg, bg, minimum, "light")

    def test_light_has_two_ambers(self):
        """primary is a fill; primaryText/Strong are the amber text roles."""
        fill = contrast(self.light["primary"], self.light["surface"])
        text = contrast(self.light["primaryText"], self.light["surface"])
        self.assertLess(fill, 4.5, f"light primary ({fill:.2f}:1) must not be usable as text")
        self.assertGreaterEqual(text, 4.5, f"light primaryText ({text:.2f}:1) must pass AA")

    def test_light_ok_is_not_text(self):
        """ok is a dot/icon role in light mode; as 11 px text it would fail AA (4.38:1)."""
        ratio = contrast(self.light["ok"], self.light["surface"])
        self.assertGreaterEqual(ratio, 3.0, "ok must at least pass non-text contrast")
        self.assertLess(ratio, 4.5, "ok is non-text only in light mode — use on_surface for words")


class Scales(unittest.TestCase):
    def setUp(self):
        self.tokens = json.loads(TOKENS_PATH.read_text())
        self.metric = self.tokens["metric"]

    def test_radius_scale(self):
        radii = {k: v for k, v in self.metric.items() if k.startswith("radius")}
        self.assertEqual(set(radii), {"radiusTick", "radiusRow", "radiusPanel", "radiusPill"})
        self.assertEqual(set(radii.values()), RADIUS_SCALE)

    def test_general_spacing_is_on_the_scale(self):
        for key in ("gap", "pad", "panelPad", "launcherGap"):
            self.assertIn(self.metric[key], SPACING_SCALE, f"{key} is off the 4 px scale")

    def test_bar_geometry_is_fixed(self):
        self.assertEqual(self.metric["barHeight"], 40, "the bar never grows")
        self.assertEqual(self.metric["barTopGap"], 6)
        self.assertEqual(self.metric["barSideGap"], 8)
        self.assertEqual(self.metric["barSideGapWide"], 12)
        self.assertEqual(self.metric["barPad"], 10)
        self.assertEqual(self.metric["clusterGap"], 6)
        self.assertEqual(self.metric["icon"], 16)
        heights = [k for k in self.metric if k.lower().startswith("barheight")]
        self.assertEqual(heights, ["barHeight"], "one bar height; it does not scale with resolution")

    def test_panel_and_launcher_geometry(self):
        self.assertEqual(self.metric["panelWidth"], 420)
        self.assertEqual(self.metric["panelWidthWide"], 480)
        self.assertEqual(self.metric["panelPad"], 16)
        self.assertEqual(self.metric["panelRow"], 40)
        self.assertEqual(self.metric["panelHeader"], 32)
        self.assertEqual(self.metric["launcherWidth"], 520)
        self.assertEqual(self.metric["launcherInput"], 48)
        self.assertEqual(self.metric["launcherRow"], 36)
        self.assertEqual(self.metric["launcherMaxHeight"], 480)
        self.assertEqual(self.metric["launcherGap"], 8)

    def test_one_shadow_and_measured_motion(self):
        self.assertEqual(self.metric["shadowY"], 8)
        self.assertEqual(self.metric["shadowBlur"], 24)
        self.assertEqual(self.metric["shadowAlpha"], 0.08)
        self.assertEqual(self.metric["motionHover"], 120)
        self.assertEqual(self.metric["motionPanel"], 180)
        self.assertEqual(self.metric["motionEase"], [0.2, 0, 0, 1])

    def test_type_scale(self):
        sizes = {self.metric["fontDisplay"], self.metric["fontTitle"],
                 self.metric["fontBody"], self.metric["fontMeta"]}
        self.assertEqual(sizes, TYPE_SCALE)
        lines = {self.metric["lineDisplay"], self.metric["lineTitle"],
                 self.metric["lineBody"], self.metric["lineMeta"]}
        self.assertEqual(lines, LINE_SCALE)

    def test_font_families(self):
        self.assertEqual(self.tokens["type"]["familyBody"], "Inter")
        self.assertEqual(self.tokens["type"]["familyMono"], "IBM Plex Mono")
        self.assertEqual(self.tokens["meta"]["fontBody"], "Inter")
        self.assertEqual(self.tokens["meta"]["fontMono"], "IBM Plex Mono")


class Turkish(unittest.TestCase):
    def setUp(self):
        self.tokens = json.loads(TOKENS_PATH.read_text())

    def test_one_date_format(self):
        meta = self.tokens["meta"]
        self.assertEqual(meta["locale"], "tr_TR")
        self.assertEqual(meta["dateFormat"], "d MMMM yyyy EEEE")

    def test_no_uppercase_transforms(self):
        """Turkish 'i' becomes 'İ'; locale-free uppercasing produces 'I'. Use the written form."""
        needles = ("toUpperCase", "AllUppercase", "text-transform")
        offenders = []
        paths = list((ROOT / "shell").glob("*.qml")) + [ROOT / "branding" / "noctalia" / "config.toml"]
        for path in paths:
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if any(needle in line for needle in needles):
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "uppercase transforms are forbidden:\n" + "\n".join(offenders))


class NoctaliaPalette(unittest.TestCase):
    """The Noctalia palette is a projection of the same tokens, not a second palette."""

    DARK = {
        "primary": ("colour", "amber"),
        "on_primary": ("colour", "onPrimary"),
        "secondary": ("colour", "muted"),
        "on_secondary": ("colour", "bg"),
        "tertiary": ("colour", "ok"),
        "on_tertiary": ("colour", "okInk"),
        "error": ("colour", "danger"),
        "on_error": ("colour", "dangerInk"),
        "surface": ("colour", "bg"),
        "on_surface": ("colour", "text"),
        "surface_container": ("colour", "card"),
        "on_surface_variant": ("colour", "muted"),
        "outline_variant": ("colour", "line"),
        "hover": ("colour", "cardHover"),
        "on_hover": ("colour", "text"),
    }
    LIGHT = {
        # Noctalia v2 has no text-only primary role; primary carries the on-card amber text.
        "primary": ("light", "primaryTextStrong"),
        "on_primary": ("light", "onPrimary"),
        "secondary": ("light", "muted"),
        "on_secondary": ("light", "surface"),
        "tertiary": ("light", "ok"),
        "on_tertiary": ("light", "okInk"),
        "error": ("light", "danger"),
        "on_error": ("light", "dangerInk"),
        "surface": ("light", "surface"),
        "on_surface": ("light", "text"),
        "surface_container": ("light", "card"),
        "on_surface_variant": ("light", "muted"),
        "outline_variant": ("light", "line"),
        "hover": ("light", "cardHover"),
        "on_hover": ("light", "text"),
    }

    def setUp(self):
        self.tokens = json.loads(TOKENS_PATH.read_text())
        self.palette = json.loads(PALETTE_PATH.read_text())

    def test_roles_match_tokens(self):
        for mode, mapping in (("dark", self.DARK), ("light", self.LIGHT)):
            for role, (section, name) in mapping.items():
                expected = self.tokens[section][name]
                actual = self.palette[mode][role]
                self.assertEqual(
                    actual, expected,
                    f"{mode}.{role} is {actual}, tokens say {section}.{name} = {expected}",
                )

    def test_no_blue_in_ui_roles(self):
        for mode in ("dark", "light"):
            secondary = self.palette[mode]["secondary"].lstrip("#")
            r, g, b = (int(secondary[i : i + 2], 16) for i in (0, 2, 4))
            self.assertFalse(b > r + 24 and b > g + 8, f"{mode} secondary is blue — blue is not a UI role")


if __name__ == "__main__":
    unittest.main()
