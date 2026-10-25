"""Script + scene-plan generation.

Three sources, in order of preference:
  1. **curated knowledge pack** (deterministic, reviewed, bilingual) - default.
  2. **local LLM** (optional; llama.cpp GGUF inside the runtime) - validated JSON.
  3. **generic scaffold** (always available, honest about being generic).

The output is always a validated `Story`: every scene has narration in each
requested language, a motif, elements for the visual world and an action list
that the timing stage maps onto narration clauses.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from .knowledge import find_pack, list_packs
from .schema import Scene, Story, StoryValidationError, validate_story

# speaking-rate estimates (words / second) used only for planning
WPS = {"en": 2.65, "ur": 2.15}
SCENE_OVERHEAD = 1.1  # lead-in + tail + clause gaps


def _words(text: str) -> int:
    return len([w for w in text.split() if w])


def estimate_duration(scene: Scene, langs: Sequence[str]) -> float:
    per_lang = [max(1.0, _words(scene.text_for(l)) / WPS.get(l, 2.4)) for l in langs]
    return max(per_lang) + SCENE_OVERHEAD


def _select_scenes(pack: Dict, target: float, langs: Sequence[str]) -> List[Dict]:
    """Pick hook + middle scenes + recap that fit the target duration."""
    scenes = [Scene.from_dict(s) for s in pack["scenes"]]
    if not scenes:
        return []
    hook = scenes[0]
    recap = scenes[-1] if len(scenes) > 1 else None
    middle = scenes[1:-1] if recap else scenes[1:]
    chosen = [scenes[0]]
    total = estimate_duration(hook, langs)
    if recap:
        total += estimate_duration(recap, langs)
    # add middle scenes while they fit (allow 15% overshoot on the first pick)
    for sc in middle:
        d = estimate_duration(sc, langs)
        if total + d <= target * 1.15 or len(chosen) == 1:
            chosen.append(sc)
            total += d
    if recap:
        chosen.append(recap)
    # keep the plan order sensible: hook, middle..., recap
    order = {id(s): i for i, s in enumerate(scenes)}
    chosen.sort(key=lambda s: order[id(s)])
    return [s.to_dict() for s in chosen]


GENERIC_SCAFFOLD = [
    {
        "id": "hook",
        "purpose": "hook",
        "motif": "structure",
        "headline": {"en": "{topic}", "ur": "{topic_ur}"},
        "narration": {
            "en": "We use {topic} all the time, but explaining it is harder than using it. Let's take it apart into parts we can draw, and put them back together.",
            "ur": "ہم {topic_ur} روز استعمال کرتے ہیں، مگر اس کی وضاحت کرنا اسے استعمال کرنے سے مشکل ہے۔ آئیے اس کے حصوں میں تقسیم کریں اور پھر انہیں جوڑ کر دکھائیں۔",
        },
        "elements": [
            {"type": "plate", "slot": "plate"},
            {"type": "hero", "slot": "hero", "params": {"en": "{topic}", "ur": "{topic_ur}"}},
        ],
        "actions": [{"action": "question"}, {"action": "nodes_in"}],
        "character": {"pose": "present", "slot": "char_left"},
    },
    {
        "id": "parts",
        "purpose": "explain",
        "motif": "structure",
        "headline": {"en": "The parts", "ur": "اجزاء"},
        "narration": {
            "en": "Start with the parts. Name each piece of {topic} and what it does, because every explanation is built from clear parts and the links between them.",
            "ur": "شروع اجزاء سے کریں۔ {topic_ur} کے ہر حصے کا نام اور اس کا کام بتائیں، کیونکہ ہر وضاحت واضح حصوں اور ان کے تعلق سے بنتی ہے۔",
        },
        "elements": [
            {"type": "plate", "slot": "plate"},
            {"type": "concept_nodes", "slot": "stage",
             "params": {"nodes_en": ["input", "process", "output", "result"],
                        "nodes_ur": ["ان پٹ", "عمل", "آؤٹ پٹ", "نتیجہ"]}},
        ],
        "actions": [{"action": "nodes_in"}],
        "character": {"pose": "point_right", "slot": "char_left"},
    },
    {
        "id": "process",
        "purpose": "explain",
        "motif": "flow",
        "headline": {"en": "The process", "ur": "عمل"},
        "narration": {
            "en": "Then follow the process. Something goes in, something changes in the middle, and something comes out. The arrows show the direction of that change.",
            "ur": "پھر عمل کو دیکھیں۔ کچھ اندر جاتا ہے، درمیان میں کچھ بدلتا ہے، اور کچھ باہر آتا ہے۔ تیر اس تبدیلی کی سمت دکھاتے ہیں۔",
        },
        "elements": [
            {"type": "plate", "slot": "plate"},
            {"type": "process_chain", "slot": "stage",
             "params": {"nodes_en": ["start", "change", "result"],
                        "nodes_ur": ["شروعات", "تبدیلی", "نتیجہ"]}},
        ],
        "actions": [{"action": "process"}],
        "character": {"pose": "present", "slot": "char_right"},
    },
    {
        "id": "recap",
        "purpose": "recap",
        "motif": "layers",
        "headline": {"en": "Parts + process + result", "ur": "اجزاء، عمل، نتیجہ"},
        "narration": {
            "en": "So {topic} makes sense as a system: parts, a process and a result. Swap the labels for real details and the same explanation becomes specific.",
            "ur": "تو {topic_ur} ایک نظام کی طرح سمجھ میں آتا ہے: اجزاء، عمل اور نتیجہ۔ یہی وضاحت حقیقی تفصیلات ڈالنے سے مخصوص بن جاتی ہے۔",
        },
        "elements": [
            {"type": "plate", "slot": "plate"},
            {"type": "compare", "slot": "stage",
             "params": {"left_en": ["what goes in", "what changes", "what comes out"],
                        "left_ur": ["کیا اندر جاتا ہے", "کیا بدلتا ہے", "کیا باہر آتا ہے"],
                        "right_en": ["a part", "a process", "a result"],
                        "right_ur": ["ایک حصہ", "ایک عمل", "ایک نتیجہ"]}},
        ],
        "actions": [{"action": "compare"}],
        "character": {"pose": "celebrate", "slot": "char_left"},
    },
]


def _fill(text: str, topic: str, topic_ur: str) -> str:
    return text.replace("{topic}", topic).replace("{topic_ur}", topic_ur)


def topic_in_urdu(topic: str) -> str:
    """Best-effort Urdu rendering of a topic string.

    Transliteration is deliberately avoided: if the topic is already Urdu we keep
    it, otherwise we keep the Latin term inside the Urdu sentence (which is how
    Urdu technical speech actually handles borrowed terms).
    """
    if re.search(r"[\u0600-\u06FF]", topic):
        return topic
    return topic


def compose_generic(topic: str, langs: Sequence[str]) -> Story:
    topic_clean = " ".join(topic.split())
    topic_ur = topic_in_urdu(topic_clean)
    scenes = []
    for tpl in GENERIC_SCAFFOLD:
        seen_actions = []
        for a in tpl["actions"]:
            seen_actions.append(dict(a))
        scenes.append(Scene.from_dict({
            "id": tpl["id"],
            "purpose": tpl["purpose"],
            "motif": tpl["motif"],
            "narration": {k: _fill(v, topic_clean, topic_ur) for k, v in tpl["narration"].items()},
            "headline": {k: _fill(v, topic_clean, topic_ur) for k, v in tpl["headline"].items()},
            "keywords": {"en": [], "ur": []},
            "elements": tpl["elements"],
            "actions": seen_actions,
            "character": tpl["character"],
            "camera": "push_in",
        }))
    story = Story(
        topic=topic_clean, world="generic", palette="violet",
        title={"en": topic_clean, "ur": topic_ur},
        scenes=scenes, languages=list(langs), generator="generic-scaffold",
        warnings=[
            "No curated knowledge pack matched this topic, so the script uses a generic "
            "explanatory scaffold with abstract schematic visuals. Add a knowledge pack "
            "(ckd/content/knowledge.py) or run the optional local LLM for a topic-specific "
            "script and objects."
        ],
    )
    return story


_SENTENCE_END = "۔.!?؟"


def _split_sentences(text: str) -> List[str]:
    """Split on sentence punctuation, keeping the punctuation with its sentence."""
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in _SENTENCE_END:
            if buf.strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out


def _fit_duration(story: Story, langs: Sequence[str], target: float) -> List[str]:
    """Trim trailing sentences until the plan fits `target` (never below 2 sentences).

    Curated packs are written for ~45-60 s. Asking for a shorter video must actually
    shorten it, not silently ignore the number, so we drop whole sentences from the
    longest scenes and report exactly what was removed.
    """
    warnings: List[str] = []
    budget = target * 1.08
    for _ in range(24):
        total = sum(estimate_duration(sc, langs) for sc in story.scenes)
        if total <= budget:
            break
        # longest scene with the most sentences wins the trim
        cand = None
        for sc in story.scenes:
            if sc.purpose == "hook":
                continue
            counts = [len(_split_sentences(sc.narration.get(l, ""))) for l in langs]
            if not counts or min(counts) <= 2:
                continue
            if cand is None or estimate_duration(sc, langs) > estimate_duration(cand, langs):
                cand = sc
        if cand is None:
            # nothing left to trim sentence-by-sentence: drop one middle scene
            middle = [sc for sc in story.scenes if sc.purpose not in ("hook", "recap")]
            if len(story.scenes) <= 3 or not middle:
                break
            drop = min(middle, key=lambda sc: estimate_duration(sc, langs),
                       default=None)
            if drop is None:
                break
            # only drop when that actually lands closer to the requested length
            shorter = total - estimate_duration(drop, langs)
            if abs(target - shorter) >= abs(target - total):
                break
            story.scenes.remove(drop)
            warnings.append(
                f"narration shortened to approach the {target:.0f}s target: "
                f"removed scene '{drop.id}' from the curated plan"
            )
            continue
        for lang in langs:
            parts = _split_sentences(cand.narration.get(lang, ""))
            cand.narration[lang] = " ".join(parts[:-1])
        warnings.append(
            f"narration shortened to approach the {target:.0f}s target: "
            f"dropped one sentence from scene '{cand.id}'"
        )
    else:
        pass
    total = sum(estimate_duration(sc, langs) for sc in story.scenes)
    if total > target * 1.25:
        warnings.append(
            f"the curated pack still needs about {total:.0f}s at this length; "
            f"ask for >= {total:.0f}s to keep every beat"
        )
    return warnings


def compose_from_pack(pack: Dict, topic: str, langs: Sequence[str], target_seconds: float) -> Story:
    picked = _select_scenes(pack, target_seconds, langs)
    scenes = [Scene.from_dict(s) for s in picked]
    story = Story(
        topic=topic.strip(), world=pack["world"], palette=pack["palette"],
        title=dict(pack["title"]), scenes=scenes, languages=list(langs),
        generator="curated-pack", source_pack=pack["id"],
    )
    story.warnings.extend(_fit_duration(story, langs, target_seconds))
    return story


def compose_story(
    topic: str,
    *,
    languages: Sequence[str] = ("en",),
    target_seconds: float = 45.0,
    llm: Optional[object] = None,
    palette: str = "auto",
    notes: str = "",
) -> Story:
    """Build a validated story for `topic`."""
    topic = (topic or "").strip()
    if not topic:
        raise ValueError("topic is required")
    langs = list(dict.fromkeys(languages)) or ["en"]
    # 1. curated pack
    pack = find_pack(topic)
    if pack is not None:
        story = compose_from_pack(pack, topic, langs, target_seconds)
    # 2. optional local LLM
    elif llm is not None:
        from .llm import generate_with_llm

        story = generate_with_llm(llm, topic, langs, target_seconds, palette=palette)
    # 3. generic scaffold
    else:
        story = compose_generic(topic, langs)
    if palette not in ("auto", "", None):
        story.palette = palette
    if notes.strip():
        story = _merge_notes(story, notes.strip(), langs)
    validate_story(story, languages=langs)
    return story


def _merge_notes(story: Story, notes: str, langs: Sequence[str]) -> Story:
    """Attach user-supplied facts as a clearly-marked extra scene.

    Notes are used verbatim, so they can only be attached when they are written
    in every requested language (split by '||' or a language header).
    """
    parts = [p.strip() for p in notes.split("||") if p.strip()]
    narration: Dict[str, str] = {}
    if len(parts) >= len(langs):
        for lang, part in zip(langs, parts):
            narration[lang] = part
    elif len(langs) == 1:
        narration[langs[0]] = notes
    else:
        story.warnings.append(
            "User notes were skipped: multi-language runs need notes split by '||' in the "
            "same order as the requested languages."
        )
        return story
    scene = Scene.from_dict({
        "id": "user_notes",
        "purpose": "example",
        "motif": "structure",
        "narration": narration,
        "headline": {"en": "Your notes", "ur": "آپ کے نوٹس"},
        "elements": [
            {"type": "plate", "slot": "plate"},
            {"type": "concept_nodes", "slot": "stage",
             "params": {"nodes_en": ["from your notes"], "nodes_ur": ["آپ کے نوٹس سے"]}},
        ],
        "actions": [{"action": "nodes_in"}],
        "character": {"pose": "present", "slot": "char_right"},
    })
    # insert before the recap so the recap still closes the video
    idx = len(story.scenes) - 1 if story.scenes and story.scenes[-1].purpose == "recap" else len(story.scenes)
    story.scenes.insert(idx, scene)
    story.warnings.append("A 'user notes' scene was added from your outline; review it before publishing.")
    return story


def available_topics() -> List[Dict[str, str]]:
    return list_packs()
