"""Narration assembly: per-scene speech, word timelines and exact durations.

Key rules
  * Timing is generated *per language* - Urdu and English take different amounts
    of time, so scene lengths differ between the two videos.
  * Each clause is synthesised separately, which gives reliable clause
    boundaries (real audio lengths) even when word-level alignment is only
    approximate.
  * Scene audio is padded to an exact frame-aligned duration, so the video and
    audio timelines agree to the sample.
  * Results are cached by content hash: re-running a project does not re-synth
    unchanged text.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..content.schema import Story
from ..util.hashing import hash_json
from ..util.logging import get_logger
from .base import (
    SynthesisResult, TTSError, WordTiming, read_wav, split_clauses, write_wav, _normalize_audio,
    polish_speech, trim_silence,
)
from .espeak import EspeakEngine, EspeakVoice

LOG = get_logger("ckd.voice.narration")

CLAUSE_GAP = 0.22      # silence between clauses inside a scene
SCENE_TAIL = 0.34      # silence after the last clause of a scene
SCENE_LEAD = 0.22      # small lead-in before speech starts


@dataclass
class ClauseAudio:
    text: str
    start: float           # relative to scene start
    end: float
    words: List[WordTiming] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"text": self.text, "start": round(self.start, 3), "end": round(self.end, 3),
                "words": [w.to_dict() for w in self.words]}


@dataclass
class SceneAudio:
    index: int
    scene_id: str
    start: float                # global timeline
    duration: float             # frame-aligned
    frames: int
    clauses: List[ClauseAudio] = field(default_factory=list)
    audio: Optional[np.ndarray] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def words(self) -> List[WordTiming]:
        out: List[WordTiming] = []
        for c in self.clauses:
            out.extend(c.words)
        return out

    def words_relative(self) -> List[WordTiming]:
        """Word timings relative to the scene start (for captions)."""
        out: List[WordTiming] = []
        for c in self.clauses:
            for w in c.words:
                out.append(WordTiming(w.text, w.start, w.end))
        return out

    def to_dict(self) -> dict:
        return {
            "index": self.index, "scene_id": self.scene_id, "start": round(self.start, 3),
            "duration": round(self.duration, 3), "frames": self.frames,
            "clauses": [c.to_dict() for c in self.clauses], "warnings": self.warnings,
        }


@dataclass
class NarrationTrack:
    language: str
    sample_rate: int
    audio: np.ndarray
    scenes: List[SceneAudio]
    engine: str
    voice: str
    timing_kind: str
    warnings: List[str] = field(default_factory=list)
    mastering: dict = field(default_factory=dict)  # measured LUFS / true peak

    @property
    def duration(self) -> float:
        return len(self.audio) / float(self.sample_rate)

    def to_dict(self, *, include_words: bool = True) -> dict:
        return {
            "language": self.language,
            "engine": self.engine,
            "voice": self.voice,
            "timing_kind": self.timing_kind,
            "sample_rate": self.sample_rate,
            "duration": round(self.duration, 3),
            "warnings": self.warnings,
            "mastering": self.mastering,
            "scenes": [s.to_dict() for s in self.scenes],
        }


class SpeechCache:
    """Content-addressed speech cache (WAV + timings JSON)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _key(self, text: str, lang: str, engine: str, voice: str, speed: float) -> str:
        return hash_json({"t": text, "l": lang, "e": engine, "v": voice, "s": round(speed, 3)},
                         prefix="speech-v1")

    def get(self, text: str, lang: str, engine: str, voice: str, speed: float) -> Optional[SynthesisResult]:
        key = self._key(text, lang, engine, voice, speed)
        wav = self.root / f"{key}.wav"
        meta = self.root / f"{key}.json"
        if not (wav.exists() and meta.exists()):
            return None
        try:
            audio, sr = read_wav(wav)
            data = json.loads(meta.read_text(encoding="utf-8"))
            if abs(len(audio) / sr - float(data["duration"])) > 0.02:
                LOG.warning("speech cache corrupt for %s (duration mismatch); regenerating", key[:8])
                return None
            timings = [WordTiming(w["w"], float(w["s"]), float(w["e"])) for w in data.get("words", [])]
            return SynthesisResult(
                audio=audio, sample_rate=sr, timings=timings,
                timing_kind=data.get("timing_kind", "proportional"),
                engine=data.get("engine", engine), voice=data.get("voice", voice),
                warnings=list(data.get("warnings", [])),
            )
        except Exception as exc:  # noqa: BLE001 - a broken cache entry must not kill the run
            LOG.warning("speech cache unreadable (%s); regenerating", exc)
            return None

    def put(self, text: str, lang: str, engine: str, voice: str, speed: float,
            result: SynthesisResult) -> None:
        key = self._key(text, lang, engine, voice, speed)
        wav = self.root / f"{key}.wav"
        meta = self.root / f"{key}.json"
        tmp = wav.with_suffix(".wav.tmp")
        write_wav(tmp, result.audio, result.sample_rate)
        tmp.replace(wav)
        meta.write_text(
            json.dumps({**result.to_dict(), "text": text}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )


def resolve_engine(lang: str, pref: str = "auto") -> str:
    """Which engine *would* narrate this language, without downloading anything.

    Returns "espeak", "piper" (voice already cached) or "piper-download" (a
    download would be attempted).  The composer uses this to plan a duration with
    the right speaking rate: espeak is roughly half as fast as a Piper voice.
    """
    pref = str(pref or "auto")
    if pref.startswith("espeak"):
        return "espeak"
    try:
        from .registry import DEFAULT_VOICE_BY_LANG, voice_available
    except Exception:  # pragma: no cover - registry is always importable
        return "piper-download"
    voice_id = pref if pref not in ("auto", "", None) else DEFAULT_VOICE_BY_LANG.get(lang)
    if not voice_id:
        return "piper-download"
    return "piper" if voice_available(voice_id) else "piper-download"


class Narrator:
    """Creates narration tracks using the best available engine per language."""

    def __init__(
        self,
        *,
        voice_en: str = "auto",
        voice_ur: str = "auto",
        allow_download: bool = True,
        allow_espeak_fallback: bool = True,
        cache: SpeechCache | None = None,
        speed: float = 0.78,
    ) -> None:
        # 0.78 is a narration pace (about 160 wpm on Kokoro), not a demo pace.
        # At 1.0 the same script reads at 192 wpm, which sounds rushed on video.
        self.voice_en = voice_en
        self.voice_ur = voice_ur
        self.allow_download = allow_download
        self.allow_espeak_fallback = allow_espeak_fallback
        self.cache = cache or SpeechCache(Path.home() / ".cache" / "ckd" / "speech")
        self.speed = speed
        self._engines: Dict[str, object] = {}
        self.warnings: List[str] = []

    # ---------------------------------------------------------------- engines
    def engine_for(self, lang: str):
        if lang in self._engines:
            return self._engines[lang]
        pref = self.voice_en if lang == "en" else self.voice_ur
        engine = None
        if pref.startswith("espeak"):
            engine = EspeakEngine(EspeakVoice(name=pref.split(":", 1)[1] if ":" in pref else
                                              ("en-us" if lang == "en" else "ur")))
        elif pref.startswith("kokoro"):
            from .kokoro_engine import DEFAULT_VOICE, KokoroEngine

            voice = pref.split(":", 1)[1] if ":" in pref else DEFAULT_VOICE
            engine = KokoroEngine(voice, speed=self.speed, allow_download=self.allow_download)
        else:
            engine = self._neural_engine(lang, pref)
        self._engines[lang] = engine
        return engine

    def _neural_engine(self, lang: str, pref: str):
        """Piper if a voice is cached, then Kokoro for English, then espeak.

        Each failure is reported in ``self.warnings`` - the pipeline surfaces
        those in ``report.json``, so a fallback is never silent.
        """
        problems: List[str] = []
        if pref not in ("auto", "", None):
            try:
                from .piper_engine import PiperEngine

                return PiperEngine(pref, allow_download=self.allow_download, speed=self.speed)
            except Exception as exc:  # noqa: BLE001 - fall back by design
                problems.append(f"piper {pref}: {type(exc).__name__}: {exc}")
        else:
            try:
                from .piper_engine import PiperEngine

                return PiperEngine.for_language(lang, allow_download=self.allow_download,
                                                speed=self.speed)
            except Exception as exc:  # noqa: BLE001 - fall back by design
                problems.append(f"piper: {type(exc).__name__}: {exc}")
        if lang == "en":
            try:
                from .kokoro_engine import DEFAULT_VOICE, KokoroEngine

                return KokoroEngine(DEFAULT_VOICE, speed=self.speed,
                                    allow_download=self.allow_download)
            except Exception as exc:  # noqa: BLE001 - fall back by design
                problems.append(f"kokoro: {type(exc).__name__}: {exc}")
        msg = f"{lang}: neural voice unavailable ({'; '.join(problems)})."
        if not self.allow_espeak_fallback:
            raise TTSError(msg + " Enable the offline espeak fallback or fix the voice.")
        LOG.warning(msg + " Using the offline espeak development voice.")
        self.warnings.append(msg + " Falling back to espeak (development voice).")
        name = "ur" if lang == "ur" else "en-us"
        return EspeakEngine(EspeakVoice(name=name))

    # -------------------------------------------------------------- synthesis
    def synth(self, text: str, lang: str) -> SynthesisResult:
        engine = self.engine_for(lang)
        ename = getattr(engine, "name", "unknown")
        vname = getattr(getattr(engine, "voice", None), "name", "") or getattr(
            getattr(engine, "spec", None), "id", "")
        speed = 1.0 if ename == "espeak" else self.speed
        cached = self.cache.get(text, lang, ename, str(vname), speed)
        if cached is not None:
            return cached
        result = engine.synthesize(text, lang)
        # no per-clause peak normalisation: it flattens the read into that
        # machine-gun cadence.  Loudness is fixed once, by the mastering stage.
        polished = polish_speech(result.audio, result.sample_rate,
                                 lowpass_hz=10500.0 if ename == "espeak" else 12000.0)
        audio, lead, trail = trim_silence(polished, result.sample_rate)
        # shift word timings by the trimmed lead-in
        result.timings = [WordTiming(w.text, max(0.0, w.start - lead), max(0.0, w.end - lead))
                          for w in result.timings]
        result.audio = audio.astype(np.float32)
        self.cache.put(text, lang, ename, str(vname), speed, result)
        return result

    def build(self, story: Story, lang: str, *, fps: int, max_seconds: Optional[float] = None) -> NarrationTrack:
        """Synthesise the whole story for one language with frame-exact scenes."""
        engine = self.engine_for(lang)
        ename = getattr(engine, "name", "unknown")
        vname = getattr(getattr(engine, "voice", None), "name", "") or getattr(
            getattr(engine, "spec", None), "id", "")
        sample_rate = 22050
        scene_audios: List[SceneAudio] = []
        chunks: List[np.ndarray] = []
        cursor = 0.0
        timing_kinds = set()
        warnings = list(self.warnings)
        for idx, scene in enumerate(story.scenes):
            text = scene.text_for(lang)
            clauses_text = split_clauses(text)
            if not clauses_text:
                raise TTSError(f"scene {scene.id}: no narration text for {lang}")
            pieces: List[np.ndarray] = []
            clause_records: List[ClauseAudio] = []
            t = SCENE_LEAD
            pieces.append(np.zeros(int(SCENE_LEAD * sample_rate), dtype=np.float32))
            for ci, clause in enumerate(clauses_text):
                res = self.synth(clause, lang)
                timing_kinds.add(res.timing_kind)
                for w in res.warnings:
                    if w not in warnings:
                        warnings.append(w)
                sample_rate = res.sample_rate
                dur = len(res.audio) / float(sample_rate)
                words = [WordTiming(w.text, t + w.start, t + w.end) for w in res.timings]
                clause_records.append(ClauseAudio(text=clause, start=t, end=t + dur, words=words))
                pieces.append(res.audio)
                t += dur
                if ci < len(clauses_text) - 1:
                    gap = np.zeros(int(CLAUSE_GAP * sample_rate), dtype=np.float32)
                    pieces.append(gap)
                    t += CLAUSE_GAP
            t += SCENE_TAIL
            scene_audio_raw = np.concatenate(pieces)
            frames = max(1, int(round(t * fps)))
            duration = frames / float(fps)
            pad = int(round(duration * sample_rate)) - len(scene_audio_raw)
            if pad > 0:
                scene_audio_raw = np.concatenate(
                    [scene_audio_raw, np.zeros(pad, dtype=np.float32)]
                )
            elif pad < 0:  # never truncate speech; extend the scene instead
                frames = int(np.ceil(len(scene_audio_raw) / sample_rate * fps))
                duration = frames / float(fps)
                scene_audio_raw = np.concatenate(
                    [scene_audio_raw,
                     np.zeros(int(round(duration * sample_rate)) - len(scene_audio_raw), dtype=np.float32)]
                )
            scene_audios.append(
                SceneAudio(index=idx, scene_id=scene.id, start=cursor, duration=duration,
                           frames=frames, clauses=clause_records, audio=scene_audio_raw,
                           warnings=[])
            )
            chunks.append(scene_audio_raw)
            cursor += duration
        full = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        if max_seconds is not None and cursor > max_seconds * 1.35:
            warnings.append(
                f"narration is {cursor:.0f}s for a {max_seconds:.0f}s target; "
                "scenes were not truncated (quality first) - rerun with a lower duration target or edit the script"
            )
        kind = "espeak-events" if timing_kinds == {"espeak-events"} else (
            sorted(timing_kinds)[0] if len(timing_kinds) == 1 else "mixed"
        )
        return NarrationTrack(
            language=lang, sample_rate=sample_rate, audio=full, scenes=scene_audios,
            engine=ename, voice=str(vname), timing_kind=kind, warnings=warnings,
        )
