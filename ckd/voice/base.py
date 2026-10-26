"""Offline text-to-speech engines.

Two engines, both fully offline at inference time:

``piper``
    Neural VITS voices (Piper).  Best quality; English + Urdu (`ur_PK-fasih`).
    Model weights are downloaded once into the persistent cache.  Inference is
    CPU-only, ~real time on a free Colab core for medium voices.

``espeak``
    espeak-ng formant synthesiser (LGPL).  Always available (pip wheel bundles
    the library + data), tiny, and *explicitly labelled as a development voice*
    in the UI and in the project metadata - it is not creator-quality.

Both return an audio buffer plus a word timeline.  The timeline is tagged with
its provenance (`espeak-events` = measured word onsets, `piper-alignment` =
measured phoneme alignment, `proportional` = estimated) so captions can honestly
report whether they are word-accurate or approximate.
"""
from __future__ import annotations

import math
import re
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..util.logging import get_logger

LOG = get_logger("ckd.voice")

# A word timing entry: (text, start_s, end_s)
Timing = Tuple[str, float, float]


@dataclass
class WordTiming:
    text: str
    start: float
    end: float

    def to_dict(self) -> dict:
        return {"w": self.text, "s": round(self.start, 3), "e": round(self.end, 3)}


@dataclass
class SynthesisResult:
    audio: np.ndarray  # float32 mono in [-1, 1]
    sample_rate: int
    timings: List[WordTiming] = field(default_factory=list)
    timing_kind: str = "proportional"  # espeak-events | piper-alignment | proportional
    engine: str = "espeak"
    voice: str = ""
    warnings: List[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return len(self.audio) / float(self.sample_rate)

    def to_dict(self) -> dict:
        return {
            "engine": self.engine,
            "voice": self.voice,
            "sample_rate": self.sample_rate,
            "duration": round(self.duration, 3),
            "timing_kind": self.timing_kind,
            "words": [t.to_dict() for t in self.timings],
            "warnings": self.warnings,
        }


class TTSError(RuntimeError):
    pass


def write_wav(path: str | Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write mono float32 audio as 16-bit PCM WAV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(audio, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(int(sample_rate))
        fh.writeframes(pcm.tobytes())


def read_wav(path: str | Path) -> Tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as fh:
        n = fh.getnframes()
        rate = fh.getframerate()
        raw = fh.readframes(n)
        width = fh.getsampwidth()
        channels = fh.getnchannels()
    if width != 2:
        raise TTSError(f"Unsupported WAV sample width {width}")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


# --------------------------------------------------------------------- helpers
_SENT_RE = re.compile(r"(?<=[.!?۔؟])\s+")


def split_clauses(text: str) -> List[str]:
    """Split narration into synthesis clauses (sentences, Urdu danda aware)."""
    text = " ".join(text.split())
    if not text:
        return []
    parts = _SENT_RE.split(text)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # very long sentences: split again on Urdu commas so prosody can breathe
        if len(p) > 220:
            for sub in re.split(r"(?<=[،;:])\s+", p):
                if sub.strip():
                    out.append(sub.strip())
        else:
            out.append(p)
    return out


def _tokens(text: str) -> List[str]:
    return [t for t in text.split(" ") if t]


def proportional_timings(text: str, duration: float, *, start: float = 0.0) -> List[WordTiming]:
    """Estimate word timings by syllable-ish weight (documented as approximate)."""
    words = _tokens(text)
    if not words:
        return []
    weights = []
    for w in words:
        vowels = len(re.findall(r"[aeiouyɑɛɪɔʊəaeiouAEIOU\u0670\u064E\u064F\u0650\u0653\u0654]", w))
        weights.append(max(2.0, float(len(w)) * 0.6 + vowels))
    total = sum(weights)
    t = start
    out: List[WordTiming] = []
    for w, wt in zip(words, weights):
        d = duration * wt / total
        out.append(WordTiming(w, t, t + d))
        t += d
    return out


def _fir_lowpass(sr: int, cutoff: float, taps: int = 63) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff / sr * n) * np.hamming(taps)
    return h / h.sum()


_LP_CACHE: dict = {}


def polish_speech(audio: np.ndarray, sr: int, *, lowpass_hz: float = 10500.0,
                  highpass_hz: float = 80.0, target_peak: float = 0.97) -> np.ndarray:
    """Per-clause conditioning: remove rumble, tame the harshest band, no level games.

    Two deliberate changes from the first version (both were hurting intelligibility):

    * the low-pass sits at 10.5 kHz instead of 6.8 kHz.  Speech consonants carry
      most of their cues between 4 and 9 kHz; cutting at 6.8 kHz leaves the voice
      muffled and "swallowed" - exactly the effect that makes synthetic speech
      unreadable on a phone speaker.
    * no per-clause peak normalisation.  Normalising every clause to the same peak
      flattens the read into a machine-gun cadence; consistent loudness is handled
      once, at the end, by `ckd.voice.mastering`.
    """
    if audio.size == 0:
        return audio
    key = (sr, lowpass_hz, highpass_hz)
    kernel = _LP_CACHE.get(key)
    if kernel is None:
        kernel = _fir_lowpass(sr, lowpass_hz)
        _LP_CACHE[key] = kernel
    a = audio.astype(np.float32)
    lp = np.convolve(a, kernel, mode="same").astype(np.float32)
    hp_kernel = _fir_lowpass(sr, highpass_hz)
    rumble = np.convolve(a, hp_kernel, mode="same").astype(np.float32)
    a = (lp - rumble * 0.9).astype(np.float32)
    # safety clip only: leave the read's dynamics alone
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    if peak > target_peak:
        a = a * (target_peak / peak)
    return a.astype(np.float32)


def _normalize_audio(audio: np.ndarray, target_peak: float = 0.92) -> np.ndarray:
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak < 1e-6:
        return audio
    return audio * (target_peak / peak)


def trim_silence(audio: np.ndarray, sample_rate: int, thresh: float = 0.006,
                 keep: float = 0.03) -> Tuple[np.ndarray, float, float]:
    """Trim leading/trailing silence. Returns (audio, lead_removed_s, trail_removed_s)."""
    if audio.size == 0:
        return audio, 0.0, 0.0
    env = np.abs(audio)
    win = max(1, int(sample_rate * 0.01))
    kernel = np.ones(win, dtype=np.float32) / win
    smooth = np.convolve(env, kernel, mode="same")
    above = np.where(smooth > thresh)[0]
    if above.size == 0:
        return np.zeros(0, dtype=np.float32), len(audio) / sample_rate, 0.0
    start = max(0, above[0] - int(sample_rate * keep))
    end = min(len(audio), above[-1] + int(sample_rate * keep))
    return audio[start:end], start / sample_rate, (len(audio) - end) / sample_rate


def upsample_linear(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    if src_rate == dst_rate or audio.size == 0:
        return audio
    n_out = int(round(audio.size * dst_rate / src_rate))
    x_old = np.linspace(0.0, 1.0, audio.size, endpoint=False)
    x_new = np.linspace(0.0, 1.0, n_out, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)
