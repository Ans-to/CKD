"""espeak-ng engine via ctypes (no subprocess, no shell, no network).

espeak-ng reports a WORD event per spoken word with its character offset and
audio position, which gives us *measured* word onsets - much better than a
proportional guess.  The audio callback gives us the raw PCM, so we never write
temporary files.
"""
from __future__ import annotations

import ctypes
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import espeakng_loader
import numpy as np

from .base import SynthesisResult, TTSError, WordTiming, proportional_timings
from ..util.logging import get_logger

LOG = get_logger("ckd.voice.espeak")

# espeak_EVENT from speak_lib.h (events are passed as a C array terminated by 0)
class _Event(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("unique_identifier", ctypes.c_uint),
        ("text_position", ctypes.c_int),
        ("length", ctypes.c_int),
        ("audio_position", ctypes.c_int),
        ("sample", ctypes.c_int),
        ("user_data", ctypes.c_void_p),
        ("id", ctypes.c_char * 8),
    ]


_CB = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.POINTER(ctypes.c_short), ctypes.c_int, ctypes.POINTER(_Event)
)

EVENT_WORD = 1
EVENT_END = 5

_LOCK = threading.Lock()
_LIB = None
_STATE: Dict[str, object] = {"chunks": [], "events": []}


def phonemize(text: str, voice: str = "en-us") -> str:
    """IPA phonemes for ``text`` from the shared espeak instance.

    Used by the Kokoro engine: Kokoro's token vocabulary *is* the espeak-ng IPA
    inventory, so the Urdu engine's library doubles as the English phonemiser.
    It must go through ``_library()`` - calling ``espeak_Initialize`` a second
    time on an engine that already has a synth callback installed wedges
    ``espeak_Synchronize`` (found the hard way: a test run hung for 15 minutes).
    """
    lib = _library()
    with _LOCK:
        lib.espeak_SetVoiceByName(voice.encode())
        chunks: List[str] = []
        buf = ctypes.create_string_buffer(text.encode("utf-8"))
        ptr = ctypes.cast(buf, ctypes.c_void_p)
        handle = ctypes.pointer(ptr)
        for _ in range(2000):  # hard stop: never loop forever on odd input
            res = lib.espeak_TextToPhonemes(handle, 1, 0x02)  # 0x02 = IPA
            if not res:
                break
            piece = res.decode("utf-8").strip()
            if piece:
                chunks.append(piece)
        return " ".join(chunks)


def _library():
    global _LIB
    if _LIB is not None:
        return _LIB
    lib = ctypes.CDLL(espeakng_loader.get_library_path())
    lib.espeak_Initialize.restype = ctypes.c_int
    rate = lib.espeak_Initialize(1, 0, espeakng_loader.get_data_path().encode(), 0)
    if rate <= 0:
        raise TTSError("espeak-ng failed to initialise (espeak_Initialize)")
    lib.espeak_SetVoiceByName.restype = ctypes.c_int
    lib.espeak_Synth.argtypes = [
        ctypes.c_char_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_int,
        ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p,
    ]
    lib.espeak_SetParameter.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lib.espeak_TextToPhonemes.restype = ctypes.c_char_p
    lib.espeak_TextToPhonemes.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.c_int]

    @_CB
    def _cb(wav, n_samples, events):
        chunks = _STATE["chunks"]
        evs = _STATE["events"]
        if n_samples > 0 and wav:
            # n_samples is the number of 16-bit samples in the buffer.  Reading
            # n_samples * 2 used to pull a buffer-length of uninitialised heap
            # memory into every chunk: that is the "tatatatttta" noise.
            arr = np.ctypeslib.as_array(wav, shape=(n_samples,))
            chunks.append(arr.copy())
        if events:
            i = 0
            while i < 5000:
                ev = events[i]
                if ev.type == 0:
                    break
                if ev.type == EVENT_WORD:
                    evs.append((ev.text_position, ev.length, ev.audio_position))
                i += 1
        return 0

    _STATE["callback"] = _cb  # keep alive
    lib.espeak_SetSynthCallback(_cb)
    _STATE["rate"] = rate
    _LIB = lib
    LOG.info("espeak-ng ready (sample rate %d Hz)", rate)
    return lib


VOICE_ALIASES = {
    "en": "en-us",
    "en-us": "en-us",
    "en-gb": "en-gb",
    "ur": "ur",
    "ur-pk": "ur",
}


@dataclass
class EspeakVoice:
    name: str = "en-us"
    rate: int = 150  # words per minute (measured 1.3 wps in this build)
    pitch: int = 46
    variant: str | None = None
    amplitude: int = 84


class EspeakEngine:
    name = "espeak"

    def __init__(self, voice: EspeakVoice | None = None) -> None:
        self.voice = voice or EspeakVoice()
        _library()

    def _apply_voice(self, lang: str, rate: Optional[int], pitch: Optional[int]) -> EspeakVoice:
        lib = _library()
        name = self.voice.name
        if name in ("auto", "", None):
            name = VOICE_ALIASES.get(lang, "en-us")
        name = VOICE_ALIASES.get(name, name)
        if self.voice.variant:
            name = f"{name}+{self.voice.variant}"
        rc = lib.espeak_SetVoiceByName(name.encode())
        if rc != 0:
            LOG.warning("espeak voice %r unavailable; falling back to en-us", name)
            name = "en-us"
            lib.espeak_SetVoiceByName(b"en-us")
        v = EspeakVoice(name=name, rate=rate or self.voice.rate, pitch=pitch or self.voice.pitch,
                        amplitude=self.voice.amplitude)
        lib.espeak_SetParameter(1, int(v.rate), 0)     # espeakRATE
        lib.espeak_SetParameter(3, int(v.pitch), 0)    # espeakPITCH
        lib.espeak_SetParameter(2, int(v.amplitude), 0)  # espeakVOLUME
        return v

    def synthesize(
        self,
        text: str,
        lang: str = "en",
        *,
        rate: Optional[int] = None,
        pitch: Optional[int] = None,
    ) -> SynthesisResult:
        text = " ".join(text.split())
        if not text:
            raise TTSError("empty text")
        lib = _library()
        with _LOCK:
            v = self._apply_voice(lang, rate, pitch)
            _STATE["chunks"] = []
            _STATE["events"] = []
            payload = text.encode("utf-8")
            rc = lib.espeak_Synth(payload, len(payload) + 1, 0, 1, 0, 1, None, None)
            if rc != 0:
                raise TTSError(f"espeak_Synth failed with code {rc}")
            lib.espeak_Synchronize()
            chunks = list(_STATE["chunks"])
            events = list(_STATE["events"])
        rate_hz = int(_STATE.get("rate", 22050))
        if not chunks:
            raise TTSError("espeak produced no audio")
        audio = np.concatenate(chunks).astype(np.float32) / 32768.0
        timings, kind, warnings = self._word_timings(text, events, len(audio) / rate_hz)
        return SynthesisResult(
            audio=audio, sample_rate=rate_hz, timings=timings, timing_kind=kind,
            engine="espeak", voice=v.name, warnings=warnings,
        )

    def _word_timings(self, text: str, events, duration: float):
        """Map espeak WORD events (byte offsets) onto script words."""
        warnings: List[str] = []
        raw = text.encode("utf-8")
        # byte offset -> character index
        byte_to_char = {}
        b = 0
        for i, ch in enumerate(text):
            byte_to_char[b] = i
            b += len(ch.encode("utf-8"))
        onsets: List[Tuple[int, float]] = []
        for pos, length, audio_ms in events:
            char_idx = byte_to_char.get(pos)
            if char_idx is None:
                continue
            onsets.append((char_idx, audio_ms / 1000.0))
        words = [w for w in text.split(" ") if w]
        if not onsets or len(onsets) < max(2, len(words) // 3):
            warnings.append(
                f"espeak reported {len(onsets)} word onsets for {len(words)} words; "
                "falling back to proportional word timing (approximate)"
            )
            return proportional_timings(text, duration), "proportional", warnings
        # align onset list to whitespace tokens using character positions
        starts = []
        cursor = 0
        for w in words:
            idx = text.find(w, cursor)
            starts.append(idx if idx >= 0 else cursor)
            cursor = max(cursor, idx + len(w))
        timings: List[WordTiming] = []
        prev_char = 0
        j = 0
        for i, w in enumerate(words):
            next_start = duration
            while j < len(onsets) and onsets[j][0] < starts[i]:
                j += 1
            if j < len(onsets):
                t0 = onsets[j][1]
            else:
                t0 = timings[-1].end if timings else 0.0
            k = j + 1
            if k < len(onsets):
                t1 = onsets[k][1]
            else:
                t1 = duration
            t1 = max(t0 + 0.05, min(t1, duration))
            timings.append(WordTiming(w, t0, t1))
            prev_char = starts[i] + len(w)
        return timings, "espeak-events", warnings

    @staticmethod
    def available() -> bool:
        try:
            _library()
            return True
        except Exception:
            return False

    @staticmethod
    def languages() -> List[str]:
        return ["en", "ur"]
