"""Regression tests for the two bugs that made the narration unlistenable.

1. The espeak callback was asked for ``n_samples * 2`` samples, i.e. every audio
   buffer came back with a buffer-length of uninitialised heap memory appended.
   The audible result was a stream of noise bursts between words - "tatatatttta".
2. The track was never loudness-mastered, so it arrived peak-normalised and
   uneven.  ``master_voice`` must land on the documented -15 LUFS / -1.5 dBTP.
"""
from __future__ import annotations

import numpy as np
import pytest

from ckd.voice.base import SynthesisResult, polish_speech


def test_espeak_buffer_length_matches_declared_events():
    """Synthesised audio must last about as long as the word events claim."""
    from ckd.voice.espeak import EspeakEngine

    eng = EspeakEngine()
    text = ("Every day the sun delivers more energy to the roof than the whole "
            "house can use before sunset.")
    res = eng.synthesize(text, "en")
    assert isinstance(res, SynthesisResult)
    assert res.timings, "espeak must report word timings"
    spoken_end = max(t.end for t in res.timings)
    duration = len(res.audio) / res.sample_rate
    # before the fix the audio was ~2.4x the length of the speech it contained
    assert duration < spoken_end * 1.25 + 0.6, (
        f"audio {duration:.2f}s but last word ends at {spoken_end:.2f}s - "
        "the synthesis callback is reading past the end of its buffer"
    )
    # and the speech must actually fill the clip, not be padded with silence
    win = res.sample_rate // 100
    rms = np.array([float(np.sqrt(np.mean(res.audio[i:i + win].astype(np.float64) ** 2)))
                    for i in range(0, len(res.audio) - win, win)])
    assert (rms > rms.max() * 0.05).mean() > 0.45


def test_espeak_consonants_survive_polish():
    """The per-clause filter must not muffle the 4-9 kHz consonant band."""
    sr = 22050
    t = np.arange(sr) / sr
    sibilant = (0.2 * np.sin(2 * np.pi * 6000 * t)).astype(np.float32)
    out = polish_speech(sibilant, sr, lowpass_hz=10500.0)
    energy_in = float(np.sum(sibilant ** 2))
    energy_out = float(np.sum(out ** 2))
    assert energy_out > 0.5 * energy_in, "6 kHz should pass: it carries 's' and 't'"


def test_master_voice_hits_loudness_and_true_peak():
    from ckd.voice.mastering import master_voice, TARGET_LUFS, TRUE_PEAK_DB

    sr = 22050
    rng = np.random.default_rng(3)
    # speech-like: harmonic bursts with pauses and a realistic crest factor
    parts = []
    for _ in range(24):
        n = int(sr * rng.uniform(0.18, 0.32))
        t = np.arange(n) / sr
        f0 = rng.uniform(95, 140)
        sig = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 6))
        sig *= (0.35 / np.abs(sig).max()) * rng.uniform(0.4, 1.0)
        parts.append(sig.astype(np.float32))
        parts.append(np.zeros(int(sr * rng.uniform(0.05, 0.18)), dtype=np.float32))
    audio = np.concatenate(parts)
    res = master_voice(audio, sr)
    assert res.applied, res.warning
    assert len(res.audio) == len(audio), "mastering must not change the length"
    assert abs(res.lufs_out - TARGET_LUFS) <= 0.6, res.lufs_out
    assert res.true_peak_db <= TRUE_PEAK_DB + 0.3, res.true_peak_db


def test_master_voice_is_skippable_and_reports_failure(monkeypatch):
    from ckd.voice import mastering

    sr = 22050
    audio = np.zeros(sr, dtype=np.float32)
    res = mastering.master_voice(audio[: sr // 10], sr)
    assert not res.applied and res.warning
    assert len(res.audio) == sr // 10


def test_mux_keeps_loudness(tmp_path):
    """Muxing must not change the level: ffmpeg's default mono->stereo upmix
    scales by 1/sqrt(2) and silently costs 3 dB after mastering."""
    import subprocess

    import imageio_ffmpeg

    from ckd.render.ffmpeg import mux_audio
    from ckd.voice.base import read_wav, write_wav
    from ckd.voice.mastering import measure_lufs

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    sr = 24000
    t = np.arange(sr * 3) / sr
    tone = (0.25 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    wav = tmp_path / "tone.wav"
    write_wav(wav, tone, sr)
    silent = tmp_path / "silent.mp4"
    subprocess.run([exe, "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"color=c=black:s=320x240:r=24:d=3", "-pix_fmt", "yuv420p",
                    str(silent)], check=True)
    out = tmp_path / "muxed.mp4"
    mux_audio(silent, wav, out, fade_out=0.05, duration=3.0)
    raw = subprocess.run([exe, "-v", "quiet", "-i", str(out), "-vn", "-ac", "1",
                          "-ar", str(sr), "-f", "s16le", "-"], capture_output=True).stdout
    got = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    before, _ = measure_lufs(tone, sr)
    after, _ = measure_lufs(got, sr)
    assert abs(before - after) < 0.4, f"mux changed loudness {before:.2f} -> {after:.2f} LUFS"
