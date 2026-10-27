"""Kokoro-82M neural voice: the default English narration engine.

Why Kokoro and not Piper
------------------------
Piper is the obvious choice for offline neural TTS, but every published Piper
voice is Git-LFS backed on Hugging Face / GitHub, and this build environment can
reach neither (see docs/VOICES.md for the full list of dead ends, including the
LFS batch API returning 403).  Kokoro-82M is published as plain ONNX bytes and a
copy of the weights - model, tokenizer and all 60 voice packs - is redistributed
inside the ``expo-kokoro`` npm package, and **npm is reachable**.  So the same
model that powers a lot of "sounds like a person" demos is available here
without any hosted inference API: it runs on CPU through onnxruntime.

Model details
-------------
* Kokoro-82M v1.0, q8 quantised: 92 361 116 bytes, Apache-2.0.
* 24 kHz output, 256-dim style vectors, one style row per token count.
* Inputs: ``input_ids`` [1, N] int64, ``style`` [1, 256] float32, ``speed`` [1].
* Phonemes: Kokoro's vocabulary *is* the espeak-ng IPA inventory, which is
  convenient - we already ship espeak-ng for the Urdu voice, so the same ctypes
  binding produces the phonemes.

Honesty note
------------
Kokoro gives no word-level alignment.  Word timings from this engine are
distributed across the clause in proportion to syllable weight and are labelled
``estimated`` in every artifact - never presented as measured.
"""
from __future__ import annotations

import ctypes
import hashlib
import io
import json
import os
import tarfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from ..util.logging import get_logger
from .base import SynthesisResult, TTSError, WordTiming, proportional_timings

LOG = get_logger("ckd.voice.kokoro")

# The one download this engine needs.  Pinned, because the asset inside a
# package version is what the hash check below is written against.
NPM_TGZ_URL = "https://registry.npmjs.org/expo-kokoro/-/expo-kokoro-1.1.9.tgz"
MODEL_MEMBER = "package/build/kokoro-quantized.onnx"
TOKENIZER_MEMBER = "package/build/tokenizer.json"
MODEL_BYTES = 92_361_116
# sha256 of the assembled q8 model, published by the kokoro-q8-shards package
# ("Reassembly is byte-identical") and identical to the copy in expo-kokoro.
MODEL_SHA256 = "fbae9257e1e05ffc727e951ef9b9c98418e6d79f1c9b6b13bd59f5c9028a1478"
SAMPLE_RATE = 24_000

# voices worth using for explainer narration (Kokoro v1.0 English)
VOICES = {
    "af_heart": "warm female, the Kokoro reference voice",
    "af_bella": "bright female",
    "af_nicole": "soft female (whisper style)",
    "am_michael": "steady male, documentary read",
    "am_fenrir": "deep male",
    "am_puck": "lively male",
    "bf_emma": "British female",
    "bm_george": "British male",
}
DEFAULT_VOICE = "af_heart"


def cache_dir() -> Path:
    env = os.environ.get("CKD_KOKORO_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "ckd" / "kokoro"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, *, timeout: float = 600.0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "ckd-video-studio"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as fh:
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            fh.write(block)
    tmp.replace(dest)


def ensure_assets(*, voice: str = DEFAULT_VOICE, allow_download: bool = True) -> Dict[str, Path]:
    """Make sure model + tokenizer + one voice pack exist locally.

    Returns paths and never claims success it did not verify: the model hash is
    checked on first use, and a corrupt or truncated file is deleted rather than
    left to fail mysteriously later.
    """
    root = cache_dir()
    root.mkdir(parents=True, exist_ok=True)
    model = root / "kokoro-quantized.onnx"
    tok = root / "tokenizer.json"
    vbin = root / "voices" / f"{voice}.bin"
    stamp = root / "assets.json"

    if model.exists() and model.stat().st_size != MODEL_BYTES:
        LOG.warning("kokoro model has wrong size (%d), re-fetching", model.stat().st_size)
        model.unlink()

    need_download = not (model.exists() and tok.exists() and vbin.exists())
    if need_download:
        if not allow_download:
            raise TTSError("Kokoro weights are not cached and downloads are disabled "
                           "(run `python -m ckd voices --install` once)")
        tgz = root / "expo-kokoro-1.1.9.tgz"
        if not tgz.exists() or tgz.stat().st_size < 80_000_000:
            LOG.info("downloading Kokoro assets from npm (%s)", NPM_TGZ_URL)
            t0 = time.time()
            _download(NPM_TGZ_URL, tgz)
            LOG.info("downloaded %.1f MB in %.0fs", tgz.stat().st_size / 1e6, time.time() - t0)
        with tarfile.open(tgz, "r:gz") as tf:
            if not model.exists():
                LOG.info("extracting model (%d bytes)", MODEL_BYTES)
                member = tf.extractfile(MODEL_MEMBER)
                if member is None:
                    raise TTSError("kokoro model missing from npm package")
                tmp = model.with_suffix(".part")
                with tmp.open("wb") as fh:
                    while True:
                        block = member.read(1 << 20)
                        if not block:
                            break
                        fh.write(block)
                tmp.replace(model)
            if not tok.exists():
                member = tf.extractfile(TOKENIZER_MEMBER)
                if member is None:
                    raise TTSError("kokoro tokenizer missing from npm package")
                tok.write_bytes(member.read())
            if not vbin.exists():
                member = tf.extractfile(f"package/build/voices/{voice}.bin")
                if member is None:
                    raise TTSError(f"voice {voice!r} is not in the package; "
                                   f"choose from {', '.join(sorted(VOICES))}")
                vbin.parent.mkdir(parents=True, exist_ok=True)
                vbin.write_bytes(member.read())
        digest = _sha256(model)
        if digest != MODEL_SHA256:
            model.unlink()
            raise TTSError(f"Kokoro model hash mismatch ({digest[:16]}...); deleted")
        stamp.write_text(json.dumps({"model_sha256": digest, "voice": voice,
                                     "source": NPM_TGZ_URL}, indent=2), encoding="utf-8")
        tgz.unlink(missing_ok=True)
    return {"model": model, "tokenizer": tok, "voice": vbin, "root": root}


def assets_present(voice: str = DEFAULT_VOICE) -> bool:
    root = cache_dir()
    return ((root / "kokoro-quantized.onnx").exists()
            and (root / "tokenizer.json").exists()
            and (root / "voices" / f"{voice}.bin").exists())


# --------------------------------------------------------------- phonemisation
def phonemize(text: str, lang: str = "en") -> str:
    """espeak-ng IPA for one clause, with its trailing punctuation preserved.

    Kokoro's tokenizer knows `. , ! ?` and uses them as pause marks; espeak's
    phoneme output drops them, so the closing punctuation is put back by hand.
    """
    from .espeak import phonemize as _ipa

    out = _ipa(text, "en-us" if lang == "en" else "ur")
    tail = text.rstrip()[-1:] if text.strip() else ""
    if tail in ".,!?;:—":
        out = out + tail
    return out


@dataclass
class KokoroVoice:
    name: str = DEFAULT_VOICE
    speed: float = 1.0


class KokoroEngine:
    """CPU Kokoro-82M inference behind the same interface as the espeak engine."""

    name = "kokoro"

    def __init__(self, voice: str = DEFAULT_VOICE, *, speed: float = 1.0,
                 allow_download: bool = True) -> None:
        if not voice:
            voice = DEFAULT_VOICE
        self.voice = KokoroVoice(voice, speed)
        self.allow_download = allow_download
        self._assets = ensure_assets(voice=voice, allow_download=allow_download)
        self._session = None
        self._vocab = json.loads(
            self._assets["tokenizer"].read_text(encoding="utf-8"))["model"]["vocab"]
        raw = np.fromfile(self._assets["voice"], dtype=np.float32)
        if raw.size % 256 != 0:
            raise TTSError(f"voice pack {voice} has an unexpected size")
        self._styles = raw.reshape(-1, 256)

    # ------------------------------------------------------------------ internals
    def _sess(self):
        if self._session is None:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.intra_op_num_threads = max(1, min(4, (os.cpu_count() or 2)))
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            self._session = ort.InferenceSession(str(self._assets["model"]),
                                                 sess_options=opts,
                                                 providers=["CPUExecutionProvider"])
        return self._session

    def token_ids(self, phonemes: str) -> List[int]:
        ids = [self._vocab[ch] for ch in phonemes if ch in self._vocab]
        return ids

    def speak_phonemes(self, phonemes: str) -> np.ndarray:
        ids = self.token_ids(phonemes)
        if not ids:
            return np.zeros(0, dtype=np.float32)
        # Kokoro's style row is indexed by token count (510 rows, one per length)
        style = self._styles[min(len(ids), self._styles.shape[0] - 1)][None, :]
        out = self._sess().run(None, {
            "input_ids": np.asarray([ids], dtype=np.int64),
            "style": style.astype(np.float32),
            "speed": np.asarray([self.voice.speed], dtype=np.float32),
        })[0]
        return np.asarray(out, dtype=np.float32).reshape(-1)

    # --------------------------------------------------------------------- public
    def synthesize(self, text: str, lang: str = "en") -> SynthesisResult:
        if lang != "en":
            raise TTSError("Kokoro v1.0 has no Urdu voice; use the espeak engine for ur")
        ph = phonemize(text, lang)
        audio = self.speak_phonemes(ph)
        if audio.size == 0:
            raise TTSError(f"Kokoro produced no audio for {text!r}")
        peak = float(np.abs(audio).max())
        if peak > 1e-6:
            audio = audio * (0.95 / peak)
        dur = audio.size / float(SAMPLE_RATE)
        return SynthesisResult(
            audio=audio.astype(np.float32),
            sample_rate=SAMPLE_RATE,
            timings=proportional_timings(text, dur),
            timing_kind="estimated",
            engine="kokoro",
            voice=self.voice.name,
        )

    def describe(self) -> dict:
        return {"engine": self.name, "voice": self.voice.name,
                "speed": self.voice.speed, "sample_rate": SAMPLE_RATE,
                "timing_kind": "estimated", "model": "Kokoro-82M-v1.0-q8",
                "license": "Apache-2.0"}
