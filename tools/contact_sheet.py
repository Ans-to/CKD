"""Contact sheet from a finished MP4 (visual QA without opening a video player).

    python tools/contact_sheet.py samples/solar-en-16x9.mp4 out.png --cols 3 --rows 3

Each tile is labelled with its timestamp so a reviewer can jump to a moment.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ckd.render.ffmpeg import ffmpeg_path, probe  # noqa: E402


def grab(video: Path, t: float, out: Path) -> Path:
    cmd = [ffmpeg_path(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
           "-frames:v", "1", "-y", str(out)]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def sheet(video: Path, out: Path, cols: int = 3, rows: int = 3, tile_w: int = 420) -> Path:
    info = probe(video)
    span = max(0.2, info.duration - 0.5)
    n = cols * rows
    times = [0.3 + span * (i / max(1, n - 1)) for i in range(n)]
    tmp = out.parent / "_frames"
    tmp.mkdir(exist_ok=True)
    th = int(tile_w * info.height / info.width)
    label_h = 26
    grid = Image.new("RGB", (cols * tile_w, rows * (th + label_h)), (8, 8, 10))
    draw = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype(str(ROOT / "assets/fonts/SpaceGrotesk-Variable.ttf"), 15)
    except Exception:  # pragma: no cover - font is optional here
        font = ImageFont.load_default()
    for i, t in enumerate(times):
        frame = grab(video, t, tmp / f"{i:02d}.png")
        img = Image.open(frame).convert("RGB").resize((tile_w - 6, th - 6), Image.LANCZOS)
        r, c = divmod(i, cols)
        x, y = c * tile_w, r * (th + label_h)
        grid.paste(img, (x + 3, y + 3))
        draw.text((x + 8, y + th + 3), f"{t:6.1f}s", fill=(235, 235, 245), font=font)
    grid.save(out)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out")
    ap.add_argument("--cols", type=int, default=3)
    ap.add_argument("--rows", type=int, default=3)
    ap.add_argument("--tile", type=int, default=420)
    args = ap.parse_args(argv)
    video = Path(args.video)
    if not video.exists():
        print(f"no such file: {video}")
        return 2
    out = sheet(video, Path(args.out), cols=args.cols, rows=args.rows, tile_w=args.tile)
    info = probe(video)
    print(f"{video} -> {out}")
    print(f"  {info.duration:.2f}s {info.width}x{info.height} {info.fps:.0f}fps "
          f"{info.video_codec}/{info.audio_codec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
