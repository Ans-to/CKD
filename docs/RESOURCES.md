# Resource expectations

Measured on the machine this was developed on: **2 vCPU, 4 GB RAM, Python 3.11, ffmpeg 7.0.2,
no GPU**. A free Colab CPU runtime is comparable (2 vCPU, ~12 GB RAM), so these numbers are a fair
planning guide — expect ±30 % depending on host contention.

## Render time

| output | frames | per frame | wall time |
|---|---|---|---|
| 16:9 720p, one 50 s video | ~1 200 | 260–400 ms | **6–8 min** |
| 16:9 720p, one 85 s video | ~2 000 | 260–400 ms | **9–13 min** |
| 9:16 720p, one 50 s video | ~1 200 | 65–140 ms | **1.5–3 min** |
| 16:9 480p (draft), one 50 s video | ~1 200 | 110–180 ms | **2–3 min** |
| 16:9 1080p (high), one 50 s video | ~1 200 | 550–800 ms | **11–16 min** |

Add ~10 s for narration (espeak) or ~30–60 s for a first Piper download, and ~5–15 s for
concat + mux + verify.

**All four combinations** (en/ur × 16:9/9:16) for a 45 s script at `standard`: roughly **18–25 min**
and **4 video files**.

Costs that go away on a second run: unchanged scenes are reused (a cached re-render of the same project
takes 20–60 s), narration is cached per phrase, and the font/shaper caches are warm.

## Disk

| item | size |
|---|---|
| repository (code + fonts) | ~14 MB |
| one 720p video, 85 s | 7–9 MB |
| one 720p video, 50 s | 4–6 MB |
| one scene clip, 720p | 1–3 MB |
| narration wav, 85 s | 3.5 MB |
| Piper voice model | 60–120 MB (in `~/.cache/ckd`, not the repo) |
| 4-scene project, both formats, both languages, 45 s | ~500–900 MB peak |

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
