"""The KDE schemes must be the same measured palette, not a second hand-written one.

KDE is the primary desktop line (2026-11-20). These tests parse the generated `.colors` files,
check AA contrast on the pairs KDE actually draws, and fail if the generator drifts.
"""

from __future__ import annotations

import configparser
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "gen_kde_theme.py"
TOKENS_PATH = ROOT / "branding" / "tokens.json"
DARK = ROOT / "branding" / "kde" / "Parametral.colors"
LIGHT = ROOT / "branding" / "kde" / "ParametralLight.colors"
SNIPPET = ROOT / "branding" / "kde" / "kdeglobals-snippet.ini"
KONSOLE = ROOT / "branding" / "kde" / "konsole" / "Parametral.colorscheme"
SDDM = ROOT / "branding" / "sddm" / "parametral" / "Main.qml"


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_kde_theme", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["gen_kde_theme"] = module
    spec.loader.exec_module(module)
    return module


def channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    x, y = luminance(a), luminance(b)
    high, low = max(x, y), min(x, y)
    return (high + 0.05) / (low + 0.05)


def hex_rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def csv_rgb(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in value.split(","))  # type: ignore[return-value]


def parse(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(path.read_text())
    return parser


class Generated(unittest.TestCase):
    def setUp(self):
        self.gen = load_generator()
        self.tokens = json.loads(TOKENS_PATH.read_text())

    def test_dark_matches_tokens(self):
        self.assertEqual(DARK.read_text(), self.gen.render(self.tokens, "dark"))

    def test_light_matches_tokens(self):
        self.assertEqual(LIGHT.read_text(), self.gen.render(self.tokens, "light"))

    def test_snippet_matches_tokens(self):
        self.assertEqual(SNIPPET.read_text(), self.gen.render_snippet(self.tokens))

    def test_kde_format_has_no_hex(self):
        for path in (DARK, LIGHT):
            self.assertNotIn("#", path.read_text(), f"{path.name}: KDE wants R,G,B, not hex")

    def test_first_login_fonts(self):
        text = SNIPPET.read_text()
        self.assertIn("font=Inter", text)
        self.assertIn("fixed=IBM Plex Mono", text)
        self.assertNotIn("Noto Sans", text)


class Contrast(unittest.TestCase):
    def setUp(self):
        self.dark = parse(DARK)
        self.light = parse(LIGHT)

    def assert_pair(self, parser, section, fg, bg, minimum, label):
        ratio = contrast(csv_rgb(parser[section][fg]), csv_rgb(parser[section][bg]))
        self.assertGreaterEqual(
            ratio, minimum, f"{label}: {section}.{fg} on {bg} = {ratio:.2f}:1"
        )

    def test_dark_pairs(self):
        for section in ("Colors:Window", "Colors:View", "Colors:Button", "Colors:Tooltip"):
            self.assert_pair(self.dark, section, "ForegroundNormal", "BackgroundNormal", 7.0, "dark")
            self.assert_pair(self.dark, section, "ForegroundInactive", "BackgroundNormal", 4.5, "dark")
            self.assert_pair(self.dark, section, "ForegroundActive", "BackgroundNormal", 4.5, "dark")
        self.assert_pair(self.dark, "Colors:Selection", "ForegroundNormal", "BackgroundNormal", 4.5, "dark")
        self.assert_pair(self.dark, "WM", "activeForeground", "activeBackground", 7.0, "dark")

    def test_light_pairs(self):
        for section in ("Colors:Window", "Colors:View", "Colors:Button", "Colors:Tooltip"):
            self.assert_pair(self.light, section, "ForegroundNormal", "BackgroundNormal", 7.0, "light")
            self.assert_pair(self.light, section, "ForegroundInactive", "BackgroundNormal", 4.5, "light")
            self.assert_pair(self.light, section, "ForegroundActive", "BackgroundNormal", 4.5, "light")
        self.assert_pair(self.light, "Colors:Selection", "ForegroundNormal", "BackgroundNormal", 4.5, "light")
        self.assert_pair(self.light, "WM", "activeForeground", "activeBackground", 7.0, "light")

    def test_light_selection_uses_fill_and_ink(self):
        tokens = json.loads(TOKENS_PATH.read_text())["light"]
        selection = self.light["Colors:Selection"]
        self.assertEqual(csv_rgb(selection["BackgroundNormal"]), hex_rgb(tokens["primary"]))
        self.assertEqual(csv_rgb(selection["ForegroundNormal"]), hex_rgb(tokens["onPrimary"]))

    def test_no_blue_link(self):
        for parser, label in ((self.dark, "dark"), (self.light, "light")):
            for section in ("Colors:Window", "Colors:View", "Colors:Button"):
                r, g, b = csv_rgb(parser[section]["ForegroundLink"])
                self.assertFalse(b > r + 24 and b > g + 8, f"{label} {section} link is blue")


class LookAndFeel(unittest.TestCase):
    LAYOUT = ROOT / "branding" / "kde" / "look-and-feel" / "org.parametral.desktop" / "contents" / "layouts" / "org.kde.plasma.desktop-layout.js"
    DEFAULTS = ROOT / "branding" / "kde" / "look-and-feel" / "org.parametral.desktop" / "contents" / "defaults"
    SPLASH = ROOT / "branding" / "kde" / "look-and-feel" / "org.parametral.desktop" / "contents" / "splash" / "Splash.qml"
    PANEL = ROOT / "branding" / "plasma-theme" / "Parametral" / "widgets" / "panel-background.svg"
    RULER = ROOT / "branding" / "kde" / "plasmoids" / "org.parametral.ruler"
    RULER_QML = RULER / "contents" / "ui" / "main.qml"
    RULER_META = RULER / "metadata.json"

    def test_panel_is_one_40px_top_plate(self):
        text = self.LAYOUT.read_text()
        self.assertIn('panel.location = "top"', text)
        self.assertIn("panel.height = 40", text)
        self.assertIn('panel.hiding = "none"', text)
        self.assertNotIn('panel.location = "bottom"', text)
        self.assertNotIn('panel.hiding = "autohide"', text)

    def test_parametral_plasma_theme_is_selected(self):
        text = self.DEFAULTS.read_text()
        self.assertIn("name=Parametral", text)
        self.assertNotIn("name=breeze-dark", text)
        self.assertIn("ColorScheme=Parametral", text)

    def test_splash_uses_tokens_and_inter(self):
        tokens = json.loads(TOKENS_PATH.read_text())
        allowed = {
            value.upper()
            for section in ("colour", "light")
            for value in tokens[section].values()
            if isinstance(value, str) and value.startswith("#")
        }
        text = self.SPLASH.read_text()
        for match in re.findall(r"#[0-9A-Fa-f]{6}", text):
            self.assertIn(match.upper(), allowed, f"splash colour {match} is not a token")
        self.assertIn('font.family: "Inter"', text)

    def test_ruler_applet_is_the_signature(self):
        qml = self.RULER_QML.read_text()
        self.assertIn("activeWidth: 14", qml)
        self.assertIn("idleWidth: 6", qml)
        self.assertIn("tickHeight: 2", qml)
        self.assertIn("PlasmaCore.Theme.highlightColor", qml)
        self.assertIn("PlasmaCore.Theme.disabledTextColor", qml)
        self.assertIn("PagerModel.VirtualDesktops", qml)
        self.assertIn("pagerModel.changePage(index)", qml)
        self.assertNotIn("#", qml, "the applet takes colours from the KDE scheme, not hex")
        metadata = json.loads(self.RULER_META.read_text())
        self.assertEqual(metadata["KPlugin"]["Id"], "org.parametral.ruler")
        self.assertEqual(metadata["KPackageStructure"], "Plasma/Applet")
        self.assertIn('panel.addWidget("org.parametral.ruler")', self.LAYOUT.read_text())

    def test_panel_svg_has_a_ruler(self):
        text = self.PANEL.read_text()
        self.assertIn('<g id="bar">', text)
        self.assertIn('height="2"', text)
        self.assertIn('fill-opacity="0.14"', text)

    def test_panel_svg_is_token_coloured_and_12px(self):
        tokens = json.loads(TOKENS_PATH.read_text())["colour"]
        text = self.PANEL.read_text()
        self.assertIn(tokens["surface"].upper(), text.upper())
        self.assertIn(tokens["amber"].upper(), text.upper())
        self.assertIn("A12,12", text)
        self.assertNotIn("A14,14", text)


class Konsole(unittest.TestCase):
    def test_ansi_roles_match_tokens(self):
        tokens = json.loads(TOKENS_PATH.read_text())["colour"]
        parser = parse(KONSOLE)
        self.assertEqual(csv_rgb(parser["Background"]["Color"]), hex_rgb(tokens["bg"]))
        self.assertEqual(csv_rgb(parser["Foreground"]["Color"]), hex_rgb(tokens["text"]))
        self.assertEqual(csv_rgb(parser["Color1"]["Color"]), hex_rgb(tokens["danger"]))
        self.assertEqual(csv_rgb(parser["Color2"]["Color"]), hex_rgb(tokens["ok"]))
        self.assertEqual(csv_rgb(parser["Color3"]["Color"]), hex_rgb(tokens["amber"]))


class Sddm(unittest.TestCase):
    def test_colours_are_token_values(self):
        tokens = json.loads(TOKENS_PATH.read_text())
        allowed = {
            value.upper()
            for section in ("colour", "light")
            for value in tokens[section].values()
            if isinstance(value, str) and value.startswith("#")
        }
        for line in SDDM.read_text().splitlines():
            if "property color" not in line:
                continue
            for match in re.findall(r"#[0-9A-Fa-f]{6}", line):
                self.assertIn(match.upper(), allowed, f"SDDM colour {match} is not a token")

    def test_inter_is_used(self):
        text = SDDM.read_text()
        self.assertIn('font.family: "Inter"', text)
        self.assertNotIn("DejaVu Sans", text)


if __name__ == "__main__":
    unittest.main()
