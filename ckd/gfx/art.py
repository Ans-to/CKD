"""Premium-flat art helpers: gradients, soft shadows, rim light, sprite cache.

The first version of this project drew every prop as a flat fill with a hard
outline, which reads as clip-art.  This module holds the small vocabulary that
makes the difference:

  * **shape gradients** — a polygon or rounded rect filled with a vertical ramp,
    so surfaces catch light instead of being one flat colour;
  * **soft shadows** — a blurred silhouette offset under a prop, which is what
    actually sells depth at a glance;
  * **rim light** — a thin bright edge on the light-facing side;
  * **sprite caching** — all of the above is expensive per call, so a prop is
    rasterised once at the exact pixel size it will be drawn at, cached, and
    then pasted as a single image every frame.

Everything is drawn at the painter's supersample resolution, so the result stays
crisp when the frame is downsampled.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, Iterable, Optional, Sequence, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageFilter

Point = Tuple[float, float]

# --------------------------------------------------------------------- colours
RGB = Tuple[int, int, int]


def to_rgba(color, alpha: int = 255) -> Tuple[int, int, int, int]:
    if isinstance(color, (tuple, list)):
        if len(color) == 4:
            return (int(color[0]), int(color[1]), int(color[2]), int(color[3]))
        if len(color) == 3:
            return (int(color[0]), int(color[1]), int(color[2]), alpha)
    if isinstance(color, str):
        s = color.lstrip("#")
        if len(s) == 3:
            s = "".join(c * 2 for c in s)
        if len(s) == 6:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), alpha)
        if len(s) == 8:
            return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    raise ValueError(f"cannot parse colour {color!r}")


def mix(a, b, t: float) -> RGB:
    ca, cb = to_rgba(a), to_rgba(b)
    t = max(0.0, min(1.0, t))
    return (int(ca[0] + (cb[0] - ca[0]) * t),
            int(ca[1] + (cb[1] - ca[1]) * t),
            int(ca[2] + (cb[2] - ca[2]) * t))


def shade(color, f: float) -> RGB:
    c = to_rgba(color)
    return (max(0, min(255, int(c[0] * f))),
            max(0, min(255, int(c[1] * f))),
            max(0, min(255, int(c[2] * f))))


def alpha(color, a: float) -> Tuple[int, int, int, int]:
    c = to_rgba(color)
    a = max(0.0, min(1.0, a))
    return (c[0], c[1], c[2], int(c[3] * a))


# ------------------------------------------------------------------ gradients
def vertical_gradient(top, bottom, size: Tuple[int, int], power: float = 1.0) -> Image.Image:
    """RGB image with a vertical ramp between two colours."""
    w, h = size
    c0, c1 = to_rgba(top), to_rgba(bottom)
    img = Image.new("RGB", (1, max(2, h)))
    px = img.load()
    for y in range(img.height):
        t = (y / (img.height - 1)) ** power
        px[0, y] = (int(c0[0] + (c1[0] - c0[0]) * t),
                    int(c0[1] + (c1[1] - c0[1]) * t),
                    int(c0[2] + (c1[2] - c0[2]) * t))
    return img.resize((w, h), Image.BILINEAR)


def radial_glow(size: Tuple[int, int], color, cx: float = 0.5, cy: float = 0.5,
                radius: float = 0.7, power: float = 1.6) -> Image.Image:
    """RGBA image: soft radial falloff of `color` on transparent."""
    w, h = size
    small = (max(2, w // 8), max(2, h // 8))
    img = Image.new("RGBA", small, (0, 0, 0, 0))
    px = img.load()
    c = to_rgba(color)
    for y in range(small[1]):
        for x in range(small[0]):
            dx = (x / small[0] - cx) * (small[0] / small[1])
            dy = y / small[1] - cy
            d = math.sqrt(dx * dx + dy * dy) / max(1e-4, radius)
            a = max(0.0, 1.0 - d) ** power
            if a > 0.002:
                px[x, y] = (c[0], c[1], c[2], int(a * c[3]))
    return img.resize((w, h), Image.BICUBIC)


# ---------------------------------------------------------------------- masks
def _bbox(points: Sequence[Point], pad: float = 2.0) -> Tuple[int, int, int, int]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (int(math.floor(min(xs) - pad)), int(math.floor(min(ys) - pad)),
            int(math.ceil(max(xs) + pad)), int(math.ceil(max(ys) + pad)))


def polygon_mask(points: Sequence[Point], size: Tuple[int, int], offset: Point = (0, 0),
                 blur: float = 0.0) -> Image.Image:
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.polygon([(p[0] - offset[0], p[1] - offset[1]) for p in points], fill=255)
    if blur > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    return mask


def rounded_mask(box, radius: float, size: Tuple[int, int], offset: Point = (0, 0),
                 blur: float = 0.0) -> Image.Image:
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0 - offset[0], y0 - offset[1], x1 - offset[0], y1 - offset[1]),
                        radius=radius, fill=255)
    if blur > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    return mask


# ----------------------------------------------------------------- sprite cache
class SpriteCache:
    """Rasterise a prop once at its final pixel size, then paste it every frame.

    `draw` receives a PIL canvas covering exactly the prop's box at supersampled
    resolution, plus the origin offset, and painting happens in layout pixels
    (the canvas is scaled by `ss`).  Keys must capture everything that changes the
    pixels — a caller that forgets an input simply re-renders too often, it never
    draws stale art.
    """

    def __init__(self, limit: int = 160) -> None:
        self._items: Dict[tuple, Tuple[Image.Image, float, float]] = {}
        self.limit = limit
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple, box: Tuple[float, float, float, float], ss: int,
            draw: Callable[[Image.Image, float, float, int], None]) -> Tuple[Image.Image, float, float]:
        """Return (image, origin_x_in_layout, origin_y_in_layout)."""
        cached = self._items.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        x0, y0, x1, y1 = box
        w = max(1, int(math.ceil((x1 - x0) * ss)))
        h = max(1, int(math.ceil((y1 - y0) * ss)))
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw(img, x0, y0, ss)
        if len(self._items) > self.limit:
            self._items.clear()
        record = (img, x0, y0)
        self._items[key] = record
        return record


def draw_gradient_polygon(img: Image.Image, points: Sequence[Point], top, bottom,
                          offset: Point = (0, 0), power: float = 1.0) -> None:
    """Fill a polygon with a vertical gradient (all coords in canvas pixels)."""
    local = [(p[0] - offset[0], p[1] - offset[1]) for p in points]
    bx0, by0, bx1, by1 = _bbox(local, pad=1)
    w, h = max(1, bx1 - bx0), max(1, by1 - by0)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(p[0] - bx0, p[1] - by0) for p in local], fill=255)
    grad = vertical_gradient(top, bottom, (w, h), power=power).convert("RGBA")
    grad.putalpha(mask)
    img.alpha_composite(grad, (bx0, by0))


def draw_gradient_round(img: Image.Image, box, radius: float, top, bottom,
                        offset: Point = (0, 0), power: float = 1.0) -> None:
    x0, y0, x1, y1 = box
    bx0, by0 = int(math.floor(x0 - offset[0])), int(math.floor(y0 - offset[1]))
    bx1, by1 = int(math.ceil(x1 - offset[0])), int(math.ceil(y1 - offset[1]))
    w, h = max(1, bx1 - bx0), max(1, by1 - by0)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((x0 - offset[0] - bx0, y0 - offset[1] - by0,
                                            x1 - offset[0] - bx0, y1 - offset[1] - by0),
                                           radius=radius, fill=255)
    grad = vertical_gradient(top, bottom, (w, h), power=power).convert("RGBA")
    grad.putalpha(mask)
    img.alpha_composite(grad, (bx0, by0))


def draw_soft_shadow(img: Image.Image, points: Sequence[Point], offset: Point = (0, 0),
                     dx: float = 0.0, dy: float = 14.0, blur: float = 10.0,
                     color=(12, 8, 24), strength: float = 0.45) -> None:
    """Blurred silhouette offset under a prop."""
    local = [(p[0] - offset[0] + dx, p[1] - offset[1] + dy) for p in points]
    bx0, by0, bx1, by1 = _bbox(local, pad=blur * 3 + 4)
    bx0, by0 = min(bx0, 0), min(by0, 0)
    bx1, by1 = max(bx1, img.width), max(by1, img.height)
    w, h = bx1 - bx0, by1 - by0
    layer = Image.new("L", (w, h), 0)
    ImageDraw.Draw(layer).polygon([(p[0] - bx0, p[1] - by0) for p in local], fill=255)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    c = to_rgba(color)
    tint = Image.new("RGBA", (w, h), (c[0], c[1], c[2], int(255 * strength)))
    tint.putalpha(ImageChops.multiply(layer, tint.getchannel("A")))
    img.alpha_composite(tint, (bx0, by0))


def draw_rim(img: Image.Image, points: Sequence[Point], color, offset: Point = (0, 0),
             width: float = 3.0, strength: float = 0.5, light_from: str = "left") -> None:
    """Bright edge along the light-facing side of an already painted shape.

    Implemented by intersecting the shape's mask with a shifted copy of itself,
    which gives a clean inner edge whatever the shape is.
    """
    local = [(p[0] - offset[0], p[1] - offset[1]) for p in points]
    bx0, by0, bx1, by1 = _bbox(local, pad=width * 3 + 4)
    w, h = max(1, bx1 - bx0), max(1, by1 - by0)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([(p[0] - bx0, p[1] - by0) for p in local], fill=255)
    shift = int(round(width * 1.6))
    if light_from == "left":
        inner = ImageChops.offset(mask, shift, shift // 2)
    elif light_from == "right":
        inner = ImageChops.offset(mask, -shift, shift // 2)
    else:
        inner = ImageChops.offset(mask, 0, shift)
    edge = ImageChops.subtract(mask, inner).filter(ImageFilter.GaussianBlur(0.6))
    c = to_rgba(color)
    layer = Image.new("RGBA", (w, h), (c[0], c[1], c[2], 255))
    layer.putalpha(ImageChops.multiply(edge, Image.new("L", (w, h), int(255 * strength))))
    img.alpha_composite(layer, (bx0, by0))


def draw_gloss(img: Image.Image, box, offset: Point = (0, 0), strength: float = 0.16) -> None:
    """A soft diagonal highlight across a surface (glass, metal, screen)."""
    x0, y0, x1, y1 = box
    local = (x0 - offset[0], y0 - offset[1], x1 - offset[0], y1 - offset[1])
    w, h = int(local[2] - local[0]), int(local[3] - local[1])
    if w <= 0 or h <= 0:
        return
    grad = Image.linear_gradient("L").rotate(35, expand=True).resize((w, h), Image.BILINEAR)
    band = grad.point(lambda v: int(strength * 255 * max(0.0, math.sin(v / 255.0 * math.pi))))
    gloss = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    gloss.putalpha(band)
    img.alpha_composite(gloss, (int(local[0]), int(local[1])))


def rounded_polygon(points: Sequence[Point], radius: float, steps: int = 4) -> Sequence[Point]:
    """Round the corners of a polygon by inserting arc points (cheap smoothing)."""
    n = len(points)
    if n < 3 or radius <= 0:
        return points
    out = []
    for i in range(n):
        p_prev = points[(i - 1) % n]
        p_cur = points[i]
        p_next = points[(i + 1) % n]
        v1 = (p_prev[0] - p_cur[0], p_prev[1] - p_cur[1])
        v2 = (p_next[0] - p_cur[0], p_next[1] - p_cur[1])
        l1 = math.hypot(*v1) or 1.0
        l2 = math.hypot(*v2) or 1.0
        r = min(radius, l1 * 0.45, l2 * 0.45)
        a = (p_cur[0] + v1[0] / l1 * r, p_cur[1] + v1[1] / l1 * r)
        b = (p_cur[0] + v2[0] / l2 * r, p_cur[1] + v2[1] / l2 * r)
        for k in range(steps + 1):
            t = k / steps
            x = (1 - t) ** 2 * a[0] + 2 * (1 - t) * t * p_cur[0] + t ** 2 * b[0]
            y = (1 - t) ** 2 * a[1] + 2 * (1 - t) * t * p_cur[1] + t ** 2 * b[1]
            out.append((x, y))
    return out


def smooth_path(points: Sequence[Point], closed: bool = False, tension: float = 0.5) -> Sequence[Point]:
    """Catmull-Rom resampling for organic silhouettes (hills, dunes, blobs)."""
    pts = list(points)
    if len(pts) < 3:
        return pts
    if closed:
        pts = [pts[-1]] + pts + [pts[0], pts[1]]
    else:
        pts = [pts[0]] + pts + [pts[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(6):
            t = k / 6.0
            t2, t3 = t * t, t * t * t
            x = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
            y = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
            out.append((x, y))
    out.append(pts[-2])
    return out


SPRITES = SpriteCache()
