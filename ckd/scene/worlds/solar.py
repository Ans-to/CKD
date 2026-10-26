"""Solar-energy visual world.

Parametric objects: sun with animated rays, house, rooftop PV array, exploded
cell layer stack, electron flow, inverter with DC->AC waveform, battery, grid
pylon, efficiency/heat split.  Nothing here is a finished scene - the planner
decides which objects appear and which actions play.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Sequence, Tuple

from ...gfx.painter import Painter, mix, rgba, shade, with_alpha
from ...gfx.primitives import (
    arrow, bezier_points, clamp, clouds, dashed_line, ease_in_out, ease_out, flow_dots, ground_band,
    hill, lerp, packet, pixel_grid, sag_curve, signal_wave, stagger, stars, sun, wave_arcs, wobble,
)
from ..stage import Box, Stage
from . import solar_props
from .base import RenderContext, World


class SolarWorld(World):
    id = "solar"
    palette_name = "warm"
    element_types = (
        "sky", "sun", "house", "panel", "label", "layer_stack", "electrons", "inverter",
        "wire", "waveform", "battery", "grid", "efficiency_bar", "heat_arrows", "array",
        "caption", "arrow",
    )

    # ----------------------------------------------------------------- layout
    def slots(self, stage: Stage) -> Dict[str, Box]:
        """Disjoint prop regions.

        Every named box is used by at most one prop per scene, so two objects can
        never land on each other.  The composer assigns slots by name; unknown
        names would all fall back to a single centred box, which is why every prop
        used by the knowledge base has a real entry here.
        """
        wx, wy, ww, wh = stage.world_area
        s: Dict[str, Box] = {}

        def frac(fx: float, fy: float, fw: float, fh: float) -> Box:
            return (wx + ww * fx, wy + wh * fy, ww * fw, wh * fh)

        if stage.format == "vertical":
            # 9:16 is composed as two zones: a wide prop band across the top, and
            # the lower-right quadrant beside the presenter.  Placed in stage
            # coordinates (not one shallow strip) so props get real room without
            # ever landing on the character.
            W, H = float(stage.width), float(stage.height)
            s["back"] = (0, H * 0.245, W, H * 0.56)
            s["sun"] = (W * 0.64, H * 0.245, W * 0.30, H * 0.15)
            s["house"] = (W * 0.07, H * 0.285, W * 0.54, H * 0.245)
            s["roof"] = (W * 0.11, H * 0.245, W * 0.46, H * 0.095)
            s["panel_label"] = (W * 0.56, H * 0.545, W * 0.41, H * 0.045)
            s["stage"] = (W * 0.03, H * 0.245, W * 0.94, H * 0.545)
            s["stage_left"] = (W * 0.055, H * 0.255, W * 0.415, H * 0.215)
            s["stage_mid"] = (W * 0.52, H * 0.255, W * 0.20, H * 0.215)
            s["stage_right"] = (W * 0.74, H * 0.245, W * 0.20, H * 0.225)
            s["grid"] = (W * 0.74, H * 0.245, W * 0.20, H * 0.30)
            s["house_small"] = (W * 0.52, H * 0.48, W * 0.42, H * 0.245)
            s["bar"] = (W * 0.03, H * 0.245, W * 0.94, H * 0.155)
            s["array"] = (W * 0.46, H * 0.44, W * 0.48, H * 0.22)
            s["stack"] = (W * 0.03, H * 0.245, W * 0.72, H * 0.29)
            s["circuit"] = (W * 0.04, H * 0.25, W * 0.92, H * 0.30)
            s["wire"] = (W * 0.20, H * 0.36, W * 0.60, H * 0.12)
            s["wave"] = (W * 0.05, H * 0.58, W * 0.90, H * 0.14)
            s["wave_band"] = (W * 0.06, H * 0.80, W * 0.88, H * 0.08)
            s["caption_band"] = (W * 0.04, H * 0.585, W * 0.92, H * 0.07)
        else:
            s["back"] = (wx, wy, ww, wh)
            s["sun"] = (wx + ww * 0.74, wy + wh * 0.02, ww * 0.19, wh * 0.34)
            s["house"] = (wx + ww * 0.52, wy + wh * 0.34, ww * 0.36, wh * 0.56)
            s["roof"] = (wx + ww * 0.50, wy + wh * 0.22, ww * 0.38, wh * 0.26)
            s["panel_label"] = (wx + ww * 0.52, wy + wh * 0.93, ww * 0.30, wh * 0.10)
            s["stage"] = (wx + ww * 0.02, wy + wh * 0.06, ww * 0.94, wh * 0.82)
            s["stage_left"] = frac(0.00, 0.10, 0.32, 0.62)
            s["stage_mid"] = frac(0.35, 0.14, 0.18, 0.54)
            s["stage_right"] = frac(0.55, 0.10, 0.18, 0.62)
            s["grid"] = frac(0.755, 0.02, 0.205, 0.72)
            s["house_small"] = frac(0.755, 0.36, 0.205, 0.60)
            s["bar"] = frac(0.00, 0.24, 0.64, 0.36)
            s["array"] = frac(0.675, 0.04, 0.285, 0.84)
            s["stack"] = (wx + ww * 0.06, wy + wh * 0.06, ww * 0.64, wh * 0.80)
            s["circuit"] = (wx + ww * 0.44, wy + wh * 0.30, ww * 0.40, wh * 0.50)
            s["wire"] = (wx + ww * 0.16, wy + wh * 0.40, ww * 0.52, wh * 0.24)
            s["wave"] = (wx + ww * 0.40, wy + wh * 0.58, ww * 0.46, wh * 0.24)
            s["wave_band"] = (wx + ww * 0.06, wy + wh * 0.80, ww * 0.88, wh * 0.16)
            s["caption_band"] = (wx + ww * 0.04, wy + wh * 0.84, ww * 0.92, wh * 0.14)
        # aliases: a wire may name the prop it links; resolve to that prop's box
        s["panel"] = s["stage_left"]
        s["inverter"] = s["stage_right"]
        s["battery"] = s["stage_mid"]
        s["field"] = s["array"]
        s["meter"] = s["bar"]
        return s

    # ------------------------------------------------------------- background
    def background(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        pal = ctx.palette
        wx, wy, ww, wh = st.world_area
        horizon = wy + wh * 0.62
        # sky + ridges + ground are static per format: paint once, paste every frame
        img, ox, oy = solar_props.backdrop(st.width, st.height, horizon, pal, p.ss)
        p.paste_sprite(img, ox, oy)

        # dust motes catching the light (cheap, adds depth over the plate)
        rnd = random.Random(7)
        for i in range(20):
            mx = (rnd.random() * 1.10 - 0.05) * st.width
            my = wy + rnd.random() * (st.height - wy)
            tw = 0.5 + 0.5 * math.sin(ctx.t * 1.3 + i * 2.1)
            p.ellipse(mx, my, st.px(1.4), st.px(1.4),
                      fill=with_alpha(pal["accent3"], 0.08 + 0.16 * tw))
        # a soft light shaft from the sun.  Only in 16:9: at 9:16 the narrow frame
        # turns it into a hard vertical seam down the right edge.
        if st.format == "landscape":
            shaft_x = st.width * 0.74
            for k in range(5):
                spread = 0.018 + k * 0.014
                a = (0.026 - k * 0.004) * (0.85 + 0.15 * math.sin(ctx.t * 0.8 + k))
                p.polygon([(shaft_x - st.width * spread * 0.5, wy + wh * 0.02),
                           (shaft_x + st.width * spread * 0.5, wy + wh * 0.02),
                           (shaft_x + st.width * (spread * 2.2 + 0.03), st.height),
                           (shaft_x + st.width * (spread * 0.9 + 0.01), st.height)],
                          fill=with_alpha(pal["accent3"], max(0.0, a)))

    # ---------------------------------------------------------------- objects
    def _el_sky(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        st = ctx.stage
        # keep clouds out of the headline band so type stays readable
        top = st.headline_area[1] + st.headline_area[3] + st.px(6)
        clouds(p, (0, top, st.width, max(st.px(40), st.height * 0.24)), ctx.t, ctx.col("paper"),
               count=3, seed=7)

    def _el_sun(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "sun"))
        pal = ctx.palette
        rise = ease_out(ctx.progress("sun_rise"))
        cx = x + w * 0.5
        cy = y + h * (0.85 - 0.45 * rise)
        r = min(w, h) * 0.24
        if ctx.progress("sun_rise") <= 0.0:
            r *= 0.6
        # the sun moves, so it is drawn live rather than cached as a sprite
        for mult, a in ((3.4, 0.07), (2.2, 0.11), (1.5, 0.18)):
            p.ellipse(cx, cy, r * mult, r * mult, fill=with_alpha(pal["accent3"], a))
        if rise > 0.2:
            for i in range(12):
                ang = i * math.pi / 6 + ctx.t * 0.05
                l0, l1 = r * 1.22, r * (1.55 + 0.08 * math.sin(ctx.t * 1.5 + i))
                p.line([(cx + math.cos(ang) * l0, cy + math.sin(ang) * l0),
                        (cx + math.cos(ang) * l1, cy + math.sin(ang) * l1)],
                       with_alpha(pal["accent3"], 0.40), width=max(1.5, r * 0.08))
        p.ellipse(cx, cy, r, r, fill=with_alpha(pal["accent3"], 0.98))
        p.ellipse(cx - r * 0.10, cy - r * 0.14, r * 0.84, r * 0.80,
                  fill=with_alpha(mix(pal["accent3"], pal["paper"], 0.55), 0.55))

        # rays travelling to the panel
        ray_p = ctx.progress("rays_travel")
        if ray_p > 0:
            tx, ty, tw, th = self.slot(ctx.stage, "roof")
            for i in range(9):
                u = (i / 8.0)
                sx = cx + (u - 0.5) * r * 2.4
                sy = cy + r * 0.9
                ex = tx + tw * (0.15 + 0.7 * u)
                ey = ty + th * 0.72
                t0 = stagger(ray_p, i, 9, 0.75)
                if t0 <= 0:
                    continue
                a = math.sin(math.pi * t0) ** 0.6
                mid = ((sx + ex) / 2 + 12 * math.sin(i), (sy + ey) / 2 - 8)
                pts = bezier_points((sx, sy), mid, mid, (ex, ey), 8)
                k = max(2, int(len(pts) * t0))
                p.line(pts[:k], with_alpha(pal["accent3"], 0.85 * a), width=max(2.0, r * 0.06))
                if t0 > 0.5:
                    p.ellipse(ex, ey, 3.2, 3.2, fill=with_alpha(pal["accent3"], a))

    def _el_house(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "house"))
        night = ctx.progress("night_glow")
        build_p = ctx.progress("build_bridge")
        build = ease_out(build_p) if build_p else 1.0
        img, ox, oy = solar_props.house(ctx.palette, p.ss, x, y, w, h,
                                        glow=0.30 + 0.70 * night, build=build)
        p.paste_sprite(img, ox, oy)

    def _el_panel(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        params = el.get("params", {})
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        rows = int(params.get("rows", 3))
        cols = int(params.get("cols", 4))
        glow = ease_in_out(ctx.progress("panel_glow"))
        photons = ctx.progress("photons_hit")
        img, ox, oy = solar_props.panel(ctx.palette, p.ss, x, y, w, h, rows=rows, cols=cols,
                                        glow=glow, legs=bool(params.get("legs")))
        p.paste_sprite(img, ox, oy)
        # photons landing on the array: a short sparkle burst, drawn live
        if photons > 0:
            for i in range(rows * cols):
                t0 = stagger(photons, i, rows * cols, 0.55)
                if t0 <= 0:
                    continue
                r_, c_ = divmod(i, cols)
                px_ = x + w * (0.14 + 0.68 * (c_ + 0.5) / cols)
                py_ = y + h * (0.24 + 0.42 * (r_ + 0.5) / rows)
                a = math.sin(math.pi * min(1.0, t0)) ** 0.7
                p.ellipse(px_, py_, ctx.stage.px(3.4) * (0.6 + a), ctx.stage.px(3.4) * (0.6 + a),
                          fill=with_alpha(ctx.col("accent3"), 0.45 * a))

    def _draw_exploded(self, p: Painter, ctx: RenderContext, quadrant, t: float) -> None:
        """Pull the panel apart into glass / cell / backing slabs (2.5D depth)."""
        xs = [q[0] for q in quadrant]
        ys = [q[1] for q in quadrant]
        cx = sum(xs) / 4
        cy = sum(ys) / 4
        span = max(xs) - min(xs)
        gap = span * 0.14 * t
        layers = [
            (ctx.col("glass"), -gap * 1.2, 0.30),
            (mix(ctx.col("cool"), ctx.col("accent3"), 0.35), 0.0, 0.34),
            (ctx.col("metal_dark"), gap * 1.2, 0.30),
        ]
        for i, (col, dy, alpha) in enumerate(layers):
            pts = [(q[0] + (q[0] - cx) * 0.10 * t, q[1] + dy + (q[1] - cy) * 0.10 * t) for q in quadrant]
            p.polygon(pts, fill=with_alpha(col, 0.55), outline=with_alpha(ctx.col("paper"), 0.55), width=2)

    def _el_layer_stack(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        """Exploded cross-section of the panel: glass / silicon / backing."""
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stack"))
        labels = ctx.labels(el, "labels")
        pal = ctx.palette
        t = ease_in_out(ctx.progress("explode_layers"))
        slabs = 3
        slab_h = h * 0.15
        gap = h * 0.115
        total = slabs * slab_h + (slabs - 1) * gap
        top = y + (h - total) / 2
        # the camera push-in scales the world up by ~7 %, so a plate that starts at
        # the slot's left edge gets cropped.  Inset by the safe margin and keep the
        # label column inside the frame.
        inset = ctx.stage.safe_x * 0.9
        x = max(x, inset)
        slab_w = min(w * 0.52, ctx.stage.width - inset * 1.4 - x - ctx.stage.width * 0.24)
        slab_w = max(ctx.stage.px(120), slab_w)
        fill = [mix(pal["glass"], pal["paper"], 0.45),
                mix(pal["cool"], pal["ink"], 0.30),
                mix(pal["metal_dark"], pal["ink"], 0.30)]
        lx = x + slab_w + ctx.stage.px(26)
        for i in range(slabs):
            spread = (i - 1) * gap * 1.25 * t
            sy = top + i * (slab_h + gap) + spread
            skew = slab_h * 0.34
            img, ox, oy = solar_props.slab(pal, p.ss, x, sy, x + slab_w, sy + slab_h,
                                           fill[i], skew=skew,
                                           edge=with_alpha(pal["paper"], 0.8) if i == 0 else None)
            p.paste_sprite(img, ox, oy)
            if i == 1 and t > 0.25:
                # photo-active cells waking up along the silicon layer
                for c in range(6):
                    cx = x + skew + (c + 0.5) * (slab_w - skew * 2) / 6
                    a = clamp((t - 0.25) / 0.6) * (0.55 + 0.45 * math.sin(ctx.t * 3 + c))
                    p.ellipse(cx, sy + slab_h * 0.5, ctx.stage.px(3.2), ctx.stage.px(3.2),
                              fill=with_alpha(pal["accent3"], a))
            if labels and i < len(labels):
                mid = sy + slab_h * 0.5
                appear = clamp(t * 1.5 - i * 0.18)
                # leader line from the plate to its label, with a dot on the plate
                p.line([(x + slab_w - skew * 0.4, mid), (lx - ctx.stage.px(9), mid)],
                       with_alpha(pal["muted"], 0.55 * appear),
                       width=max(1.2, ctx.stage.px(1.6)))
                p.ellipse(x + slab_w - skew * 0.4, mid, ctx.stage.px(2.8), ctx.stage.px(2.8),
                          fill=with_alpha(pal["accent3"], appear))
                self.label(p, ctx, lx, mid, labels[i], size=ctx.stage.label_size(),
                           align="left", bg=False,
                           max_width=ctx.stage.width - ctx.stage.safe_x - lx, alpha=appear)

    def _el_electrons(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "circuit"))
        flow = ctx.progress("electrons_flow")
        count = int((el.get("params") or {}).get("count", 12))
        # a rounded rectangular circuit: panel -> inverter -> load -> back
        loop = []
        r = min(w, h) * 0.22
        pts = [
            (x + w * 0.10, y + h * 0.20), (x + w * 0.90, y + h * 0.20),
            (x + w * 0.90, y + h * 0.80), (x + w * 0.10, y + h * 0.80),
        ]
        for i in range(4):
            a = pts[i]
            b = pts[(i + 1) % 4]
            steps = 26
            for s in range(steps):
                u = s / steps
                loop.append((lerp(a[0], b[0], u), lerp(a[1], b[1], u)))
        dashed_line(p, pts[0], pts[1], with_alpha(ctx.col("cool"), 0.55), width=3, dash=12, gap=8, phase=ctx.t)
        dotted = with_alpha(ctx.col("cool"), 0.35)
        p.line([pts[1], pts[2], pts[3]], dotted, width=2)
        if flow > 0:
            n = max(4, int(count * flow))
            flow_dots(p, loop, t=ctx.t, color=ctx.col("accent3"), count=n, speed=0.28,
                      radius=max(2.5, min(w, h) * 0.018), spread=0.0)

    def _el_inverter(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage_right"))
        bw, bh = w * 0.74, h * 0.66
        bx, by = x + (w - bw) / 2, y + (h - bh) / 2
        pulse = ctx.progress("inverter_pulse")
        img, ox, oy = solar_props.inverter(ctx.palette, p.ss, bx, by, bw, bh)
        p.paste_sprite(img, ox, oy)

        # live overlays: the AC trace on the screen and the pulsing status LED
        sx0, sx1 = bx + bw * 0.20, bx + bw * 0.80
        sy0, sy1 = by + bh * 0.16 + bh * 0.02, by + bh * 0.44
        mid = (sy0 + sy1) / 2
        amp = (sy1 - sy0) * 0.28
        pts = []
        for i in range(48):
            u = i / 47
            pts.append((sx0 + (sx1 - sx0) * u,
                        mid - math.sin(u * math.tau * 1.6 - ctx.t * 5.0) * amp))
        p.line(pts, with_alpha(ctx.col("accent3"), 0.80 + 0.20 * math.sin(ctx.t * 5.0)),
               width=max(2.0, bh * 0.016))
        led_a = 0.35 + 0.55 * (0.5 + 0.5 * math.sin(ctx.t * 6.0)) * (0.45 + 0.55 * pulse)
        led_x, led_y = bx + bw * 0.20, by + bh * 0.88
        p.ellipse(led_x, led_y, bw * 0.05, bw * 0.05,
                  fill=with_alpha(ctx.col("accent3"), led_a))
        p.ellipse(led_x, led_y, bw * (0.13 + 0.06 * pulse), bw * (0.13 + 0.06 * pulse),
                  fill=with_alpha(ctx.col("accent3"), 0.10 * led_a))
        self.label(p, ctx, bx + bw / 2, by - bh * 0.10, ctx.pick("inverter", "انورٹر"),
                   size=ctx.stage.label_size() * 0.95)

    def _el_wire(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "wire"))
        params = el.get("params", {})
        ax, ay, aw, ah = self.slot(ctx.stage, params.get("from", "stage_left"))
        bx, by, bw, bh = self.slot(ctx.stage, params.get("to", "stage_right"))
        a = (ax + aw * 0.96, ay + ah * 0.52)
        b = (bx + bw * 0.04, by + bh * 0.52)
        pts = sag_curve(a, b, h * 0.20, 26)
        progress = max(ctx.progress("dc_arrow"), ctx.progress("split_flow"))
        if progress <= 0:
            progress = 1.0
        solar_props.cable(p, pts, casing=shade(ctx.col("ink"), 0.85), core=ctx.col("accent2"),
                          width=max(4.0, ctx.stage.px(7.0)), progress=min(1.0, progress * 1.4))
        if ctx.progress("dc_arrow") > 0:
            flow_dots(p, pts, t=ctx.t, color=ctx.col("accent3"), count=4, speed=0.6,
                      radius=max(2.5, h * 0.05))

    def _el_waveform(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "wave"))
        kind = (el.get("params") or {}).get("kind", "dc_then_ac")
        mid = y + h / 2
        p.rect(x, y, x + w, y + h, fill=with_alpha(ctx.col("ink"), 0.55), radius=8)
        p.line([(x + 8, mid), (x + w - 8, mid)], with_alpha(ctx.col("muted"), 0.3), width=1.5)
        if kind == "dc_then_ac":
            dc_p = ease_in_out(ctx.progress("dc_arrow"))
            ac_p = ease_in_out(ctx.progress("ac_wave"))
            half = x + w * 0.46
            # DC: flat line above the axis
            if dc_p > 0:
                p.line([(x + w * 0.06, mid - h * 0.26), (x + w * 0.06 + (half - x) * dc_p, mid - h * 0.26)],
                       ctx.col("accent3"), width=4)
                self.label(p, ctx, x + w * 0.24, y + h * 0.18, "DC", bg=False,
                           size=ctx.stage.label_size(), color=ctx.col("accent3"))
            if ac_p > 0:
                pts = []
                n = 40
                for i in range(n):
                    u = i / (n - 1)
                    pts.append((half + (x + w * 0.94 - half) * u,
                                mid + math.sin(u * math.tau * 3) * h * 0.30 * dc_p))
                p.line(pts, ctx.col("cool"), width=4)
                self.label(p, ctx, x + w * 0.72, y + h * 0.18, "AC", bg=False,
                           size=ctx.stage.label_size(), color=ctx.col("cool"))
            p.line([(half, y + 6), (half, y + h - 6)], with_alpha(ctx.col("paper"), 0.25), width=1.5)
        else:
            bits = (el.get("params") or {}).get("bits", "1011")
            amp = h * 0.26
            pts = []
            per = (w * 0.86) / len(bits)
            for i, b in enumerate(bits):
                lvl = -amp if b == "1" else amp
                pts += [(x + w * 0.07 + i * per, mid + lvl), (x + w * 0.07 + (i + 1) * per, mid + lvl)]
            p.line(pts, ctx.col("accent3"), width=3)

    def _el_battery(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage_right"))
        fill_p = ease_in_out(ctx.progress("battery_fill"))
        fill = 0.18 + 0.78 * fill_p
        img, ox, oy = solar_props.battery(ctx.palette, p.ss, x, y, w, h, fill=fill)
        p.paste_sprite(img, ox, oy)
        # above the cell, not over its terminal
        self.label(p, ctx, x + w / 2, y - h * 0.06, ctx.pick("battery", "بیٹری"),
                   size=ctx.stage.label_size() * 0.95)

    def _el_grid(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "grid"))
        energy = ctx.progress("split_flow")
        img, ox, oy = solar_props.pylon(ctx.palette, p.ss, x, y, w, h,
                                        energy=round(energy, 1))
        p.paste_sprite(img, ox, oy)
        if energy > 0.3:
            cx = x + w * 0.5
            for i in range(3):
                u = ((ctx.t * 0.7) + i / 3) % 1.0
                p.ellipse(cx, lerp(y + h, y + h * 0.12, u), ctx.stage.px(2.8), ctx.stage.px(2.8),
                          fill=with_alpha(ctx.col("accent3"), 0.9 * (1 - u * 0.45)))
        self.label(p, ctx, x + w * 0.5, y + h * 1.02, ctx.pick("grid", "گرڈ"),
                   size=ctx.stage.label_size() * 0.9)

    def _el_efficiency_bar(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        """Split meter: how much of the sunlight becomes electricity vs heat."""
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        pal = ctx.palette
        share = float((el.get("params") or {}).get("share", 0.2))
        reveal = ease_in_out(ctx.progress("efficiency_bar"))
        bw, bh = w * 0.80, h * 0.13
        bx, by = x + (w - bw) / 2, y + h * 0.34
        radius = bh / 2

        # track: dark glass with an inner shadow line
        p.rect(bx - 4, by - 4, bx + bw + 4, by + bh + 4, fill=with_alpha(pal["shadow"], 0.55),
               radius=radius + 4)
        p.rect(bx, by, bx + bw, by + bh, fill=with_alpha(pal["ink"], 0.92), radius=radius)
        p.rect(bx + 2, by + 2, bx + bw - 2, by + bh * 0.45,
               fill=with_alpha(pal["paper"], 0.05), radius=radius * 0.6)

        # heat portion first (warm), then the small electricity slice on top of it
        heat_w = bw * (1 - share)
        if reveal > 0:
            fill_h = heat_w * min(1.0, reveal * 1.15)
            p.rect(bx, by, bx + max(bh, fill_h), by + bh,
                   fill=with_alpha(mix(pal["accent2"], pal["accent"], 0.45), 0.92), radius=radius)
            elec_w = bw * share * max(0.0, reveal * 1.6 - 0.6)
            if elec_w > 1:
                p.rect(bx, by, bx + max(bh, elec_w), by + bh,
                       fill=with_alpha(pal["accent3"], 0.98), radius=radius)
                # slim highlight along the top of the electricity slice
                p.rect(bx + bh * 0.4, by + bh * 0.18, bx + elec_w - bh * 0.3,
                       by + bh * 0.40, fill=with_alpha(mix(pal["accent3"], pal["paper"], 0.55), 0.55),
                       radius=bh * 0.11)
            # hairline divider between the two shares
            if reveal > 0.6:
                dx = bx + heat_w
                p.rect(dx - 1.2, by, dx + 1.2, by + bh, fill=with_alpha(pal["ink"], 0.6))

        # labels with small colour chips, sitting above the track
        ly = by - bh * 1.05
        self.label(p, ctx, bx + bh * 1.2, ly, ctx.pick("electricity", "بجلی"),
                   size=ctx.stage.label_size() * 0.95, bg=False, color=pal["accent3"],
                   align="left")
        self.label(p, ctx, bx + bw, ly, ctx.pick("heat", "گرمی"),
                   size=ctx.stage.label_size() * 0.95, bg=False, color=pal["accent2"],
                   align="right")

        # heat shimmer: short rising wisps just above the warm share
        hum = ease_in_out(ctx.progress("heat_arrows"))
        if hum > 0:
            for i in range(6):
                u = stagger(hum, i, 6, 0.7)
                if u <= 0:
                    continue
                hx = bx + heat_w * (0.14 + 0.14 * i)
                top_y = by - bh * (0.55 + 0.55 * u)
                sway = math.sin(ctx.t * 1.6 + i * 1.1) * ctx.stage.px(5)
                pts = []
                for k in range(9):
                    v = k / 8.0
                    pts.append((hx + sway * v * v, by - bh * 0.1 - (by - bh * 0.1 - top_y) * v))
                p.line(pts, with_alpha(pal["accent2"], 0.30 * u),
                       width=max(1.2, ctx.stage.px(1.8)))

    def _el_heat_arrows(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        # drawn as part of efficiency_bar when both exist; standalone version:
        if any(e.get("type") == "efficiency_bar" for e in []):
            return
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        heat = ease_in_out(ctx.progress("heat_arrows"))
        for i in range(6):
            u = stagger(heat, i, 6, 0.7)
            if u <= 0:
                continue
            sx = x + w * (0.12 + 0.13 * i)
            sy = y + h * 0.62
            p.line([(sx, sy), (sx + 20 * math.sin(ctx.t * 1.7 + i), sy - h * 0.16 * u)],
                   with_alpha(ctx.col("accent2"), 0.75 * u), width=3)

    def _el_array(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        """A small solar field: rows of tilted panels standing on the ground."""
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage_right"))
        params = el.get("params") or {}
        rows = int(params.get("rows", 2))
        cols = int(params.get("cols", 3))
        grow = ease_out(ctx.progress("array_expand")) if ctx.progress("array_expand") else 1.0
        pal = ctx.palette
        cw = w * 0.30
        ch = h * 0.30
        # a shadowed soil strip under the whole field anchors it to the ground
        p.ellipse(x + w * 0.5, y + h * 0.98, w * 0.52, max(2.0, h * 0.055),
                  fill=with_alpha(pal["shadow"], 0.30))
        for r in range(rows):
            for c in range(cols):
                pr = stagger(grow, (rows - 1 - r) * cols + c, rows * cols, 0.75)
                if pr <= 0.02:
                    continue
                # back rows sit a little higher and smaller: cheap perspective
                depth = 1.0 - r * 0.14
                bx = x + w * 0.06 + c * cw * 1.12 + (r % 2) * cw * 0.22
                by = y + h * 0.20 + r * ch * 1.02
                pw, ph = cw * depth * (0.65 + 0.35 * pr), ch * depth * (0.65 + 0.35 * pr)
                # panel face
                quad = [(bx, by + ph * 0.18), (bx + pw, by),
                        (bx + pw, by + ph * 0.86), (bx, by + ph * 1.04)]
                p.polygon([(qx, qy + ph * 0.10) for qx, qy in quad],
                          fill=with_alpha(pal["shadow"], 0.45))
                p.polygon(quad, fill=with_alpha(mix(pal["cool"], pal["ink"], 0.62), 0.96))
                # a couple of cell lines, not a full grid
                for k in (0.33, 0.66):
                    p.line([(bx + pw * k, by + ph * 0.06), (bx + pw * k, by + ph * 0.95)],
                           with_alpha(pal["metal"], 0.35), width=1.2)
                p.line([*quad, quad[0]], with_alpha(mix(pal["metal"], pal["paper"], 0.45), 0.85),
                       width=1.8)
                # support post
                p.line([(bx + pw * 0.5, by + ph * 0.95), (bx + pw * 0.5, by + ph * 1.30)],
                       with_alpha(pal["metal_dark"], 0.8), width=max(1.6, pw * 0.05))
                # specular streak across the glass
                p.polygon([(bx + pw * 0.12, by + ph * 0.30), (bx + pw * 0.30, by + ph * 0.16),
                           (bx + pw * 0.52, by + ph * 0.70), (bx + pw * 0.34, by + ph * 0.84)],
                          fill=with_alpha(mix(pal["paper"], pal["glass"], 0.5), 0.10))

    def _el_label(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "caption_band"))
        text = ctx.label(el)
        if not text:
            return
        params = el.get("params", {})
        alpha = 1.0
        target = params.get("leader_to")
        if target:
            tx, ty, tw, th = self.slot(ctx.stage, target)
            p.line([(x + w * 0.5, y + h * 0.15), (tx + tw * 0.5, ty + th * 0.95)],
                   with_alpha(ctx.col("muted"), 0.75), width=max(1.5, ctx.stage.px(2)))
        self.label(p, ctx, x + w / 2, y + h / 2, text,
                   size=params.get("size", ctx.stage.label_size()), alpha=max(0.55, alpha))

    def _el_arrow(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        params = el.get("params", {})
        ax, ay, aw, ah = self.slot(ctx.stage, params.get("from", "stage_left"))
        bx, by, bw, bh = self.slot(ctx.stage, params.get("to", "stage_right"))
        t = ease_in_out(ctx.any_progress("flow_recap", "split_flow", "dc_arrow"))
        if t <= 0:
            return
        a = (ax + aw * 0.8, ay + ah * 0.5)
        b = (bx + bw * 0.2, by + bh * 0.5)
        arrow(p, a, lerp_pt(a, b, t), ctx.col("accent3"), width=5, head=14)

    def _el_caption(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        self._el_label(p, ctx, el)

    def _el_recap_flow(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        """Animated energy path across the recap: panel -> inverter -> battery -> house."""
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        a = self.slot(ctx.stage, "stage_left")
        b = self.slot(ctx.stage, "stage_mid")
        c = self.slot(ctx.stage, "stage_right")
        d = self.slot(ctx.stage, "house_small")
        # gentle arcs: a deep sag between two close props reads as a piece of
        # bunting, so the drop is proportional to the gap, not to the slot height
        def arc(p0, p1, n=16):
            gap = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
            return sag_curve(p0, p1, gap * 0.10, n)

        pts_a = arc((a[0] + a[2] * 0.92, a[1] + a[3] * 0.50), (b[0] + b[2] * 0.08, b[1] + b[3] * 0.50))
        pts_b = arc((b[0] + b[2] * 0.92, b[1] + b[3] * 0.50), (c[0] + c[2] * 0.10, c[1] + c[3] * 0.50))
        pts_c = arc((c[0] + c[2] * 0.55, c[1] + c[3] * 0.30), (d[0] + d[2] * 0.50, d[1] + d[3] * 0.05), 12)
        prog = ctx.progress("flow_recap")
        if prog <= 0:
            return
        for i, (pts, speed) in enumerate(((pts_a, 0.55), (pts_b, 0.7), (pts_c, 0.9))):
            u = clamp(prog * 1.6 - i * 0.18)
            if u <= 0:
                continue
            k = max(2, int(len(pts) * u))
            p.line(pts[:k], with_alpha(ctx.col("accent2"), 0.85), width=4)
            flow_dots(p, pts, t=ctx.t * (1 + 0.2 * i), color=ctx.col("accent3"),
                      count=4, speed=speed, radius=ctx.stage.px(3.4))

    # ------------------------------------------------------------ foreground
    def foreground(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        # floating dust motes in the light
        rnd = random.Random(3)
        for i in range(14):
            bx = rnd.random() * st.width
            by = st.height * (0.25 + rnd.random() * 0.5)
            drift = math.sin(ctx.t * (0.4 + rnd.random() * 0.6) + i) * 14
            rise = (ctx.t * (6 + rnd.random() * 10)) % (st.height * 0.5)
            p.ellipse(bx + drift, by - rise, 2.0, 2.0,
                      fill=with_alpha(ctx.col("accent3"), 0.35 * (1 - rise / (st.height * 0.5))))
        self.atmosphere(p, ctx, 0.32)


def lerp_pt(a, b, t):
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))
