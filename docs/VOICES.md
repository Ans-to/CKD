# Voices and monetisation

**Read this if you plan to monetise a video.** This is the only part of the pipeline where the licence
of an *external model* can restrict what you do with the output.

## The two engines

### 1 · Piper (neural, preferred)

- Engine: `piper-tts` — MIT.
- Models: downloaded on first use into `~/.cache/ckd/voices/<voice_id>/` (60–120 MB each).
- Voices registered in this repo (`ckd/voice/registry.py`):

| voice id | language | quality | licence status |
|---|---|---|---|
| `en_US-lessac-medium` | English (US) | medium | voice model on Hugging Face `rhasspy/piper-voices`; dataset behind it is derived from public-domain/CC audio — **verify the model card before monetising** |
| `en_US-ryan-high` | English (US) | high | same caveat |
| `en_GB-alan-medium` | English (GB) | medium | same caveat |
| `ur_PK-fasih-medium` | Urdu (PK) | medium | Fasih Urdu corpus; **verify the model card before monetising** |

`python -m ckd voices` prints the same table with a `license` field and whether the model is cached.

**Why so cautious?** Piper voices inherit the terms of the corpus they were trained on. Some corpora are
CC BY 4.0 (fine with attribution), some are permissively licensed, and a few are research-only. The
model cards on Hugging Face state which. This repository therefore does **not** claim the voices are
commercially cleared, and it does not ship the model weights (you download them yourself, which also
means the licence is between you and the model's author).

### 2 · espeak-ng (offline fallback, always available)

- Licence: GPL-3.0 (the engine). Loaded through `espeakng-loader` + `py-espeak-ng`.
- It sounds robotic. It is used when no Piper voice can be downloaded, and the log/report says so:
  `WARNING en: neural voice unavailable (…). Using the offline espeak development voice.`
- Output audio: your own generator output; the GPL applies to distributing the *binary*, not to a video
  you made with it. If you redistribute a bundle that includes the espeak binaries, that bundle carries
  GPL obligations — the ZIP built by `tools/make_zip.py` deliberately contains source and fonts only.

## Practical guidance

| your use | recommendation |
|---|---|
| personal / educational uploads | either engine is fine |
| monetised channel | check the Piper model card for each voice you keep; if unclear, train your own Piper voice on audio you have rights to, or use the espeak voice |
| client work | record/commission a voice, or use a voice with a written commercial licence; keep the licence file with the project |
| dubbing an existing video | do not clone a real person's voice — this repo does not include voice cloning |

## Language coverage

- **English:** `en_US-lessac-medium` (default), `en_US-ryan-high`, `en_GB-alan-medium`.
- **Urdu:** `ur_PK-fasih-medium`. Written Urdu is normalised before synthesis (numbers spelled out,
  `polish_speech()` trims DC/rumble and limits peaks) but the model's pronunciation of English loanwords
  is not perfect — check names in your own review pass.
- If a language has no registered voice, the pipeline falls back to espeak for that language only, and
  records `engine: espeak` in `report.json` for that track.

## What is stored where

```
~/.cache/ckd/voices/<voice_id>/<voice_id>.onnx      model (not in the repo)
~/.cache/ckd/voices/<voice_id>/<voice_id>.onnx.json metadata
projects/<topic>/audio/<lang>.wav                   narration (gitignored)
projects/<topic>/audio/<lang>.json                  words/timings + engine name
projects/_cache/speech/<hash>.wav                   phrase cache (gitignored)
```

Deleting `~/.cache/ckd` forces a re-download on the next run; deleting a project's `audio/` only forces
re-synthesis of that project. Neither action touches the repository.
