# Nokia documentary opening — 15-second vector preview

The current opening is rendered with CKD's accepted **premium-flat / vector-rig** style. The earlier Blender blockout was explicitly rejected and is no longer used for this deliverable.

## Current output

- **Video:** [`samples/nokia-opening-15s.mp4`](../samples/nokia-opening-15s.mp4)
- **GitHub download:** [Download the MP4](https://github.com/Ans-to/CKD/raw/refs/heads/arena/dc7dfd05-ckd/samples/nokia-opening-15s.mp4)
- **Length/format:** 15 seconds, 1280×720, 24 fps, 360 frames, H.264 + AAC
- **Narration:** the previously approved local Kokoro voice track is retained; only the rejected visuals were rebuilt.

The cut changes exactly at the sentence boundary: first, one generic classic handset animates against the documentary skyline; then the phone graphic clears and the single vector-rig character enters beside the sentence-derived typographic beat **“NOKIA ≈ MOBILE PHONES.”** Captions reset at the same cut. No phone drawable is repeated in the second shot.

The visible disclosure reads **“STYLIZED GRAPHIC · NOT ARCHIVAL FOOTAGE.”** The handset is generic illustrative geometry, not an accurate Nokia product model, archival footage, or a technical schematic.

## Render it

The local renderer is `scripts/nokia_opening_vector_15s.py`. It uses the repository's bundled fonts, the existing scene renderer, and the audio already embedded in the source MP4. It does not call a hosted AI service or require Blender.

```bash
python -m venv .venv
. .venv/bin/activate
pip install pillow numpy uharfbuzz freetype-py imageio-ffmpeg python-bidi espeakng-loader
python scripts/nokia_opening_vector_15s.py
```

The **Nokia Documentary Opening (Vector)** GitHub Actions workflow caches its Python render dependencies, validates the 15-second/720p/24-fps/360-frame output, uploads an artifact, and commits a changed MP4 to this session branch. The committed sample is also directly downloadable using the link above.

## Earlier Blender studies

`scripts/blender/nokia_opening_15s.py` and `samples/nokia-smartphone-shift-3d.mp4` remain as historical experiments only. They are not the current opening, and the rejected Blender-rendered `nokia-opening-15s.mp4` has been replaced by the vector preview.
