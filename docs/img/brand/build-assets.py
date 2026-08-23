#!/usr/bin/env python3
"""Generate the Shuddhi brand asset set from one geometry definition.

The mark: a DISTILLING FLASK. Round bulb, short neck, a side arm, and one
drop leaving it. शुद्धि means purification, and distillation is the oldest
and most universally legible picture of purification there is — raw input
in, one refined thing out, impurities left behind.

Why this and not the alternatives we drew:

  hexagon             HashiCorp claims it for infrastructure tooling
  chevrons + dot      the download glyph at 32px and below
  bars + dot          the wifi glyph
  ring with a top gap the power button
  scallop + check     the verified badge
  bare droplet        DigitalOcean
  scalloped seal      workable, but badges are everywhere; this is ownable

A retort is rare in developer tooling (most "lab" icons are Erlenmeyer
triangles or test tubes), it reads the same in every market, and it matches
what the product name literally means. Proportions are tuned so the bulb —
which is the silhouette — survives 16px.

Note on the ML sense of "distillation" (teacher-to-student model
compression): use this as a VISUAL metaphor and in copy, but never describe
Shuddhi as "a distillation tool", which would misdirect the exact audience
we want.
"""

import math
import os

BLUE = "#3a81f6"
INK_DARK = "#f0f1f9"
INK_LIGHT = "#0a0c18"
MUTED_DARK = "#a1a4b2"
MUTED_LIGHT = "#5a5f70"
BG_TILE = "#0a0c18"

CX = CY = 66.0
R = 54.0
SW = 10.5
GAP_HALF_DEG = 26.0


BUMPS = 10        # fewer, chunkier teeth so the scallop survives 16px
R_INNER = 43.0
DOT_R = 12.0


def _pt(angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return CX + R * math.cos(a), CY - R * math.sin(a)


def mark_paths(colour: str) -> str:
    sw = SW
    half_neck = 10.5
    bulb_r, cx, cy, neck_top = 30.0, 56.0, 82.0, 22.0
    dy = math.sqrt(max(bulb_r ** 2 - half_neck ** 2, 1))
    join_y = cy - dy
    L, R = cx - half_neck, cx + half_neck
    body = (f'<path d="M{L},{neck_top} L{L},{join_y:.1f} A{bulb_r},{bulb_r} 0 1 0 {R},{join_y:.1f} '
            f'L{R},{neck_top}" fill="none" stroke="{colour}" stroke-width="{sw}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')
    lip = (f'<path d="M{L - 7},{neck_top} L{R + 7},{neck_top}" fill="none" stroke="{colour}" '
           f'stroke-width="{sw}" stroke-linecap="round"/>')
    arm = (f'<path d="M{R},{neck_top + 15} L{R + 31},{neck_top + 32}" fill="none" stroke="{colour}" '
           f'stroke-width="{sw}" stroke-linecap="round"/>')
    drop = f'<circle cx="{R + 35}" cy="{neck_top + 54}" r="{sw * 0.72:.1f}" fill="{colour}"/>'
    return body + lip + arm + drop


def symbol(colour: str, size: int = 1024) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="0 0 132 132" role="img" aria-labelledby="t d">'
            f'<title id="t">Shuddhi</title>'
            f'<desc id="d">An open-topped seal: a ring broken at the top closing around bars '
            f'that narrow to a single dot — many documents in, one sealed corpus out.</desc>'
            f'{mark_paths(colour)}</svg>')


def app_icon(size: int = 1024) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="0 0 176 176" role="img" aria-label="Shuddhi">'
            f'<rect width="176" height="176" rx="40" fill="{BG_TILE}"/>'
            f'<g transform="translate(22,22)">{mark_paths(BLUE)}</g></svg>')


def lockup(ink: str, muted: str, name: str) -> str:
    """Horizontal lockup: mark, wordmark, and the Devanagari beneath.

    The Devanagari stays in the WORDMARK rather than the symbol: it carries
    the origin where it is an asset, without making the symbol illegible at
    16px or dependent on a Devanagari font being installed.
    """
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="320" viewBox="0 0 480 128" role="img" aria-labelledby="t{name} d{name}">
<title id="t{name}">Shuddhi</title>
<desc id="d{name}">The Shuddhi flask beside the wordmark Shuddhi, with शुद्धि set beneath it.</desc>
<g transform="translate(4,-2)">{mark_paths(BLUE)}</g>
<text x="150" y="66" font-family="IBM Plex Sans, Geist, Helvetica Neue, Arial, sans-serif"
      font-size="44" font-weight="600" letter-spacing="-0.8" fill="{ink}">Shuddhi</text>
<text x="152" y="94" font-family="Noto Sans Devanagari, Kohinoor Devanagari, Devanagari MT, sans-serif"
      font-size="22" fill="{muted}">शुद्धि</text>
</svg>'''


def social_card() -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="Shuddhi — prove what your model was trained on">
<rect width="1200" height="630" fill="#04050d"/>
<g transform="translate(96,150) scale(1.5)">{mark_paths(BLUE)}</g>
<text x="96" y="428" font-family="IBM Plex Sans, Geist, Helvetica Neue, Arial, sans-serif"
      font-size="66" font-weight="600" letter-spacing="-1.4" fill="{INK_DARK}">Shuddhi</text>
<text x="96" y="486" font-family="IBM Plex Sans, Geist, Helvetica Neue, Arial, sans-serif"
      font-size="30" fill="{MUTED_DARK}">Prove what your model was trained on.</text>
<text x="96" y="536" font-family="IBM Plex Mono, ui-monospace, Menlo, monospace"
      font-size="21" fill="{BLUE}">Apache-2.0 · github.com/agentanywhere/shuddhi</text>
</svg>'''


FILES = {
    "shuddhi-symbol.svg": symbol(BLUE),
    "shuddhi-symbol-mono-dark.svg": symbol(INK_DARK),
    "shuddhi-symbol-mono-light.svg": symbol(INK_LIGHT),
    "shuddhi-app-icon.svg": app_icon(),
    "shuddhi-horizontal-dark.svg": lockup(INK_DARK, MUTED_DARK, "d"),
    "shuddhi-horizontal-light.svg": lockup(INK_LIGHT, MUTED_LIGHT, "l"),
    "shuddhi-social-card.svg": social_card(),
    "favicon.svg": symbol(BLUE, 64),
}

if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    os.makedirs(out, exist_ok=True)
    for name, body in FILES.items():
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(body + "\n")
        print("wrote", name)
