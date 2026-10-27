"""Wi-Fi / wireless networking visual world.

Parametric objects: room with depth, router (antennas + LED), phones/laptops/TVs,
emitting wave arcs, travelling packets, modulated waveform, bit stream, signal
strength bars, walls that attenuate.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

from ...gfx.painter import Painter, mix, rgba, shade, with_alpha
from ...gfx.primitives import (
    arrow, bezier_points, clamp, dashed_line, ease_in_out, ease_out, flow_dots, lerp, packet,
    perspective_floor, pixel_grid, scanlines, signal_wave, square_wave, stagger, wave_arcs, wobble,
)
from ..stage import Box, Stage
from .base import RenderContext, World


class WifiWorld(World):
    id = "wifi"
    palette_name = "tech"
    element_types = (
        "room", "router", "device", "waves", "packet", "waveform", "bit_stack", "label",
        "signal_bars", "arrow", "caption", "router_pulse",
    )

    # ----------------------------------------------------------------- layout
    def slots(self, stage: Stage) -> Dict[str, Box]:
        wx, wy, ww, wh = stage.world_area
        s: Dict[str, Box] = {}
        if stage.format == "vertical":
            s["back"] = (0, wy, ww, wh)
            s["router"] = (ww * 0.18, wy + wh * 0.06, ww * 0.42, wh * 0.30)
            s["device"] = (ww * 0.58, wy + wh * 0.52, ww * 0.34, wh * 0.38)
            s["slot_a"] = s["router"]
            s["slot_b"] = (ww * 0.56, wy + wh * 0.10, ww * 0.34, wh * 0.30)
            s["slot_c"] = (ww * 0.10, wy + wh * 0.56, ww * 0.30, wh * 0.34)
            s["slot_d"] = (ww * 0.60, wy + wh * 0.56, ww * 0.34, wh * 0.34)
            s["link"] = (ww * 0.20, wy + wh * 0.20, ww * 0.62, wh * 0.40)
            s["stage"] = (ww * 0.04, wy + wh * 0.06, ww * 0.92, wh * 0.62)
            s["stage_left"] = (ww * 0.06, wy + wh * 0.18, ww * 0.34, wh * 0.44)
            s["stage_right"] = (ww * 0.56, wy + wh * 0.30, ww * 0.36, wh * 0.44)
            s["bit_trail"] = (ww * 0.10, wy + wh * 0.72, ww * 0.62, wh * 0.16)
            s["caption_band"] = (ww * 0.04, wy + wh * 0.84, ww * 0.92, wh * 0.14)
        else:
            s["back"] = (wx, wy, ww, wh)
            s["router"] = (wx + ww * 0.04, wy + wh * 0.30, ww * 0.26, wh * 0.42)
            s["device"] = (wx + ww * 0.68, wy + wh * 0.32, ww * 0.26, wh * 0.46)
            s["slot_a"] = s["router"]
            s["slot_b"] = (wx + ww * 0.62, wy + wh * 0.14, ww * 0.26, wh * 0.34)
            s["slot_c"] = (wx + ww * 0.60, wy + wh * 0.54, ww * 0.26, wh * 0.34)
            s["slot_d"] = (wx + ww * 0.84, wy + wh * 0.20, ww * 0.16, wh * 0.30)
            s["link"] = (wx + ww * 0.22, wy + wh * 0.28, ww * 0.50, wh * 0.40)
            s["stage"] = (wx + ww * 0.06, wy + wh * 0.14, ww * 0.60, wh * 0.58)
            s["stage_left"] = (wx + ww * 0.04, wy + wh * 0.30, ww * 0.24, wh * 0.42)
            s["stage_right"] = (wx + ww * 0.66, wy + wh * 0.26, ww * 0.30, wh * 0.48)
            s["bit_trail"] = (wx + ww * 0.30, wy + wh * 0.80, ww * 0.44, wh * 0.14)
            s["caption_band"] = (wx + ww * 0.08, wy + wh * 0.82, ww * 0.84, wh * 0.14)
        return s

    # ------------------------------------------------------------- background
    def background(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        pal = ctx.palette
        wx, wy, ww, wh = st.world_area
        p.gradient_rect(0, 0, st.width, st.height, pal["bg_top"], pal["bg_bottom"])
        # back wall with a subtle grid, like a studio/room
        wall_bottom = wy + wh * 0.72
        p.rect(0, 0, st.width, wall_bottom, fill=mix(pal["bg_top"], pal["bg_bottom"], 0.45))
        pixel_grid(p, (0, 0, st.width, wall_bottom), with_alpha(pal["cool"], 0.10), cell=st.px(48),
                   offset=(ctx.t * 6) % st.px(48))
        # floor in perspective
        perspective_floor(p, (0, wall_bottom, st.width, st.height - wall_bottom),
                          pal["ground"], pal["ground_far"], t=ctx.t, lines=10)
        # wall art: three pixel blocks
        rnd = random.Random(21)
        for i in range(3):
            bx = st.width * (0.10 + i * 0.07)
            by = wy + wh * (0.08 + rnd.random() * 0.1)
            p.rect(bx, by, bx + st.px(34), by + st.px(34), fill=with_alpha(pal["accent"], 0.18 + 0.1 * i),
                   radius=6, outline=with_alpha(pal["cool"], 0.3), width=2)
        # soft rim light from the router side
        p.radial_rect(0, 0, st.width, st.height, with_alpha(pal["cool"], 26), with_alpha(pal["bg_top"], 0), cx=0.25, cy=0.45)

    # ---------------------------------------------------------------- objects
    def _el_room(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        if not (el.get("params") or {}).get("walls"):
            return
        st = ctx.stage
        wx, wy, ww, wh = st.world_area
        block_walls = clamp(ctx.progress("walls_block"))
        # three partition walls between router and device
        for i in range(3):
            u = stagger(block_walls, i, 3, 0.8)
            if u <= 0:
                continue
            x = wx + ww * (0.36 + 0.13 * i)
            top = wy + wh * (0.06 + 0.03 * i)
            bottom = wy + wh * (0.62 + 0.05 * i)
            h = (bottom - top) * u
            p.rect(x, bottom - h, x + st.px(16), bottom, fill=mix(ctx.col("metal_dark"), ctx.col("ink"), 0.55),
                   radius=4)
            p.rect(x, bottom - h, x + st.px(16), bottom - h + st.px(5), fill=with_alpha(ctx.col("metal"), 0.5),
                   radius=3)

    def _el_router(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "router"))
        boot = ease_out(ctx.progress("router_boot")) if ctx.progress("router_boot") else 1.0
        bw, bh = w * 0.66, h * 0.34 * (0.85 + 0.15 * boot)
        bx, by = x + (w - bw) / 2, y + h * 0.62
        # antennas
        for i, side in enumerate((-1, 1)):
            ax0 = bx + bw * (0.5 + side * 0.22)
            ay0 = by + bh * 0.10
            grow = clamp(boot * 1.4 - i * 0.15)
            ax1 = ax0 + side * bw * 0.12 * grow
            ay1 = ay0 - bh * 1.05 * grow
            p.line([(ax0, ay0), (ax1, ay1)], with_alpha(ctx.col("metal_dark"), 1.0), width=max(3.0, w * 0.035))
            p.ellipse(ax1, ay1, w * 0.026, w * 0.026, fill=ctx.col("accent3"))
        # body
        p.rect(bx - 4, by - 4, bx + bw + 4, by + bh + 4, fill=with_alpha(ctx.col("shadow"), 0.8), radius=10)
        p.rect(bx, by, bx + bw, by + bh, fill=mix(ctx.col("metal_dark"), ctx.col("ink"), 0.35), radius=8)
        p.rect(bx + bw * 0.06, by + bh * 0.12, bx + bw * 0.94, by + bh * 0.34,
               fill=with_alpha(ctx.col("ink"), 0.55), radius=4)
        # LEDs
        for i in range(4):
            lx = bx + bw * (0.14 + i * 0.16)
            on = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(ctx.t * (3 + i) + i))
            p.ellipse(lx, by + bh * 0.62, w * 0.018, w * 0.018,
                      fill=with_alpha([ctx.col("accent3"), ctx.col("cool"), ctx.col("plant"), ctx.col("accent2")][i],
                                      0.55 + 0.45 * on))
        # ports
        for i in range(3):
            px_ = bx + bw * (0.60 + i * 0.11)
            p.rect(px_, by + bh * 0.66, px_ + bw * 0.06, by + bh * 0.80,
                   fill=with_alpha(ctx.col("ink"), 0.7), radius=2)
        self.label(p, ctx, bx + bw / 2, by + bh + ctx.stage.px(16), ctx.pick("router", "روٹر"),
                   size=ctx.stage.label_size() * 0.9, bg=False, color=ctx.col("muted"))

    def _el_device(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "device"))
        kind = (el.get("params") or {}).get("kind", "phone")
        appear = ease_out(clamp(ctx.any_progress("devices_join", "waves_emit", "packet_arrives",
                                                 "signal_drop", "band_compare") * 1.6))
        if appear <= 0.001:
            appear = 1.0
        scale = 0.7 + 0.3 * appear
        if kind == "laptop":
            bw, bh = w * 0.70 * scale, h * 0.46 * scale
            bx, by = x + (w - bw) / 2, y + h * 0.30
            p.rect(bx - 3, by - 3, bx + bw + 3, by + bh + 3, fill=with_alpha(ctx.col("shadow"), 0.8), radius=6)
            p.rect(bx, by, bx + bw, by + bh, fill=mix(ctx.col("metal_dark"), ctx.col("ink"), 0.4), radius=4)
            p.rect(bx + bw * 0.06, by + bh * 0.08, bx + bw * 0.94, by + bh * 0.86,
                   fill=with_alpha(ctx.col("glass"), 0.55), radius=3)
            self._screen_content(p, ctx, bx + bw * 0.06, by + bh * 0.08, bw * 0.88, bh * 0.78)
            p.polygon([(bx - bw * 0.12, by + bh), (bx + bw * 1.12, by + bh),
                       (bx + bw * 1.02, by + bh * 1.16), (bx - bw * 0.02, by + bh * 1.16)],
                      fill=mix(ctx.col("metal"), ctx.col("metal_dark"), 0.4))
        elif kind == "tv":
            bw, bh = w * 0.86 * scale, h * 0.60 * scale
            bx, by = x + (w - bw) / 2, y + h * 0.16
            p.rect(bx - 4, by - 4, bx + bw + 4, by + bh + 4, fill=with_alpha(ctx.col("shadow"), 0.85), radius=8)
            p.rect(bx, by, bx + bw, by + bh, fill=mix(ctx.col("ink"), ctx.col("metal_dark"), 0.25), radius=5)
            p.rect(bx + bw * 0.04, by + bh * 0.06, bx + bw * 0.96, by + bh * 0.90,
                   fill=with_alpha(ctx.col("glass"), 0.45), radius=3)
            self._screen_content(p, ctx, bx + bw * 0.04, by + bh * 0.06, bw * 0.92, bh * 0.84)
            p.rect(bx + bw * 0.42, by + bh, bx + bw * 0.58, by + bh + h * 0.06,
                   fill=with_alpha(ctx.col("metal_dark"), 0.9))
        else:  # phone
            bw, bh = w * 0.34 * scale, h * 0.62 * scale
            bx, by = x + (w - bw) / 2, y + h * 0.22
            p.rect(bx - 4, by - 4, bx + bw + 4, by + bh + 4, fill=with_alpha(ctx.col("shadow"), 0.85), radius=12)
            p.rect(bx, by, bx + bw, by + bh, fill=mix(ctx.col("metal_dark"), ctx.col("ink"), 0.45), radius=10)
            p.rect(bx + bw * 0.08, by + bh * 0.05, bx + bw * 0.92, by + bh * 0.95,
                   fill=with_alpha(ctx.col("glass"), 0.55), radius=7)
            self._screen_content(p, ctx, bx + bw * 0.10, by + bh * 0.08, bw * 0.80, bh * 0.72)
            p.ellipse(bx + bw / 2, by + bh * 0.90, bw * 0.06, bw * 0.06,
                      fill=with_alpha(ctx.col("paper"), 0.7))
        self.label(p, ctx, x + w / 2, y + h * 0.96, ctx.pick(kind, {"phone": "فون", "laptop": "لیپ ٹاپ",
                                                                   "tv": "ٹی وی"}.get(kind, kind)),
                   size=ctx.stage.label_size() * 0.85, bg=False, color=ctx.col("muted"))

    def _screen_content(self, p: Painter, ctx: RenderContext, x: float, y: float, w: float, h: float) -> None:
        play = clamp(ctx.any_progress("packet_arrives", "decode_bits", "packets_share"))
        # video scrub bar
        p.rect(x + w * 0.08, y + h * 0.18, x + w * 0.92, y + h * 0.62,
               fill=with_alpha(ctx.col("bg_bottom"), 0.5), radius=3)
        p.ellipse(x + w * 0.5, y + h * 0.40, w * 0.10, w * 0.10,
                  fill=with_alpha(ctx.col("paper"), 0.85 if play > 0.2 else 0.4))
        p.polygon([(x + w * 0.47, y + h * 0.34), (x + w * 0.47, y + h * 0.46),
                   (x + w * 0.55, y + h * 0.40)], fill=with_alpha(ctx.col("bg_bottom"), 0.9))
        # scrub bar
        p.rect(x + w * 0.08, y + h * 0.74, x + w * 0.92, y + h * 0.79,
               fill=with_alpha(ctx.col("paper"), 0.25), radius=2)
        p.rect(x + w * 0.08, y + h * 0.74, x + w * 0.08 + w * 0.84 * max(0.05, play),
               y + h * 0.79, fill=ctx.col("accent3"), radius=2)
        # signal bars
        for i in range(3):
            bh_ = h * (0.06 + 0.03 * i)
            col = ctx.col("paper") if play > 0.1 else with_alpha(ctx.col("paper"), 0.3)
            p.rect(x + w * (0.10 + i * 0.05), y + h * 0.62 - bh_, x + w * (0.135 + i * 0.05),
                   y + h * 0.62, fill=with_alpha(col, 0.8), radius=1)

    def _el_waves(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        params = el.get("params") or {}
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "link"))
        r0_slot = self.slot(ctx.stage, "router")
        rcx = r0_slot[0] + r0_slot[2] * 0.5
        rcy = r0_slot[1] + r0_slot[3] * 0.45
        emit = ctx.any_progress("waves_emit", "frequency_shift", "packets_share", "page_zoom") or 1.0
        count = int(params.get("count", 4))
        attenuate = bool(params.get("attenuate"))
        drop = ctx.progress("signal_drop")
        facing = 1
        r_max = (x + w - rcx) if rcx < x + w else w
        base = min(w, h) * 0.20
        col = ctx.col("cool")
        for i in range(count):
            ph = ((ctx.t * 0.55) + i / count) % 1.0
            r = base * (1 + 3.4 * ph)
            a = 0.85 * (1 - ph) ** 1.3 * emit
            if attenuate:
                a *= max(0.15, 1 - drop * 1.2)
            if a <= 0.02:
                continue
            p.arc(rcx, rcy, r, r, -62, 62, with_alpha(col, a), width=max(2.5, h * 0.022))
            if params.get("band"):
                pass
        # 5 GHz vs 2.4 GHz comparison ribbons
        comp = ctx.progress("band_compare")
        if comp > 0:
            for i, (label, span, colr) in enumerate((("5 GHz", 0.55, ctx.col("accent2")),
                                                     ("2.4 GHz", 0.95, ctx.col("accent3")))):
                u = stagger(comp, i, 2, 0.7)
                if u <= 0:
                    continue
                yy = y + h * (0.30 + 0.16 * i)
                pts = []
                for k in range(24):
                    t2 = k / 23
                    pts.append((lerp(rcx, x + w * span, t2), yy + math.sin(t2 * 6.0 - ctx.t * 3) * h * 0.03))
                p.line(pts[: max(2, int(len(pts) * u))], with_alpha(colr, 0.85), width=3)
                self.label(p, ctx, x + w * span + ctx.stage.px(18), yy, label, bg=False,
                           size=ctx.stage.label_size() * 0.85, color=colr, align="left")

    def _el_packet(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "link"))
        a_slot = self.slot(ctx.stage, "router")
        b_slot = self.slot(ctx.stage, "device")
        a = (a_slot[0] + a_slot[2] * 0.8, a_slot[1] + a_slot[3] * 0.35)
        b = (b_slot[0] + b_slot[2] * 0.2, b_slot[1] + b_slot[3] * 0.35)
        prog = ctx.any_progress("packet_arrives", "packets_share", "flow_recap")
        n = 6
        for i in range(n):
            u = ((ctx.t * 0.42) + i / n) % 1.0
            if prog <= 0:
                continue
            cx = lerp(a[0], b[0], u)
            cy = a[1] + (b[1] - a[1]) * u * 0.4 - math.sin(u * math.pi) * h * 0.10
            size = max(8.0, h * 0.055)
            packet(p, cx, cy, size, ctx.col("accent3"), glow=True, alpha=0.95)

    def _el_waveform(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        params = el.get("params") or {}
        kind = params.get("kind", "modulated")
        bits = str(params.get("bits", "1011001"))
        p.rect(x, y + h * 0.12, x + w, y + h * 0.52, fill=with_alpha(ctx.col("ink"), 0.55), radius=10)
        mid = y + h * 0.38
        # carrier always present; modulation switches it
        mod = ctx.any_progress("modulate_wave", "waves_emit")
        bits_p = ctx.progress("bits_appear")
        cols = ctx.col("cool")
        # carrier sine, amplitude gated by bit pattern
        samples = 220
        step = (w * 0.92) / samples
        per = samples / max(1, len(bits))
        pts_on, pts_off = [], []
        for i in range(samples):
            u = i / (samples - 1)
            xx = x + w * 0.04 + i * step
            bit_idx = min(len(bits) - 1, int(i / per))
            on = bits[bit_idx] == "1"
            amp = h * 0.16 * (1.0 if on else 0.10)
            if mod > 0:
                amp = lerp(h * 0.16, amp, mod)
            yy = mid + math.sin(u * math.tau * 9 - ctx.t * 6) * amp
            pts_on.append((xx, yy))
        p.line(pts_on, with_alpha(cols, 0.95), width=3)
        # bit labels
        if bits_p > 0:
            size = ctx.stage.label_size() * 1.1
            for i, b in enumerate(bits):
                u = (i + 0.5) / len(bits)
                a = stagger(bits_p, i, len(bits), 0.6)
                if a <= 0:
                    continue
                xx = x + w * (0.04 + 0.92 * u)
                yy = y + h * 0.20
                p.rect(xx - size * 0.55, yy - size * 0.55, xx + size * 0.55, yy + size * 0.55,
                       fill=with_alpha(ctx.col("bg_bottom"), 0.9 * a), radius=4,
                       outline=with_alpha(ctx.col("accent3") if b == "1" else ctx.col("muted"), a), width=2)
                self.label(p, ctx, xx, yy, b, bg=False, size=size,
                           color=ctx.col("accent3") if b == "1" else ctx.col("muted"), alpha=a)

    def _el_bit_stack(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "bit_trail"))
        bits = str((el.get("params") or {}).get("bits", "1011 0100")).replace(" ", "")
        appear = ctx.any_progress("bits_appear", "decode_bits", "flow_recap")
        if appear <= 0:
            return
        n = len(bits)
        size = ctx.stage.label_size() * 1.4
        for i, b in enumerate(bits):
            u = stagger(appear, i, n, 0.75)
            if u <= 0:
                continue
            xx = x + w * (0.06 + 0.88 * i / max(1, n - 1))
            yy = y + h * 0.5 + math.sin(ctx.t * 2 + i * 0.7) * h * 0.05
            col = ctx.col("accent3") if b == "1" else ctx.col("muted")
            p.rect(xx - size * 0.5, yy - size * 0.55, xx + size * 0.5, yy + size * 0.55,
                   fill=with_alpha(col, 0.25 * u), radius=3, outline=with_alpha(col, 0.9 * u), width=2)
            self.label(p, ctx, xx, yy, b, bg=False, size=size * 0.95, color=col, alpha=u)

    def _el_signal_bars(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "caption_band"))
        level = float((el.get("params") or {}).get("level", 0.6))
        drop = ctx.progress("signal_drop")
        lvl = max(0.08, level * (1 - 0.75 * drop))
        n = 5
        bar_w = w * 0.035
        for i in range(n):
            bh_ = h * 0.55 * ((i + 1) / n)
            bx = x + w * 0.08 + i * bar_w * 1.8
            on = (i + 1) / n <= lvl + 1e-6
            p.rect(bx, y + h * 0.62 - bh_, bx + bar_w, y + h * 0.62,
                   fill=with_alpha(ctx.col("accent3") if on else ctx.col("metal_dark"), 0.95 if on else 0.35),
                   radius=2)
        self.label(p, ctx, x + w * 0.40, y + h * 0.45,
                   ctx.pick(f"signal {int(round(lvl * 100))}%", f"سگنل {int(round(lvl * 100))}%"),
                   size=ctx.stage.label_size(), bg=False, color=ctx.col("muted"), align="left")

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
        ax, ay, aw, ah = self.slot(ctx.stage, params.get("from", "stage_left"))
        bx, by, bw, bh = self.slot(ctx.stage, params.get("to", "stage_right"))
        t = ease_in_out(ctx.any_progress("flow_recap", "packets_share"))
        if t > 0:
            a = (ax + aw * 0.85, ay + ah * 0.4)
            b = (bx + bw * 0.1, by + bh * 0.4)
            arrow(p, a, (lerp(a[0], b[0], t), lerp(a[1], b[1], t)), ctx.col("accent3"), width=4)

    def _el_router_pulse(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "router"))
        p.glow(x + w / 2, y + h * 0.5, w * 0.6, ctx.col("cool"),
               alpha=0.10 + 0.12 * ctx.progress("router_boot"), steps=3)

    # ------------------------------------------------------------ foreground
    def foreground(self, p: Painter, ctx: RenderContext) -> None:
        st = ctx.stage
        scanlines(p, (0, 0, st.width, st.height), "#000000", alpha=0.045, step=max(3.0, st.px(4)))
        rnd = random.Random(9)
        for i in range(10):
            x = rnd.random() * st.width
            y = rnd.random() * st.height
            a = 0.10 + 0.12 * (0.5 + 0.5 * math.sin(ctx.t * 2 + i))
            p.ellipse(x, y, 1.6, 1.6, fill=with_alpha(ctx.col("cool"), a))
        self.atmosphere(p, ctx, 0.38)
