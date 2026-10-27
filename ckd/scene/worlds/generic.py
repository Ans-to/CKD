"""Generic world: topic-agnostic explanatory schematics.

Used when no curated knowledge pack exists.  It is *not* a fixed scene: the
planner supplies the concept labels and the relationships between them, and this
world draws a labelled, animated schematic (nodes, connectors, process chain,
compare columns, scale bars) in the requested palette.

Honest limitation (also surfaced to the user): without a curated pack or a local
LLM the *explanation text* is a generic scaffold and the visuals are abstract
schematics rather than topic-specific machines/structures.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

from ...gfx.painter import Painter, mix, rgba, shade, with_alpha
from ...gfx.primitives import (
    arrow, clamp, dashed_line, ease_in_out, ease_out, flow_dots, lerp, pixel_grid, stagger,
)
from ..stage import Box, Stage
from .base import RenderContext, World


class GenericWorld(World):
    id = "generic"
    palette_name = "violet"
    element_types = (
        "plate", "concept_nodes", "process_chain", "compare", "scale_bar", "icon", "label",
        "arrow", "caption", "stat_card", "question",
    )

    # ----------------------------------------------------------------- layout
    def slots(self, stage: Stage) -> Dict[str, Box]:
        wx, wy, ww, wh = stage.world_area
        pad = ww * 0.04
        plate = (wx + pad, wy + wh * 0.06, ww - pad * 2, wh * 0.86)
        s: Dict[str, Box] = {
            "back": (wx, wy, ww, wh),
            "plate": plate,
            "stage": plate,
            "stage_left": (plate[0] + plate[2] * 0.03, plate[1] + plate[3] * 0.12, plate[2] * 0.42, plate[3] * 0.72),
            "stage_right": (plate[0] + plate[2] * 0.55, plate[1] + plate[3] * 0.12, plate[2] * 0.42, plate[3] * 0.72),
            "caption_band": (plate[0], plate[1] + plate[3] * 0.84, plate[2], plate[3] * 0.14),
            "hero": (plate[0] + plate[2] * 0.10, plate[1] + plate[3] * 0.22, plate[2] * 0.80, plate[3] * 0.52),
        }
        return s

    # ------------------------------------------------------------- background
    def background(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        pal = ctx.palette
        p.gradient_rect(0, 0, st.width, st.height, pal["bg_top"], pal["bg_bottom"])
        p.radial_rect(0, 0, st.width, st.height, with_alpha(pal["sky_glow"], 30),
                      with_alpha(pal["bg_top"], 0), cx=0.5, cy=0.25, power=1.4)
        pixel_grid(p, (0, 0, st.width, st.height), with_alpha(pal["glass"], 0.06), cell=st.px(56),
                   offset=(ctx.t * 4) % st.px(56))
        # floating geometric shapes for depth
        rnd = random.Random(17)
        for i in range(5):
            bx = st.width * rnd.random()
            by = st.height * (0.1 + 0.7 * rnd.random())
            size = st.px(10 + rnd.random() * 22)
            ang = ctx.t * (0.2 + 0.2 * i) + i
            pts = [(bx + math.cos(ang + k * math.tau / 3) * size,
                    by + math.sin(ang + k * math.tau / 3) * size) for k in range(3)]
            p.polygon(pts, outline=with_alpha(pal["cool"], 0.18), width=2)

    # ---------------------------------------------------------------- objects
    def _el_plate(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "plate"))
        grow = ease_out(clamp(ctx.t / 0.5))
        ph = h * grow
        p.rect(x - 3, y - 3 + (h - ph) / 2, x + w + 3, y + ph + 3,
               fill=with_alpha(ctx.col("shadow"), 0.55), radius=ctx.stage.px(18))
        p.rect(x, y + (h - ph) / 2, x + w, y + ph, fill=with_alpha(ctx.col("ink"), 0.42),
               radius=ctx.stage.px(16), outline=with_alpha(ctx.col("cool"), 0.30), width=2)
        # corner ticks
        for (cx, cy, sx, sy) in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
            p.line([(cx + sx * 26, cy + sy * 10), (cx + sx * 26, cy + sy * 26)],
                   with_alpha(ctx.col("accent3"), 0.5), width=2)
            p.line([(cx + sx * 10, cy + sy * 26), (cx + sx * 26, cy + sy * 26)],
                   with_alpha(ctx.col("accent3"), 0.5), width=2)

    def _el_hero(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "hero"))
        text = ctx.label(el) or ""
        appear = ease_out(clamp(ctx.t / 0.6))
        style_size = ctx.stage.headline_size() * 0.72
        self.label(p, ctx, x + w / 2, y + h / 2, text, size=style_size, bg=False,
                   color=ctx.col("paper"), alpha=appear, max_width=w * 0.9)

    def _el_concept_nodes(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        labels = ctx.labels(el, "nodes")
        if not labels:
            labels = ctx.labels(el, "labels")
        if not labels:
            return
        appear = ctx.any_progress("nodes_in", "flow_recap", "process", "explain")
        n = len(labels)
        cols = 1 if n <= 2 else (2 if n <= 4 else 3)
        rows = math.ceil(n / cols)
        cw = w / cols
        ch = h / rows
        centers = []
        for i, text in enumerate(labels):
            r = i // cols
            c = i % cols
            cx = x + cw * (c + 0.5)
            cy = y + ch * (r + 0.5)
            centers.append((cx, cy))
            u = stagger(appear if appear > 0 else 1.0, i, n, 0.75)
            if u <= 0.001:
                continue
            bw, bh = cw * 0.80, ch * 0.62
            scale = 0.85 + 0.15 * ease_out(u)
            p.rect(cx - bw * scale / 2, cy - bh * scale / 2, cx + bw * scale / 2, cy + bh * scale / 2,
                   fill=with_alpha(ctx.col("ink"), 0.65 * u), radius=ctx.stage.px(14),
                   outline=with_alpha(ctx.col("cool"), 0.55 * u), width=2)
            p.rect(cx - bw * scale / 2, cy - bh * scale / 2, cx - bw * scale / 2 + ctx.stage.px(6),
                   cy + bh * scale / 2, fill=with_alpha(ctx.col("accent3"), 0.85 * u), radius=3)
            self.label(p, ctx, cx, cy, text, size=ctx.stage.label_size(), bg=False,
                       color=ctx.col("paper"), alpha=u, max_width=bw * 0.9)
        # connectors between sequential nodes
        if appear > 0 and len(centers) > 1:
            for i in range(len(centers) - 1):
                u = stagger(appear, i + 1, n, 0.75)
                if u <= 0.05:
                    continue
                a, b = centers[i], centers[i + 1]
                ax, ay = a
                bx, by = b
                if abs(ay - by) < 1:
                    pa = (ax + (bx - ax) * 0.28, ay)
                    pb = (bx - (bx - ax) * 0.28, by)
                else:
                    pa = (ax, ay + (by - ay) * 0.28)
                    pb = (bx, by - (by - ay) * 0.28)
                dashed_line(p, pa, pb, with_alpha(ctx.col("accent3"), 0.7 * u), width=2.5,
                            dash=8, gap=6, phase=ctx.t)

    def _el_process_chain(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        labels = ctx.labels(el, "nodes") or ctx.labels(el, "labels")
        if not labels:
            return
        appear = max(ctx.any_progress("process", "nodes_in", "flow_recap"), 0.0)
        n = len(labels)
        cy = y + h * 0.5
        for i, text in enumerate(labels):
            u = stagger(appear if appear > 0 else 1.0, i, n, 0.7)
            if u <= 0.001:
                continue
            cx = x + w * (0.08 + 0.84 * i / max(1, n - 1))
            r = min(w / n, h) * 0.16
            p.ellipse(cx, cy, r, r, fill=with_alpha(ctx.col("ink"), 0.7 * u),
                      outline=with_alpha(ctx.col("accent"), 0.8 * u), width=3)
            self.label(p, ctx, cx, cy + r * 1.9, text, size=ctx.stage.label_size() * 0.95,
                       bg=False, color=ctx.col("paper"), alpha=u, max_width=w / n * 0.95)
            if i < n - 1:
                u2 = stagger(appear if appear > 0 else 1.0, i + 1, n, 0.7)
                if u2 > 0.05:
                    arrow(p, (cx + r * 1.15, cy), (cx + w * 0.84 / max(1, n - 1) - r * 1.15, cy),
                          with_alpha(ctx.col("accent3"), 0.8 * u2), width=3, head=9)
                    flow_dots(p, [(cx + r * 1.15, cy), (cx + w * 0.84 / max(1, n - 1) - r * 1.15, cy)],
                              t=ctx.t, color=ctx.col("accent3"), count=2, speed=0.8, radius=2.5)

    def _el_compare(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        left = ctx.labels(el, "left") or ["A"]
        right = ctx.labels(el, "right") or ["B"]
        appear = max(ctx.any_progress("compare", "nodes_in", "explain"), 0.0)
        for side, items in ((0, left), (1, right)):
            bx = x + w * (0.04 + side * 0.50)
            bw = w * 0.42
            u = stagger(appear if appear > 0 else 1.0, side, 2, 0.85)
            if u <= 0.001:
                continue
            col = ctx.col("accent") if side == 0 else ctx.col("cool")
            p.rect(bx, y + h * 0.10, bx + bw, y + h * 0.90, fill=with_alpha(ctx.col("ink"), 0.55 * u),
                   radius=ctx.stage.px(12), outline=with_alpha(col, 0.6 * u), width=2)
            for i, item in enumerate(items[:4]):
                yy = y + h * (0.24 + 0.18 * i)
                p.ellipse(bx + bw * 0.10, yy, ctx.stage.px(4), ctx.stage.px(4), fill=with_alpha(col, u))
                self.label(p, ctx, bx + bw * 0.17, yy, item, size=ctx.stage.label_size() * 0.95,
                           bg=False, color=ctx.col("paper"), alpha=u, align="left",
                           max_width=bw * 0.78)
        p.line([(x + w * 0.5, y + h * 0.10), (x + w * 0.5, y + h * 0.90)],
               with_alpha(ctx.col("muted"), 0.35), width=2)

    def _el_scale_bar(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        frac = float((el.get("params") or {}).get("frac", 0.5))
        prog = clamp(ctx.any_progress("scale", "explain", "efficiency") or 1.0)
        bw = w * 0.7 * prog
        p.rect(x + w * 0.15, y + h * 0.45, x + w * 0.15 + bw, y + h * 0.55,
               fill=with_alpha(ctx.col("accent3"), 0.85), radius=h * 0.05)
        p.rect(x + w * 0.15, y + h * 0.45, x + w * 0.85, y + h * 0.55,
               fill=None, outline=with_alpha(ctx.col("muted"), 0.5), width=2, radius=h * 0.05)
        self.label(p, ctx, x + w * 0.5, y + h * 0.30, ctx.label(el), size=ctx.stage.label_size(),
                   bg=False, color=ctx.col("paper"))

    def _el_icon(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        spin = ctx.t * 0.6
        r = min(w, h) * 0.28
        cx, cy = x + w / 2, y + h / 2
        pts = [(cx + math.cos(spin + k * math.tau / 6) * r, cy + math.sin(spin + k * math.tau / 6) * r)
               for k in range(6)]
        p.polygon(pts, fill=with_alpha(ctx.col("cool"), 0.35), outline=with_alpha(ctx.col("accent3"), 0.8), width=3)
        self.label(p, ctx, cx, cy + r * 1.6, ctx.label(el), size=ctx.stage.label_size(), bg=False)

    def _el_stat_card(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        params = el.get("params") or {}
        value = str(params.get("value", "—"))
        caption = ctx.label(el)
        u = clamp(ctx.any_progress("stat", "explain") or 1.0)
        bw, bh = w * 0.55, h * 0.42
        cx, cy = x + w / 2, y + h / 2
        p.rect(cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2, fill=with_alpha(ctx.col("ink"), 0.6 * u),
               radius=ctx.stage.px(14), outline=with_alpha(ctx.col("accent"), 0.6 * u), width=2)
        self.label(p, ctx, cx, cy - bh * 0.12, value, size=ctx.stage.headline_size() * 0.8,
                   bg=False, color=ctx.col("accent3"), alpha=u)
        self.label(p, ctx, cx, cy + bh * 0.26, caption, size=ctx.stage.label_size(), bg=False,
                   color=ctx.col("muted"), alpha=u, max_width=bw * 0.9)

    def _el_question(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "hero"))
        text = ctx.label(el)
        if not text:
            return
        u = clamp(ctx.any_progress("question", "explain") * 1.4 or 1.0)
        self.label(p, ctx, x + w / 2, y + h / 2, text, size=ctx.stage.headline_size() * 0.62,
                   bg=False, color=ctx.col("paper"), alpha=u, max_width=w * 0.9)

    def _el_label(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "caption_band"))
        text = ctx.label(el)
        if text:
            self.label(p, ctx, x + w / 2, y + h / 2, text,
                       size=(el.get("params") or {}).get("size", ctx.stage.label_size()))

    def _el_caption(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        self._el_label(p, ctx, el)

    def _el_arrow(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        params = el.get("params") or {}
        a = self.slot(ctx.stage, params.get("from", "stage_left"))
        b = self.slot(ctx.stage, params.get("to", "stage_right"))
        t = ease_in_out(ctx.any_progress("flow_recap", "explain"))
        if t > 0:
            p0 = (a[0] + a[2] * 0.8, a[1] + a[3] * 0.5)
            p1 = (b[0] + b[2] * 0.2, b[1] + b[3] * 0.5)
            arrow(p, p0, (lerp(p0[0], p1[0], t), lerp(p0[1], p1[1], t)), ctx.col("accent3"), width=4)

    # ------------------------------------------------------------ foreground
    def foreground(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        rnd = random.Random(23)
        for i in range(18):
            bx = rnd.random() * st.width
            by = (rnd.random() * st.height + ctx.t * (4 + rnd.random() * 10)) % st.height
            p.ellipse(bx, by, 1.8, 1.8, fill=with_alpha(ctx.col("cool"), 0.18))
        self.atmosphere(p, ctx, 0.4)
