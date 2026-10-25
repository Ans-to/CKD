"""Rasterization of shaped words into cached sprites.

Words are rasterized once per (word, style, size, supersample) into an alpha
mask; colour, outline and shadow are applied when drawing so that highlight
animations are cheap.  Captions and kinetic titles animate these sprites.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import freetype
import numpy as np
from PIL import Image, ImageFilter

from .fonts import FontBook
from .shaping import (
    Layout, Line, PlacedWord, Run, TextStyle, TextShaper, Word, base_direction,
    _resolve_align,
)
from .fonts import is_arabic

LOAD_FLAGS = freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING


@dataclass
class WordMask:
    mask: np.ndarray  # float32 0..1, supersampled pixels
    ox: float  # x of mask left edge relative to the word origin (layout px)
    oy: float  # y of mask top edge relative to the baseline (layout px, +down)
    width: float  # in layout px
    height: float
    ss: int

    @property
    def advance(self) -> float:
        return self.width


@dataclass
class StyledSprite:
    image: Image.Image  # supersampled RGBA
    ox: float
    oy: float

    @property
    def size(self) -> Tuple[int, int]:
        return self.image.size


class TextRenderer:
    def __init__(self, shaper: TextShaper | None = None, ss: int = 2) -> None:
        self.shaper = shaper or TextShaper()
        self.ss = ss
        self._mask_cache: Dict[tuple, WordMask] = {}
        self._sprite_cache: Dict[tuple, StyledSprite] = {}
        self._measure_cache: Dict[tuple, Tuple[float, float]] = {}
        self._layout_cache: Dict[tuple, Layout] = {}
        self._size_cache: Dict[tuple, None] = {}

    # ------------------------------------------------------------------ masks
    def _apply_size(self, run: Run, style: TextStyle) -> freetype.Face:
        face = self.shaper.fonts.face(run.font)
        px = style.size * self.ss
        key = (run.font.key, round(px, 2))
        if key not in self._size_cache:
            face.ft.set_char_size(int(round(px * 64)), 0, 72, 72)
            self._size_cache[key] = None
        return face.ft

    def word_mask(self, word: Word, style: TextStyle) -> WordMask:
        key = (
            word.text,
            tuple(r.font.key for r in word.runs),
            round(style.size, 2),
            round(style.letter_spacing, 3),
            self.ss,
        )
        cached = self._mask_cache.get(key)
        if cached is not None:
            return cached
        ss = self.ss
        glyphs: List[Tuple[np.ndarray, int, int]] = []
        cursor = 0.0
        x_min = math.inf
        y_min = math.inf
        x_max = -math.inf
        y_max = -math.inf
        for run in word.runs:
            ft = self._apply_size(run, style)
            # HarfBuzz emits glyphs left-to-right (visual order) for RTL too, so the
            # run always starts at the current pen position.
            run_origin = cursor
            for g in run.glyphs:
                try:
                    ft.load_glyph(g.gid, LOAD_FLAGS)
                except Exception:
                    continue
                bmp = ft.glyph.bitmap
                if bmp.width == 0 or bmp.rows == 0:
                    continue
                buf = np.array(bmp.buffer, dtype=np.uint8, copy=True)
                if bmp.pitch != bmp.width:
                    buf = buf.reshape((bmp.rows, bmp.pitch))[:, : bmp.width]
                else:
                    buf = buf.reshape((bmp.rows, bmp.width))
                gx = (run_origin + g.x) * ss
                gy = -g.y * ss
                x0 = int(round(gx)) + ft.glyph.bitmap_left
                y0 = int(round(gy)) - ft.glyph.bitmap_top
                glyphs.append((buf, x0, y0))
                x_min = min(x_min, x0)
                y_min = min(y_min, y0)
                x_max = max(x_max, x0 + buf.shape[1])
                y_max = max(y_max, y0 + buf.shape[0])
            cursor += run.width
        if not glyphs:
            empty = np.zeros((1, 1), dtype=np.float32)
            wm = WordMask(mask=empty, ox=0.0, oy=0.0, width=word.width, height=0.0, ss=ss)
            self._mask_cache[key] = wm
            return wm
        pad = 2
        W = int(x_max - x_min) + pad * 2
        H = int(y_max - y_min) + pad * 2
        acc = np.zeros((H, W), dtype=np.uint8)
        for buf, x0, y0 in glyphs:
            dx = x0 - int(x_min) + pad
            dy = y0 - int(y_min) + pad
            h, w = buf.shape
            region = acc[dy: dy + h, dx: dx + w]
            np.maximum(region, buf, out=region)
        wm = WordMask(
            mask=acc.astype(np.float32) / 255.0,
            ox=(int(x_min) - pad) / ss,
            oy=(int(y_min) - pad) / ss,
            width=W / ss,
            height=H / ss,
            ss=ss,
        )
        if len(self._mask_cache) > 6000:
            self._mask_cache.clear()
        self._mask_cache[key] = wm
        return wm

    # ---------------------------------------------------------------- sprites
    def word_sprite(
        self,
        word: Word,
        style: TextStyle,
        fill,
        outline=None,
        outline_width: float = 0.0,
        shadow: Optional[Tuple[float, float, float, float]] = None,
    ) -> StyledSprite:
        """RGBA sprite with colour/outline/shadow baked in (cached)."""
        key = (
            word.text,
            tuple(r.font.key for r in word.runs),
            round(style.size, 2),
            str(fill),
            str(outline),
            round(outline_width, 2),
            str(shadow),
            self.ss,
        )
        cached = self._sprite_cache.get(key)
        if cached is not None:
            return cached
        wm = self.word_mask(word, style)
        mask = wm.mask
        from ..gfx.palette import parse_color

        fill_c = parse_color(fill) if not isinstance(fill, tuple) or len(fill) != 4 else tuple(int(c) for c in fill)
        out_c = parse_color(outline) if outline is not None else None
        arr = np.zeros(mask.shape[:2] + (4,), dtype=np.uint8)
        arr[..., 0] = fill_c[0]
        arr[..., 1] = fill_c[1]
        arr[..., 2] = fill_c[2]
        arr[..., 3] = (np.clip(mask, 0, 1) * fill_c[3]).astype(np.uint8)
        img = Image.fromarray(arr, "RGBA")
        if out_c is not None and outline_width > 0:
            radius = max(1, int(round(outline_width * self.ss)))
            m = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
            dil = Image.fromarray(m, "L").filter(ImageFilter.MaxFilter(radius * 2 + 1))
            oarr = np.zeros(arr.shape, dtype=np.uint8)
            oarr[..., 0] = out_c[0]
            oarr[..., 1] = out_c[1]
            oarr[..., 2] = out_c[2]
            oarr[..., 3] = (np.asarray(dil).astype(np.float32) / 255.0 * out_c[3]).astype(np.uint8)
            img = Image.alpha_composite(Image.fromarray(oarr, "RGBA"), img)
        if shadow is not None:
            sx, sy, blur, alpha = shadow
            m = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
            sh = Image.fromarray(m, "L")
            if blur > 0:
                sh = sh.filter(ImageFilter.GaussianBlur(blur * self.ss))
            sarr = np.zeros(arr.shape, dtype=np.uint8)
            sarr[..., 3] = (np.asarray(sh).astype(np.float32) * alpha).astype(np.uint8)
            shadow_img = Image.fromarray(sarr, "RGBA")
            pad = int(abs(sx) * self.ss) + int(blur * self.ss * 2) + 4
            canvas = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
            canvas.alpha_composite(shadow_img, (pad + int(sx * self.ss), pad + int(sy * self.ss)))
            canvas.alpha_composite(img, (pad, pad))
            img = canvas
            ox = wm.ox - pad / self.ss
            oy = wm.oy - pad / self.ss
        else:
            ox, oy = wm.ox, wm.oy
        sprite = StyledSprite(image=img, ox=ox, oy=oy)
        if len(self._sprite_cache) > 4000:
            self._sprite_cache.clear()
        self._sprite_cache[key] = sprite
        return sprite

    # ---------------------------------------------------------------- metrics
    def measure(self, word: Word, style: TextStyle) -> Tuple[float, float]:
        """(ink_left, ink_width) of a word relative to its advance origin.

        Nastaliq and pixel fonts overhang their advance box substantially, so
        layout must use real ink extents or words collide.
        """
        key = (
            word.text,
            tuple(r.font.key for r in word.runs),
            round(style.size, 2),
            round(style.letter_spacing, 3),
            self.ss,
        )
        cached = self._measure_cache.get(key)
        if cached is not None:
            return cached
        wm = self.word_mask(word, style)
        ink_w = max(wm.width, word.width * 0.6)
        result = (wm.ox, ink_w)
        self._measure_cache[key] = result
        return result

    # ------------------------------------------------------------------ layout
    def layout(self, text: str, style: TextStyle, max_width: float) -> Layout:
        """Bidi-aware, ink-aware paragraph layout at output pixel resolution.

        Implements a pragmatic subset of UAX#9: per-token direction classes,
        neutral resolution (N1/N2), level assignment (I1/I2 simplified for one
        level of nesting), greedy line breaking over same-level units and L2
        visual reordering.  Words (not glyphs) are the atomic unit, which is
        exactly what animated captions and kinetic type need.
        """
        text = " ".join(text.split())
        if style.uppercase and style.language != "ur":
            text = text.upper()
        cache_key = (
            text, style.size, style.language, style.role, style.line_height, style.letter_spacing,
            style.weight, style.align, round(max_width, 2), style.uppercase,
        )
        cached = self._layout_cache.get(cache_key)
        if cached is not None:
            return cached
        direction = base_direction(text)
        base_level = 0 if direction == "ltr" else 1
        tokens = [t for t in text.split(" ") if t]
        words: List[Word] = []
        pos = 0
        for tok in tokens:
            words.append(self.shaper.shape_word(tok, style, index=len(words), char_start=pos))
            pos += len(tok) + 1
        if not words:
            return Layout(
                text=text, direction=direction, lines=[], width=0.0, height=0.0, words=[],
                font_size=style.size, line_height=style.resolved_line_height(), box_width=max_width,
            )
        space_adv = self.shaper.space_advance(style, direction)
        ink = [self.measure(w, style) for w in words]
        # Natural typography advances words by their advance width, but Nastaliq
        # and pixel fonts overhang their advance box.  We keep the advance origin
        # as the placement anchor and reserve the full ink extent as the slot so
        # neighbouring words can never collide.
        adv = [w.width for w in words]
        slots = []
        for k in range(len(words)):
            ox, ink_w = ink[k]
            slot = max(adv[k], ox + ink_w) + max(0.0, -ox)
            slots.append(slot)
        levels = _resolve_levels(words, base_level)

        # ---- break units: words at the paragraph level may break individually,
        # embedded opposite-direction islands stay glued together (so an English
        # phrase inside Urdu is never chopped in the middle).
        units: List[Tuple[List[int], float]] = []
        i = 0
        n = len(words)
        while i < n:
            if levels[i] == base_level:
                units.append(([i], slots[i]))
                i += 1
                continue
            j = i + 1
            while j < n and levels[j] != base_level:
                j += 1
            idxs = list(range(i, j))
            width = sum(slots[k] for k in idxs) + space_adv * (len(idxs) - 1)
            units.append((idxs, width))
            i = j

        # ---- greedy line breaking in logical order
        lines_units: List[List[Tuple[List[int], float]]] = []
        cur: List[Tuple[List[int], float]] = []
        cur_w = 0.0
        for unit in units:
            add = unit[1] if not cur else cur_w + space_adv + unit[1]
            if cur and add > max_width and cur_w > 0:
                lines_units.append(cur)
                cur = [unit]
                cur_w = unit[1]
            else:
                cur.append(unit)
                cur_w = add
        if cur:
            lines_units.append(cur)

        line_h = style.resolved_line_height()
        lines: List[Line] = []
        placed_all: List[PlacedWord] = []
        y = 0.0
        for li, unit_list in enumerate(lines_units):
            idxs_logical: List[int] = [k for idxs, _w in unit_list for k in idxs]
            visual = _reorder_l2(idxs_logical, levels)
            # collision-aware natural spacing: advance normally, but never let the
            # ink boxes of neighbouring words overlap (Nastaliq overhangs).
            rel: List[Tuple[int, float]] = []
            pen = 0.0
            for pos, k in enumerate(visual):
                ink_left, ink_w = ink[k]
                x_adv = pen + max(0.0, -ink_left)
                ink_right = x_adv + ink_left + ink_w
                rel.append((k, x_adv))
                pen = max(pen + adv[k] + space_adv, ink_right + space_adv * 0.55)
            if rel:
                total = max(
                    max(x + adv[k] + max(0.0, ink[k][0] + ink[k][1] - adv[k]) for k, x in rel),
                    rel[-1][1] + adv[rel[-1][0]],
                )
            else:
                total = 0.0
            align = _resolve_align(style.align, direction)
            if align == "left":
                start_x = 0.0
            elif align == "right":
                start_x = max_width - total
            else:
                start_x = (max_width - total) / 2.0
            baseline = y + line_h * 0.72
            line_words: List[PlacedWord] = []
            for k, x_adv in rel:
                line_words.append(PlacedWord(words[k], start_x + x_adv, baseline, li))
            lines.append(Line(words=line_words, width=total, y_top=y, baseline=baseline, height=line_h))
            placed_all.extend(line_words)
            y += line_h
        # Alignment is solved inside the full `max_width` box, but `width` reports the
        # ink width of the widest line. Callers place the block with `x + word.x`, so
        # re-origin every line on the widest line: otherwise a short line in a wide box
        # is pushed right (landscape captions drifted and clipped off-frame).
        widest = max((ln.width for ln in lines), default=0.0)
        slack = max_width - widest
        if align == "center":
            shift = -slack / 2.0
        elif align == "right":
            shift = -slack
        else:
            shift = 0.0
        if abs(shift) > 0.01:
            for ln in lines:
                for i, pw in enumerate(ln.words):
                    ln.words[i] = PlacedWord(pw.word, pw.x + shift, pw.baseline, pw.line)
            placed_all = [pw for ln in lines for pw in ln.words]
        result = Layout(
            text=text, direction=direction, lines=lines,
            width=widest, height=y,
            words=placed_all, font_size=style.size, line_height=line_h, box_width=max_width,
        )
        if len(self._layout_cache) > 600:
            self._layout_cache.clear()
        self._layout_cache[cache_key] = result
        return result

    # ------------------------------------------------------------------ draw
    def draw_word(
        self,
        painter,
        word: Word,
        style: TextStyle,
        x: float,
        baseline: float,
        fill,
        *,
        scale: float = 1.0,
        alpha: float = 1.0,
        dy: float = 0.0,
        dx: float = 0.0,
        pivot: str = "center",
        outline=None,
        outline_width: float = 0.0,
        shadow=None,
        ink_pos: bool = False,
    ) -> Tuple[float, float, float, float]:
        """Draw one word sprite; returns its layout-space ink box (x0,y0,x1,y1)."""
        sprite = self.word_sprite(word, style, fill, outline, outline_width, shadow)
        ox, oy = sprite.ox, sprite.oy
        if scale != 1.0:
            if pivot == "center":
                cx = word.width / 2.0
                ox = ox * scale + cx * (1 - scale)
                oy = oy * scale
            else:
                ox = ox * scale
                oy = oy * scale
        # x is the word's advance origin; the sprite carries its own ink offset.
        px = (x if ink_pos else x + ox) + dx
        py = baseline + dy + oy
        painter.paste_sprite(sprite.image, px, py, scale=scale, alpha=alpha)
        return (px, py, px + sprite.image.width / self.ss * scale, py + sprite.image.height / self.ss * scale)

    def draw_layout(
        self,
        painter,
        layout: Layout,
        style: TextStyle,
        origin: Tuple[float, float],
        fill,
        *,
        word_style: Optional[Callable[[PlacedWord, int], dict]] = None,
        outline=None,
        outline_width: float = 0.0,
        shadow=None,
    ) -> List[Tuple[float, float, float, float]]:
        """Draw a full paragraph. `word_style(word, index)` may return per-word
        overrides: {fill, scale, alpha, dx, dy, pivot}."""
        x0, y0 = origin
        boxes = []
        for i, pw in enumerate(layout.words):
            overrides = word_style(pw, i) if word_style else {}
            boxes.append(
                self.draw_word(
                    painter,
                    pw.word,
                    style,
                    x0 + pw.x,
                    y0 + pw.baseline,
                    overrides.get("fill", fill),
                    scale=overrides.get("scale", 1.0),
                    alpha=overrides.get("alpha", 1.0),
                    dx=overrides.get("dx", 0.0),
                    dy=overrides.get("dy", 0.0),
                    pivot=overrides.get("pivot", "center"),
                    outline=overrides.get("outline", outline),
                    outline_width=overrides.get("outline_width", outline_width),
                    shadow=overrides.get("shadow", shadow),
                )
            )
        return boxes


def measure_paragraph(shaper: TextShaper, text: str, style: TextStyle, max_width: float) -> Layout:
    return shaper.layout(text, style, max_width)


# --------------------------------------------------------------------- bidi
def _token_class(word: Word) -> str:
    """R = Arabic letters, L = Latin letters, EN = digits, N = neutral."""
    arab = latin = digit = 0
    for ch in word.text:
        if is_arabic(ch) and ch.isalpha():
            arab += 1
        elif ch.isascii() and ch.isalpha():
            latin += 1
        elif ch.isdigit():
            digit += 1
    if arab and not latin:
        return "R"
    if latin and not arab:
        return "L"
    if arab and latin:
        return "L" if word.direction == "ltr" else "R"
    if digit:
        return "EN"
    return "N"


def _resolve_levels(words: Sequence[Word], base_level: int) -> List[int]:
    classes = [_token_class(w) for w in words]
    n = len(classes)
    # N1/N2: neutral takes the surrounding direction if both sides agree,
    # otherwise the embedding (paragraph) direction.  European numbers inside an
    # RTL paragraph render LTR (level 2).
    resolved = list(classes)
    i = 0
    while i < n:
        if classes[i] != "N":
            i += 1
            continue
        j = i
        while j < n and classes[j] == "N":
            j += 1
        before = resolved[i - 1] if i > 0 else None
        after = classes[j] if j < n else None
        if before == after and before in ("R", "L"):
            fill = before
        elif before == "R" and after is None:
            fill = "R" if base_level == 1 else "L"
        elif before is None and after == "R":
            fill = "R" if base_level == 1 else "L"
        else:
            fill = "R" if base_level == 1 else "L"
        for k in range(i, j):
            resolved[k] = fill
        i = j
    levels: List[int] = []
    for cls in resolved:
        if cls == "R":
            levels.append(base_level if base_level == 1 else 1)
        elif cls == "L":
            levels.append(0 if base_level == 0 else 2)
        else:  # EN
            levels.append(2 if base_level == 1 else 0)
    return levels


def _reorder_l2(logical: Sequence[int], levels: Sequence[int]) -> List[int]:
    """UAX#9 rule L2: reverse contiguous runs from the highest level down to the
    lowest odd level."""
    order = list(logical)
    lvl = [levels[k] for k in logical]
    if not order:
        return order
    highest = max(lvl)
    odd = [v for v in lvl if v % 2 == 1]
    if not odd:
        return order
    lowest_odd = min(odd)
    for level in range(highest, lowest_odd - 1, -1):
        i = 0
        while i < len(order):
            if lvl[i] >= level:
                j = i
                while j < len(order) and lvl[j] >= level:
                    j += 1
                order[i:j] = order[i:j][::-1]
                lvl[i:j] = lvl[i:j][::-1]
                i = j
            else:
                i += 1
    return order
