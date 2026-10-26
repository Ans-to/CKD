"""Script / plan data model + validation + automatic repair.

Model output (or composer output) is *never* trusted blindly: it is parsed,
validated against a strict schema, repaired where a deterministic fix exists,
and only then rendered.  Every scene carries both language variants so the two
videos stay semantically aligned.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence

SUPPORTED_LANGUAGES = ("en", "ur")
SUPPORTED_FORMATS = ("landscape", "vertical")
PURPOSES = ("hook", "explain", "example", "recap", "cta")


def aspect_size(fmt: str, height: int = 720) -> tuple[int, int]:
    """Render size for a format: `height` is the *short* side, rounded to even.

    So `standard` (720) means 1280x720 landscape, 720x1280 portrait - the short
    side is the expensive dimension, and a portrait video should not silently be
    a third of the resolution of its landscape twin.
    """
    height = int(height) // 2 * 2
    if fmt == "vertical":
        return height, (height * 16 // 9) // 2 * 2
    if fmt == "square":
        return height, height
    return (height * 16 // 9) // 2 * 2, height


@dataclass
class Beat:
    """One animated step inside a scene, timed against the narration."""

    id: str
    at: float = 0.0  # seconds from scene start (filled by the timing stage)
    hold: float = 1.0
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "at": round(self.at, 3), "hold": round(self.hold, 3), "params": self.params}


@dataclass
class Scene:
    id: str
    purpose: str
    narration: Dict[str, str] = field(default_factory=dict)  # {"en": ..., "ur": ...}
    headline: Dict[str, str] = field(default_factory=dict)  # short on-screen title
    keywords: Dict[str, List[str]] = field(default_factory=dict)  # words to highlight
    motif: str = "flow"  # flow | cycle | compare | layers | structure | scale
    elements: List[Dict[str, Any]] = field(default_factory=list)
    beats: List[Beat] = field(default_factory=list)
    character: Dict[str, Any] = field(default_factory=dict)
    # seconds a headline stays on screen before fading (0 = keep for the scene).
    # Documentary scripts want a title card that gets out of the way.
    headline_hold: float = 0.0
    camera: str = "push_in"
    actions: List[Dict[str, Any]] = field(default_factory=list)
    notes: str = ""

    def text_for(self, lang: str) -> str:
        return (self.narration.get(lang) or self.narration.get("en") or "").strip()

    def headline_for(self, lang: str) -> str:
        return (self.headline.get(lang) or self.headline.get("en") or "").strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["beats"] = [b.to_dict() for b in self.beats]
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Scene":
        beats = [
            Beat(id=str(b.get("id", f"b{i}")), at=float(b.get("at", 0.0)), hold=float(b.get("hold", 1.0)),
                 params=dict(b.get("params", {})))
            for i, b in enumerate(d.get("beats", []) or [])
        ]
        return Scene(
            id=str(d.get("id", "")),
            purpose=str(d.get("purpose", "explain")),
            narration={k: str(v) for k, v in (d.get("narration") or {}).items()},
            headline={k: str(v) for k, v in (d.get("headline") or {}).items()},
            keywords={k: list(v) for k, v in (d.get("keywords") or {}).items()},
            motif=str(d.get("motif", "flow")),
            elements=list(d.get("elements") or []),
            beats=beats,
            character=dict(d.get("character") or {}),
            headline_hold=float(d.get("headline_hold", 0.0) or 0.0),
            camera=str(d.get("camera", "push_in")),
            actions=list(d.get("actions") or []),
            notes=str(d.get("notes", "")),
        )


@dataclass
class Story:
    topic: str
    world: str = "generic"  # visual world id (solar / wifi / bridge / generic)
    palette: str = "warm"
    title: Dict[str, str] = field(default_factory=dict)
    scenes: List[Scene] = field(default_factory=list)
    languages: List[str] = field(default_factory=lambda: ["en"])
    generator: str = "composer"
    warnings: List[str] = field(default_factory=list)
    source_pack: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "world": self.world,
            "palette": self.palette,
            "title": self.title,
            "scenes": [s.to_dict() for s in self.scenes],
            "languages": self.languages,
            "generator": self.generator,
            "warnings": self.warnings,
            "source_pack": self.source_pack,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Story":
        return Story(
            topic=str(d.get("topic", "")),
            world=str(d.get("world", "generic")),
            palette=str(d.get("palette", "warm")),
            title={k: str(v) for k, v in (d.get("title") or {}).items()},
            scenes=[Scene.from_dict(s) for s in d.get("scenes", [])],
            languages=list(d.get("languages") or ["en"]),
            generator=str(d.get("generator", "unknown")),
            warnings=list(d.get("warnings") or []),
            source_pack=d.get("source_pack"),
        )


class StoryValidationError(ValueError):
    def __init__(self, problems: Sequence[str]):
        self.problems = list(problems)
        super().__init__("Invalid story:\n  - " + "\n  - ".join(self.problems))


def extract_json(text: str) -> Dict[str, Any]:
    """Pull the first JSON object out of a model response (handles code fences)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start < 0:
        raise StoryValidationError(["model output contained no JSON object"])
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = text[start: i + 1]
                try:
                    return json.loads(raw)
                except json.JSONDecodeError as exc:
                    return json.loads(_repair_json(raw, exc))
    raise StoryValidationError(["unbalanced JSON braces in model output"])


def _repair_json(raw: str, exc: json.JSONDecodeError) -> str:
    """Conservative fixes for the JSON mistakes models actually make."""
    s = raw
    # trailing commas
    s = re.sub(r",\s*([}\]])", r"\1", s)
    # smart quotes used as delimiters
    s = s.replace("“", '"').replace("”", '"')
    # single quotes around keys/values: only when the doc has no double quotes
    if '"' not in s:
        s = s.replace("'", '"')
    return s


def validate_story(story: Story, *, languages: Sequence[str] = SUPPORTED_LANGUAGES,
                   min_scenes: int = 3, max_scenes: int = 14) -> None:
    problems: List[str] = []
    if not story.topic.strip():
        problems.append("topic is empty")
    if not story.scenes:
        problems.append("story has no scenes")
    if len(story.scenes) > max_scenes:
        problems.append(f"too many scenes ({len(story.scenes)} > {max_scenes})")
    if len(story.scenes) < min_scenes:
        problems.append(f"too few scenes ({len(story.scenes)} < {min_scenes})")
    seen = set()
    for i, sc in enumerate(story.scenes):
        label = sc.id or f"scene[{i}]"
        if not sc.id:
            problems.append(f"scene[{i}] has no id")
        elif sc.id in seen:
            problems.append(f"duplicate scene id {sc.id!r}")
        seen.add(sc.id)
        for lang in languages:
            body = sc.text_for(lang)
            if not body:
                problems.append(f"{label}: missing narration for {lang!r}")
                continue
            if len(body) < 12:
                problems.append(f"{label}: narration for {lang!r} too short")
            if lang == "ur":
                if not re.search(r"[\u0600-\u06FF]", body):
                    problems.append(f"{label}: 'ur' narration contains no Arabic-script characters")
                if re.search(r"[A-Za-z]{4,}", body) and not re.search(r"[A-Za-z]{4,}.*[A-Za-z]{4,}", body):
                    problems.append(f"{label}: 'ur' narration looks like Roman Urdu (Latin words)")
            else:
                ur_chars = len(re.findall(r"[\u0600-\u06FF]", body))
                if ur_chars > 0.4 * len(body):
                    problems.append(f"{label}: 'en' narration is mostly non-Latin text")
            if re.search(r"https?://", body):
                problems.append(f"{label}: narration contains a URL")
        if sc.purpose not in PURPOSES:
            problems.append(f"{label}: unknown purpose {sc.purpose!r}")
        if sc.motif not in ("flow", "cycle", "compare", "layers", "structure", "scale"):
            problems.append(f"{label}: unknown motif {sc.motif!r}")
    if problems:
        raise StoryValidationError(problems)


def needs_repair(story: Story, languages: Sequence[str]) -> List[str]:
    """Problems that can be fixed automatically (missing ids/fields, language gaps)."""
    fixes: List[str] = []
    for i, sc in enumerate(story.scenes):
        if not sc.id:
            sc.id = f"scene_{i + 1}"
            fixes.append(f"assigned id {sc.id}")
        if sc.purpose not in PURPOSES:
            sc.purpose = "explain"
            fixes.append(f"{sc.id}: purpose defaulted to explain")
        if sc.motif not in ("flow", "cycle", "compare", "layers", "structure", "scale"):
            sc.motif = "flow"
            fixes.append(f"{sc.id}: motif defaulted to flow")
        for lang in languages:
            if not sc.text_for(lang) and sc.text_for("en"):
                fixes.append(f"{sc.id}: no {lang} narration (cannot auto-translate)")
    return fixes
