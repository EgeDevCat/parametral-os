#!/usr/bin/env python3
"""Render previews of the Parametral boot splash and login screen.

The real boot uses Plymouth and the real login uses SDDM; these PNGs are the design
reference both are built from (same colours, same spacing, same logo placement).
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

W, H = 1920, 1080
CREAM_TOP = (250, 246, 238)
CREAM_BOTTOM = (236, 226, 210)
INK = (26, 26, 30)
INK_SOFT = (92, 88, 82)
AMBER = (224, 169, 59)

F_LIGHT = "/usr/share/fonts/TTF/DejaVuSans-ExtraLight.ttf"
F_REG = "/usr/share/fonts/TTF/DejaVuSans.ttf"


def font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", (1, h))
    px = img.load()
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
    return img.resize((w, h), Image.BILINEAR)


def soft_glow(size, center, radius, color, strength=90):
    """A blurred radial blob, composited as a light halo."""
    w, h = size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    steps = 26
    for i in range(steps, 0, -1):
        r = radius * i / steps
        a = int(strength * (1 - i / steps) ** 1.6)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color + (a,))
    return layer.filter(ImageFilter.GaussianBlur(radius // 6))


def logo(size):
    path = os.path.join(ASSETS, "parametral-mark-1024.png")
    img = Image.open(path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    return img


def compose_base():
    bg = gradient((W, H), CREAM_TOP, CREAM_BOTTOM).convert("RGBA")
    bg = Image.alpha_composite(bg, soft_glow((W, H), (W // 2, 380), 620, (255, 250, 235), 120))
    bg = Image.alpha_composite(bg, soft_glow((W, H), (W // 2, 760), 900, (236, 214, 176), 60))
    return bg


def drop_shadow(mask_img, offset=(0, 18), blur=28, alpha=70):
    pad = blur * 3
    w, h = mask_img.size
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.paste((30, 25, 20, alpha), (pad + offset[0], pad + offset[1]), mask_img)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.paste(mask_img, (pad, pad), mask_img)
    return canvas


def draw_centered(draw, xy, text, fnt, fill):
    x, y = xy
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text((x - (box[2] - box[0]) / 2 - box[0], y), text, font=fnt, fill=fill)


def render_boot(out):
    img = compose_base()
    mark = logo(300)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glow.paste(mark, (W // 2 - mark.width // 2, 300), mark)
    glow = glow.filter(ImageFilter.GaussianBlur(26))
    img = Image.alpha_composite(img, glow)
    img.paste(mark, (W // 2 - mark.width // 2, 300), mark)

    d = ImageDraw.Draw(img)
    draw_centered(d, (W // 2, 640), "Parametral", font(F_LIGHT, 96), INK)
    draw_centered(d, (W // 2, 760), "S İ S T E M   B A Ş L A T I L I Y O R", font(F_REG, 22), INK_SOFT)

    # three soft breathing dots
    cy = 900
    for i, x in enumerate((-44, 0, 44)):
        r = 7 if i != 1 else 9
        alpha = 210 if i == 1 else 120
        d.ellipse([W // 2 + x - r, cy - r, W // 2 + x + r, cy + r], fill=INK + (alpha,))

    img.convert("RGB").save(out, quality=95)
    return out


def render_login(out):
    img = compose_base()

    mark = logo(170)
    img.paste(mark, (W // 2 - mark.width // 2, 150), mark)
    d = ImageDraw.Draw(img)
    draw_centered(d, (W // 2, 340), "Parametral", font(F_LIGHT, 68), INK)

    card_w, card_h = 780, 480
    cx, cy = W // 2 - card_w // 2, 470

    # shadow layer: the same rounded rect, blurred, sitting slightly lower
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [cx, cy + 20, cx + card_w, cy + card_h + 22], radius=34, fill=(58, 48, 34, 26))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(52)))

    card = Image.new("RGBA", (card_w, card_h), (255, 254, 251, 252))
    # the card sits on a near-white background: a very light border keeps the rounded
    # shape readable without looking hard
    ImageDraw.Draw(card).rounded_rectangle([0, 0, card_w - 1, card_h - 1], radius=34,
                                          fill=(255, 254, 251, 252),
                                          outline=(214, 203, 185, 90), width=2)
    img.alpha_composite(card, (cx, cy))

    d = ImageDraw.Draw(img)
    draw_centered(d, (W // 2, cy + 46), "Hoş geldiniz", font(F_LIGHT, 36), INK)

    field_w, field_h = 580, 64
    fx = W // 2 - field_w // 2
    fy1 = cy + 126
    for i, label in enumerate(("operator", "••••••••••")):
        fy = fy1 + i * 88
        d.rounded_rectangle([fx, fy, fx + field_w, fy + field_h], radius=16,
                            fill=(255, 255, 255, 225), outline=(222, 212, 196, 220), width=2)
        d.text((fx + 24, fy + 19), label, font=font(F_REG, 23), fill=INK if i == 0 else INK_SOFT)

    by = fy1 + 2 * 88 + 8
    d.rounded_rectangle([fx, by, fx + field_w, by + 64], radius=16, fill=AMBER + (255,))
    draw_centered(d, (W // 2, by + 17), "Giriş yap", font(F_REG, 23), (38, 30, 16))

    draw_centered(d, (W // 2, H - 84), "Parametral OS  ·  sürüm 0.3", font(F_LIGHT, 22), INK_SOFT)

    img.convert("RGB").save(out, quality=95)
    return out


if __name__ == "__main__":
    boot = render_boot(os.path.join(ASSETS, "preview-boot.png"))
    login = render_login(os.path.join(ASSETS, "preview-login.png"))
    print(boot)
    print(login)
