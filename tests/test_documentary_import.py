"""The documentary world: imported scripts, vertical re-composition, honesty."""
from __future__ import annotations

import pytest


def test_aspect_size_keeps_the_short_side():
    """A 9:16 render must not be a third of the resolution of its 16:9 twin."""
    from ckd.content.schema import aspect_size

    assert aspect_size("landscape", 720) == (1280, 720)
    assert aspect_size("vertical", 720) == (720, 1280)
    assert aspect_size("vertical", 1080) == (1080, 1920)
    assert aspect_size("square", 720) == (720, 720)
    for fmt in ("landscape", "vertical", "square"):
        w, h = aspect_size(fmt, 480)
        assert w % 2 == 0 and h % 2 == 0


def test_vertical_statements_dock_between_hero_and_supers():
    """In 9:16 the wide slot sits on the hero, so a statement would be covered."""
    from ckd.content.schema import Story, Scene
    from ckd.scene.stage import make_stage
    from ckd.scene.worlds import get_world

    world = get_world("business")
    scene = Scene.from_dict({
        "id": "s", "purpose": "explain", "narration": {"en": "x"},
        "headline": {"en": ""}, "elements": [], "actions": [],
    })
    for fmt, h, w in (("vertical", 1280, 720), ("landscape", 720, 1280)):
        stage = make_stage(w, h, fmt, "documentary", 24)
        slots = world.slots(stage)
        if fmt == "vertical":
            x, y, sw, sh = slots["statement_low"]
            hero_bottom = slots["phone"][1] + slots["phone"][3]
            assert y > hero_bottom - 1, (y, hero_bottom)
            assert y + sh < stage.caption_area[1]
        else:
            assert "statement_low" not in slots


def test_lower_third_stays_above_the_caption_band():
    from ckd.scene.stage import make_stage
    from ckd.scene.worlds import get_world

    world = get_world("business")
    for fmt, w, h in (("landscape", 1280, 720), ("vertical", 720, 1280)):
        stage = make_stage(w, h, fmt, "documentary", 24)
        x, y, sw, sh = world.slots(stage)["upper_supers"]
        assert y + sh <= stage.caption_area[1], fmt
        assert y >= stage.world_area[1], fmt


def test_shot_fades_last_less_than_a_second():
    """Consecutive shots must not ghost over each other for half a scene.

    The first version faded over a *fraction* of the action, so three 10-second
    phone shots were all half-visible at once and the frame looked double-exposed.
    """
    from ckd.scene.worlds.base import ActionState, RenderContext
    from ckd.scene.worlds.business import _shot
    from ckd.scene.stage import make_stage

    stage = make_stage(1280, 720, "landscape", "documentary", 24)
    actions = [ActionState("a", 0.0, 5.0), ActionState("b", 5.0, 10.0)]
    a = {"type": "phone", "params": {"in": "a", "out": "b"}}
    b = {"type": "phone", "params": {"in": "b"}}

    def at(t: float) -> tuple[float, float]:
        ctx = RenderContext(stage=stage, language="en", t=t, duration=10.0, actions=actions)
        return _shot(ctx, a), _shot(ctx, b)

    assert at(0.0)[0] == 0.0 and at(1.0)[0] > 0.95
    assert at(4.5) == (1.0, 0.0), at(4.5)
    # 0.5 s after the cut the old shot is gone, the new one is fully in
    assert at(5.5) == (0.0, 1.0), at(5.5)
    # an element with no timing at all is drawn, not silently dropped
    ctx = RenderContext(stage=stage, language="en", t=1.0, duration=10.0, actions=[])
    assert _shot(ctx, {"type": "phone", "params": {}}) == 1.0


def test_ecosystem_labels_stay_inside_the_frame():
    """A node on the left of the hub used to print its label through the hub."""
    from ckd.content.schema import Scene
    from ckd.scene.stage import make_stage
    from ckd.scene.worlds import get_world

    world = get_world("business")
    for fmt, w, h in (("landscape", 1280, 720), ("vertical", 720, 1280)):
        stage = make_stage(w, h, fmt, "documentary", 24)
        slot = "tall" if fmt == "vertical" else "wide"
        x, y, sw, sh = world.slot(stage, slot)
        assert x >= 0 and x + sw <= w + 0.5, (fmt, x, sw, w)
        assert y >= stage.headline_area[1], (fmt, y)
        assert y + sh <= stage.caption_area[1], (fmt, y + sh)
