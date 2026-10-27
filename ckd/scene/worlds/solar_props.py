"""Premium-flat props for the solar world.

Each prop is a function that paints into a cached sprite (see `gfx.art.SpriteCache`)
in *layout* coordinates and is then pasted as one image per frame.  That keeps the
expensive work — gradients, blurred shadows, rim light — to once per shape, so a
720p frame still renders in ~100 ms on two CPU cores.

Style rules used throughout:
  * surfaces get a vertical gradient, never a single flat fill;
  * every object sitting on the ground gets a blurred contact shadow;
  * the light comes from the upper left, so rim light runs along the top edge;
  * outlines are soft and dark, drawn *under* the shape (silhouette dilation),
    not as a hard 3 px stroke around it.
"""
from __future__ import annotations

import math
from typing import Dict, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter

from ...gfx import art
from ...gfx.art import SPRITES, alpha, mix, shade, to_rgba
from ...gfx.primitives import lerp

Point = Tuple[float, float]


class Pen:
    """Converts layout coordinates into sprite-canvas pixels.

    Translucent fills are painted through a scratch layer and composited, because
    `ImageDraw` writes RGBA verbatim instead of blending (that bug once put a
    grey slab across the sky).
    """

    def __init__(self, img: Image.Image, ox: float, oy: float, ss: int) -> None:
        self.img = img
        self.ox = ox
        self.oy = oy
        self.ss = ss

    # -- coordinate helpers -------------------------------------------------
    def P(self, pts: Sequence[Point]):
        return [((x - self.ox) * self.ss, (y - self.oy) * self.ss) for x, y in pts]

    def pt(self, x: float, y: float) -> Tuple[float, float]:
        return ((x - self.ox) * self.ss, (y - self.oy) * self.ss)

    def box(self, x0: float, y0: float, x1: float, y1: float):
        p0 = self.pt(x0, y0)
        p1 = self.pt(x1, y1)
        return (p0[0], p0[1], p1[0], p1[1])

    # -- blending -----------------------------------------------------------
    def act(self, box, fn) -> None:
        x0, y0, x1, y1 = box
        x0 = max(0, int(math.floor(x0)) - 2)
        y0 = max(0, int(math.floor(y0)) - 2)
        x1 = min(self.img.width, int(math.ceil(x1)) + 2)
        y1 = min(self.img.height, int(math.ceil(y1)) + 2)
        if x1 <= x0 or y1 <= y0:
            return
        layer = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        fn(ImageDraw.Draw(layer), x0, y0)
        self.img.alpha_composite(layer, (x0, y0))

    @staticmethod
    def _clear(*colors) -> bool:
        return any(c is not None and to_rgba(c)[3] < 255 for c in colors)

    def _bounds_poly(self, pts):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    # -- shapes -------------------------------------------------------------
    def poly(self, pts: Sequence[Point], fill=None, outline=None, width: float = 0.0) -> None:
        local = self.P(pts)
        bb = self._bounds_poly(local)

        def fn(d, ox, oy):
            d.polygon([(x - ox, y - oy) for x, y in local], fill=fill, outline=outline,
                      width=int(width * self.ss))
        if self._clear(fill, outline):
            self.act((bb[0] - width * self.ss, bb[1] - width * self.ss,
                      bb[2] + width * self.ss, bb[3] + width * self.ss), fn)
        else:
            fn(ImageDraw.Draw(self.img), 0, 0)

    def rect(self, x0, y0, x1, y1, fill=None, radius=0.0, outline=None, width=0.0) -> None:
        # normalise: props scale down a long way in 9:16, and a detail that is
        # thinner than its own inset would otherwise invert the box
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        if x1 - x0 < 0.05 or y1 - y0 < 0.05:
            return
        b = self.box(x0, y0, x1, y1)

        def fn(d, ox, oy):
            bb = (b[0] - ox, b[1] - oy, b[2] - ox, b[3] - oy)
            if radius > 0:
                d.rounded_rectangle(bb, radius=radius * self.ss, fill=fill, outline=outline,
                                    width=int(width * self.ss))
            else:
                d.rectangle(bb, fill=fill, outline=outline, width=int(width * self.ss))
        if self._clear(fill, outline):
            self.act(b, fn)
        else:
            fn(ImageDraw.Draw(self.img), 0, 0)

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=None, width=0.0) -> None:
        if rx <= 0.01 or ry <= 0.01:
            return
        c = self.pt(cx, cy)
        b = (c[0] - rx * self.ss, c[1] - ry * self.ss, c[0] + rx * self.ss, c[1] + ry * self.ss)

        def fn(d, ox, oy):
            d.ellipse((b[0] - ox, b[1] - oy, b[2] - ox, b[3] - oy), fill=fill, outline=outline,
                      width=int(width * self.ss))
        if self._clear(fill, outline):
            self.act(b, fn)
        else:
            fn(ImageDraw.Draw(self.img), 0, 0)

    def line(self, pts: Sequence[Point], color, width: float = 2.0) -> None:
        local = self.P(pts)
        bb = self._bounds_poly(local)
        w = max(1, int(width * self.ss))

        def fn(d, ox, oy):
            d.line([(x - ox, y - oy) for x, y in local], fill=color, width=w, joint="curve")
        if self._clear(color):
            self.act((bb[0] - w, bb[1] - w, bb[2] + w, bb[3] + w), fn)
        else:
            fn(ImageDraw.Draw(self.img), 0, 0)

    # -- art helpers --------------------------------------------------------
    def grad_poly(self, pts: Sequence[Point], top, bottom, power: float = 1.0) -> None:
        art.draw_gradient_polygon(self.img, self.P(pts), top, bottom, power=power)

    def grad_round(self, x0, y0, x1, y1, top, bottom, radius: float = 0.0, power: float = 1.0) -> None:
        art.draw_gradient_round(self.img, self.box(x0, y0, x1, y1), radius * self.ss,
                                top, bottom, power=power)

    def shadow(self, pts: Sequence[Point], dx: float = 0.0, dy: float = 10.0,
               blur: float = 8.0, strength: float = 0.42, color=(14, 10, 26)) -> None:
        art.draw_soft_shadow(self.img, self.P(pts), dx=dx * self.ss, dy=dy * self.ss,
                             blur=blur * self.ss, color=color, strength=strength)

    def rim(self, pts: Sequence[Point], color, width: float = 2.0, strength: float = 0.5,
            side: str = "left") -> None:
        art.draw_rim(self.img, self.P(pts), color, width=width * self.ss,
                     strength=strength, light_from=side)

    def gloss(self, x0, y0, x1, y1, strength: float = 0.18) -> None:
        art.draw_gloss(self.img, self.box(x0, y0, x1, y1), strength=strength)


def _silhouette(img: Image.Image, outline, grow: float = 2.0) -> Image.Image:
    """Put a soft dark line *under* the painted sprite (keeps edges readable)."""
    mask = img.getchannel("A")
    grown = mask.filter(ImageFilter.MaxFilter(int(max(3, grow * 2 + 1))))
    line_layer = Image.new("RGBA", img.size, to_rgba(outline))
    line_layer.putalpha(grown.point(lambda v: int(v * 0.9)))
    return Image.alpha_composite(line_layer, img)


# ----------------------------------------------------------------------- sky
def draw_hills(pen: Pen, stage_w: float, horizon: float, layers: Sequence[dict]) -> None:
    """Three parallax ridge lines with atmospheric fade toward the horizon."""
    for layer in layers:
        pts = layer["pts"]
        pen.poly(pts, fill=layer["fill"])


def backdrop(stage_w: float, stage_h: float, horizon: float, pal: Dict[str, str], ss: int,
             seed: int = 4) -> Tuple[Image.Image, float, float]:
    """Static sky + ridges + ground, rendered once per format.

    Covers the *whole* frame: the plate is drawn outside the camera transform, so
    any uncovered pixel would show as a flat band at the bottom of the video.
    """
    key = ("solar-backdrop", round(stage_w, 1), round(stage_h, 1), round(horizon, 1),
           pal.get("bg_top"), pal.get("sky_glow"), pal.get("ground"), ss)
    box = (0.0, 0.0, stage_w, stage_h)

    def paint(img: Image.Image, ox: float, oy: float, s: int) -> None:
        pen = Pen(img, ox, oy, s)
        w = stage_w
        h = stage_h
        top = to_rgba(pal["bg_top"])
        glow = to_rgba(pal["sky_glow"])
        # base coat first: gradients and ridge polygons leave hairline gaps at
        # their joins, and a gap in a static plate is a black seam in the video.
        pen.poly([(0, 0), (w, 0), (w, h), (0, h)], fill=mix(pal["bg_top"], pal["sky_glow"], 0.55))

        # --- sky: three stacked ramps so the horizon warms up gradually
        pen.grad_round(0, -2, w, horizon * 0.62, mix(top, glow, 0.10), mix(top, glow, 0.42),
                       radius=0, power=1.25)
        pen.grad_round(0, horizon * 0.60, w, horizon * 1.02, mix(top, glow, 0.42),
                       mix(top, glow, 0.72), radius=0, power=1.5)

        # --- sun bloom, painted into the sky
        bloom = art.radial_glow((int(w * s), int(horizon * 1.1 * s)),
                                alpha(pal["accent3"], 0.30), cx=0.80, cy=0.52,
                                radius=0.55, power=1.9)
        img.alpha_composite(bloom, (int(-ox * s), int(-oy * s)))

        # --- ridges: far (hazy) -> near (dark, saturated)
        far = mix(pal["ground_far"], pal["sky_glow"], 0.42)
        mid = mix(pal["ground_far"], pal["ground"], 0.45)
        near = pal["ground"]
        ridge_far = art.smooth_path([
            (-20, horizon + 18), (w * 0.18, horizon - 26), (w * 0.38, horizon + 6),
            (w * 0.60, horizon - 34), (w * 0.82, horizon + 2), (w + 20, horizon + 22)], closed=False)
        pen.poly([(-20, h)] + list(ridge_far) + [(w + 20, h)], fill=far)
        ridge_mid = art.smooth_path([
            (-20, horizon + 54), (w * 0.22, horizon + 22), (w * 0.46, horizon + 58),
            (w * 0.70, horizon + 26), (w * 0.90, horizon + 52), (w + 20, horizon + 44)],
            closed=False)
        pen.poly([(-20, h)] + list(ridge_mid) + [(w + 20, h)], fill=mid)
        ridge_near = art.smooth_path([
            (-20, horizon + 96), (w * 0.26, horizon + 74), (w * 0.52, horizon + 104),
            (w * 0.78, horizon + 80), (w + 20, horizon + 100)], closed=False)
        pen.grad_poly([(-20, h)] + list(ridge_near) + [(w + 20, h)],
                      shade(near, 1.06), shade(near, 0.86))

    img, ox, oy = SPRITES.get(key, box, ss, paint)
    return img, ox, oy


# --------------------------------------------------------------------- props
def house(pal: Dict[str, str], ss: int, x: float, y: float, w: float, h: float,
          *, glow: float = 0.35, build: float = 1.0) -> Tuple[Image.Image, float, float]:
    key = ("solar-house", round(x), round(y), round(w), round(h), round(glow, 2),
           round(build, 2), pal.get("paper"), ss)
    box = (x - w * 0.10, y - h * 0.10, x + w * 1.10, y + h * 1.14)

    def paint(img, ox, oy, s):
        pen = Pen(img, ox, oy, s)
        body_h = h * 0.66 * build
        bx0, bx1 = x + w * 0.08, x + w * 0.92
        by1 = y + h
        by0 = by1 - body_h
        roof_h = h * 0.30 * build
        peak = (x + w * 0.5, by0 - roof_h)

        # contact shadow on the ground
        pen.shadow([(bx0 - 4, by1 - 4), (bx1 + 4, by1 - 4), (bx1 + 10, by1 + 3), (bx0 - 10, by1 + 3)],
                   dy=6, blur=9, strength=0.50)

        wall_top, wall_bot = mix(pal["paper"], pal["sky_glow"], 0.06), shade(pal["paper"], 0.86)
        pen.grad_round(bx0, by0, bx1, by1, wall_top, wall_bot, radius=6)
        # wall shading: the sun is on the left, so the right third is darker
        pen.poly([(bx0 + w * 0.60, by0), (bx1, by0), (bx1, by1), (bx0 + w * 0.54, by1)],
                 fill=alpha(shade(pal["paper"], 0.74), 0.55))

        # roof: gable with an overhang and a shadow line on the wall
        roof = [(bx0 - w * 0.07, by0 + 3), peak, (bx1 + w * 0.07, by0 + 3)]
        pen.poly([(rvx, rvy + 6) for rvx, rvy in roof], fill=alpha((14, 10, 22), 0.35))
        pen.grad_poly(roof, mix(pal["accent2"], pal["paper"], 0.34), shade(pal["accent2"], 0.62))
        # lit slope (facing the sun on the left) and an eave shadow on the wall
        pen.poly([(bx0 - w * 0.07, by0 + 3), peak, (x + w * 0.5, by0 + 3)],
                 fill=alpha(mix(pal["accent2"], pal["paper"], 0.55), 0.55))
        pen.rect(bx0, by0 + 1, bx1, by0 + h * 0.035, fill=alpha((16, 10, 26), 0.30))
        pen.line([(bx0 - w * 0.07, by0 + 3), peak, (bx1 + w * 0.07, by0 + 3)],
                 alpha(shade(pal["accent2"], 0.55), 0.85), width=2.2)
        pen.rect(bx0 + w * 0.04, by0 + 2, bx1 - w * 0.04, by0 + h * 0.018,
                 fill=alpha((14, 10, 22), 0.22))

        # windows
        for wx_ in (0.17, 0.56):
            ww_ = w * 0.20
            wy_ = by0 + body_h * 0.20
            wh_ = body_h * 0.30
            gx0, gx1 = x + w * wx_, x + w * wx_ + ww_
            pen.rect(gx0 - 2, wy_ - 2, gx1 + 2, wy_ + wh_ + 2, fill=alpha((18, 12, 26), 0.55),
                     radius=3)
            warm = mix(mix(pal["accent3"], pal["accent"], 0.45), pal["paper"], 0.10 + 0.22 * glow)
            pen.grad_round(gx0, wy_, gx1, wy_ + wh_, mix(warm, pal["paper"], 0.45), shade(warm, 0.72),
                           radius=2)
            # mullions
            pen.line([((gx0 + gx1) / 2, wy_), ((gx0 + gx1) / 2, wy_ + wh_)],
                     alpha((20, 14, 30), 0.55), width=1.4)
            pen.line([(gx0, wy_ + wh_ * 0.52), (gx1, wy_ + wh_ * 0.52)],
                     alpha((20, 14, 30), 0.55), width=1.2)
            if glow > 0.05:
                pen.ellipse((gx0 + gx1) / 2, wy_ + wh_ * 0.5, ww_ * 0.95, wh_ * 0.95,
                            fill=alpha(pal["accent3"], 0.05 + 0.09 * glow))

        # door
        dx0 = x + w * 0.40
        dw = w * 0.15
        pen.rect(dx0 - 2, by1 - body_h * 0.44 - 2, dx0 + dw + 2, by1, fill=alpha((18, 12, 26), 0.5),
                 radius=3)
        pen.grad_round(dx0, by1 - body_h * 0.42, dx0 + dw, by1,
                       shade(pal["ink"], 1.0), shade(pal["ink"], 0.72), radius=2)
        pen.ellipse(dx0 + dw * 0.78, by1 - body_h * 0.20, 1.5, 1.5,
                    fill=alpha(pal["accent3"], 0.85))

        # rim light along the roof edge and the left wall
        pen.rim(roof, alpha(pal["accent3"], 0.55), width=1.6, strength=0.35)

    return SPRITES.get(key, box, ss, paint)


def panel(pal: Dict[str, str], ss: int, x: float, y: float, w: float, h: float,
          *, rows: int = 3, cols: int = 4, glow: float = 0.0, tilt: float = 0.16,
          legs: bool = False, explode: float = 0.0,
          ) -> Tuple[Image.Image, float, float]:
    """Photovoltaic array: skewed glass, per-cell gradient, reflection streak."""
    glow = round(max(0.0, min(1.0, glow)) / 0.12) * 0.12
    key = ("solar-panel", round(x), round(y), round(w), round(h), rows, cols,
           round(glow, 2), round(tilt, 3), legs, round(explode, 2), pal.get("cool"), ss)
    box = (x - w * 0.10, y - h * 0.16, x + w * 1.10, y + h * 1.22)

    def paint(img, ox, oy, s):
        pen = Pen(img, ox, oy, s)
        pw = w * 0.92
        ph = pw * (rows / max(1, cols)) * 0.72
        if ph > h * 0.9:
            ph = h * 0.9
            pw = ph * (cols / max(1, rows)) / 0.72
        skew = ph * tilt
        pw = max(60.0, pw - skew)
        cx, cy = x + w / 2, y + h / 2
        x0, x1 = cx - pw / 2, cx + pw / 2
        top_y, bot_y = cy - ph / 2, cy + ph / 2
        quad = [(x0 + skew, top_y), (x1, top_y - skew * 0.18),
                (x1 - skew, bot_y), (x0, bot_y - skew * 0.18)]

        if legs:
            for lx in (x0 + pw * 0.22, x1 - pw * 0.22):
                pen.rect(lx - 2.5, bot_y - ph * 0.05, lx + 2.5, bot_y + ph * 0.42,
                         fill=alpha(shade(pal["metal_dark"], 0.8), 0.95), radius=1.5)
            pen.shadow([(x0, bot_y + ph * 0.34), (x1, bot_y + ph * 0.30),
                        (x1, bot_y + ph * 0.44), (x0, bot_y + ph * 0.48)],
                       dy=4, blur=8, strength=0.4)

        # glass plate: a thin blue-ish edge under the cell grid
        pen.grad_poly(quad, mix(pal["cool"], pal["ink"], 0.55), mix(pal["cool"], pal["ink"], 0.78))
        # cells: deep indigo silicon with a specular gradient, thin silver busbars
        for r in range(rows):
            for c in range(cols):
                u0, u1 = c / cols, (c + 1) / cols
                v0, v1 = r / rows, (r + 1) / rows

                def pt(u, v):
                    tx = quad[0][0] + (quad[1][0] - quad[0][0]) * u
                    ty = quad[0][1] + (quad[1][1] - quad[0][1]) * u
                    bx = quad[3][0] + (quad[2][0] - quad[3][0]) * u
                    by = quad[3][1] + (quad[2][1] - quad[3][1]) * u
                    return (tx + (bx - tx) * v, ty + (by - ty) * v)

                inset = 0.045
                cell = [pt(u0 + inset, v0 + inset), pt(u1 - inset, v0 + inset),
                        pt(u1 - inset, v1 - inset), pt(u0 + inset, v1 - inset)]
                lit = glow * (0.6 + 0.4 * math.sin((r * cols + c) * 0.9))
                base_dark = mix(pal["ink"], pal["cool"], 0.42)
                top_c = mix(base_dark, pal["glass"], 0.30 + 0.22 * max(0.0, lit))
                bot_c = shade(base_dark, 0.62)
                pen.grad_poly(cell, top_c, bot_c, power=1.25)
                # busbar detail: two thin lines per cell
                for frac in (0.34, 0.67):
                    a_ = pt(u0 + inset, v0 + (v1 - v0) * frac)
                    b_ = pt(u1 - inset, v0 + (v1 - v0) * frac)
                    pen.line([a_, b_], alpha(mix(pal["metal"], pal["cool"], 0.4), 0.30), width=1.0)
        # silver frame around the whole array
        pen.line([*quad, quad[0]], alpha(mix(pal["metal"], pal["ink"], 0.25), 0.95), width=3.4)
        pen.line([(quad[0][0], quad[0][1] + 2), (quad[1][0], quad[1][1] + 2.5)],
                 alpha(mix(pal["metal"], pal["paper"], 0.75), 0.85), width=1.8)

        # reflection streak across the glass
        streak = [(x0 + skew * 1.2, top_y + ph * 0.06),
                  (x0 + skew * 1.2 + pw * 0.16, top_y + ph * 0.06),
                  (x0 + pw * 0.24, bot_y - ph * 0.06),
                  (x0 + pw * 0.10, bot_y - ph * 0.06)]
        pen.poly(streak, fill=alpha((255, 255, 255), 0.10))
        # frame
        pen.line([*quad, quad[0]], alpha(shade(pal["metal"], 0.85), 0.95), width=3.0)
        pen.line([(quad[0][0], quad[0][1] + 2), (quad[1][0], quad[1][1] + 2)],
                 alpha((255, 255, 255), 0.35), width=1.6)
        if explode > 0:
            _exploded(pen, pal, quad, explode)

    return SPRITES.get(key, box, ss, paint)


def _exploded(pen: Pen, pal: Dict[str, str], quad, t: float) -> None:
    """Cell cross-section sliding out of the array (glass / silicon / backing)."""
    x0 = min(p[0] for p in quad)
    x1 = max(p[0] for p in quad)
    y0 = min(p[1] for p in quad)
    w = (x1 - x0) * 0.86
    layers = [("glass", 0.30), ("silicon", 0.55), ("backing", 0.80)]
    for i, (name, fy) in enumerate(layers):
        off = t * (60 + i * 26)
        ly = y0 + (max(p[1] for p in quad) - y0) * fy - off
        col = {"glass": mix(pal["glass"], pal["paper"], 0.35),
               "silicon": mix(pal["cool"], pal["accent3"], 0.35),
               "backing": shade(pal["metal_dark"], 0.9)}[name]
        pen.grad_round(x0 + 8, ly, x0 + 8 + w, ly + 14, mix(col, pal["paper"], 0.18), col, radius=4)


def inverter(pal: Dict[str, str], ss: int, x: float, y: float, w: float, h: float,
             *, pulse: float = 0.0, wave_phase: float = 0.0) -> Tuple[Image.Image, float, float]:
    """Inverter body (cached) — the AC trace and the pulse LED are drawn live.

    Caching by animation phase would create a new sprite per frame, which is
    slower than just drawing two vectors over a cached body.
    """
    key = ("solar-inverter", round(x), round(y), round(w), round(h), pal.get("metal"), ss)
    box = (x - w * 0.15, y - h * 0.12, x + w * 1.15, y + h * 1.15)

    def paint(img, ox, oy, s):
        pen = Pen(img, ox, oy, s)
        bx0, bx1 = x + w * 0.10, x + w * 0.90
        by0, by1 = y + h * 0.06, y + h
        pen.shadow([(bx0, by1 - 6), (bx1, by1 - 6), (bx1 + 6, by1 + 4), (bx0 - 6, by1 + 4)],
                   dy=5, blur=8, strength=0.45)
        pen.grad_round(bx0, by0, bx1, by1, shade(pal["metal"], 1.08), shade(pal["metal"], 0.62),
                       radius=7)
        # brushed metal edges
        pen.rect(bx0 + 3, by0 + 3, bx1 - 3, by0 + h * 0.03, fill=alpha((255, 255, 255), 0.16),
                 radius=2)
        # screen
        sx0, sx1 = bx0 + w * 0.10, bx1 - w * 0.10
        sy0, sy1 = by0 + h * 0.10, by0 + h * 0.42
        pen.rect(sx0 - 2, sy0 - 2, sx1 + 2, sy1 + 2, fill=alpha((10, 8, 18), 0.85), radius=4)
        pen.grad_round(sx0, sy0, sx1, sy1, mix(pal["ink"], pal["cool"], 0.18),
                       shade(pal["ink"], 0.9), radius=3)
        # vents
        for i in range(4):
            vx = bx0 + w * 0.14 + i * w * 0.19
            pen.rect(vx, by0 + h * 0.52, vx + w * 0.10, by0 + h * 0.78,
                     fill=alpha((255, 255, 255), 0.10), radius=2)
        # status LED seat (the lit state is drawn live)
        pen.ellipse(bx0 + w * 0.16, by0 + h * 0.90, w * 0.045, w * 0.045,
                    fill=alpha(shade(pal["ink"], 0.8), 0.9))
        pen.rim([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)], alpha(pal["paper"], 0.5),
                width=1.8, strength=0.30)

    return SPRITES.get(key, box, ss, paint)


def battery(pal: Dict[str, str], ss: int, x: float, y: float, w: float, h: float,
            *, fill: float = 0.35) -> Tuple[Image.Image, float, float]:
    fill = round(max(0.03, min(1.0, fill)) / 0.1) * 0.1
    key = ("solar-battery", round(x), round(y), round(w), round(h), round(fill, 1), pal.get("metal"), ss)
    box = (x - w * 0.2, y - h * 0.1, x + w * 1.2, y + h * 1.12)

    def paint(img, ox, oy, s):
        pen = Pen(img, ox, oy, s)
        bx0, bx1 = x + w * 0.10, x + w * 0.90
        by0, by1 = y + h * 0.10, y + h
        pen.shadow([(bx0, by1 - 5), (bx1, by1 - 5), (bx1 + 5, by1 + 3), (bx0 - 5, by1 + 3)],
                   dy=4, blur=7, strength=0.42)
        # terminal
        pen.rect(x + w * 0.40, by0 - h * 0.05, x + w * 0.60, by0 + 2,
                 fill=alpha(shade(pal["metal"], 0.75), 0.95), radius=2)
        pen.grad_round(bx0, by0, bx1, by1, shade(pal["metal"], 1.06), shade(pal["metal"], 0.58),
                       radius=8)
        # charge window: dark glass cell with a bright state-of-charge bar
        wx0, wx1 = bx0 + w * 0.10, bx1 - w * 0.10
        wy0, wy1 = by0 + h * 0.14, by1 - h * 0.12
        pen.grad_round(wx0, wy0, wx1, wy1, shade(pal["ink"], 1.05), shade(pal["ink"], 0.80), radius=5)
        fill_y = wy1 - (wy1 - wy0) * max(0.04, min(1.0, fill))
        pen.grad_round(wx0 + 2.5, fill_y, wx1 - 2.5, wy1 - 2.5,
                       mix(pal["accent3"], pal["accent"], 0.35), pal["accent"], radius=4)
        pen.line([(wx0 + 2.5, fill_y), (wx1 - 2.5, fill_y)],
                 alpha(mix(pal["accent3"], pal["paper"], 0.55), 0.9), width=1.6)
        for i in range(4):
            ly = wy0 + (wy1 - wy0) * (0.2 + 0.2 * i)
            pen.line([(wx0 + 3, ly), (wx0 + 8, ly)], alpha((255, 255, 255), 0.22), width=1.2)
            pen.line([(wx1 - 8, ly), (wx1 - 3, ly)], alpha((255, 255, 255), 0.22), width=1.2)
        pen.rim([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)], alpha(pal["paper"], 0.45),
                width=1.6, strength=0.28)

    return SPRITES.get(key, box, ss, paint)


def sun_disc(pal: Dict[str, str], ss: int, cx: float, cy: float, r: float,
             *, glow: float = 1.0, rays: bool = True) -> Tuple[Image.Image, float, float]:
    key = ("solar-sun", round(cx), round(cy), round(r), round(glow, 2), rays, ss)
    box = (cx - r * 4, cy - r * 4, cx + r * 4, cy + r * 4)

    def paint(img, ox, oy, s):
        pen = Pen(img, ox, oy, s)
        # layered bloom
        for i, (mult, a) in enumerate(((3.6, 0.10), (2.4, 0.16), (1.6, 0.26))):
            pen.ellipse(cx, cy, r * mult * glow, r * mult * glow,
                        fill=alpha(pal["accent3"], a))
        if rays:
            for i in range(12):
                ang = i * math.pi / 6
                l0, l1 = r * 1.25, r * 1.62
                pen.line([(cx + math.cos(ang) * l0, cy + math.sin(ang) * l0),
                          (cx + math.cos(ang) * l1, cy + math.sin(ang) * l1)],
                         alpha(pal["accent3"], 0.45), width=2.0)
        pen.ellipse(cx, cy, r, r, fill=alpha(pal["accent3"], 0.98))
        pen.ellipse(cx, cy - r * 0.16, r * 0.92, r * 0.88, fill=alpha(mix(pal["accent3"], pal["paper"], 0.45), 0.55))

    return SPRITES.get(key, box, ss, paint)


def slab(pal: Dict[str, str], ss: int, x0: float, y0: float, x1: float, y1: float,
         fill, *, skew: float = 0.0, alpha_top: float = 0.0, edge=None,
         ) -> Tuple[Image.Image, float, float]:
    """A single glass/metal layer of the cell sandwich (used by the exploded stack)."""
    key = ("solar-slab", round(x0), round(y0), round(x1), round(y1), str(fill),
           round(skew, 1), round(alpha_top, 2), str(edge), ss)
    box = (x0 - abs(skew) - 20, y0 - 20, x1 + abs(skew) + 20, y1 + 20)

    def paint(img, ox, oy, s):
        pen = Pen(img, ox, oy, s)
        quad = [(x0 + skew, y0), (x1, y0 + skew * 0.18), (x1 - skew, y1), (x0, y1 - skew * 0.18)]
        pen.shadow(quad, dy=9, blur=10, strength=0.34)
        base = to_rgba(fill)
        pen.grad_poly(quad, mix(base, pal["paper"], 0.30), shade(base, 0.72), power=1.15)
        # a bright top edge sells a thin plate in perspective
        pen.line([quad[0], quad[1]], alpha(mix(base, pal["paper"], 0.75), 0.85), width=2.2)
        if edge is not None:
            pen.line([*quad, quad[0]], alpha(edge, 0.55), width=1.4)
        else:
            pen.line([*quad, quad[0]], alpha(shade(base, 0.55), 0.55), width=1.4)
        pen.gloss(x0, y0, x1, y1, strength=0.10)
    return SPRITES.get(key, box, ss, paint)


def pylon(pal: Dict[str, str], ss: int, x: float, y: float, w: float, h: float,
          *, energy: float = 0.0) -> Tuple[Image.Image, float, float]:
    """Stylised transmission tower with tapered legs and cross-arms."""
    key = ("solar-pylon", round(x), round(y), round(w), round(h), round(energy, 1), ss)
    box = (x - w * 0.2, y - h * 0.05, x + w * 1.2, y + h * 1.15)

    def paint(img, ox, oy, s):
        pen = Pen(img, ox, oy, s)
        cx = x + w * 0.5
        base = y + h
        top = y + h * 0.10
        leg = mix(pal["metal_dark"], pal["metal"], 0.35)
        pen.shadow([(cx - w * 0.22, base - 3), (cx + w * 0.22, base - 3),
                    (cx + w * 0.26, base + 5), (cx - w * 0.26, base + 5)],
                   dy=4, blur=8, strength=0.42)
        # tapered legs + ladder bracing
        for side in (-1, 1):
            pen.line([(cx + side * w * 0.26, base), (cx + side * w * 0.07, top)],
                     leg, width=3.4)
        rungs = 7
        for i in range(rungs):
            t0 = i / rungs
            t1 = (i + 1) / rungs
            y0 = base + (top - base) * t0
            y1 = base + (top - base) * t1
            hw0 = w * (0.26 + (0.07 - 0.26) * t0)
            hw1 = w * (0.26 + (0.07 - 0.26) * t1)
            pen.line([(cx - hw0, y0), (cx + hw1, y1)], alpha(leg, 0.55), width=1.5)
            pen.line([(cx + hw0, y0), (cx - hw1, y1)], alpha(leg, 0.55), width=1.5)
        # cross-arms
        for i, (fy, half) in enumerate(((0.28, 0.46), (0.44, 0.38), (0.60, 0.30))):
            yy = y + h * fy
            pen.line([(cx - w * half, yy), (cx + w * half, yy)], leg, width=3.0)
            for side in (-1, 1):
                pen.line([(cx + side * w * half, yy), (cx + side * w * (half - 0.10), yy + h * 0.06)],
                         alpha(leg, 0.7), width=1.8)
                # insulator
                pen.ellipse(cx + side * w * half, yy + h * 0.075, 2.6, 4.0,
                            fill=alpha(mix(pal["metal"], pal["paper"], 0.4), 0.9))
        pen.ellipse(cx, top, 3.2, 3.2, fill=alpha(leg, 0.9))
        if energy > 0:
            for i in range(4):
                u = ((i / 4) + (energy * 0.35)) % 1.0
                pen.ellipse(cx, lerp(base, top, u), 3.0, 3.0, fill=alpha(pal["accent3"], 0.85))
    return SPRITES.get(key, box, ss, paint)


def cable(pen_or_painter, points, *, casing="3a2a44", core="#ff6b6b", width: float = 8.0,
          progress: float = 1.0) -> None:
    """Two-tone cable: dark casing with a warm conductor line inside."""
    pts = list(points)
    if progress < 1.0:
        pts = pts[: max(2, int(len(pts) * progress))]
    pen_or_painter.line(pts, alpha(casing, 0.9), width=width)
    pen_or_painter.line(pts, alpha(core, 0.95), width=width * 0.52)
    pen_or_painter.line([(x, y - width * 0.18) for x, y in pts], alpha(mix(core, "#ffffff", 0.5), 0.45),
                        width=max(1.0, width * 0.14))
