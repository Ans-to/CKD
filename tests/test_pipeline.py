"""Acceptance F/G/H: media integrity, caching and interrupt/resume.

This is the only slow test module: it renders a deliberately tiny story at draft quality.
"""
import json
from pathlib import Path

import pytest

from ckd.content.options import RenderOptions
from ckd.content.schema import Scene, Story
from ckd.pipeline.run import Pipeline

SHORT = {
    "en": [
        "Sunlight lands on the roof.",
        "Inside, silicon turns light into current.",
        "The inverter makes it usable at home.",
    ],
    "ur": [
        "دھوپ چھت پر پڑتی ہے۔",
        "اندر سلکان روشنی کو کرنٹ میں بدلتا ہے۔",
        "انورٹر اسے گھر کے لیے قابلِ استعمال بناتا ہے۔",
    ],
}


def _tiny_story(language: str = "en") -> Story:
    scenes = []
    for i, key in enumerate(("hook", "cells", "recap")):
        scenes.append(Scene.from_dict({
            "id": key,
            "purpose": "hook" if i == 0 else ("recap" if i == 2 else "explain"),
            "headline": {"en": f"Short scene {i + 1}", "ur": f"مختصر منظر {i + 1}"},
            "narration": {"en": SHORT["en"][i], "ur": SHORT["ur"][i]},
            "elements": [{"type": "sky", "slot": "back"},
                         {"type": "sun", "slot": "sun"}] if i == 1 else
                        [{"type": "sky", "slot": "back"}, {"type": "house", "slot": "house"}],
            "actions": [],
            "keywords": {"en": [], "ur": []},
        }))
    return Story(topic="tiny solar", world="solar", palette="warm",
                 title={"en": "Tiny solar", "ur": "چھوٹا سولر"},
                 scenes=scenes, languages=[language], generator="test")


@pytest.fixture()
def pipe(tmp_path: Path) -> Pipeline:
    opts = RenderOptions(topic="tiny solar", languages=["en"], formats=["landscape"],
                         duration=20, quality="draft", fps=24)
    return Pipeline(options=opts, root=tmp_path, project_dir=tmp_path / "projects" / "tiny-solar",
                    supersample_override=1)


def test_render_cache_and_resume(pipe: Pipeline):
    story = _tiny_story()
    tracks = pipe.narrate(story)
    first = pipe.render_videos(story, tracks)
    assert first, "expected at least one video"
    meta = next(iter(first.values()))
    assert meta["verified"] is True, meta.get("problems")
    scene_files = sorted(pipe.project.scene_dir.rglob("*.mp4"))
    assert len(scene_files) == len(story.scenes)
    stamps = {p.name: p.stat().st_mtime_ns for p in scene_files}

    # 1. unchanged project: everything is reused, nothing is rewritten
    pipe2 = Pipeline(options=pipe.options, root=pipe.root, project_dir=pipe.project_dir,
                     supersample_override=1)
    tracks2 = pipe2.narrate(story)
    second = pipe2.render_videos(story, tracks2)
    for path in scene_files:
        assert path.stat().st_mtime_ns == stamps[path.name], f"{path.name} was needlessly re-rendered"
    assert next(iter(second.values()))["verified"] is True

    # 2. a corrupt scene must be detected and re-rendered, not reused
    victim = scene_files[1]
    victim.write_bytes(victim.read_bytes()[:2048])
    pipe3 = Pipeline(options=pipe.options, root=pipe.root, project_dir=pipe.project_dir,
                     supersample_override=1)
    tracks3 = pipe3.narrate(story)
    third = pipe3.render_videos(story, tracks3)
    assert victim.stat().st_size > 2048
    assert next(iter(third.values()))["verified"] is True

    # 3. editing one scene re-renders only that scene
    before = {p.name: p.stat().st_mtime_ns for p in scene_files}
    story.scenes[2].narration["en"] = "The inverter turns it into household power."
    pipe4 = Pipeline(options=pipe.options, root=pipe.root, project_dir=pipe.project_dir,
                     supersample_override=1)
    tracks4 = pipe4.narrate(story)
    pipe4.render_videos(story, tracks4)
    after = {p.name: p.stat().st_mtime_ns for p in scene_files}
    changed = [name for name in before if before[name] != after[name]]
    assert len(changed) == 1, f"expected exactly one re-rendered scene, got {changed}"


def test_report_lists_engine_timing_and_problems(pipe: Pipeline):
    story = _tiny_story()
    tracks = pipe.narrate(story)
    result = pipe.render_videos(story, tracks)
    pipe._write_report(story, tracks, result)
    report = json.loads((pipe.project.root / "report.json").read_text(encoding="utf-8"))
    assert report["topic"] == "tiny solar"
    assert report["narration"]["en"]["engine"] in ("espeak", "piper", "kokoro")
    assert report["narration"]["en"]["timing_kind"] in (
        "espeak-events", "piper-events", "piper-alignment", "measured",
        "proportional", "estimated")
    for meta in report["videos"].values():
        assert "verified" in meta and "path" in meta


def test_compile_only_does_not_render(pipe: Pipeline, monkeypatch):
    monkeypatch.setattr(pipe, "render_videos", lambda *a, **k: pytest.fail("must not render"))
    result = pipe.run(compile_only=True)
    assert result["tracks"]["en"]["duration"] > 0
    assert (pipe.project.story_path).exists()
