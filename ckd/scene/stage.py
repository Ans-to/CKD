"""Stage: canvas geometry, safe areas and typography for one format.

Landscape and vertical are *designed separately*, never cropped:
  * landscape: world occupies the central band, headline top-left, captions
    bottom-centre, character stands bottom-left/right of the world.
  * vertical:  world is stacked (sky/structures upper 60%), headline top,
    character large at the bottom third, captions just above the safe margin.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from ..gfx.palette import get_palette

Rect = Tuple[float, float, float, float]  # x, y, w, h
Box = Rect


@dataclass
class Stage:
    width: int
    height: int
    format: str = "landscape"
    fps: int = 24
    safe_x: float = 0.0
    safe_top: float = 0.0
    safe_bottom: float = 0.0
    palette: Dict[str, str] = field(default_factory=dict)
    scale: float = 1.0  # relative typography scale (1.0 == 720p height baseline)
    character_side: str = "left"  # which side the presenter stands on (layout-aware)

    def __post_init__(self) -> None:
        if self.format == "vertical":
            self.safe_x = self.width * 0.055
            self.safe_top = self.height * 0.045
            self.safe_bottom = self.height * 0.035
        else:
            self.safe_x = self.width * 0.05
            self.safe_top = self.height * 0.05
            self.safe_bottom = self.height * 0.045
        self.scale = self.height / 720.0

    # ------------------------------------------------------------------ areas
    @property
    def content_w(self) -> float:
        return self.width - 2 * self.safe_x

    @property
    def content_h(self) -> float:
        return self.height - self.safe_top - self.safe_bottom

    def px(self, v: float) -> float:
        """Scale a 720p-baseline pixel value to this stage."""
        return v * self.scale

    @property
    def headline_area(self) -> Rect:
        if self.format == "vertical":
            return (self.safe_x, self.height * 0.075, self.content_w, self.height * 0.155)
        return (self.safe_x, self.safe_top, self.content_w * 0.60, self.height * 0.22)

    @property
    def caption_area(self) -> Rect:
        if self.format == "vertical":
            return (self.safe_x, self.height * 0.805, self.content_w, self.height * 0.175)
        return (self.safe_x + self.content_w * 0.10, self.height * 0.80,
                self.content_w * 0.80, self.height * 0.135)

    @property
    def world_area(self) -> Rect:
        """Area available to topic visuals (character zone excluded).

        The presenter occupies a full-height column on one side; the world is
        laid out in the remaining space so props are never hidden behind the
        character.  Vertical videos put the character at the bottom, so the
        world keeps the full width above it.
        """
        if self.format == "vertical":
            return (0.0, self.height * 0.245, float(self.width), self.height * 0.295)
        # start below the headline band: a tall prop must never grow into the text
        top, bottom = self.height * 0.245, self.height * 0.795
        if self.character_side == "right":
            return (self.width * 0.03, top, self.width * 0.79, bottom - top)
        return (self.width * 0.19, top, self.width * 0.79, bottom - top)

    @property
    def character_height(self) -> float:
        return self.height * (0.275 if self.format == "vertical" else 0.56)

    @property
    def character_floor(self) -> float:
        return self.height * (0.795 if self.format == "vertical" else 0.905)

    def character_anchor(self, slot: str = "char_left") -> Tuple[Tuple[float, float], int]:
        """Return ((x, feet_y), facing) for a character slot.

        In landscape the stage's `character_side` wins so a scene can never ask
        for a position its props already occupy.  In vertical the presenter
        stands in a bottom corner, clear of the prop band above and the captions
        below, and always faces into the frame.
        """
        if self.format == "vertical":
            left = self.character_side != "right"
            x = self.width * (0.235 if left else 0.765)
            return ((x, self.character_floor), 1 if left else -1)
        left = self.character_side != "right"
        x = self.width * (0.115 if left else 0.885)
        return ((x, self.character_floor), 1 if left else -1)

    # -------------------------------------------------------------- type sizes
    def headline_size(self) -> float:
        return self.px(50 if self.format == "landscape" else 40)

    def caption_size(self) -> float:
        return self.px(33 if self.format == "landscape" else 31)

    def label_size(self) -> float:
        return self.px(21 if self.format == "landscape" else 20)

    def kicker_size(self) -> float:
        return self.px(16)


def make_stage(width: int, height: int, fmt: str, palette: str | Dict[str, str], fps: int = 24) -> Stage:
    pal = palette if isinstance(palette, dict) else get_palette(palette)
    return Stage(width=width, height=height, format=fmt, fps=fps, palette=pal)
