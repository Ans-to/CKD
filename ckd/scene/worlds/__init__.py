"""World registry: topic -> visual language."""
from __future__ import annotations

from typing import Dict, List, Optional

from .base import RenderContext, World
from .solar import SolarWorld
from .wifi import WifiWorld
from .bridge import BridgeWorld
from .generic import GenericWorld
from .business import BusinessWorld

_REGISTRY: Dict[str, type] = {
    "solar": SolarWorld,
    "wifi": WifiWorld,
    "bridge": BridgeWorld,
    "generic": GenericWorld,
    "business": BusinessWorld,
}

_CACHE: Dict[str, World] = {}

KEYWORDS = {
    "solar": ["solar", "sunlight", "photovoltaic", "pv ", "sun", "سولر", "شمسی", "سورج"],
    "wifi": ["wi-fi", "wifi", "wireless", "router", "radio wave", "5g", "network", "وائی فائی", "روٹر"],
    "bridge": ["bridge", "truss", "suspension", "span", "beam", "پل", "ٹرس"],
    "business": ["company", "business", "market", "empire", "startup", "brand", "corporation",
                 "nokia", "apple", "microsoft", "documentary", "کمپنی", "کاروبار", "مارکیٹ"],
}


def get_world(world_id: str | None) -> World:
    key = (world_id or "generic").lower()
    if key not in _REGISTRY:
        key = "generic"
    if key not in _CACHE:
        _CACHE[key] = _REGISTRY[key]()
    return _CACHE[key]


def detect_world(topic: str) -> str:
    t = (topic or "").lower()
    best, best_len = "generic", 0
    for wid, kws in KEYWORDS.items():
        for kw in kws:
            if kw and kw in t and len(kw) > best_len:
                best, best_len = wid, len(kw)
    return best


def available_worlds() -> List[str]:
    return sorted(_REGISTRY)


__all__ = ["RenderContext", "World", "get_world", "detect_world", "available_worlds"]
