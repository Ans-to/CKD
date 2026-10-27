"""Rebuild the Nokia opening in CKD's premium-flat/vector style.

This is a 15-second, two-sentence cut.  A generic classic handset owns the
first sentence; on the exact second-sentence boundary, it clears for a
sentence-derived typographic association and the project's single vector-rig
character.  The drawings are stylized graphics, not archival footage or an
accurate Nokia product model.  The narration is retained from the prior cut.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from ckd.content.schema import Scene
from ckd.scene.renderer import SceneRenderSpec, SceneRenderer
from ckd.scene.stage import make_stage
from ckd.scene.worlds.business import BusinessWorld
from ckd.scene.timing import build_captions
from ckd.text.render import TextRenderer
from ckd.voice.base import WordTiming
from ckd.voice.narration import ClauseAudio, SceneAudio

ROOT = Path(__file__).resolve().parents[1]
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
    """Business world with a persistent, explicit illustration disclosure."""

    def foreground(self, p, ctx) -> None:
        super().foreground(p, ctx)
        self.label(
            p, ctx, ctx.stage.width - ctx.stage.safe_x, ctx.stage.height * 0.17,
            "STYLIZED GRAPHIC · NOT ARCHIVAL FOOTAGE",
            size=ctx.stage.px(14), color=ctx.col("muted"), bg=True,
            align="right", alpha=0.78, max_width=ctx.stage.px(360), role="small",
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
        headline_hold=6.4,
        keywords={"en": ["billions", "pockets", "synonymous", "phones"]},
        motif="scale",
        camera="slow_push",
        elements=[
            {
                "type": "phone",
                "slot": "phone",
                "params": {
                    "kind": "classic", "screen": "blank", "ring": True,
                    "in": "hook", "out": "play", "cut": True,
                },
            },
            {
                "type": "statement",
                "slot": "wide",
                "params": {
                    "en": "NOKIA ≈ MOBILE PHONES", "variant": 1,
                    "in": "play", "cut": True,
                },
            },
        ],
        actions=[{"action": "hook", "at": 0.0}, {"action": "play", "at": CUT_AT}],
        character={
            "visible": True,
            "visible_from": CUT_AT,
            "slot": "char_right",
            "pose": "present",
        },
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
    # phone-to-type handoff, character entrance, and caption reset all coincide.
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
