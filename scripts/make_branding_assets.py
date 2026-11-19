#!/usr/bin/env python3
"""Generate the artwork the boot splash and the login theme load at runtime.

Everything stays inside branding/ so the ISO build does not depend on scripts/.

Two backgrounds on purpose:
  * plymouth  — clean cream gradient (the mark sits centred in the splash, a watermark
                behind it would just compete with it)
  * sddm      — the same cream, plus a large, very faint ink watermark of the mark so the
                login screen has depth instead of a flat colour field
"""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
BRAND = os.path.join(ROOT, "branding")

W, H = 1920, 1080
TOP = (251, 247, 240)
BOTTOM = (231, 219, 200)
MARK = os.path.join(ASSETS, "parametral-mark-1024.png")


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


def vignette(img, amount=34):
    """Very light darkening at the edges — keeps the cream from looking flat."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse([-W * 0.30, -H * 0.40, W * 1.30, H * 1.40], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(240))
    dark = Image.new("RGBA", img.size, (62, 52, 40, 255))
    dark.putalpha(mask.point(lambda v: int((255 - v) * amount / 255)))
    return Image.alpha_composite(img, dark)


def ink_watermark(size_px=1050, alpha=0.07, blur=9):
    """The mark recoloured to soft ink, used as a background watermark."""
    mark = Image.open(MARK).convert("RGBA")
    mark.thumbnail((size_px, size_px), Image.LANCZOS)
    a = mark.split()[3].point(lambda v: int(v * alpha))
    ink = Image.new("RGBA", mark.size, (74, 63, 48, 255))
    ink.putalpha(a)
    return ink.filter(ImageFilter.GaussianBlur(blur))


def logo_glow(size_px=620, strength=200):
    """A soft white radial halo that lifts the mark off the watermark."""
    g = Image.new("RGBA", (size_px, size_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    c = size_px // 2
    steps = 40
    for i in range(steps, 0, -1):
        r = c * i / steps
        a = int(strength * (1 - i / steps) ** 2.2)
        d.ellipse([c - r, c - r, c + r, c + r], fill=(255, 253, 247, a))
    return g.filter(ImageFilter.GaussianBlur(size_px // 14))


def background(watermark=False):
    img = gradient()
    img = glow(img, (W // 2, 380), 660, (255, 252, 242), 115)
    img = glow(img, (W // 2, 840), 920, (233, 208, 168), 52)
    if watermark:
        # primary ghost: upper right, so only its lower-left arc grazes the card
        wm = ink_watermark(1050, alpha=0.062, blur=10)
        img.alpha_composite(wm, (int(W * 0.80) - wm.width // 2,
                                 int(H * 0.17) - wm.height // 2))
        # a much fainter echo bottom-left keeps the frame from feeling lopsided
        echo = ink_watermark(760, alpha=0.035, blur=14)
        img.alpha_composite(echo, (int(W * 0.14) - echo.width // 2,
                                   int(H * 0.88) - echo.height // 2))
    img = vignette(img)
    return img.convert("RGB")


def dot():
    """12 px soft ink dot for the splash animation."""
    d = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
    ImageDraw.Draw(d).ellipse([2, 2, 11, 11], fill=(26, 26, 30, 235))
    return d.filter(ImageFilter.GaussianBlur(0.6))


def main():
    for target, wm in (("plymouth/parametral", False), ("sddm/parametral", True)):
        d = os.path.join(BRAND, target)
        os.makedirs(d, exist_ok=True)
        background(watermark=wm).save(os.path.join(d, "background.png"), optimize=True)

        mark = Image.open(MARK).convert("RGBA")
        mark.thumbnail((256, 256), Image.LANCZOS)
        mark.save(os.path.join(d, "logo.png"))

        big = Image.open(MARK).convert("RGBA")
        big.thumbnail((420, 420), Image.LANCZOS)
        big.save(os.path.join(d, "logo-large.png"))
        if target.startswith("plymouth"):
            dot().save(os.path.join(d, "dot.png"))
        else:
            logo_glow().save(os.path.join(d, "logo-glow.png"))
        print("wrote", d)


if __name__ == "__main__":
    main()
