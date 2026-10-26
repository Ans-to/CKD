"""Import a written documentary script into a renderable scene plan.

The scripts that motivated this module look like this (a very common format for
YouTube business/history documentaries):

```
HOW NOKIA LOST ITS EMPIRE

The Rise and Fall of a Mobile Phone Giant

**Video format:** Faceless business documentary
**Target duration:** 7-9 minutes

SCENE 1 — THE HOOK

**Time:** 0:00–0:35

**[VOICEOVER]**

Imagine building a company so powerful...

**[VISUAL DIRECTION]**

- 0:00-0:05: Extreme close-up of a classic mobile phone ringing in a dark room.
- 0:05-0:12: Rapid montage of people using old Nokia phones...

**[ON-SCREEN TEXT]**

1865 — Nokia's beginnings

**[AUDIO]**

Begin with a phone ringtone...
```

`import_script()` turns that into a `Story` the existing pipeline can render:
each `SCENE n — TITLE` block becomes a scene, the VOICEOVER becomes narration,
and the VISUAL DIRECTION bullets become timed *shots*.

What is honoured
----------------
* narration verbatim (nothing is rewritten, summarised or re-worded);
* scene order, scene titles and on-screen text;
* the timecodes in the visual direction, when they are present, so a cut lands
  where the writer asked for it rather than one-per-sentence;
* the declared duration, used as the planning target.

What is *not* honoured, honestly
--------------------------------
The direction text asks for things a procedural renderer cannot produce:
"realistic cinematic footage", "historical photographs", "archival", "montage of
people".  Those bullets are mapped to the nearest thing this renderer actually
has -- a labelled motion graphic of the *subject* the bullet names (a phone, a
factory, a globe, a chart, an ecosystem) -- and the substitution is recorded in
`story.warnings`, one line per scene, so nobody mistakes the result for footage.
Bullets that name something with no graphic equivalent at all become a clean
title/statement card instead of a fake photograph.

The importer never invents facts.  Numbers that appear in the script appear on
screen; nothing is added.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .schema import Scene, Story

# --------------------------------------------------------------------- parsing
_SCENE_RE = re.compile(
    r"^\s*(?:SCENE\s+(\d+)|PART\s+(\d+))\s*[—–:.\-]\s*(.+?)\s*$", re.I)
_SECTION_RE = re.compile(r"^\s*\*\*\s*\[?\s*([A-Z][A-Z /&'\-]{2,40}?)\s*\]?\s*\*\*\s*:?\s*$")
_BOLD_LINE_RE = re.compile(r"^\s*\*\*(.+?):?\*\*\s*:?\s*(.*)$")
_META_RE = re.compile(r"^\s*\*\*([A-Za-z ]{3,28})\s*:?\*\*\s*:?\s*(.+)$")
_TIME_RANGE_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[–—\-]\s*(\d{1,2}):(\d{2})")
_BULLET_RE = re.compile(r"^\s*[-*•]\s+(.+)$")
_LEAD_TIME_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*[–—\-]\s*(\d{1,2}):(\d{2})\s*:\s*(.+)$")
_HEADER_STYLE_RE = re.compile(r"^\s*(OPTIONAL\s+)?(CALL TO ACTION|OUTRO|ENDING|CTA)\s*$", re.I)

# Section names, normalised
VOICEOVER = "voiceover"
VISUALS = "visuals"
ONSCREEN = "onscreen"
AUDIO = "audio"
TITLE = "title"


def _norm_section(name: str) -> str:
    n = re.sub(r"[^A-Z ]", "", name.upper()).strip()
    if n.startswith("VOICE") or n in {"VO", "NARRATION", "SCRIPT"}:
        return VOICEOVER
    if n.startswith("VISUAL") or n in {"SHOTS", "B-ROLL", "BROLL", "FOOTAGE"}:
        return VISUALS
    if n.startswith("ON SCREEN") or n.startswith("ONSCREEN") or n in {"TEXT", "SUPERS"}:
        return ONSCREEN
    if n.startswith("AUDIO") or n.startswith("MUSIC") or n.startswith("SOUND"):
        return AUDIO
    if n in {"TITLE"}:
        return TITLE
    return n.lower()


def _mmss(text: str) -> float:
    m = re.match(r"(\d{1,2}):(\d{2})(?::(\d{2}))?$", text.strip())
    if not m:
        return 0.0
    if m.group(3) is not None:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return int(m.group(1)) * 60 + int(m.group(2))


def _seconds(h: str, m: str, s: str, _d: str) -> float:
    return int(h) * 60 + int(m)


@dataclass
class ScriptScene:
    number: int
    title: str
    narration: str = ""
    visuals: List[str] = field(default_factory=list)
    onscreen: List[str] = field(default_factory=list)
    t_start: Optional[float] = None
    t_end: Optional[float] = None
    audio_note: str = ""


@dataclass
class ParsedScript:
    title: str = ""
    subtitle: str = ""
    meta: Dict[str, str] = field(default_factory=dict)
    scenes: List[ScriptScene] = field(default_factory=list)
    cta: Optional[ScriptScene] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def target_seconds(self) -> Optional[float]:
        """Midpoint of a stated "7-9 minutes" range, else the last timecode."""
        dur = self.meta.get("target duration", "") or self.meta.get("duration", "")
        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:[–—-]\s*(\d+(?:\.\d+)?))?\s*(?:minutes?|mins?|m)\b",
                      dur, re.I)
        if m:
            lo = float(m.group(1))
            hi = float(m.group(2)) if m.group(2) else lo
            return (lo + hi) / 2.0 * 60.0
        m = re.search(r"(\d+)\s*(?:seconds?|secs?|s)\b", dur, re.I)
        if m:
            return float(m.group(1))
        times = [s.t_end for s in self.scenes if s.t_end]
        if times:
            return float(max(times))
        return None


def parse_script(text: str) -> ParsedScript:
    """Parse the markdown-ish script format into scenes.  Never raises on odd input."""
    ps = ParsedScript()
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # ---- title block: everything before the first scene / known section
    i = 0
    prefix: List[str] = []
    while i < len(lines):
        line = lines[i]
        if _SCENE_RE.match(line) or _SECTION_RE.match(line) or _META_RE.match(line) \
                or _HEADER_STYLE_RE.match(line):
            break
        if line.strip():
            prefix.append(line.strip())
        elif prefix:
            # a blank line after the title block ends it
            break
        i += 1
    if prefix:
        ps.title = prefix[0].lstrip("#").strip()
        rest = [p for p in prefix[1:] if p and not p.startswith("**")]
        if rest:
            ps.subtitle = rest[0]
    while i < len(lines) and not _SCENE_RE.match(lines[i]) and not _SECTION_RE.match(lines[i]) \
            and not _HEADER_STYLE_RE.match(lines[i]):
        m = _META_RE.match(lines[i])
        if m:
            ps.meta[m.group(1).strip().lower()] = m.group(2).strip()
        i += 1

    # ---- scenes
    current: Optional[ScriptScene] = None
    section = ""
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        scene_m = _SCENE_RE.match(line)
        cta_m = _HEADER_STYLE_RE.match(line)
        sec_m = _SECTION_RE.match(line)

        if scene_m or (cta_m and "SCENE" not in line.upper()):
            if current is not None:
                ps.scenes.append(current)
            if cta_m and not scene_m:
                current = ScriptScene(number=len(ps.scenes) + 1,
                                      title="Call to action" if "OPTION" in line.upper() else
                                      line.strip().title())
                ps.cta = current
                section = ""
                i += 1
                continue
            num = int(scene_m.group(1) or scene_m.group(2) or (len(ps.scenes) + 1))
            title = scene_m.group(3)
            title = re.sub(r"^[#*\s]+|[#*\s]+$", "", title)
            current = ScriptScene(number=num, title=title)
            section = ""
            i += 1
            continue

        if sec_m:
            section = _norm_section(sec_m.group(1))
            i += 1
            continue

        if current is None:
            i += 1
            continue

        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        tm = re.search(r"\*\*Time:\*\*\s*(.+)$", stripped, re.I) or \
            re.match(r"^\s*Time:\s*(.+)$", stripped, re.I)
        if tm:
            rng = _TIME_RANGE_RE.search(tm.group(1))
            if rng:
                current.t_start = int(rng.group(1)) * 60 + int(rng.group(2))
                current.t_end = int(rng.group(3)) * 60 + int(rng.group(4))
            i += 1
            continue

        bullet = _BULLET_RE.match(stripped)
        if section == VISUALS:
            if bullet:
                current.visuals.append(bullet.group(1).strip())
            elif current.visuals:
                current.visuals[-1] += " " + stripped
            else:
                current.visuals.append(stripped)
        elif section == ONSCREEN:
            if bullet:
                current.onscreen.append(bullet.group(1).strip())
            else:
                current.onscreen.append(stripped)
        elif section == AUDIO:
            if bullet:
                current.audio_note = (current.audio_note + " " + bullet.group(1)).strip()
            else:
                current.audio_note = (current.audio_note + " " + stripped).strip()
        elif section == VOICEOVER:
            body = stripped
            if body.startswith("**") and body.endswith("**") and len(body) < 40:
                i += 1
                continue
            current.narration = (current.narration + (" " if current.narration else "") + body).strip()
        else:
            # unsectioned prose inside a scene is treated as narration
            if not current.narration:
                current.narration = stripped
        i += 1
    if current is not None:
        ps.scenes.append(current)

    # CTA scenes are not normal scenes: keep them separate but in order
    ps.scenes = [s for s in ps.scenes if s is not ps.cta]
    if not ps.scenes:
        ps.warnings.append("no 'SCENE n — TITLE' blocks found; the script was not imported")
    return ps


# ------------------------------------------------------- visual direction -> shots
# keyword -> (element type, params).  First match wins, so order matters.
_RULES: Sequence[Tuple[Tuple[str, ...], str, Dict]] = (
    (("split-screen", "split screen", "comparison between", "versus", "vs."),
     "compare_phones", {}),
    (("touchscreen smartphone", "touchscreen", "modern smartphone", "smartphone"),
     "phone", {"kind": "touch"}),
    (("keypad", "classic mobile", "classic phone", "old nokia", "nokia phone",
      "mobile phone", "handset", "phone ringing", "phones"),
     "phone", {"kind": "classic"}),
    (("world map", "global map", "across continents", "global", "worldwide", "cities",
      "global telecommunications", "global network", "distribution routes", "routes",
      "across the world"),
     "globe", {}),
    (("financial chart", "chart", "graph", "financial graphic", "timeline moving",
      "market share", "value"),
     "chart", {}),
    (("timeline", "decision points", "product lifecycle"),
     "timeline", {}),
    (("application ecosystem", "ecosystem", "operating systems", "apps", "developers",
      "platform"),
     "ecosystem", {}),
    (("cell tower", "towers", "fiber", "data infrastructure", "network infrastructure",
      "telecommunications infrastructure", "network of cell", "communication equipment",
      "radio equipment", "network equipment", "base station", "signals"),
     "tower", {}),
    (("factory", "paper mill", "manufacturing", "industrial", "rubber"),
     "factory", {}),
    (("headquarters", "office", "executive", "business leader", "conference table",
      "laboratory", "workspace", "engineers"),
     "statement", {}),
    (("fingers", "browser", "page", "icons", "app store", "interface", "screen"),
     "phone", {"kind": "touch", "screen": "apps"}),
)

_SUBJECT_HINTS = (
    "phone", "handset", "mobile", "chart", "map", "globe", "tower", "factory",
    "timeline", "ecosystem", "screen", "browser", "makers", "engineers",
)


def _classify(bullet: str) -> Tuple[str, Dict, str]:
    """Return (element type, params, honest note about what was substituted)."""
    low = bullet.lower()
    for keys, kind, params in _RULES:
        if any(k in low for k in keys):
            note = ""
            if any(w in low for w in ("footage", "archival", "photograph", "montage",
                                      "stock", "realistic", "cinematic")):
                note = "rendered as a stylised motion graphic, not footage"
            return kind, dict(params), note
    if any(w in low for w in ("text", "title", "statement", "quote", "label")):
        return "statement", {}, ""
    return "statement", {}, ""


def _strip_lead(text: str) -> Tuple[Optional[float], Optional[float], str]:
    """Split "0:05-0:12: cut to ..." into (start, end, description)."""
    m = _LEAD_TIME_RE.match(text)
    if not m:
        return None, None, text.strip()
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = int(m.group(3)) * 60 + int(m.group(4))
    return start, end, m.group(5).strip()


def _shots_for(scene: ScriptScene, index: int) -> Tuple[List[Dict], List[str], Dict[str, float]]:
    """Build elements + action list for one scene from its visual direction.

    Returns (elements, notes, shot_times) where shot_times maps action id to a
    fraction of the scene (0..1).
    """
    elements: List[Dict] = [{"type": "skyline", "slot": "back"}]
    notes: List[str] = []
    bullets = scene.visuals or []
    shots: List[Tuple[Optional[float], Optional[float], str]] = []
    for b in bullets:
        shots.append(_strip_lead(b))

    # fall back to the scene's own timecode range when bullets carry none
    times = [s for s in shots if s[0] is not None]
    if not times and scene.t_start is not None and scene.t_end is not None:
        n = max(1, len(shots))
        span = max(1.0, scene.t_end - scene.t_start)
        shots = [(scene.t_start + span * i / n, scene.t_start + span * (i + 1) / n, s[2])
                 for i, s in enumerate(shots)]
    if not shots:
        # no direction at all: one statement card built from the on-screen text
        text = " ".join(scene.onscreen[:2]) if scene.onscreen else scene.title
        shots = [(None, None, text)]

    # normalise to fractions of this scene
    base = min([s[0] for s in shots if s[0] is not None] or [0.0])
    end = max([s[1] for s in shots if s[1] is not None] or [base + len(shots)])
    span = max(1.0, end - base)

    actions: List[Dict] = []
    frac_times: Dict[str, float] = {}
    supers = None
    if scene.onscreen:
        lines = [_sentence(clean_direction(x), 54) for x in scene.onscreen if x.strip()][:3]
        if lines:
            supers = {"type": "lower_third", "slot": "upper_supers",
                      "params": {"in": "supers", "lines_en": lines}}
    for i, (s0, s1, desc) in enumerate(shots):
        kind, params, note = _classify(desc)
        aid = f"shot{i + 1}"
        # each shot is `in` on its own action and `out` on the next one
        el = {"type": kind, "slot": _slot_for(kind, i, len(shots)), "params": {"in": aid}}
        if i + 1 < len(shots):
            el["params"]["out"] = f"shot{i + 2}"
        el["shot"] = desc  # kept for review; the renderer ignores unknown keys
        if kind == "phone":
            if "touch" not in str(params.get("kind")):
                params = {"kind": "classic", "ring": True}
        if kind == "chart":
            # a chart with no data would have to invent a trend.  Fall back to the
            # years the script itself mentions, drawn as a timeline.
            years = re.findall(r"\b(1[89]\d{2}|20\d{2}|1990s|2000s)\b", scene.narration + " " + " ".join(scene.onscreen))
            if len(years) >= 2:
                kind = "timeline"
                el["type"] = "timeline"
                params = {"years": list(dict.fromkeys(years))[:5],
                          "notes": ["" for _ in dict.fromkeys(years)][:5],
                          "en": _sentence(clean_direction(desc), 48)}
            else:
                params.update({"mode": "empty"})
        if kind == "statement":
            copy = clean_direction(desc)
            params.update({"en": _sentence(copy, 58), "ur": ""})
        el["params"].update(params)
        elements.append(el)
        if s0 is not None and s1 is not None:
            frac = max(0.0, min(0.98, (s0 - base) / span))
        else:
            frac = i / max(1, len(shots))
        actions.append({"action": aid, "at_frac": round(frac, 4)})
        frac_times[aid] = frac
        if note:
            notes.append(f"{scene.number}.{i + 1}: \"{_shorten(desc, 70)}\" -> {note}")
    if supers is not None:
        elements.append(supers)   # drawn last: supers sit on top of the picture
        actions.insert(0, {"action": "supers", "at_frac": 0.16})
    return elements, notes, frac_times


def _slot_for(kind: str, i: int, n: int) -> str:
    if kind in ("globe", "chart", "timeline", "ecosystem", "compare_phones", "statement"):
        return "wide"
    if kind == "phone":
        return "phone"
    if kind == "factory":
        return "factory"
    if kind == "tower":
        return "tower"
    if kind == "stat":
        return "hero"
    return "stage"


_CAMERA_VERBS = (
    "an extreme close-up of", "extreme close-up of", "extreme close-up", "close-up of",
    "close up of", "cut to", "show an", "show a", "show the", "show", "display",
    "transition to", "transition from", "cut between", "end with", "end on", "depict",
    "reveal", "animate", "montage of", "rapid montage of", "a wide view of",
    "a dramatic transition from", "a dramatic transition to", "a slow", "slowly",
)


def clean_direction(text: str) -> str:
    """Turn a visual-direction bullet into readable on-screen copy.

    "Show an archival-style industrial paper mill in 19th-century Finland."
    -> "archival-style industrial paper mill in 19th-century Finland"
    """
    t = re.sub(r"^\d{1,2}:\d{2}\s*[–—-]\s*\d{1,2}:\d{2}\s*:?\s*", "", text).strip()
    low = t.lower()
    for verb in _CAMERA_VERBS:
        if low.startswith(verb + " "):
            t = t[len(verb):].strip()
            low = t.lower()
    t = re.sub(r"^the\s+", "", t)
    return t.strip().rstrip(".").strip()


def _shorten(text: str, limit: int = 46) -> str:
    t = re.sub(r"^\d{1,2}:\d{2}\s*[–—-]\s*\d{1,2}:\d{2}\s*:?\s*", "", text).strip()
    t = re.sub(r"\s+", " ", t)
    if len(t) <= limit:
        return t
    cut = t[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:") + "…"


def _headline(title: str) -> str:
    t = title.strip().rstrip(".")
    # "THE HOOK" -> "The hook"; keep existing mixed case
    if t.isupper():
        t = t.capitalize()
    return t


def import_script(text: str, *, languages: Sequence[str] = ("en",),
                  include_cta: bool = True, palette: str = "documentary",
                  world: str = "business") -> Story:
    """Parse a written documentary script into a validated, renderable `Story`."""
    ps = parse_script(text)
    scenes: List[Scene] = []
    warnings: List[str] = list(ps.warnings)
    substituted: List[str] = []
    for i, sc in enumerate(ps.scenes):
        elements, notes, shot_fracs = _shots_for(sc, i)
        substituted.extend(notes)
        headline = {"en": _headline(sc.title) or f"Part {sc.number}"}
        narration: Dict[str, str] = {}
        for lang in languages:
            if lang == "en":
                narration["en"] = sc.narration or sc.title
            else:
                warnings.append(
                    f"scene {sc.number}: the script is English only, so {lang!r} narration is "
                    "missing and the run will refuse to render that language "
                    "(write it yourself, or run English only)")
        onscreen = {"en": " · ".join(sc.onscreen[:2]) if sc.onscreen else ""}
        scenes.append(Scene.from_dict({
            "id": f"s{sc.number:02d}_{_slug(sc.title)}",
            "purpose": "hook" if i == 0 else ("recap" if i == len(ps.scenes) - 1 else "explain"),
            "narration": narration,
            "headline": headline,
            "keywords": {"en": [w for w in re.findall(r"[A-Z][a-z]{4,}", sc.title)][:3]},
            "motif": "structure",
            "elements": elements,
            "beats": [],
            # the shot times come from the writer's own timecodes, not from the
            # sentence count: that is what "0:05-0:12" means
            "actions": [{"action": k, "at_frac": v} for k, v in shot_fracs.items()],
            "character": {"visible": False},          # faceless documentary
            "headline_hold": 5.0 if i else 6.0,       # title card, then out of the way
            "camera": ["slow_push", "drift", "slow_pull", "pan_right"][i % 4],
            "notes": sc.audio_note,
        }))
    if include_cta and ps.cta is not None and ps.cta.narration:
        scenes.append(Scene.from_dict({
            "id": "cta",
            "purpose": "cta",
            "narration": {"en": ps.cta.narration},
            "headline": {"en": ""},
            "keywords": {"en": []},
            "motif": "structure",
            "elements": [
                {"type": "skyline", "slot": "back"},
                {"type": "statement", "slot": "wide",
                 "params": {"in": "subscribe", "en": "Subscribe"}},
            ],
            "actions": [{"action": "subscribe"}],
            "character": {"visible": False},
            "headline_hold": 4.0,
            "camera": "pull_out",
        }))
    story = Story(
        topic=ps.title or "imported script",
        world=world,
        palette=palette,
        title={"en": ps.title or "Imported script", "ur": ""},
        scenes=scenes,
        languages=list(languages),
        generator="imported-script",
        source_pack=None,
    )
    if ps.subtitle:
        story.warnings.append(f"subtitle from the script: {ps.subtitle}")
    story.warnings.append(
        "This is a procedural renderer, not a stock-footage editor: every visual-direction "
        "bullet became a labelled motion graphic of the thing it names (phone, factory, globe, "
        "chart, ecosystem). No footage, no archival photographs and no real product photos are "
        "used or imitated.")
    if substituted:
        story.warnings.append(
            "The script asked for footage/archival/photographic shots, which this renderer "
            "cannot produce: " + "; ".join(substituted[:8])
            + (" …" if len(substituted) > 8 else "")
        )
    target = ps.target_seconds
    total_words = sum(len(s.narration.split()) for s in ps.scenes)
    spoken = total_words / 2.65
    if target:
        story.warnings.append(
            f"script declares {target / 60:.1f} min of running time; its voice-over is about "
            f"{spoken / 60:.1f} min at 160 wpm ({total_words} words). The narration is used "
            "verbatim, so the render follows the words, not the declared duration.")
        ratio = target / max(1.0, spoken)
        if ratio > 1.5:
            need = (target / 60.0) * 160.0
            story.warnings.append(
                f"the script is {ratio:.1f}x shorter than its declared duration: at 160 wpm, "
                f"{target / 60:.0f} minutes needs roughly {need:.0f} spoken words and this script "
                f"has {total_words}. Nothing was invented to fill the gap - add writing to the "
                "script, or publish it at its true length.")
    return story


def _sentence(text: str, limit: int = 58) -> str:
    """Trim to a phrase a title card can hold, keeping a whole clause if possible."""
    t = text.strip()
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    if len(t) <= limit:
        return t
    cut = t[:limit]
    if "," in cut:
        cut = cut.rsplit(",", 1)[0]
    else:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.") + "…"


def _slug(text: str) -> str:
    t = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return t[:28] or "scene"


def read_script(path) -> str:
    from pathlib import Path

    return Path(path).read_text(encoding="utf-8-sig")
