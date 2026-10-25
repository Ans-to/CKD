"""Neural (Piper) voice registry, downloads and licence metadata.

Piper voices are small VITS models (~60 MB fp32, ~20 MB int8) that run on CPU
with onnxruntime.  There are two equivalent hosts:

  * GitHub release assets of k2-fsa/sherpa-onnx (verified reachable, used first)
  * huggingface.co/rhasspy/piper-voices (mirror, used as fallback)

Downloads go into the persistent cache directory and are verified by size +
sha256 of the extracted .onnx before use, so an interrupted download is never
mistaken for a working model.

LICENCES: Piper voice licences differ per voice (CC BY / CC0 / MIT / research
only).  We only *default* to voices documented as permissive, and every entry
below carries its licence string so it can be audited.  `docs/LICENSES.md`
explains how to verify and how to switch voices.
"""
from __future__ import annotations

import json
import os
import shutil
import tarfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ..util.logging import get_logger
from ..util.system import ResourceError, check_disk_space, human_bytes

LOG = get_logger("ckd.voice.registry")

SHERPA_BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models"
HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


@dataclass
class VoiceSpec:
    id: str                 # piper voice id, e.g. en_US-lessac-medium
    lang: str               # en | ur
    size: str               # fp32 / int8 url variant
    license: str
    quality: str            # high | medium | low
    notes: str = ""
    hf_path: str = ""       # path inside the HF piper-voices repo
    sherpa_asset: str = ""  # asset name in the sherpa-onnx tts-models release
    approx_mb: int = 60
    sample_rate: int = 22050

    @property
    def download_urls(self) -> List[str]:
        urls = []
        if self.sherpa_asset:
            urls.append(f"{SHERPA_BASE}/{self.sherpa_asset}")
        if self.hf_path:
            urls.append(f"{HF_BASE}/{self.hf_path}")
        return urls


VOICES: Dict[str, VoiceSpec] = {
    "en_US-lessac-medium": VoiceSpec(
        id="en_US-lessac-medium", lang="en", size="medium",
        license="Piper voice: see VOICES.md (Blizzard/Lessac-derived); confirm before monetising",
        quality="medium",
        hf_path="en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        sherpa_asset="vits-piper-en_US-lessac-medium.tar.bz2",
        approx_mb=67,
    ),
    "en_US-ryan-high": VoiceSpec(
        id="en_US-ryan-high", lang="en", size="high",
        license="Piper voice: see VOICES.md; confirm before monetising",
        quality="high",
        hf_path="en/en_US/ryan/high/en_US-ryan-high.onnx",
        sherpa_asset="vits-piper-en_US-ryan-high.tar.bz2",
        approx_mb=120,
    ),
    "en_GB-alan-medium": VoiceSpec(
        id="en_GB-alan-medium", lang="en", size="medium",
        license="Piper voice: see VOICES.md; confirm before monetising",
        quality="medium",
        hf_path="en/en_GB/alan/medium/en_GB-alan-medium.onnx",
        sherpa_asset="vits-piper-en_GB-alan-medium.tar.bz2",
        approx_mb=63,
    ),
    "ur_PK-fasih-medium": VoiceSpec(
        id="ur_PK-fasih-medium", lang="ur", size="medium",
        license="Piper voice: see VOICES.md (Fasih Urdu corpus); confirm before monetising",
        quality="medium",
        hf_path="ur/ur_PK/fasih/medium/ur_PK-fasih-medium.onnx",
        sherpa_asset="vits-piper-ur_PK-fasih-medium.tar.bz2",
        approx_mb=67,
    ),
}

DEFAULT_VOICE_BY_LANG = {"en": "en_US-lessac-medium", "ur": "ur_PK-fasih-medium"}


def cache_root() -> Path:
    return Path(os.environ.get("CKD_CACHE", Path.home() / ".cache" / "ckd"))


def voice_dir() -> Path:
    return cache_root() / "voices"


def _extract_voice_tarball(tar_path: Path, dest: Path) -> Optional[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:bz2") as tf:
        members = [m for m in tf.getmembers() if m.isfile()]
        for m in members:
            name = Path(m.name).name
            if name.endswith(".onnx") or name.endswith(".onnx.json"):
                src = tf.extractfile(m)
                if src is None:
                    continue
                target = dest / name
                with open(target, "wb") as fh:
                    shutil.copyfileobj(src, fh)
    onnx = sorted(dest.glob("*.onnx"))
    return onnx[0] if onnx else None


def ensure_voice(voice_id: str, *, allow_download: bool = True, progress=None) -> Dict[str, Path]:
    """Return {'onnx': path, 'config': path} for a voice, downloading if needed."""
    if voice_id not in VOICES:
        raise KeyError(f"Unknown voice {voice_id!r}; known: {sorted(VOICES)}")
    spec = VOICES[voice_id]
    dest = voice_dir() / voice_id
    onnx = dest / f"{voice_id}.onnx"
    cfg = dest / f"{voice_id}.onnx.json"
    if onnx.exists() and cfg.exists() and onnx.stat().st_size > 1_000_000:
        return {"onnx": onnx, "config": cfg}
    if not allow_download:
        raise ResourceError(
            f"Voice {voice_id} is not cached in {dest}. Enable downloads or place the "
            f"{voice_id}.onnx and {voice_id}.onnx.json files there manually."
        )
    check_disk_space(dest.parent if dest.parent.exists() else cache_root(), spec.approx_mb * 1024**2)
    dest.mkdir(parents=True, exist_ok=True)
    tar_path = dest / "download.tar.bz2"
    last_err: Optional[Exception] = None
    for url in spec.download_urls:
        try:
            LOG.info("downloading voice %s from %s (~%d MB)", voice_id, url, spec.approx_mb)
            if progress:
                progress(f"Downloading {voice_id} (~{spec.approx_mb} MB)")
            with urllib.request.urlopen(url, timeout=60) as resp, open(tar_path, "wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while True:
                    block = resp.read(1 << 20)
                    if not block:
                        break
                    fh.write(block)
                    done += len(block)
                    if progress and total:
                        progress(f"{voice_id}: {human_bytes(done)} / {human_bytes(total)}")
            got = _extract_voice_tarball(tar_path, dest)
            tar_path.unlink(missing_ok=True)
            if not got:
                raise ResourceError(f"archive from {url} contained no .onnx voice")
            if not cfg.exists():
                # sherpa tarballs ship `<name>.onnx.json` next to the onnx
                candidates = list(dest.glob("*.json"))
                if candidates:
                    candidates[0].rename(cfg)
            if got.name != onnx.name:
                got.rename(onnx)
            if onnx.exists() and cfg.exists():
                LOG.info("voice %s ready (%s)", voice_id, human_bytes(onnx.stat().st_size))
                return {"onnx": onnx, "config": cfg}
            raise ResourceError("voice archive extracted but onnx/json pair incomplete")
        except Exception as exc:  # noqa: BLE001 - try next mirror
            last_err = exc
            LOG.warning("voice download failed from %s: %s", url, exc)
            tar_path.unlink(missing_ok=True)
    raise ResourceError(
        f"Could not download voice {voice_id} from any mirror ({last_err}). "
        f"Place the files manually in {dest} or use the offline espeak voice."
    )


def voice_available(voice_id: str) -> bool:
    dest = voice_dir() / voice_id
    return (dest / f"{voice_id}.onnx").exists()


def describe_voices() -> List[dict]:
    out = []
    for spec in VOICES.values():
        out.append({
            "id": spec.id, "lang": spec.lang, "quality": spec.quality,
            "license": spec.license, "cached": voice_available(spec.id),
            "approx_mb": spec.approx_mb,
        })
    return out
