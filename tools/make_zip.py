"""Build a portable ZIP of the project (source, fonts, docs, notebook, samples metadata).

    python tools/make_zip.py dist/ckd-video-studio.zip

Excluded on purpose: rendered projects, caches, voice models, .git, __pycache__ and the
sample MP4s (they are reproducible and multi-megabyte). Use --with-samples to include them.
"""
from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ipynb_checkpoints", "projects", "_cache",
             "models", ".venv", "dist"}
SKIP_SUFFIX = {".pyc", ".pyo", ".wav", ".part"}
MEDIA = {".mp4"}


def iter_files(with_samples: bool):
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix in SKIP_SUFFIX:
            continue
        if path.suffix in MEDIA and not with_samples:
            continue
        yield path, rel


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="dist/ckd-video-studio.zip")
    ap.add_argument("--with-samples", action="store_true", help="include the rendered sample MP4s")
    args = ap.parse_args(argv)
    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    files = list(iter_files(args.with_samples))
    manifest = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path, rel in files:
            zf.write(path, rel.as_posix())
            manifest.append(f"{sha256(path)}  {rel.as_posix()}")
        zf.writestr("MANIFEST.sha256", "\n".join(manifest) + "\n")
    size_mb = out.stat().st_size / 1e6
    print(f"{out}  ({len(files)} files, {size_mb:.1f} MB)")
    print("verify with: sha256sum -c MANIFEST.sha256   (inside the unzipped folder)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
