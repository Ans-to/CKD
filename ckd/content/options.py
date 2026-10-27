"""Option definitions shared by the CLI, notebook UI and pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence

from .schema import SUPPORTED_FORMATS, SUPPORTED_LANGUAGES, aspect_size

FPS_CHOICES = (24, 30)
QUALITY_PRESETS: Dict[str, Dict[str, Any]] = {
    # name: height, supersample factor, x264 preset, crf
    "draft": {"height": 480, "supersample": 1, "preset": "veryfast", "crf": 26},
    "standard": {"height": 720, "supersample": 2, "preset": "veryfast", "crf": 22},
    "high": {"height": 1080, "supersample": 2, "preset": "medium", "crf": 20},
}


@dataclass
class RenderOptions:
    topic: str
    languages: List[str] = field(default_factory=lambda: ["en"])
    formats: List[str] = field(default_factory=lambda: ["landscape"])
    duration: float = 45.0  # target narration length in seconds
    quality: str = "standard"
    fps: int = 24
    include_captions: bool = True
    include_character: bool = True
    voice_en: str = "auto"  # auto | piper:<voice> | espeak
    voice_ur: str = "auto"
    allow_espeak_fallback: bool = True
    master_audio: bool = True  # dialogue mastering (-15 LUFS / -1.5 dBTP)
    script_path: str = ""  # render a written script instead of generating one
    script_text: bool = False  # script_path was written from pasted text, not chosen
    llm: str = "none"  # none | gguf path
    seed: int = 7
    notes: str = ""  # optional user outline / extra facts
    palette: str = "auto"
    burn_captions: bool = True
    subtitle_files: bool = True

    def __post_init__(self) -> None:
        self.languages = [l for l in dict.fromkeys(self.languages)]
        self.formats = [f for f in dict.fromkeys(self.formats)]
        for lang in self.languages:
            if lang not in SUPPORTED_LANGUAGES:
                raise ValueError(f"Unsupported language {lang!r}; choose from {SUPPORTED_LANGUAGES}")
        for fmt in self.formats:
            if fmt not in SUPPORTED_FORMATS:
                raise ValueError(f"Unsupported format {fmt!r}; choose from {SUPPORTED_FORMATS}")
        if not self.languages:
            raise ValueError("At least one language is required")
        if not self.formats:
            raise ValueError("At least one format is required")
        if self.fps not in FPS_CHOICES:
            raise ValueError(f"fps must be one of {FPS_CHOICES}")
        if self.quality not in QUALITY_PRESETS:
            raise ValueError(f"quality must be one of {tuple(QUALITY_PRESETS)}")
        # 0 is not "zero seconds": it means the source owns its own length (an
        # imported script is spoken verbatim, so there is no target to hit)
        if float(self.duration) != 0.0 and not (10.0 <= float(self.duration) <= 900.0):
            raise ValueError("duration must be 0 (use the script's own length) "
                             "or between 10 and 900 seconds")

    # -------------------------------------------------------------- computed
    @property
    def preset(self) -> Dict[str, Any]:
        return QUALITY_PRESETS[self.quality]

    def size_for(self, fmt: str) -> tuple[int, int]:
        return aspect_size(fmt, self.preset["height"])

    def supersample_for(self, fmt: str) -> int:
        return int(self.preset["supersample"])

    def to_dict(self) -> dict:
        d = asdict(self)
        d["size"] = {f: list(self.size_for(f)) for f in self.formats}
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "RenderOptions":
        known = {k: v for k, v in d.items() if k in RenderOptions.__dataclass_fields__}
        known.pop("size", None)
        return RenderOptions(**known)
