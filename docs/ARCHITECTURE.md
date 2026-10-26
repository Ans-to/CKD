# How it works

One sentence: a **topic** becomes a **story** (scenes with narration), the narration becomes a
**timeline** (word timings), and each scene is drawn **frame by frame** into its own MP4, which is then
concatenated and muxed with the audio.

```
topic ──► composer ──► story.json ──► review ──► narrator ──► audio + word timings
                                                                   │
                              ┌────────────────────────────────────┘
                              ▼
                    per scene: stage geometry + world + actions
                              │  frame t = f(background, props, character, type, captions)
                              ▼
                        scene_NN.mp4  (cached by hash)
                              │
                              ▼
                 concat ──► mux audio ──► verify ──► MP4 + SRT/ASS + report.json
```

## Layers

| module | responsibility | notable decisions |
|---|---|---|
| `ckd/content` | schema, options, knowledge packs, composer | a pack is data only; the composer only *selects* scenes and trims sentences — it never invents facts |
| `ckd/text` | fonts, HarfBuzz shaping, line breaking, drawing | Pillow's own layout has no Raqm here, so shaping is HarfBuzz + FreeType and glyphs are drawn by hand; RTL is laid out logically and reordered per line |
| `ckd/gfx` | painter, palette, character rig, primitives | drawing happens at 2× and is box-downsampled; gradients and the vignette are cached/composited once per frame, not per element |
| `ckd/scene` | stage geometry, timing, renderer, worlds | format differences live in `Stage`, not in `if vertical:` branches scattered through the worlds |
| `ckd/voice` | TTS engines, registry, narration | word timings come from the engine when available; otherwise they are interpolated and the track is labelled `proportional` |
| `ckd/render` | ffmpeg wrappers | encode per scene, concat with `-c copy`, mux with `-t`, always probe the result |
| `ckd/pipeline` | project state, orchestration, subtitles, LLM adapter | the project directory *is* the state; every stage is resumable |

## A frame, in order

1. `SceneRenderer.render(t)` builds a `RenderContext` (time, progress per action, palette, element list).
2. **World background** is drawn inside a camera transform (`pan`, `zoom`) so the layers parallax.
3. **World elements** are drawn in scene order (`sky`, `sun`, `house`, `panel`, …) — each element is a
   parametric drawing routine with its own entrance/loop progress.
4. **Character** is drawn outside the camera so it stays planted in frame; the mouth flaps while words
   are being spoken and it blinks on a fixed schedule.
5. **Headline** words stagger in; the block is auto-sized so it can never overflow its area.
6. **Captions** show the current cue with word-level highlighting; the pill is sized from the text and
   clamped into the safe area.
7. **Foreground** (dust, light shafts) and the scene's intro/outro tint.
8. The 2× buffer is box-downsampled, then a single output-resolution vignette is applied.

## Scene geometry is per format, not a crop

`Stage` owns `headline_area`, `caption_area`, `world_area`, `character_anchor`, type sizes and the
safe margins. Worlds ask the stage for slots (`stage_left`, `stack`, `roof`, …) and never hard-code
pixels, so 9:16 gets its own composition: headline across the top, props in a band, character in a
bottom corner, captions just above the safe margin.

## Caching and resume

| key | includes | consequence |
|---|---|---|
| `script_hash` | topic, languages, duration, notes, llm, palette, seed, script version | changing any of them regenerates `story.json`; an edited story is kept only while the request is unchanged |
| `narration_hash` | per-language text of every scene, voice settings | editing one scene re-synthesises that language only |
| `scene_hash` | narration hash, the scene's element dict, index, format, quality, fps, captions, character, seed, output size, `RENDER_VERSION` | only changed scenes are re-encoded |
| `script_hash` | topic, languages, duration, notes, palette, seed, `--script` path **and the script file's SHA-256**, `plan version` | editing the script re-imports it; an untouched script reuses its plan |
| speech cache | text, language, engine, voice, speed | repeated phrases are free |

Each scene writes `<name>.part.mp4` and is renamed to `<name>.mp4` only after `verify_video()` passes,
so a kill mid-encode cannot leave a "finished-looking" corrupt scene. On resume, a scene without a
valid sidecar (`<name>.json`) or with a mismatched hash is simply re-rendered.

## Adding a topic

1. Add a pack to `ckd/content/knowledge.py`: `id`, `world`, `palette`, `title{en,ur}`, scenes with
   `narration{en,ur}`, `headline{en,ur}`, `elements[]`, `actions[]`, `keywords{en,ur}`.
2. Use only element types the world declares in `element_types` (`solar`, `wifi`, `bridge`, `generic`).
3. Run `python -m ckd preview --topic "<your topic>" --langs en,ur --formats landscape,vertical` and
   look at the sheets.
4. Add the topic id to `tests/test_content.py` if it has a distinct structure worth locking down.

A new *world* is a bigger job: subclass `World` in `ckd/scene/worlds/`, implement `slots()`,
`background()`, `_el_*()` element drawers and (optionally) `foreground()`, then register it in
`get_world()`. `ckd/scene/worlds/business.py` is the reference for a *faceless* world: no
character, subject-centred slots, and a `lower_third` element that draws the script's own
on-screen text.

## An imported script

`--script` / `new_project_from_script()` replaces the composer with
`ckd/content/script_import.py`:

```
documentary markdown ──parse_script()──► ScriptScene[] (title, time codes, VO, direction, supers)
                     ──_shots_for()────► elements[] + timed actions ("shot3" at_frac 0.5)
                     ──import_script()─► Story (world="business", palette="documentary",
                                                 character.visible=False)
```

Each visual-direction bullet becomes one shot: `_classify()` maps it onto an element type by
keyword, `0:05–0:12` prefixes become the shot's `at_frac`, and the bullet text (with the camera
verb stripped) becomes the on-screen statement. Anything that asks for footage is recorded as a
warning and drawn as the nearest schematic — the importer never claims otherwise. The plan then
goes through exactly the same timing, narration, render and verify stages as a composed story.

## Deliberate non-goals

No diffusion models, no stock media, no 3D engine, no GPU kernels, no web service. If a feature needs
a paid API or a license that forbids monetisation, it does not belong here.
