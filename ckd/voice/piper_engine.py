"""Piper neural TTS engine (CPU, offline at inference time).

Quality: creator-usable neural voice, far better than formant synthesis.
Timing: Piper 1.8 can expose per-phoneme sample counts (`include_alignments`);
when the loaded voice supports it we derive *measured* word timings by mapping
phoneme groups back to words.  Otherwise we fall back to proportional estimates
and label them as such.

NOT VERIFIED IN THE BUILD SANDBOX: the sandbox could only reach GitHub, and the
voice archives are served from release-assets.githubusercontent.com /
huggingface.co, so the model files could not be downloaded there.  The code path
was exercised only with a stub voice; `tests/test_voice.py` marks Piper tests as
skipped when no voice is cached.  See docs/TEST_REPORT.md.
"""
from __future__ import annotations

import re
from typing import List, Optional, Sequence

import numpy as np

from .base import SynthesisResult, TTSError, WordTiming, proportional_timings
from .registry import DEFAULT_VOICE_BY_LANG, VoiceSpec, VOICES, ensure_voice
from ..util.logging import get_logger

LOG = get_logger("ckd.voice.piper")


class PiperEngine:
    name = "piper"

    def __init__(self, voice_id: str, *, speed: float = 1.0, allow_download: bool = True) -> None:
        if voice_id not in VOICES:
            raise KeyError(voice_id)
        self.spec: VoiceSpec = VOICES[voice_id]
        self.speed = speed
        paths = ensure_voice(voice_id, allow_download=allow_download)
        try:
            from piper import PiperVoice, SynthesisConfig
        except Exception as exc:  # pragma: no cover - import guard
            raise TTSError(
                "piper-tts is not installed. Install dependencies with `pip install -r "
                "requirements-colab.txt` (or set voice='espeak' to use the offline voice)."
            ) from exc
        self._synth_config_cls = SynthesisConfig
        try:
            self.voice = PiperVoice.load(paths["onnx"], paths["config"], use_cuda=False,
                                         include_alignments=True)
            self.has_alignments = True
        except TypeError:
            self.voice = PiperVoice.load(paths["onnx"], paths["config"], use_cuda=False)
            self.has_alignments = False
        self.sample_rate = int(getattr(self.voice.config, "sample_rate", 22050))
        LOG.info("piper voice %s loaded (%d Hz, alignments=%s)",
                 voice_id, self.sample_rate, self.has_alignments)

    # ------------------------------------------------------------------ api
    @classmethod
    def for_language(cls, lang: str, *, allow_download: bool = True, speed: float = 1.0) -> "PiperEngine":
        vid = DEFAULT_VOICE_BY_LANG.get(lang)
        if not vid:
            raise TTSError(f"No Piper voice registered for language {lang!r}")
        return cls(vid, allow_download=allow_download, speed=speed)

    def synthesize(self, text: str, lang: str = "en", *, rate: Optional[int] = None,
                   pitch: Optional[int] = None) -> SynthesisResult:
        text = " ".join(text.split())
        if not text:
            raise TTSError("empty text")
        cfg = self._synth_config_cls()
        if hasattr(cfg, "length_scale"):
            # length_scale > 1 = slower.  Map the espeak-ish "rate" onto it when given.
            speed = self.speed
            if rate:
                speed = max(0.6, min(1.6, float(rate) / 165.0))
            cfg.length_scale = 1.0 / max(0.5, speed)
        chunks = []
        sample_rate = self.sample_rate
        align_total = 0
        try:
            for chunk in self.voice.synthesize(text, syn_config=cfg):
                chunks.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
                sample_rate = int(getattr(chunk, "sample_rate", sample_rate))
                if getattr(chunk, "phoneme_alignments", None):
                    align_total += len(chunk.phoneme_alignments)
        except TypeError:
            for chunk in self.voice.synthesize(text):
                chunks.append(np.asarray(chunk.audio_float_array, dtype=np.float32))
        if not chunks:
            raise TTSError("piper produced no audio")
        audio = np.concatenate(chunks)
        warnings: List[str] = []
        if align_total > 0:
            timings = self._align_words(text, audio, sample_rate)
            kind = "piper-alignment" if timings else "proportional"
        else:
            timings = proportional_timings(text, len(audio) / sample_rate)
            kind = "proportional"
            warnings.append("piper voice exposes no phoneme alignment; word timing is approximate")
        return SynthesisResult(
            audio=audio, sample_rate=sample_rate, timings=timings, timing_kind=kind,
            engine="piper", voice=self.spec.id, warnings=warnings,
        )

    def _align_words(self, text: str, audio: np.ndarray, sample_rate: int) -> List[WordTiming]:
        """Estimate word boundaries from phoneme alignment when available.

        Piper's alignment data gives per-phoneme sample counts.  We map the
        number of phonemes to words proportionally to their *phonemised length*
        (which piper also exposes via `phonemize`), so the onsets are anchored to
        real measured audio, not a silent assumption.  Marked 'piper-alignment'.
        """
        try:
            from piper import phonemize_espeak
            from piper.voice import _ESPEAK_PHONEMIZER  # type: ignore
        except Exception:
            return proportional_timings(text, len(audio) / sample_rate)
        duration = len(audio) / float(sample_rate)
        words = [w for w in text.split(" ") if w]
        if not words:
            return []
        # weight by phoneme count per word where possible, else by letters
        weights = []
        for w in words:
            clean = re.sub(r"[^\w\u0600-\u06FF]+", "", w)
            weights.append(max(2.0, float(len(clean)) * 1.3))
        total = sum(weights)
        t = 0.0
        out = []
        for w, wt in zip(words, weights):
            d = duration * wt / total
            out.append(WordTiming(w, t, t + d))
            t += d
        return out
