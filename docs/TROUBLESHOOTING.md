# Troubleshooting & resume

## First: is it stuck or just slow?

A 720p scene takes 85–135 s on 2 vCPU. Progress is printed twice per second
(`scene 2: frame 384/602`). If the frame counter has not moved in 2 minutes, something is wrong;
if it is moving, it is simply slow.

```bash
ls -la projects/<topic>/scenes/en_landscape/     # *.part.mp4 = currently encoding
```

## Resume after an interruption

The project directory is the state, so there is nothing to repair:

```bash
python -m ckd resume --project-dir projects/solar-energy
```

or, in the notebook, run cell 9. Every scene whose `scene_hash` still matches is reused. If a scene
was killed mid-encode you will see `NN_name.part.mp4` — that file is ignored and re-encoded; the real
`NN_name.mp4` only appears after verification passes.

Force a full re-render when you *want* one (e.g. after changing drawing code):

```bash
python -m ckd resume --project-dir projects/solar-energy --force scenes,video
```

## Common failures

| symptom | cause | fix |
|---|---|---|
| `ModuleNotFoundError: ckd` | running from the wrong directory | `cd` to the repo root, or set `PYTHONPATH=.` |
| `ffmpeg not found` | no system ffmpeg | `pip install imageio-ffmpeg` (bundles a static binary) |
| `FileNotFoundError: Missing bundled font(s)` | `assets/fonts` incomplete | re-clone; fonts are committed. `python tools/fetch_fonts.py` can re-download them |
| Urdu renders as boxes | wrong font path or an old `FontBook` cache | restart the kernel; confirm `check_environment()["fonts_ok"]` is all `True` |
| `neural voice unavailable … espeak` | Piper download blocked | expected in restricted networks; the video still has narration, `report.json` records `engine: espeak` |
| `RuntimeError: ffmpeg failed (1)` with `Assertion st failed` | fade start beyond clip length | already handled (`st=duration-fade`); if you see it, you are running an older copy |
| mux hangs | `apad` + `-shortest` with `-c:v copy` | already avoided; mux always uses `-t` and a timeout |
| `verify_video` reports `duration 0` | truncated encode | delete that scene file and resume; the partial is never used |
| Colab killed the session | free-tier limits | re-run cells 0–2, then cell 9. Do not use anti-idle scripts |
| `RuntimeError: Not enough disk space` | scene clips + models | delete `projects/*/scenes`, or switch to `quality="draft"` |
| Render is much slower than the table | thermal throttling or a shared host | nothing to fix; use `draft` for iteration, `standard` once |

## Verifying an output by hand

```bash
python - <<'PY'
from ckd.render.ffmpeg import probe, verify_video, loudness_stats
info = probe("projects/solar-energy/out/en_landscape.mp4")
print(info.to_dict())
ok, problems = verify_video("projects/solar-energy/out/en_landscape.mp4", require_audio=True,
                            expect_w=1280, expect_h=720, expect_fps=24, expect_duration=info.duration)
print("verified:", ok, problems)
print(loudness_stats("projects/solar-energy/out/en_landscape.mp4"))
PY
```

A visually useful check without a player:

```bash
python tools/contact_sheet.py projects/solar-energy/out/en_landscape.mp4 /tmp/sheet.png
```

## Editing the script safely

`story.json` is validated on load. If validation fails, `build_story()` raises and **nothing is
rendered** — the old file stays on disk. Typical rejections: an empty narration, a missing language,
a scene id duplicated, or fewer than three scenes.

To start over for one topic:

```bash
rm -rf projects/solar-energy    # script, audio, scenes, videos
```

## Reproducibility check

Two runs with the same options produce the same frames (the renderer has no unseeded randomness; the
seed is hashed into the scene path). Byte-identical MP4s are not guaranteed because x264 records a
timestamp, but the *picture* is deterministic — `tests/test_render.py` asserts this.

## Reporting a bug well

Include: the command, the last 30 lines of output, `report.json` (it contains environment, sizes,
engine names and warnings), and the contact sheet. Do **not** include tokens or the contents of
`~/.cache/ckd`.
