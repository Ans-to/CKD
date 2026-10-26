# CKD — topic → finished explainer video, on a free Colab CPU

Give it a topic. It writes a bilingual script, narrates it, draws a scene-by-scene motion-graphics
explainer with one recurring character, and renders a verified MP4 — in **English or Urdu**, in
**16:9 or 9:16** — with no GPU, no paid API and **no hosted AI inference**.

```
"solar energy"  →  script + scene plan  →  your review  →  1280×720 MP4, H.264 + AAC
```

## What it actually does

| step | what happens | where |
|---|---|---|
| 1. script | a knowledge pack (or an optional local GGUF model) builds scenes with narration in every requested language | `ckd/content/` |
| 2. review | `story.json` is plain JSON you can edit; it is re-validated before rendering | `projects/<topic>/story.json` |
| 3. narration | local TTS (Piper if it can download, else the offline espeak voice) with measured word timings | `ckd/voice/` |
| 4. storyboard | real stills from the renderer, one contact sheet per language × format | `projects/<topic>/preview/` |
| 5. scene render | each scene is drawn frame by frame (Pillow + HarfBuzz + FreeType), encoded on its own, then cached | `ckd/scene/`, `ckd/render/` |
| 6. mux | scene clips are concatenated, audio is muxed, the result is probed and verified, SRT/ASS subtitles + `report.json` are written | `ckd/pipeline/` |

Everything is **procedural vector-ish drawing**: no stock footage, no per-scene generated images, one
sprite-rigged character reused everywhere.

## Try it

**In Colab (no PC needed):** open `notebooks/CKD_Video_Studio.ipynb`, run the cells, type a topic.
Start with `docs/GETTING_STARTED.md` — written for a phone browser.

**In a terminal:**

```bash
pip install -r requirements.txt
python -m ckd topics
python -m ckd script --topic "how wifi works" --langs en,ur --out story.json   # review this
python -m ckd preview --topic "how wifi works" --langs en --formats landscape  # look before rendering
python -m ckd render  --topic "solar energy" --langs en,ur --formats landscape,vertical --quality standard
```

Two finished samples, rendered by the code in this repo (not mockups):

| file | language / format | length | notes |
|---|---|---|---|
| `samples/solar-en-16x9.mp4` | English 16:9, 1280×720 | 110.1 s | + `story.json`, `report.json`, `srt`, frame sheet |
| `samples/solar-ur-9x16.mp4` | Urdu 9:16, 404×720 | 137.2 s | Nastaliq, RTL, Urdu numerals, `srt` |

Both use the same six-beat plan (hook → silicon cells → inverter → storage → efficiency → recap) and
were asked for at `--duration 90`. The offline espeak fallback in this container speaks at about half
the rate the planner assumes for the Piper neural voice, so the narration came out at 110 s / 137 s —
that is recorded in `story.warnings` and `report.json` rather than hidden, and it is why
`--duration` is a target, not a promise. Rendered here on 2 vCPU; see `docs/TEST_REPORT.md` for what
is and is not verified.

## Formats and languages, genuinely re-composed

| | 16:9 landscape | 9:16 vertical |
|---|---|---|
| headline | top-left, 60 % of the content width | full width, block under the top margin |
| world | one band between headline and captions, presenter at the frame edge | two zones: a wide prop band across the top **plus** the free quadrant beside the presenter |
| character | bottom corner, 56 % of frame height | bottom corner, 27.5 % |
| captions | bottom band, pill auto-fitted inside the safe area | band above the safe margin |

The prop slots are different geometry per format — a 9:16 frame is composed again
(two zones, different label placement), it is never a crop of the 16:9 frame.

Urdu is real Urdu script shaped with HarfBuzz (RTL, Nastaliq), with bidi islands such as
`(solar panel)` kept in Latin order and digits switched to `۱۲۳`. Nothing is mirrored or romanised.

## Guarantees the code enforces

- **One character.** `ckd/gfx/character.py` is the only human figure; scenes cannot add another.
- **No network during rendering.** Tests monkeypatch `socket.connect` and render a frame.
- **No silent fallbacks.** If the neural voice is unavailable, the log and `report.json` say
  `engine: espeak` and why. If a duration cannot be met, `story.warnings` says by how much.
- **Correct cache invalidation.** Scene keys include narration text, the scene's element dict, format,
  quality, fps, captions, character, seed and `RENDER_VERSION`; the script key includes the topic,
  languages, duration, notes, palette, seed and a script version. Change the drawing code and bump
  `RENDER_VERSION`, and stale clips are re-rendered instead of reused.
- **Corrupt output detection.** Every finished video is probed for stream count, codec, resolution,
  fps and duration; scene files that fail are re-rendered.

## Repository map

```
ckd/                 the engine (no notebook code inside it)
  content/           schema, options, knowledge packs, composer, optional local LLM
  text/              fonts, HarfBuzz shaping, RTL line breaking, text rendering
  gfx/               supersampled painter, palettes, character rig, primitives
  scene/             stage geometry, timing, renderer, worlds/{solar,wifi,bridge,generic}
  voice/             TTS engines, registry, narration with word timings
  render/            ffmpeg encode / concat / mux / probe / verify
  pipeline/          project state, run orchestration, subtitles, LLM adapter
  notebook_api.py    everything the Colab notebook calls
  cli.py             `python -m ckd ...`
notebooks/           the Colab notebook
assets/fonts/        bundled OFL fonts (see docs/LICENSES.md)
samples/             a real rendered video + its plan/report/contact sheet
configs/             example option files
tests/               pytest suite (install, content, text, render, pipeline)
docs/                getting started, private repo, troubleshooting, limits, licences
tools/               contact_sheet.py, make_zip.py, fetch_fonts.py
```

## Documentation

- `docs/GETTING_STARTED.md` — phone-friendly walkthrough (Colab, one topic, one video)
- `docs/PRIVATE_REPO.md` — using this from a private GitHub repo without leaking a token
- `docs/ARCHITECTURE.md` — how a frame is built, cache layout, where to add a topic
- `docs/TROUBLESHOOTING.md` — resume after a disconnect, common failures, fixes
- `docs/LIMITATIONS.md` — what this is not, and where it is approximate
- `docs/RESOURCES.md` — measured time/storage on a free CPU runtime
- `docs/TEST_REPORT.md` — what was tested, where, and what passed
- `docs/LICENSES.md` — code licence, font licences, voice licence caveats

## Status

The engine is complete and tested locally (CPU, Python 3.11, ffmpeg 7). The Colab notebook has
**not** been executed on Google Colab yet — see `docs/TEST_REPORT.md`, which separates local
evidence from what still needs a Colab run.

Code: MIT. Fonts: SIL OFL 1.1. TTS voices: see `docs/VOICES.md` before monetising.
