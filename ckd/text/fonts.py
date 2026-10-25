"""Font registry: one place that maps semantic roles to bundled OFL fonts.

Shaping is done with HarfBuzz (uharfbuzz) and rasterization with FreeType
(freetype-py).  We do **not** rely on Pillow's optional libraqm build, which is
missing in many environments (including the sandbox this project was developed
in) and which in any case gives less control over bidi line layout.

Bundled fonts (all SIL Open Font License 1.1, see assets/fonts/OFL-*.txt):
  * Space Grotesk  - display / kinetic typography (Latin)
  * Inter          - UI + body text (Latin)
  * Silkscreen     - pixel-art accents (Latin)
  * Noto Nastaliq Urdu - Urdu display/captions (Arabic script, Nastaliq)
  * Noto Naskh Arabic  - small Urdu labels, mixed text, digits
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Sequence, Tuple

import freetype
import uharfbuzz as hb

DEFAULT_FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# role -> (filename, default weight, default wght axis value)
_FONT_FILES: Dict[str, Tuple[str, int, float]] = {
    "display": ("SpaceGrotesk-Variable.ttf", 700, 700),
    "display-light": ("SpaceGrotesk-Variable.ttf", 400, 400),
    "body": ("Inter-Variable.ttf", 400, 400),
    "body-bold": ("Inter-Variable.ttf", 700, 700),
    "pixel": ("Silkscreen-Regular.ttf", 400, 400),
    "pixel-bold": ("Silkscreen-Bold.ttf", 400, 400),
    "urdu": ("NotoNastaliqUrdu-Variable.ttf", 400, 400),
    "urdu-bold": ("NotoNastaliqUrdu-Variable.ttf", 700, 700),
    "urdu-naskh": ("NotoNaskhArabic-Variable.ttf", 400, 400),
    "urdu-naskh-bold": ("NotoNaskhArabic-Variable.ttf", 700, 700),
}

# Which faces to try for a given script, in order.
SCRIPT_STACKS: Dict[str, Tuple[str, ...]] = {
    "arab": ("urdu", "urdu-naskh"),
    "latin": ("display", "body", "urdu"),
}


@dataclass(frozen=True)
class FontRef:
    role: str
    path: str
    weight: int = 400
    variations: Tuple[Tuple[str, float], ...] = ()

    @property
    def key(self) -> str:
        var = ",".join(f"{k}={v}" for k, v in self.variations)
        return f"{self.role}:{self.weight}:{var}"


@dataclass
class _Face:
    ref: FontRef
    ft: freetype.Face
    hb: hb.Font
    upem: int
    has_variations: bool


class FontBook:
    """Loads fonts once and caches FreeType / HarfBuzz objects."""

    def __init__(self, font_dir: str | Path | None = None) -> None:
        self.font_dir = Path(font_dir) if font_dir else DEFAULT_FONT_DIR
        self._faces: Dict[str, _Face] = {}
        self._missing: Dict[str, Tuple[str, ...]] = {}

    # ------------------------------------------------------------------ setup
    def available(self) -> Dict[str, bool]:
        return {role: (self.font_dir / fname).exists() for role, (fname, _, _) in _FONT_FILES.items()}

    def require_fonts(self, roles: Iterable[str]) -> None:
        missing = [r for r in roles if not (self.font_dir / _FONT_FILES[r][0]).exists()]
        if missing:
            raise FileNotFoundError(
                f"Missing bundled font(s) for roles {missing} in {self.font_dir}. "
                "Restore assets/fonts (see docs/LICENSES.md) or run tools/fetch_fonts.py."
            )

    def ref(self, role: str, weight: int | None = None) -> FontRef:
        if role not in _FONT_FILES:
            raise KeyError(f"Unknown font role {role!r}. Known: {sorted(_FONT_FILES)}")
        fname, _default_weight, axis_default = _FONT_FILES[role]
        path = self.font_dir / fname
        variations: Tuple[Tuple[str, float], ...] = ()
        if weight is not None and "Variable" in fname:
            variations = (("wght", float(weight)),)
            axis = float(weight)
        else:
            axis = axis_default
        if "Variable" in fname and not variations:
            variations = (("wght", axis),)
        return FontRef(role=role, path=str(path), weight=int(axis), variations=variations)

    # --------------------------------------------------------------- internals
    def face(self, ref: FontRef) -> _Face:
        cached = self._faces.get(ref.key)
        if cached is not None:
            return cached
        if not Path(ref.path).exists():
            raise FileNotFoundError(f"Font file not found: {ref.path}")
        ft = freetype.Face(ref.path)
        has_var = hasattr(ft, "set_var_design_coords")
        if has_var and ref.variations:
            try:
                ft.set_var_design_coords([v for _n, v in ref.variations])
            except Exception:
                pass
        blob = hb.Blob.from_file_path(ref.path)
        hb_face = hb.Face(blob)
        hb_font = hb.Font(hb_face)
        if ref.variations:
            try:
                hb_font.set_variations({n: v for n, v in ref.variations})
            except Exception:
                pass
        obj = _Face(ref=ref, ft=ft, hb=hb_font, upem=hb_face.upem or 1000, has_variations=has_var)
        self._faces[ref.key] = obj
        return obj

    def has_glyph(self, ref: FontRef, codepoint: int) -> bool:
        return self.face(ref).ft.get_char_index(codepoint) != 0


# ---------------------------------------------------------------- script utils
_ARABIC_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0x08A0, 0x08FF),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
    (0x200C, 0x200F),  # ZWNJ / ZWJ / RLM / LRM
)


def is_arabic(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _ARABIC_RANGES)


def is_latin(ch: str) -> bool:
    return ch.isascii() and (ch.isalpha() or ch.isdigit())


def script_of(ch: str) -> str:
    if is_arabic(ch):
        return "arab"
    if is_latin(ch):
        return "latin"
    return "neutral"


@lru_cache(maxsize=1024)
def rtl_ratio(text: str) -> float:
    arab = sum(1 for ch in text if is_arabic(ch))
    latin = sum(1 for ch in text if is_latin(ch) and ch.isalpha())
    total = arab + latin
    return 0.0 if total == 0 else arab / total


def base_direction(text: str, override: str | None = None) -> str:
    """Very light UAX#9 P2/P3: first strong character decides, else env default."""
    if override in ("rtl", "ltr"):
        return override
    for ch in text:
        s = script_of(ch)
        if s == "arab":
            return "rtl"
        if s == "latin" and ch.isalpha():
            return "ltr"
    return "ltr"


def font_role_for_script(script: str, *, style: str = "display", language: str = "en") -> str:
    """Pick a concrete role for a script run.

    `style` is one of display / body / small.
    """
    if script == "arab":
        if style == "small":
            return "urdu-naskh"
        return "urdu-bold" if style in ("display", "bold") else "urdu"
    if style == "pixel":
        return "pixel"
    if style == "body" or style == "small":
        return "body-bold" if language == "ur" else "body"
    return "display" if language != "ur" else "display"


def default_font_dir() -> Path:
    env = os.environ.get("CKD_FONT_DIR")
    return Path(env) if env else DEFAULT_FONT_DIR
