#!/usr/bin/env python3
"""Generate the KDE colour schemes from branding/tokens.json.

KDE is the primary desktop line (2026-11-20 decision). Its palette must be the same measured
palette as the shell, not a hand-written second one. This generator emits:

    branding/kde/Parametral.colors        (dark)
    branding/kde/ParametralLight.colors   (light)
    branding/kde/kdeglobals-snippet.ini   (first-login defaults)

    python3 scripts/gen_kde_theme.py
    python3 scripts/gen_kde_theme.py --check
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "branding" / "tokens.json"
KDE = ROOT / "branding" / "kde"


def rgb(value: str) -> str:
    raw = value.lstrip("#")
    return ",".join(str(int(raw[i : i + 2], 16)) for i in (0, 2, 4))


def mix(a: str, b: str, t: float) -> str:
    """Blend two token colours; t=0 is a, t=1 is b. Derived, never hand-written."""
    ra, ga, ba = (int(a.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    rb, gb, bb = (int(b.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
    return "#" + "".join(
        f"{round(x + (y - x) * t):02X}" for x, y in ((ra, rb), (ga, gb), (ba, bb))
    )


def scheme(tokens: dict, mode: str) -> dict[str, dict[str, str]]:
    if mode == "dark":
        c = tokens["colour"]
        bg, surface, card, hover = c["bg"], c["surface"], c["card"], c["cardHover"]
        text, muted, faint, line = c["text"], c["muted"], c["faint"], c["line"]
        accent, on_accent = c["amber"], c["onPrimary"]
        danger, ok, link = c["danger"], c["ok"], c["amber"]
        active_bg = surface
    else:
        c = tokens["light"]
        bg, surface, card, hover = c["bg"], c["surface"], c["card"], c["cardHover"]
        text, muted, faint, line = c["text"], c["muted"], c["faint"], c["line"]
        accent, on_accent = c["primary"], c["onPrimary"]
        danger, ok, link = c["danger"], c["ok"], c["primaryTextStrong"]
        active_bg = card

    body = {
        "fg": text,
        "inactive": muted,
        "active": link,
        "link": link,
        "visited": mix(link, muted, 0.55),
        "negative": danger,
        "neutral": link,
        "positive": ok,
    }

    def block(background: str, alternate: str) -> dict[str, str]:
        return {
            "BackgroundNormal": background,
            "BackgroundAlternate": alternate,
            "ForegroundNormal": body["fg"],
            "ForegroundInactive": body["inactive"],
            "ForegroundActive": body["active"],
            "ForegroundLink": body["link"],
            "ForegroundVisited": body["visited"],
            "ForegroundNegative": body["negative"],
            "ForegroundNeutral": body["neutral"],
            "ForegroundPositive": body["positive"],
        }

    selection = {
        "BackgroundNormal": accent,
        "BackgroundAlternate": mix(accent, bg, 0.18),
        "ForegroundNormal": on_accent,
        "ForegroundInactive": on_accent,
        "ForegroundActive": on_accent,
        "ForegroundLink": on_accent,
        "ForegroundVisited": on_accent,
        "ForegroundNegative": on_accent,
        "ForegroundNeutral": on_accent,
        "ForegroundPositive": on_accent,
    }

    return {
        "Colors:Window": block(bg if mode == "dark" else surface, surface if mode == "dark" else card),
        "Colors:View": block(surface, card),
        "Colors:Button": block(card, hover),
        "Colors:Selection": selection,
        "Colors:Tooltip": block(card, hover),
        "Colors:Complementary": block(bg, surface),
        "Colors:Header": block(surface, bg),
        "WM": {
            "activeBackground": active_bg,
            "activeForeground": text,
            "inactiveBackground": bg,
            "inactiveForeground": muted,
            "activeBlend": accent,
            "inactiveBlend": line,
        },
        "ColorEffects:Disabled": {
            "Color": faint,
            "ColorAmount": "0",
            "ColorEffect": "0",
            "ContrastAmount": "0.65",
            "ContrastEffect": "1",
            "IntensityAmount": "0.1",
            "IntensityEffect": "2",
        },
    }


def render(tokens: dict, mode: str) -> str:
    name = "Parametral" if mode == "dark" else "ParametralLight"
    display = "Parametral" if mode == "dark" else "Parametral Light"
    lines = [
        "[General]",
        f"ColorScheme={name}",
        f"Name={display}",
        "shadeSortColumn=true",
        "",
    ]
    for section, values in scheme(tokens, mode).items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key}={rgb(value) if value.startswith('#') else value}")
        lines.append("")
    return "\n".join(lines)


def render_snippet(tokens: dict) -> str:
    """The dark scheme + fonts, appended to a fresh account's kdeglobals."""
    lines = [
        "[General]",
        "ColorScheme=Parametral",
        "font=Inter,10,-1,5,50,0,0,0,0,0",
        "fixed=IBM Plex Mono,10,-1,5,50,0,0,0,0,0",
        "menuFont=Inter,10,-1,5,50,0,0,0,0,0",
        "toolBarFont=Inter,10,-1,5,50,0,0,0,0,0",
        "smallestReadableFont=Inter,8,-1,5,50,0,0,0,0,0",
        "activeFont=Inter,10,-1,5,75,0,0,0,0,0",
        "",
    ]
    for section, values in scheme(tokens, "dark").items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key}={rgb(value) if value.startswith('#') else value}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    tokens = json.loads(TOKENS.read_text())
    outputs = {
        KDE / "Parametral.colors": render(tokens, "dark"),
        KDE / "ParametralLight.colors": render(tokens, "light"),
        KDE / "kdeglobals-snippet.ini": render_snippet(tokens),
    }
    if "--check" in sys.argv:
        stale = [path for path, text in outputs.items() if not path.exists() or path.read_text() != text]
        if stale:
            for path in stale:
                print(f"{path.relative_to(ROOT)} is stale — run scripts/gen_kde_theme.py")
            return 1
        print("KDE colour schemes are up to date")
        return 0
    for path, text in outputs.items():
        path.write_text(text)
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
