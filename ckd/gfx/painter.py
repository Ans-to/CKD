"""Supersampled 2D painter used by every visual builder.

The renderer draws in *layout pixels* at a fixed logical canvas (e.g. 1600x900)
that is supersampled by `ss` and downscaled once per frame.  All primitives take
layout coordinates; the painter multiplies internally, so art code never deals
with the supersample factor.

Design notes
  * Pillow's ImageDraw is C-implemented: fast enough for 24-30 fps at 720p on a
    free Colab CPU core.
  * `ImageDraw.Draw(im, "RGBA")` gives alpha-blended fills, needed for soft
    shading.  For crisp groups we draw into a temporary layer and composite it
    once (see `layer()`), which avoids double-blending seams.
"""
from __future__ import annotations

import math
import random
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

RGBA = Tuple[int, int, int, int]
Point = Tuple[float, float]


def rgba(color, alpha: int | None = None) -> RGBA:
    """Normalise a colour spec to RGBA."""
    if isinstance(color, str):
        from .palette import parse_color

        color = parse_color(color)
    if isinstance(color, (list, tuple)):
        if len(color) == 3:
            return (int(color[0]), int(color[1]), int(color[2]), 255 if alpha is None else alpha)
        if len(color) == 4:
            if alpha is None:
                return (int(color[0]), int(color[1]), int(color[2]), int(color[3]))
            return (int(color[0]), int(color[1]), int(color[2]), int(alpha * color[3] / 255))
    if isinstance(color, int):
        return (color, color, color, 255 if alpha is None else alpha)
    raise ValueError(f"Bad colour spec: {color!r}")


def with_alpha(color, alpha: float) -> RGBA:
    c = rgba(color)
    return (c[0], c[1], c[2], int(max(0, min(255, c[3] * alpha))))


def shade(color, factor: float, alpha: int | None = None) -> RGBA:
    c = rgba(color)
    return (
        int(max(0, min(255, c[0] * factor))),
        int(max(0, min(255, c[1] * factor))),
        int(max(0, min(255, c[2] * factor))),
        c[3] if alpha is None else alpha,
    )


def mix(c1, c2, t: float) -> RGBA:
    a, b = rgba(c1), rgba(c2)
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
        int(a[3] + (b[3] - a[3]) * t),
    )


@dataclass
class Transform:
    """Simple 2D affine transform applied to primitives inside a group."""

    tx: float = 0.0
    ty: float = 0.0
    scale: float = 1.0
    rotation: float = 0.0  # degrees, clockwise
    ox: float = 0.0
    oy: float = 0.0

    def apply(self, pts: Sequence[Point]) -> List[Point]:
        out: List[Point] = []
        rad = math.radians(self.rotation)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        for x, y in pts:
            x -= self.ox
            y -= self.oy
            x *= self.scale
            y *= self.scale
            if self.rotation:
                x, y = x * cos_a - y * sin_a, x * sin_a + y * cos_a
            x += self.ox + self.tx
            y += self.oy + self.ty
            out.append((x, y))
        return out


class Painter:
    def __init__(self, width: int, height: int, ss: int = 2, background: RGBA | None = None) -> None:
        self.width = int(width)
        self.height = int(height)
        self.ss = int(ss)
        self.image = Image.new("RGBA", (self.width * self.ss, self.height * self.ss), background or (0, 0, 0, 0))
        self._draw = ImageDraw.Draw(self.image, "RGBA")
        self._transform = Transform()
        self._stack: List[Transform] = []

    # ------------------------------------------------------------- transform
    @contextmanager
    def transformed(self, transform: Transform):
        prev = self._transform
        self._transform = transform
        try:
            yield
        finally:
            self._transform = prev

    @contextmanager
    def layer(self, alpha: float = 1.0, offset: Point = (0, 0), blur: float = 0.0):
        """Draw into an offscreen layer, composite it once with `alpha`."""
        sub = Painter(self.width, self.height, self.ss)
        prev = self._transform
        try:
            yield sub
        finally:
            self._transform = prev
        img = sub.image
        if blur > 0:
            img = img.filter(ImageFilter.GaussianBlur(blur * self.ss))
        if alpha < 1.0:
            a = img.getchannel("A").point(lambda v: int(v * alpha))
            img.putalpha(a)
        if offset != (0, 0):
            self.image.alpha_composite(img, (int(offset[0] * self.ss), int(offset[1] * self.ss)))
        else:
            self.image.alpha_composite(img)

    # --------------------------------------------------------------- helpers
    def _p(self, pts: Iterable[Point]) -> List[Tuple[float, float]]:
        scaled = self._transform.apply(list(pts))
        return [(x * self.ss, y * self.ss) for x, y in scaled]

    def _pt(self, x: float, y: float) -> Tuple[float, float]:
        return self._p([(x, y)])[0]

    def _w(self, width: float) -> int:
        return max(1, int(round(width * self.ss * self._transform.scale)))

    def _radius(self, r: float) -> float:
        return r * self.ss * self._transform.scale

    # ------------------------------------------------------------- primitives
    def polygon(self, pts: Sequence[Point], fill=None, outline=None, width: float = 0.0) -> None:
        p = self._p(pts)
        if len(p) < 3:
            return
        self._draw.polygon(p, fill=rgba(fill) if fill is not None else None)
        if outline is not None:
            closed = p + [p[0]]
            self._draw.line(closed, fill=rgba(outline), width=self._w(width or 2), joint="curve")

    def shape_path(self, pts: Sequence[Point], fill=None, outline=None, width: float = 0.0, closed: bool = True) -> None:
        p = self._p(pts)
        if closed and len(p) >= 3:
            self._draw.polygon(p, fill=rgba(fill) if fill is not None else None)
        if outline is not None:
            seq = p + ([p[0]] if closed else [])
            if len(seq) > 1:
                self._draw.line(seq, fill=rgba(outline), width=self._w(width or 2), joint="curve")

    def line(self, pts: Sequence[Point], color, width: float = 2.0, cap: str = "round") -> None:
        p = self._p(pts)
        w = self._w(width)
        if len(p) >= 2:
            self._draw.line(p, fill=rgba(color), width=w, joint="curve")
            if cap == "round":
                r = w / 2
                for x, y in (p[0], p[-1]):
                    self._draw.ellipse((x - r, y - r, x + r, y + r), fill=rgba(color))

    def rect(self, x0: float, y0: float, x1: float, y1: float, fill=None, outline=None, width: float = 0.0, radius: float = 0.0) -> None:
        a = self._pt(x0, y0)
        b = self._pt(x1, y1)
        box = (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))
        if radius > 0 and hasattr(self._draw, "rounded_rectangle"):
            self._draw.rounded_rectangle(
                box,
                radius=self._radius(radius),
                fill=rgba(fill) if fill is not None else None,
                outline=rgba(outline) if outline is not None else None,
                width=self._w(width) if outline is not None else 0,
            )
        else:
            self._draw.rectangle(
                box,
                fill=rgba(fill) if fill is not None else None,
                outline=rgba(outline) if outline is not None else None,
                width=self._w(width) if outline is not None else 0,
            )

    def ellipse(self, cx: float, cy: float, rx: float, ry: float | None = None, fill=None, outline=None, width: float = 0.0) -> None:
        ry = rx if ry is None else ry
        c = self._pt(cx, cy)
        rx_p = self._radius(rx)
        ry_p = self._radius(ry)
        box = (c[0] - rx_p, c[1] - ry_p, c[0] + rx_p, c[1] + ry_p)
        self._draw.ellipse(
            box,
            fill=rgba(fill) if fill is not None else None,
            outline=rgba(outline) if outline is not None else None,
            width=self._w(width) if outline is not None else 0,
        )

    def arc(self, cx: float, cy: float, rx: float, ry: float, start: float, end: float, color, width: float = 3.0) -> None:
        c = self._pt(cx, cy)
        box = (c[0] - self._radius(rx), c[1] - self._radius(ry), c[0] + self._radius(rx), c[1] + self._radius(ry))
        self._draw.arc(box, start, end, fill=rgba(color), width=self._w(width))

    def pie(self, cx: float, cy: float, r: float, start: float, end: float, fill=None, outline=None, width: float = 0.0) -> None:
        c = self._pt(cx, cy)
        rp = self._radius(r)
        box = (c[0] - rp, c[1] - rp, c[0] + rp, c[1] + rp)
        self._draw.pieslice(
            box,
            start,
            end,
            fill=rgba(fill) if fill is not None else None,
            outline=rgba(outline) if outline is not None else None,
            width=self._w(width) if outline is not None else 0,
        )

    def ring(self, cx: float, cy: float, r_out: float, thickness: float, color, start: float = 0.0, end: float = 360.0) -> None:
        r_in = max(0.1, r_out - thickness)
        steps = max(8, int(abs(end - start) / 6))
        outer, inner = [], []
        for i in range(steps + 1):
            a = math.radians(start + (end - start) * i / steps)
            outer.append((cx + math.cos(a) * r_out, cy + math.sin(a) * r_out))
            inner.append((cx + math.cos(a) * r_in, cy + math.sin(a) * r_in))
        self.polygon(outer + list(reversed(inner)), fill=color)

    def glow(self, cx: float, cy: float, r: float, color, alpha: float = 0.5, steps: int = 5) -> None:
        for i in range(steps, 0, -1):
            f = i / steps
            self.ellipse(cx, cy, r * f, r * f, fill=with_alpha(color, alpha / steps * (1.2 - 0.5 * f)))

    def blob(self, cx: float, cy: float, r: float, wobble: float = 0.12, points: int = 16, seed: int = 7, fill=None, outline=None, width: float = 0.0, phase: float = 0.0) -> None:
        rnd = random.Random(seed)
        radii = [1.0 + (rnd.random() - 0.5) * 2 * wobble for _ in range(points)]
        pts = []
        for i in range(points):
            a = phase + 2 * math.pi * i / points
            rr = r * radii[i]
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        self.polygon(pts, fill=fill, outline=outline, width=width)

    # -------------------------------------------------------------- texturing
    def gradient_rect(self, x0: float, y0: float, x1: float, y1: float, color_top, color_bottom, steps: int = 64) -> None:
        a = self._pt(x0, y0)
        b = self._pt(x1, y1)
        box = (int(min(a[0], b[0])), int(min(a[1], b[1])), int(max(a[0], b[0])), int(max(a[1], b[1])))
        if box[2] <= box[0] or box[3] <= box[1]:
            return
        grad = vertical_gradient(box[2] - box[0], box[3] - box[1], color_top, color_bottom)
        if rgba(color_top)[3] == 255 and rgba(color_bottom)[3] == 255:
            # opaque backdrop: a plain paste is ~40x faster than alpha_composite
            self.image.paste(grad, (box[0], box[1]))
            self._draw = ImageDraw.Draw(self.image, "RGBA")
        else:
            self.image.alpha_composite(grad, (box[0], box[1]))

    def radial_rect(self, x0: float, y0: float, x1: float, y1: float, inner, outer, cx: float = 0.5, cy: float = 0.4, power: float = 1.0) -> None:
        a = self._pt(x0, y0)
        b = self._pt(x1, y1)
        box = (int(min(a[0], b[0])), int(min(a[1], b[1])), int(max(a[0], b[0])), int(max(a[1], b[1])))
        if box[2] <= box[0] or box[3] <= box[1]:
            return
        w, h = box[2] - box[0], box[3] - box[1]
        if rgba(outer)[3] == 0:
            # additive light: premultiplied RGB + full alpha, combined with `screen`
            # (bit-exact for adds over an opaque backdrop and much cheaper)
            glow = radial_gradient(w, h, _premultiply(inner, outer), (0, 0, 0, 255), cx, cy, power)
            region = self.image.crop(box)
            self.image.paste(ImageChops.screen(region, glow), (box[0], box[1]))
            self._draw = ImageDraw.Draw(self.image, "RGBA")
        else:
            grad = radial_gradient(w, h, inner, outer, cx, cy, power)
            self.image.alpha_composite(grad, (box[0], box[1]))

    def fill(self, color) -> None:
        self._draw.rectangle((0, 0, self.image.width, self.image.height), fill=rgba(color))

    def paste_image(self, img: Image.Image, x: float, y: float, scale: float = 1.0, alpha: float = 1.0) -> None:
        """Paste an RGBA PIL image at layout coords (top-left), optionally scaled."""
        p = self._pt(x, y)
        s = scale * self.ss * self._transform.scale
        w = max(1, int(round(img.width * s)))
        h = max(1, int(round(img.height * s)))
        if (w, h) != img.size:
            img = img.resize((w, h), Image.LANCZOS)
        if alpha < 1.0:
            img = img.copy()
            a = img.getchannel("A").point(lambda v: int(v * alpha))
            img.putalpha(a)
        self.image.alpha_composite(img, (int(p[0]), int(p[1])))

    def paste_sprite(self, img: Image.Image, x: float, y: float, scale: float = 1.0, alpha: float = 1.0) -> None:
        """Paste an image that is already at supersampled resolution.

        `x`/`y` are layout coordinates of the image's top-left corner; only the
        position is multiplied by the supersample factor.
        """
        p = self._pt(x, y)
        if scale != 1.0:
            w = max(1, int(round(img.width * scale)))
            h = max(1, int(round(img.height * scale)))
            img = img.resize((w, h), Image.LANCZOS)
        if alpha < 1.0:
            img = img.copy()
            a = img.getchannel("A").point(lambda v: int(v * alpha))
            img.putalpha(a)
        self.image.alpha_composite(img, (int(round(p[0])), int(round(p[1]))))

    def paste_pixel(self, img: Image.Image, x: float, y: float, scale: float = 1.0, alpha: float = 1.0) -> None:
        """Paste with NEAREST resampling to keep pixel-art edges crisp."""
        p = self._pt(x, y)
        if scale != 1.0:
            w = max(1, int(round(img.width * scale * self.ss)))
            h = max(1, int(round(img.height * scale * self.ss)))
            img = img.resize((w, h), Image.NEAREST)
        if alpha < 1.0:
            img = img.copy()
            a = img.getchannel("A").point(lambda v: int(v * alpha))
            img.putalpha(a)
        self.image.alpha_composite(img, (int(round(p[0])), int(round(p[1]))))

    def paste_sprite_scaled(self, img: Image.Image, target_w: float, target_h: float, x: float, y: float) -> None:
        p = self._pt(x, y)
        w = max(1, int(round(target_w * self.ss)))
        h = max(1, int(round(target_h * self.ss)))
        self.image.alpha_composite(img.resize((w, h), Image.NEAREST), (int(round(p[0])), int(round(p[1]))))

    def paste_alpha(self, mask: np.ndarray, x: float, y: float, color, scale: float = 1.0) -> None:
        """Paste a float/bool alpha mask (rendered at ss resolution) tinted with `color`."""
        p = self._pt(x, y)
        if scale != 1.0:
            img = Image.fromarray((np.clip(mask, 0, 1) * 255).astype(np.uint8), "L")
            img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
            mask = np.asarray(img).astype(np.float32) / 255.0
        h, w = mask.shape[:2]
        c = rgba(color)
        patch = np.empty((h, w, 4), dtype=np.uint8)
        patch[..., 0] = c[0]
        patch[..., 1] = c[1]
        patch[..., 2] = c[2]
        patch[..., 3] = (np.clip(mask, 0, 1) * c[3]).astype(np.uint8)
        x0, y0 = int(round(p[0])), int(round(p[1]))
        self._alpha_patch(patch, x0, y0)

    def _alpha_patch(self, patch: np.ndarray, x0: int, y0: int) -> None:
        """Numpy alpha-composite of an RGBA patch with clipping."""
        h, w = patch.shape[:2]
        W, H = self.image.width, self.image.height
        sx0, sy0 = max(0, -x0), max(0, -y0)
        dx0, dy0 = max(0, x0), max(0, y0)
        dx1, dy1 = min(W, x0 + w), min(H, y0 + h)
        if dx1 <= dx0 or dy1 <= dy0:
            return
        src = patch[sy0: sy0 + (dy1 - dy0), sx0: sx0 + (dx1 - dx0)].astype(np.float32)
        dst = np.asarray(self.image)[dy0:dy1, dx0:dx1].astype(np.float32)
        sa = src[..., 3:4] / 255.0
        out = src[..., :3] * sa + dst[..., :3] * (1 - sa)
        outa = src[..., 3:4] + dst[..., 3:4] * (1 - sa)
        merged = np.concatenate([out, outa], axis=-1).astype(np.uint8)
        self.image.paste(Image.fromarray(merged, "RGBA"), (dx0, dy0))
        self._draw = ImageDraw.Draw(self.image, "RGBA")

    def noise(self, amount: float = 0.04, seed: int = 3) -> None:
        arr = np.asarray(self.image).astype(np.int16)
        rng = np.random.default_rng(seed)
        n = rng.normal(0, 255 * amount, arr.shape[:2])[..., None]
        arr[..., :3] = np.clip(arr[..., :3] + n, 0, 255)
        self.image.paste(Image.fromarray(arr.astype(np.uint8), "RGBA"))

    def vignette(self, strength: float = 0.35, color=(0, 0, 0), power: float = 2.2) -> None:
        """Darken the frame edges.

        Implemented as a channel-wise multiply so it runs as one C operation; use
        `vignette_rgb()` on the final frame where possible (4x cheaper at ss=2).
        """
        W, H = self.image.width, self.image.height
        mult = vignette_multiplier(W, H, strength, color, power)
        r, g, b, a = self.image.split()
        rgb = Image.merge("RGB", (r, g, b))
        rgb = ImageChops.multiply(rgb, mult)
        r2, g2, b2 = rgb.split()
        self.image = Image.merge("RGBA", (r2, g2, b2, a))
        self._draw = ImageDraw.Draw(self.image, "RGBA")

    # ---------------------------------------------------------------- output
    def result(self) -> Image.Image:
        """Downscale to layout resolution with high quality anti-aliasing.

        For the common ss=2 case an area-average (box) reduction is both faster
        than LANCZOS and exactly correct for 2x supersampling.
        """
        if self.ss == 1:
            return self.image
        if self.ss == 2:
            return self.image.reduce(2)
        return self.image.resize((self.width, self.height), Image.LANCZOS)

    def result_rgb(self) -> Image.Image:
        return self.result().convert("RGB")


def _premultiply(color, over) -> RGBA:
    c = rgba(color)
    a = c[3] / 255.0
    o = rgba(over)
    return (
        int(c[0] * a + o[0] * (1 - a)),
        int(c[1] * a + o[1] * (1 - a)),
        int(c[2] * a + o[2] * (1 - a)),
        255,
    )


def vignette_multiplier(w: int, h: int, strength: float = 0.35, color=(0, 0, 0),
                        power: float = 2.2) -> Image.Image:
    """Cached RGB multiplier image that darkens edges by `strength`."""
    import numpy as np

    key = ("vigmult", w, h, round(strength, 3), tuple(color), round(power, 2))
    got = _GRAD_CACHE.get(key)
    if got is not None:
        return got
    yy, xx = np.mgrid[0:h, 0:w]
    nx = (xx - w / 2) / max(1.0, w / 2)
    ny = (yy - h / 2) / max(1.0, h / 2)
    d = np.clip(np.sqrt(nx * nx + ny * ny) / 1.414, 0, 1) ** power
    c = np.array(rgba(color)[:3], np.float32)
    a = (d * strength)[..., None]
    m = 255.0 * (1 - a) + c * a
    img = Image.fromarray(np.clip(m, 0, 255).astype(np.uint8), "RGB")
    if len(_GRAD_CACHE) > 300:
        _GRAD_CACHE.clear()
    _GRAD_CACHE[key] = img
    return img


# ------------------------------------------------------------------ gradients
_GRAD_CACHE: Dict[Tuple, Image.Image] = {}


GRAD_MAX_SIDE = 320  # smooth gradients are generated small and upscaled
_UPSCALED: Dict[Tuple, Image.Image] = {}
_UPSCALED_CAP = 10  # a full-size gradient is expensive; keep the last few per video


def _upscaled(key: Tuple, img: Image.Image, w: int, h: int) -> Image.Image:
    """Return `img` resized to (w, h), memoised (a stage size repeats every frame)."""
    ck = (key, w, h)
    got = _UPSCALED.get(ck)
    if got is not None:
        return got
    out = img.resize((w, h), Image.BILINEAR)
    if len(_UPSCALED) >= _UPSCALED_CAP:
        _UPSCALED.clear()
    _UPSCALED[ck] = out
    return out


def _grad_size(w: int, h: int) -> tuple[int, int]:
    m = max(w, h, 1)
    if m <= GRAD_MAX_SIDE:
        return max(1, w), max(1, h)
    k = GRAD_MAX_SIDE / m
    return max(2, int(w * k)), max(2, int(h * k))


def vertical_gradient(w: int, h: int, top, bottom) -> Image.Image:
    gw, gh = _grad_size(w, h)
    key = ("v", gw, gh, rgba(top), rgba(bottom))
    cached = _GRAD_CACHE.get(key)
    if cached is not None:
        img = cached
    else:
        c0, c1 = np.array(rgba(top), np.float32), np.array(rgba(bottom), np.float32)
        t = np.linspace(0, 1, gh, dtype=np.float32)[:, None, None]
        arr = (c0[None, None, :] * (1 - t) + c1[None, None, :] * t)
        arr = np.repeat(arr, gw, axis=1).astype(np.uint8)
        img = Image.fromarray(arr, "RGBA")
        if len(_GRAD_CACHE) > 300:
            _GRAD_CACHE.clear()
        _GRAD_CACHE[key] = img
    if img.size != (w, h):
        return _upscaled(("v", gw, gh, rgba(top), rgba(bottom)), img, w, h)
    return img


def radial_gradient(w: int, h: int, inner, outer, cx: float = 0.5, cy: float = 0.4, power: float = 1.0) -> Image.Image:
    gw, gh = _grad_size(w, h)
    key = ("r", gw, gh, rgba(inner), rgba(outer), round(cx, 3), round(cy, 3), round(power, 2))
    cached = _GRAD_CACHE.get(key)
    if cached is not None:
        img = cached
    else:
        yy, xx = np.mgrid[0:gh, 0:gw]
        nx = (xx / max(gw - 1, 1) - cx)
        ny = (yy / max(gh - 1, 1) - cy)
        d = np.clip(np.sqrt(nx * nx + ny * ny) / 0.75, 0, 1) ** power
        c0, c1 = np.array(rgba(inner), np.float32), np.array(rgba(outer), np.float32)
        arr = c0[None, None, :] * (1 - d[..., None]) + c1[None, None, :] * d[..., None]
        img = Image.fromarray(arr.astype(np.uint8), "RGBA")
        if len(_GRAD_CACHE) > 300:
            _GRAD_CACHE.clear()
        _GRAD_CACHE[key] = img
    if img.size != (w, h):
        return _upscaled(("r", gw, gh, rgba(inner), rgba(outer), round(cx, 3), round(cy, 3), round(power, 2)),
                         img, w, h)
    return img
