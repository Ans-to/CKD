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
| `tests/test_voice_quality.py` | the espeak buffer bug cannot come back (audio length vs reported word events), the per-clause filter keeps 6 kHz consonants, mastering lands within 0.6 LUFS of -15 at <= -1.2 dBTP, and a too-short track is refused rather than silently passed through |

```
$ PYTHONPATH=. python3 -m pytest tests -q
49 passed in 43.2s
```

Four of those are new for the imported-script path (`tests/test_documentary_import.py`):
a 9:16 render keeps the short side (`aspect_size("vertical", 720) == (720, 1280)` rather than
`404×720`), vertical statements dock between the hero and the supers instead of behind the
phone, the lower third never reaches the caption band in either format, and consecutive
shots stop ghosting over each other (the shot fade is now in seconds, not in fractions of an
action). `tests/test_voice_quality.py` also gained three cases: narration is imported
verbatim, a requested chart without numbers never grows a series, and shot cuts land on the
script's own timecodes.

The `test_glyph_raster_size_follows_style_when_one_renderer_mixes_sizes` case is a
regression test for a real bug found during visual QA: a single `TextRenderer`
draws kickers, labels, captions and headlines at different sizes on faces that are
shared per font. The old cache claimed "size already applied" per `(font, px)`, so
after any other size was used the glyph *bitmaps* were rasterized at the stale
pixel size while layout advances stayed correct — captions came out as tiny letters
with huge gaps. Fixed by tracking the current char size per FreeType face.

## 2. Render integrity — all four language/format combinations

One topic ("solar energy"), one six-beat plan, rendered with
`--duration 90 --quality standard` (720p, 24 fps). Each row is the file now in `samples/`
or `projects/solar-energy/out/`.

| output | duration | size | streams | loudness of the *finished file* | `verify_video()` |
|---|---|---|---|---|---|
| English 16:9 | 63.63 s | 1280×720 @ 24 | h264 / aac | -15.7 LUFS / -1.4 dBTP | `(True, [])` |
| English 9:16 | 63.63 s | 404×720 @ 24 | h264 / aac | -15.7 LUFS / -1.4 dBTP | `(True, [])` |
| Urdu 16:9 | 75.21 s | 1280×720 @ 24 | h264 / aac | -15.6 LUFS / -1.3 dBTP | `(True, [])` |
| Urdu 9:16 | 75.21 s | 404×720 @ 24 | h264 / aac | -15.6 LUFS / -1.3 dBTP | `(True, [])` |

The loudness column is measured on the muxed MP4, not on the intermediate WAV: that distinction caught
a real bug. ffmpeg's default mono→stereo upmix scales by 1/√2, so every finished video was 3 dB
quieter than the track it was built from (-18.7 LUFS instead of -15.6). The mux now uses an explicit
`pan=stereo|c0=c0|c1=c0`, and `test_mux_keeps_loudness` fails if the level ever moves again.

`verify_video()` does a full-file decode (catches truncation/corruption) plus size/fps/codec/audio
stream checks. The English 16:9 file decodes to a peak of −0.37 dBFS with no sample at full scale
(no clipping), mean −17.6 dB.

Subtitles: `samples/*.srt`, one cue per sentence, word times taken from the TTS event stream
(`timing_kind: espeak-events` in this environment), plus `.ass` alongside the project files.

**Duration honesty.** The plan was requested at `--duration 90` and came out at 63.6 s (English) and
75.2 s (Urdu), because narration now speaks at a real pace (146 / 148 wpm) instead of the broken
~78 wpm of the previous build. `--duration 45` produces a plan that fits a 30-60 s slot. The pipeline
records the measured duration against the target in `story.warnings` and `report.json` rather than
hiding the difference.

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
10. Urdu headlines (9:16 especially) ran past the top edge of the frame: Nastaliq
    ink is much taller than its line box, so a block that "fits" by advance still
    overflows. Auto-sizing now reserves a 0.80 height / 0.92 width margin for
    Arabic-script text.

11. `Painter.paste_sprite` applied the camera's translation but not its **scale**, so the
    static sky plate slid ~20 px sideways at the end of a `push_in` and left a flat dark band
    down the frame edge. The plate is now drawn outside the camera transform (it is a
    full-bleed backdrop, not a parallax layer), and `paste_sprite` honours zoom for the props
    that *are* inside it.
12. The sky plate only covered `horizon + 260` px, so the bottom of a 720 px frame was
    never painted; a 9:16 frame showed a hard horizontal seam where the plate ended. The
    plate now covers the full stage height and starts with an opaque base coat (gradient and
    polygon joins leave hairline gaps that a static plate turns into black seams).
13. `Pen.rect` / `Pen.ellipse` inverted their own box when a detail's inset was larger than
    its size — which happens constantly once props are scaled down for 9:16 — and PIL raised
    `ValueError: y1 must be greater than or equal to y0`, killing the vertical render. Boxes
    are now sorted and sub-pixel shapes are skipped.
14. Every prop name the knowledge base uses (`panel`, `inverter`, `battery`, `array`, `meter`,
    `bar`) was missing from `SolarWorld.slots()`, so they all fell back to the same centred
    fallback box: in 9:16 the battery, inverter and grid pylon were drawn on top of each
    other. Slots are now disjoint per format, and a wire that names a prop resolves to that
    prop's real box.
15. The 9:16 light shaft became a hard vertical seam in the narrow frame; it is now 16:9 only.
16. The exploded cell stack ran off the left edge under the push-in camera (a 7.5 % zoom is
    enough to crop a plate that starts at the slot edge). The stack insets by the safe margin
    and clamps its plate width and label column to the frame.
17. The presenter's arms were one tapered capsule each with a shaded stripe down them: at
    frame scale they read as noodles with blobs at the cuff. The arm is now sleeve → elbow →
    tapered forearm → wrist → palm, with the T-shirt sleeve covering the whole upper arm; the
    poses were retuned so `present` opens both hands, `think` puts the elbow up with the hand
    near the chin, and `shrug` lifts the palms instead of the shoulders.
18. Headline and caption type carried a 3 px dark outline that read as a sticker; replaced
    with a soft contact shadow, which lets the type sit on the artwork (premium-flat look).
19. In 9:16 the hook's "solar panel" label sat under the presenter's head, the array field
    was cropped by the right edge, and the recap house overflowed the safe area. All slots
    are now clamped inside the safe area in both formats.

Known cosmetic weaknesses that remain (documented, not hidden):

- The art is deliberately **flat and graphic** (soft gradients, single-tone props,
  cast shadows, rim light). It is not illustration-grade: no textures, no painted
  lighting, no character animation beyond pose + mouth + blink + bounce.
- Prop labels can still sit close to a prop edge in dense recap frames; placement is
  slot-level, with no per-frame collision solving.
- The presenter's arm can pass in front of a prop edge; there is no per-frame
  occlusion solving, only slot-level placement.
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

## 7. Art-system rebuild (v13–v17)

The first visual system (a pixel-art presenter on flat single-fill props) was rejected as not good
enough, so the art layer was rebuilt rather than patched:

- **Presenter** (`ckd/gfx/character.py`) is a smooth vector rig: tapered torso, separate legs with a
  real gap, rolled cuffs, boots, a parametric hair dome, sleeve → elbow → tapered forearm → wrist →
  palm arms, a rim light restricted to the key-light side, and a shared palette with the type.
  Poses are parameters (`present`, `explain`, `point_left/right`, `think`, `celebrate`, `shrug`,
  `idle`) — still exactly one character, still no per-scene generation.
- **Props** (`ckd/scene/worlds/solar_props.py`) are cached sprites built from gradients, cast
  shadows and specular streaks: house with a lit roof slope and amber windows, solar panel with cell
  gutters and glass, inverter with a live AC trace, battery with a fill gauge, grid pylon, cable,
  and the exploded cell slabs.
- **Type** lost its outline for a soft contact shadow, and the caption pill gained a hairline top
  light, so headline and captions read as graphic elements, not stickers.
- **Layout** is now slot-driven with disjoint regions per format (see the defect list above); 9:16 is
  a two-zone composition, not a crop.

Render cost of the rebuild is unchanged (≈110 ms/frame at 720p16:9, ≈36 ms at 404×720), because
props are cached sprites and only the animated parts are drawn live.

## 8. Voice rebuild (v18–v19)

The v17 narration was rejected: *"cant understand a single word there is tatatatttta in it"*. The
complaint was correct, and the cause was not the accent or the pitch — it was a memory bug plus a
missing mastering stage.

### 8.1 The "tatatatttta" was uninitialised memory

`ckd/voice/espeak.py` passed `shape=(n_samples * 2,)` to `np.ctypeslib.as_array` when reading the audio
callback buffer. espeak-ng packs **`n_samples`** 16-bit samples there. Half of every chunk was therefore
whatever happened to be in the heap after the buffer — 452 bursts of noise across a 110 s track, one
between roughly every word.

Evidence, measured on the same sentence before and after:

| | before | after |
|---|---|---|
| declared samples per callback | 1 324 | 1 324 |
| samples actually read | 2 648 | 1 324 |
| audio for one 13-word sentence | 5.37 s | 5.63 s (of 139 wpm speech, not noise) |
| measured F0 | 276 Hz (noise-contaminated) | 98 Hz |
| energy above 6 kHz | 13 % | 4 % |

The regression test (`test_espeak_buffer_length_matches_declared_events`) fails if the synthesised audio
is ever materially longer than the word events it contains — the exact signature of reading past the
buffer.

### 8.2 The engine itself was also wrong for the job

espeak is a formant synthesiser. Even with clean buffers it sounds like a machine, and the user asked
for a professional voice-over. English now uses **Kokoro-82M** (Apache-2.0, q8 ONNX, CPU). It is
downloaded once from npm (89 MB, SHA-256 verified) because every Piper voice — the usual choice — is
LFS-backed and unreachable from this environment; the full list of dead ends is in `docs/VOICES.md`.

| kpi | espeak (v17) | Kokoro (v19) |
|---|---|---|
| words per minute | 78 (1.3 w/s) | **146** |
| noise islands per 100 s of audio | 411 | 0 by construction; 252 syllable peaks in 60 s is normal speech |
| F0 | 276 Hz, formant buzz | 202 Hz, natural female |
| word timings | measured (`espeak-events`) | **estimated**, and labelled so everywhere |

Urdu still uses espeak, because no Urdu neural voice exists in any mirror this environment can reach.
That is stated in the README, `docs/VOICES.md` and `report.json` (`narration_engine: espeak`).

### 8.3 Mastering

Every track now goes through `ckd/voice/mastering.py` before muxing:

```
high-pass 88 Hz → -1.3 dB @215 Hz → +1.6 dB @3.1 kHz → de-esser
               → compressor 4:1 / 3 ms attack / 120 ms release / +3 dB makeup
               → loudnorm -15 LUFS / -1.5 dBTP → static trim, bounded by true peak
```

| track | in | out | true peak | warning |
|---|---|---|---|---|
| English (Kokoro) | -20.5 LUFS | **-15.6 LUFS** | **-1.5 dBTP** | none |
| Urdu (espeak) | -22.5 LUFS | **-15.5 LUFS** | **-1.5 dBTP** | none |

Rejected attempts, recorded so they are not retried: two-pass *linear* loudnorm undershoots by 1-2 dB
(linear mode refuses the +8 dB the track needs because it would break the peak ceiling, then silently
falls back); gain plus plain peak normalisation is not loudness (-22.1 LUFS); and a simple 2.5:1
compressor leaves a 17 dB crest factor that no normaliser can fix (lands at -16.2 LUFS with the peak
already at the ceiling). The working combination lowers the crest factor to ~16 dB *first*.

### 8.4 What is still not good

- Urdu is intelligible and correctly shaped but still a formant voice. It is the honest fallback, not
  a claim of equal quality.
- Kokoro's word timings are estimated. Captions can lag a syllable at clause boundaries; the files say
  `estimated` rather than pretending otherwise.
- Both sample videos are longer than the 30-60 s default because the six-beat plan was requested at
  `--duration 90`; `--duration 45` produces a plan that fits.

## 9. Imported documentary script — end-to-end

A second, independent end-to-end run: the script in `scripts/nokia.md` (written in the timecoded
documentary format: 4 scenes + a CTA, 338 spoken words, a declared "7-9 minutes") rendered through
the normal CLI, not through a test harness.

```
$ PYTHONPATH=. python3 -m ckd render --script scripts/nokia.md --langs en \
      --formats landscape,vertical --quality standard --voice-en kokoro:am_michael
project: projects/nokia
  OK en_landscape: projects/nokia/out/en_landscape.mp4 (202.5s 1280x720 24.0fps)
  OK en_vertical:  projects/nokia/out/en_vertical.mp4  (202.5s 720x1280 24.0fps)
```

| output | duration | size | narration | warnings |
|---|---|---|---|---|
| `scripts/nokia.md` → 16:9 | 202.5 s | 1280×720 | Kokoro `am_michael`, 0.9× rate, `estimated` word timings | 4 (see below) |
| `scripts/nokia.md` → 9:16 | 202.5 s | 720×1280 | same master | same |

The four warnings the run printed are the point of the feature, not noise:

1. procedural renderer, not a stock-footage editor (always, for an imported script);
2. two visual-direction bullets asked for footage/archival material and cannot be produced;
3. the script declares 8.0 min, its words are 2.1 min at 160 wpm;
4. 8 minutes would need ~1280 words and this script has 338 — nothing was invented to fill it.

### 9.1 Defects found by watching this render

1. **Shots ghosted over each other.** The shot fade was `progress × 1.6` of the action, so a
   10-second shot took six seconds to fade in. Three phone shots in a row were all half-visible
   and the frame read as a double exposure. Fades are now 0.45 s in / 0.35 s out, and an element
   whose action id is unknown is drawn rather than silently dropped.
2. **Statements were invisible in 9:16.** Importer statements use the `wide` slot, which in portrait
   is centred on the hero, so "Development of early mobile communication equipment" was drawn
   *behind* the phone. Vertical statements now use a `statement_low` slot between the hero and the
   supers, and carry a panel instead of bare text.
3. **The 9:16 render was 404×720.** `aspect_size()` treated the requested height as the frame height
   for both formats, so a portrait render was a third of the area of its landscape twin. Height is now
   the *short* side: 720p is 1280×720 and 720×1280.
4. **Vertical lower thirds dropped a line and landed on the caption band.** The panel now keeps all
   three of the writer's supers, grows upwards from the caption band, and is drawn on a solid panel
   (0.93) over a soft halo — at 0.66, lit factory windows read straight through the text.
5. **The "0:05-0:12" timecodes were parsed but not used for cuts.** Shot actions carried no timing,
   so cuts fell on sentence boundaries; pinned `at_frac` actions were also ignored whenever the
   narration had no clauses. Both are fixed and covered by tests.
6. **`--duration` fought the script.** An imported script has its own length, so the run now plans
   with `duration = 0` (no target) and the narration warning about a mismatch cannot fire. `--topic`
   is optional when `--script` is given.
7. **The writer's supers sat on the scene for its whole length.** The lower third was pinned open
   from 12 % to the end, so every frame of a 54-second scene carried the same three lines on top of
   the factory, the tower and the phone. A super now comes in at 12 %, holds about ten seconds
   (sized against the scene's *spoken* length, not its declared timecode window) and leaves.
8. **Editing the script did not change the plan.** `script_hash()` hashed the script *path*, so
   saving new words to `scripts/nokia.md` and re-running reused the previous `story.json` — the
   render silently ignored the edit. The hash now includes the file's SHA-256, and the plan version
   was bumped so existing projects re-import once.
9. **A pasted script was lost on reopen.** `new_project_from_script()` wrote `script.md` *after*
   `project.json` had been saved, so `open_project()` saw no script path and composed a generic
   scaffold instead — a different video with a different script.
