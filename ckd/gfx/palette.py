"""Colour palettes.

Every visual world picks a palette by name so that a video has a coherent look
and different topics feel different.  Palettes are plain dicts of hex colours so
they are easy to edit / extend from the notebook.
"""
from __future__ import annotations

from typing import Dict, Tuple

PALETTES: Dict[str, Dict[str, str]] = {
    "warm": {
        "bg_top": "#1b1030",
        "bg_bottom": "#3a1d3d",
        "sky_glow": "#ff9d5c",
        "ground": "#2a1633",
        "ground_far": "#3d2246",
        "ink": "#1a1023",
        "paper": "#fff4e2",
        "accent": "#ffb347",
        "accent2": "#ff6b6b",
        "accent3": "#ffd93d",
        "cool": "#5ac8fa",
        "metal": "#cbd5e1",
        "metal_dark": "#7c8ba1",
        "glass": "#8fd3ff",
        "plant": "#68d391",
        "shadow": "#12081c",
        "text": "#fff8ef",
        "muted": "#d9c8c0",
    },
    "tech": {
        "bg_top": "#08121f",
        "bg_bottom": "#102a43",
        "sky_glow": "#2dd4bf",
        "ground": "#0a1a29",
        "ground_far": "#143a52",
        "ink": "#06121c",
        "paper": "#eaf6ff",
        "accent": "#38bdf8",
        "accent2": "#f472b6",
        "accent3": "#a3e635",
        "cool": "#22d3ee",
        "metal": "#cbd5e1",
        "metal_dark": "#64748b",
        "glass": "#7dd3fc",
        "plant": "#4ade80",
        "shadow": "#040d16",
        "text": "#eaf6ff",
        "muted": "#9fb3c8",
    },
    "blueprint": {
        "bg_top": "#0b2545",
        "bg_bottom": "#123a63",
        "sky_glow": "#7cc6fe",
        "ground": "#08203c",
        "ground_far": "#0f3358",
        "ink": "#031427",
        "paper": "#e8f3ff",
        "accent": "#ffb703",
        "accent2": "#fb5607",
        "accent3": "#8ecae6",
        "cool": "#4cc9f0",
        "metal": "#d7e3f4",
        "metal_dark": "#7f9cc4",
        "glass": "#9ad5ff",
        "plant": "#57cc99",
        "shadow": "#06182c",
        "text": "#eaf4ff",
        "muted": "#a9c1e0",
    },
    "forest": {
        "bg_top": "#0d1f1a",
        "bg_bottom": "#1b3a2f",
        "sky_glow": "#a7f3d0",
        "ground": "#10241c",
        "ground_far": "#1e4335",
        "ink": "#07130f",
        "paper": "#f2fff8",
        "accent": "#f9c74f",
        "accent2": "#f9844a",
        "accent3": "#90be6d",
        "cool": "#4cc9f0",
        "metal": "#d9e2e8",
        "metal_dark": "#7c8f86",
        "glass": "#a7e8d5",
        "plant": "#43aa8b",
        "shadow": "#050d0a",
        "text": "#f1fff8",
        "muted": "#a9cbbd",
    },
    "violet": {
        "bg_top": "#160b2b",
        "bg_bottom": "#2d1b4e",
        "sky_glow": "#c084fc",
        "ground": "#1a1030",
        "ground_far": "#2b1a48",
        "ink": "#100821",
        "paper": "#f7f0ff",
        "accent": "#f0abfc",
        "accent2": "#38bdf8",
        "accent3": "#fde047",
        "cool": "#7dd3fc",
        "metal": "#d5d1e8",
        "metal_dark": "#8a7fb0",
        "glass": "#c4b5fd",
        "plant": "#6ee7b7",
        "shadow": "#0a0418",
        "text": "#f8f2ff",
        "muted": "#bfb0d8",
    },
    "daylight": {
        "bg_top": "#bfe6ff",
        "bg_bottom": "#eaf7ff",
        "sky_glow": "#fff3b0",
        "ground": "#cfe8c9",
        "ground_far": "#a9d3a1",
        "ink": "#152635",
        "paper": "#ffffff",
        "accent": "#ff8f3f",
        "accent2": "#e63946",
        "accent3": "#ffd166",
        "cool": "#2a9df4",
        "metal": "#dce6ee",
        "metal_dark": "#7d8fa3",
        "glass": "#8ecdf7",
        "plant": "#59a96a",
        "shadow": "#9fb6c9",
        "text": "#12212e",
        "muted": "#4a5f72",
    },
}

DEFAULT_PALETTE = "warm"
PALETTE_ALIASES = {
    "solar": "warm",
    "energy": "warm",
    "wifi": "tech",
    "network": "tech",
    "bridge": "blueprint",
    "engineering": "blueprint",
    "biology": "forest",
    "nature": "forest",
    "space": "violet",
    "science": "violet",
    "bright": "daylight",
    "light": "daylight",
}


def parse_color(color) -> Tuple[int, int, int, int]:
    if isinstance(color, (tuple, list)):
        r, g, b = (int(c) for c in color[:3])
        a = int(color[3]) if len(color) > 3 else 255
        return (r, g, b, a)
    s = str(color).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), 255)
    if len(s) == 8:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16))
    raise ValueError(f"Bad colour: {color!r}")


def get_palette(name: str | None, *, overrides: Dict[str, str] | None = None) -> Dict[str, str]:
    key = (name or DEFAULT_PALETTE).lower()
    key = PALETTE_ALIASES.get(key, key)
    if key not in PALETTES:
        key = DEFAULT_PALETTE
    pal = dict(PALETTES[key])
    if overrides:
        pal.update(overrides)
    pal["_name"] = key
    return pal
