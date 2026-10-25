"""Scene renderer: composes one scene of a video, frame by frame.

Layer order
    background (world) -> topic objects -> camera-transformed world layer ->
    character (pixel-art, animated) -> kinetic headline -> captions ->
    foreground/atmosphere -> intro/outro transition

Captions and headline are drawn *outside* the camera transform so they never
distort or drift outside the safe area.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

from ..gfx.character import CHARACTER
from ..gfx.painter import Painter, Transform, mix, rgba, shade, with_alpha
from ..gfx.primitives import clamp, ease_in_out, ease_out, ease_out_back, lerp, stagger, wobble
from ..text.render import TextRenderer, StyledSprite
from ..text.shaping import TextStyle
from ..voice.base import WordTiming
from ..voice.narration import SceneAudio
from ..content.schema import Scene
from .stage import Stage
from .timing import CaptionCue, assign_actions, build_captions
from .worlds.base import ActionState, RenderContext, World

# --------------------------------------------------------------------- camera
CAMERAS = ("push_in", "pull_out", "pan_right", "pan_left", "drift", "static", "tilt_up")


@dataclass
class CameraState:
    scale: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0


def camera_at(kind: str, phase: float, stage: Stage) -> CameraState:
    """Camera move sampled at scene phase (0..1)."""
    e = ease_in_out(phase)
    if kind == "push_in":
        return CameraState(1.0 + 0.075 * e, -stage.width * 0.012 * e, -stage.height * 0.008 * e)
    if kind == "pull_out":
        return CameraState(1.075 - 0.075 * e, stage.width * 0.012 * (1 - e), 0)
    if kind == "pan_right":
        return CameraState(1.045, -stage.width * 0.030 * (e - 0.5), 0)
    if kind == "pan_left":
        return CameraState(1.045, stage.width * 0.030 * (e - 0.5), 0)
    if kind == "tilt_up":
        return CameraState(1.04, 0, stage.height * 0.026 * (e - 0.35))
    if kind == "drift":
        return CameraState(1.02, math.sin(phase * math.pi * 1.2) * stage.width * 0.008,
                           math.cos(phase * math.pi) * stage.height * 0.006)
    return CameraState(1.0, 0.0, 0.0)


@dataclass
class SceneRenderSpec:
    scene: Scene
    stage: Stage
    language: str
    narration: SceneAudio
    world: World
    renderer: TextRenderer
    scene_index: int = 0
    scene_count: int = 1
    include_captions: bool = True
    include_character: bool = True
    seed: int = 7
    total_title: str = ""
    supersample: int | None = None  # defaults to the text renderer's supersample

    @property
    def duration(self) -> float:
        return self.narration.duration


URDU_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _autosize(renderer: TextRenderer, text: str, style: TextStyle, max_w: float, max_h: float,
              *, min_size: float = 12.0, max_lines: int = 3):
    """Shrink the font size until the paragraph fits the box (no clipped text)."""
    size = style.size
    while size >= min_size:
        st = TextStyle(**{**style.__dict__, "size": size})
        lay = renderer.layout(text, st, max_w)
        if lay.width <= max_w + 0.5 and lay.height <= max_h + 0.5 and len(lay.lines) <= max_lines:
            return lay, st
        size *= 0.93
    st = TextStyle(**{**style.__dict__, "size": min_size})
    return renderer.layout(text, st, max_w), st


class SceneRenderer:
    def __init__(self, spec: SceneRenderSpec) -> None:
        self.spec = spec
        # per-scene stage: the character side changes the world layout, and stages
        # are shared between scenes, so never mutate the incoming stage.
        side = "left"
        if spec.include_character:
            slot = (spec.scene.character or {}).get("slot", "char_left")
            side = "right" if str(slot).endswith("right") else "left"
        self.stage = replace(spec.stage, character_side=side)
        spec = replace(spec, stage=self.stage)
        self.spec = spec
        self.world = spec.world
        self.renderer = spec.renderer
        self.actions: List[ActionState] = assign_actions(
            spec.scene, spec.narration, scene_duration=spec.duration
        )
        self.cues: List[CaptionCue] = build_captions(
            spec.narration.words, scene_duration=spec.duration
        )
        self.headline_words = self._prepare_headline()
        self.keyword_set = {k.lower() for k in (spec.scene.keywords.get(spec.language) or [])}
        self._blink_times = self._make_blinks()

    # ------------------------------------------------------------------ setup
    def _prepare_headline(self) -> List[Tuple[str, bool]]:
        text = self.spec.scene.headline_for(self.spec.language)
        if not text:
            return []
        kw = {k.lower() for k in (self.spec.scene.keywords.get(self.spec.language) or [])}
        out = []
        for w in text.split():
            clean = w.strip("،,.:;!?؟۔").lower()
            out.append((w, clean in kw))
        return out

    def _make_blinks(self) -> List[float]:
        rng = np.random.default_rng(self.spec.seed + self.spec.scene_index)
        times = []
        t = 1.2 + float(rng.random() * 1.5)
        while t < self.spec.duration:
            times.append(t)
            t += 2.4 + float(rng.random() * 2.6)
        return times

    # --------------------------------------------------------------- drawing
    def context(self, t: float) -> RenderContext:
        return RenderContext(
            stage=self.stage,
            language=self.spec.language,
            t=t,
            duration=self.spec.duration,
            actions=self.actions,
            renderer=self.renderer,
            scene_index=self.spec.scene_index,
            scene_count=self.spec.scene_count,
            purpose=self.spec.scene.purpose,
            rng_seed=self.spec.seed,
            elements=list(self.spec.scene.elements),
        )

    def render(self, t: float, *, painter: Optional[Painter] = None) -> Image.Image:
        t = max(0.0, min(self.spec.duration - 1e-4, t))
        ctx = self.context(t)
        # the painter and the text renderer must share the supersample factor, or
        # glyph sprites and layout coordinates disagree (text half-size + gaps).
        ss = painter.ss if painter is not None else (self.spec.supersample or self.renderer.ss)
        p = painter or Painter(self.stage.width, self.stage.height, ss=ss,
                               background=rgba(self.stage.palette["bg_top"]))
        if painter is None:
            p.image.paste(Image.new("RGBA", p.image.size, rgba(self.stage.palette["bg_top"])), (0, 0))
        phase = t / max(1e-3, self.spec.duration)

        # ---- world (camera-transformed)
        cam = camera_at(self.spec.scene.camera, phase, self.stage)
        intro = clamp(t / 0.42)
        outro = clamp((self.spec.duration - t) / 0.34)
        layer_alpha = min(intro, outro) ** 0.8
        with p.transformed(Transform(tx=cam.pan_x, ty=cam.pan_y, scale=cam.scale,
                                     ox=self.stage.width / 2, oy=self.stage.height / 2)):
            self.world.background(p, ctx)
            for el in self.spec.scene.elements:
                self.world.draw_element(p, ctx, el)

        # ---- character (outside camera so it 'stands' in the frame)
        if self.spec.include_character:
            self._draw_character(p, ctx, t)

        # ---- typography
        self._draw_headline(p, ctx, t)
        if self.spec.include_captions:
            self._draw_captions(p, ctx, t)

        # ---- foreground + transition
        with p.transformed(Transform(ox=self.stage.width / 2, oy=self.stage.height / 2)):
            self.world.foreground(p, ctx)
        self._draw_transition(p, t, layer_alpha)
        img = p.result()
        # vignette at output resolution: identical look, a quarter of the pixels
        from ..gfx.painter import ImageChops as _IC, vignette_multiplier

        r, g, b, a = img.split()
        rgb = _IC.multiply(Image.merge("RGB", (r, g, b)),
                           vignette_multiplier(self.stage.width, self.stage.height, 0.30))
        return rgb

    # ------------------------------------------------------------- character
    def _speaking(self, t: float) -> Tuple[bool, float]:
        for cue in self.cues:
            for w in cue.words:
                if w.start <= t <= w.end:
                    return True, clamp((w.end - t) / max(0.12, w.end - w.start))
        return False, 0.0

    def _draw_character(self, p: Painter, ctx: RenderContext, t: float) -> None:
        char = self.spec.scene.character or {}
        slot = char.get("slot", "char_left")
        pose = char.get("pose", "present")
        (x, floor), facing = self.stage.character_anchor(slot)
        speaking, _ = self._speaking(t)
        # mouth flaps while words are being spoken, blink on schedule
        mouth = "open" if speaking and (int(t * 11) % 3 != 0) else ("smile" if not speaking else "small")
        blink = any(abs(t - b) < 0.09 for b in self._blink_times)
        ent = ease_out_back(clamp(t / 0.55))
        bounce = 0.0
        if speaking:
            bounce = 0.85 + 0.15 * math.sin(t * 9.0)
        exit_p = clamp((self.spec.duration - t) / 0.3)
        alpha = min(1.0, ent * exit_p)
        # subtle idle sway
        sway = math.sin(t * 1.6) * self.stage.px(2.2)
        CHARACTER.draw(
            p, x + sway, floor + (1 - ent) * self.stage.px(26), self.stage.character_height,
            pose=pose, alpha=alpha, blink=blink, mouth=mouth, bounce=bounce,
            facing=facing, shadow=True,
        )

    # -------------------------------------------------------------- headline
    def _draw_headline(self, p: Painter, ctx: RenderContext, t: float) -> None:
        if not self.headline_words:
            return
        st = self.stage
        ax, ay, aw, ah = st.headline_area
        size = st.headline_size()
        style = TextStyle(size=size, language=self.spec.language,
                          role="display" if self.spec.language != "ur" else "display",
                          align="left" if self.spec.language != "ur" else "right", line_height=1.14)
        text = " ".join(w for w, _ in self.headline_words)
        max_w = min(aw, st.content_w * (0.94 if st.format == "vertical" else 0.60))
        lay, style = _autosize(self.renderer, text, style, max_w, ah, min_size=size * 0.6, max_lines=3)
        size = style.size
        if st.format == "vertical":
            ox = (st.width - lay.width) / 2
        else:
            ox = ax
        # vertically centre the block inside its area so ascenders never clip
        oy = ay + max(0.0, (ah - lay.height) / 2)
        reveal = clamp(t / 0.75)
        total_words = max(1, len(lay.words))
        keyword_flags = [flag for _w, flag in self.headline_words]
        boxes = []
        for i, pw in enumerate(lay.words):
            pr = stagger(reveal, min(i, total_words - 1), total_words, 0.7)
            if pr <= 0.001:
                continue
            ease = ease_out_back(pr)
            dy = (1 - ease) * size * 0.55
            alpha = clamp(pr * 1.6)
            is_kw = keyword_flags[i] if i < len(keyword_flags) else False
            color = st.palette["accent"] if is_kw else st.palette["text"]
            if is_kw:
                color = st.palette["accent3"] if i % 2 == 0 else st.palette["accent"]
            box = self.renderer.draw_word(
                p, pw.word, style, ox + pw.x, oy + pw.baseline, color,
                scale=0.9 + 0.1 * ease, alpha=alpha, dy=dy,
                outline=with_alpha(st.palette["ink"], alpha), outline_width=size * 0.055,
                shadow=(0, size * 0.055, size * 0.06, 0.35 * alpha),
            )
            boxes.append(box)
        # underline sweep under the last headline line
        if lay.lines:
            ln = lay.lines[-1]
            uw = ln.width * ease_out(clamp((t - 0.35) / 0.55))
            uy = oy + ln.baseline + size * 0.20
            ux0 = ox + (ln.words[0].x if ln.words else 0)
            if uw > 2:
                p.rect(ux0, uy, ux0 + uw, uy + max(3.0, size * 0.075),
                       fill=with_alpha(st.palette["accent"], 0.9), radius=size * 0.04)
        # purpose kicker
        kicker = self._kicker_text()
        if kicker:
            # keep the strip inside the safe area: it used to sit above the frame edge
            # sit it at the far edge of the content area, level with the first line,
            # instead of above the headline (where it used to clip the frame top)
            ky = oy + max(0.0, st.px(4) - ease_out(clamp(t / 0.5)) * st.px(10))
            kx = st.width - st.safe_x
            self.world.kicker(p, ctx, kicker, kx, ky, align="right")

    def _kicker_text(self) -> str:
        idx = self.spec.scene_index + 1
        total = self.spec.scene_count
        if self.spec.language == "ur":
            return f"حصہ {idx} از {total}".translate(URDU_DIGITS)
        return f"PART {idx} / {total}"

    # -------------------------------------------------------------- captions
    def _draw_captions(self, p: Painter, ctx: RenderContext, t: float) -> None:
        cue = None
        for c in self.cues:
            if c.start - 0.06 <= t <= c.end + 0.12:
                cue = c
                break
        if cue is None or not cue.words:
            return
        st = self.stage
        cx0, cy0, cw, ch = st.caption_area
        size = st.caption_size()
        style = TextStyle(size=size, language=self.spec.language, role="body",
                          align="center", line_height=1.22 if self.spec.language != "ur" else 1.8)
        text = cue.text
        # the pill and the text must fit the band together: reserve the pill padding
        # before auto-sizing, otherwise narrow formats overflow edge-to-edge.
        pad_x = size * 0.85
        pad_y = size * 0.55
        max_w = max(size * 2.5, min(cw, st.content_w) - pad_x * 2)
        max_h = max(size * 1.2, ch * 0.92 - pad_y * 1.25)
        lay, style = _autosize(self.renderer, text, style, max_w, max_h,
                              min_size=size * 0.62, max_lines=3)
        size = style.size
        pad_x = size * 0.85
        pad_y = size * 0.55
        appear = clamp((t - (cue.start - 0.06)) / 0.18)
        ease = ease_out(appear)
        alpha = ease
        dy = (1 - ease) * size * 0.35
        # backdrop pill behind the cue
        bw = min(lay.width + pad_x * 2, min(cw, st.content_w))
        bh = min(lay.height + pad_y * 1.25, ch)
        bx = st.width / 2 - bw / 2
        by = cy0 + ch / 2 - bh / 2 + dy * 0.3
        # never let the caption pill leave the safe area
        margin = max(st.safe_x * 0.5, size * 0.35)
        bx = max(margin, min(bx, st.width - margin - bw))
        p.rect(bx, by, bx + bw, by + bh, fill=with_alpha(st.palette["ink"], 0.74 * alpha),
               radius=size * 0.7)
        ox = st.width / 2 - lay.width / 2
        oy = by + (bh - lay.height) / 2
        kw = {k.lower() for k in (self.spec.scene.keywords.get(self.spec.language) or [])}
        for i, pw in enumerate(lay.words):
            w = cue.words[i] if i < len(cue.words) else None
            active = bool(w and w.start <= t <= w.end + 0.05)
            said = bool(w and t > w.end)
            base = st.palette["text"] if not said else mix(st.palette["text"], st.palette["muted"], 0.22)
            color = st.palette["accent3"] if active else base
            clean = pw.word.text.strip("،,.:;!?؟۔").lower()
            if not active and clean in kw:
                color = st.palette["accent"]
            scale = 1.0 + (0.06 if active else 0.0)
            self.renderer.draw_word(
                p, pw.word, style, ox + pw.x, oy + pw.baseline, color,
                scale=scale, alpha=alpha, dy=dy,
                outline=with_alpha(st.palette["ink"], 0.85 * alpha), outline_width=size * 0.045,
            )

    # ------------------------------------------------------------ transition
    def _draw_transition(self, p: Painter, t: float, layer_alpha: float) -> None:
        st = self.stage
        dur = self.spec.duration
        # intro: quick fade from background colour + horizontal wipe
        if t < 0.26:
            k = 1 - ease_out(t / 0.26)
            glow = mix(st.palette["bg_top"], st.palette["accent3"], 0.28)
            p.rect(0, 0, st.width, st.height, fill=with_alpha(glow, k * 0.85))
        # outro: fade to colour with a shrink cue
        if dur - t < 0.32:
            k = 1 - ease_in_out((dur - t) / 0.32)
            p.rect(0, 0, st.width, st.height,
                   fill=with_alpha(mix(st.palette["bg_top"], st.palette["accent3"], 0.22), k * 0.88))
            bar_h = st.height * 0.012 * k
            p.rect(0, st.height / 2 - bar_h / 2, st.width * k, st.height / 2 + bar_h / 2,
                   fill=with_alpha(st.palette["accent"], 0.9 * k))


def render_still(spec: SceneRenderSpec, t: float, ss: int = 2) -> Image.Image:
    renderer = SceneRenderer(spec)
    return renderer.render(t, painter=Painter(spec.stage.width, spec.stage.height, ss=ss))
