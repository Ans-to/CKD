# Getting started — from a phone, in a browser, for free

You need: a Google account, a browser, and about 20 minutes (most of it waiting for a render).
No terminal, no Python install, no GPU, no credit card.

---

## 1 · Open the notebook in Colab

1. Put this repository on GitHub (public or private — see `PRIVATE_REPO.md` if it is private).
2. Go to <https://colab.research.google.com> → **File ▸ Open notebook ▸ GitHub**.
3. Paste the repository URL, pick `notebooks/CKD_Video_Studio.ipynb`.
4. **Runtime ▸ Change runtime type ▸ Hardware accelerator: None** (CPU is correct here — a GPU
   gives this pipeline nothing and burns your quota faster).

## 2 · Run the first three cells

Tap the ▶ button on each cell in order:

| cell | what it does | how long |
|---|---|---|
| **0 · Get the code** | clones the repo into `/content/CKD` (paste your URL into `REPO_URL` first) | ~10 s |
| **1 · Install** | `pip install -r requirements.txt` | 1–2 min |
| **2 · Health check** | prints CPU, RAM, disk, ffmpeg, fonts, voices | ~5 s |

The health check ends with `✅ environment looks good` or a list of `problems`. If it lists a missing
font, the clone did not finish — re-run cell 0.

## 3 · Pick your topic

In cell 3 you only need to change one line:

```python
TOPIC = "solar energy"
LANGUAGES = ["en"]            # or ["ur"], or ["en", "ur"]
FORMATS = ["landscape"]       # "landscape" = 16:9, "vertical" = 9:16
DURATION = 45
QUALITY = "standard"          # "draft" for a quick look, "standard" for 720p
```

Any topic words work. Three topics have hand-written, reviewed scenes: **solar energy**,
**how wifi works**, **bridge engineering**. Anything else gets a generic scaffold, and the report
labels it as such — it is honest about being generic rather than pretending otherwise.

## 4 · Read the script (do not skip this)

Cell 4 prints every scene: headline, narration in each language, and which visual elements it uses.
Cell 4b shows the same thing as JSON and lets you rewrite it. If you change the JSON, run the next
cell to validate it; if it is rejected, nothing is written and you keep the old plan.

## 5 · Look at the storyboard

Cell 5 renders a handful of real stills per scene into contact sheets and shows them inline.
This is where you catch a wrong label or a cramped layout **before** spending 8 minutes on a render.

## 6 · Render

Cell 6 renders scene by scene, muxes the audio, verifies the file and prints a table:

```
video  path                                    seconds  size      fps  verified
en_landscape  /content/projects/.../en_landscape.mp4  83.29  1280x720  24.0  True
```

Cell 7 plays the MP4 inline. Cell 8 downloads the video(s) and a ZIP of the whole project.

## 7 · If Colab disconnects

Free runtimes are recycled after idle time or ~90 minutes of use. Everything is checkpointed:

1. Re-run cells **0, 1, 2** (code, install, health check).
2. Run **cell 9**. It lists the projects on disk, reopens the newest one and calls `render()`
   again — finished scenes are reused, only the missing ones are drawn.

If you want projects to survive a full runtime reset, mount Drive in a new cell and point
`projects_dir` at it:

```python
from google.colab import drive
drive.mount("/content/drive")
# then in cell 3:
# projects_dir="/content/drive/MyDrive/ckd-projects", root="/content/drive/MyDrive"
```

## 8 · Typical timings on a free Colab CPU (2 vCPU)

| output | draft (480p) | standard (720p) |
|---|---|---|
| 16:9, 50 s | ~2 min | ~7 min |
| 16:9, 85 s | ~3.5 min | ~12 min |
| 9:16, 50 s | ~40 s | ~2 min |
| both languages, both formats, 50 s | ~5 min | ~18 min |

Disk: about 15 MB per finished 720p video plus scene cache (2–6 MB per scene). A 4-scene project
with both formats and both languages peaks around **900 MB**, dominated by scene clips you can delete
once the final MP4 exists.

## 9 · What costs money

Nothing in this repository. Colab's free tier is free; there are no paid APIs, no hosted model calls,
no subscriptions. The only optional download is a TTS voice model (60–120 MB) which Colab fetches once
and caches under `~/.cache/ckd`.

## 10 · Before you publish a video

- Read `docs/LIMITATIONS.md` — e.g. the schematics are labelled illustrations, not engineering data.
- Check `docs/VOICES.md` — the narration voice's licence matters if you monetise.
- Keep the `report.json`: it records which engine narrated, what warnings were raised, and the exact
  render settings, which is what you need if a viewer asks how it was made.
