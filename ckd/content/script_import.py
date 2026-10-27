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
* one new visual beat per spoken sentence, cut on measured sentence timing;
* the visual direction as the authoritative vocabulary and ordered shot list,
  semantically aligned to the sentence it describes (not blindly assigned by
  bullet index);
* the declared duration, used as a planning target, never to pad the narration.

What is *not* honoured, honestly
--------------------------------
The direction text asks for things a procedural renderer cannot produce:
"realistic cinematic footage", "historical photographs", "archival", "montage of
people".  Those bullets are mapped to the nearest thing this renderer actually
has -- a labelled motion graphic of the *subject* the bullet names (a phone, a
factory, a globe, a chart, an ecosystem) -- and the substitution is recorded in
`story.warnings`, so nobody mistakes the result for footage. A picture is used
once per video; sentences without a distinct matching subject become animated
typographic cards containing a phrase from the narration, not a fake photograph.

The importer never invents facts.  Numbers that appear in the script appear on
screen; nothing is added.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

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
    (("financial chart", "chart", "graph", "financial graphic", "timeline moving",
      "market share"),
     "chart", {}),
    (("timeline", "decision points", "product lifecycle"),
     "timeline", {}),
    (("world map", "global map", "across continents", "continents", "worldwide",
      "distribution routes", "routes", "across the world", "global"),
     "globe", {}),
    (("application ecosystem", "ecosystem", "operating systems", "developers",
      "platform"),
     "ecosystem", {}),
    (("cell tower", "towers", "fiber", "data infrastructure", "network infrastructure",
      "telecommunications infrastructure", "network of cell", "communication equipment",
      "radio equipment", "network equipment", "base station", "signals"),
     "tower", {}),
    (("factory", "paper mill", "manufacturing", "industrial", "rubber", "cables"),
     "factory", {}),
    (("headquarters", "office", "executive", "business leader", "conference table",
      "laboratory", "workspace", "engineers"),
     "statement", {}),
    (("touchscreen smartphone", "touchscreen", "modern smartphone", "smartphone"),
     "phone", {"kind": "touch"}),
    (("fingers", "browser", "page", "icons", "app store", "interface", "screen", "apps"),
     "phone", {"kind": "touch", "screen": "apps"}),
    (("keypad", "classic mobile", "classic phone", "old nokia", "nokia phone",
      "mobile phone", "handset", "phones", "phone"),
     "phone", {"kind": "classic"}),
)

def _classify(bullet: str) -> Tuple[str, Dict, str]:
    """Return (element type, params, honest note about what was substituted).

    A direction line often names two things ("a world map as phone icons spread
    across continents"); the rule with the most matching words wins instead of
    whichever rule happens to be listed first, so the picture answers the
    subject the line is *about*.
    """
    low = bullet.lower()
    best: Optional[Tuple[int, str, Dict]] = None
    for keys, kind, params in _RULES:
        hits = sum(1 for k in keys if k in low)
        if hits and (best is None or hits > best[0]):
            best = (hits, kind, dict(params))
    if best is not None:
        kind, params = best[1], best[2]
        note = ""
        if any(w in low for w in ("footage", "archival", "photograph", "montage",
                                  "stock", "realistic", "cinematic")):
            note = "rendered as a stylised motion graphic, not footage"
        if kind == "phone":
            if "ring" in low:
                params["ring"] = True
            if any(w in low for w in ("apps", "interface", "icons", "software")):
                params.setdefault("screen", "apps")
        return kind, params, note
    return "statement", {}, ""


def _strip_lead(text: str) -> Tuple[Optional[float], Optional[float], str]:
    """Split "0:05-0:12: cut to ..." into (start, end, description)."""
    m = _LEAD_TIME_RE.match(text)
    if not m:
        return None, None, text.strip()
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = int(m.group(3)) * 60 + int(m.group(4))
    return start, end, m.group(5).strip()


def _visual_key(kind: str, params: Dict) -> str:
    """Identity of a visual *type* for the strict no-repeat rule.

    Phone variants still read as phone shots; changing a ring flag or screen
    colour does not make a repeated phone a new picture.  A typographic card is
    unique by its own narration-derived words, so cards are keyed by that copy.
    """
    if kind == "statement":
        return "statement:" + str(params.get("en", ""))
    return kind


def _normalise(kind: str, params: Dict) -> Dict:
    """Fill renderer defaults before emitting an element."""
    params = {k: v for k, v in params.items() if k not in ("in", "out")}
    if kind == "phone":
        if "touch" in str(params.get("kind")):
            params.setdefault("screen", "blank")
        else:
            params = {"kind": "classic", "ring": bool(params.get("ring", False))}
    return params


def _card_text(sentence: str) -> str:
    """The words of a typographic card: the sentence's own key phrase.

    Never the visual-direction bullet - a card must say what the narrator is
    saying at that moment, or it is out of context by definition.  A sentence too
    long to set large is cut at a clause boundary (cards are read, not skimmed),
    never at a character count in the middle of a thought.
    """
    text = re.sub(r"\s+", " ", clean_direction(sentence)).strip().rstrip(".")
    # a card that opens with "But" or "So" reads like a fragment of something else
    text = re.sub(r"^(?:But|And|So|Now|Then|Yet|Still)\s+", "", text, flags=re.I).strip()
    if len(text) > 110:
        parts = [x.strip(" ,;:") for x in re.split(r"(?<=[,;:])\s+|\s+[\u2014\u2013]\s+", text)]
        parts = [x for x in parts if x]
        # the clause carrying the most meaning, preferring one that fits whole
        fitting = [x for x in parts if len(x) <= 110]
        pick = max(fitting, key=lambda x: len(_tokens(x))) if fitting else max(parts, key=len)
        text = pick
    if len(text) > 110:
        text = text[:110].rsplit(" ", 1)[0].rstrip(" ,;:") + "\u2026"
    return text[:1].upper() + text[1:] if text else text


_STOP = {
    "the", "and", "that", "with", "from", "this", "they", "them", "their", "there",
    "into", "over", "when", "what", "were", "was", "are", "for", "but", "not",
    "you", "your", "its", "it's", "has", "have", "had", "will", "would", "could",
    "than", "then", "also", "which", "while", "about", "after", "before", "more",
    "most", "some", "such", "only", "very", "just", "like", "even", "made", "make",
    "began", "become", "became", "been", "being", "does", "did", "doing", "can",
}


def _tokens(text: str) -> Set[str]:
    out: Set[str] = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z'\-]+", text.lower()):
        if len(raw) < 4 or raw in _STOP:
            continue
        out.add(raw.rstrip("s") if len(raw) > 4 else raw)
    return out


_FAMILY = {
    "phone": "device", "compare_phones": "device", "ecosystem": "network",
    "tower": "network", "factory": "industry", "globe": "data",
    "timeline": "data", "chart": "data", "stat": "data", "label": "data",
}


def _family(kind: str) -> str:
    return _FAMILY.get(kind, "abstract")


def _overlap(sentence: str, bullet: str) -> float:
    """How much a sentence and a direction bullet are talking about the same thing."""
    a, b = _tokens(sentence), _tokens(bullet)
    if not a or not b:
        return 0.0
    return float(len(a & b))


def _sentence_plan(scene: ScriptScene, used: Set[str], notes: List[str], *,
                   card_offset: int = 0) -> List[Tuple[str, Dict, str]]:
    """One visual per *spoken* sentence, matched to the words at that moment.

    The writer's direction bullets stay authoritative for *what* is drawn; the
    question this function answers is *which sentence* each bullet belongs to.
    Handing bullets out in file order, one sentence at a time, is what put a
    paper mill on the line about smartphones - the lists drift apart as soon as
    one sentence expands into three.  So bullets are aligned to sentences the
    way two transcriptions of the same speech are aligned: in order (a bullet
    never jumps backwards), one bullet per sentence at most, and only where the
    words actually agree.

    Per sentence, after alignment:

    1. use the bullet aligned to it;
    2. failing that, use a new subject the sentence itself names (years ->
       timeline, "touchscreen" -> a touch handset, "the world" -> a globe);
    3. failing that, set a phrase from the sentence as type. An unmatched bullet
       is reported, never forced under unrelated dialogue.

    A visual type is never drawn twice in the same video, so a subject already
    on the reel is passed over even if the writer asks for it again.
    """
    from ..voice.base import split_clauses

    sentences = split_clauses(scene.narration or "") or [scene.title or "\u2026"]
    queue: List[Tuple[str, str, Dict]] = []
    for bullet in (scene.visuals or []):
        desc = _strip_lead(bullet)[2]
        kind, params, note = _classify(desc)
        queue.append((desc, kind, _normalise(kind, params) | {"__note": note}))

    def clean(kind: str, params: Dict) -> Dict:
        return {k: v for k, v in params.items() if k != "__note"}

    def available(kind: str, params: Dict) -> bool:
        if kind == "statement":
            return True  # each card's text is its unique visual
        key = _visual_key(kind, clean(kind, params))
        return not key or key not in used

    # -- align sentences to bullets (Needleman-Wunsch over words) -------------
    kinds = [_classify(t) for t in sentences]
    n, m = len(sentences), len(queue)
    score = [[0.0] * m for _ in range(n)]
    for i, sentence in enumerate(sentences):
        s_kind = kinds[i][0]
        for j, (desc, kind, params) in enumerate(queue):
            if not available(kind, params):
                continue  # already on the reel: this video shows it once
            v = _overlap(sentence, desc)
            if s_kind != "statement" and _family(s_kind) == _family(kind):
                v += 1.0  # a device sentence may take a device bullet
            # two shared words (or one plus a recognisable subject) is agreement;
            # a single shared word is a coincidence like "market" or "company"
            score[i][j] = v if v >= 2.0 else 0.0

    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    move = [[0] * (m + 1) for _ in range(n + 1)]  # 0 skip sentence, 1 skip bullet, 2 match
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best, how = dp[i + 1][j], 0
            if dp[i][j + 1] > best + 1e-9:
                best, how = dp[i][j + 1], 1
            if score[i][j] > 0 and score[i][j] + dp[i + 1][j + 1] > best + 1e-9:
                best, how = score[i][j] + dp[i + 1][j + 1], 2
            dp[i][j], move[i][j] = best, how

    aligned: Dict[int, int] = {}
    i = j = 0
    while i < n and j < m:
        how = move[i][j]
        if how == 2:
            aligned[i] = j
            i += 1
            j += 1
        elif how == 1:
            j += 1
        else:
            i += 1

    # -- choose the picture for every sentence, in order ----------------------
    claimed: Set[int] = set()
    plan: List[Tuple[str, Dict, str]] = []
    card_count = 0
    for i, sentence in enumerate(sentences):
        s_kind, s_params, _ = _classify(sentence)
        s_params = _normalise(s_kind, s_params)

        def take(kind: str, params: Dict, note: str
                 ) -> Optional[Tuple[str, Dict, str]]:
            """Accept a picture only if the video has not shown it already."""
            params = clean(kind, params)
            if not available(kind, params):
                return None
            if kind != "statement":
                used.add(_visual_key(kind, params))
            return (kind, params, note)

        choice: Optional[Tuple[str, Dict, str]] = None
        if i in aligned:
            bullet_i = aligned[i]
            _desc, kind, params = queue[bullet_i]
            choice = take(kind, params, params.get("__note", ""))
            if choice is not None:
                claimed.add(bullet_i)
        if choice is None and s_kind != "statement":
            choice = take(s_kind, s_params, "")
        if choice is None:
            choice = ("statement", {}, "")
        kind, params, note = choice
        if kind == "statement":
            params = {**params, "en": _card_text(sentence), "ur": "",
                      "variant": (card_offset + card_count) % 3}
            card_count += 1
        plan.append((kind, params, note))
        if note:
            notes.append(f"{scene.number}: \"{_shorten(sentence, 60)}\" -> {note}")

    unmatched = [q[0] for bj, q in enumerate(queue) if bj not in claimed]
    if unmatched:
        notes.append(
            f"{scene.number}: {len(unmatched)} direction bullet(s) had nothing in "
            f"the spoken text to match and were not drawn: "
            + " | ".join(_shorten(u, 50) for u in unmatched))
    return plan


def _shots_for(scene: ScriptScene, index: int, used: Set[str], *,
               card_offset: int = 0) -> Tuple[List[Dict], List[str], Dict]:
    """Build one scene's elements from its spoken sentences + visual direction.

    Returns (elements, notes, control) where `control` carries the number of
    sentence beats, the times for the on-screen-text super, and how many
    typographic cards the no-repeat rule forced.
    """
    elements: List[Dict] = [{"type": "skyline", "slot": "back"}]
    notes: List[str] = []
    plan = _sentence_plan(scene, used, notes, card_offset=card_offset)
    n = len(plan)
    cards = 0
    for i, (kind, params, _note) in enumerate(plan):
        aid = f"beat{i + 1}"
        # each beat is `in` on its own cue and `out` on the next one
        el: Dict = {"type": kind, "slot": _slot_for(kind, i, n),
                    "params": {"in": aid, "cut": True}}
        if i + 1 < n:
            el["params"]["out"] = f"beat{i + 2}"
        # kept for review: which sentence this picture is answering
        el["sentence"] = _shorten(scene_narration_sentence(scene, i), 90)
        if kind == "chart":
            # a chart with no data would have to invent a trend.  Fall back to the
            # years the script itself mentions, drawn as a timeline.
            years = re.findall(r"\b(1[89]\d{2}|20\d{2}|1990s|2000s)\b",
                               scene.narration + " " + " ".join(scene.onscreen))
            if len(years) >= 2:
                kind = "timeline"
                el["type"] = "timeline"
                params = {"years": list(dict.fromkeys(years))[:5],
                          "notes": ["" for _ in dict.fromkeys(years)][:5],
                          "en": _sentence(clean_direction(scene_narration_sentence(scene, i)), 48)}
            else:
                params = {**params, "mode": "empty"}
        if kind == "statement":
            cards += 1
        el["params"].update(params)
        elements.append(el)

    control: Dict = {"beats": n, "cards": cards, "total": n}
    if scene.onscreen:
        lines = [_sentence(clean_direction(x), 54) for x in scene.onscreen if x.strip()][:3]
        if lines:
            super_el = {"type": "lower_third", "slot": "upper_supers",
                        "params": {"in": "supers", "out": "supers_out", "lines_en": lines}}
            elements.append(super_el)   # drawn last: supers sit on top of the picture
            # A lower third is a *super*, not a subtitle: it comes in, holds about
            # ten seconds and leaves.  Size the hold against the scene's *spoken*
            # length, not the writer's timecode window, which is often three times
            # the narration it contains.
            spoken = len(scene.narration.split()) / 2.65 + 2.0
            if scene.t_start is not None and scene.t_end is not None and spoken < 6.0:
                spoken = max(6.0, (scene.t_end - scene.t_start) * 0.5)
            hold_frac = min(0.45, max(0.12, 10.0 / max(6.0, spoken)))
            in_frac = 0.12
            control["supers"] = (in_frac, min(0.92, in_frac + hold_frac))
    return elements, notes, control


def scene_narration_sentence(scene: ScriptScene, index: int) -> str:
    """The sentence that beat `index` is answering (for review and story.json)."""
    from ..voice.base import split_clauses

    sentences = split_clauses(scene.narration or "")
    if 0 <= index < len(sentences):
        return sentences[index]
    return scene.title or ""


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
    # pictures already on the reel: a visual appears at most once per video
    used: Set[str] = set()
    cards = beats = 0
    for i, sc in enumerate(ps.scenes):
        elements, notes, control = _shots_for(sc, i, used, card_offset=cards)
        for note in notes:
            if "rendered as a stylised motion graphic, not footage" in note:
                substituted.append(note)
            else:
                warnings.append(note)
        cards += int(control.get("cards", 0))
        beats += int(control.get("total", 0))
        # one beat per spoken sentence, in order, with no time pinned: the timing
        # stage maps beat n onto spoken sentence n, so the picture changes exactly
        # when the narration moves on
        actions: List[Dict] = [{"action": f"beat{b + 1}"} for b in range(int(control["beats"]))]
        if control.get("supers"):
            a, b = control["supers"]
            actions.append({"action": "supers", "at_frac": round(a, 4)})
            actions.append({"action": "supers_out", "at_frac": round(b, 4)})
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
            "actions": actions,
            "character": {"visible": False},          # faceless documentary
            "headline_hold": 0.85,                   # clear title before sentence-driven visuals
            "camera": ["slow_push", "drift", "slow_pull", "pan_right"][i % 4],
            "notes": sc.audio_note,
        }))
    if include_cta and ps.cta is not None and ps.cta.narration:
        elements, notes, control = _shots_for(ps.cta, len(ps.scenes), used, card_offset=cards)
        for note in notes:
            if "rendered as a stylised motion graphic, not footage" in note:
                substituted.append(note)
            else:
                warnings.append(note)
        cards += int(control.get("cards", 0))
        beats += int(control.get("total", 0))
        scenes.append(Scene.from_dict({
            "id": "cta",
            "purpose": "cta",
            "narration": {"en": ps.cta.narration},
            "headline": {"en": ""},
            "keywords": {"en": []},
            "motif": "structure",
            "elements": elements,
            "actions": [{"action": f"beat{b + 1}"}
                        for b in range(int(control["beats"]))],
            "character": {"visible": False},
            "headline_hold": 0.0,
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
    if beats:
        story.warnings.append(
            f"{beats} spoken sentences, one picture each; {beats - cards} are drawn "
            f"subjects and {cards} are typographic cards. A picture is never shown "
            "twice in a video, so once the script's subjects are used up the "
            "remaining sentences are set as text. Add more distinct subjects to "
            "[VISUAL DIRECTION] (different places, objects, diagrams) for more "
            "drawn subjects and fewer cards. Typographic cards show a phrase from "
            "their matching spoken sentence; the narration and subtitles remain "
            "verbatim.")
    story.warnings.append(
        "This is a procedural renderer, not a stock-footage editor: matched visual-direction "
        "bullets become labelled motion graphics of their named subjects (phone, factory, globe, "
        "chart, ecosystem). Unmatched bullets are listed separately and are not forced under "
        "unrelated narration. No footage, archival photographs or real product photos are used.")
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
