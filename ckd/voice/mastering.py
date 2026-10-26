"""Voice-over mastering: the difference between "TTS output" and a usable voice track.

Research summary (why this chain, in this order)
-----------------------------------------------
Professional explainer voice-over is not just "a good voice".  The delivery is
mastered so it survives phone speakers and platform loudness normalisation:

* **Loudness** — YouTube normalises to about **-14 LUFS**, Apple Podcasts and most
  web explainers sit at **-16 LUFS**, EBU R128 broadcast is -23 LUFS.  Every one of
  those specs also caps **true peak at -1 dBTP** (inter-sample peaks clip after AAC
  encoding).  We target **-15 LUFS integrated, -1.5 dBTP**: loud enough not to be
  pulled *down* by YouTube, quiet enough to keep headroom for the AAC encoder.
  (ITU-R BS.1770 / EBU R128 measurement; platform targets are conventions.)
* **Signal chain order** — noise handling → EQ → compression → de-essing →
  levelling → limiter.  Compression before de-essing amplifies sibilance; EQ
  before compression keeps the compressor from reacting to rumble.
* **EQ** — high-pass around 85-100 Hz removes rumble and plosive thumps that eat
  headroom; a small dip at ~210 Hz removes boxiness; +1.5 dB at ~3 kHz restores
  consonant presence ("intelligibility band") without harshness.
* **Compression** — 2-3:1 with a slow-ish release keeps a consistent level across
  sentences, which is what makes narration feel calm instead of jumpy.
* **De-essing** — formant synthesisers (and many neural voices) over-emphasise
  sibilance; untamed "s/sh" is the main cause of listener fatigue.
* **Limiter** — a final safety net, not a level tool: peak stop at -1.5 dBTP.

The chain is implemented with ffmpeg filters (already a dependency), in two
passes so ``loudnorm`` can run in linear mode instead of squashing dynamics.

Nothing here is a substitute for a good engine: this module makes a *clear* voice
sound professional; it cannot make a formant synthesiser sound human.  See
``docs/VOICES.md`` for the engine hierarchy (Piper neural → espeak dev fallback).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

from ..util.logging import get_logger

LOG = get_logger("ckd.voice.master")

# mastering targets (see module docstring)
TARGET_LUFS = -15.0
TRUE_PEAK_DB = -1.5
LRA = 11.0


@dataclass
class MasterResult:
    audio: np.ndarray
    applied: bool
    lufs_in: Optional[float] = None
    lufs_out: Optional[float] = None
    true_peak_db: Optional[float] = None
    warning: str = ""

    def to_dict(self) -> dict:
        return {
            "applied": self.applied,
            "target_lufs": TARGET_LUFS,
            "target_true_peak_db": TRUE_PEAK_DB,
            "lufs_in": None if self.lufs_in is None else round(self.lufs_in, 2),
            "lufs_out": None if self.lufs_out is None else round(self.lufs_out, 2),
            "true_peak_db": None if self.true_peak_db is None else round(self.true_peak_db, 2),
            "warning": self.warning,
        }


def _ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _run(args, timeout: float = 600.0) -> subprocess.CompletedProcess:
    # ffmpeg can wedge on odd inputs; a timeout turns that into a reported
    # failure instead of a render that never finishes.
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, returncode=124, stdout="",
                                           stderr=f"ffmpeg timed out after {timeout:.0f}s")


def _write_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    import wave

    pcm = np.clip(audio, -1.0, 1.0)
    data = (pcm * 32767.0).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(int(sr))
        fh.writeframes(data)


def _read_wav(path: Path, sr: int) -> np.ndarray:
    import wave

    with wave.open(str(path), "rb") as fh:
        raw = fh.readframes(fh.getnframes())
        width = fh.getsampwidth()
    if width == 2:
        a = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        a = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:  # pragma: no cover - defensive
        raise ValueError(f"unsupported wav width {width}")
    return a


def measure_lufs(audio: np.ndarray, sr: int) -> Tuple[Optional[float], Optional[float]]:
    """Integrated loudness (LUFS) and true peak (dBTP) via ffmpeg ebur128."""
    with tempfile.TemporaryDirectory(prefix="ckd-master-") as td:
        src = Path(td) / "in.wav"
        _write_wav(src, audio, sr)
        proc = _run([_ffmpeg(), "-hide_banner", "-nostats", "-i", str(src),
                     "-af", "ebur128=peak=true", "-f", "null", "-"])
    text = proc.stderr
    lufs = None
    tp = None
    m = re.findall(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", text)
    if m:
        lufs = float(m[-1])
    m = re.findall(r"Peak:\s*(-?\d+(?:\.\d+)?)\s*dBFS", text)
    if m:
        tp = float(m[-1])
    return lufs, tp


def master_voice(audio: np.ndarray, sr: int, *, target_lufs: float = TARGET_LUFS,
                 true_peak: float = TRUE_PEAK_DB) -> MasterResult:
    """Apply the broadcast-style dialogue chain to a narration track.

    Three stages, in the order the research says to use them:

    1. **tone** - high-pass, boxiness dip, presence lift, de-ess.  No level change.
    2. **dynamics** - 4:1 compression, 3 ms attack, 3 dB makeup.  This is the stage
       that matters.  Both formant and neural voices arrive far too peaky: the raw
       espeak track measures **19.5 dB peak-to-loudness**, where broadcast dialogue
       sits around 14.  A peak-to-loudness ratio that high cannot be brought to
       -15 LUFS without either clipping or leaving the track 1-2 dB quiet - which
       is exactly what happened on the first attempt (measured -16.2 LUFS).
       Squeezing the crest to ~16 dB first lets the loudness stage land on target.
    3. **loudness** - ``loudnorm`` to -15 LUFS / -1.5 dBTP, then one *static* trim
       if the measurement is still off.  The trim never uses a limiter, so it can
       only add gain that the true peak allows; it can never reintroduce distortion.

    Two-pass *linear* loudnorm was tried and abandoned: linear mode refuses to
    apply the +13 dB the track needs because that would push peaks over the
    ceiling, so it silently falls back and undershoots.

    Returns the mastered audio at the same sample rate and padded/trimmed to the
    same length, so scene boundaries and word timings stay valid.  On any failure
    the original audio is returned *with a warning*, never silently.
    """
    a = np.asarray(audio, dtype=np.float32)
    if a.size < sr * 0.2:  # under 200 ms: nothing sensible to master
        return MasterResult(audio=a, applied=False, warning="track too short to master")
    lufs_in, tp_in = measure_lufs(a, sr)
    with tempfile.TemporaryDirectory(prefix="ckd-master-") as td:
        src = Path(td) / "in.wav"
        out = Path(td) / "out.wav"
        _write_wav(src, a, sr)
        chain = ",".join([
            "highpass=f=88:poles=2",
            "equalizer=f=215:t=q:w=0.9:g=-1.3",
            "equalizer=f=3100:t=q:w=1.1:g=1.6",
            "deesser=i=0.35:m=0.6:f=0.45",
            "acompressor=threshold=0.02:ratio=4:attack=3:release=120:knee=6:makeup=3",
            f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={LRA}",
        ])
        proc = _run([_ffmpeg(), "-hide_banner", "-nostats", "-y", "-i", str(src),
                     "-af", chain, "-ar", str(int(sr)), "-ac", "1",
                     "-c:a", "pcm_s16le", str(out)])
        if proc.returncode != 0 or not out.exists():
            LOG.warning("mastering chain failed: %s", proc.stderr[-400:])
            return MasterResult(audio=a, applied=False, lufs_in=lufs_in, true_peak_db=tp_in,
                                warning="ffmpeg mastering failed; audio left unmastered")
        b = _read_wav(out, sr)
        lufs_now, tp_now = measure_lufs(b, sr)
        # static trim, bounded by the true-peak headroom: no limiter, no distortion
        if lufs_now is not None and tp_now is not None:
            room = true_peak - tp_now            # dB we may still add
            need = target_lufs - lufs_now        # dB we would like to add
            gain = max(-2.0, min(2.0, min(need, room)))
            if abs(gain) >= 0.05:
                b = (b * (10 ** (gain / 20.0))).astype(np.float32)
                lufs_now, tp_now = measure_lufs(b, sr)
    # keep the exact length so scene boundaries and word timings stay valid
    if len(b) > len(a):
        b = b[: len(a)]
    elif len(b) < len(a):
        b = np.concatenate([b, np.zeros(len(a) - len(b), dtype=np.float32)])
    # Loudness is a *target*, true peak is a *limit*.  When they conflict the
    # peak wins - that is what a mastering engineer does too - so anything inside
    # 0.8 dB of target is reported as success rather than as a failure.
    warning = ""
    if lufs_now is None or abs(lufs_now - target_lufs) > 0.8:
        warning = "loudness target not reached (%.1f LUFS)" % (
            lufs_now if lufs_now is not None else float("nan"))
    elif tp_now is not None and tp_now > true_peak + 0.5:
        warning = "true-peak target not reached (%.1f dBTP)" % tp_now
    return MasterResult(audio=b.astype(np.float32), applied=True, lufs_in=lufs_in,
                        lufs_out=lufs_now, true_peak_db=tp_now, warning=warning)
