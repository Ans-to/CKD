"""ffmpeg wrapper (binary from imageio-ffmpeg, no system install needed).

Used for: per-scene H.264 encoding from raw RGB frames, lossless concatenation,
audio muxing, and output verification (ffprobe-style checks via `ffmpeg -i`).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..util.logging import get_logger

LOG = get_logger("ckd.render.ffmpeg")


def ffmpeg_path() -> str:
    env = os.environ.get("CKD_FFMPEG")
    if env and Path(env).exists():
        return env
    for cand in ("ffmpeg",):
        found = shutil.which(cand)
        if found:
            return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "ffmpeg not found. Install it with `pip install imageio-ffmpeg` (bundles a static "
            "binary) or apt-get install ffmpeg."
        ) from exc


def ffmpeg_version() -> str:
    out = subprocess.run([ffmpeg_path(), "-hide_banner", "-version"], capture_output=True, text=True)
    return (out.stdout or "").splitlines()[0] if out.stdout else "unknown"


def encode_frames(
    frame_iter: Iterable,
    out_path: str | Path,
    *,
    width: int,
    height: int,
    fps: int,
    crf: int = 22,
    preset: str = "veryfast",
    total_frames: Optional[int] = None,
    progress=None,
) -> Path:
    """Encode RGB PIL frames to an H.264 MP4 (no audio)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".part.mp4")
    cmd = [
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-",
        "-an",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-g", str(max(2, fps * 2)),
        str(tmp),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    count = 0
    try:
        for frame in frame_iter:
            if frame.mode != "RGB":
                frame = frame.convert("RGB")
            if frame.size != (width, height):
                frame = frame.resize((width, height))
            proc.stdin.write(frame.tobytes())
            count += 1
            if progress and total_frames and count % max(1, int(fps)) == 0:
                progress(count, total_frames)
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        rc = proc.wait()
    except BrokenPipeError:
        err = proc.stderr.read().decode("utf-8", "replace")
        rc = proc.wait()
    if rc != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg scene encode failed (rc={rc}): {err[-1500:]}")
    tmp.replace(out_path)
    return out_path


def concat_videos(parts: Sequence[str | Path], out_path: str | Path) -> Path:
    """Concatenate scene MP4s with the concat demuxer (stream copy, no re-encode)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    listing = out_path.with_suffix(".concat.txt")
    with open(listing, "w", encoding="utf-8") as fh:
        for part in parts:
            fh.write(f"file '{Path(part).resolve().as_posix()}'\n")
    tmp = out_path.with_suffix(".part.mp4")
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
           "-movflags", "+faststart", str(tmp)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        listing.unlink(missing_ok=True)
        tmp.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg concat timed out")
    listing.unlink(missing_ok=True)
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg concat failed: {proc.stderr[-1200:]}")
    tmp.replace(out_path)
    return out_path


def mux_audio(video: str | Path, audio: str | Path, out_path: str | Path,
              *, fade_out: float = 0.35, duration: float | None = None) -> Path:
    """Mux narration onto a silent video.

    We do NOT use `apad` + `-shortest`: with stream copy that combination can
    stall in some ffmpeg builds.  The narration WAV is already padded to the
    exact frame-aligned video length, so a hard `-t` bound is enough.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if duration is None:
        duration = probe(video).duration
    tmp = out_path.with_suffix(".part.mp4")
    fade = max(0.05, min(fade_out, max(0.05, duration / 4)))
    cmd = [
        ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
        # Explicit upmix: ffmpeg's default mono->stereo rematrix scales by
        # 1/sqrt(2), which quietly drops the whole track by 3 dB after mastering.
        "-af", f"pan=stereo|c0=c0|c1=c0,"
               f"afade=t=out:st={max(0.0, duration - fade):.3f}:d={fade:.3f}",
        "-t", f"{duration:.3f}",
        "-movflags", "+faststart",
        str(tmp),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=max(120, 12 + duration * 3))
    except subprocess.TimeoutExpired:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg mux timed out for {video}")
    if proc.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg mux failed: {proc.stderr[-1200:]}")
    tmp.replace(out_path)
    return out_path


@dataclass
class MediaInfo:
    path: Path
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: Optional[str]
    has_audio: bool
    nb_frames: Optional[int] = None
    bitrate_kbps: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "path": str(self.path), "duration": round(self.duration, 3), "width": self.width,
            "height": self.height, "fps": round(self.fps, 3), "video_codec": self.video_codec,
            "audio_codec": self.audio_codec, "has_audio": self.has_audio,
            "nb_frames": self.nb_frames, "bitrate_kbps": self.bitrate_kbps,
        }


def probe(path: str | Path) -> MediaInfo:
    """Minimal ffprobe replacement using `ffmpeg -i` output parsing."""
    path = Path(path)
    proc = subprocess.run([ffmpeg_path(), "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True)
    text = proc.stderr or ""
    if "Invalid data" in text or not text:
        raise RuntimeError(f"not a readable media file: {path}")
    duration = 0.0
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", text)
    if m:
        duration = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    width = height = 0
    fps = 0.0
    video_codec = ""
    mv = re.search(r"Stream #\d+:\d+.*?: Video: (\w+).*?, (\d+)x(\d+)", text)
    if mv:
        video_codec = mv.group(1)
        width, height = int(mv.group(2)), int(mv.group(3))
        mf = re.search(r"(\d+(?:\.\d+)?) fps", text)
        if mf:
            fps = float(mf.group(1))
        else:
            mt = re.search(r"(\d+)/(\d+) .*fps", text)
    audio_codec = None
    ma = re.search(r"Stream #\d+:\d+.*?: Audio: (\w+)", text)
    if ma:
        audio_codec = ma.group(1)
    nb_frames = None
    mbr = re.search(r"bitrate: (\d+) kb/s", text)
    return MediaInfo(
        path=path, duration=duration, width=width, height=height, fps=fps,
        video_codec=video_codec, audio_codec=audio_codec, has_audio=audio_codec is not None,
        nb_frames=nb_frames, bitrate_kbps=float(mbr.group(1)) if mbr else None,
    )


def verify_video(path: str | Path, *, expect_w: int, expect_h: int, expect_fps: float,
                 expect_duration: float, tolerance: float = 0.35,
                 require_audio: bool = True) -> Tuple[bool, List[str]]:
    """Full integrity check used before a render is marked complete."""
    problems: List[str] = []
    try:
        info = probe(path)
    except Exception as exc:  # noqa: BLE001
        return False, [f"unreadable: {exc}"]
    if (info.width, info.height) != (expect_w, expect_h):
        problems.append(f"size {info.width}x{info.height} != {expect_w}x{expect_h}")
    if abs(info.fps - expect_fps) > 0.6:
        problems.append(f"fps {info.fps} != {expect_fps}")
    if abs(info.duration - expect_duration) > tolerance:
        problems.append(f"duration {info.duration:.2f}s != {expect_duration:.2f}s")
    if info.video_codec not in ("h264", "libx264"):
        problems.append(f"video codec {info.video_codec} not h264")
    if require_audio and not info.has_audio:
        problems.append("no audio stream")
    # decode the whole file to catch truncated/corrupt streams
    dec = subprocess.run([ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-v", "error",
                          "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
    if dec.returncode != 0 or dec.stderr.strip():
        problems.append(f"decode errors: {dec.stderr.strip()[:300]}")
    return (not problems), problems


def extract_frame(video: str | Path, out_png: str | Path, at: float) -> Path:
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{max(0.0, at):.3f}",
           "-i", str(video), "-frames:v", "1", str(out_png)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"frame extract failed: {proc.stderr[-600:]}")
    return out_png


def loudness_stats(path: str | Path) -> Optional[Dict[str, float]]:
    """Peak/mean volume of the audio track (used by the media-integrity test)."""
    proc = subprocess.run([ffmpeg_path(), "-hide_banner", "-i", str(path), "-af", "volumedetect",
                           "-f", "null", "-"], capture_output=True, text=True)
    text = proc.stderr or ""
    mean = re.search(r"mean_volume: (-?\d+(?:\.\d+)?) dB", text)
    peak = re.search(r"max_volume: (-?\d+(?:\.\d+)?) dB", text)
    if not mean or not peak:
        return None
    return {"mean_db": float(mean.group(1)), "peak_db": float(peak.group(1))}
