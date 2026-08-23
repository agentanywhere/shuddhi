#!/usr/bin/env python3
"""Generate the Shuddhi brand asset set from one geometry definition.

The mark: a SEAL. A scalloped stamp — the shape of a certification seal or
a wax seal — closing around a single solid centre. Many documents in, one
sealed corpus out.

How we got here, because the rejects are the argument for the survivor:

  hexagon            HashiCorp claims it for infrastructure tooling
  chevrons + dot     that is the download icon at 32px and below
  bars + dot         that is the wifi icon
  ring with a top gap  that is the power button
  scalloped + check  that is the verified badge

Every literal illustration of "filtering" collided with a UI glyph, which
is the metaphor telling us something: filtering is the commodity half of
this product. Attestation is the half that is ours, and a stamp is the
oldest and most universal way to draw it — a notary seal reads the same in
every market, which matters for an international audience.
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
SW = 9.0
GAP_HALF_DEG = 26.0


BUMPS = 10        # fewer, chunkier teeth so the scallop survives 16px
R_INNER = 43.0
DOT_R = 12.0


def _pt(angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return CX + R * math.cos(a), CY - R * math.sin(a)


def mark_paths(colour: str) -> str:
    """A scalloped seal with a single mark at its centre.

    Every literal reading of "filter" collided with a UI icon: chevrons over
    a dot is the download glyph, bars over a dot is the wifi glyph, and a
    ring with a gap at the top is the power button. A hexagon belongs to
    HashiCorp. So the mark says the thing that is actually ours — this was
    SEALED — in the oldest visual language there is for it: a stamp.
    """
    pts = []
    n = BUMPS * 2
    for i in range(n):
        ang = math.pi / 2 + i * (2 * math.pi / n)
        rad = R if i % 2 == 0 else R_INNER
        pts.append((CX + rad * math.cos(ang), CY - rad * math.sin(ang)))
    d = f"M{pts[0][0]:.2f},{pts[0][1]:.2f}"
    for i in range(1, len(pts) + 1):
        x, y = pts[i % len(pts)]
        d += f" L{x:.2f},{y:.2f}"
    d += " Z"
    seal = (f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{SW}" '
            f'stroke-linejoin="round" stroke-linecap="round"/>')
    core = f'<circle cx="{CX:.0f}" cy="{CY:.0f}" r="{DOT_R}" fill="{colour}"/>'
    return seal + core


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
<desc id="d{name}">The Shuddhi seal beside the wordmark Shuddhi, with शुद्धि set beneath it.</desc>
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
