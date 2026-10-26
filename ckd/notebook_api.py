"""Notebook-facing API: everything the Colab notebook calls, without a CLI.

Design goals
------------
* every stage is a separate function, so a reviewer can stop after the script
  and edit `story.json` before a single frame is rendered;
* no hidden state: the project directory *is* the state (see `pipeline/project.py`);
* failures raise `NotebookError` with a sentence a person can act on, and nothing
  is silently substituted (no placeholder video, no guessed language).
"""
from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .content.composer import available_topics
from .content.options import QUALITY_PRESETS, RenderOptions
from .content.schema import Story
from .pipeline.run import Pipeline
from .util.logging import setup_logging


class NotebookError(RuntimeError):
    """Something the person at the keyboard can act on."""


# --------------------------------------------------------------------- helpers
def _slug(topic: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in topic.strip()]
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:48] or "video"


def topics() -> List[Dict[str, str]]:
    """Curated topics; each one has a hand-written bilingual knowledge pack."""
    return available_topics()


def check_environment(root: str | Path = ".", *, min_free_gb: float = 3.0) -> Dict[str, Any]:
    """Report Python/ffmpeg/font/voice/disk state. Soft issues land in `problems`."""
    from .render.ffmpeg import ffmpeg_version
    from .text.fonts import FontBook
    from .util.system import human_bytes, system_info
    from .voice.registry import describe_voices

    info = system_info(root)
    fonts = FontBook().available()
    voices = describe_voices()
    report: Dict[str, Any] = {
        "cpu_count": info.cpu_count,
        "ram_gb": round(info.mem_total / 1e9, 2),
        "ram_available_gb": round(info.mem_available / 1e9, 2),
        "free_disk_gb": round(info.disk_free / 1e9, 2),
        "gpu": info.gpu,
        "ffmpeg": ffmpeg_version(),
        "fonts_ok": {k: v for k, v in fonts.items()},
        "voices_cached": [v["id"] for v in voices if v["cached"]],
        "problems": [],
    }
    if report["free_disk_gb"] < min_free_gb:
        report["problems"].append(
            f"Only {report['free_disk_gb']:.1f} GB free ({human_bytes(info.disk_free)}); "
            "one 60 s pair (16:9 + 9:16) needs roughly 1.5 GB. Free space or use quality='draft'."
        )
    missing = [role for role, ok in fonts.items() if not ok]
    if missing:
        report["problems"].append(
            f"Fonts missing for roles {missing}. Re-clone the repo or run the font download cell."
        )
    if not report["voices_cached"]:
        report["problems"].append(
            "No Piper voice is cached yet — the first narration will download one "
            "(allowed in Colab, needs internet). If that fails the offline espeak voice is used."
        )
    return report


# --------------------------------------------------------------------- project
@dataclass
class Project:
    """A handle on one project directory (script, audio, scenes, videos)."""

    pipeline: Pipeline
    options: RenderOptions

    @property
    def root(self) -> Path:
        return Path(self.pipeline.project.root)

    def story(self) -> Story:
        return self.pipeline.story_for_review()

    def story_text(self) -> str:
        """Pretty JSON of the current plan — edit it, then pass it to `save_story`."""
        return json.dumps(self.story().to_dict(), indent=1, ensure_ascii=False)

    def save_story(self, text: str) -> Story:
        """Replace `story.json` with edited JSON and validate it before rendering."""
        data = json.loads(text)
        story = Story.from_dict(data)
        (self.root / "story.json").write_text(
            json.dumps(story.to_dict(), indent=1, ensure_ascii=False), encoding="utf-8"
        )
        self.pipeline.project.state["script_hash"] = None  # force a plan re-check
        self.pipeline.project.save()
        return story


def new_project(
    topic: str,
    *,
    languages: Iterable[str] = ("en",),
    formats: Iterable[str] = ("landscape",),
    duration: float = 45.0,
    quality: str = "standard",
    fps: int = 24,
    captions: bool = True,
    character: bool = True,
    voice_en: str = "auto",
    voice_ur: str = "auto",
    notes: str = "",
    seed: int = 7,
    projects_dir: str | Path = "projects",
    root: str | Path = ".",
    llm: str = "none",
) -> Project:
    """Create (or reopen) a project and compose its script. No frames are rendered."""
    if quality not in QUALITY_PRESETS:
        raise NotebookError(f"quality must be one of {sorted(QUALITY_PRESETS)}")
    if not str(topic).strip():
        raise NotebookError("topic is empty — pass something like 'how wifi works'")
    opts = RenderOptions(
        topic=str(topic),
        languages=list(languages),
        formats=list(formats),
        duration=float(duration),
        quality=quality,
        fps=int(fps),
        include_captions=bool(captions),
        include_character=bool(character),
        voice_en=voice_en,
        voice_ur=voice_ur,
        notes=notes,
        seed=int(seed),
        llm=llm,
    )
    setup_logging()
    pipe = Pipeline(options=opts, root=root, project_dir=Path(projects_dir) / _slug(topic))
    pipe.build_story()
    return Project(pipeline=pipe, options=opts)


def new_project_from_script(
    script: str | Path,
    *,
    languages: Iterable[str] = ("en",),
    formats: Iterable[str] = ("landscape",),
    quality: str = "standard",
    fps: int = 24,
    captions: bool = True,
    character: bool = False,
    voice_en: str = "auto",
    voice_ur: str = "auto",
    projects_dir: str | Path = "projects",
    root: str | Path = ".",
    name: str = "",
) -> Project:
    """Render a script you already wrote, instead of inventing one from a topic.

    `script` is either a path to a .md/.txt file or the script text itself, in the
    documentary format (SCENE n — TITLE / **[VOICEOVER]** / **[VISUAL DIRECTION]** /
    **[ON-SCREEN TEXT]** / optional CALL TO ACTION).  The words are spoken verbatim.
    """
    from .content.script_import import parse_script

    text = script if isinstance(script, str) and "\n" in script else None
    if text is None:
        path = Path(script)
        if not path.exists():
            raise NotebookError(f"script file not found: {path}")
        text = path.read_text(encoding="utf-8")
        name = name or path.stem
        script_path = str(path)
    else:
        script_path = ""
    if quality not in QUALITY_PRESETS:
        raise NotebookError(f"quality must be one of {sorted(QUALITY_PRESETS)}")
    parsed = parse_script(text)
    if not parsed.scenes:
        raise NotebookError("no 'SCENE n — TITLE' blocks found in the script")
    name = name or parsed.title or "documentary"
    opts = RenderOptions(
        topic=name,
        languages=list(languages),
        formats=list(formats),
        duration=float(parsed.target_seconds or 60.0),
        quality=quality,
        fps=int(fps),
        include_captions=bool(captions),
        include_character=bool(character),
        voice_en=voice_en,
        voice_ur=voice_ur,
        script_path=script_path,
        script_text=script_path == "",
    )
    setup_logging()
    pipe = Pipeline(options=opts, root=root, project_dir=Path(projects_dir) / _slug(name))
    if opts.script_text:
        # the cell *is* the script: write it next to the project so the run is
        # reproducible and the words can be edited and re-rendered
        out = pipe.project.root / "script.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        opts.script_path = str(out)
    pipe.build_story()
    return Project(pipeline=pipe, options=opts)


def open_project(project_dir: str | Path, *, root: str | Path = ".") -> Project:
    """Reopen an existing project (after an interruption, or in a new session)."""
    path = Path(project_dir)
    state_file = path / "project.json"
    if not state_file.exists():
        raise NotebookError(f"{path} is not a project directory (no project.json).")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    opts = RenderOptions.from_dict(state.get("options", {}))
    pipe = Pipeline(options=opts, root=root, project_dir=path)
    return Project(pipeline=pipe, options=opts)


def preview(project: Project, *, samples: int = 2, lang: Optional[str] = None,
            fmt: Optional[str] = None) -> List[Path]:
    """Storyboard stills for every language × format, for visual review."""
    story = project.pipeline.build_story()
    tracks = project.pipeline.narrate(story)
    out: List[Path] = []
    for language in project.options.languages:
        if lang and language != lang:
            continue
        for f in project.options.formats:
            if fmt and f != fmt:
                continue
            out.append(project.pipeline.preview_sheet(story, tracks, language, f, samples=samples))
    return out


def render(project: Project, *, force: Iterable[str] = ()) -> Dict[str, Any]:
    """Render everything; narration is cached and unchanged scenes are skipped."""
    project.pipeline.force = tuple(force)
    return project.pipeline.run()


def render_quick(project: Project) -> Dict[str, Any]:
    """Re-render with the cheapest preset — a fast end-to-end smoke test."""
    saved = project.options.quality
    project.options.quality = "draft"
    try:
        return render(project, force=("scenes", "video"))
    finally:
        project.options.quality = saved


def result_table(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Flatten `Pipeline.run()` output into rows the notebook can print."""
    rows = []
    for key, meta in (result.get("videos") or {}).items():
        rows.append({
            "video": key,
            "path": str(meta.get("path")),
            "seconds": round(float(meta.get("duration", 0)), 2),
            "size": f"{meta.get('width')}x{meta.get('height')}",
            "fps": meta.get("fps"),
            "verified": bool(meta.get("verified")),
            "problems": "; ".join(meta.get("problems") or []) or "-",
        })
    return rows


def zip_project(project: Project, *, out: str | Path | None = None) -> Path:
    """Bundle sources + project outputs (no caches, no .git) for a browser download."""
    root = Path(project.pipeline.root).resolve()
    out = Path(out) if out else root / f"{_slug(project.options.topic)}-bundle.zip"
    exclude = {"__pycache__", ".git", "_cache", "cache", "models", ".ipynb_checkpoints"}
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "bundle"
        staging.mkdir()
        for item in root.iterdir():
            if item.name in exclude or item.name.startswith("."):
                continue
            _copy(item, staging / item.name, exclude)
        shutil.make_archive(str(out.with_suffix("")), "zip", root_dir=staging)
    return out


def _copy(src: Path, dst: Path, exclude: set[str]) -> None:
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for child in src.iterdir():
            if child.name in exclude:
                continue
            _copy(child, dst / child.name, exclude)
    else:
        shutil.copy2(src, dst)
