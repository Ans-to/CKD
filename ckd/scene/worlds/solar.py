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
        wx, wy, ww, wh = stage.world_area
        vertical = stage.format == "vertical"
        s: Dict[str, Box] = {}
        if vertical:
            s["back"] = (0, wy, ww, wh)
            s["sun"] = (ww * 0.70, wy + wh * 0.02, ww * 0.24, wh * 0.26)
            s["house"] = (ww * 0.08, wy + wh * 0.34, ww * 0.62, wh * 0.58)
            s["roof"] = (ww * 0.12, wy + wh * 0.28, ww * 0.56, wh * 0.26)
            s["panel_label"] = (ww * 0.10, wy + wh * 0.88, ww * 0.52, wh * 0.10)
            s["stage"] = (ww * 0.05, wy + wh * 0.08, ww * 0.90, wh * 0.84)
            s["stage_left"] = (ww * 0.03, wy + wh * 0.06, ww * 0.30, wh * 0.44)
            s["stage_mid"] = (ww * 0.34, wy + wh * 0.06, ww * 0.30, wh * 0.44)
            s["stage_right"] = (ww * 0.62, wy + wh * 0.06, ww * 0.29, wh * 0.44)
            s["stack"] = (ww * 0.03, wy + wh * 0.04, ww * 0.72, wh * 0.60)
            s["circuit"] = (ww * 0.04, wy + wh * 0.10, ww * 0.92, wh * 0.70)
            s["wire"] = (ww * 0.20, wy + wh * 0.30, ww * 0.60, wh * 0.28)
            s["wave"] = (ww * 0.05, wy + wh * 0.58, ww * 0.90, wh * 0.30)
            s["wave_band"] = (ww * 0.06, wy + wh * 0.80, ww * 0.88, wh * 0.16)
            s["grid"] = (ww * 0.60, wy + wh * 0.05, ww * 0.34, wh * 0.40)
            # the recap puts a battery directly above this, so keep the gable low
            s["house_small"] = (ww * 0.66, wy + wh * 0.56, ww * 0.26, wh * 0.32)
            s["caption_band"] = (ww * 0.04, wy + wh * 0.78, ww * 0.92, wh * 0.18)
        else:
            s["back"] = (wx, wy, ww, wh)
            s["sun"] = (wx + ww * 0.74, wy + wh * 0.02, ww * 0.19, wh * 0.34)
            s["house"] = (wx + ww * 0.50, wy + wh * 0.34, ww * 0.36, wh * 0.56)
            s["roof"] = (wx + ww * 0.48, wy + wh * 0.24, ww * 0.38, wh * 0.26)
            s["panel_label"] = (wx + ww * 0.52, wy + wh * 0.93, ww * 0.30, wh * 0.10)
            s["stage"] = (wx + ww * 0.06, wy + wh * 0.06, ww * 0.66, wh * 0.82)
            s["stage_left"] = (wx + ww * 0.01, wy + wh * 0.10, ww * 0.40, wh * 0.74)
            s["stage_mid"] = (wx + ww * 0.44, wy + wh * 0.14, ww * 0.20, wh * 0.62)
            s["stage_right"] = (wx + ww * 0.66, wy + wh * 0.14, ww * 0.19, wh * 0.62)
            s["stack"] = (wx + ww * 0.10, wy + wh * 0.06, ww * 0.62, wh * 0.80)
            s["circuit"] = (wx + ww * 0.44, wy + wh * 0.30, ww * 0.40, wh * 0.50)
            s["wire"] = (wx + ww * 0.24, wy + wh * 0.52, ww * 0.30, wh * 0.22)
            s["wave"] = (wx + ww * 0.40, wy + wh * 0.58, ww * 0.46, wh * 0.24)
            # a wide, low band under the props: reads as an oscilloscope strip, never
            # collides with the wire or the inverter body
            s["wave_band"] = (wx + ww * 0.06, wy + wh * 0.80, ww * 0.88, wh * 0.16)
            s["grid"] = (wx + ww * 0.80, wy + wh * 0.06, ww * 0.19, wh * 0.40)
            s["house_small"] = (wx + ww * 0.78, wy + wh * 0.40, ww * 0.21, wh * 0.46)
            s["caption_band"] = (wx + ww * 0.04, wy + wh * 0.84, ww * 0.92, wh * 0.14)
        return s

    # ------------------------------------------------------------- background
    def background(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        pal = ctx.palette
        wx, wy, ww, wh = st.world_area
        full_top = 0.0
        p.gradient_rect(0, full_top, st.width, wy + wh * 0.62, pal["bg_top"], pal["sky_glow"])
        p.radial_rect(0, full_top, st.width, wy + wh * 0.7, with_alpha(pal["sky_glow"], 120),
                      with_alpha(pal["bg_top"], 0), cx=0.82, cy=0.12, power=1.5)
        horizon = wy + wh * 0.62
        hill(p, -40, st.width + 40, horizon + 6, wh * 0.20, with_alpha(pal["ground_far"], 0.85),
             seed=4, bumps=2)
        hill(p, -40, st.width + 40, horizon + 10, wh * 0.11, with_alpha(pal["ground"], 0.95),
             seed=9, bumps=3)
        ground_band(p, -10, st.width + 10, horizon + 4, pal["ground"], pattern="dots",
                    t=ctx.t * 0.4, depth=st.height - horizon)
        # distant panels for depth
        rnd = random.Random(11)
        for i in range(4):
            bx = wx - ww * 0.06 + i * ww * 0.09
            self._mini_panel(p, bx, horizon + wh * 0.10 + rnd.random() * 8, 26, 16, pal)
        # title-safe warm wash
        p.rect(0, 0, st.width, st.height, fill=with_alpha(pal["accent3"], 0.02))

    def _mini_panel(self, p: Painter, x: float, y: float, w: float, h: float, pal) -> None:
        p.polygon([(x + w * 0.15, y), (x + w, y - h * 0.25), (x + w * 0.85, y + h * 0.45), (x, y + h * 0.7)],
                  fill=with_alpha(pal["glass"], 0.35))

    # ---------------------------------------------------------------- objects
    def _el_sky(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        st = ctx.stage
        # keep clouds out of the headline band so type stays readable
        top = st.headline_area[1] + st.headline_area[3] + st.px(6)
        clouds(p, (0, top, st.width, max(st.px(40), st.height * 0.24)), ctx.t, ctx.col("paper"),
               count=3, seed=7)

    def _el_sun(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "sun"))
        rise = ease_out(ctx.progress("sun_rise"))
        cx = x + w * 0.5
        cy = y + h * (0.85 - 0.45 * rise)
        r = min(w, h) * 0.26
        if ctx.progress("sun_rise") <= 0.0:
            r *= 0.6
        sun(p, cx, cy, r, t=ctx.t, color=ctx.col("accent3"), glow_color=ctx.col("accent3"),
            rays=rise > 0.2)
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
                p.line(pts[:k], with_alpha(ctx.col("accent3"), 0.85 * a), width=max(2.0, r * 0.06))
                if t0 > 0.5:
                    p.ellipse(ex, ey, 3.2, 3.2, fill=with_alpha("#fffbe6", a))

    def _el_house(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "house"))
        pal = ctx.palette
        build = ease_out(ctx.progress("build_bridge")) if ctx.progress("build_bridge") else 1.0
        body_h = h * 0.62 * build
        bx0, bx1 = x + w * 0.12, x + w * 0.88
        by1 = y + h
        by0 = by1 - body_h
        p.rect(bx0 - 3, by0 - 3, bx1 + 3, by1, fill=with_alpha(pal["shadow"], 1.0), radius=6)
        p.rect(bx0, by0, bx1, by1, fill=mix(pal["paper"], pal["ground_far"], 0.35), radius=4)
        # roof (simple gable that doubles as the panel mount)
        peak = (x + w * 0.5, by0 - h * 0.22 * build)
        p.polygon([(bx0 - w * 0.06, by0 + 4), peak, (bx1 + w * 0.06, by0 + 4)],
                  fill=mix(pal["accent2"], pal["ink"], 0.35))
        p.line([(bx0 - w * 0.06, by0 + 4), peak, (bx1 + w * 0.06, by0 + 4)],
               shade(pal["accent2"], 0.7), width=3)
        # windows: warm light, brighter after sunset action
        night = ctx.progress("night_glow")
        lit = 0.25 + 0.75 * night
        for i, wx_ in enumerate((0.24, 0.55)):
            ww_ = w * 0.16
            wy_ = by0 + body_h * 0.22
            p.rect(x + w * wx_, wy_, x + w * wx_ + ww_, wy_ + body_h * 0.28,
                   fill=mix(pal["ink"], pal["accent3"], 0.18 + 0.55 * lit), radius=3)
            p.line([(x + w * wx_ + ww_ / 2, wy_), (x + w * wx_ + ww_ / 2, wy_ + body_h * 0.28)],
                   with_alpha(pal["ink"], 0.6), width=2)
        # door
        p.rect(x + w * 0.40, by1 - body_h * 0.34, x + w * 0.48, by1, fill=shade(pal["ink"], 0.7), radius=2)

    def _el_panel(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        params = el.get("params", {})
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        rows = int(params.get("rows", 3))
        cols = int(params.get("cols", 4))
        explode = bool(params.get("explode"))
        t_explode = ease_in_out(ctx.progress("explode_layers"))
        pw = w * 0.92
        ph = pw * (rows / max(1, cols)) * 0.72
        if ph > h * 0.9:
            ph = h * 0.9
            pw = ph * (cols / max(1, rows)) / 0.72
        # tilted panel: parallelogram.  The skew pushes the top edge right and the
        # bottom edge left, so reserve that overhang inside the slot instead of
        # letting the panel bleed past the safe area (and get cropped by the
        # camera push-in).
        tilt = ph * 0.18
        pw = max(ctx.stage.px(90), pw - tilt)
        cx, cy = x + w / 2, y + h / 2
        x0, x1 = cx - pw / 2, cx + pw / 2
        top_y, bot_y = cy - ph / 2, cy + ph / 2
        quad = [(x0 + tilt, top_y), (x1, top_y - tilt * 0.2), (x1 - tilt, bot_y), (x0, bot_y - tilt * 0.2)]
        shadow_off = ph * 0.10
        p.polygon([(qx, qy + shadow_off) for qx, qy in quad], fill=with_alpha(ctx.col("shadow"), 0.45))
        p.polygon(quad, fill=mix(ctx.col("metal_dark"), ctx.col("ink"), 0.35))
        # cells grid with perspective skew
        glow = ease_in_out(ctx.progress("panel_glow"))
        photons = ctx.progress("photons_hit")
        for r in range(rows):
            for c in range(cols):
                u0, u1 = c / cols, (c + 1) / cols
                v0, v1 = r / rows, (r + 1) / rows
                def pt(u, v):
                    # bilinear inside the quad
                    topx, topy = lerp(quad[0][0], quad[1][0], u), lerp(quad[0][1], quad[1][1], u)
                    botx, boty = lerp(quad[3][0], quad[2][0], u), lerp(quad[3][1], quad[2][1], u)
                    return (lerp(topx, botx, v), lerp(topy, boty, v))
                inset = 0.03
                cell = [pt(u0 + inset, v0 + inset), pt(u1 - inset, v0 + inset),
                        pt(u1 - inset, v1 - inset), pt(u0 + inset, v1 - inset)]
                cell_glow = stagger(photons, r * cols + c, rows * cols, 0.5) * 0.35 + glow * 0.35
                base = mix(ctx.col("bg_bottom"), ctx.col("cool"), 0.30 + 0.5 * cell_glow)
                p.polygon(cell, fill=base, outline=with_alpha(ctx.col("glass"), 0.5), width=1.5)
                if cell_glow > 0.05:
                    p.polygon(cell, fill=with_alpha(ctx.col("accent3"), 0.10 * cell_glow))
        # frame rails
        p.line(quad + [quad[0]], with_alpha(ctx.col("metal"), 0.9), width=4)
        # exploded layers slide apart when requested
        if explode and t_explode > 0:
            self._draw_exploded(p, ctx, quadrant=quad, t=t_explode)

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
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stack"))
        labels = ctx.labels(el, "labels")
        t = ease_in_out(ctx.progress("explode_layers"))
        slabs = 3
        slab_h = h * 0.17
        gap = h * 0.11
        total = slabs * slab_h + (slabs - 1) * gap
        top = y + (h - total) / 2
        slab_w = w * 0.58
        colors = [ctx.col("glass"), mix(ctx.col("cool"), ctx.col("accent3"), 0.4), ctx.col("metal_dark")]
        lx = x + w * 0.63  # label column, always clear of the slabs
        for i in range(slabs):
            spread = (i - 1) * gap * 1.15 * t
            sy = top + i * (slab_h + gap) + spread
            sx0, sx1 = x, x + slab_w
            skew = slab_h * 0.30
            p.polygon([(sx0 + skew, sy), (sx1, sy + skew * 0.2), (sx1 - skew, sy + slab_h),
                       (sx0, sy + slab_h - skew * 0.2)],
                      fill=with_alpha(colors[i % len(colors)], 0.85 if i != 1 else 0.95),
                      outline=with_alpha(ctx.col("paper"), 0.7), width=2)
            if i == 1 and t > 0.3:  # photo-active cells
                for c in range(5):
                    cx = sx0 + (c + 0.6) * (sx1 - sx0) / 5.4
                    p.ellipse(cx, sy + slab_h * 0.5, slab_h * 0.10, slab_h * 0.10,
                              fill=with_alpha(ctx.col("accent3"), 0.9 * clamp((t - 0.3) / 0.7)))
            if labels and i < len(labels):
                mid = sy + slab_h * 0.5
                appear = clamp(t * 1.6 - i * 0.2)
                p.line([(sx1 - skew * 0.4, mid), (lx - ctx.stage.px(8), mid)],
                       with_alpha(ctx.col("muted"), 0.85 * appear), width=max(1.5, ctx.stage.px(2)))
                p.ellipse(sx1 - skew * 0.4, mid, ctx.stage.px(3), ctx.stage.px(3),
                          fill=with_alpha(ctx.col("accent3"), appear))
                self.label(p, ctx, lx, mid, labels[i], size=ctx.stage.label_size(),
                           align="left", bg=True, max_width=x + w - lx, alpha=appear)

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
        bw, bh = w * 0.72, h * 0.62
        bx, by = x + (w - bw) / 2, y + (h - bh) / 2
        pulse = ctx.progress("inverter_pulse")
        glow_a = 0.25 + 0.5 * (0.5 + 0.5 * math.sin(ctx.t * 6)) * (0.35 + 0.65 * pulse)
        p.rect(bx - 4, by - 4, bx + bw + 4, by + bh + 4, fill=with_alpha(ctx.col("shadow"), 0.7), radius=10)
        p.rect(bx, by, bx + bw, by + bh, fill=mix(ctx.col("metal"), ctx.col("ink"), 0.55), radius=8)
        p.rect(bx + bw * 0.08, by + bh * 0.10, bx + bw * 0.92, by + bh * 0.40,
               fill=with_alpha(ctx.col("ink"), 0.85), radius=4)
        # small screen with a sine wave
        ys = by + bh * 0.25
        pts = []
        for i in range(24):
            u = i / 23
            pts.append((bx + bw * (0.12 + 0.76 * u),
                        ys + math.sin(u * math.tau * 1.6 - ctx.t * 5) * bh * 0.09))
        p.line(pts, with_alpha(ctx.col("accent3"), 0.75 + 0.25 * math.sin(ctx.t * 5)), width=2.5)
        # LED indicator
        p.ellipse(bx + bw * 0.18, by + bh * 0.62, bw * 0.05, bw * 0.05,
                  fill=with_alpha(ctx.col("accent3"), glow_a))
        p.glow(bx + bw * 0.18, by + bh * 0.62, bw * 0.16, ctx.col("accent3"), alpha=0.35 * glow_a, steps=3)
        # cooling fins
        for i in range(5):
            fx = bx + bw * (0.42 + i * 0.10)
            p.line([(fx, by + bh * 0.55), (fx, by + bh * 0.85)], with_alpha(ctx.col("metal_dark"), 0.9), width=3)
        self.label(p, ctx, bx + bw / 2, by - bh * 0.12, ctx.pick("inverter", "انورٹر"),
                   size=ctx.stage.label_size() * 0.95)

    def _el_wire(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "wire"))
        params = el.get("params", {})
        a_slot = params.get("from", "stage_left")
        b_slot = params.get("to", "stage_right")
        ax, ay, aw, ah = self.slot(ctx.stage, a_slot)
        bx, by, bw, bh = self.slot(ctx.stage, b_slot)
        a = (ax + aw * 0.92, ay + ah * 0.55)
        b = (bx + bw * 0.08, by + bh * 0.55)
        sag = h * 0.45
        pts = sag_curve(a, b, sag, 22)
        draw_p = max(ctx.progress("dc_arrow"), ctx.progress("split_flow"))
        if draw_p <= 0:
            draw_p = 1.0
        p.line(pts, with_alpha(ctx.col("ink"), 0.85), width=7)
        p.line(pts, with_alpha(ctx.col("accent2"), 0.9), width=4)
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
        bw, bh = w * 0.46, h * 0.62
        bx, by = x + (w - bw) / 2, y + (h - bh) / 2
        p.rect(bx - 4, by - 4, bx + bw + 4, by + bh + 4, fill=with_alpha(ctx.col("shadow"), 0.65), radius=10)
        p.rect(bx, by, bx + bw, by + bh, fill=mix(ctx.col("metal"), ctx.col("ink"), 0.35), radius=8)
        p.rect(bx + bw * 0.34, by - bh * 0.07, bx + bw * 0.66, by, fill=ctx.col("metal_dark"), radius=2)
        frac = clamp(ctx.progress("battery_fill"))
        inner_y0 = by + bh * 0.78
        fill_h = (bh * 0.62) * frac
        for i in range(4):
            cy0 = inner_y0 - bh * 0.15 * (i + 1)
            if (i + 1) / 4 <= frac + 1e-6:
                p.rect(bx + bw * 0.14, cy0, bx + bw * 0.86, cy0 + bh * 0.12,
                       fill=ctx.col("accent3"), radius=3)
        if frac > 0:
            p.glow(bx + bw / 2, inner_y0 - fill_h / 2, bw * 0.9, ctx.col("accent3"), alpha=0.22, steps=3)
        bolts = [[(bx + bw * 0.5, by + bh * 0.5), (bx + bw * 0.42, by + bh * 0.66),
                  (bx + bw * 0.52, by + bh * 0.66), (bx + bw * 0.44, by + bh * 0.86)]]
        if frac > 0.15:
            p.line(bolts[0], with_alpha("#ffffff", 0.75), width=2.5)
        self.label(p, ctx, bx + bw / 2, by - bh * 0.14, ctx.pick("battery", "بیٹری"),
                   size=ctx.stage.label_size() * 0.95)

    def _el_grid(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "grid"))
        cx = x + w * 0.5
        base = y + h
        top = y + h * 0.18
        p.line([(cx, top), (cx, base)], ctx.col("metal_dark"), width=6)
        for i in range(3):
            yy = top + (base - top) * (0.18 + i * 0.26)
            half = w * (0.06 + i * 0.055)
            p.line([(cx - half, yy), (cx + half, yy)], ctx.col("metal"), width=4)
            p.line([(cx - half, yy), (cx - half * 0.55, yy - h * 0.06)], ctx.col("metal"), width=2.5)
            p.line([(cx + half, yy), (cx + half * 0.55, yy - h * 0.06)], ctx.col("metal"), width=2.5)
        p.line([(cx - w * 0.16, base), (cx - w * 0.16, base + h * 0.06)], ctx.col("metal_dark"), width=4)
        p.line([(cx + w * 0.16, base), (cx + w * 0.16, base + h * 0.06)], ctx.col("metal_dark"), width=4)
        if ctx.progress("split_flow") > 0.3:
            for i in range(3):
                u = ((ctx.t * 0.7) + i / 3) % 1.0
                p.ellipse(cx, lerp(base, top, u), 3.0, 3.0, fill=with_alpha(ctx.col("accent3"), 1 - u * 0.4))
        self.label(p, ctx, cx, base + h * 0.16, ctx.pick("grid", "گرڈ"), size=ctx.stage.label_size() * 0.9)

    def _el_efficiency_bar(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        share = float((el.get("params") or {}).get("share", 0.2))
        frac = ease_in_out(ctx.progress("efficiency_bar")) * share
        bw, bh = w * 0.78, h * 0.12
        bx, by = x + (w - bw) / 2, y + h * 0.30
        p.rect(bx - 3, by - 3, bx + bw + 3, by + bh + 3, fill=with_alpha(ctx.col("shadow"), 0.6), radius=bh)
        p.rect(bx, by, bx + bw, by + bh, fill=mix(ctx.col("ink"), ctx.col("metal_dark"), 0.35), radius=bh)
        if frac > 0:
            p.rect(bx, by, bx + max(bh, bw * frac), by + bh, fill=ctx.col("accent3"), radius=bh)
            p.glow(bx + bw * frac, by + bh / 2, bh * 1.3, ctx.col("accent3"), alpha=0.3, steps=3)
        # heat share
        heat = ease_in_out(ctx.progress("heat_arrows"))
        if heat > 0:
            hx = bx + bw * (1 - share) * 0.55
            for i in range(5):
                u = stagger(heat, i, 5, 0.7)
                if u <= 0:
                    continue
                yy = by + bh + h * (0.06 + 0.12 * u) + i * 3
                p.line([(bx + bw * (0.3 + i * 0.13), yy), (bx + bw * (0.3 + i * 0.13) + 16 * math.sin(ctx.t * 2 + i), yy - h * 0.10)],
                       with_alpha(ctx.col("accent2"), 0.7 * u), width=3)
        self.label(p, ctx, bx + bw * max(0.14, frac * 0.55), by - bh * 1.0,
                   ctx.pick("electricity", "بجلی"), size=ctx.stage.label_size() * 0.9, bg=False,
                   color=ctx.col("accent3"))
        self.label(p, ctx, bx + bw * 0.86, by - bh * 1.0, ctx.pick("heat", "گرمی"),
                   size=ctx.stage.label_size() * 0.9, bg=False, color=ctx.col("accent2"))

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
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage_right"))
        rows = int((el.get("params") or {}).get("rows", 2))
        cols = int((el.get("params") or {}).get("cols", 3))
        grow = ease_out(ctx.progress("array_expand")) if ctx.progress("array_expand") else 1.0
        cw, ch = w * 0.26, h * 0.26
        for r in range(rows):
            for c in range(cols):
                p_ = stagger(grow, r * cols + c, rows * cols, 0.8)
                if p_ <= 0.01:
                    continue
                bx = x + w * 0.10 + c * cw * 1.12
                by = y + h * 0.22 + r * ch * 1.15
                size = 0.6 + 0.4 * p_
                p.polygon([(bx, by), (bx + cw * size, by - ch * 0.18 * size),
                           (bx + cw * size * 0.9, by + ch * 0.72 * size), (bx - cw * 0.1 * size, by + ch * 0.9 * size)],
                          fill=mix(ctx.col("bg_bottom"), ctx.col("cool"), 0.55),
                          outline=with_alpha(ctx.col("glass"), 0.8), width=2)

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
        pts_a = sag_curve((a[0] + a[2] * 0.92, a[1] + a[3] * 0.55), (b[0] + b[2] * 0.08, b[1] + b[3] * 0.55),
                          a[3] * 0.35, 14)
        pts_b = sag_curve((b[0] + b[2] * 0.92, b[1] + b[3] * 0.50), (c[0] + c[2] * 0.10, c[1] + c[3] * 0.50),
                          a[3] * 0.30, 14)
        pts_c = sag_curve((c[0] + c[2] * 0.55, c[1] + c[3] * 0.30), (d[0] + d[2] * 0.50, d[1] + d[3] * 0.05),
                          a[3] * 0.22, 12)
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
