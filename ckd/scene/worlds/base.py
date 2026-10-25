"""World base classes: the contract every visual world implements.

A *world* owns one topic family's visual language: background, the parametric
objects of that domain, and how those objects animate.  Worlds are reusable
tool kits, not finished scenes: the scene plan decides which elements appear,
where they sit and which actions play.

Contract
--------
``slots(stage)``        named composition boxes for this format
``background``          layered backdrop + depth
``draw_element``        dispatch on element["type"]
``foreground``          atmosphere/vignette/particles above everything
``character_slot``      where the presenter stands, and which way it faces

Everything is drawn in layout pixels; the renderer applies the camera transform
and draws captions/headline outside it so text is never distorted.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ...gfx.painter import Painter, mix, rgba, shade, with_alpha
from ...gfx.primitives import clamp, ease_in_out, ease_out
from ...text.render import TextRenderer
from ...text.shaping import TextStyle
from ..stage import Rect, Stage

Box = Tuple[float, float, float, float]  # x, y, w, h


@dataclass
class ActionState:
    id: str
    start: float
    end: float

    def progress(self, now: float) -> float:
        if now <= self.start:
            return 0.0
        if now >= self.end:
            return 1.0
        return clamp((now - self.start) / max(1e-3, self.end - self.start))


@dataclass
class RenderContext:
    stage: Stage
    language: str
    t: float
    duration: float
    actions: List[ActionState] = field(default_factory=list)
    renderer: Optional[TextRenderer] = None
    scene_index: int = 0
    scene_count: int = 1
    purpose: str = "explain"
    rng_seed: int = 0
    elements: List[Dict] = field(default_factory=list)
    extras: Dict[str, object] = field(default_factory=dict)

    # ------------------------------------------------------------- animation
    def progress(self, action_id: str) -> float:
        for a in self.actions:
            if a.id == action_id:
                return a.progress(self.t)
        return 0.0

    def since(self, action_id: str) -> float:
        for a in self.actions:
            if a.id == action_id:
                return self.t - a.start
        return 1e6

    def active(self, action_id: str) -> bool:
        for a in self.actions:
            if a.id == action_id:
                return a.start <= self.t <= a.end
        return False

    def any_progress(self, *action_ids: str) -> float:
        return max((self.progress(a) for a in action_ids), default=0.0)

    # ------------------------------------------------------------------ text
    @property
    def palette(self) -> Dict[str, str]:
        return self.stage.palette

    def col(self, key: str, default: str = "#ffffff") -> str:
        return self.palette.get(key, default)

    def find(self, kind: str) -> Optional[Dict]:
        """First scene element of `kind` (lets props share one geometry)."""
        for el in self.elements:
            if el.get("type") == kind:
                return el
        return None

    def pick(self, en: str = "", ur: str = "") -> str:
        return ur if self.language == "ur" and ur else en

    def label(self, el: Dict) -> str:
        params = el.get("params") or {}
        return self.pick(str(params.get("en", "")), str(params.get("ur", "")))

    def labels(self, el: Dict, key: str = "labels") -> List[str]:
        params = el.get("params") or {}
        en = params.get(f"{key}_en") or []
        ur = params.get(f"{key}_ur") or []
        if self.language == "ur" and ur:
            return list(ur)
        return list(en)

    def before(self, action_id: str, t: float) -> float:
        """Progress of an action as of an arbitrary time (for animation sampling)."""
        for a in self.actions:
            if a.id == action_id:
                return a.progress(t)
        return 0.0


class World:
    id: str = "generic"
    palette_name: str = "warm"
    element_types: Tuple[str, ...] = ()

    # ------------------------------------------------------------------ layout
    def slots(self, stage: Stage) -> Dict[str, Box]:
        raise NotImplementedError

    def slot(self, stage: Stage, name: str) -> Box:
        s = self.slots(stage)
        if name in s:
            return s[name]
        # graceful fallback: centre of the world area
        wx, wy, ww, wh = stage.world_area
        return (wx + ww * 0.25, wy + wh * 0.25, ww * 0.5, wh * 0.5)

    # ------------------------------------------------------------- rendering
    def background(self, p: Painter, ctx: RenderContext) -> None:
        raise NotImplementedError

    def draw_element(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        kind = el.get("type", "")
        fn = getattr(self, f"_el_{kind}", None)
        if fn is None:
            self.unknown_element(p, ctx, el)
            return
        fn(p, ctx, el)

    def unknown_element(self, p: Painter, ctx: RenderContext, el: Dict) -> None:
        """Visible, honest fallback for an element this world cannot draw."""
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage"))
        p.rect(x + w * 0.2, y + h * 0.3, x + w * 0.8, y + h * 0.7,
               fill=with_alpha(ctx.col("ink"), 0.5), outline=with_alpha(ctx.col("accent"), 0.7), width=2, radius=8)
        self.label(p, ctx, x + w / 2, y + h / 2, f"[{el.get('type')}]", size=ctx.stage.label_size())

    def foreground(self, p: Painter, ctx: RenderContext) -> None:
        pass

    def character_slot(self, stage: Stage, name: str) -> Tuple[Tuple[float, float], int]:
        (x, y), facing = stage.character_anchor(name)
        return (x, float(y)), facing

    # --------------------------------------------------------------- helpers
    def label(self, p: Painter, ctx: RenderContext, x: float, y: float, text: str, *,
              size: float | None = None, color: str | None = None, bg: bool = True,
              align: str = "center", alpha: float = 1.0, max_width: float | None = None,
              role: str = "small") -> Box:
        """Draw a caption-style label with an optional rounded backdrop."""
        if not text or ctx.renderer is None:
            return (x, y, 0, 0)
        size = size or ctx.stage.label_size()
        color = color or ctx.col("text")
        style = TextStyle(size=size, language=ctx.language, role=role, align="center")
        mw = max_width or ctx.stage.content_w * 0.55
        from ...gfx.primitives import fit_text

        lay, style = fit_text(ctx.renderer, ctx.language, text, style, mw, size * 3.2, max_lines=3)
        w, h = lay.width, lay.height
        if align == "center":
            x0 = x - w / 2
        elif align == "right":
            x0 = x - w
        else:
            x0 = x
        y0 = y - h / 2
        if bg:
            pad = size * 0.42
            p.rect(x0 - pad, y0 - pad * 0.45, x0 + w + pad, y0 + h + pad * 0.30,
                   fill=with_alpha(ctx.col("ink"), 0.55 * alpha), radius=size * 0.42)
        ctx.renderer.draw_layout(p, lay, style, (x0 + (w - lay.width) / 2, y0), with_alpha(color, alpha))
        return (x0, y0, w, h)

    def kicker(self, p: Painter, ctx: RenderContext, text: str, x: float, y: float,
               *, align: str = "left", alpha: float = 0.9) -> float:
        """Small "PART 1 / 3" strip. Returns its width so callers can right-align."""
        if not text or ctx.renderer is None:
            return 0.0
        style = TextStyle(size=ctx.stage.kicker_size(), language=ctx.language, role="small")
        lay = ctx.renderer.layout(text, style, ctx.stage.content_w)
        x0 = x - lay.width if align == "right" else x
        ctx.renderer.draw_layout(p, lay, style, (x0, y), with_alpha(ctx.col("muted"), alpha))
        return lay.width

    def atmosphere(self, p: Painter, ctx: RenderContext, strength: float = 0.35) -> None:
        """Post-look hook.  The vignette itself is applied once on the final frame
        by the renderer (cheaper and identical), so worlds only add particles or
        grade effects here."""
        return None
