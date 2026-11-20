"""check_visual.py must measure what the design spec says, on synthetic pixels.

The audit tool is part of the gate: if it cannot tell a 40 px plate from a 30 px one, or a
14 px amber tick from a 6 px one, the review is decoration. These tests build small PNGs with
zlib and assert the measurements directly.
"""

from __future__ import annotations

import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_visual as cv  # noqa: E402


def write_png(path: Path, width: int, height: int, rgb: bytearray) -> None:
    raw = b"".join(b"\x00" + bytes(rgb[y * width * 3 : (y + 1) * width * 3]) for y in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(
            ">I", zlib.crc32(kind + body) & 0xFFFFFFFF
        )

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


class Canvas:
    def __init__(self, width: int, height: int, colour: str = "#0B0F14"):
        self.width, self.height = width, height
        self.rgb = bytearray(cv.hex_rgb(colour) * (width * height))

    def rect(self, x0: int, y0: int, x1: int, y1: int, colour: str) -> None:
        c = cv.hex_rgb(colour)
        for y in range(y0, y1):
            for x in range(x0, x1):
                offset = (y * self.width + x) * 3
                self.rgb[offset : offset + 3] = bytes(c)

    def save(self, path: Path) -> None:
        write_png(path, self.width, self.height, self.rgb)


def good_bar() -> Canvas:
    c = Canvas(1280, 800)
    c.rect(8, 6, 1272, 46, "#12171E")          # 40 px plate, 8 px side inset, 6 px top gap
    c.rect(20, 44, 1260, 46, "#2A323C")        # 2 px ruler
    x = 30
    for width, colour in ((6, "#7C8592"), (6, "#7C8592"), (14, "#E0A93B"), (6, "#7C8592")):
        c.rect(x, 40, x + width, 42, colour)
        x += width + 8
    return c


class Measure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "shot.png"

    def tearDown(self):
        self.tmp.cleanup()

    def measure(self, canvas: Canvas) -> dict:
        canvas.save(self.path)
        return cv.measure(self.path, "bar")

    def test_good_bar_passes(self):
        result = self.measure(good_bar())
        self.assertEqual(result["failures"], [], result)
        self.assertEqual(result["bar"]["height"], 40)
        self.assertEqual(result["bar"]["top"], 6)
        self.assertEqual(result["bar"]["left"], 8)
        self.assertEqual(result["bar"]["right"], 1271)
        self.assertEqual(result["kenar_boslugu"]["left"], 8)
        self.assertEqual(result["kenar_boslugu"]["right"], 8)
        self.assertEqual(max(w for row in result["amber_runs"] for w in row["widths"]), 14)
        self.assertLess(result["amber_piksel_orani"], 1.2)
        self.assertEqual(result["palet_disi_orani"], 0)
        self.assertEqual(result["siyah_orani"], 0)

    def test_short_plate_fails(self):
        canvas = Canvas(1280, 800)
        canvas.rect(8, 6, 1272, 36, "#12171E")   # 30 px, the T6 regression
        result = self.measure(canvas)
        self.assertIn("bar-height", result["failures"])
        self.assertEqual(result["bar"]["height"], 30)

    def test_plate_flush_to_edge_fails(self):
        canvas = Canvas(1280, 800)
        canvas.rect(0, 6, 1280, 46, "#12171E")
        result = self.measure(canvas)
        self.assertIn("edge", result["failures"])
        self.assertEqual(result["bar"]["left"], 0)

    def test_foreign_blue_fails_palette(self):
        canvas = good_bar()
        canvas.rect(100, 10, 300, 30, "#0000FF")
        result = self.measure(canvas)
        self.assertIn("palette", result["failures"])
        self.assertGreater(result["palet_disi_orani"], 5.0)

    def test_small_amber_tick_fails(self):
        canvas = Canvas(1280, 800)
        canvas.rect(8, 6, 1272, 46, "#12171E")
        canvas.rect(30, 40, 36, 42, "#E0A93B")   # 6 px active tick
        result = self.measure(canvas)
        self.assertIn("amber-tick", result["failures"])

    def test_pure_black_block_fails(self):
        canvas = good_bar()
        canvas.rect(0, 500, 1280, 800, "#000000")
        result = self.measure(canvas)
        self.assertIn("black", result["failures"])
        self.assertGreater(result["siyah_orani"], 35.0)

    def test_light_mode_finds_the_light_plate(self):
        canvas = Canvas(1280, 800, "#EFE7D9")
        canvas.rect(8, 6, 1272, 46, "#F4EFE6")
        canvas.rect(30, 40, 44, 42, "#B8862B")
        canvas.save(self.path)
        result = cv.measure(self.path, "bar", "light")
        self.assertEqual(result["mode"], "light")
        self.assertEqual(result["bar"]["height"], 40)
        self.assertEqual(result["bar"]["top"], 6)
        self.assertNotIn("bar-height", result["failures"])

    def test_png_roundtrip(self):
        canvas = good_bar()
        canvas.save(self.path)
        width, height, px = cv.decode_png(self.path)
        self.assertEqual((width, height), (1280, 800))
        self.assertEqual(cv.pixel(px, width, 100, 20), cv.hex_rgb("#12171E"))


if __name__ == "__main__":
    unittest.main()
