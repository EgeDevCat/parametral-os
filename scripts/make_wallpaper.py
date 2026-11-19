#!/usr/bin/env python3
"""Generate the Parametral desktop wallpapers (light + dark, 2560x1440).

Same language as the login screen: soft gradient, the gauge as a large ghost, a warm
glow, and a small wordmark in a corner. Nothing hard-edged.
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
OUT = os.path.join(ROOT, "branding", "wallpapers")
MARK = os.path.join(ASSETS, "parametral-mark-1024.png")
F_LIGHT = "/usr/share/fonts/TTF/DejaVuSans-ExtraLight.ttf"

W, H = 2560, 1440

PALETTES = {
    "dark": dict(top=(24, 27, 33), bottom=(8, 9, 11), ghost=(255, 246, 232), ghost_a=0.12,
                 glow=((255, 176, 102), 46), glow2=((90, 140, 220), 26),
                 ink=(240, 235, 226), sub=(150, 143, 131), vig=70),
    "light": dict(top=(252, 249, 243), bottom=(230, 218, 199), ghost=(74, 63, 48), ghost_a=0.06,
                  glow=((255, 250, 235), 110), glow2=((233, 208, 168), 55),
                  ink=(26, 26, 30), sub=(120, 114, 104), vig=30),
}


def font(size):
    try:
        return ImageFont.truetype(F_LIGHT, size)
    except OSError:
        return ImageFont.load_default()


def gradient(p):
    strip = Image.new("RGB", (1, H))
    px = strip.load()
    for y in range(H):
        t = y / (H - 1)
        px[0, y] = tuple(round(a + (b - a) * t) for a, b in zip(p["top"], p["bottom"]))
    return strip.resize((W, H), Image.BILINEAR).convert("RGBA")


def glow(img, center, radius, color, strength):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    for i in range(28, 0, -1):
        r = radius * i / 28
        d.ellipse([cx - r, cy - r, cx + r, cy + r],
                  fill=color + (int(strength * (1 - i / 28) ** 1.6),))
    return Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(radius // 6)))


def ghost(color, alpha, size, blur):
    m = Image.open(MARK).convert("RGBA")
    m.thumbnail((size, size), Image.LANCZOS)
    a = m.split()[3].point(lambda v: int(v * alpha))
    flat = Image.new("RGBA", m.size, color + (255,))
    flat.putalpha(a)
    return flat.filter(ImageFilter.GaussianBlur(blur))


def vignette(img, amount):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse([-W * 0.25, -H * 0.35, W * 1.25, H * 1.35], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(320))
    dark = Image.new("RGBA", img.size, (0, 0, 0, 255))
    dark.putalpha(mask.point(lambda v: int((255 - v) * amount / 255)))
    return Image.alpha_composite(img, dark)


def build(mode):
    p = PALETTES[mode]
    img = gradient(p)
    img = glow(img, (int(W * 0.22), int(H * 0.86)), 900, *p["glow"])
    img = glow(img, (int(W * 0.86), int(H * 0.18)), 780, *p["glow2"])

    # the mark, large and off-centre right, cut by the frame
    g = ghost(p["ghost"], p["ghost_a"], 1500, 10)
    img.alpha_composite(g, (int(W * 0.86) - g.width // 2, int(H * 0.40) - g.height // 2))
    g2 = ghost(p["ghost"], p["ghost_a"] * 0.55, 700, 20)
    img.alpha_composite(g2, (int(W * 0.10) - g2.width // 2, int(H * 0.12) - g2.height // 2))

    img = vignette(img, p["vig"])

    d = ImageDraw.Draw(img)
    d.text((96, H - 150), "Parametral", font=font(54), fill=p["ink"] + (235,))
    d.text((96, H - 88), "OS", font=font(26), fill=p["sub"] + (200,))
    return img.convert("RGB")


def main():
    os.makedirs(OUT, exist_ok=True)
    for mode in ("dark", "light"):
        path = os.path.join(OUT, f"parametral-{mode}.png")
        build(mode).save(path, optimize=True)
        print(path)


if __name__ == "__main__":
    main()
