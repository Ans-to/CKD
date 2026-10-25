"""Acceptance D/E: Urdu shaping, wrapping, and both formats being re-composed."""
from ckd.content.composer import compose_story
from ckd.scene.stage import make_stage
from ckd.text.render import TextRenderer, TextStyle

URDU = "سولر پینل سورج کی روشنی کو بجلی میں کیسے بدلتے ہیں اور یہ بجلی گھر تک کیسے پہنچتی ہے"


def test_urdu_wraps_instead_of_overflowing():
    r = TextRenderer(ss=1)
    style = TextStyle(size=46, language="ur", role="display", align="right", line_height=1.8)
    lay = r.layout(URDU, style, 340)
    assert len(lay.lines) >= 2, "an Urdu paragraph must wrap at the requested width"
    assert lay.width <= 340 + 1.0, f"line overflowed: {lay.width:.1f} > 340"


def test_bidi_island_keeps_its_order():
    r = TextRenderer(ss=1)
    style = TextStyle(size=28, language="ur", role="body", align="right")
    text = "پینل (solar panel) چھت پر لگایا جاتا ہے"
    lay = r.layout(text, style, 420)
    words = [w.word.text for w in lay.words]
    assert "solar" in " ".join(words) and "panel" in " ".join(words)
    joined = " ".join(words)
    assert joined.index("solar") < joined.index("panel"), "Latin island must keep LTR order"


def test_alignment_origin_is_consistent_with_reported_width():
    """Regression: text was placed with `x + word.x` while alignment used the box width."""
    r = TextRenderer(ss=1)
    for align in ("left", "center", "right"):
        style = TextStyle(size=30, language="en", role="body", align=align)
        lay = r.layout("a short caption that is much narrower than its box", style, 866)
        assert lay.width < 866 - 50
        first = min(w.x for w in lay.words)
        last = max(w.x for w in lay.words)
        assert 0.0 <= first <= 4.0, f"{align}: block should start at its own origin, got {first:.1f}"
        assert last < lay.width, f"{align}: words must stay inside the reported width"


def test_vertical_and_landscape_are_recomposed_not_cropped():
    land = make_stage(1280, 720, "landscape", {}, fps=24)
    vert = make_stage(406, 720, "vertical", {}, fps=24)
    assert land.caption_area != vert.caption_area
    # the vertical headline spans the frame width; the landscape one leaves room for props
    assert vert.headline_area[2] / vert.width > 0.85
    assert land.headline_area[2] / land.width < 0.60
    assert vert.character_height / vert.height < land.character_height / land.height
    (vx, _), _ = vert.character_anchor("char_left")
    (lx, _), _ = land.character_anchor("char_left")
    assert abs(vx / vert.width - lx / land.width) > 0.05, "character must be re-placed per format"
    assert land.world_area[1] > land.headline_area[1] + land.headline_area[3] * 0.55


def test_urdu_digits_in_kicker():
    from ckd.scene.renderer import URDU_DIGITS

    assert "3/1".translate(URDU_DIGITS) == "۳/۱"


def test_every_pack_scene_renders_headline_and_caption_inside_safe_area(wifi_narration):
    import numpy as np

    from ckd.scene.renderer import SceneRenderSpec, SceneRenderer
    from ckd.scene.worlds import get_world

    story = compose_story("how wifi works", languages=["en"], target_seconds=45)
    stage = make_stage(406, 720, "vertical", story.palette, fps=24)
    renderer = TextRenderer(ss=1)
    for i, scene in enumerate(story.scenes[:2]):
        spec = SceneRenderSpec(scene=scene, stage=stage, language="en",
                               narration=wifi_narration.scenes[i], world=get_world(story.world),
                               renderer=renderer, scene_index=i, scene_count=len(story.scenes))
        img = np.asarray(SceneRenderer(spec).render(wifi_narration.scenes[i].duration * 0.5).convert("RGB"))
        # nothing pure-white may touch the outermost 6 px (that means clipped text)
        edges = [img[:6], img[-6:], img[:, :6], img[:, -6:]]
        for band in edges:
            assert not (band.min(axis=2) > 245).any(), "text is clipped by the frame edge"
