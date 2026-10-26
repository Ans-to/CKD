# Resource expectations

Measured on the machine this was developed on: **2 vCPU, 4 GB RAM, Python 3.11, ffmpeg 7.0.2,
no GPU**. A free Colab CPU runtime is comparable (2 vCPU, ~12 GB RAM), so these numbers are a fair
planning guide — expect ±30 % depending on host contention.

## Render time

Measured on the final six-beat solar render (`--duration 90`, `--quality standard` = 720p24),
one worker, from `report.json`:

| output | frames | per frame | scene render time | video length |
|---|---|---|---|---|
| 16:9 720p (English) | 1 527 | ~115 ms | **176 s** | 63.6 s |
| 16:9 720p (Urdu) | 1 805 | ~112 ms | **202 s** | 75.2 s |
| 9:16 720p (English) | 1 527 | ~40 ms | **61 s** | 63.6 s |
| 9:16 720p (Urdu) | 1 805 | ~40 ms | **72 s** | 75.2 s |
| 16:9 480p draft | — | roughly 0.4× the 720p cost | **~1 min** per 60 s | — |
| 16:9 1080p (`high`) | — | **not measured** — expect ~2.25× the 720p cost | **~7 min** per 60 s (estimate) | — |

**All four combinations** of the same six-beat plan took **13 min** end to end on 2 vCPU, including
narration, per-scene clips, concat, mux, probe and verify, and produced four verified MP4s.

Narration, measured separately: Kokoro-82M q8 runs at about **1.5× real time** on 2 cores — 63 s of
English speech synthesises in ~40 s, once, and is then cached clause by clause. espeak is ~50× real
time but is only used for Urdu here. The one-off Kokoro download is 89 MB from npm.

Vertical costs ~0.33× of landscape because there are 3.2× fewer pixels per frame. A scene is
rendered once per language×format: changing only the caption language does not re-render video.

A second run over an unchanged project is **seconds**: scene clips, narration and the story plan are
all reused (see `docs/TROUBLESHOOTING.md` for what forces a re-render).

## Disk

| item | size |
|---|---|
| repository (code + fonts) | ~14 MB |
| one 720p video, 85 s | 7–9 MB |
| one 720p video, 50 s | 4–6 MB |
| one scene clip, 720p | 1–3 MB |
| narration wav, 85 s | 3.5 MB |
| Piper voice model | 60–120 MB (in `~/.cache/ckd`, not the repo) |
| 4-scene project, both formats, both languages, 60 s | ~700 MB (see `du -sh projects/`) |

Draft quality uses roughly a quarter of the scene-cache space. Deleting `projects/<topic>/scenes/`
after a successful run frees most of it; the final MP4s stay.

## Memory

Peak RSS while rendering is **600–900 MB** (one frame at a time, 2× supersample buffer, glyph sprite
cache). The pipeline checks available RAM and free disk before it starts a scene and raises a readable
error instead of being OOM-killed.

## What is *not* needed

- No GPU. There is no CUDA path at all.
- No system ffmpeg (`imageio-ffmpeg` ships a static binary).
- No internet at render time — only for the optional first-time voice download.
- No paid account of any kind.

## Colab free-tier reality

- Sessions are recycled after idle periods and after roughly 90 minutes of use; long renders can be cut.
  Because every scene is cached on disk, resuming costs only the missing scenes.
- Colab disk is ephemeral (~70–100 GB). Mount Drive if you want projects to survive a runtime reset.
- This pipeline never tries to keep a session alive or evade limits. If a render is cut, resume it.
