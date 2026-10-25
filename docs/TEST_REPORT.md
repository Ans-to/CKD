# Test report

**Scope of this report**

Everything below was executed **inside this container** (Linux, 2 vCPU, ~3 GB RAM,
Python 3.11, no GPU, no Colab). Nothing here is evidence of a Colab run: the
notebook has **not** been executed on Colab yet, because the sandbox has no
Colab runtime. Where a result depends on the local environment (voice engine,
font availability) it is marked as such.

Reproduce everything with:

```bash
python -m pytest tests -q          # unit + integration tests
python tools/contact_sheet.py samples/solar-en-16x9.mp4 out.png
```

## 1. Automated tests

| Suite | Covers |
| --- | --- |
| `tests/test_install.py` | package imports and version, bundled fonts, ffmpeg on PATH, CLI help, environment report, requirements match imports |
| `tests/test_content.py` | topic-only call gives a bilingual plan, Urdu is real Urdu script, solar/wifi/bridge plans are structurally different, unknown topic warns + falls back, schema rejects empty text, duration fitting, notes attached |
| `tests/test_text_and_layout.py` | Urdu wraps instead of overflowing, bidi island order, alignment origin matches reported width, 9:16 is re-composed not cropped, Urdu digits, headline/caption inside the safe area, glyph raster size per style |
| `tests/test_render.py` | frame geometry and determinism, one character rig across scenes, CPU-only + no network, ffmpeg probe/verify, worlds differ structurally |
| `tests/test_pipeline.py` | render cache + resume, report contents, compile-only mode |
| `tests/test_security.py` | no credentials committed, no hosted AI inference endpoints, download hosts limited to model weights, media/models git-ignored |

```
$ PYTHONPATH=. python3 -m pytest tests -q
33 passed in 26.2s
```

The `test_glyph_raster_size_follows_style_when_one_renderer_mixes_sizes` case is a
regression test for a real bug found during visual QA: a single `TextRenderer`
draws kickers, labels, captions and headlines at different sizes on faces that are
shared per font. The old cache claimed "size already applied" per `(font, px)`, so
after any other size was used the glyph *bitmaps* were rasterized at the stale
pixel size while layout advances stayed correct — captions came out as tiny letters
with huge gaps. Fixed by tracking the current char size per FreeType face.

## 2. Render integrity — all four language/format combinations

Each row is a file in `samples/` or `projects/solar-energy/out/`, produced by the v11 render.

| output | duration | size | streams | `verify_video()` |
|---|---|---|---|---|
| English 16:9 | 74.79 s | 1280×720 @ 24 | h264 / aac | `(True, [])` |
| English 9:16 | 74.79 s | 404×720 @ 24 | h264 / aac | `(True, [])` |
| Urdu 16:9 | 91.63 s | 1280×720 @ 24 | h264 / aac | `(True, [])` |
| Urdu 9:16 | 91.63 s | 404×720 @ 24 | h264 / aac | `(True, [])` |

Loudness on the English 16:9 file: mean −20.4 dB, peak −0.3 dB (no clipping). `verify_video()` does a
full-file decode (catches truncation/corruption) plus size/fps/codec/audio-stream checks.

Subtitles: `samples/*.srt`, one cue per sentence, word times taken from the TTS event stream
(`timing_kind: espeak-events` in this environment).

**Duration honesty.** The four videos were requested with `--duration 60` but came out at 74.8 s and
91.6 s, because the offline espeak voice speaks at ~1.3 words/s while the planner's table assumes a
Piper voice at ~2.2–2.6 words/s. The pipeline now measures the narration after synthesis and writes
the mismatch into `story.warnings` and `report.json` (see "narration measured 74.8s against a 60s
target"). This is a known, disclosed gap, not a silent miss.

## 3. Visual QA

Frames were extracted with ffmpeg and inspected by eye, not just asserted:

- 4x4 contact sheet per render (`tools/contact_sheet.py`), reviewed scene by scene.
- Caption band, headline band and prop band cropped and checked separately.
- Vertical video checked at 406x720; landscape at 1280x720.

Defects found and fixed in this loop (all post-hoc, i.e. found by looking at frames):

1. Every frame was composited with a flat yellow wash: `ImageDraw.Draw(img, "RGBA")`
   does not alpha-blend. Rewritten to draw translucent shapes on an offscreen layer
   and `alpha_composite` it; `Painter.result()` now flattens any remaining partial
   alpha onto the background so a frame can never be returned with holes.
2. Caption text drifted to the right and clipped at the frame edge: layout centred
   words inside `max_width` while callers positioned the block by `layout.width`.
   Layout now re-origins each line on the widest line.
3. Caption pills ran edge-to-edge on 9:16 Urdu: the pill now reserves its own
   padding before auto-sizing, then clamps inside the safe area.
4. Glyph raster-size cache bug described in §1 (affected every render that used
   more than one font size, i.e. all of them).
5. Inverter scene had the presenter standing on top of the house and the panel
   bleeding past the left edge under the push-in camera; the scene now uses
   `char_left` + panel/inverter only, and the panel's skew is reserved inside its
   slot.
6. Every scene ended with a fade to a pale sky wash — a visible yellow flash at
   each cut. The outro now fades to the dark ink colour.
7. On 9:16 the "PART n / m" chip was drawn on the headline's first line. It now
   sits just above the caption band on that format.
8. Urdu headlines were laid out like English ones (block on the left). They are now
   mirrored to the right edge, with the chip moved to the top-left.
9. The 9:16 recap put the house's gable inside the battery above it; the house slot
   was lowered and shortened for that format.

Known cosmetic weaknesses that remain (documented, not hidden):

- The presenter's pointing arm can pass in front of a prop edge; there is no
  per-frame occlusion solving, only slot-level placement.
- Curated packs are written for ~45-90 s. Asking for a much shorter target drops
  whole sentences/scenes and records that in `story.warnings`; it cannot invent a
  15 s edit of a 46 s pack.
- Dense recap scenes read busier than single-idea scenes; the pack keeps at most
  three props per frame for that reason.

## 4. Bilingual / dual-format

| Combo | Rendered here | Notes |
| --- | --- | --- |
| English 16:9 | yes | `samples/solar-en-16x9.mp4` (74.8 s, verified) |
| English 9:16 | yes | `projects/solar-energy/out/en_vertical.mp4` (404×720) |
| Urdu 16:9 | yes | `projects/solar-energy/out/ur_landscape.mp4` (Nastaliq, RTL, Urdu digits) |
| Urdu 9:16 | yes | `samples/solar-ur-9x16.mp4` (91.6 s, verified) |

Layouts are genuinely re-composed, not cropped: 16:9 puts the headline top-left (top-right in Urdu),
the world in a central band and the presenter at a bottom corner; 9:16 centres a full-width headline,
widens the world band and shrinks the presenter to 27.5 % of the frame height.

Text is shaped with HarfBuzz and rasterised with FreeType. Pillow in this
container has **no Raqm**, so bidi reordering is implemented in
`ckd/text/shaping.py` (per-token direction classes, neutral resolution, visual
reordering) rather than delegated to Pillow.

## 5. Cost / privacy

- No hosted AI inference is called at any point: the curated generator, the
  rules-based LLM stand-in and the deterministic renderer all run locally.
- `tests/test_security.py` fails the build if an external inference endpoint or a
  committed credential appears.
- TTS: Piper (neural, offline) is the intended default; in this container the
  Piper voice could not be downloaded, so the renders in `samples/` use the local
  **espeak** fallback. That is stated in each `report.json` (`engine: espeak`,
  `timing_kind: espeak-events`). Word timings are approximate for both engines.

## 6. Not yet verified

- **Colab**: notebook cells have never been executed on Colab. The notebook is
  JSON-valid and the API it calls is exercised by the tests locally, but first-run
  Colab behaviour (package install, Piper download, Drive mount) is unverified.
- **Piper voices**: blocked by the sandbox network; only espeak has actually
  produced audio here.
- **Upscaled 1080p**: `quality=high` is implemented but only 720p/480p were
  rendered and timed (720p ≈ 60-100 s per scene on 2 vCPU).
