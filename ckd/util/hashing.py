"""Stable content hashing used by the resumable pipeline cache."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def stable_json(obj: Any) -> str:
    """Serialize deterministically (sorted keys, no whitespace noise)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_default)


def _default(o: Any) -> Any:
    if isinstance(o, Path):
        return str(o)
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if isinstance(o, set):
        return sorted(o)
    return repr(o)


def hash_json(obj: Any, *, prefix: str = "") -> str:
    h = hashlib.sha256()
    if prefix:
        h.update(prefix.encode("utf-8"))
        h.update(b"\x00")
    h.update(stable_json(obj).encode("utf-8"))
    return h.hexdigest()


def hash_file(path: str | Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short_hash(value: str, n: int = 10) -> str:
    return value[:n]
