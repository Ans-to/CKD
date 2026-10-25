"""Reusable drawing tools shared by every visual world.

These are *tools*, not scenes: hills, wires, arrows, packets, waves, cables,
clouds, dashboard bars.  Worlds compose them per topic, so the library grows
without ever shipping a fixed set of finished scenes.
"""
from __future__ import annotations

import math
import random
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .painter import Painter, mix, rgba, shade, with_alpha

Point = Tuple[float, float]


# --------------------------------------------------------------------- easing
def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def ease_out(t: float) -> float:
    t = clamp(t)
    return 1 - (1 - t) ** 3


def ease_in(t: float) -> float:
    t = clamp(t)
    return t ** 3


def ease_out_back(t: float, s: float = 1.7) -> float:
    t = clamp(t) - 1.0
    return 1 + t * t * ((s + 1) * t + s)


def stagger(t: float, i: int, n: int, overlap: float = 0.6) -> float:
    """Per-item progress for a staggered reveal."""
    if n <= 0:
        return 1.0
    span = 1.0 - overlap
    start = span * (i / max(1, n - 1)) if n > 1 else 0.0
    return clamp((t - start) / max(0.08, overlap))


def wobble(t: float, amp: float = 1.0, freq: float = 1.0, phase: float = 0.0) -> float:
    return math.sin(t * math.tau * freq + phase) * amp


# ------------------------------------------------------------------- geometry
def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_pt(a: Point, b: Point, t: float) -> Point:
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))


def bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1 - t
    x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
    y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
    return (x, y)


def bezier_points(p0, p1, p2, p3, n: int = 24) -> List[Point]:
    return [bezier(p0, p1, p2, p3, i / (n - 1)) for i in range(n)]


def sag_curve(a: Point, b: Point, sag: float, n: int = 24) -> List[Point]:
    """Catenary-ish cable hanging between two points."""
    pts = []
    for i in range(n):
        t = i / (n - 1)
        x = lerp(a[0], b[0], t)
        y = lerp(a[1], b[1], t) + math.sin(math.pi * t) * sag
        pts.append((x, y))
    return pts


def arrow(painter: Painter, a: Point, b: Point, color, width: float = 4.0,
          head: float = 12.0, alpha: float = 1.0) -> None:
    col = with_alpha(color, alpha)
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-3:
        return
    ux, uy = dx / length, dy / length
    tip = b
    base = (tip[0] - ux * head, tip[1] - uy * head)
    painter.line([a, base], col, width=width)
    nx, ny = -uy, ux
    painter.polygon(
        [tip, (base[0] + nx * head * 0.55, base[1] + ny * head * 0.55),
         (base[0] - nx * head * 0.55, base[1] - ny * head * 0.55)],
        fill=col,
    )


def curved_arrow(painter: Painter, pts: Sequence[Point], color, width: float = 4.0,
                 head: float = 12.0, alpha: float = 1.0) -> None:
    if len(pts) < 2:
        return
    col = with_alpha(color, alpha)
    painter.line(list(pts[:-1]), col, width=width)
    arrow(painter, pts[-2], pts[-1], color, width=width * 0.9, head=head, alpha=alpha)


def dashed_line(painter: Painter, a: Point, b: Point, color, width: float = 2.0,
                dash: float = 10.0, gap: float = 8.0, phase: float = 0.0, alpha: float = 1.0) -> None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-3:
        return
    ux, uy = dx / dist, dy / dist
    col = with_alpha(color, alpha)
    d = -((phase * (dash + gap)) % (dash + gap))
    while d < dist:
        s = max(0.0, d)
        e = min(dist, d + dash)
        if e > s:
            painter.line([(a[0] + ux * s, a[1] + uy * s), (a[0] + ux * e, a[1] + uy * e)], col, width=width, cap="butt")
        d += dash + gap


# ------------------------------------------------------------------ landscapes
def hill(painter: Painter, x0: float, x1: float, base_y: float, height: float,
         color, roughness: float = 0.35, seed: int = 1, bumps: int = 3, y_offset: float = 0.0) -> None:
    rnd = random.Random(seed)
    pts = [(x0, base_y + 200)]
    n = 26
    phases = [(rnd.random() * math.tau, 0.6 + rnd.random()) for _ in range(bumps)]
    for i in range(n + 1):
        t = i / n
        x = lerp(x0, x1, t)
        h = 0.5 + 0.5 * math.sin(math.pi * t) ** 0.7
        wob = sum(math.sin(t * math.tau * (k + 1) * 1.3 + ph) * 0.18 * a for k, (ph, a) in enumerate(phases))
        y = base_y - height * h * (1 + wob * roughness) + y_offset
        pts.append((x, y))
    pts.append((x1, base_y + 200))
    painter.polygon(pts, fill=color)


def clouds(painter: Painter, area: Tuple[float, float, float, float], t: float, color,
           count: int = 4, seed: int = 3, speed: float = 6.0) -> None:
    x0, y0, w, h = area
    rnd = random.Random(seed)
    for i in range(count):
        bx = x0 + rnd.random() * w
        by = y0 + rnd.random() * h * 0.55
        s = 0.6 + rnd.random() * 0.8
        drift = (t * speed * (0.4 + rnd.random() * 0.8)) % (w + 300)
        cx = x0 - 150 + (bx - x0 + drift) % (w + 300)
        for k in range(4):
            painter.ellipse(cx + k * 26 * s - 40 * s, by + math.sin(k * 1.7) * 6 * s,
                            34 * s, 18 * s, fill=with_alpha(color, 0.55))


def sun(painter: Painter, cx: float, cy: float, r: float, *, t: float = 0.0, color="#ffe9a8",
        glow_color="#ffb347", rays: bool = True, pulse: float = 0.04) -> None:
    pulse_r = r * (1 + pulse * math.sin(t * 2.0))
    painter.glow(cx, cy, pulse_r * 3.2, glow_color, alpha=0.35, steps=6)
    if rays:
        for i in range(12):
            a = t * 0.6 + i * math.tau / 12
            r0 = pulse_r * 1.35
            r1 = pulse_r * (1.75 + 0.12 * math.sin(t * 3 + i))
            painter.line([(cx + math.cos(a) * r0, cy + math.sin(a) * r0),
                          (cx + math.cos(a) * r1, cy + math.sin(a) * r1)],
                         with_alpha(glow_color, 0.5), width=max(2.0, r * 0.07))
    painter.ellipse(cx, cy, pulse_r, pulse_r, fill=color)


def stars(painter: Painter, area: Tuple[float, float, float, float], t: float, color="#ffffff",
          count: int = 60, seed: int = 5) -> None:
    x0, y0, w, h = area
    rnd = random.Random(seed)
    for i in range(count):
        x = x0 + rnd.random() * w
        y = y0 + rnd.random() * h
        tw = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * (0.8 + rnd.random() * 2.2) + i))
        painter.ellipse(x, y, 1.4, 1.4, fill=with_alpha(color, tw * 0.8))


def ground_band(painter: Painter, x0: float, x1: float, y: float, color, pattern: str = "dots",
                t: float = 0.0, depth: float = 120.0, alpha: float = 1.0) -> None:
    painter.rect(x0, y, x1, y + depth, fill=with_alpha(color, alpha))
    if pattern == "dots":
        step = 46
        row = 0
        yy = y + 22
        while yy < y + depth:
            xx = x0 + (row % 2) * step / 2 + ((t * 6) % step)
            while xx < x1:
                painter.ellipse(xx, yy, 2.2, 2.2, fill=with_alpha(color, 0.25))
                xx += step
            yy += 34
            row += 1
    elif pattern == "lines":
        yy = y + 16
        while yy < y + depth:
            painter.line([(x0, yy), (x1, yy)], with_alpha("#000000", 0.10), width=2)
            yy += 18


def perspective_floor(painter: Painter, area: Tuple[float, float, float, float], color,
                      horizon_color, t: float = 0.0, lines: int = 12) -> None:
    x0, y0, w, h = area
    painter.gradient_rect(x0, y0, x0 + w, y0 + h, horizon_color, color)
    vp = (x0 + w / 2, y0 + h * 0.18)
    for i in range(lines + 1):
        t2 = i / lines
        x = x0 + t2 * w
        painter.line([vp, (x, y0 + h)], with_alpha("#000000", 0.08), width=1.5)
    for i in range(1, 6):
        y = vp[1] + (y0 + h - vp[1]) * (i / 5) ** 2
        painter.line([(x0, y), (x0 + w, y)], with_alpha("#000000", 0.07), width=1.5)


# ------------------------------------------------------------------ tech bits
def fit_text(renderer, shaper_lang: str, text: str, style, max_w: float, max_h: float = 1e9,
             *, max_lines: int = 3, min_scale: float = 0.55):
    """Shrink-to-fit paragraph layout used by every label/badge helper.

    Returns (layout, style).  Prevents ever clipping or overflowing a label box.
    """
    from ..text.shaping import TextStyle

    size = style.size
    while True:
        st = TextStyle(**{**style.__dict__, "size": size})
        lay = renderer.layout(text, st, max_w)
        if lay.width <= max_w + 0.5 and lay.height <= max_h + 0.5 and len(lay.lines) <= max_lines:
            return lay, st
        if size <= style.size * min_scale or size <= 9:
            return lay, st
        size *= 0.92


def wave_arcs(painter: Painter, cx: float, cy: float, r0: float, r_max: float, t: float,
              color, count: int = 4, width: float = 4.0, spread: float = 70.0,
              loops: float = 0.55, alpha: float = 1.0, facing: int = 1) -> None:
    """Emanating arcs (Wi-Fi style), animated outward with fading."""
    for i in range(count):
        p = ((t * loops) + i / count) % 1.0
        r = r0 + (r_max - r0) * p
        a = alpha * (1 - p) ** 1.4
        if a <= 0.02:
            continue
        a0 = -spread if facing >= 0 else 180 - spread
        a1 = spread if facing >= 0 else 180 + spread
        painter.arc(cx, cy, r, r, a0, a1, with_alpha(color, a), width=width)


def signal_wave(painter: Painter, x0: float, x1: float, y: float, t: float, color,
                amp: float = 18.0, freq: float = 3.0, speed: float = 2.0, width: float = 3.0,
                alpha: float = 1.0, samples: int = 60) -> None:
    pts = []
    for i in range(samples):
        u = i / (samples - 1)
        x = lerp(x0, x1, u)
        env = math.sin(math.pi * u) ** 0.5
        yy = y + math.sin((u * freq - t * speed) * math.tau) * amp * env
        pts.append((x, yy))
    painter.line(pts, with_alpha(color, alpha), width=width)


def square_wave(painter: Painter, x0: float, x1: float, y: float, amp: float, bits: str,
                t: float = 0.0, color="#ffffff", width: float = 3.0, reveal: float = 1.0) -> None:
    if not bits:
        return
    per = (x1 - x0) / len(bits)
    pts = []
    for i, b in enumerate(bits):
        if i / len(bits) > reveal:
            break
        xa, xb = x0 + i * per, x0 + (i + 1) * per
        level = y - amp if b == "1" else y + amp
        pts.append((xa, level))
        pts.append((xb, level))
    if len(pts) > 1:
        painter.line(pts, color, width=width)


def packet(painter: Painter, x: float, y: float, size: float, color, *, label: str = "",
           glow: bool = True, alpha: float = 1.0) -> None:
    if glow:
        painter.glow(x, y, size * 1.6, color, alpha=0.35 * alpha, steps=3)
    painter.rect(x - size / 2, y - size / 2, x + size / 2, y + size / 2,
                 fill=with_alpha(color, alpha), radius=size * 0.22)


def cable(painter: Painter, a: Point, b: Point, sag: float, color, width: float = 4.0,
          t: float = 0.0, sparks: int = 0, spark_color=None, progress: float = 1.0) -> None:
    pts = sag_curve(a, b, sag)
    if progress < 1.0:
        k = max(2, int(len(pts) * clamp(progress)))
        pts = pts[:k]
    painter.line(pts, color, width=width)
    if sparks and spark_color and progress >= 1.0:
        for i in range(sparks):
            u = ((t * 0.4) + i / sparks) % 1.0
            idx = int(u * (len(pts) - 1))
            x, y = pts[idx]
            painter.ellipse(x, y, width * 0.9, width * 0.9, fill=spark_color)


def flow_dots(painter: Painter, pts: Sequence[Point], t: float, color, count: int = 5,
              speed: float = 0.5, radius: float = 4.0, alpha: float = 1.0, spread: float = 0.0) -> None:
    n = len(pts)
    if n < 2:
        return
    for i in range(count):
        u = ((t * speed) + i / count) % 1.0
        idx = min(n - 1, int(u * (n - 1)))
        x, y = pts[idx]
        painter.glow(x, y, radius * 2.4, color, alpha=0.25 * alpha, steps=3)
        painter.ellipse(x, y, radius, radius, fill=with_alpha(color, alpha))


def gauge_bar(painter: Painter, x: float, y: float, w: float, h: float, frac: float,
              fill, track, *, label: str = "", radius: float | None = None) -> None:
    r = h / 2 if radius is None else radius
    painter.rect(x, y, x + w, y + h, fill=track, radius=r)
    f = clamp(frac)
    if f > 0:
        painter.rect(x, y, x + max(h, w * f), y + h, fill=fill, radius=r)


def badge(painter: Painter, cx: float, cy: float, text: str, *, fill, text_color, size: float = 18.0,
          renderer=None, alpha: float = 1.0, pad_x: float = 12.0) -> Tuple[float, float]:
    """Pill-shaped label. Returns its (w, h)."""
    if renderer is None:
        return (0.0, 0.0)
    from ..text.shaping import TextStyle

    style = TextStyle(size=size, language="en", role="small")
    lay = renderer.layout(text, style, 10000)
    w = lay.width + pad_x * 2
    h = size * 1.9
    painter.rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, fill=with_alpha(fill, alpha),
                 radius=h / 2)
    renderer.draw_layout(painter, lay, style, (cx - lay.width / 2, cy - lay.height / 2 + h * 0.06),
                         with_alpha(text_color, alpha))
    return (w, h)


def scanlines(painter: Painter, area: Tuple[float, float, float, float], color="#000000",
              alpha: float = 0.06, step: float = 4.0) -> None:
    x0, y0, w, h = area
    y = y0
    while y < y0 + h:
        painter.line([(x0, y), (x0 + w, y)], with_alpha(color, alpha), width=1)
        y += step


def pixel_grid(painter: Painter, area, color, alpha: float = 0.12, cell: float = 32.0,
               offset: float = 0.0) -> None:
    x0, y0, w, h = area
    x = x0 + (offset % cell)
    while x < x0 + w:
        painter.line([(x, y0), (x, y0 + h)], with_alpha(color, alpha), width=1)
        x += cell
    y = y0 + (offset % cell)
    while y < y0 + h:
        painter.line([(x0, y), (x0 + w, y)], with_alpha(color, alpha), width=1)
        y += cell


def gears(painter: Painter, cx: float, cy: float, r: float, teeth: int, t: float, color,
          speed: float = 1.0, tooth: float = 0.22, hole: float = 0.35) -> None:
    pts = []
    n = teeth * 2
    for i in range(n):
        a = t * speed + i * math.tau / n
        rr = r if i % 2 == 0 else r * (1 - tooth)
        pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
    painter.polygon(pts, fill=color)
    painter.ellipse(cx, cy, r * hole, r * hole, fill=(0, 0, 0, 0))
