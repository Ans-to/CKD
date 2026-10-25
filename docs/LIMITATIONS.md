# Limitations — read this before publishing

This project is honest about what it is. Everything below is a real constraint of the current
implementation, not a to-do list dressed up as modesty.

## What it is

A **procedural motion-graphics explainer generator**: code draws the scenes, a script provides the
words, a local TTS voice reads them. It is designed for short, factual, structural explanations
(how a panel works, how Wi-Fi carries data, why a truss holds a load).

## What it is not

- **Not photorealistic.** Every frame is flat vector-style drawing. There is no 3D camera, no lighting
  model, no textures, no depth of field. "2.5D" here means parallax layers and camera pans, not ray
  tracing.
- **Not a generative video model.** No diffusion, no image synthesis, no stock footage. If you want a
  cinematic b-roll shot, this tool will never produce it.
- **Not a fact source.** The three curated packs contain descriptive, non-numeric explanations. The
  generic scaffold for unknown topics is a *structure*, not knowledge — it says so in its warnings and
  in `report.json`. **Check anything you publish.** No citations are generated because none were used.
- **Not a narrator with emotion.** Word timings are measured (engine events) or interpolated, and the
  fallback voice is `espeak`, which sounds robotic. The pipeline labels which one was used, per video.
- **Not a character animator.** One character rig, a handful of poses, a mouth flap keyed to speech and
  a blink timer. It cannot gesture at a specific labelled object or walk.
- **Not a diagram engine with real data.** The solar layer stack, the Wi-Fi wave and the truss are
  **labelled schematics** built from geometric primitives. They illustrate the idea; they are not
  accurate engineering models, and the truss member forces are illustrative arrows, not computed
  stresses. Do not use a frame from this tool as a technical drawing.
- **Not a long-form tool.** The curated packs are written for roughly 45–90 seconds. Asking for 5
  minutes produces a warning, not five minutes of content.

## Language specifics

- **Urdu** is shaped with HarfBuzz using Nastaliq (Noto Nastaliq Urdu) as the display face and Naskh
  as the body face. Line breaking works at word boundaries with bidi islands preserved. Known gaps:
  Nastaliq ascenders/descenders are tall, so line height is generous and the headline auto-shrinks;
  a very long single Urdu word could still exceed a narrow column on 9:16.
- **English** uses Inter / Space Grotesk / Silkscreen. Mixed-direction captions (English with an Urdu
  word) are laid out per line, but the *caption* is still one language per cue.
- Captions are a transcription of the narration, not a translation, and they are generated from the
  same text the TTS was given — so they match what is spoken, not necessarily grammatical ideals.

## Technical limits

- **CPU only.** A 720p 16:9 minute takes ~7–12 minutes on 2 vCPU. 1080p is roughly 2.5× slower.
- **Memory.** Peak RSS is ~600–900 MB per frame worker; the free Colab runtime (12 GB) is fine, but two
  renders in one session plus a mounted model can get tight.
- **Disk.** Scene clips dominate: 2–6 MB per scene per format per language. Delete `scenes/` once you
  have the final MP4 and the project will still resume (it will re-render on demand).
- **Cache invalidation is explicit.** If you change drawing code, bump `RENDER_VERSION` in
  `ckd/pipeline/run.py`, otherwise previously rendered scenes are reused with the old look.
- **Audio pipeline** muxes one narration track per language. There is no music, no ducking, no
  sound-effects layer, and no loudness normalisation beyond peak limiting.
- **Subtitles** are SRT + ASS generated from the same timings. They are *phrase-level accurate*
  (each cue matches the words spoken in that window), but on the espeak fallback the per-word timings
  are proportional, not measured — the report says `timing_kind: proportional` when that happens.

## Environment limits

- **Piper voices must be downloaded once.** In a network-restricted sandbox (or a locked-down Colab),
  the download can fail; the pipeline then uses the offline `espeak` voice and says so. It will not
  produce a silent video and pretend.
- **No Colab-specific tricks.** No tunnels, no keep-alive pings, no background services, no quota
  evasion. The notebook renders, then stops.
- **Windows/macOS** are untested. The code is pure Python + Pillow + ffmpeg and should work, but the
  tested target is Linux with Python 3.11.

## Licensing limits

- Code is MIT; the bundled fonts are SIL OFL 1.1 (commercial use allowed, attribution in
  `docs/LICENSES.md`).
- **Voices differ.** Piper voices have per-model licences (some datasets are research-only). Before
  monetising, read `docs/VOICES.md` and, if in doubt, use the `espeak` voice or record your own.
- The generated audio and video are yours to use, subject to the voice licence above.
