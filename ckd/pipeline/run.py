"""The end-to-end pipeline: topic -> MP4, resumable and content-addressed.

Stage graph (each stage has a content hash; unchanged stages are skipped):

  script ──► narration[lang] ──► timing[lang] ──► scenes[lang,fmt]xN ──► video[lang,fmt]

The cache key of a scene includes the script hash, the narration hash, the
format/quality/fps flags and the scene index - so editing the script, changing
the voice, changing the format or the quality invalidates exactly the affected
artefacts and nothing else.

Every scene is encoded to its own MP4.  A completed scene is only reused when
its sidecar hash matches AND the file still passes a decode/duration check, so a
truncated or corrupt file is re-rendered instead of being trusted.
"""
from __future__ import annotations

import json
import math
import shutil
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from PIL import Image

from ..content.composer import compose_story, estimate_duration
from ..content.options import RenderOptions
from ..content.schema import Story, validate_story
from ..gfx.painter import Painter
from ..render.ffmpeg import (
    concat_videos, encode_frames, extract_frame, loudness_stats, mux_audio, probe, verify_video,
)
from ..scene.renderer import SceneRenderer, SceneRenderSpec
from ..scene.stage import make_stage
from ..scene.timing import assign_actions, build_captions, storyboard_timing
from ..scene.worlds import get_world
from ..text.render import TextRenderer
from ..util.hashing import hash_json
from ..util.logging import get_logger
from ..voice.narration import Narrator, NarrationTrack, SpeechCache
from .project import Project, open_project, slugify
from .subtitles import write_ass, write_srt

LOG = get_logger("ckd.pipeline")


class PipelineError(RuntimeError):
    pass


@dataclass
class StageResult:
    stage: str
    status: str  # done | cached | failed
    detail: str = ""
    seconds: float = 0.0


ProgressFn = Callable[[str, float, str], None]

# Bump when the *drawing* changes (composition, palette, timings). Scene caches from
# an older value are treated as stale, because a cached clip would otherwise keep an
# old look. Script/logic changes bump the "v" inside script_hash instead.
RENDER_VERSION = 17


def _noop(stage: str, frac: float, msg: str) -> None:  # pragma: no cover
    LOG.info("[%s %.0f%%] %s", stage, frac * 100, msg)


@dataclass
class Pipeline:
    options: RenderOptions
    root: str | Path
    project_dir: Optional[Path] = None
    character: bool = True
    allow_download: bool = True
    cache_dir: Optional[Path] = None
    progress: ProgressFn = _noop
    supersample_override: Optional[int] = None
    force: Sequence[str] = field(default_factory=tuple)  # e.g. ("scenes", "video")

    def __post_init__(self) -> None:
        base = Path(self.project_dir) if self.project_dir else Path(self.root) / slugify(self.options.topic)
        self.project = open_project(base, self.options)
        self.cache = Path(self.cache_dir) if self.cache_dir else Path(self.root) / "_cache"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.speech_cache = SpeechCache(self.cache / "speech")
        self.renderer = TextRenderer(ss=2)
        self.log: List[StageResult] = []

    # ------------------------------------------------------------------ stages
    def script_hash(self) -> str:
        o = self.options
        payload = {
            "topic": o.topic.strip().lower(), "langs": o.languages, "duration": o.duration,
            "notes": o.notes, "llm": o.llm, "palette": o.palette, "seed": o.seed, "v": 5,
        }
        return hash_json(payload, prefix="script")

    def _speech_rate(self) -> float:
        """Words-per-second scale for the voice that will actually narrate.

        Planning with Piper's speaking rate and then rendering with the offline
        espeak fallback overshot the requested duration by ~80 %, so the composer
        is told which one it is dealing with.
        """
        from ..voice.narration import resolve_engine

        engines = set()
        for lang, want in (("en", self.options.voice_en), ("ur", self.options.voice_ur)):
            if lang in self.options.languages:
                engines.add(resolve_engine(lang, want))
        return 0.55 if "espeak" in engines else 1.0

    def build_story(self, *, compile_only: bool = False) -> Story:
        stage = "script"
        self.progress(stage, 0.05, "Composing script and scene plan")
        t0 = time.time()
        story_path = self.project.story_path
        # a reviewed/edited story wins over regeneration until the request changes
        reviewed = self.project.state.get("reviewed_script_hash")
        content_hash = self.project.state.get("script_hash")
        llm = None
        if self.options.llm not in ("none", "", None):
            from .llm_adapter import load_llm_or_raise

            llm = load_llm_or_raise(self.options.llm)
        story: Optional[Story] = None
        if story_path.exists() and content_hash == self.reviewed_script_hash_expected():
            try:
                story = Story.from_dict(json.loads(story_path.read_text(encoding="utf-8")))
                self.progress(stage, 0.5, f"Reusing saved script ({story.generator})")
            except Exception as exc:  # noqa: BLE001
                LOG.warning("could not reuse saved script: %s", exc)
                story = None
        if story is None:
            story = compose_story(
                self.options.topic, languages=self.options.languages,
                target_seconds=self.options.duration, llm=llm,
                palette=self.options.palette, notes=self.options.notes,
                speech_rate=self._speech_rate(),
            )
            self.project.write_json(story_path, story.to_dict())
        validate_story(story, languages=self.options.languages)
        self.project.state["script_hash"] = self.script_hash()
        self.project.state["story_id"] = hash_json(story.to_dict())[:12]
        self.project.state["world"] = story.world
        self.project.state["generator"] = story.generator
        self.project.state["warnings"] = list(story.warnings)
        for warning in story.warnings:
            LOG.warning("script: %s", warning)
        self.project.save()
        self._record(StageResult(stage, "done", f"{len(story.scenes)} scenes, world={story.world}",
                                 time.time() - t0))
        self.progress(stage, 1.0, f"Script ready: {len(story.scenes)} scenes")
        return story

    def reviewed_script_hash_expected(self) -> str:
        return self.script_hash()

    def story_for_review(self) -> Story:
        """Return the story for editing (generates it if needed)."""
        return self.build_story()

    # --------------------------------------------------------------- narration
    def narration_hash(self, lang: str, story: Story) -> str:
        o = self.options
        payload = {
            "story": hash_json(story.to_dict()),
            "lang": lang,
            "voice": o.voice_en if lang == "en" else o.voice_ur,
            "fallback": o.allow_espeak_fallback,
            "fps": o.fps,
            "v": 3,
        }
        return hash_json(payload, prefix="narration")

    def narrate(self, story: Story, *, force: bool = False) -> Dict[str, NarrationTrack]:
        narrator = Narrator(
            voice_en=self.options.voice_en, voice_ur=self.options.voice_ur,
            allow_download=self.allow_download,
            allow_espeak_fallback=self.options.allow_espeak_fallback,
            cache=self.speech_cache,
        )
        tracks: Dict[str, NarrationTrack] = {}
        for li, lang in enumerate(self.options.languages):
            stage = f"narration:{lang}"
            t0 = time.time()
            self.progress(stage, 0.05 * li, f"Preparing {lang} narration")
            want = self.narration_hash(lang, story)
            track_json = self.project.audio_path(lang).with_suffix(".json")
            wav = self.project.audio_path(lang)
            if not force and track_json.exists() and wav.exists():
                try:
                    meta = json.loads(track_json.read_text(encoding="utf-8"))
                    if meta.get("hash") == want:
                        track = _track_from_meta(meta, wav)
                        info = probe_wav(wav)
                        if abs(info - track.duration) < 0.1:
                            tracks[lang] = track
                            self._record(StageResult(stage, "cached", f"{track.duration:.1f}s reused",
                                                     time.time() - t0))
                            self.progress(stage, 1.0, f"{lang}: narration reused ({track.duration:.1f}s)")
                            continue
                        LOG.warning("%s narration wav length mismatch; regenerating", lang)
                except Exception as exc:  # noqa: BLE001
                    LOG.warning("%s narration reuse failed (%s); regenerating", lang, exc)
            track = narrator.build(story, lang, fps=self.options.fps,
                                   max_seconds=self.options.duration)
            from ..voice.base import write_wav

            write_wav(wav, track.audio, track.sample_rate)
            self.project.write_json(track_json, {"hash": want, **track.to_dict(include_words=True)})
            tracks[lang] = track
            self._record(StageResult(stage, "done",
                                     f"{track.engine}/{track.voice} {track.duration:.1f}s "
                                     f"timing={track.timing_kind}", time.time() - t0))
            self.progress(stage, 1.0, f"{lang}: {track.engine} narration {track.duration:.1f}s")
        # measured narration is the ground truth for duration.  The composer plans
        # with a speaking-rate table; if the voice that actually ran is much slower
        # (the offline espeak fallback is ~half the rate of a Piper voice), say so
        # instead of shipping a video that quietly misses the requested length.
        target = float(self.options.duration)
        for lang, track in tracks.items():
            if target <= 0:
                continue
            ratio = track.duration / target
            if ratio > 1.2 or ratio < 0.7:
                note = (
                    f"{lang}: narration measured {track.duration:.1f}s against a "
                    f"{target:.0f}s target (engine: {track.engine}). The plan was sized "
                    f"with an estimated speaking rate; re-run with --duration "
                    f"{track.duration:.0f} to keep every beat, or a shorter --duration "
                    f"to drop scenes."
                )
                if note not in story.warnings:
                    story.warnings.append(note)
                    LOG.warning(note)
        self.project.write_json(self.project.story_path, story.to_dict())

        # storyboards (per language, with measured timing)
        board = storyboard_timing(story, tracks)
        for lang in tracks:
            self.project.write_json(self.project.storyboard_path(lang), board.get(lang, {}))
        self.project.write_json(self.project.root / "storyboard.json", board)
        self.project.state["narration"] = {
            lang: {"engine": t.engine, "voice": t.voice, "duration": round(t.duration, 2),
                   "timing_kind": t.timing_kind, "warnings": t.warnings}
            for lang, t in tracks.items()
        }
        self.project.save()
        return tracks

    # ------------------------------------------------------------------ scenes
    def scene_audio_hash(self, na) -> str:
        """Hash of *this scene's* audio only.

        The whole-language narration hash changes when any sentence changes, which used
        to invalidate every scene on a one-line edit. A scene clip depends on its own
        duration, frame count and word timings, so that is what belongs in the key.
        """
        payload = {
            "scene_id": na.scene_id,
            "duration": round(float(na.duration), 3),
            "frames": int(na.frames),
            "clauses": [
                {"t": c.text, "s": round(c.start, 3), "e": round(c.end, 3),
                 "w": [[w.text, round(w.start, 3), round(w.end, 3)] for w in c.words]}
                for c in na.clauses
            ],
        }
        return hash_json(payload, prefix="sceneaudio")

    def scene_hash(self, lang: str, fmt: str, index: int, scene, scene_audio: str) -> str:
        o = self.options
        payload = {
            "audio": scene_audio, "scene": scene.to_dict(), "index": index,
            "fmt": fmt, "quality": o.quality, "fps": o.fps, "captions": o.include_captions,
            "character": o.include_character, "seed": o.seed, "v": RENDER_VERSION,
            "size": list(o.size_for(fmt)),
        }
        return hash_json(payload, prefix="scene")

    def render_scene(self, story: Story, lang: str, fmt: str, index: int,
                     track: NarrationTrack, *, force: bool = False) -> Tuple[Path, str]:
        o = self.options
        scene = story.scenes[index]
        na = track.scenes[index]
        stage_label = f"scene:{lang}:{fmt}:{index + 1}"
        out = self.project.scene_path(lang, fmt, index, scene.id)
        sidecar = out.with_suffix(".json")
        want = self.scene_hash(lang, fmt, index, scene, self.scene_audio_hash(na))
        width, height = o.size_for(fmt)
        expected = na.frames / float(o.fps)
        if not force and out.exists() and sidecar.exists():
            try:
                meta = json.loads(sidecar.read_text(encoding="utf-8"))
                if meta.get("hash") == want and meta.get("frames") == na.frames:
                    ok, problems = verify_video(
                        out, expect_w=width, expect_h=height, expect_fps=o.fps,
                        expect_duration=expected, tolerance=0.25, require_audio=False,
                    )
                    if ok:
                        self._record(StageResult(stage_label, "cached", f"{expected:.1f}s reused", 0.0))
                        return out, "cached"
                    LOG.warning("scene %s failed integrity check: %s", out.name, problems)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("scene reuse check failed for %s: %s", out.name, exc)
        t0 = time.time()
        stage = make_stage(width, height, fmt, story.palette, fps=o.fps)
        ss = self.supersample_override or o.supersample_for(fmt)
        tr = self.renderer
        # the text renderer's supersample must match the painter's
        if tr.ss != ss:
            tr = TextRenderer(ss=ss)
            self.renderer = tr
        world = get_world(story.world)
        spec = SceneRenderSpec(
            scene=scene, stage=stage, language=lang, narration=na, world=world, renderer=tr,
            scene_index=index, scene_count=len(story.scenes),
            include_captions=o.include_captions, include_character=o.include_character,
            seed=o.seed, supersample=ss,
        )
        renderer = SceneRenderer(spec)
        frames = na.frames
        progress_cb = None

        def gen():
            for f in range(frames):
                t = f / float(o.fps)
                yield renderer.render(t)

        def on_progress(done: int, total: int) -> None:
            base = 0.05 + 0.9 * (done / max(1, total))
            self.progress(stage_label, base, f"{lang}/{fmt} scene {index + 1}: frame {done}/{total}")

        encode_frames(
            gen(), out, width=width, height=height, fps=o.fps,
            crf=int(o.preset["crf"]), preset=str(o.preset["preset"]),
            total_frames=frames, progress=on_progress,
        )
        ok, problems = verify_video(out, expect_w=width, expect_h=height, expect_fps=o.fps,
                                    expect_duration=expected, tolerance=0.3, require_audio=False)
        if not ok:
            raise PipelineError(f"scene render failed verification: {problems}")
        self.project.write_json(sidecar, {
            "hash": want, "frames": frames, "duration": expected, "scene_id": scene.id,
            "width": width, "height": height, "fps": o.fps,
        })
        dt = time.time() - t0
        self._record(StageResult(stage_label, "done", f"{frames} frames in {dt:.1f}s", dt))
        self.progress(stage_label, 1.0, f"{lang}/{fmt} scene {index + 1} done ({dt:.1f}s)")
        return out, "done"

    # ------------------------------------------------------------------ videos
    def render_videos(self, story: Story, tracks: Dict[str, NarrationTrack],
                      *, force: bool = False) -> Dict[str, dict]:
        results: Dict[str, dict] = {}
        for lang in self.options.languages:
            track = tracks[lang]
            for fmt in self.options.formats:
                key = f"{lang}_{fmt}"
                self.progress(f"video:{key}", 0.01, f"Rendering {lang}/{fmt}")
                parts: List[Path] = []
                for i in range(len(story.scenes)):
                    part, status = self.render_scene(story, lang, fmt, i, track, force=force)
                    parts.append(part)
                    self.progress(f"video:{key}", 0.05 + 0.85 * (i + 1) / len(story.scenes),
                                  f"{lang}/{fmt}: scene {i + 1}/{len(story.scenes)} {status}")
                self._prune_scene_dir(lang, fmt, [sc.id for sc in story.scenes])
                joined = self.project.out_dir / f"{key}.video.mp4"
                concat_videos(parts, joined)
                final = self.project.video_path(lang, fmt)
                mux_audio(joined, self.project.audio_path(lang), final, duration=track.duration)
                joined.unlink(missing_ok=True)
                width, height = self.options.size_for(fmt)
                ok, problems = verify_video(final, expect_w=width, expect_h=height,
                                            expect_fps=self.options.fps,
                                            expect_duration=track.duration, tolerance=0.4)
                loud = loudness_stats(final)
                info = probe(final)
                meta = {
                    "language": lang, "format": fmt, "path": str(final),
                    "duration": info.duration, "width": info.width, "height": info.height,
                    "fps": info.fps, "verified": ok, "problems": problems,
                    "audio": loud, "timing_kind": track.timing_kind,
                    "caption_kind": "word-synced (" + track.timing_kind + ")",
                    "narration_engine": track.engine, "narration_voice": track.voice,
                }
                results[key] = meta
                if not ok:
                    LOG.warning("final %s failed verification: %s", key, problems)
                # subtitles
                cues = self._all_cues(story, track, lang)
                write_srt(self.project.subtitle_dir / f"{key}.srt", cues)
                write_ass(self.project.subtitle_dir / f"{key}.ass", cues, language=lang,
                          play_w=width, play_h=height)
                self.progress(f"video:{key}", 1.0, f"{lang}/{fmt} ready: {final.name}")
                self._record(StageResult(f"video:{key}", "done" if ok else "issues",
                                         f"{info.duration:.1f}s {info.width}x{info.height}", 0.0))
        self.project.state["videos"] = list(results.values())
        self.project.state["videos_by_key"] = results
        self.project.save()
        return results

    def _prune_scene_dir(self, lang: str, fmt: str, scene_ids: Sequence[str]) -> None:
        """Delete clips left over from a longer plan (e.g. 4 scenes -> 3).

        Cached scene files are keyed by index, so a plan that drops a scene would
        otherwise leave orphaned ``03_recap.mp4`` sitting in the project forever,
        which is confusing when the folder is inspected or zipped.
        """
        from .project import slugify

        wanted = {f"{i:02d}_{slugify(sid, 18)}" for i, sid in enumerate(scene_ids)}
        folder = self.project.scene_dir / f"{lang}_{fmt}"
        for path in folder.glob("*"):
            if path.suffix not in (".mp4", ".json", ".part.mp4"):
                continue
            # scene files are named "<index>_<id>.mp4" / ".json"
            stem = path.name.split(".", 1)[0]
            if stem not in wanted:
                try:
                    path.unlink()
                except OSError:
                    pass

    def _all_cues(self, story: Story, track: NarrationTrack, lang: str) -> List[dict]:
        cues: List[dict] = []
        for scene, na in zip(story.scenes, track.scenes):
            for c in build_captions(na.words, scene_duration=na.duration):
                cues.append({
                    "start": na.start + c.start,
                    "end": na.start + c.end,
                    "text": c.text,
                })
        return cues

    # -------------------------------------------------------------- previews
    def preview_sheet(self, story: Story, tracks: Dict[str, NarrationTrack], lang: str,
                      fmt: str, samples: int = 3, ss: int = 1) -> Path:
        """Contact sheet of stills per scene - cheap visual QA before rendering."""
        width, height = self.options.size_for(fmt)
        stage = make_stage(width, height, fmt, story.palette, fps=self.options.fps)
        world = get_world(story.world)
        tr = TextRenderer(ss=ss)
        track = tracks[lang]
        thumbs: List[Tuple[str, Image.Image]] = []
        for i, (scene, na) in enumerate(zip(story.scenes, track.scenes)):
            spec = SceneRenderSpec(
                scene=scene, stage=stage, language=lang, narration=na, world=world,
                renderer=tr, scene_index=i, scene_count=len(story.scenes),
                include_captions=self.options.include_captions,
                include_character=self.options.include_character, seed=self.options.seed,
                supersample=ss,
            )
            sr = SceneRenderer(spec)
            for k in range(samples):
                frac = 0.25 + 0.6 * (k / max(1, samples - 1)) if samples > 1 else 0.55
                img = sr.render(na.duration * frac, painter=Painter(width, height, ss=ss))
                thumbs.append((f"{scene.id} {frac:.2f}", img))
        cols = samples
        rows = len(story.scenes)
        tw = 360 if fmt == "landscape" else 200
        th = int(tw * height / width)
        sheet = Image.new("RGB", (cols * tw + 8, rows * th + 8), (12, 10, 18))
        for idx, (_label, img) in enumerate(thumbs):
            r, c = divmod(idx, cols)
            sheet.paste(img.resize((tw - 4, th - 4), Image.LANCZOS), (c * tw + 2, r * th + 2))
        out = self.project.preview_dir / f"{lang}_{fmt}_sheet.png"
        sheet.save(out)
        return out

    def preview_still(self, story: Story, tracks: Dict[str, NarrationTrack], *, lang: str,
                      fmt: str, scene_index: int = 0, frac: float = 0.55, ss: int = 2) -> Path:
        width, height = self.options.size_for(fmt)
        stage = make_stage(width, height, fmt, story.palette, fps=self.options.fps)
        tr = TextRenderer(ss=ss)
        scene = story.scenes[scene_index]
        na = tracks[lang].scenes[scene_index]
        spec = SceneRenderSpec(
            scene=scene, stage=stage, language=lang, narration=na, world=get_world(story.world),
            renderer=tr, scene_index=scene_index, scene_count=len(story.scenes),
            include_captions=self.options.include_captions,
            include_character=self.options.include_character, seed=self.options.seed,
            supersample=ss,
        )
        img = SceneRenderer(spec).render(na.duration * frac, painter=Painter(width, height, ss=ss))
        out = self.project.preview_dir / f"{lang}_{fmt}_scene{scene_index + 1}.png"
        img.save(out)
        return out

    # -------------------------------------------------------------------- run
    def run(self, *, compile_only: bool = False) -> Dict[str, object]:
        start = time.time()
        story = self.build_story()
        self.progress("narration", 0.02, "Synthesising narration")
        tracks = self.narrate(story)
        if compile_only:
            self.project.state["status"] = "scripted"
            self.project.save()
            return {"project": str(self.project.root), "story": story.to_dict(),
                    "tracks": {k: v.to_dict() for k, v in tracks.items()},
                    "seconds": time.time() - start}
        force_scenes = "scenes" in self.force
        self.progress("render", 0.02, "Rendering scenes")
        videos = self.render_videos(story, tracks, force=force_scenes or "video" in self.force)
        self.project.state["status"] = "complete"
        self.project.state["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.project.state["elapsed_seconds"] = round(time.time() - start, 1)
        self.project.save()
        self._write_report(story, tracks, videos)
        return {
            "project": str(self.project.root),
            "story": story.to_dict(),
            "videos": videos,
            "seconds": round(time.time() - start, 1),
            "stages": [r.__dict__ for r in self.log],
        }

    def _write_report(self, story: Story, tracks: Dict[str, NarrationTrack],
                      videos: Dict[str, dict]) -> None:
        report = {
            "topic": story.topic,
            "world": story.world,
            "generator": story.generator,
            "palette": story.palette,
            "scenes": [{"id": s.id, "purpose": s.purpose, "narration_en": s.text_for("en")[:180],
                        "narration_ur": s.text_for("ur")[:180]} for s in story.scenes],
            "story_warnings": story.warnings,
            "narration": {lang: {"engine": t.engine, "voice": t.voice,
                                 "timing_kind": t.timing_kind, "duration": round(t.duration, 2),
                                 "warnings": t.warnings} for lang, t in tracks.items()},
            "videos": videos,
            "stages": [r.__dict__ for r in self.log],
            "environment": _env_info(),
        }
        self.project.write_json(self.project.root / "report.json", report)

    def _record(self, result: StageResult) -> None:
        self.log.append(result)


def probe_wav(path: Path) -> float:
    from ..voice.base import read_wav

    audio, sr = read_wav(path)
    return len(audio) / float(sr)


def _track_from_meta(meta: dict, wav_path: Path) -> NarrationTrack:
    from ..voice.base import WordTiming, read_wav
    from ..voice.narration import ClauseAudio, SceneAudio

    audio, sr = read_wav(wav_path)
    scenes = []
    for s in meta.get("scenes", []):
        clauses = []
        for c in s.get("clauses", []):
            clauses.append(ClauseAudio(
                text=c["text"], start=float(c["start"]), end=float(c["end"]),
                words=[WordTiming(w["w"], float(w["s"]), float(w["e"])) for w in c.get("words", [])],
            ))
        scenes.append(SceneAudio(
            index=int(s["index"]), scene_id=s["scene_id"], start=float(s["start"]),
            duration=float(s["duration"]), frames=int(s["frames"]), clauses=clauses,
        ))
    return NarrationTrack(
        language=meta.get("language", "en"), sample_rate=int(meta.get("sample_rate", sr)),
        audio=audio, scenes=scenes, engine=meta.get("engine", "unknown"),
        voice=meta.get("voice", ""), timing_kind=meta.get("timing_kind", "proportional"),
        warnings=list(meta.get("warnings", [])),
    )


def _env_info() -> dict:
    import platform
    import sys

    from ..util.system import system_info

    info = system_info()
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        **info.to_dict(),
    }


def run_pipeline(options: RenderOptions, root: str | Path, **kwargs) -> Dict[str, object]:
    return Pipeline(options=options, root=root, **kwargs).run()
