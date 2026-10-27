# Voices, mastering and monetisation

**Read this if you plan to monetise a video.** This is the only part of the pipeline where the licence
of an *external model* can restrict what you do with the output.

Two separate things make narration sound like a voice-over rather than a robot:

1. **the engine** — a neural model with natural prosody, and
2. **the mastering chain** — the tone, dynamics and loudness work every broadcast voice track gets.

This repository does both. Neither is faked: every number below was measured on the sample renders
that ship with this branch, and the engine actually used for a track is written into
`report.json` (`narration_engine`) and `audio/<lang>.json`.

## The three engines

### 1 · Kokoro-82M — neural, the default English voice

- Engine: `onnxruntime` running **Kokoro-82M v1.0, q8**; weights are **Apache-2.0**.
- Why this and not Piper: every published Piper voice is Git-LFS backed on Hugging Face or GitHub, and
  the build environment for this repository can reach neither (see *Dead ends* below). A byte-identical
  copy of the Kokoro weights, its tokenizer and all 60 voice packs are redistributed inside the
  `expo-kokoro` npm package, and npm **is** reachable — so a genuinely good neural voice is available
  with no hosted inference API and no paid service.
- Download: one 89 MB npm tarball on first use, cached in `~/.cache/ckd/kokoro/`. The model is checked
  against its published SHA-256 (`fbae9257…1478`, 92 361 116 bytes) and **deleted rather than used** if
  the hash does not match.
- Speed: 24 kHz mono, roughly **1.5-2× faster than real time on 2 CPU cores**. A 60 s narration
  synthesises in about 30-40 s, once; the phrase cache makes re-renders free.
- Voices (`--voice-en kokoro:<name>`): `af_heart` (default — warm female), `am_michael` (documentary
  male), `am_fenrir`, `am_puck`, `af_bella`, `af_nicole`, `bf_emma`, `bm_george`.
- Pace: the narrator runs Kokoro at `speed = 0.78`, which measures **146-160 wpm** on the sample
  scripts. That is the range documentary narration actually sits in; 1.0 reads at ~190 wpm and sounds
  rushed.
- **Timings are approximate.** Kokoro publishes no word alignment. Word timings are distributed across
  each clause by syllable weight and every artifact labels them `estimated`. The espeak engine, which
  does report real word events, is labelled `espeak-events`. Burned captions and `.srt` files carry this
  distinction with them.

### 2 · Piper — neural, optional

- Engine: `piper-tts` (MIT). Voices download on first use into `~/.cache/ckd/voices/<voice_id>/`.
- Registered voices live in `ckd/voice/registry.py`: `en_US-lessac-medium`, `en_US-ryan-high`,
  `en_GB-alan-medium`, `ur_PK-fasih-medium`.
- **In this build environment Piper cannot be used**, because both mirrors are unreachable. On a normal
  machine or on Colab it works, and the narrator prefers it whenever a voice is already cached.
- Licence: Piper voices inherit the terms of their training corpus. Some are CC BY 4.0, some
  permissive, a few research-only. The model cards state which. This repository therefore does **not**
  claim the Piper voices are commercially cleared, and it does not ship the weights.

### 3 · espeak-ng — offline fallback, always available

- Licence: GPL-3.0 engine, loaded through `espeakng-loader`.
- Sounds robotic. It is the **Urdu** voice in these samples, because no neural Urdu TTS exists that
  this environment can download (Piper has no Urdu voice at all — see below).
- Kokoro needs *phonemes*, not text, and Kokoro's vocabulary is the espeak-ng IPA inventory, so the
  same espeak library is also used to phonemise English. That is the only thing Kokoro takes from it:
  no audio is ever taken from espeak for the English track.
- A fallback is never silent: the log and `report.json` say `engine: espeak` and why.

## Dead ends (recorded so nobody repeats them)

| route to a neural voice | result |
|---|---|
| Hugging Face `resolve/` URLs | connection refused/000 from this sandbox |
| `raw.githubusercontent.com`, `media.githubusercontent.com` | 000 |
| GitHub release assets / `objects.githubusercontent.com` | TLS closed (curl exit 35) |
| GitHub LFS batch API | 403 `Resource not accessible by integration` |
| `contents` API for any LFS-tracked `.onnx` | returns the 133-byte pointer, not the weights |
| `smseagle/piper-voices`, every LFS-backed Piper `.onnx` | same, all pointers |
| `piper-tts` / `sherpa-onnx` / `kokoro-onnx` Python wheels | library only, no model files |
| **npm registry** | **works** — this is how Kokoro is obtained |
| `codeload.github.com`, `pypi.org` | work |

There is **no Urdu Piper voice**: `rhasspy/piper/VOICES.md` and `piper1-gpl/docs/VOICES.md` list 35
languages and Urdu is not among them. Kokoro v1.0 has no Urdu either. A Kokoro-82M Urdu fine-tune
(`MuhammadNoman76/lughaat-tts`) exists on Hugging Face but cannot be downloaded here, so the Urdu track
in these samples uses espeak and says so. When a neural Urdu voice is reachable, it plugs into the same
`Narrator` interface.

## Mastering

`ckd/voice/mastering.py` runs once on the whole narration track, after synthesis and before muxing:

```
high-pass 88 Hz  →  -1.3 dB @ 215 Hz (boxiness)  →  +1.6 dB @ 3.1 kHz (presence)  →  de-esser
                 →  compressor 4:1, 3 ms attack, 120 ms release, +3 dB makeup
                 →  loudnorm  -15 LUFS / -1.5 dBTP  →  static trim if still off target
```

Why each stage is where it is:

- **Loudness** — YouTube normalises to about -14 LUFS, Spotify and most web video to -14, Apple Podcasts
  to -16, EBU R128 broadcast to -23. We target **-15 LUFS integrated, -1.5 dBTP**: loud enough that
  YouTube does not pull it down, quiet enough to leave AAC headroom. True peak matters more than sample
  peak because AAC decoding can push inter-sample peaks over full scale.
- **Order** — tone before dynamics (the compressor should not react to rumble), dynamics before
  loudness (a normaliser cannot create dynamics, only scale them), de-essing after the compressor
  (compression amplifies sibilance).
- **The compressor is the part that actually fixed the level.** The raw Kokoro and espeak tracks measure
  a peak-to-loudness ratio of 17-19 dB; broadcast dialogue sits near 14. No normaliser can make a track
  that peaky both loud and clean, so it is compressed first, then normalised.
- **Loudness is a target; true peak is a limit.** Where they conflict the limit wins, so anything within
  0.8 dB of target is reported as success, not as a failure.

Measured on the shipped samples (reproducible from `report.json`):

| track | engine | in | out | true peak |
|---|---|---|---|---|
| English | Kokoro `af_heart` | -20.5 LUFS | **-15.6 LUFS** | **-1.5 dBTP** |
| Urdu | espeak `ur` | -22.5 LUFS | **-15.5 LUFS** | **-1.5 dBTP** |

## What was wrong before

The previous build's narration was rejected as unlistenable ("tatatatttta"). Two separate defects:

1. **A buffer bug, not a voice problem.** The espeak callback was told the audio buffer held
   `n_samples * 2` samples. It held `n_samples`. Half of every audio chunk was therefore uninitialised
   heap memory — literal noise interleaved with the speech, 452 noise islands in a 110 s track. Fixed,
   with a regression test that fails if the audio is ever again longer than the speech events it
   contains.
2. **No mastering.** Each clause was peak-normalised on its own, which flattens a read into a
   machine-gun cadence, and nothing set the track's loudness. Per-clause normalisation is gone; the
   mastering stage owns level now.

The low-pass in the per-clause filter also moved from 6.8 kHz to 10.5 kHz: cutting at 6.8 kHz removes
much of the 4-9 kHz band that carries consonant cues, which is what makes synthetic speech unreadable
on a phone speaker.

## Practical guidance

| your use | recommendation |
|---|---|
| personal / educational uploads | anything here is fine |
| monetised channel | Kokoro weights are Apache-2.0 (commercial use allowed). For Piper voices check each model card; if unclear, train your own voice on audio you have rights to |
| client work | commission a voice, or use a voice with a written commercial licence; keep the licence file with the project |
| dubbing an existing video | do not clone a real person's voice — this repo contains no voice cloning |

If you redistribute a bundle that includes the espeak binaries, that bundle carries GPL obligations —
the ZIP built by `tools/make_zip.py` deliberately contains source and fonts only.

## What is stored where

```
~/.cache/ckd/kokoro/kokoro-quantized.onnx    Kokoro weights (92 MB, not in the repo)
~/.cache/ckd/kokoro/tokenizer.json           Kokoro phoneme vocabulary
~/.cache/ckd/kokoro/voices/<name>.bin        one 510x256 style pack per voice
~/.cache/ckd/voices/<voice_id>/              Piper models, if used
projects/<topic>/audio/<lang>.wav            narration (gitignored)
projects/<topic>/audio/<lang>.json           words/timings + engine + mastering numbers
projects/_cache/speech/<hash>.wav            per-clause phrase cache (gitignored)
```

Deleting `~/.cache/ckd` forces a re-download on the next run; deleting a project's `audio/` only forces
re-synthesis of that project. Neither action touches the repository.
