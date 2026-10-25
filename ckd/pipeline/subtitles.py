"""Subtitle writers (SRT + ASS) with RTL-safe styling.

Captions on screen are rendered by our own text engine, but we also emit soft
subtitle files so users can re-style or translate them later.  ASS styling uses
per-language fonts and alignment so RTL subtitles display correctly in players
that respect ASS (VLC, mpv, ffmpeg burn-in).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Sequence

from ..voice.base import WordTiming


def _ts_srt(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        s += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _ts_ass(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:d}:{m:02d}:{s:05.2f}"


def write_srt(path: str | Path, cues: Sequence[dict]) -> Path:
    """cues: [{start, end, text}] in seconds."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for i, c in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(f"{_ts_srt(c['start'])} --> {_ts_srt(c['end'])}")
        lines.append(c["text"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


DEFAULT_STYLES = {
    "en": {"font": "Inter", "size": 30, "bold": 0},
    "ur": {"font": "Noto Nastaliq Urdu", "size": 30, "bold": 0},
}


def write_ass(path: str | Path, cues: Sequence[dict], *, language: str = "en",
              play_w: int = 1280, play_h: int = 720) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    style = DEFAULT_STYLES.get(language, DEFAULT_STYLES["en"])
    margin_v = int(play_h * 0.14)
    alignment = 2  # bottom centre for both languages (RTL shaping handled by libass)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_w}
PlayResY: {play_h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['font']},{style['size']},&H00FFFFFF,&H00FFFFFF,&H00120A1E,&H80000 000,{style['bold']},0,0,0,100,100,0,0,3,3,0,{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for c in cues:
        text = str(c["text"]).replace("\n", "\\N")
        events.append(
            f"Dialogue: 0,{_ts_ass(c['start'])},{_ts_ass(c['end'])},Default,,0,0,0,,{{\\fad(120,120)}}{text}"
        )
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path
