"""Project state: what was requested, what was produced, what can be reused.

A project lives in a directory (usually on Drive) and contains:

    project.json                 request + status + evidence
    story.json                   the (reviewable) script + scene plan
    storyboard.<lang>.json       per-language timing/captions/actions
    audio/<lang>.wav             full narration track
    script/<lang>_<fmt>.ass      soft subtitle file (also .srt)
    scenes/<lang>_<fmt>/*.mp4    finished scene renders (cacheable)
    out/<lang>_<fmt>.mp4         final videos
    preview/*.png                storyboard contact sheets
    logs/                        stage logs
"""
from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..util.hashing import hash_json, hash_file
from ..util.logging import get_logger

LOG = get_logger("ckd.pipeline.project")

SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 42) -> str:
    s = SLUG_RE.sub("-", text.lower()).strip("-")
    if not s:
        s = "topic"
    if any("\u0600" <= ch <= "\u06FF" for ch in text):
        # non-latin topics get a stable hash suffix so folders stay portable
        s = "urdu-" + hash_json(text)[:8]
    return s[:max_len].strip("-")


def project_key(options) -> str:
    """Stable id for a request: same request -> same project (so it resumes)."""
    return hash_json({
        "topic": options.topic.strip().lower(),
        "langs": sorted(options.languages),
        "formats": sorted(options.formats),
        "duration": round(float(options.duration), 1),
        "quality": options.quality,
        "fps": options.fps,
        "captions": options.include_captions,
        "character": options.include_character,
        "voice_en": options.voice_en,
        "voice_ur": options.voice_ur,
        "llm": options.llm,
        "notes": options.notes.strip(),
        "palette": options.palette,
        "seed": options.seed,
        "pipeline": 3,
    }, prefix="project")


@dataclass
class Project:
    root: Path
    options: Any
    state: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------ paths
    @property
    def key(self) -> str:
        return self.state.get("key") or project_key(self.options)

    @property
    def story_path(self) -> Path:
        return self.root / "story.json"

    @property
    def state_path(self) -> Path:
        return self.root / "project.json"

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    @property
    def scene_dir(self) -> Path:
        return self.root / "scenes"

    @property
    def out_dir(self) -> Path:
        return self.root / "out"

    @property
    def preview_dir(self) -> Path:
        return self.root / "preview"

    @property
    def subtitle_dir(self) -> Path:
        return self.root / "subtitles"

    def video_path(self, lang: str, fmt: str) -> Path:
        return self.out_dir / f"{lang}_{fmt}.mp4"

    def audio_path(self, lang: str) -> Path:
        return self.audio_dir / f"{lang}.wav"

    def storyboard_path(self, lang: str) -> Path:
        return self.root / f"storyboard.{lang}.json"

    def scene_path(self, lang: str, fmt: str, index: int, scene_id: str) -> Path:
        return self.scene_dir / f"{lang}_{fmt}" / f"{index:02d}_{slugify(scene_id, 18)}.mp4"

    def ensure_dirs(self) -> None:
        for d in (self.root, self.audio_dir, self.scene_dir, self.out_dir, self.preview_dir,
                  self.subtitle_dir, self.root / "logs"):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ state
    def load(self) -> "Project":
        if self.state_path.exists():
            try:
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                LOG.warning("project.json unreadable (%s); starting fresh", exc)
                self.state = {}
        return self

    def save(self) -> None:
        self.ensure_dirs()
        self.state.setdefault("key", self.key)
        self.state["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tmp = self.state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.state, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.state_path)

    def mark(self, stage: str, *, status: str = "done", **info) -> None:
        entry = self.state.setdefault("stages", {}).setdefault(stage, {})
        entry.update({"status": status, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **info})
        self.save()

    def stage_info(self, stage: str) -> Dict[str, Any]:
        return self.state.get("stages", {}).get(stage, {})

    # --------------------------------------------------------------- utilities
    def write_json(self, path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def open_project(root: str | Path, options) -> Project:
    root = Path(root)
    proj = Project(root=root, options=options).load()
    proj.state["key"] = project_key(options)
    proj.state["options"] = options.to_dict()
    proj.state["topic"] = options.topic
    proj.ensure_dirs()
    proj.save()
    return proj


def list_projects(root: str | Path) -> List[Dict[str, Any]]:
    root = Path(root)
    out = []
    if not root.exists():
        return out
    for p in sorted(root.iterdir()):
        state_file = p / "project.json"
        if not state_file.exists():
            continue
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "dir": str(p),
            "topic": state.get("topic", p.name),
            "updated_at": state.get("updated_at"),
            "videos": state.get("videos", []),
            "stages": {k: v.get("status") for k, v in state.get("stages", {}).items()},
        })
    out.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    return out
