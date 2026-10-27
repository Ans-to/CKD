# Blender 3D video experiment

This is an optional, manual GitHub Actions experiment for a short procedural 3D motion graphic. It does not change the normal video-render pipeline.

## What it renders

`scripts/blender/nokia_device_shift.py` creates two generic, stylised device forms—a keypad handset and a touchscreen handset—on a dark studio set, then renders a slow camera drift and a conceptual connector between them. On-screen text calls the scene an illustrative schematic and explicitly says it is not a real product model. It is **not** an accurate Nokia handset, a historical reconstruction, archival footage, or an engineering diagram. The output is silent; it is a visual/CI proof of concept, not a finished narrated documentary.

The render uses Blender 4.5's Python runtime (`bpy`) with Cycles on CPU at 960×540, 24 fps, and 2 samples per frame. FFmpeg is bundled through its Python wheel for encoding. The default 96 frames produce a 4-second proof of concept. The optional `frames` input is limited by the script to 24–240 frames.

## Run it

1. Open the repository’s **Actions** tab and choose **Blender 3D Video Experiment**.
2. Select **Run workflow**. Leave frames at `192` for the default 8-second test.
3. When the job finishes, download the `nokia-smartphone-shift-3d` artifact from that run. It contains `nokia-smartphone-shift-3d.mp4`.

The workflow is manually dispatchable from the repository's **Actions** tab once it is on the default branch. In this Arena experiment branch only, a path-scoped push trigger is also enabled so the render can run even when the GitHub connection cannot dispatch workflows through the API; its output MP4 is committed back to this branch and uploaded as a run artifact. Other branches and ordinary source changes do not trigger renders. GitHub Actions must be enabled for the repository.

For a local render, install Blender and FFmpeg, then run the Blender script in background mode and encode the generated `frame_####.png` sequence with FFmpeg as the workflow does.
