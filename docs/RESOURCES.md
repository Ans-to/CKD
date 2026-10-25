# Resource expectations

Measured on the machine this was developed on: **2 vCPU, 4 GB RAM, Python 3.11, ffmpeg 7.0.2,
no GPU**. A free Colab CPU runtime is comparable (2 vCPU, ~12 GB RAM), so these numbers are a fair
planning guide — expect ±30 % depending on host contention.

## Render time

Measured on the final 4-scene solar render (4 languages×formats, 60 s target), one worker:

| output | frames | per frame | wall time |
|---|---|---|---|
| 16:9 720p, 75 s (English) | 1 795 | ~116 ms | **3 min 30 s** |
| 16:9 720p, 92 s (Urdu) | 2 199 | ~112 ms | **4 min 05 s** |
| 9:16 720p, 75 s (English) | 1 795 | ~37 ms | **65 s** |
| 9:16 720p, 92 s (Urdu) | 2 199 | ~35 ms | **76 s** |
| 16:9 480p draft | — | roughly 0.4× the 720p cost | **~1 min 20 s** per 75 s |
| 16:9 1080p (`high`) | — | **not measured** — expect ~2.25× the 720p cost | **~8 min** per 75 s (estimate) |

**All four combinations** of one 4-scene plan (en/ur × 16:9/9:16) took **9 min 20 s** end to end on
2 vCPU, including concat, mux, probe and verify, and produced four verified MP4s.

Per-scene timings from the same run (720p 16:9): 46.6 s, 56.4 s, 61.5 s, 47.1 s for 398–516 frames.
Vertical costs ~0.3× of landscape because there are 2.4× fewer pixels per frame.

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
