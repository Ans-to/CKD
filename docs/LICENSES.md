# Licences

## This project's code

MIT. See `LICENSE`. You may use it commercially, modify it, and ship it, provided the copyright notice
is kept. There is no warranty.

## Bundled fonts (`assets/fonts/`)

All fonts are licensed under the **SIL Open Font License 1.1**, which permits commercial use,
modification and embedding. They are shipped unmodified.

| file | family | licence |
|---|---|---|
| `Inter-Variable.ttf` | Inter | SIL OFL 1.1 |
| `SpaceGrotesk-Variable.ttf` | Space Grotesk | SIL OFL 1.1 |
| `Silkscreen-Regular.ttf`, `Silkscreen-Bold.ttf` | Silkscreen | SIL OFL 1.1 |
| `NotoNastaliqUrdu-Variable.ttf` | Noto Nastaliq Urdu | SIL OFL 1.1 |
| `NotoNaskhArabic-Variable.ttf` | Noto Naskh Arabic | SIL OFL 1.1 |

The OFL requires that the fonts not be sold on their own and that modified versions not use the
reserved names. Bundling them inside a video renderer, or burning their glyphs into a video, is fine.

Full licence text: <https://openfontlicense.org/> and the `OFL.txt` files published alongside each
family in <https://github.com/google/fonts>. The original licence headers are retained in the font
binaries' name tables.

## Text-to-speech

**Important:** TTS voices are the one part of this pipeline whose licence can restrict monetisation.
See `VOICES.md` for the per-voice detail and the safe default.

| engine | licence | what it means for you |
|---|---|---|
| `espeak-ng` (offline fallback) | GPL-3.0 | used as an external library/binary via `espeakng-loader`; this repo does not vendor or link it into a distributed derivative. Audio you generate is your own output. |
| Piper (`piper-tts`) | MIT (the *engine*) | the engine is MIT, but each **voice model** carries its own dataset licence — check `VOICES.md` before monetising |
| Piper voice models | per-model (CC BY 4.0 / MIT / research-only depending on the corpus) | verify before publishing a monetised video, or use a voice you trained yourself |

If you need a voice with unambiguous commercial terms, record your own and feed it to Piper's training
scripts, or use `espeak` with the caveat above.

## Python dependencies

Installed from PyPI, not vendored: Pillow (HPND), NumPy (BSD-3), uharfbuzz (MIT), freetype-py (FTL/
GPLv2 dual), imageio-ffmpeg (BSD-2 + a separate FFmpeg build; FFmpeg is LGPL/GPL depending on the
build flags — the static binary shipped by `imageio-ffmpeg` is LGPL-compatible), python-bidi (LGPL),
piper-tts (MIT), espeakng-loader (GPL-3.0 wrapper data).

**Distribution note:** if you ship a *binary bundle* that includes FFmpeg or espeak-ng binaries, those
binaries keep their own licences (LGPL / GPL). Rendered videos are not affected by that; the software
distribution is. The portable ZIP produced by `tools/make_zip.py` contains source + fonts only.

## Content

The three knowledge packs are original prose written for this project. They contain no quoted text
and no statistics that need attribution. Illustrations are drawn from geometric primitives and carry
no third-party assets. Any topic you add is your responsibility.

`scripts/nokia.md` is a sample script supplied by the project's author for testing the
imported-script path; it is original prose about a public company's history, contains no quoted
material or images, and the video made from it uses no company logo, product photograph or
trademark rendering. Every phone drawn by `ckd/scene/worlds/business_props.py` is a generic
shape, never a specific model.

## Music

There is none. If you add a track, its licence is on you — the pipeline has no music stage.
