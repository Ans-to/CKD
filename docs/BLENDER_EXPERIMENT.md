# Blender video experiment

This optional GitHub Actions experiment renders a short stylized Nokia documentary opening. It is separate from the normal video-render pipeline.

## Current output: first 15 seconds

`scripts/blender/nokia_opening_15s.py` opens on a generic classic-style feature phone in a dark reveal, then transitions to one faceless silhouette beside an abstract Snake-era game graphic. The first two narration sentences are spoken in full; the remaining time holds on the visual with a restrained sound-design tail. There is exactly one human character.

The device is illustrative only: it is not an accurate Nokia handset, archival footage, or an engineering model. The video carries an on-screen disclosure. Narration is synthesized locally with the repository's Kokoro-82M ONNX voice (`am_michael`, Apache-2.0). The model is downloaded from the public npm package and run on the Actions CPU runner; no hosted AI-inference API is used. Caption cut points use Kokoro's estimated timings, not forced alignment. A small original two-note chime is synthesized locally, not copied from Nokia's ringtone. The preview is exactly 15 seconds, 720×404, 24 fps, with 360 frames (an even-height frame for H.264).

### Run it

1. Open the repository's **Actions** tab and choose **Blender 3D Video Experiment**.
2. Select **Run workflow**. The workflow always renders the 15-second opening.
3. Download the `nokia-opening-15s` artifact, or use `samples/nokia-opening-15s.mp4` on this session branch.

On this Arena branch, a path-scoped push trigger is also enabled because the GitHub connection cannot dispatch workflows through the API. A successful run commits the MP4 back to this branch and uploads a downloadable run artifact. GitHub Actions must be enabled for the repository.

## Runtime caching

GitHub-hosted runners are fresh virtual machines, so Blender is not permanently installed on a runner or in the repository. The workflow caches the Python virtual environment containing Blender's published `bpy` runtime, FFmpeg wheel, and local voice dependencies, plus Kokoro's model assets. The initial run seeds those caches; later runs restore them instead of reinstalling/downloading those components. The small OS shared libraries are still installed on each fresh runner. A self-hosted runner would be needed for a truly persistent system installation.

## Previous 4-second experiment

`scripts/blender/nokia_device_shift.py` and `samples/nokia-smartphone-shift-3d.mp4` are retained as the earlier silent keypad-versus-touchscreen schematic. That older video also uses generic illustrative geometry, not real product models.
