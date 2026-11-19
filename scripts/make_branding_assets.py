#!/usr/bin/env python3
"""Generate the artwork the boot splash and the login theme load at runtime.

Everything stays inside branding/ so the ISO build does not depend on scripts/.
"""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
BRAND = os.path.join(ROOT, "branding")

W, H = 1920, 1080
TOP = (250, 246, 238)
BOTTOM = (233, 222, 204)


def gradient():
    strip = Image.new("RGB", (1, H))
    px = strip.load()
    for y in range(H):
        t = y / (H - 1)
        px[0, y] = tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM))
    return strip.resize((W, H), Image.BILINEAR).convert("RGBA")


def glow(img, center, radius, color, strength):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    for i in range(24, 0, -1):
        r = radius * i / 24
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=color + (int(strength * (1 - i / 24) ** 1.5),))
    return Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(radius // 7)))


def background():
    img = gradient()
    img = glow(img, (W // 2, 400), 640, (255, 252, 240), 110)
    img = glow(img, (W // 2, 820), 900, (232, 208, 170), 55)
    return img.convert("RGB")


def dot():
    """12 px soft ink dot for the splash animation."""
    d = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    ImageDraw.Draw(d).ellipse([2, 2, 11, 11], fill=(26, 26, 30, 235))
    return d.filter(ImageFilter.GaussianBlur(0.6))


def main():
    bg = background()
    for target in ("plymouth/parametral", "sddm/parametral"):
        d = os.path.join(BRAND, target)
        os.makedirs(d, exist_ok=True)
        bg.save(os.path.join(d, "background.png"), optimize=True)

        mark = Image.open(os.path.join(ASSETS, "parametral-mark-1024.png")).convert("RGBA")
        mark.thumbnail((256, 256), Image.LANCZOS)
        mark.save(os.path.join(d, "logo.png"))

        big = Image.open(os.path.join(ASSETS, "parametral-mark-1024.png")).convert("RGBA")
        big.thumbnail((420, 420), Image.LANCZOS)
        big.save(os.path.join(d, "logo-large.png"))
        if target.startswith("plymouth"):
            dot().save(os.path.join(d, "dot.png"))
        print("wrote", d)


if __name__ == "__main__":
    main()
