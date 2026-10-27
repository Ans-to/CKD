"""Bridge-engineering visual world.

Parametric objects: valley + river, deck, piers, truss triangles, suspension
towers and cables, traffic, dead/live load arrows, compression/tension force
arrows, bending curve.  Bridge type is a parameter, so the same tools build a
beam, truss or suspension schematic (clearly labelled as a schematic, not an
as-built engineering model).
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

from ...gfx.painter import Painter, mix, rgba, shade, with_alpha
from ...gfx.primitives import (
    arrow, bezier_points, cable, clamp, dashed_line, ease_in_out, ease_out, flow_dots, hill, lerp,
    pixel_grid, sag_curve, stagger,
)
from ..stage import Box, Stage
from .base import RenderContext, World


class BridgeWorld(World):
    id = "bridge"
    palette_name = "blueprint"
    element_types = (
        "valley", "bridge", "truck", "weight_arrows", "force_arrows", "member_forces", "label",
        "arrow", "caption", "dimension",
    )

    # ----------------------------------------------------------------- layout
    def slots(self, stage: Stage) -> Dict[str, Box]:
        wx, wy, ww, wh = stage.world_area
        s: Dict[str, Box] = {}
        if stage.format == "vertical":
            s["back"] = (0, wy, ww, wh)
            s["bridge"] = (ww * 0.01, wy + wh * 0.20, ww * 0.98, wh * 0.58)
            s["deck"] = (ww * 0.04, wy + wh * 0.22, ww * 0.92, wh * 0.20)
            s["pier"] = (ww * 0.04, wy + wh * 0.58, ww * 0.92, wh * 0.22)
            s["truss"] = (ww * 0.04, wy + wh * 0.16, ww * 0.92, wh * 0.34)
            s["cable"] = (ww * 0.04, wy + wh * 0.08, ww * 0.92, wh * 0.30)
            s["stage"] = (ww * 0.02, wy + wh * 0.10, ww * 0.96, wh * 0.70)
            s["caption_band"] = (ww * 0.03, wy + wh * 0.84, ww * 0.94, wh * 0.14)
        else:
            s["back"] = (wx, wy, ww, wh)
            s["bridge"] = (wx + ww * 0.01, wy + wh * 0.24, ww * 0.98, wh * 0.56)
            s["deck"] = (wx + ww * 0.04, wy + wh * 0.26, ww * 0.92, wh * 0.16)
            s["pier"] = (wx + ww * 0.04, wy + wh * 0.60, ww * 0.92, wh * 0.24)
            s["truss"] = (wx + ww * 0.04, wy + wh * 0.20, ww * 0.92, wh * 0.30)
            s["cable"] = (wx + ww * 0.02, wy + wh * 0.10, ww * 0.96, wh * 0.26)
            s["stage"] = (wx + ww * 0.02, wy + wh * 0.10, ww * 0.96, wh * 0.80)
            s["caption_band"] = (wx + ww * 0.06, wy + wh * 0.86, ww * 0.88, wh * 0.12)
        return s

    # ------------------------------------------------------------- background
    def background(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        pal = ctx.palette
        wx, wy, ww, wh = st.world_area
        p.gradient_rect(0, 0, st.width, st.height, pal["bg_top"], mix(pal["bg_bottom"], pal["glass"], 0.35))
        # blueprint grid in the sky
        pixel_grid(p, (0, 0, st.width, wy + wh * 0.7), with_alpha(pal["glass"], 0.07), cell=st.px(52),
                   offset=(ctx.t * 3) % st.px(52))
        # distant hills (three parallax layers, increasing contrast with depth)
        horizon = wy + wh * 0.62
        hill(p, -60, st.width + 60, horizon - wh * 0.02, wh * 0.34,
             with_alpha(mix(pal["bg_bottom"], pal["glass"], 0.35), 0.45), seed=3, bumps=2)
        hill(p, -60, st.width + 60, horizon + 2, wh * 0.22,
             with_alpha(mix(pal["ground_far"], pal["metal_dark"], 0.35), 0.85), seed=8, bumps=3)
        hill(p, -60, st.width + 60, horizon + 8, wh * 0.11, palette_color(pal, "ground"), seed=12, bumps=2)
        # haze band on the horizon so the valleys read as distance
        p.rect(0, horizon - wh * 0.04, st.width, horizon + wh * 0.03,
               fill=with_alpha(pal["glass"], 0.10))
        # river in the valley
        rx0, rx1 = -20, st.width + 20
        river_y = horizon + wh * 0.06
        p.gradient_rect(rx0, river_y, rx1, st.height,
                        mix(pal["glass"], pal["bg_bottom"], 0.30),
                        mix(pal["glass"], pal["bg_bottom"], 0.85))
        for i in range(9):
            yy = river_y + wh * 0.04 + i * wh * 0.055
            if yy > st.height:
                break
            w_ = st.width * (0.18 + 0.06 * i)
            x_ = st.width * 0.5 - w_ / 2 + math.sin(ctx.t * 0.6 + i) * st.width * 0.03
            p.line([(x_, yy), (x_ + w_, yy)], with_alpha("#dff1ff", 0.28 + 0.12 * (i % 2)),
                   width=max(1.5, st.px(2)))

    # ---------------------------------------------------------------- objects
    def _el_valley(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        # atmosphere: birds / clouds sketched, keeps the valley alive
        st = ctx.stage
        for i in range(3):
            bx = (st.width * (0.15 + 0.3 * i) + ctx.t * 8 * (1 + i * 0.2)) % (st.width + 200) - 100
            by = st.height * (0.12 + 0.05 * i) + math.sin(ctx.t * 1.2 + i) * 6
            p.line([(bx - 8, by), (bx, by - 5)], with_alpha(ctx.col("glass"), 0.5), width=2)
            p.line([(bx, by - 5), (bx + 8, by)], with_alpha(ctx.col("glass"), 0.5), width=2)

    def _bridge_geometry(self, ctx: RenderContext, el: Dict) -> Dict[str, object]:
        """Geometry for the bridge and every prop that sits on it.

        The scene's own bridge element always wins, so the truck, the load arrows
        and the force labels are guaranteed to agree with the drawn deck.
        """
        src = ctx.find("bridge") or el
        x, y, w, h = self.slot(ctx.stage, src.get("slot", "bridge"))
        params = src.get("params") or {}
        kind = params.get("kind", "truss")
        spans = max(1, int(params.get("spans", 3)))
        deck_y = y + h * (0.46 if kind != "suspension" else 0.62)
        return {"x": x, "y": y, "w": w, "h": h, "kind": kind, "spans": spans, "deck_y": deck_y}

    def _el_bridge(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        g = self._bridge_geometry(ctx, el)
        x, y, w, h = g["x"], g["y"], g["w"], g["h"]
        deck_y = g["deck_y"]
        kind = g["kind"]
        spans = g["spans"]
        stress = bool((el.get("params") or {}).get("stress"))
        build = ease_out(ctx.progress("build_bridge")) if ctx.progress("build_bridge") else 1.0
        col_metal = ctx.col("metal")
        col_deck = mix(ctx.col("metal"), ctx.col("ink"), 0.30)

        # --- piers / tower feet first: they anchor everything visually
        pier_top = deck_y + h * 0.055
        xs = [x + w * (i / spans) for i in range(spans + 1)]
        for i, px in enumerate(xs[1:-1], start=1):
            growth = clamp((build - i * 0.10) * 1.9)
            if growth <= 0:
                continue
            ph = (y + h * 0.96 - pier_top) * growth
            pw = max(w * 0.016, ctx.stage.px(6))
            p.rect(px - pw * 1.15, pier_top, px + pw * 1.15, pier_top + ph,
                   fill=with_alpha(ctx.col("shadow"), 0.85), radius=3)
            p.rect(px - pw, pier_top, px + pw, pier_top + ph,
                   fill=mix(col_metal, ctx.col("bg_bottom"), 0.30), radius=2)
            p.rect(px - pw * 1.7, pier_top - h * 0.016, px + pw * 1.7, pier_top,
                   fill=with_alpha(col_metal, 0.95), radius=2)

        # --- deck: a solid slab with a lip, so it reads as a road the truck drives on
        deck_h = max(ctx.stage.px(9), h * 0.045)
        dgrow = clamp(build * 1.25)
        dx0 = x + w * 0.015
        dx1 = dx0 + (w * 0.97) * dgrow
        p.rect(dx0, deck_y, dx1, deck_y + deck_h, fill=col_deck, radius=deck_h * 0.30)
        p.rect(dx0, deck_y, dx1, deck_y + deck_h * 0.30,
               fill=with_alpha(col_metal, 0.95), radius=deck_h * 0.15)
        # road markings drift with the camera to sell the movement
        stripe_w = ctx.stage.px(16)
        sx = dx0 + ((ctx.t * 40) % (stripe_w * 2))
        while sx < dx1 - stripe_w:
            p.rect(sx, deck_y + deck_h * 0.52, min(dx1, sx + stripe_w * 0.9),
                   deck_y + deck_h * 0.70, fill=with_alpha(ctx.col("accent3"), 0.55), radius=1)
            sx += stripe_w * 2

        # --- abutments at both ends
        for side in (0, 1):
            ax = x + w * (0.015 if side == 0 else 0.985)
            p.rect(ax - w * 0.012, deck_y, ax + w * 0.012, y + h * 0.96,
                   fill=mix(col_metal, ctx.col("ink"), 0.45), radius=2)

        if kind in ("truss", "beam") and build > 0.3:
            self._draw_truss(p, ctx, x, y, w, h, deck_y, spans, build, stress,
                            truss=(kind == "truss"))
        if kind == "suspension" and build > 0.2:
            self._draw_suspension(p, ctx, x, y, w, h, deck_y, spans, build, stress)
        if (el.get("params") or {}).get("dimensions"):
            self._dimension(p, ctx, x + w * 0.04, deck_y + h * 0.46, x + w * 0.96,
                            deck_y + h * 0.46, ctx.pick("span", "شرح"))

    def _draw_truss(self, p, ctx, x, y, w, h, deck_y, spans, build, stress, truss=True) -> None:
        truss_top = deck_y - h * (0.30 if truss else 0.075)
        seg = (w * 0.96) / max(1, spans * 2)
        col = mix(ctx.col("metal"), ctx.col("glass"), 0.25)
        warm = ctx.col("accent2")
        cool = ctx.col("cool")
        tension_p = ctx.progress("member_forces")
        if not truss:
            # beam bridge: a shallow girder band under the deck instead of triangles
            g0 = x + w * 0.02
            g1 = g0 + (w * 0.96) * clamp(build * 1.3)
            gh = h * 0.075
            p.rect(g0, deck_y + h * 0.05, g1, deck_y + h * 0.05 + gh,
                   fill=mix(ctx.col("metal_dark"), ctx.col("ink"), 0.45), radius=3)
            if stress and ctx.progress("bending") > 0:
                pts = [(g0 + (g1 - g0) * (k / 29),
                        deck_y + h * 0.05 + gh + math.sin(math.pi * k / 29) * ctx.stage.px(16)
                        * ctx.progress("bending")) for k in range(30)]
                p.line(pts, with_alpha(ctx.col("cool"), 0.9), width=3)
            return
        for i in range(spans * 2):
            x0 = x + w * 0.02 + i * seg
            x1 = x0 + seg
            appear = clamp(build * 1.4 - i * 0.06)
            if appear <= 0:
                continue
            # top chord
            p.line([(x0, truss_top), (x1, truss_top)], with_alpha(col, appear), width=max(3.0, h * 0.020))
            # bottom chord (deck side)
            p.line([(x0, deck_y), (x1, deck_y)], with_alpha(col, appear), width=max(3.0, h * 0.022))
            # diagonals
            if i % 2 == 0:
                p.line([(x0, deck_y), (x1, truss_top)], with_alpha(col, appear), width=max(2.5, h * 0.016))
            else:
                p.line([(x0, truss_top), (x1, deck_y)], with_alpha(col, appear), width=max(2.5, h * 0.016))
            p.line([(x0, truss_top), (x0, deck_y)], with_alpha(col, appear), width=max(2.5, h * 0.014))
            # force colouring along members (tension blue / compression red)
            if stress and tension_p > 0:
                a = clamp(tension_p * 1.4 - i * 0.05) * 0.9
                if a > 0:
                    p.line([(x0, truss_top), (x1, truss_top)], with_alpha(warm, a), width=max(3.0, h * 0.022))
                    p.line([(x0, deck_y), (x1, deck_y)], with_alpha(cool, a), width=max(3.0, h * 0.024))
        p.line([(x + w * 0.02, truss_top), (x + w * 0.98, truss_top)],
               with_alpha(col, clamp(build * 1.3)), width=max(3.0, h * 0.020))

    def _draw_suspension(self, p, ctx, x, y, w, h, deck_y, spans, build, stress) -> None:
        tower_h = h * 0.62
        tower_w = w * 0.022
        tower_xs = [x + w * (i / spans) for i in range(spans + 1)]
        tension_p = ctx.progress("tower_push")
        tense = ctx.progress("cables_tense")
        for i, tx in enumerate(tower_xs):
            grow = clamp((build - 0.1 * i) * 1.6)
            if grow <= 0:
                continue
            th = tower_h * grow
            p.rect(tx - tower_w, deck_y - th, tx + tower_w, deck_y,
                   fill=mix(ctx.col("metal_dark"), ctx.col("ink"), 0.4), radius=2)
            p.rect(tx - tower_w * 1.5, deck_y - th, tx + tower_w * 1.5, deck_y - th + h * 0.02,
                   fill=with_alpha(ctx.col("metal"), 0.95))
        # main cables (sagging between towers) + hangers
        anchors = [(x + w * 0.01, deck_y - h * 0.05)] + \
                  [(tx, deck_y - tower_h * 0.95) for tx in tower_xs] + \
                  [(x + w * 0.99, deck_y - h * 0.05)]
        cable_pts = []
        for i in range(len(anchors) - 1):
            a, b = anchors[i], anchors[i + 1]
            seg = sag_curve(a, b, h * 0.16, 20)
            cable_pts.extend(seg if i == 0 else seg[1:])
            draw_upto = int(len(cable_pts) * clamp(build * 1.3)) if build < 1 else len(cable_pts)
        if cable_pts:
            keep = int(len(cable_pts) * clamp(build * 1.3))
            p.line(cable_pts[: max(2, keep)], ctx.col("accent3"), width=max(3.0, h * 0.018))
            # hangers
            if tense > 0:
                for i in range(2, len(cable_pts) - 2, 4):
                    cx, cy = cable_pts[i]
                    if cy > deck_y:
                        continue
                    a = clamp(tense * 1.5 - (i / len(cable_pts)))
                    if a <= 0:
                        continue
                    p.line([(cx, cy), (cx, deck_y)], with_alpha(ctx.col("accent3"), 0.7 * a),
                           width=max(1.5, h * 0.008))
        # tension arrows pulling towers inward
        if stress and tense > 0:
            for tx in tower_xs[1:-1]:
                a = clamp(tense)
                arrow(p, (tx - w * 0.05, deck_y - tower_h * 0.6), (tx - w * 0.012, deck_y - tower_h * 0.6),
                      with_alpha(ctx.col("cool"), a), width=3, head=10)
                arrow(p, (tx + w * 0.05, deck_y - tower_h * 0.6), (tx + w * 0.012, deck_y - tower_h * 0.6),
                      with_alpha(ctx.col("cool"), a), width=3, head=10)
        if stress and tension_p > 0:
            for tx in tower_xs[1:-1]:
                arrow(p, (tx, deck_y - tower_h * 0.6), (tx, deck_y - tower_h * 0.2),
                      with_alpha(ctx.col("accent2"), clamp(tension_p)), width=3, head=10)

    def _dimension(self, p: Painter, ctx: RenderContext, x0, y0, x1, y1, label: str) -> None:
        dashed_line(p, (x0, y0), (x1, y1), with_alpha(ctx.col("glass"), 0.7), width=2, dash=10, gap=6, phase=ctx.t)
        p.line([(x0, y0 - 10), (x0, y0 + 10)], with_alpha(ctx.col("glass"), 0.8), width=2)
        p.line([(x1, y0 - 10), (x1, y0 + 10)], with_alpha(ctx.col("glass"), 0.8), width=2)
        self.label(p, ctx, (x0 + x1) / 2, y0 - ctx.stage.px(16), label, bg=False,
                   size=ctx.stage.label_size() * 0.9, color=ctx.col("glass"))

    def _el_truck(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        g = self._bridge_geometry(ctx, {"slot": el.get("slot", "deck"),
                                        "params": {"kind": (el.get("params") or {}).get("kind", "truss")}})
        # place the truck on the deck, driving when the action plays
        deck_y = g["deck_y"]
        x, w, h = g["x"], g["w"], g["h"]
        drive = ease_in_out(ctx.progress("truck_drives"))
        appear = clamp(ctx.any_progress("truck_drives", "live_load") * 2.2) or 1.0
        tx = x + w * (0.12 + 0.62 * drive)
        ty = deck_y - ctx.stage.px(1)
        deck_h = max(ctx.stage.px(9), h * 0.045)
        bw, bh = deck_h * 4.4, deck_h * 2.1
        alpha = 1.0
        # shadow
        p.ellipse(tx, ty - 2, bw * 0.6, ctx.stage.px(3), fill=with_alpha(ctx.col("shadow"), 0.5))
        # trailer
        p.rect(tx - bw * 0.5, ty - bh, tx + bw * 0.28, ty - bh * 0.18,
               fill=mix(ctx.col("paper"), ctx.col("accent2"), 0.35), radius=3)
        p.rect(tx + bw * 0.16, ty - bh * 0.95, tx + bw * 0.52, ty - bh * 0.18,
               fill=ctx.col("accent2"), radius=3)
        # cab window
        p.rect(tx + bw * 0.30, ty - bh * 0.86, tx + bw * 0.46, ty - bh * 0.55,
               fill=with_alpha(ctx.col("ink"), 0.65), radius=2)
        # wheels
        for wx in (-bw * 0.36, -bw * 0.16, bw * 0.34):
            p.ellipse(tx + wx, ty - bh * 0.10, bh * 0.20, bh * 0.20, fill=ctx.col("ink"))
            p.ellipse(tx + wx, ty - bh * 0.10, bh * 0.09, bh * 0.09, fill=with_alpha(ctx.col("metal"), 0.8))

    def _el_weight_arrows(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        kind = (el.get("params") or {}).get("kind", "dead")
        g = self._bridge_geometry(ctx, {"slot": "bridge", "params": {"kind": "beam"}})
        deck_y = g["deck_y"]
        x, w = g["x"], g["w"]
        if kind == "dead":
            prog = ctx.progress("dead_load")
            n = 5
            for i in range(n):
                u = stagger(prog, i, n, 0.8)
                if u <= 0:
                    continue
                ax = x + w * (0.12 + 0.76 * i / (n - 1))
                arrow(p, (ax, deck_y - ctx.stage.px(46) * u), (ax, deck_y - ctx.stage.px(6)),
                      with_alpha(ctx.col("accent2"), 0.9 * u), width=3, head=9)
        else:
            prog = max(ctx.progress("live_load"), ctx.progress("sum_load"), ctx.progress("truck_drives"))
            if prog > 0:
                tx = x + w * (0.12 + 0.62 * ease_in_out(ctx.progress("truck_drives")))
                arrow(p, (tx, deck_y - ctx.stage.px(64)), (tx, deck_y - ctx.stage.px(12)),
                      with_alpha(ctx.col("accent3"), 0.95), width=4, head=12)
                self.label(p, ctx, tx + ctx.stage.px(52), deck_y - ctx.stage.px(52),
                           ctx.pick("live load", "لائیو لوڈ"), bg=False,
                           size=ctx.stage.label_size() * 0.9, color=ctx.col("accent3"))

    def _el_force_arrows(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        kind = (el.get("params") or {}).get("kind", "compression")
        prog = ctx.any_progress("compression", "load_push", "load_path", "bending")
        if prog <= 0:
            return
        g = self._bridge_geometry(ctx, {"slot": "bridge", "params": {"kind": "beam"}})
        x, y, w, h, deck_y = g["x"], g["y"], g["w"], g["h"], g["deck_y"]
        e = clamp(prog)
        if kind == "compression":
            for px in (x + w * 0.33, x + w * 0.66):
                for i in range(3):
                    u = stagger(e, i, 3, 0.8)
                    if u <= 0:
                        continue
                    y0 = deck_y - ctx.stage.px(20) - i * ctx.stage.px(18) * u
                    arrow(p, (px, deck_y - ctx.stage.px(8)), (px, deck_y - ctx.stage.px(8) + ctx.stage.px(40) * u),
                          with_alpha(ctx.col("accent2"), 0.9), width=4, head=11)
            self.label(p, ctx, x + w * 0.5, deck_y + ctx.stage.px(72),
                       ctx.pick("compression", "دباؤ"), bg=True,
                       size=ctx.stage.label_size(), color=ctx.col("accent2"))
        elif kind == "bending":
            # exaggerated bending curve under the deck (schematic, not to scale)
            pts = []
            for i in range(30):
                u = i / 29
                bx = x + w * (0.02 + 0.96 * u)
                by = deck_y + math.sin(math.pi * u) * ctx.stage.px(26) * e
                pts.append((bx, by))
            p.line(pts, with_alpha(ctx.col("cool"), 0.9), width=3)
            self.label(p, ctx, x + w * 0.5, deck_y + ctx.stage.px(80),
                       ctx.pick("tension (stretched)", "کھنچاؤ"), bg=True,
                       size=ctx.stage.label_size(), color=ctx.col("cool"))
        elif kind == "tension":
            for tx in (x + w * 0.33, x + w * 0.66):
                arrow(p, (tx - ctx.stage.px(30), deck_y - ctx.stage.px(60) * e),
                      (tx, deck_y - ctx.stage.px(20) * e), with_alpha(ctx.col("cool"), 0.9), width=3, head=10)

    def _el_member_forces(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        prog = ctx.any_progress("member_forces", "load_spread")
        if prog <= 0:
            return
        g = self._bridge_geometry(ctx, {"slot": "bridge"})
        x, y, w, h, deck_y = g["x"], g["y"], g["w"], g["h"], g["deck_y"]
        truss_top = deck_y - h * (0.30 if g["kind"] == "truss" else 0.075)
        labels = [(ctx.pick("T", "T"), x + w * 0.35, truss_top - ctx.stage.px(12), ctx.col("cool")),
                  (ctx.pick("C", "C"), x + w * 0.35, deck_y + ctx.stage.px(34), ctx.col("accent2")),
                  (ctx.pick("T", "T"), x + w * 0.62, truss_top - ctx.stage.px(12), ctx.col("cool")),
                  (ctx.pick("C", "C"), x + w * 0.62, deck_y + ctx.stage.px(34), ctx.col("accent2"))]
        for i, (text, lx, ly, col) in enumerate(labels):
            u = stagger(prog, i, len(labels), 0.7)
            if u <= 0:
                continue
            p.rect(lx - ctx.stage.px(11), ly - ctx.stage.px(11), lx + ctx.stage.px(11), ly + ctx.stage.px(11),
                   fill=with_alpha(col, 0.25 * u), radius=ctx.stage.px(11),
                   outline=with_alpha(col, 0.9 * u), width=2)
            self.label(p, ctx, lx, ly, text, bg=False, size=ctx.stage.label_size(), color=col, alpha=u)

    def _el_label(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "caption_band"))
        text = ctx.label(el)
        if text:
            self.label(p, ctx, x + w / 2, y + h / 2, text,
                       size=(el.get("params") or {}).get("size", ctx.stage.label_size()))

    def _el_caption(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        self._el_label(p, ctx, el)

    def _el_arrow(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        self._el_force_arrows(p, ctx, el)

    def _el_dimension(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        g = self._bridge_geometry(ctx, {"slot": "bridge", "params": {"kind": "beam"}})
        self._dimension(p, ctx, g["x"] + g["w"] * 0.04, g["deck_y"] + ctx.stage.px(70),
                        g["x"] + g["w"] * 0.96, g["y"] + ctx.stage.px(70),
                        ctx.pick("deck", "ڈیک"))

    # ------------------------------------------------------------ foreground
    def foreground(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        # faint blueprint corner marks (technical drawing feel)
        for (cx, cy, sx, sy) in ((0, 0, 1, 1), (st.width, 0, -1, 1), (0, st.height, 1, -1),
                                 (st.width, st.height, -1, -1)):
            p.line([(cx + sx * st.px(26), cy + sy * st.px(10)), (cx + sx * st.px(26), cy + sy * st.px(26))],
                   with_alpha(ctx.col("glass"), 0.25), width=2)
            p.line([(cx + sx * st.px(10), cy + sy * st.px(26)), (cx + sx * st.px(26), cy + sy * st.px(26))],
                   with_alpha(ctx.col("glass"), 0.25), width=2)
        self.atmosphere(p, ctx, 0.35)


def palette_color(pal: Dict[str, str], key: str) -> str:
    return pal.get(key, "#000000")
