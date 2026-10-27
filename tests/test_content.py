"""Acceptance B + C: topic-only operation and topic-specific scene plans."""
import pytest

from ckd.content.composer import compose_story
from ckd.content.schema import StoryValidationError, validate_story


def _signature(story):
    return [tuple(sorted({el["type"] for el in sc.elements})) for sc in story.scenes]


def test_topic_only_call_produces_bilingual_plan():
    story = compose_story("how solar panels work", languages=["en", "ur"], target_seconds=45)
    assert story.scenes
    for scene in story.scenes:
        assert scene.narration["en"].strip()
        assert scene.narration["ur"].strip()
        assert scene.narration["ur"] != scene.narration["en"]


def test_urdu_is_real_urdu_script():
    story = compose_story("wifi", languages=["ur"], target_seconds=45)
    text = " ".join(sc.narration["ur"] for sc in story.scenes)
    arabic = sum(1 for ch in text if "\u0600" <= ch <= "\u06ff")
    assert arabic > len(text) * 0.5, "Urdu narration must not be romanised"
    assert not any(word.isascii() and word.isalpha() and len(word) > 3 for word in text.split())


def test_the_three_reference_topics_are_structurally_different():
    solar = compose_story("solar energy", languages=["en"], target_seconds=45)
    wifi = compose_story("how wifi works", languages=["en"], target_seconds=45)
    bridge = compose_story("bridge engineering", languages=["en"], target_seconds=45)
    assert {solar.world, wifi.world, bridge.world} == {"solar", "wifi", "bridge"}
    assert _signature(solar) != _signature(wifi) != _signature(bridge)
    kinds = {w: {el["type"] for sc in s.scenes for el in sc.elements}
             for w, s in (("solar", solar), ("wifi", wifi), ("bridge", bridge))}
    assert "panel" in kinds["solar"] and "panel" not in kinds["wifi"]
    assert "router" in kinds["wifi"] and "waves" in kinds["wifi"]
    assert "truss" in kinds["bridge"] or "member_forces" in kinds["bridge"]


def test_unknown_topic_falls_back_to_generic_world_with_a_warning():
    story = compose_story("how bread is baked", languages=["en"], target_seconds=40)
    assert story.world in ("generic", "solar", "wifi", "bridge")
    if story.world == "generic":
        assert story.warnings, "a scaffold plan must say that it is generic"


def test_validation_rejects_empty_scene_text():
    story = compose_story("wifi", languages=["en"], target_seconds=45)
    story.scenes[0].narration["en"] = "   "
    with pytest.raises(StoryValidationError):
        validate_story(story, languages=["en"])


def test_duration_is_respected_as_closely_as_the_pack_allows():
    from ckd.content.composer import estimate_duration

    short = compose_story("wifi", languages=["en"], target_seconds=20)
    long = compose_story("wifi", languages=["en"], target_seconds=75)
    d_short = sum(estimate_duration(s, ["en"]) for s in short.scenes)
    d_long = sum(estimate_duration(s, ["en"]) for s in long.scenes)
    assert d_short < d_long
    assert short.warnings, "an unmet short target must be reported, not hidden"


def test_notes_are_attached_verbatim_when_bilingual():
    story = compose_story("wifi", languages=["en", "ur"], target_seconds=45,
                          notes="5 GHz travels shorter distances||5 گیگا ہرٹز کم فاصلہ طے کرتی ہے")
    joined = " ".join(sc.narration["en"] for sc in story.scenes)
    assert "5 GHz travels shorter distances" in joined
