"""Acceptance E/F/G: frames, formats, media integrity and character consistency."""
from pathlib import Path

import numpy as np
import pytest

from ckd.content.composer import compose_story
from ckd.scene.renderer import SceneRenderSpec, SceneRenderer
from ckd.scene.stage import make_stage
from ckd.scene.worlds import get_world
from ckd.text.render import TextRenderer


def _render(story, narration, fmt, lang="en", index=0, frac=0.5):
    w, h = (1280, 720) if fmt == "landscape" else (406, 720)
    stage = make_stage(w, h, fmt, story.palette, fps=24)
    spec = SceneRenderSpec(scene=story.scenes[index], stage=stage, language=lang,
                           narration=narration.scenes[index], world=get_world(story.world),
                           renderer=TextRenderer(ss=1), scene_index=index,
                           scene_count=len(story.scenes))
    return SceneRenderer(spec).render(narration.scenes[index].duration * frac)


@pytest.mark.parametrize("fmt,size", [("landscape", (1280, 720)), ("vertical", (406, 720))])
def test_frame_geometry_and_determinism(wifi_narration, story, fmt, size):
    img = _render(story, wifi_narration, fmt)
    assert img.size == size
    a = np.asarray(img.convert("RGB"))
    b = np.asarray(_render(story, wifi_narration, fmt).convert("RGB"))
    assert np.array_equal(a, b), "the same frame must render identically (no random seeds leaking)"
    assert a.std() > 12, "frame looks blank"


def test_character_is_the_same_rig_in_every_scene(wifi_narration, story):
    tiles = []
    for i in range(len(story.scenes)):
        img = _render(story, wifi_narration, "landscape", index=i, frac=0.8)
        tiles.append(np.asarray(img.convert("RGB"))[:, :360])
    # the presenter's silhouette occupies the same column in every scene
    masks = []
    for tile in tiles:
        skin = (tile[:, :, 0] > 190) & (tile[:, :, 1] > 150) & (tile[:, :, 2] < 190)
        masks.append(skin.sum(axis=0))
    profiles = np.array([m / max(1, m.sum()) for m in masks])
    assert profiles.std(axis=0).mean() < 0.02


def test_render_is_cpu_only_and_needs_no_network(monkeypatch, wifi_narration, story):
    import socket

    def explode(*_a, **_kw):
        raise AssertionError("rendering must not open sockets")

    monkeypatch.setattr(socket.socket, "connect", explode)
    monkeypatch.setattr(socket, "create_connection", explode)
    _render(story, wifi_narration, "vertical")


def test_ffmpeg_helpers_probe_and_verify(tmp_path: Path):
    from ckd.render.ffmpeg import encode_frames, probe, verify_video

    from PIL import Image

    frames = [Image.new("RGB", (128, 72), (30 + i * 8, 10, 40)) for i in range(6)]
    out = tmp_path / "clip.mp4"
    encode_frames(frames, out, width=128, height=72, fps=24, crf=28)
    info = probe(out)
    assert info.width == 128 and info.height == 72
    assert 0.2 <= info.duration <= 0.45
    ok, problems = verify_video(out, require_audio=False, expect_w=128, expect_h=72,
                                expect_fps=24, expect_duration=0.25)
    assert ok, problems
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"not a video")
    ok_bad, problems_bad = verify_video(bad, require_audio=False, expect_w=128, expect_h=72,
                                        expect_fps=24, expect_duration=0.25)
    assert not ok_bad and problems_bad, "a corrupt file must be reported"


def test_worlds_are_structurally_different(tmp_path: Path):
    """Solar, wifi and bridge must not be the same drawing with new labels."""
    from ckd.scene.worlds import get_world

    shapes = {}
    for topic in ("solar energy", "how wifi works", "bridge engineering"):
        s = compose_story(topic, languages=["en"], target_seconds=45)
        world = get_world(s.world)
        shapes[s.world] = set(world.element_types)
    assert shapes["solar"] - shapes["wifi"]
    assert shapes["wifi"] - shapes["bridge"]
    assert shapes["bridge"] - shapes["solar"]
