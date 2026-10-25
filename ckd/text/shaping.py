"""Shaping + line layout for mixed English/Urdu text.

Why a custom engine?
  * We must guarantee correct Urdu (Nastaliq) shaping and RTL order on every
    runtime, including Pillow builds without libraqm.
  * Captions and kinetic typography need *word* granularity: every word is an
    independently animated, independently coloured sprite with known bounds.

Architecture
  text -> words (split on spaces) -> per-word script runs (arab / latin)
       -> HarfBuzz shaping per run (font units, upem scale)
       -> bidi-lite island grouping -> greedy line breaking
       -> placed words with (x, baseline_y) in layout pixels

Limitations (documented in docs/LIMITATIONS.md): full UAX#9 bracket/mirroring
resolution and kashida justification are not implemented; only word-internal
shaping and island-level reordering.  That covers caption/label use, which is
what the pipeline generates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Tuple

import uharfbuzz as hb

from .fonts import FontBook, FontRef, base_direction, font_role_for_script, script_of

# --------------------------------------------------------------------- shaping


@dataclass
class Glyph:
    gid: int
    x: float  # glyph origin x, relative to run origin, in px
    y: float  # glyph origin y (up positive), relative to baseline, in px
    cluster: int
    adv: float  # advance in px


@dataclass
class Run:
    text: str
    script: str
    direction: str
    font: FontRef
    glyphs: List[Glyph]
    width: float

    def to_dict(self) -> dict:
        return {"text": self.text, "script": self.script, "direction": self.direction, "font": self.font.key}


@dataclass
class Word:
    """A single whitespace-delimited token, shaped and ready to rasterize."""

    text: str
    runs: List[Run]
    direction: str
    width: float  # advance width in px (== layout width)
    index: int = 0  # token index in the paragraph
    char_start: int = 0
    char_end: int = 0

    @property
    def font_keys(self) -> Tuple[str, ...]:
        return tuple(r.font.key for r in self.runs)

    @property
    def scripts(self) -> Tuple[str, ...]:
        return tuple(r.script for r in self.runs)


@dataclass
class PlacedWord:
    word: Word
    x: float  # left edge of the word's advance box
    baseline: float  # y of baseline (top-down coordinates)
    line: int


@dataclass
class Line:
    words: List[PlacedWord]
    width: float
    y_top: float
    baseline: float
    height: float


@dataclass
class Layout:
    text: str
    direction: str
    lines: List[Line]
    width: float
    height: float
    words: List[PlacedWord]
    font_size: float
    line_height: float
    box_width: float

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "direction": self.direction,
            "width": round(self.width, 2),
            "height": round(self.height, 2),
            "lines": len(self.lines),
            "words": len(self.words),
        }


@dataclass
class TextStyle:
    """Text style in *output pixels* (renderer works at supersampled scale)."""

    size: float = 48.0
    language: str = "en"
    role: str = "display"  # display | body | small | pixel
    line_height: float = 1.18
    letter_spacing: float = 0.0
    weight: int | None = None
    align: str = "center"  # left | center | right | start
    max_width: float | None = None
    uppercase: bool = False

    def resolved_line_height(self) -> float:
        if self.language == "ur":
            # Nastaliq stacks glyphs vertically; needs generous leading.
            return self.size * max(self.line_height, 1.85)
        return self.size * self.line_height


def _arabic_role(style: TextStyle) -> str:
    if style.role == "small":
        return "urdu-naskh" if style.weight is None or style.weight < 600 else "urdu-naskh-bold"
    if style.role in ("display", "bold") or (style.weight or 400) >= 600:
        return "urdu-bold"
    return "urdu"


def _latin_role(style: TextStyle) -> str:
    if style.role == "pixel":
        return "pixel-bold" if (style.weight or 400) >= 600 else "pixel"
    if style.role in ("body", "small"):
        return "body-bold" if (style.weight or 400) >= 600 else "body"
    return "display" if (style.weight or 400) >= 500 else "display-light"


class TextShaper:
    def __init__(self, fonts: FontBook | None = None) -> None:
        self.fonts = fonts or FontBook()

    # ------------------------------------------------------------------ public
    def shape_word(self, text: str, style: TextStyle, index: int = 0, char_start: int = 0) -> Word:
        runs = []
        widths = []
        for seg_text, script in _script_segments(text):
            if script == "arab":
                ref = self.fonts.ref(_arabic_role(style), style.weight)
            elif script == "latin":
                ref = self.fonts.ref(_latin_role(style), style.weight)
            else:
                # neutral-only segment: borrow the surrounding language's font
                ref = self.fonts.ref(
                    _arabic_role(style) if base_direction(text) == "rtl" else _latin_role(style), style.weight
                )
            run = self._shape_run(seg_text, ref, style, script=script, rtl=(script == "arab"))
            runs.append(run)
            widths.append(run.width)
        direction = base_direction(text)
        if direction == "rtl":
            # visual order of runs inside an RTL word: reverse logical order
            runs = list(reversed(runs))
        width = sum(widths)
        return Word(
            text=text,
            runs=runs,
            direction=direction,
            width=width,
            index=index,
            char_start=char_start,
            char_end=char_start + len(text),
        )

    def layout(self, text: str, style: TextStyle, max_width: float) -> Layout:
        text = " ".join(text.split())
        if style.uppercase and style.language != "ur":
            text = text.upper()
        direction = base_direction(text)
        tokens = _tokenize(text)
        words: List[Word] = []
        space_adv = self._space_advance(style, direction)
        for tok, start in tokens:
            if tok == " ":
                continue
            words.append(self.shape_word(tok, style, index=len(words), char_start=start))
        line_h = style.resolved_line_height()

        units = _break_units(text, words, space_adv)
        lines_units = _greedy_lines(units, max_width, space_adv)
        lines: List[Line] = []
        placed_all: List[PlacedWord] = []
        y = 0.0
        for li, unit_list in enumerate(lines_units):
            line_words: List[PlacedWord] = []
            # width of the line (sum of unit widths + spaces between units)
            total = sum(u[1] for u in unit_list) + space_adv * max(0, len(unit_list) - 1)
            align = _resolve_align(style.align, direction)
            if align == "left":
                start_x = 0.0
            elif align == "right":
                start_x = max_width - total
            else:
                start_x = (max_width - total) / 2.0
            baseline = y + line_h * 0.72
            if direction == "rtl":
                # place units from the right edge moving left, words inside a unit
                # follow the unit's own direction
                cur_right = start_x + total
                for unit_words, unit_w in unit_list:
                    if unit_words and unit_words[0].direction == "ltr":
                        xw = cur_right - unit_w
                        for w in unit_words:
                            line_words.append(PlacedWord(w, xw, baseline, li))
                            xw += w.width + space_adv
                    else:
                        xr = cur_right
                        for w in unit_words:
                            xw = xr - w.width
                            line_words.append(PlacedWord(w, xw, baseline, li))
                            xr = xw - space_adv
                    cur_right -= unit_w + space_adv
            else:
                cur_left = start_x
                for unit_words, unit_w in unit_list:
                    if unit_words and unit_words[0].direction == "rtl":
                        xr = cur_left + unit_w
                        for w in unit_words:
                            xw = xr - w.width
                            line_words.append(PlacedWord(w, xw, baseline, li))
                            xr = xw - space_adv
                    else:
                        xw = cur_left
                        for w in unit_words:
                            line_words.append(PlacedWord(w, xw, baseline, li))
                            xw += w.width + space_adv
                    cur_left += unit_w + space_adv
            lines.append(
                Line(words=line_words, width=total, y_top=y, baseline=baseline, height=line_h)
            )
            placed_all.extend(line_words)
            y += line_h
        return Layout(
            text=text,
            direction=direction,
            lines=lines,
            width=max((ln.width for ln in lines), default=0.0),
            height=y if lines else 0.0,
            words=placed_all,
            font_size=style.size,
            line_height=line_h,
            box_width=max_width,
        )

    # --------------------------------------------------------------- internals
    def _shape_run(self, text: str, ref: FontRef, style: TextStyle, script: str, rtl: bool) -> Run:
        face = self.fonts.face(ref)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.direction = "rtl" if rtl else "ltr"
        buf.guess_segment_properties()
        if style.language == "ur":
            buf.language = "ur"
        features = {"kern": True, "liga": True, "calt": True, "ccmp": True, "locl": True, "rlig": True}
        hb.shape(face.hb, buf, features)
        scale = style.size / float(face.upem)
        glyphs: List[Glyph] = []
        pen = 0.0
        positions = buf.glyph_positions
        infos = buf.glyph_infos
        # HarfBuzz returns glyphs in visual order for both directions (RTL runs
        # come back left-to-right), so a plain left-to-right pen works for both.
        for i, (info, pos) in enumerate(zip(infos, positions)):
            adv = pos.x_advance * scale
            gx = pen + pos.x_offset * scale
            pen += adv
            if style.letter_spacing:
                gx += style.letter_spacing * i
            glyphs.append(
                Glyph(gid=info.codepoint, x=gx, y=pos.y_offset * scale, cluster=info.cluster, adv=adv)
            )
        width = abs(pen) + style.letter_spacing * max(0, len(glyphs) - 1)
        return Run(
            text=text,
            script=script,
            direction="rtl" if rtl else "ltr",
            font=ref,
            glyphs=glyphs,
            width=width,
        )

    def space_advance(self, style: TextStyle, direction: str) -> float:
        """Width of a single word space in px for the given style/direction."""
        return self._space_advance(style, direction)

    def _space_advance(self, style: TextStyle, direction: str) -> float:
        role = _arabic_role(style) if direction == "rtl" else _latin_role(style)
        return self._lazy_space(role, style, direction)

    def _lazy_space(self, role: str, style: TextStyle, direction: str) -> float:
        cache_key = (role, style.size, style.letter_spacing, direction)
        cached = _SPACE_CACHE.get(cache_key)
        if cached is not None:
            return cached
        ref = self.fonts.ref(role, style.weight)
        run = self._shape_run(" ", ref, style, script="neutral", rtl=(direction == "rtl"))
        width = run.width * 1.06
        _SPACE_CACHE[cache_key] = width
        return width


_SPACE_CACHE: dict = {}


def _first_strong(text: str) -> str:
    for ch in text:
        if script_of(ch) != "neutral":
            return ch
    return " "


def _script_segments(text: str) -> List[Tuple[str, str]]:
    """Split a token into arabic / latin / neutral segments for font selection.

    Neutral characters (spaces, punctuation) attach to the neighbouring segment
    so that a trailing Urdu full stop is shaped by the Urdu font.
    """
    segments: List[Tuple[str, str]] = []
    for ch in text:
        s = script_of(ch)
        if s == "neutral" and segments:
            segments[-1] = (segments[-1][0] + ch, segments[-1][1])
        elif segments and segments[-1][1] == s:
            segments[-1] = (segments[-1][0] + ch, s)
        elif segments and segments[-1][1] == "neutral":
            segments[-1] = (segments[-1][0] + ch, s)
        else:
            segments.append((ch, s))
    return segments


def _tokenize(text: str) -> List[Tuple[str, int]]:
    tokens: List[Tuple[str, int]] = []
    buf = []
    start = 0
    for i, ch in enumerate(text):
        if ch == " ":
            if buf:
                tokens.append(("".join(buf), start))
                buf = []
            tokens.append((" ", i))
        else:
            if not buf:
                start = i
            buf.append(ch)
    if buf:
        tokens.append(("".join(buf), start))
    return tokens


def _break_units(text: str, words: Sequence[Word], space_adv: float) -> List[List[Tuple[List[Word], float]]]:
    """Group words into unbreakable units.

    An island is a maximal sequence of words sharing direction. Words inside an
    island whose direction equals the paragraph direction may break (they behave
    like normal lines), while opposite-direction islands stay glued together so
    an English phrase inside Urdu is never chopped in the middle.
    """
    base = base_direction(text)
    units: List[List[Tuple[List[Word], float]]] = []
    i = 0
    n = len(words)
    while i < n:
        w = words[i]
        if w.direction == base:
            units.append([([w], w.width)])
            i += 1
            continue
        # opposite direction island: gather same-direction words
        island = [w]
        j = i + 1
        while j < n and words[j].direction != base:
            island.append(words[j])
            j += 1
        width = sum(x.width for x in island) + space_adv * (len(island) - 1)
        units.append([(island, width)])
        i = j
    return units


def _greedy_lines(
    units: List[List[Tuple[List[Word], float]]], max_width: float, space_adv: float
) -> List[List[Tuple[List[Word], float]]]:
    lines: List[List[Tuple[List[Word], float]]] = []
    cur: List[Tuple[List[Word], float]] = []
    cur_w = 0.0
    for unit in units:
        uw = unit[0][1]
        add = uw if not cur else cur_w + space_adv + uw
        if cur and add > max_width:
            lines.append(cur)
            cur = list(unit)
            cur_w = uw
        else:
            cur.extend(unit)
            cur_w = add
    if cur:
        lines.append(cur)
    return lines


def _resolve_align(align: str, direction: str) -> str:
    if align == "start":
        return "right" if direction == "rtl" else "left"
    if align == "end":
        return "left" if direction == "rtl" else "right"
    if align in ("left", "center", "right"):
        return align
    return "center"
