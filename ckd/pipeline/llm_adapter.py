"""Optional local LLM support (llama.cpp GGUF), fully offline at inference time.

This repository ships *no* model weights.  `options.llm` may point at a local
GGUF file; the loader below is intentionally strict so that a missing or broken
model produces a clear error instead of silently falling back.

If llama-cpp-python is unavailable in the runtime (it needs compilation on some
platforms, which is slow on free Colab CPU), keep `llm="none"` - the curated
knowledge packs and the generic scaffold do not need any model.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def load_llm_or_raise(spec: str) -> Any:
    path = Path(spec)
    if not path.exists():
        raise FileNotFoundError(f"LLM file not found: {spec}")
    try:
        from llama_cpp import Llama
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "llama-cpp-python is not installed. Install it with "
            "`pip install llama-cpp-python` (CPU wheel) to use a local GGUF model, "
            "or set llm='none' to use the curated packs / generic scaffold."
        ) from exc
    return Llama(model_path=str(path), n_ctx=4096, n_threads=2, verbose=False)
