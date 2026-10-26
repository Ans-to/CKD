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


# ---------------------------------------------------------------- script import
def test_import_script_keeps_narration_verbatim():
    from ckd.content.script_import import import_script

    text = (
        "HOW NOKIA LOST ITS EMPIRE\n\n**Target duration:** 7-9 minutes\n\n"
        "SCENE 1 — THE HOOK\n\n**Time:** 0:00–0:35\n\n**[VOICEOVER]**\n\n"
        "Imagine building a company so powerful that millions carry its classic phone.\n\n"
        "A company that dominates the global mobile phone market across the world.\n\n"
        "**[VISUAL DIRECTION]**\n\n- 0:00-0:05: A classic mobile phone ringing in a dark room.\n"
        "- 0:05-0:12: A world map illuminates as mobile phone icons spread across the world.\n\n"
        "**[ON-SCREEN TEXT]**\n\n2007 — market leader\n\n"
        "SCENE 2 — THE FALL\n\n**Time:** 0:35–1:10\n\n**[VOICEOVER]**\n\nThen the market changed.\n\n"
        "**[VISUAL DIRECTION]**\n\n- Show a financial chart of market share.\n"
    )
    story = import_script(text)
    assert story.world == "business" and story.palette == "documentary"
    assert len(story.scenes) == 2
    assert story.scenes[0].narration["en"] == (
        "Imagine building a company so powerful that millions carry its classic phone. "
        "A company that dominates the global mobile phone market across the world.")
    assert story.scenes[0].character.get("visible") is False, "documentaries are faceless"
    types = [el["type"] for el in story.scenes[0].elements]
    assert "phone" in types and "globe" in types
    # the writer's supers are kept, and drawn last so they sit on top
    assert types[-1] == "lower_third"
    assert any("No footage" in w for w in story.warnings), story.warnings
    # a multi-language run must refuse rather than invent Urdu
    ur_story = import_script(text, languages=("en", "ur"))
    assert not ur_story.scenes[0].narration.get("ur")


def test_import_script_never_invents_figures():
    from ckd.content.script_import import import_script

    text = ("SCENE 1 — NUMBERS\n\n**[VOICEOVER]**\n\n"
            "The transaction was completed, but its value remained undisclosed.\n\n"
            "**[VISUAL DIRECTION]**\n\n- Show a financial chart of the transaction value.\n")
    story = import_script(text)
    chart = [el for el in story.scenes[0].elements if el["type"] == "chart"]
    assert chart, "a chart was requested"
    assert not chart[0]["params"].get("values"), "no series may be invented"


def test_beats_cut_on_the_spoken_sentences_not_the_timecodes():
    """A writer's timecode is a plan; the picture must follow the voice.

    The script below gives three numbered shots over 30 s, but the narration is
    two sentences and the voice reads them in about nine seconds.  The render
    follows the sentences: one picture per sentence, each cut landing on the
    moment the next sentence is spoken.
    """
    from ckd.content.script_import import import_script
    from ckd.scene.timing import assign_actions
    from ckd.voice.narration import ClauseAudio, SceneAudio

    text = ("SCENE 1 — CUTS\n\n**[VOICEOVER]**\n\n"
            "One two three four five six seven eight. Nine ten eleven twelve.\n\n"
            "**[VISUAL DIRECTION]**\n\n- 0:00-0:05: The first thing.\n"
            "- 0:05-0:15: The second thing.\n- 0:15-0:30: The third thing.\n\n"
            "**[ON-SCREEN TEXT]**\n\nA writer's lower third\n")
    story = import_script(text)
    scene = story.scenes[0]
    beats = [a for a in scene.actions if a["action"].startswith("beat")]
    assert len(beats) == 2, "one beat per spoken sentence"
    assert all("at_frac" not in a for a in beats), "beats are not pinned by the writer"
    assert scene.headline_hold <= 1.0, "scene title must clear before the first dialogue visual"

    clauses = [ClauseAudio(text="one", start=0.3, end=3.0, words=[]),
               ClauseAudio(text="two", start=9.0, end=12.0, words=[])]
    na = SceneAudio(index=0, scene_id="s01", start=0.0, duration=15.0, frames=360,
                    clauses=clauses, audio=np.zeros(10, dtype=np.float32))
    acts = {a.id: (a.start, a.end) for a in assign_actions(scene, na, scene_duration=15.0)}
    assert acts["beat1"][0] <= clauses[0].start, acts
    assert abs(acts["beat2"][0] - clauses[1].start) <= 0.35, acts
    assert abs(acts["beat1"][1] - acts["beat2"][0]) < 1e-6, "cut, no gap"
    assert acts["beat1"][1] > acts["supers"][0], "a super overlays; it must not end the visual beat"
    assert abs(acts["supers"][1] - acts["supers_out"][0]) < 1e-6


def test_cta_also_gets_one_visual_per_spoken_sentence():
    from ckd.content.script_import import import_script

    text = ("SCENE 1 — ENDING\n\n**[VOICEOVER]**\n\n"
            "That is the story. The lesson remains.\n\n"
            "OPTIONAL CALL TO ACTION\n\nFollow for more. Share this video.")
    story = import_script(text)
    cta = next(scene for scene in story.scenes if scene.id == "cta")
    beats = [a for a in cta.actions if a["action"].startswith("beat")]
    cards = [e for e in cta.elements if e["type"] == "statement"]
    assert len(beats) == 2
    assert len(cards) == 2
    assert [card["params"]["en"] for card in cards] == ["Follow for more", "Share this video"]


def test_a_picture_is_never_drawn_twice_in_one_video():
    """One picture per sentence, and no picture repeated anywhere in the reel."""
    from ckd.content.script_import import _visual_key, import_script

    text = ("SCENE 1 — PHONES\n\n**[VOICEOVER]**\n\n"
            "A classic phone. It rang in the dark. Another mobile phone.\n\n"
            "**[VISUAL DIRECTION]**\n\n- A classic phone.\n- A phone.\n"
            "- A mobile phone.\n\n"
            "SCENE 2 — MORE PHONES\n\n**[VOICEOVER]**\n\n"
            "A classic phone again. It was still ringing.\n\n"
            "**[VISUAL DIRECTION]**\n\n- A classic phone.\n- A phone.\n")
    story = import_script(text)
    seen = set()
    for scene in story.scenes:
        subjects = [e for e in scene.elements
                    if e["type"] not in ("skyline", "statement", "lower_third")]
        for el in subjects:
            key = _visual_key(el["type"], el["params"])
            assert key not in seen, f"{key} drawn twice"
            seen.add(key)
        cards = [e for e in scene.elements if e["type"] == "statement"]
        for card in cards:
            assert card["params"]["en"], "a card must carry the sentence's own words"
