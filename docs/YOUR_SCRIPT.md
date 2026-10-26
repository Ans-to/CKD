# Render a script you already wrote

The topic→video path invents the words. This path does not: you bring a finished
documentary script, and the engine renders **your narration verbatim** as a faceless
business-documentary motion graphic in 16:9 and 9:16.

One thing to be clear about before you start: this is a **procedural motion-graphics
renderer**. It has no footage, no archive, no photographs and no image model. When your
visual direction says "archival-style paper mill in 19th-century Finland", the renderer
draws a **labelled schematic** of an industrial building — it does not pretend to show the
real mill, and it will never look like a photograph. That is a hard boundary of the
project, not a setting.

## The script format it reads

The parser is built for the timecoded documentary format most script writers produce:

```markdown
HOW NOKIA LOST ITS EMPIRE

**Target duration:** 7-9 minutes

SCENE 1 — THE HOOK

**Time:** 0:00–0:35

**[VOICEOVER]**

Imagine building a company so powerful that millions of people carry your product.

**[VISUAL DIRECTION]**

- 0:00–0:05: Extreme close-up of a classic mobile phone ringing in a dark room.
- 0:05–0:12: A world map illuminates as phone icons spread across continents.

**[ON-SCREEN TEXT]**

1865 — Nokia's beginnings

SCENE 2 — FROM A SMALL COMPANY TO A GLOBAL GIANT
...
OPTIONAL CALL TO ACTION
...
```

What is recognised:

| element | how it is used |
|---|---|
| first non-empty line | the video title (also the project name) |
| `SCENE n — TITLE` | one scene each; the title becomes the headline of that scene |
| `**Time:** 0:35–1:40` | the scene's declared window (used for planning, not to stretch narration) |
| `**[VOICEOVER]**` | spoken **verbatim**, sentence punctuation preserved |
| `**[VISUAL DIRECTION]**` bullets | one shot each; timecodes (`0:05–0:12:`) cut the shot at exactly that second |
| `**[ON-SCREEN TEXT]**` | writer's supers, drawn as a lower third on a scrim |
| `**[AUDIO]**` | kept as a production note in `story.json` (`notes`), never invented into sound |
| `CALL TO ACTION` | an extra scene with the CTA voice-over and a subscribe statement |
| `**Target duration:**` | read and reported; it is a **planning target**, not a promise |

Line-level details that matter:

- A visual-direction bullet keeps the *cut time* and loses the imperative verb
  ("Show an archival-style paper mill" → "archival-style paper mill"), so the on-screen
  statement is a label, not a command.
- A lower third is a **super, not a subtitle**: it comes in a couple of seconds into the
  scene, holds about ten seconds and leaves. It does not sit on the picture for the whole
  scene (which is what the first version did, covering every prop in a 54-second scene).
- Bullets are mapped to props by keyword: `phone` (keypad / touchscreen), `globe`,
  `chart`, `timeline`, `ecosystem`, `tower`, `factory`, `compare_phones`, or a
  `statement` card when nothing visual is named. Unknown subjects become statement cards —
  never invented diagrams.
- A requested chart with **no numbers in your script** renders as an empty chart frame
  captioned *"no figures in the script"*. The renderer never invents data points.

## Use it in the notebook (phone-friendly)

Add one cell to `notebooks/CKD_Video_Studio.ipynb`:

```python
from ckd.notebook_api import new_project_from_script, preview, render

# paste the whole script, or point at a file you uploaded to Colab
project = new_project_from_script(
    open("nokia.md").read(),          # or a path: "nokia.md"
    formats=("landscape", "vertical"),
    quality="standard",
    voice_en="kokoro:am_michael",
)
print(project.story().warnings)        # read these before you render
preview(project)                       # contact sheets in projects/<name>/preview/
result = render(project)               # resumable; scene clips are cached
```

The pasted text is written to `projects/<name>/script.md`, so the run is reproducible and
you can edit the script and re-render. Editing the file (or pasting different text) changes
the plan: the project's cache key includes the script's SHA-256, not just its filename.

## Use it in a terminal

```bash
python -m ckd preview --script scripts/nokia.md --formats landscape,vertical
python -m ckd render  --script scripts/nokia.md --formats landscape,vertical \
                      --quality standard --voice-en kokoro:am_michael
```

`--topic` is optional when `--script` is given; the project directory is named after the
script file (`scripts/nokia.md` → `projects/nokia/`).

## What it will warn you about (and why)

These warnings are generated, not decoration:

1. **"This is a procedural renderer, not a stock-footage editor…"** — always on for an
   imported script. Every bullet became a labelled motion graphic.
2. **"The script asked for footage/archival/photographic shots, which this renderer
   cannot produce: …"** — names the bullets that asked for footage.
3. **"script declares 8.0 min of running time; its voice-over is about 2.1 min…"** — your
   words are 338, and 8 minutes at 160 wpm needs ~1280 words.
4. **"the script is 3.8x shorter than its declared duration…"** — appears when the gap is
   large. Nothing is padded or invented to fill it: either write more script, or publish
   the video at its true length.
5. **"scene n: the script is English only, so 'ur' narration is missing…"** — the importer
   will not machine-translate. Ask for `--langs en` unless you have written the Urdu
   yourself. `validate_story` then refuses the run rather than shipping a silent track.

## Timing, honestly

- **Your timecodes win.** `0:05–0:12` cuts the shot at 5.0 s into the scene. Scenes
  without timecodes distribute their shots evenly over the scene's measured narration.
  Shots cross-fade in 0.45 s and out in 0.35 s, so a cut is a cut and not a double
  exposure of two props.
- **Scene length comes from the voice**, not from `**Time:**`. A scene declared 0:35–1:40
  whose words take 62 seconds is 62 seconds long. The render follows the words.
- **Word-level timing is estimated for Kokoro**, measured from TTS events for espeak.
  `report.json` labels which one produced each subtitle file. Captions are transcription,
  never translation.

## Re-composition rather than cropping

Both formats are drawn from the same story but laid out separately: the vertical stage has
its own prop band, its own statement dock (between the hero and the supers, so a caption
never sits on the phone), the supers dock above the caption band, and a different caption
wrap. A 16:9 render is **not** cropped to 9:16.

## Sample

`scripts/nokia.md` is a complete 5-scene documentary script shipped with the repo, and
`projects/nokia/` is the render made from it (`samples/` holds the same MP4s if you want to
watch before running anything). The narration is 202 s because the words take that long —
the script header says "7-9 minutes", and the run says so in the log rather than padding
the video.
