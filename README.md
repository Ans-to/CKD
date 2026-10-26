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
| 3. narration | local neural TTS (Kokoro-82M for English, espeak for Urdu here) + a broadcast mastering chain to -15 LUFS / -1.5 dBTP | `ckd/voice/` |
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

| file | language / format | length | audio | notes |
|---|---|---|---|---|
| `samples/solar-en-16x9.mp4` | English 16:9, 1280×720 | 63.6 s | Kokoro `af_heart`, -15.7 LUFS / -1.4 dBTP | + `story.json`, `report.json`, `srt`, frame sheet |
| `samples/solar-en-9x16.mp4` | English 9:16, 404×720 | 63.6 s | same master | re-composed vertical layout, `srt`, frame sheet |
| `samples/solar-ur-16x9.mp4` | Urdu 16:9, 1280×720 | 75.2 s | espeak (no neural Urdu voice), -15.6 LUFS / -1.3 dBTP | Nastaliq, RTL, Urdu numerals, `srt`, frame sheet |
| `samples/solar-ur-9x16.mp4` | Urdu 9:16, 404×720 | 75.2 s | same master | Nastaliq, RTL, Urdu numerals, `srt`, frame sheet |

`scripts/nokia.md` is rendered into `samples/nokia-en-16x9.mp4` and `samples/nokia-en-9x16.mp4`
(202 s each, Kokoro `am_michael`, 720×1280 portrait) — the same words, drawn as a faceless business
documentary. The script declares "7-9 minutes"; the voice takes 2.1 minutes for its 338 words and the
run says so instead of padding it.

Two 28 s audio-only previews are in the same folder (`voice-preview-en.mp3`, `voice-preview-ur.mp3`)
if you want to judge the narration without downloading a video.

Download any of them straight from GitHub ("Download raw file" on the file page, or the `raw.githubusercontent.com`
URL) — they are ordinary MP4s with H.264 video and AAC audio, no special player needed.

All four use the same six-beat plan (hook → silicon cells → inverter → storage → efficiency → recap) and
were asked for at `--duration 90`; with narration at a real speaking pace (146 wpm English, 148 wpm
Urdu) they land at 63.6 s and 75.2 s. `--duration 45` gives a plan that fits a 30-60 s slot.

**About the narration.** English is a neural voice (Kokoro-82M, Apache-2.0) running on CPU. Urdu is
espeak-ng, because no Urdu neural voice exists in any mirror this build environment can reach — that is
a documented limitation, not an accident, and `report.json` says so per track. Every track is mastered
to -15 LUFS / -1.5 dBTP before muxing. See `docs/VOICES.md` for the engines, licences and the list of
download routes that do not work here.

Rendered here on 2 vCPU; see `docs/TEST_REPORT.md` for what is and is not verified.

## Have a script already? Render that instead

Bring a fully written documentary script (hook / middle / recap scenes, timecoded visual
direction, on-screen text, optional CTA) and the engine will speak **your words verbatim**
and draw a faceless business documentary from them:

```bash
python -m ckd preview --script scripts/nokia.md --formats landscape,vertical
python -m ckd render  --script scripts/nokia.md --formats landscape,vertical \
                      --quality standard --voice-en kokoro:am_michael
```

```python
from ckd.notebook_api import new_project_from_script, preview, render

project = new_project_from_script(open("nokia.md").read())   # or a path
print(project.story().warnings)      # read these first
preview(project)
render(project)
```

The platform is a notebook, so the pasted-script cell in
`notebooks/CKD_Video_Studio.ipynb` (cell **3b**) is the same path without a terminal: paste into
`SCRIPT`, run, then review/preview/render/download with the existing cells.

`--topic` is not needed when `--script` supplies the words. Each `SCENE n — TITLE` becomes
a scene, each `**[VISUAL DIRECTION]**` bullet becomes a shot (cut on *your* timecode),
`**[ON-SCREEN TEXT]**` becomes a lower third, and the `CALL TO ACTION` block becomes a CTA
scene. See `docs/YOUR_SCRIPT.md` for the format in detail.

Two things it will not do, and says so in the log and in `story.json`:

- **It draws no footage.** Visual direction is mapped onto labelled motion graphics of the
  thing named (phone, factory, globe, chart, ecosystem). Nothing imitates an archival photo
  or a real product shot.
- **It does not pad.** Your declared `Target duration` is read and reported; if the
  voice-over is 2.1 min for a declared 8 min, the video is 2.1 min and the warning tells you
  how many words the duration would need. Charts requested without numbers render an empty
  frame captioned "no figures in the script" — no data is invented.

## Formats and languages, genuinely re-composed

| | 16:9 landscape | 9:16 vertical |
|---|---|---|
| headline | top-left, 60 % of the content width | full width, block under the top margin |
| world | one band between headline and captions, presenter at the frame edge | two zones: a wide prop band across the top **plus** the free quadrant beside the presenter |
| character | bottom corner, 56 % of frame height | bottom corner, 27.5 % |
| captions | bottom band, pill auto-fitted inside the safe area | band above the safe margin |
| size at `--quality standard` | 1280×720 | 720×1280 (same short side, not a third of it) |

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
  scene/             stage geometry, timing, renderer, worlds/{solar,wifi,bridge,business,generic}
  voice/             TTS engines, registry, narration with word timings
  render/            ffmpeg encode / concat / mux / probe / verify
  pipeline/          project state, run orchestration, subtitles, LLM adapter
  notebook_api.py    everything the Colab notebook calls
  cli.py             `python -m ckd ...`
notebooks/           the Colab notebook
assets/fonts/        bundled OFL fonts (see docs/LICENSES.md)
scripts/             scripts/nokia.md — a full documentary script used as an example
samples/             a real rendered video + its plan/report/contact sheet
configs/             example option files
tests/               pytest suite (install, content, text, render, pipeline)
docs/                getting started, private repo, troubleshooting, limits, licences
tools/               contact_sheet.py, make_zip.py, fetch_fonts.py
```

## Documentation

- `docs/GETTING_STARTED.md` — phone-friendly walkthrough (Colab, one topic, one video)
- `docs/YOUR_SCRIPT.md` — render a documentary script you wrote (format, warnings, limits)
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
