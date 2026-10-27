"""Rebuild the Nokia opening in CKD's premium-flat/vector style.

This is a 15-second, two-sentence cut.  The first sentence gets a living
world-network and a single generic handset sinking into a stylized pocket; on
the exact second-sentence boundary, those graphics clear for a sentence-derived
kinetic-typography association.  The documentary opening intentionally hides
the project's character.  The drawings are
not archival footage or an accurate Nokia product model.  The approved
narration is retained.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np

from ckd.content.schema import Scene
from ckd.gfx.painter import mix, with_alpha
from ckd.gfx.primitives import clamp, ease_in_out, ease_out
from ckd.scene.renderer import SceneRenderSpec, SceneRenderer
from ckd.scene.stage import make_stage
from ckd.scene.timing import build_captions
from ckd.scene.worlds.business import BusinessWorld
from ckd.scene.worlds import business_props as props
from ckd.text.render import TextRenderer
from ckd.text.shaping import TextStyle
from ckd.voice.base import WordTiming
from ckd.voice.narration import ClauseAudio, SceneAudio

INPUT_VIDEO = ROOT / "samples/nokia-opening-15s.mp4"
OUTPUT_VIDEO = INPUT_VIDEO
FPS = 24
DURATION = 15.0
FRAMES = int(FPS * DURATION)
SAMPLE_RATE = 48_000
CUT_AT = 7.986
SECOND_END = 12.8

SENTENCE_1 = (
    "Imagine building a company so powerful that billions of people around the "
    "world carry its products in their pockets."
)
SENTENCE_2 = "A company whose name becomes almost synonymous with mobile phones."


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:  # pragma: no cover - exercised by the workflow
        raise RuntimeError("Install imageio-ffmpeg to encode the preview") from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(video: Path, wav_path: Path) -> np.ndarray:
    """Keep the already-approved VO while rebuilding only the rejected visuals."""
    cmd = [ffmpeg_exe(), "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "2",
           "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(wav_path)]
    subprocess.run(cmd, check=True)
    with wave.open(str(wav_path), "rb") as src:
        if src.getnchannels() != 2 or src.getsampwidth() != 2 or src.getframerate() != SAMPLE_RATE:
            raise RuntimeError("Unexpected extracted narration format")
        samples = np.frombuffer(src.readframes(src.getnframes()), dtype="<i2").reshape(-1, 2)
    audio = samples.astype(np.float32) / 32768.0
    expected = round(DURATION * SAMPLE_RATE)
    if len(audio) < expected:
        audio = np.pad(audio, ((0, expected - len(audio)), (0, 0)))
    return audio[:expected]


def word_timings(text: str, start: float, end: float) -> list[WordTiming]:
    """Construct readable karaoke timings from the known sentence boundaries."""
    words = re.findall(r"\S+", text)
    weights = [max(1.0, len(word.strip(",.!?;:")) ** 0.78) for word in words]
    span = max(0.1, end - start)
    gaps = min(0.022 * max(0, len(words) - 1), span * 0.08)
    usable = span - gaps
    total = sum(weights)
    out: list[WordTiming] = []
    cursor = start
    for word, weight in zip(words, weights):
        finish = cursor + usable * weight / total
        out.append(WordTiming(word, cursor, finish))
        cursor = finish + (gaps / max(1, len(words) - 1))
    return out


class NokiaWorld(BusinessWorld):
    """A world-network/pocket reveal with an explicit illustration disclosure."""

    element_types = BusinessWorld.element_types + ("pocket", "equivalence")

    def _el_pocket(self, p, ctx, el, a: float) -> None:
        """Stylized jacket front and sewn pocket; this masks the handset below its lip."""
        x, y, w, h = self.slot(ctx.stage, el.get("slot", "stage_right"))
        jacket = mix(ctx.col("bg_bottom"), ctx.col("cool"), 0.13)
        panel = [(x + w * 0.16, y + h * 0.025), (x + w * 0.84, y + h * 0.025),
                 (x + w * 0.98, y + h * 0.15), (x + w * 0.96, y + h * 0.96),
                 (x + w * 0.04, y + h * 0.96), (x + w * 0.02, y + h * 0.15)]
        p.polygon(panel, fill=with_alpha(jacket, 0.96 * a),
                  outline=with_alpha(ctx.col("cool"), 0.46 * a), width=ctx.stage.px(1.6))
        # Tailored lapels and a front seam establish a garment, not a box or case.
        p.line([(x + w * 0.16, y + h * 0.03), (x + w * 0.43, y + h * 0.29),
                (x + w * 0.50, y + h * 0.12)],
               with_alpha(ctx.col("paper"), 0.19 * a), width=ctx.stage.px(1.7))
        p.line([(x + w * 0.84, y + h * 0.03), (x + w * 0.57, y + h * 0.29),
                (x + w * 0.50, y + h * 0.12)],
               with_alpha(ctx.col("paper"), 0.12 * a), width=ctx.stage.px(1.7))
        p.line([(x + w * 0.50, y + h * 0.12), (x + w * 0.50, y + h * 0.91)],
               with_alpha(ctx.col("cool"), 0.19 * a), width=ctx.stage.px(1.2))
        for i in range(2):
            by = y + h * (0.35 + i * 0.20)
            p.ellipse(x + w * 0.50, by, ctx.stage.px(2.4), ctx.stage.px(2.4),
                      fill=with_alpha(ctx.col("accent"), 0.62 * a))

        # The phone rises into view, pauses, then descends as the narration
        # reaches "in their pockets".  Draw it between the jacket and pocket lip.
        ph = h * 0.68
        pw = ph * 0.50
        cx = x + w * 0.50
        reveal = ease_out(clamp((ctx.t - 0.05) / 0.35))
        lift = ease_in_out(clamp(ctx.t / 1.2))
        sink = ease_in_out(clamp((ctx.t - 3.8) / 3.7))
        px0 = cx - pw / 2
        py0 = y + h * (0.02 - 0.18 * lift + 0.43 * sink)
        phone_alpha = a * reveal
        if phone_alpha > 0.001:
            p.glow(cx, py0 + ph * 0.45, ph * 0.52,
                   with_alpha(ctx.col("accent3"), 0.17 * phone_alpha))
            sprite, ox, oy = props.phone(ctx.palette, p.ss, px0, py0, pw, ph,
                                         kind="classic", screen="blank")
            p.paste_sprite(sprite, ox, oy, alpha=phone_alpha)
            self._phone_screen(p, ctx, px0, py0, pw, ph,
                               "classic", "blank", phone_alpha)

        # Trapezoid pocket with an open top: the descending phone is covered from
        # the bottom up, leaving its screen visible above the sewn mouth.
        px, top, pw, bottom = x + w * 0.12, y + h * 0.405, w * 0.76, y + h * 0.96
        pocket = mix(jacket, ctx.col("metal_dark"), 0.26)
        shape = [(px, top), (px + pw, top), (px + pw * 0.84, bottom),
                 (px + pw * 0.16, bottom)]
        p.polygon(shape, fill=with_alpha(pocket, 0.99 * a),
                  outline=with_alpha(ctx.col("cool"), 0.65 * a), width=ctx.stage.px(1.7))
        p.line([(px + pw * 0.04, top + h * 0.055),
                (px + pw * 0.96, top + h * 0.055)],
               with_alpha(ctx.col("paper"), 0.30 * a), width=ctx.stage.px(1.3))
        for side in (0, 1):
            sx = px + pw * (0.035 if side == 0 else 0.965)
            direction = 1 if side == 0 else -1
            for i in range(9):
                sy = top + h * (0.11 + i * 0.037)
                p.line([(sx, sy), (sx + direction * ctx.stage.px(4.5), sy)],
                       with_alpha(ctx.col("accent3"), 0.48 * a), width=ctx.stage.px(1.0))

    def _el_equivalence(self, p, ctx, el, a: float) -> None:
        """Animate the sentence's near-synonym as editorial kinetic type, not a card."""
        st = ctx.stage
        local = max(0.0, ctx.since("play"))
        style_nokia = TextStyle(size=104, language="en", role="display", align="center")
        style_equal = TextStyle(size=84, language="en", role="display", align="center")
        style_mobile = TextStyle(size=64, language="en", role="display", align="center")
        nokia = ctx.renderer.layout("NOKIA", style_nokia, st.width * 0.34)
        equal = ctx.renderer.layout("≈", style_equal, st.width * 0.10)
        mobile = ctx.renderer.layout("MOBILE PHONES", style_mobile, st.width * 0.48)
        gap = st.px(58)
        total = nokia.width + equal.width + mobile.width + gap * 2
        start = (st.width - total) / 2
        nx = start
        ex = nx + nokia.width + gap
        mx = ex + equal.width + gap
        baseline = st.height * 0.49

        pn = ease_out(clamp(local / 0.62))
        pe = ease_out(clamp((local - 0.24) / 0.58))
        pm = ease_out(clamp((local - 0.55) / 0.72))
        nokia_x = nx - (1 - pn) * st.px(72)
        equal_x = ex + (1 - pe) * st.px(20)
        mobile_x = mx + (1 - pm) * st.px(84)
        nokia_y = baseline - nokia.lines[0].baseline + (1 - pn) * st.px(18)
        equal_y = baseline - equal.lines[0].baseline + (1 - pe) * st.px(14)
        mobile_y = baseline - mobile.lines[0].baseline + (1 - pm) * st.px(18)

        p.glow(nx + nokia.width / 2, baseline - st.px(28), st.px(150),
               with_alpha(ctx.col("accent"), 0.075 * a * pn))
        p.glow(mx + mobile.width / 2, baseline - st.px(25), st.px(195),
               with_alpha(ctx.col("accent3"), 0.08 * a * pm))
        ctx.renderer.draw_layout(p, nokia, style_nokia, (nokia_x, nokia_y),
                                 with_alpha(ctx.col("text"), a * pn))
        if pe > 0.001:
            p.glow(ex + equal.width / 2, baseline - st.px(20), st.px(42),
                   with_alpha(ctx.col("accent"), 0.26 * a * pe))
            ctx.renderer.draw_layout(p, equal, style_equal, (equal_x, equal_y),
                                     with_alpha(ctx.col("accent"), a * pe))
        ctx.renderer.draw_layout(p, mobile, style_mobile, (mobile_x, mobile_y),
                                 with_alpha(ctx.col("accent3"), a * pm))

        # One travelling highlight joins the two phrases after both have landed.
        line_progress = ease_out(clamp((local - 1.15) / 0.80))
        if line_progress > 0:
            lx0 = nx + nokia.width + st.px(8)
            lx1 = mx - st.px(8)
            ly = baseline + st.px(35)
            x1 = lx0 + (lx1 - lx0) * line_progress
            p.line([(lx0, ly), (x1, ly)],
                   with_alpha(ctx.col("cool"), 0.58 * a), width=st.px(2.0))
            if local < 2.65 and line_progress > 0.05:
                pulse = (local * 0.72) % 1.0
                p.ellipse(lx0 + (lx1 - lx0) * pulse, ly,
                          st.px(4.2), st.px(4.2),
                          fill=with_alpha(ctx.col("paper"), 0.90 * a))

    def foreground(self, p, ctx) -> None:
        super().foreground(p, ctx)
        self.label(
            p, ctx, ctx.stage.width - ctx.stage.safe_x, ctx.stage.height * 0.17,
            "STYLIZED GRAPHICS · NOT ARCHIVAL FOOTAGE · NOT AN ACCURATE PRODUCT MODEL",
            size=ctx.stage.px(14), color=ctx.col("muted"), bg=True,
            align="right", alpha=0.78, max_width=ctx.stage.px(640), role="small",
        )


def build_renderer(audio: np.ndarray) -> SceneRenderer:
    clause_1 = ClauseAudio(
        text=SENTENCE_1, start=0.0, end=CUT_AT,
        words=word_timings(SENTENCE_1, 0.08, CUT_AT - 0.10),
    )
    clause_2 = ClauseAudio(
        text=SENTENCE_2, start=CUT_AT, end=SECOND_END,
        words=word_timings(SENTENCE_2, CUT_AT + 0.06, SECOND_END - 0.08),
    )
    narration = SceneAudio(
        index=0, scene_id="nokia-opening", start=0.0, duration=DURATION,
        frames=FRAMES, clauses=[clause_1, clause_2], audio=audio,
    )
    scene = Scene(
        id="nokia-opening",
        purpose="documentary_hook",
        narration={"en": f"{SENTENCE_1} {SENTENCE_2}"},
        headline={"en": "Nokia"},
        headline_hold=4.4,
        keywords={"en": ["billions", "pockets", "synonymous", "phones"]},
        motif="scale",
        camera="slow_push",
        elements=[
            {
                "type": "globe",
                "slot": "globe",
                "params": {"en": "AROUND THE WORLD", "in": "hook",
                           "out": "play", "cut": True},
            },
            {
                "type": "pocket",
                "slot": "stage_right",
                "params": {"in": "hook", "out": "play", "cut": True},
            },
            {
                "type": "equivalence",
                "slot": "wide",
                "params": {"in": "play", "cut": True},
            },
        ],
        actions=[{"action": "hook", "at": 0.0}, {"action": "play", "at": CUT_AT}],
        character={"visible": False},
        notes="Stylized illustration only; no archival footage or accurate product model.",
    )
    stage = make_stage(1280, 720, "landscape", "documentary", fps=FPS)
    text = TextRenderer(ss=1)
    spec = SceneRenderSpec(
        scene=scene, stage=stage, language="en", narration=narration,
        world=NokiaWorld(), renderer=text, scene_index=0, scene_count=1,
        include_captions=True, include_character=True, seed=41, supersample=1,
    )
    renderer = SceneRenderer(spec)
    # Do not let a karaoke chunk bridge the two visual beats: the sentence cut,
    # phone-to-type handoff, and caption reset all coincide.
    first_cues = build_captions(clause_1.words, scene_duration=CUT_AT)
    second_cues = build_captions(clause_2.words, scene_duration=DURATION - CUT_AT)
    if first_cues:
        first_cues[-1].end = min(first_cues[-1].end, CUT_AT - 0.13)
    renderer.cues = first_cues + second_cues
    return renderer


def render(output: Path, source: Path = INPUT_VIDEO) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nokia-vector-") as td:
        audio_path = Path(td) / "narration.wav"
        audio = extract_audio(source, audio_path)
        renderer = build_renderer(audio)
        cmd = [
            ffmpeg_exe(), "-y", "-v", "error",
            "-f", "rawvideo", "-pixel_format", "rgb24", "-video_size", "1280x720",
            "-framerate", str(FPS), "-i", "-",
            "-i", str(audio_path), "-frames:v", str(FRAMES),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-ar", str(SAMPLE_RATE), "-t", str(DURATION), "-movflags", "+faststart",
            str(output),
        ]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        assert proc.stdin is not None
        try:
            for frame_no in range(FRAMES):
                t = frame_no / FPS
                frame = renderer.render(t)
                proc.stdin.write(np.asarray(frame.convert("RGB"), dtype=np.uint8).tobytes())
                if frame_no % FPS == 0:
                    print(f"Rendered {frame_no:03d}/{FRAMES} frames ({t:05.2f}s)", flush=True)
        except BaseException:
            proc.stdin.close()
            proc.terminate()
            proc.wait()
            raise
        else:
            proc.stdin.close()
        code = proc.wait()
        if code:
            raise subprocess.CalledProcessError(code, cmd)
    print(f"Wrote {output} ({FRAMES} frames, {DURATION:.2f}s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT_VIDEO,
                        help="Existing cut used only as the approved narration source")
    parser.add_argument("--output", type=Path, default=OUTPUT_VIDEO)
    args = parser.parse_args()
    render(args.output, args.input)


if __name__ == "__main__":
    main()
