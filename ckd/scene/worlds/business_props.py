"""Premium-flat props for the business-documentary world.

The documentary scripts this world renders are about companies, products and
markets, so the vocabulary is deliberately small and honest:

* a **candybar phone** and a **touchscreen phone** (generic, unbranded shapes -
  we never draw a real company's product as if it were archival footage);
* a **factory** (for origin stories) and a **cell tower** (for infrastructure);
* a **globe** with network arcs;
* a **chart**, a **timeline** and a **stat card** for the numbers a script
  states - and, where a script gives no numbers, a chart that says so.

Everything static is rasterised once into the sprite cache (see `gfx.art`), so a
frame costs a paste plus a handful of live shapes.  Style rules are the same as
the other worlds: vertical gradients, contact shadows, rim light from upper
left, no hard outlines.
"""
from __future__ import annotations

import math
from typing import Dict, Sequence, Tuple

from PIL import Image, ImageDraw

from ...gfx.art import SPRITES, alpha, mix, shade, to_rgba
from .solar_props import Pen

Point = Tuple[float, float]


# ------------------------------------------------------------------- phones
def phone(pal: Dict[str, str], ss: int, x: float, y: float, w: float, h: float,
          *, kind: str = "classic", screen: str = "blank") -> Tuple[Image.Image, float, float]:
    """A generic handset. `kind` is classic (keypad) or touch (full glass)."""
    key = ("biz-phone", round(x), round(y), round(w), round(h), kind, pal.get("metal"), ss)
    box = (x - w * 0.22, y - h * 0.06, x + w * 1.22, y + h * 1.08)

    def paint(img: Image.Image, ox: float, oy: float, s: int) -> None:
        pen = Pen(img, ox, oy, s)
        r = w * 0.16 if kind == "classic" else w * 0.13
        # contact shadow on the table
        pen.shadow([(x + w * 0.12, y + h - 2), (x + w * 0.88, y + h - 2),
                    (x + w * 0.96, y + h + h * 0.035), (x + w * 0.04, y + h + h * 0.035)],
                   dy=5, blur=12, strength=0.5, color=to_rgba(pal["shadow"])[:3])
        # body: dark anodised metal with a bright edge
        pen.grad_round(x, y, x + w, y + h, mix(pal["metal_dark"], pal["metal"], 0.45),
                       shade(pal["metal_dark"], 0.55), radius=r)
        pen.rim([(x + r * 0.2, y + h * 0.02), (x + r * 0.2, y + h * 0.96)],
                alpha(pal["paper"], 0.5), width=1.6, strength=0.8)
        if kind == "classic":
            # earpiece, screen recess, keypad
            pen.rect(x + w * 0.40, y + h * 0.026, x + w * 0.60, y + h * 0.048,
                     fill=alpha(pal["ink"], 0.9), radius=h * 0.012)
            sx0, sy0 = x + w * 0.10, y + h * 0.085
            sx1, sy1 = x + w * 0.90, y + h * 0.40
            pen.grad_round(sx0, sy0, sx1, sy1, mix(pal["glass"], pal["ink"], 0.35),
                           shade(pal["ink"], 0.9), radius=w * 0.05)
            pen.gloss(sx0, sy0, sx1, sy1, strength=0.16)
            # keypad grid 3 x 4
            ky0 = y + h * 0.47
            for row in range(4):
                for col in range(3):
                    kx = x + w * (0.15 + col * 0.26)
                    kyy = ky0 + h * 0.105 * row
                    pen.rect(kx, kyy, kx + w * 0.20, kyy + h * 0.072,
                             fill=alpha(mix(pal["metal"], pal["metal_dark"], 0.45), 0.95),
                             radius=w * 0.035)
                    pen.rect(kx + w * 0.03, kyy + h * 0.012, kx + w * 0.17,
                             kyy + h * 0.021, fill=alpha(pal["paper"], 0.5), radius=2)
            pen.rect(x + w * 0.32, y + h * 0.425, x + w * 0.68, y + h * 0.45,
                     fill=alpha(pal["metal"], 0.55), radius=w * 0.02)
        else:
            # full-glass front with a thin bezel
            gx0, gy0 = x + w * 0.045, y + h * 0.018
            gx1, gy1 = x + w * 0.955, y + h * 0.968
            pen.grad_round(gx0, gy0, gx1, gy1, shade(pal["ink"], 1.1),
                           shade(pal["ink"], 0.75), radius=r * 0.9)
            pen.gloss(gx0, gy0, gx1, gy1, strength=0.20)
            pen.rect(x + w * 0.40, y + h * 0.030, x + w * 0.60, y + h * 0.042,
                     fill=alpha(pal["ink"], 0.85), radius=h * 0.008)
            # home indicator
            pen.rect(x + w * 0.36, y + h * 0.945, x + w * 0.64, y + h * 0.954,
                     fill=alpha(pal["paper"], 0.55), radius=2)
        # side buttons
        pen.rect(x - w * 0.014, y + h * 0.20, x + w * 0.004, y + h * 0.30,
                 fill=alpha(pal["metal_dark"], 0.9), radius=2)
        pen.rect(x + w * 0.996, y + h * 0.16, x + w * 1.012, y + h * 0.24,
                 fill=alpha(pal["metal_dark"], 0.9), radius=2)

    return SPRITES.get(key, box, ss, paint)


def screen_box(x: float, y: float, w: float, h: float, kind: str = "classic") -> Tuple[float, float, float, float]:
    """Inner screen rectangle for a phone drawn at (x, y, w, h)."""
    if kind == "classic":
        return (x + w * 0.10, y + h * 0.085, x + w * 0.90, y + h * 0.40)
    return (x + w * 0.045, y + h * 0.018, x + w * 0.955, y + h * 0.968)


# ---------------------------------------------------------------- industrial
def factory(pal: Dict[str, str], ss: int, x: float, y: float, w: float, h: float,
            *, lit: float = 1.0) -> Tuple[Image.Image, float, float]:
    """Sawtooth-roof mill with a chimney - the '1865 paper mill' silhouette."""
    key = ("biz-factory", round(x), round(y), round(w), round(h), round(lit, 1), pal.get("metal"), ss)
    box = (x - w * 0.08, y - h * 0.55, x + w * 1.08, y + h * 1.12)

    def paint(img: Image.Image, ox: float, oy: float, s: int) -> None:
        pen = Pen(img, ox, oy, s)
        base = y + h
        body_top = y + h * 0.34
        pen.shadow([(x + w * 0.04, base - 3), (x + w * 0.96, base - 3),
                    (x + w * 1.02, base + h * 0.04), (x - w * 0.02, base + h * 0.04)],
                   dy=4, blur=10, strength=0.45, color=to_rgba(pal["shadow"])[:3])
        # sawtooth roof
        teeth = 4
        tw = w * 0.92 / teeth
        pts = [(x + w * 0.04, body_top)]
        for i in range(teeth):
            x0 = x + w * 0.04 + i * tw
            pts += [(x0, body_top), (x0 + tw * 0.62, body_top - h * 0.17), (x0 + tw, body_top)]
        pen.poly(pts + [(x + w * 0.96, body_top)], fill=shade(pal["metal_dark"], 0.55))
        pen.grad_round(x + w * 0.04, body_top, x + w * 0.96, base,
                       mix(pal["metal_dark"], pal["ink"], 0.35), shade(pal["ink"], 1.15),
                       radius=w * 0.012)
        # chimney
        cx0, cx1 = x + w * 0.74, x + w * 0.86
        pen.grad_round(cx0, y, cx1, base - h * 0.30, shade(pal["metal_dark"], 0.85),
                       shade(pal["metal_dark"], 0.45), radius=w * 0.012)
        pen.rect(cx0 - w * 0.012, y, cx1 + w * 0.012, y + h * 0.045,
                 fill=alpha(pal["metal"], 0.55), radius=2)
        # lit windows
        rows, cols = 2, 5
        for r_ in range(rows):
            for c in range(cols):
                wx = x + w * (0.09 + c * 0.135)
                wy = body_top + h * (0.09 + r_ * 0.13)
                pen.rect(wx, wy, wx + w * 0.07, wy + h * 0.075,
                         fill=alpha(mix(pal["accent"], pal["paper"], 0.35), 0.85 * lit), radius=1.5)
        pen.rim([(x + w * 0.04, body_top + 2), (x + w * 0.04, base - 2)],
                alpha(pal["paper"], 0.35), width=1.2, strength=0.6)

    return SPRITES.get(key, box, ss, paint)


def tower(pal: Dict[str, str], ss: int, x: float, y: float, w: float, h: float,
          *, energy: float = 0.0) -> Tuple[Image.Image, float, float]:
    """Lattice telecom mast with panel antennas (replaces the grid pylon)."""
    key = ("biz-tower", round(x), round(y), round(w), round(h), round(energy, 1), pal.get("metal"), ss)
    box = (x - w * 0.25, y - h * 0.05, x + w * 1.25, y + h * 1.1)

    def paint(img: Image.Image, ox: float, oy: float, s: int) -> None:
        pen = Pen(img, ox, oy, s)
        cx = x + w * 0.5
        base = y + h
        top = y + h * 0.12
        pen.shadow([(cx - w * 0.22, base - 3), (cx + w * 0.22, base - 3),
                    (cx + w * 0.27, base + 4), (cx - w * 0.27, base + 4)],
                   dy=4, blur=8, strength=0.4, color=to_rgba(pal["shadow"])[:3])
        leg = mix(pal["metal_dark"], pal["metal"], 0.3)
        for side in (-1, 1):
            bx = cx + side * w * 0.26
            pen.line([(cx + side * w * 0.055, top), (bx, base)], leg, width=max(2.0, w * 0.045))
        # bracing
        steps = 6
        for i in range(steps):
            t0 = i / steps
            t1 = (i + 1) / steps
            w0 = w * (0.055 + 0.205 * t0)
            w1 = w * (0.055 + 0.205 * t1)
            y0 = top + (base - top) * t0
            y1 = top + (base - top) * t1
            pen.line([(cx - w0, y0), (cx + w1, y1)], alpha(leg, 0.85), width=max(1.2, w * 0.02))
            pen.line([(cx + w0, y0), (cx - w1, y1)], alpha(leg, 0.85), width=max(1.2, w * 0.02))
        # antenna panels
        for side in (-1, 1):
            px = cx + side * w * 0.14
            pen.grad_round(px - w * 0.05, top - h * 0.05, px + w * 0.05, top + h * 0.10,
                           mix(pal["metal"], pal["paper"], 0.15), shade(pal["metal_dark"], 0.7),
                           radius=w * 0.02)
        pen.line([(cx, top - h * 0.06), (cx, top)], alpha(pal["metal"], 0.9), width=max(1.5, w * 0.03))
        # status beacon
        r = max(2.5, w * 0.035)
        pen.ellipse(cx, top - h * 0.075, r, r, fill=alpha(pal["accent2"], 0.55 + 0.45 * energy))

    return SPRITES.get(key, box, ss, paint)
