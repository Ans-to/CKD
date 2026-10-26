"""Timing: turn a scene plan + measured narration into animation schedules.

Two jobs:
  1. **Actions** - each planned action is mapped onto the narration clause it
     illustrates, so motion happens *while* the narrator explains that idea.
  2. **Captions** - group narration words (with their measured onsets) into
     readable caption cues that respect safe margins, then expose per-word
     karaoke timing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from ..content.schema import Beat, Scene
from ..voice.base import WordTiming
from ..voice.narration import SceneAudio
from .worlds.base import ActionState

MAX_CAPTION_WORDS = 7
MAX_CAPTION_CHARS = 62
CAPTION_MIN_DUR = 0.85


@dataclass
class CaptionCue:
    index: int
    start: float        # relative to scene
    end: float
    words: List[WordTiming] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "text": self.text,
            "words": [w.to_dict() for w in self.words],
        }


def assign_actions(scene: Scene, narration: SceneAudio, *, scene_duration: float,
                   lead: float = 0.15) -> List[ActionState]:
    """Distribute the scene's planned actions over its narration clauses.

    If the plan provides fewer actions than clauses, the last actions stretch to
    cover the remaining clauses (state persists anyway, so this reads as a single
    continuing beat).  If it provides more, extras are spread evenly.
    """
    clauses = narration.clauses
    actions = list(scene.actions) if hasattr(scene, "actions") else []
    out: List[ActionState] = []
    if not actions:
        return out
    # An action may pin itself to a fraction of the scene (`at_frac`) or to an
    # absolute second (`at`).  Imported documentary scripts use this to cut to a
    # new shot on its own cue instead of one shot per spoken sentence.
    if any(("at_frac" in a or "at" in a) for a in actions):
        starts: List[Optional[float]] = []
        for act in actions:
            if "at" in act:
                starts.append(max(0.0, float(act["at"])))
            elif "at_frac" in act:
                starts.append(max(0.0, min(1.0, float(act["at_frac"]))) * scene_duration)
            else:
                starts.append(None)
        # an unpinned action rides along with the shot that precedes it
        last = 0.0
        for i in range(len(starts)):
            if starts[i] is None:
                starts[i] = last
            else:
                last = starts[i]
        for i, act in enumerate(actions):
            nxt = next((starts[j] for j in range(i + 1, len(starts))
                        if starts[j] is not None and starts[j] > starts[i]), scene_duration)
            begin = float(starts[i])
            finish = min(scene_duration, max(begin + 0.2, nxt))
            out.append(ActionState(act.get("action", f"action_{i}"), begin, finish))
        return out
    if not clauses:
        n = len(actions)
        for i, a in enumerate(actions):
            out.append(ActionState(a["action"], scene_duration * i / n, scene_duration))
        return out
    for i, act in enumerate(actions):
        if i < len(clauses):
            start = max(0.0, clauses[i].start - lead)
            end = min(scene_duration, clauses[i].end + 0.25)
        else:
            idx = min(len(clauses) - 1, i)
            start = max(0.0, clauses[idx].start - lead)
            end = scene_duration
        if out and start < out[-1].end:
            start = out[-1].end
        end = max(start + 0.35, min(end, scene_duration))
        out.append(ActionState(act.get("action", f"action_{i}"), start, end))
    return out


def build_captions(words: Sequence[WordTiming], *, max_words: int = MAX_CAPTION_WORDS,
                   max_chars: int = MAX_CAPTION_CHARS, scene_duration: float = 0.0) -> List[CaptionCue]:
    """Group word timings into caption cues (word-accurate when measured)."""
    cues: List[CaptionCue] = []
    cur: List[WordTiming] = []
    cur_len = 0
    for w in words:
        wl = len(w.text)
        if cur and (len(cur) >= max_words or cur_len + wl + 1 > max_chars):
            cues.append(_make_cue(len(cues), cur))
            cur, cur_len = [], 0
        cur.append(w)
        cur_len += wl + 1
    if cur:
        cues.append(_make_cue(len(cues), cur))
    # enforce minimum display time by extending into the gap (never overlapping
    # the next cue's start time)
    for i, cue in enumerate(cues):
        nxt = cues[i + 1].start if i + 1 < len(cues) else scene_duration or cue.end
        if cue.end - cue.start < CAPTION_MIN_DUR:
            cue.end = min(max(cue.start + CAPTION_MIN_DUR, cue.end), max(cue.end, nxt))
    return cues


def _make_cue(index: int, words: List[WordTiming]) -> CaptionCue:
    return CaptionCue(index=index, start=words[0].start, end=max(w.end for w in words), words=list(words))


def fill_beats(scene: Scene, narration: SceneAudio, *, scene_duration: float) -> List[Beat]:
    """Attach concrete times to the planned beats (for the storyboard JSON)."""
    beats: List[Beat] = []
    clauses = narration.clauses
    for i, b in enumerate(scene.beats):
        if i < len(clauses):
            b.at = round(clauses[i].start, 3)
            b.hold = round(max(0.3, clauses[i].end - clauses[i].start), 3)
        else:
            b.at = round(scene_duration * i / max(1, len(scene.beats)), 3)
            b.hold = round(scene_duration / max(1, len(scene.beats)), 3)
        beats.append(b)
    return beats


def storyboard_timing(story, tracks: Dict[str, "NarrationTrack"]) -> Dict[str, dict]:
    """Per-language timing summary written into project.json/storyboard."""
    from ..voice.narration import NarrationTrack  # local import to avoid a cycle

    out: Dict[str, dict] = {}
    for lang, track in tracks.items():
        scenes = []
        for scene, na in zip(story.scenes, track.scenes):
            actions = assign_actions(scene, na, scene_duration=na.duration)
            cues = build_captions(na.words, scene_duration=na.duration)
            scenes.append({
                "scene_id": scene.id,
                "start": round(na.start, 3),
                "duration": round(na.duration, 3),
                "frames": na.frames,
                "clauses": [{"text": c.text, "start": round(c.start, 3), "end": round(c.end, 3)}
                            for c in na.clauses],
                "actions": [{"id": a.id, "start": round(a.start, 3), "end": round(a.end, 3)} for a in actions],
                "captions": [c.to_dict() for c in cues],
            })
        out[lang] = {
            "duration": round(track.duration, 3),
            "timing_kind": track.timing_kind,
            "engine": track.engine,
            "voice": track.voice,
            "scenes": scenes,
        }
    return out
