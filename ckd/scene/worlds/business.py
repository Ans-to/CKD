"""Business-documentary world: companies, products, markets, networks.

This world exists for *imported scripts* - a user-written documentary broken into
scenes with a voice-over, a visual direction and on-screen text (see
`ckd/content/script_import.py`).  It is a different visual language from the
explainer worlds: a dark, cinematic stage, one large subject at a time, slow
camera moves and hard cut-aways between "shots" inside a scene.

What it can and cannot do
-------------------------
The scripts that motivated this world ask for "realistic cinematic footage,
historical photographs and archival clips".  This project is a procedural
renderer: it draws **labelled motion graphics**, not footage, and it never
pretends otherwise.  A scene whose direction says "archival footage of a 19th
century paper mill" renders as a stylised mill illustration - clearly an
illustration, with the palette and lighting of the rest of the film.  The same
rule applies to companies: phones here are generic handset silhouettes, never a
real product rendered as if it were a photograph.

Composition
-----------
One *shot* is on screen at a time.  The scene plan gives each shot an action id;
an element fades in with `params.in` and out with `params.out`, so the picture
changes while the narration keeps talking.  Elements that are not part of any
shot (background, skyline) persist for the whole scene.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Sequence, Tuple

from ...gfx.art import SPRITES, alpha, mix, shade, to_rgba
from ...gfx.painter import Painter, with_alpha
from ...gfx.primitives import clamp, ease_in_out, ease_out, flow_dots, stagger
from ...text.shaping import TextStyle
from ..stage import Box, Stage
from .base import RenderContext, World
from . import business_props as props


_FADE_IN = 0.45   # seconds
_FADE_OUT = 0.35


def _shot(ctx: RenderContext, el: Dict) -> float:
    """Fade for one shot element: in on `params.in`, out on `params.out`.

    The fade is a fixed number of *seconds*, not a fraction of the action.  With a
    fraction, a ten-second shot took six seconds to fade in, so three phone shots
    in a row were all half-visible at once and the frame read as a double exposure.
    """
    params = el.get("params") or {}
    a = 1.0
    key_in = params.get("in")
    if key_in:
        since = ctx.since(str(key_in))
        # an unknown action id means "no timing": show the element rather than
        # silently dropping it from the scene
        a *= 1.0 if since >= 1e5 else clamp(since / _FADE_IN)
    key_out = params.get("out")
    if key_out:
        since = ctx.since(str(key_out))
        if since > 0:
            a *= 1.0 - clamp(since / _FADE_OUT)
    return clamp(a)


def _params(el: Dict) -> Dict:
    return el.get("params") or {}


class BusinessWorld(World):
    id = "business"
    palette_name = "documentary"
    element_types = (
        "skyline", "phone", "factory", "tower", "globe", "chart", "timeline",
        "stat", "ecosystem", "compare_phones", "statement", "lower_third", "label",
    )

    # ----------------------------------------------------------------- layout
    def slots(self, stage: Stage) -> Dict[str, Box]:
        W, H = float(stage.width), float(stage.height)
        wx, wy, ww, wh = stage.world_area
        if stage.format == "vertical":
            band = (W * 0.06, H * 0.255, W * 0.88, H * 0.255)
            s: Dict[str, Box] = {
                "back": (wx, wy, ww, wh),
                "stage": band,
                "wide": (W * 0.055, H * 0.255, W * 0.89, H * 0.255),
                "hero": (W * 0.26, H * 0.245, W * 0.48, H * 0.275),
                "stage_left": (W * 0.055, H * 0.255, W * 0.40, H * 0.255),
                "stage_right": (W * 0.55, H * 0.255, W * 0.40, H * 0.255),
                "stage_mid": (W * 0.33, H * 0.255, W * 0.34, H * 0.255),
                "phone": (W * 0.31, H * 0.258, W * 0.38, H * 0.245),
                "phone_b": (W * 0.55, H * 0.258, W * 0.34, H * 0.225),
                "globe": (W * 0.20, H * 0.25, W * 0.60, H * 0.26),
                "tower": (W * 0.34, H * 0.252, W * 0.32, H * 0.25),
                "factory": (W * 0.10, H * 0.275, W * 0.56, H * 0.235),
                # a shot's statement docks between the hero and the supers: wide
                # slots are centred on the hero in 9:16 and the text would be
                # swallowed by the phone
                "statement_low": (W * 0.06, H * 0.525, W * 0.88, H * 0.105),
                # a network diagram needs room in both axes; the 0.255H prop band
                # squashed the orbit until the hub label sat on the top node
                "tall": (W * 0.05, H * 0.245, W * 0.90, H * 0.39),
                "caption_band": (W * 0.05, H * 0.815, W * 0.90, H * 0.10),
                "upper_supers": (W * 0.055, H * 0.66, W * 0.89, H * 0.10),
            }
            return s
        # landscape: the character owns one side, the world the rest
        s = {
            "back": (wx, wy, ww, wh),
            "stage": (wx + ww * 0.04, wy + wh * 0.06, ww * 0.92, wh * 0.86),
            "wide": (wx + ww * 0.05, wy + wh * 0.05, ww * 0.90, wh * 0.86),
            "hero": (wx + ww * 0.22, wy + wh * 0.02, ww * 0.56, wh * 0.92),
            "stage_left": (wx + ww * 0.03, wy + wh * 0.10, ww * 0.42, wh * 0.74),
            "stage_right": (wx + ww * 0.55, wy + wh * 0.10, ww * 0.42, wh * 0.74),
            "stage_mid": (wx + ww * 0.30, wy + wh * 0.10, ww * 0.40, wh * 0.74),
            "phone": (wx + ww * 0.36, wy + wh * 0.01, ww * 0.28, wh * 0.94),
            "phone_b": (wx + ww * 0.56, wy + wh * 0.10, ww * 0.22, wh * 0.76),
            "globe": (wx + ww * 0.18, wy + wh * 0.04, ww * 0.64, wh * 0.86),
            "tower": (wx + ww * 0.34, wy + wh * 0.02, ww * 0.30, wh * 0.92),
            "factory": (wx + ww * 0.08, wy + wh * 0.22, ww * 0.62, wh * 0.70),
            "caption_band": (wx, wy + wh * 0.86, ww, wh * 0.12),
            "upper_supers": (wx, wy + wh * 0.80, ww, wh * 0.12),
        }
        return s

    # ------------------------------------------------------------- background
    def background(self, p: Painter, ctx: RenderContext) -> None:
        st, pal = ctx.stage, ctx.palette
        p.gradient_rect(0, 0, st.width, st.height, pal["bg_top"], pal["bg_bottom"])
        # one cool key light from the upper right, one warm practical low left
        p.radial_rect(0, 0, st.width, st.height, with_alpha(pal["sky_glow"], 46),
                      with_alpha(pal["bg_top"], 0), cx=0.62, cy=0.18, power=1.5)
        p.radial_rect(0, 0, st.width, st.height, with_alpha(pal["accent"], 16),
                      with_alpha(pal["bg_top"], 0), cx=0.18, cy=0.78, power=1.9)
        self._skyline(p, ctx)
        # faint studio grid, mostly readable in the bottom third
        step = st.px(78)
        for i in range(1, 9):
            y = st.height * (0.42 + i * 0.065)
            p.line([(0, y), (st.width, y)], with_alpha(pal["cool"], 0.05), width=1)
        for i in range(-2, 22):
            x = i * step + (ctx.t * 2.5) % step
            p.line([(x, st.height * 0.42), (x, st.height)], with_alpha(pal["cool"], 0.035), width=1)

    def _skyline(self, p: Painter, ctx: RenderContext) -> None:
        """Two parallax city layers, cached as one sprite per layer."""
        st, pal = ctx.stage, ctx.palette
        for layer, (top_frac, col, seed, drift) in enumerate((
                (0.52, pal["ground_far"], 11, 0.6),
                (0.62, pal["ground"], 23, 1.4))):
            box = (0, st.height * top_frac, st.width, st.height)
            key = ("biz-skyline", st.width, st.height, layer, col, st.scale)

            def paint(img, ox, oy, s, top_frac=top_frac, col=col, seed=seed):
                from PIL import ImageDraw

                d = ImageDraw.Draw(img)
                rnd = random.Random(seed)
                x = 0.0
                ybase = st.height - oy
                ytop = st.height * top_frac - oy
                while x < st.width:
                    bw = st.px(rnd.uniform(34, 96))
                    bh = st.px(rnd.uniform(30, 120)) * (1.0 if layer else 0.8)
                    top = ybase - bh
                    if top < ytop:
                        top = ytop
                    d.rectangle([x, top, x + bw, ybase], fill=to_rgba(col))
                    # roof furniture
                    if rnd.random() < 0.35:
                        d.rectangle([x + bw * 0.35, top - st.px(9), x + bw * 0.5, top],
                                    fill=to_rgba(col))
                    # lit windows
                    if layer == 1:
                        rows = int((ybase - top) / st.px(16))
                        for r in range(rows):
                            for c in range(max(1, int(bw / st.px(15)))):
                                if rnd.random() < 0.28:
                                    wx = x + st.px(5) + c * st.px(15)
                                    wy = top + st.px(6) + r * st.px(16)
                                    d.rectangle([wx, wy, wx + st.px(5), wy + st.px(7)],
                                                fill=to_rgba(with_alpha(pal["accent"], 0.5)))
                    x += bw + st.px(rnd.uniform(2, 10))

            img, ox, oy = SPRITES.get(key, box, p.ss, paint)
            off = -drift * (ctx.t % 1e6) * 0.6
            p.paste_sprite(img, ox + off, oy, alpha=0.9)

    # ---------------------------------------------------------------- objects
    def draw_element(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        a = _shot(ctx, el)
        if a <= 0.002:
            return
        kind = el.get("type", "")
        fn = getattr(self, f"_el_{kind}", None)
        if fn is None:
            self.unknown_element(p, ctx, el)
        else:
            fn(p, ctx, el, a)

    def _el_skyline(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        return

    # -- phone ---------------------------------------------------------------
    def _el_phone(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        params = _params(el)
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "phone"))
        kind = str(params.get("kind", "touch"))
        aspect = 0.50 if kind == "classic" else 0.47
        ph = min(h, w / aspect)
        pw = ph * aspect
        # keep the phone inside the safe width
        if pw > w:
            pw, ph = w, w / aspect
        cx = x + w / 2
        rise = (1 - ease_out(a)) * ctx.stage.px(18)
        px0, py0 = cx - pw / 2, y + (h - ph) / 2 + rise

        # a slow float and a soft screen glow behind the device
        px0 += math.sin(ctx.t * 0.9) * ctx.stage.px(1.2)
        screen = str(params.get("screen", "blank"))
        glow = ctx.stage.px(26)
        p.glow(cx, py0 + ph * 0.45, ph * 0.46,
               with_alpha(ctx.col("cool"), 0.16 * a * (0.6 if screen == "blank" else 1.0)))
        img, ox, oy = props.phone(ctx.palette, p.ss, px0, py0, pw, ph, kind=kind, screen=screen)
        p.paste_sprite(img, ox, oy, alpha=a)
        self._phone_screen(p, ctx, px0, py0, pw, ph, kind, screen, a)

        if params.get("ring"):
            for i in range(3):
                u = (ctx.t * 0.55 + i / 3.0) % 1.0
                r = pw * (0.6 + 1.5 * u)
                p.ellipse(cx, py0 + ph * 0.45, r, r,
                          fill=None, outline=with_alpha(ctx.col("accent"), 0.22 * (1 - u) * a),
                          width=max(1.5, ctx.stage.px(2)))
        label = ctx.label(el)
        if label:
            self.label(p, ctx, cx, py0 + ph + ctx.stage.px(16), label,
                       size=ctx.stage.label_size(), bg=False, color=ctx.col("muted"), alpha=a)

    def _phone_screen(self, p: Painter, ctx: RenderContext, x: float, y: float, w: float,
                      h: float, kind: str, screen: str, a: float) -> None:
        sx0, sy0, sx1, sy1 = props.screen_box(x, y, w, h, kind)
        sw, sh = sx1 - sx0, sy1 - sy0
        if kind == "classic":
            ink = ctx.col("ink")
            p.rect(sx0, sy0, sx1, sy1, fill=with_alpha(mix(ink, ctx.col("glass"), 0.25), a),
                   radius=sw * 0.05)
            if screen == "call":
                self.label(p, ctx, sx0 + sw / 2, sy0 + sh * 0.34, "INCOMING", size=sw * 0.16,
                           bg=False, color=ctx.col("paper"), alpha=a * 0.9)
                self.label(p, ctx, sx0 + sw / 2, sy0 + sh * 0.60, "···", size=sw * 0.26,
                           bg=False, color=ctx.col("accent"), alpha=a)
            else:
                for i in range(3):
                    p.rect(sx0 + sw * 0.12, sy0 + sh * (0.24 + i * 0.20), sx0 + sw * 0.88,
                           sy0 + sh * (0.30 + i * 0.20),
                           fill=with_alpha(ctx.col("paper"), 0.5 * a), radius=2)
            # signal + battery bars in the corner
            for i in range(3):
                p.rect(sx0 + sw * 0.08 + i * sw * 0.05, sy0 + sh * 0.07 - i * 2,
                       sx0 + sw * 0.10 + i * sw * 0.05, sy0 + sh * 0.07,
                       fill=with_alpha(ctx.col("paper"), 0.7 * a))
            return
        # touch screen content
        p.rect(sx0, sy0, sx1, sy1, fill=with_alpha(ctx.col("ink"), 0.92 * a), radius=sw * 0.10)
        if screen == "apps":
            cols, rows = 4, 5
            probe = ctx.t
            for r in range(rows):
                for c in range(cols):
                    i = r * cols + c
                    u = clamp((probe - 0.25 - i * 0.06) * 2.2)
                    if u <= 0:
                        continue
                    iw = sw * 0.13
                    ix = sx0 + sw * (0.12 + c * 0.20)
                    iy = sy0 + sh * (0.10 + r * 0.135)
                    col = [ctx.col("accent"), ctx.col("cool"), ctx.col("accent3"),
                           ctx.col("accent2")][i % 4]
                    p.rect(ix, iy, ix + iw, iy + iw, fill=with_alpha(col, 0.9 * a * u),
                           radius=iw * 0.28)
            # dock
            p.rect(sx0 + sw * 0.08, sy1 - sh * 0.13, sx1 - sw * 0.08, sy1 - sh * 0.04,
                   fill=with_alpha(ctx.col("paper"), 0.10 * a), radius=sw * 0.05)
        elif screen == "sparse":
            for i in range(3):
                iw = sw * 0.15
                ix = sx0 + sw * (0.16 + i * 0.24)
                p.rect(ix, sy0 + sh * 0.16, ix + iw, sy0 + sh * 0.16 + iw,
                       fill=with_alpha(ctx.col("accent"), 0.55 * a), radius=iw * 0.26)
            self.label(p, ctx, sx0 + sw / 2, sy0 + sh * 0.52, "app store", size=sw * 0.13,
                       bg=False, color=ctx.col("muted"), alpha=a * 0.8)
            p.line([(sx0 + sw * 0.16, sy0 + sh * 0.62), (sx1 - sw * 0.16, sy0 + sh * 0.62)],
                   with_alpha(ctx.col("muted"), 0.3 * a), width=1)
            for i in range(3):
                p.rect(sx0 + sw * 0.16, sy0 + sh * (0.70 + i * 0.09), sx1 - sw * 0.16,
                       sy0 + sh * (0.74 + i * 0.09), fill=with_alpha(ctx.col("muted"), 0.18 * a),
                       radius=2)
        elif screen == "browser":
            p.rect(sx0, sy0, sx1, sy0 + sh * 0.10, fill=with_alpha(ctx.col("metal_dark"), 0.65 * a))
            p.rect(sx0 + sw * 0.08, sy0 + sh * 0.025, sx1 - sw * 0.08, sy0 + sh * 0.075,
                   fill=with_alpha(ctx.col("ink"), 0.8 * a), radius=sw * 0.03)
            for i in range(5):
                p.rect(sx0 + sw * 0.10, sy0 + sh * (0.16 + i * 0.10), sx0 + sw * (0.62 if i % 2 else 0.86),
                       sy0 + sh * (0.20 + i * 0.10), fill=with_alpha(ctx.col("paper"), 0.35 * a),
                       radius=2)
            p.rect(sx0 + sw * 0.10, sy0 + sh * 0.68, sx1 - sw * 0.10, sy0 + sh * 0.86,
                   fill=with_alpha(ctx.col("cool"), 0.25 * a), radius=3)
        elif screen == "call":
            p.rect(sx0, sy0, sx1, sy1, fill=with_alpha(shade(ctx.col("ink"), 1.1), a), radius=sw * 0.10)
            self.label(p, ctx, sx0 + sw / 2, sy0 + sh * 0.28, "INCOMING CALL", size=sw * 0.11,
                       bg=False, color=ctx.col("muted"), alpha=a * 0.9)
            for i in range(2):
                bx = sx0 + sw * (0.28 + i * 0.28)
                p.ellipse(bx, sy0 + sh * 0.74, sw * 0.075, sw * 0.075,
                          fill=with_alpha(ctx.col("accent") if i == 0 else ctx.col("accent2"),
                                          0.85 * a))
        else:  # blank / lock
            self.label(p, ctx, sx0 + sw / 2, sy0 + sh * 0.30, "9:41", size=sw * 0.30,
                       bg=False, color=ctx.col("paper"), alpha=a * 0.85)
            p.rect(sx0 + sw * 0.30, sy0 + sh * 0.44, sx1 - sw * 0.30, sy0 + sh * 0.445,
                   fill=with_alpha(ctx.col("muted"), 0.5 * a))

    # -- factory -------------------------------------------------------------
    def _el_factory(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "factory"))
        fh = h * 0.62
        fy = y + h - fh
        img, ox, oy = props.factory(ctx.palette, p.ss, x + w * 0.06, fy, w * 0.80, fh)
        p.paste_sprite(img, ox, oy, alpha=a)
        # chimney smoke: three puffs rising and fading
        cx = x + w * 0.06 + w * 0.80 * 0.80
        for i in range(3):
            u = (ctx.t * 0.28 + i / 3.0) % 1.0
            r = ctx.stage.px(10 + 26 * u)
            p.ellipse(cx + u * w * 0.10, fy - ctx.stage.px(6) - u * h * 0.32, r, r * 0.9,
                      fill=with_alpha(ctx.col("muted"), 0.16 * (1 - u) * a))
        label = ctx.label(el)
        if label:
            self.label(p, ctx, x + w * 0.46, fy - ctx.stage.px(16), label,
                       size=ctx.stage.label_size(), bg=False, color=ctx.col("muted"), alpha=a)

    # -- tower ---------------------------------------------------------------
    def _el_tower(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "tower"))
        th = h * 0.86
        img, ox, oy = props.tower(ctx.palette, p.ss, x + w * 0.2, y + h - th, w * 0.6, th,
                                  energy=0.5 + 0.5 * math.sin(ctx.t * 2.2))
        p.paste_sprite(img, ox, oy, alpha=a)
        # signal arcs leaving the antennas
        cx, cy = x + w * 0.5, y + h - th + th * 0.10
        for i in range(3):
            u = (ctx.t * 0.7 + i / 3.0) % 1.0
            r = w * (0.10 + 0.34 * u)
            p.arc(cx, cy, r, r * 0.55, 207.0, 333.0,
                  with_alpha(ctx.col("accent3"), 0.30 * (1 - u) * a), width=max(1.5, ctx.stage.px(2)))
        label = ctx.label(el)
        if label:
            self.label(p, ctx, cx, y + h + ctx.stage.px(10), label, size=ctx.stage.label_size(),
                       bg=False, color=ctx.col("muted"), alpha=a)

    # -- globe ---------------------------------------------------------------
    def _el_globe(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "globe"))
        r = min(w, h) * 0.44
        cx, cy = x + w / 2, y + h / 2
        pal = ctx.palette
        p.glow(cx, cy, r * 1.35, with_alpha(pal["cool"], 0.10 * a))
        p.ellipse(cx, cy, r, r, fill=with_alpha(mix(pal["ink"], pal["bg_bottom"], 0.35), 0.9 * a),
                  outline=with_alpha(pal["cool"], 0.35 * a), width=max(1.2, ctx.stage.px(1.4)))
        # graticule
        for i in range(1, 4):
            ry = r * (0.28 * i)
            p.arc(cx, cy, r * 0.98, ry, 180, 360, with_alpha(pal["cool"], 0.16 * a), width=1)
            p.arc(cx, cy, r * 0.98, ry, 0, 180, with_alpha(pal["cool"], 0.10 * a), width=1)
        for i in range(1, 5):
            p.arc(cx, cy, r * (i / 5.0), r, 90, 270, with_alpha(pal["cool"], 0.12 * a), width=1)
            p.arc(cx, cy, r * (i / 5.0), r, 270, 450, with_alpha(pal["cool"], 0.08 * a), width=1)
        p.ellipse(cx, cy, r * 0.98, r * 0.98, fill=None,
                  outline=with_alpha(pal["cool"], 0.28 * a), width=max(1.2, ctx.stage.px(1.5)))
        # land dots on a fixed pseudo-random set of visible points
        rnd = random.Random(7)
        reveal = ease_out(clamp(ctx.t / 1.6))
        pts = []
        for _ in range(46):
            ang = rnd.uniform(0, math.tau)
            rr = r * math.sqrt(rnd.uniform(0.05, 1.0))
            px, py = cx + math.cos(ang) * rr, cy + math.sin(ang) * rr * 0.98
            pts.append((px, py, rr))
        for px, py, rr in pts:
            if rr / r > reveal + 0.15:
                continue
            p.ellipse(px, py, ctx.stage.px(1.9), ctx.stage.px(1.9),
                      fill=with_alpha(pal["accent3"], 0.55 * a))
        # arcs between three "cities", with travelling packets
        cities = [(cx - r * 0.45, cy - r * 0.18), (cx + r * 0.30, cy - r * 0.42),
                  (cx + r * 0.48, cy + r * 0.26), (cx - r * 0.12, cy + r * 0.52)]
        for i in range(len(cities) - 1):
            a0, b0 = cities[i], cities[i + 1]
            mx, my = (a0[0] + b0[0]) / 2, (a0[1] + b0[1]) / 2 - r * 0.22
            path = []
            for k in range(19):
                u = k / 18.0
                bx = (1 - u) ** 2 * a0[0] + 2 * (1 - u) * u * mx + u ** 2 * b0[0]
                by = (1 - u) ** 2 * a0[1] + 2 * (1 - u) * u * my + u ** 2 * b0[1]
                path.append((bx, by))
            p.line(path, with_alpha(pal["accent"], 0.55 * a), width=max(1.2, ctx.stage.px(1.6)))
            flow_dots(p, path, t=ctx.t + i * 0.37, color=with_alpha(pal["accent3"], a),
                      count=2, speed=0.55, radius=ctx.stage.px(2.2))
            p.ellipse(a0[0], a0[1], ctx.stage.px(3.2), ctx.stage.px(3.2),
                      fill=with_alpha(pal["paper"], 0.9 * a))
        p.ellipse(cities[-1][0], cities[-1][1], ctx.stage.px(3.2), ctx.stage.px(3.2),
                  fill=with_alpha(pal["paper"], 0.9 * a))
        label = ctx.label(el)
        if label:
            self.label(p, ctx, cx, cy + r + ctx.stage.px(24), label, size=ctx.stage.label_size(),
                       bg=False, color=ctx.col("muted"), alpha=a)

    # -- chart ---------------------------------------------------------------
    def _el_chart(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        params = _params(el)
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "wide"))
        empty = str(params.get("mode", "")) == "empty"
        values: Sequence[float] = params.get("values") or []
        labels: Sequence[str] = params.get("labels") or []
        caption = ctx.label(el)
        mode = str(params.get("mode", "line"))
        pal = ctx.palette
        # card
        card = (x + w * 0.02, y + h * 0.02, x + w * 0.98, y + h * 0.98)
        p.rect(*card, fill=with_alpha(pal["ink"], 0.55 * a), radius=ctx.stage.px(14),
               outline=with_alpha(pal["cool"], 0.22 * a), width=1.5)
        pad_x, pad_top, pad_bot = w * 0.09, h * 0.22, h * 0.16
        gx0, gx1 = x + pad_x, x + w - pad_x * 0.7
        gy0, gy1 = y + pad_top, y + h - pad_bot
        for i in range(4):
            yy = gy0 + (gy1 - gy0) * i / 3.0
            p.line([(gx0, yy), (gx1, yy)], with_alpha(pal["muted"], 0.14 * a), width=1)
        if empty or len(values) < 2:
            # never invent a trend: say so on the card instead
            self.label(p, ctx, (gx0 + gx1) / 2, (gy0 + gy1) / 2,
                       "no figures in the script", size=ctx.stage.label_size(),
                       bg=False, color=ctx.col("muted"), alpha=a * 0.9)
            if caption:
                self.label(p, ctx, gx0, y + h * 0.10, caption, size=ctx.stage.label_size(),
                           bg=False, color=ctx.col("text"), align="left", alpha=a,
                           max_width=w * 0.8)
            return
        n = max(2, len(values))
        pts = []
        progress = ease_in_out(clamp(ctx.t / max(1.2, ctx.duration * 0.45)))
        for i, v in enumerate(values):
            px = gx0 + (gx1 - gx0) * i / (n - 1)
            py = gy1 - (gy1 - gy0) * max(0.02, min(1.0, float(v)))
            pts.append((px, py))
        show = max(2, int(round(progress * n)))
        drawn = pts[:show]
        if mode == "bars":
            bw = (gx1 - gx0) / n * 0.55
            for i, (px, py) in enumerate(drawn):
                p.rect(px - bw / 2, py, px + bw / 2, gy1,
                       fill=with_alpha(pal["accent"], 0.75 * a), radius=bw * 0.2)
        else:
            if len(drawn) >= 2:
                # area fill under the line
                poly = drawn + [(drawn[-1][0], gy1), (drawn[0][0], gy1)]
                p.polygon(poly, fill=with_alpha(pal["accent"], 0.12 * a))
                p.line(drawn, with_alpha(pal["accent"], 0.95 * a), width=max(2.0, ctx.stage.px(3)))
                for px, py in drawn:
                    p.ellipse(px, py, ctx.stage.px(3.4), ctx.stage.px(3.4),
                              fill=with_alpha(pal["paper"], 0.9 * a))
        for i, lab in enumerate(labels[:n]):
            px = gx0 + (gx1 - gx0) * i / (n - 1)
            self.label(p, ctx, px, gy1 + ctx.stage.px(18), str(lab),
                       size=ctx.stage.label_size() * 0.8, bg=False,
                       color=ctx.col("muted"), alpha=a * 0.9)
        if caption:
            self.label(p, ctx, gx0, y + h * 0.10, caption, size=ctx.stage.label_size(),
                       bg=False, color=ctx.col("text"), align="left", alpha=a,
                       max_width=w * 0.7)
        if params.get("illustrative", True):
            self.label(p, ctx, gx1, y + h * 0.10, "illustrative", size=ctx.stage.kicker_size(),
                       bg=False, color=ctx.col("muted"), align="right", alpha=a * 0.7)

    # -- timeline ------------------------------------------------------------
    def _el_timeline(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        params = _params(el)
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "wide"))
        years: List[str] = [str(v) for v in (params.get("years") or ["2007", "2010", "2013", "2014"])]
        notes: List[str] = [str(v) for v in (params.get("notes") or [""] * len(years))]
        pal = ctx.palette
        n = len(years)
        yline = y + h * 0.58
        x0, x1 = x + w * 0.06, x + w * 0.94
        p.line([(x0, yline), (x1, yline)], with_alpha(pal["muted"], 0.30 * a),
               width=max(2.0, ctx.stage.px(2.5)))
        head = ease_in_out(clamp(ctx.t / max(1.0, ctx.duration * 0.55)))
        p.line([(x0, yline), (x0 + (x1 - x0) * head, yline)],
               with_alpha(pal["accent"], 0.95 * a), width=max(2.0, ctx.stage.px(2.5)))
        for i, (year, note) in enumerate(zip(years, notes)):
            u = stagger(head, i, n, 0.8)
            if u <= 0.01:
                continue
            px = x0 + (x1 - x0) * i / max(1, n - 1)
            active = u >= 1.0
            r = ctx.stage.px(7 if active else 5)
            p.ellipse(px, yline, r, r, fill=with_alpha(pal["accent"] if active else pal["muted"], a))
            p.ellipse(px, yline, r * 2.1, r * 2.1, fill=None,
                      outline=with_alpha(pal["accent"], 0.28 * a * u), width=1.5)
            self.label(p, ctx, px, yline - ctx.stage.px(24), year,
                       size=ctx.stage.headline_size() * 0.42 if n <= 4 else ctx.stage.label_size() * 1.3,
                       bg=False, color=ctx.col("text"), alpha=a * u)
            if note:
                self.label(p, ctx, px, yline + ctx.stage.px(30), note,
                           size=ctx.stage.label_size() * 0.82, bg=False,
                           color=ctx.col("muted"), alpha=a * u, max_width=(x1 - x0) / n * 1.05)
        label = ctx.label(el)
        if label:
            self.label(p, ctx, x + w * 0.06, y + h * 0.12, label, size=ctx.stage.label_size(),
                       bg=False, color=ctx.col("text"), align="left", alpha=a)

    # -- stat ----------------------------------------------------------------
    def _el_stat(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        params = _params(el)
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "hero"))
        value = str(params.get("value", "—"))
        caption = ctx.label(el)
        pal = ctx.palette
        cx, cy = x + w / 2, y + h / 2
        u = ease_out(clamp(ctx.t / 0.9))
        # hairline rules either side of the figure
        rw = w * 0.30 * u
        p.line([(cx - rw - w * 0.05, cy - h * 0.16), (cx - w * 0.05, cy - h * 0.16)],
               with_alpha(pal["accent"], 0.8 * a), width=max(1.5, ctx.stage.px(2)))
        p.line([(cx + w * 0.05, cy - h * 0.16), (cx + rw + w * 0.05, cy - h * 0.16)],
               with_alpha(pal["accent"], 0.8 * a), width=max(1.5, ctx.stage.px(2)))
        size = min(ctx.stage.headline_size() * 2.1, w * 0.26)
        self.label(p, ctx, cx, cy, value, size=size, bg=False, color=pal["text"], alpha=a * u)
        if caption:
            self.label(p, ctx, cx, cy + h * 0.26, caption, size=ctx.stage.label_size() * 1.05,
                       bg=False, color=ctx.col("muted"), alpha=a, max_width=w * 0.9)

    # -- ecosystem -----------------------------------------------------------
    def _el_ecosystem(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        params = _params(el)
        slot = el.get("slot", "wide")
        vertical = ctx.stage.format == "vertical"
        if vertical and slot == "wide":
            slot = "tall"
        x, y, w, h = self.slot(ctx.stage, slot)
        hub = ctx.pick(str(params.get("hub", "platform")), str(params.get("hub_ur", "پلیٹ فارم")))
        nodes = ctx.labels(el, "nodes") or ["users", "apps", "developers", "devices"]
        pal = ctx.palette
        cx, cy = x + w / 2, y + h / 2
        rx, ry = (w * 0.27, h * 0.33) if vertical else (w * 0.30, h * 0.30)
        appear = ease_out(clamp(ctx.t / 1.0))
        n = len(nodes)
        for i in range(n):
            ang = -math.pi / 2 + math.tau * i / n + ctx.t * 0.06
            u = stagger(appear, i, n, 0.8)
            if u <= 0.01:
                continue
            nx, ny = cx + math.cos(ang) * rx, cy + math.sin(ang) * ry
            p.line([(cx, cy), (nx, ny)], with_alpha(pal["cool"], 0.28 * a * u),
                   width=max(1.2, ctx.stage.px(1.6)))
            flow_dots(p, [(cx, cy), (nx, ny)], t=ctx.t + i * 0.3,
                      color=with_alpha(pal["accent3"], a * u), count=1, speed=0.6,
                      radius=ctx.stage.px(2))
            r = ctx.stage.px(9)
            p.ellipse(nx, ny, r, r, fill=with_alpha(pal["ink"], 0.9 * a),
                      outline=with_alpha(pal["accent3"], 0.7 * a * u), width=2)
            # label on the outside of the orbit: a left-hand node labelled to its
            # right writes straight through the hub.  If "outside" would leave the
            # safe area, the label goes above the node instead of being clamped on
            # top of it.
            left = nx < cx
            lsize = ctx.stage.label_size() * 0.9
            style = TextStyle(size=lsize, language=ctx.language, role="small", align="left")
            tw = (ctx.renderer.layout(nodes[i], style, ctx.stage.content_w).width
                  if ctx.renderer else lsize * 4)
            safe_l, safe_r = ctx.stage.safe_x, ctx.stage.width - ctx.stage.safe_x
            if left:
                lx, ly, align = nx - r * 1.6, ny, "right"
                fits = lx - tw >= safe_l
            else:
                lx, ly, align = nx + r * 1.6, ny, "left"
                fits = lx + tw <= safe_r
            if not fits:
                lx, ly, align = nx, ny - r * 2.4, "center"
            self.label(p, ctx, lx, ly, nodes[i],
                       size=lsize, bg=False, color=ctx.col("text"),
                       align=align, alpha=a * u,
                       max_width=w * 0.26)
        p.ellipse(cx, cy, ctx.stage.px(34), ctx.stage.px(34),
                  fill=with_alpha(pal["accent"], 0.12 * a),
                  outline=with_alpha(pal["accent"], 0.8 * a), width=2)
        self.label(p, ctx, cx, cy, hub, size=ctx.stage.label_size() * 0.95, bg=False,
                   color=ctx.col("text"), alpha=a)

    # -- two phones ----------------------------------------------------------
    def _el_compare_phones(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "wide"))
        ph = h * 0.80
        specs = (("classic", "keypad", ctx.pick("2007", "2007")),
                 ("touch", "apps", ctx.pick("today", "آج")))
        for i, (kind, screen, caption) in enumerate(specs):
            pw = ph * (0.50 if kind == "classic" else 0.47)
            cx = x + w * (0.30 if i == 0 else 0.70)
            py0 = y + (h - ph) / 2
            img, ox, oy = props.phone(ctx.palette, p.ss, cx - pw / 2, py0, pw, ph,
                                      kind=kind, screen=screen)
            p.paste_sprite(img, ox, oy, alpha=a)
            self._phone_screen(p, ctx, cx - pw / 2, py0, pw, ph, kind, screen, a)
            self.label(p, ctx, cx, py0 + ph + ctx.stage.px(14), caption,
                       size=ctx.stage.label_size(), bg=False, color=ctx.col("muted"), alpha=a)
        p.line([(x + w * 0.5, y + h * 0.14), (x + w * 0.5, y + h * 0.86)],
               with_alpha(ctx.col("muted"), 0.22 * a), width=1)

    # -- big statement -------------------------------------------------------
    def _el_statement(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        """A typographic beat: one spoken sentence, set as picture.

        With one picture per sentence and no picture ever repeated, most beats of
        a documentary are type.  A single centred layout repeated thirty times
        reads as a slideshow, so there are three compositions - centred with a
        rule, left-aligned against an accent bar, and a held panel - each with a
        faint motif behind it.  Short sentences are set big; long ones shrink to
        fit rather than being clipped.
        """
        from ...gfx.primitives import fit_text
        from ...text.shaping import TextStyle

        vertical = ctx.stage.format != "landscape"
        W, H = ctx.stage.width, ctx.stage.height
        if vertical:
            # In 9:16 a typographic beat owns the middle of the frame: the other
            # slots are bands sized for a prop plus a caption, and a sentence set
            # in a 10%-tall strip shrinks to something nobody can read on a phone.
            x, y, w, h = W * 0.06, H * 0.17, W * 0.88, H * 0.44
        else:
            # Stop above the super band, which docks over the caption band at the
            # bottom: a card and the writer's on-screen text must not fight.
            sx, _sy, sw, _sh = self.slot(ctx.stage, el.get("slot", "wide"))
            x, y, w, h = sx, H * 0.06, sw, H * 0.58
        text = ctx.label(el)
        if not text:
            return
        variant = int(_params(el).get("variant", 0) or 0) % 3
        st = ctx.stage
        cx, cy = x + w / 2, y + h * 0.5
        accent = ctx.col("accent")
        cool = ctx.col("cool")
        rise = (1 - ease_out(min(1.0, a))) * st.px(10)
        cy += rise

        big = (min(st.px(64), w * 0.125) if vertical
               else min(st.px(74), w * 0.145))
        role = "headline"
        max_w = w * (0.80 if not vertical else 0.86)
        color = ctx.col("text")

        if variant == 0:
            self._motif_arcs(p, ctx, cx, cy, w, h, a)
            lay, style = fit_text(ctx.renderer, ctx.language, text,
                                  TextStyle(size=big, language=ctx.language, role=role,
                                            align="center"),
                                  max_w, h * 0.62, max_lines=4)
            x0 = cx - lay.width / 2
            y0 = cy - lay.height / 2
            ctx.renderer.draw_layout(p, lay, style, (x0, y0), with_alpha(color, a))
            uw = w * 0.10 * ease_out(clamp(ctx.t / 0.8))
            ry = y0 + lay.height + st.px(20)
            p.rect(cx - uw, ry, cx + uw, ry + max(1.5, st.px(2.4)),
                   fill=with_alpha(accent, 0.9 * a))
        elif variant == 1:
            self._motif_rules(p, ctx, x, y, w, h, a)
            lay, style = fit_text(ctx.renderer, ctx.language, text,
                                  TextStyle(size=big * 0.94, language=ctx.language, role=role,
                                            align="left"),
                                  w * 0.72, h * 0.64, max_lines=4)
            x0 = x + w * 0.10
            y0 = cy - lay.height / 2
            bar = x0 - st.px(16)
            p.rect(bar, y0 - st.px(6), bar + max(2.0, st.px(4)), y0 + lay.height + st.px(6),
                   fill=with_alpha(accent, 0.95 * a))
            ctx.renderer.draw_layout(p, lay, style, (x0, y0), with_alpha(color, a))
        else:
            self._motif_dots(p, ctx, x, y, w, h, a)
            lay, style = fit_text(ctx.renderer, ctx.language, text,
                                  TextStyle(size=big * 0.88, language=ctx.language, role=role,
                                            align="center"),
                                  w * 0.70, h * 0.60, max_lines=4)
            pad_x, pad_y = st.px(34), st.px(24)
            panel = (cx - lay.width / 2 - pad_x, cy - lay.height / 2 - pad_y,
                     cx + lay.width / 2 + pad_x, cy + lay.height / 2 + pad_y)
            p.rect(panel[0], panel[1], panel[2], panel[3],
                   fill=with_alpha(ctx.col("ink"), 0.62 * a),
                   outline=with_alpha(cool, 0.30 * a), width=max(1.0, st.px(1.2)),
                   radius=st.px(10))
            ctx.renderer.draw_layout(p, lay, style,
                                     (cx - lay.width / 2, cy - lay.height / 2), with_alpha(color, a))

    # -- card motifs: three quiet backdrops so the type never looks repeated --
    @staticmethod
    def _motif_arcs(p: Painter, ctx: RenderContext, cx: float, cy: float,
                    w: float, h: float, a: float) -> None:
        st = ctx.stage
        for i in range(3):
            r = w * (0.10 + i * 0.055)
            p.ellipse(cx, cy, r, r * 0.62, outline=with_alpha(ctx.col("cool"), (0.10 - i * 0.02) * a),
                      width=max(1.0, st.px(1.2)))

    @staticmethod
    def _motif_rules(p: Painter, ctx: RenderContext, x: float, y: float,
                     w: float, h: float, a: float) -> None:
        st = ctx.stage
        for i in range(7):
            lx = x + w * (0.04 + i * 0.135)
            p.rect(lx, y + h * 0.18, lx + max(1.0, st.px(1.2)), y + h * 0.82,
                   fill=with_alpha(ctx.col("cool"), 0.07 * a))

    @staticmethod
    def _motif_dots(p: Painter, ctx: RenderContext, x: float, y: float,
                    w: float, h: float, a: float) -> None:
        st = ctx.stage
        r = max(1.2, st.px(1.6))
        for row in range(3):
            for col in range(9):
                dx = x + w * (0.08 + col * 0.105)
                dy = y + h * (0.24 + row * 0.26)
                p.ellipse(dx, dy, r, r, fill=with_alpha(ctx.col("cool"), 0.13 * a))

    # -- on-screen text (the script's ON-SCREEN TEXT block) ------------------
    def _el_lower_third(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        """Documentary lower-third: the writer's on-screen text, on a scrim.

        It sits in the lower-left, above the caption band, and carries its own
        dark panel - supers are allowed to sit over the picture, but they must
        never be *unreadable* against a busy prop, so the panel is not optional.
        """
        lines: List[str] = [t for t in (ctx.labels(el, "lines") or []) if t]
        if not lines:
            return
        st, pal = ctx.stage, ctx.palette
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "upper_supers"))
        size = st.px(24 if st.format == "landscape" else 18)
        max_w = st.content_w * (0.66 if st.format == "landscape" else 0.88)
        rows = []
        # three supers are the writer's, not ours: keep all of them in both
        # formats and let the panel grow upwards instead of dropping a line
        for i, text in enumerate(lines[:3]):
            u = a * clamp((ctx.t - 0.1 - i * 0.16) * 2.2)
            if u <= 0.01:
                continue
            lay, style = self._fit(ctx, text, size, max_w)
            rows.append((lay, style, u))
        if not rows:
            return
        block_h = sum(lay.height for lay, _s, _u in rows) + st.px(10) * (len(rows) - 1)
        # dock immediately above the caption band: clear of the subject (which is
        # centred in the picture) and clear of the captions themselves
        bottom = min(st.caption_area[1] - st.px(10), y + h)
        if st.format == "vertical":
            # in 9:16 the caption band starts where the picture band ends, so the
            # block grows upwards and must stop below the headline
            floor = st.headline_area[1] + st.headline_area[3] + st.px(18)
            bottom = max(bottom, min(bottom, floor + block_h))
        top = bottom - block_h
        widest = max(lay.width for lay, _s, _u in rows)
        pad = st.px(16)
        # two passes: a soft halo that lifts the panel off a busy prop, then the
        # panel itself.  A single 0.66 layer let lit factory windows read straight
        # through the writer's text.
        p.rect(st.safe_x - pad * 0.9, top - pad * 1.0,
               st.safe_x + widest + pad * 1.4, bottom + pad * 1.0,
               fill=with_alpha(pal["ink"], 0.34 * rows[0][2]), radius=st.px(14))
        p.rect(st.safe_x - pad * 0.5, top - pad * 0.7,
               st.safe_x + widest + pad, bottom + pad * 0.7,
               fill=with_alpha(pal["ink"], 0.93 * rows[0][2]), radius=st.px(8))
        p.rect(st.safe_x - pad * 0.5, top - pad * 0.7, st.safe_x - pad * 0.5 + st.px(2.6),
               bottom + pad * 0.7, fill=with_alpha(pal["accent"], 0.95 * rows[0][2]))
        cy = top
        for lay, style, u in rows:
            ctx.renderer.draw_layout(p, lay, style, (st.safe_x + st.px(10), cy),
                                     with_alpha(pal["paper"], u))
            cy += lay.height + st.px(10)

    @staticmethod
    def _fit(ctx: RenderContext, text: str, size: float, max_w: float):
        """Shrink to one or two lines that fit `max_w` (never overflow the frame)."""
        from ...text.render import TextRenderer  # noqa: F401  (type only)

        style = TextStyle(size=size, language=ctx.language, role="small", align="left")
        lay = ctx.renderer.layout(text, style, max_w)
        while lay.width > max_w + 0.5 and style.size > size * 0.62:
            style = TextStyle(**{**style.__dict__, "size": style.size * 0.94})
            lay = ctx.renderer.layout(text, style, max_w)
        return lay, style

    def _el_label(self, p: Painter, ctx: RenderContext, el: Dict, a: float) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "caption_band"))
        text = ctx.label(el)
        if text:
            self.label(p, ctx, x + w / 2, y + h / 2, text, alpha=a)

    # ------------------------------------------------------------ foreground
    def foreground(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        rnd = random.Random(31)
        for i in range(16):
            bx = rnd.random() * st.width
            by = (rnd.random() * st.height + ctx.t * (3 + rnd.random() * 7)) % st.height
            p.ellipse(bx, by, 1.6, 1.6, fill=with_alpha(ctx.col("paper"), 0.10))
        self.atmosphere(p, ctx, 0.3)
