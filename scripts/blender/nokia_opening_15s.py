"""Blender-rendered, 15-second opening study for the Nokia documentary.

The 3D handset and human figure are generic illustrative shapes, not accurate
Nokia product models or archival footage. The human silhouette is the single
character used in this cut. The first two script sentences are narrated locally
with the repository's Kokoro ONNX voice; no hosted inference API is used.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FPS = 24
FRAMES = 15 * FPS
SR = 24_000
NARRATION = (
    "Imagine building a company so powerful that billions of people around the world "
    "carry its products in their pockets. "
    "A company whose name becomes almost synonymous with mobile phones."
)
SENTENCES = [
    "Imagine building a company so powerful that\nbillions of people around the world carry\nits products in their pockets.",
    "A company whose name becomes almost\nsynonymous with mobile phones.",
]

NAVY = (0.008, 0.014, 0.032, 1.0)
GRAPHITE = (0.055, 0.075, 0.105, 1.0)
TRIM = (0.24, 0.31, 0.40, 1.0)
GLASS = (0.008, 0.024, 0.032, 1.0)
PAPER = (0.88, 0.93, 0.97, 1.0)
MUTED = (0.48, 0.61, 0.72, 1.0)
GREEN = (0.25, 0.90, 0.51, 1.0)


def mat(name, color, *, metallic=0.0, roughness=0.5, emission=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = color
    m.use_nodes = True
    shader = m.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = color
    shader.inputs["Metallic"].default_value = metallic
    shader.inputs["Roughness"].default_value = roughness
    if emission:
        if "Emission Color" in shader.inputs:
            shader.inputs["Emission Color"].default_value = color
        elif "Emission" in shader.inputs:
            shader.inputs["Emission"].default_value = color
        if "Emission Strength" in shader.inputs:
            shader.inputs["Emission Strength"].default_value = emission
    return m


def box(name, location, dimensions, material, bevel=0.04):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    edge = obj.modifiers.new("Soft edges", "BEVEL")
    edge.width = min(bevel, min(dimensions) * 0.22)
    edge.segments = 3
    obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    obj.data.materials.append(material)
    return obj


def sphere(name, location, dimensions, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=1.0,
                                         location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return obj


def parent_keep_world(obj, parent):
    world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = world


def text_obj(body, name, material, *, size=0.16, location=(0.0, 0.0, 0.0),
             align="CENTER"):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.align_x = align
    curve.extrude = 0.0008
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.data.materials.append(material)
    return obj


def face_camera(light_or_camera, target):
    light_or_camera.rotation_euler = (
        Vector(target) - light_or_camera.location
    ).to_track_quat("-Z", "Y").to_euler()


def camera_overlay(obj, camera, x, y, z=-5.5):
    obj.parent = camera
    obj.location = (x, y, z)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    return obj


def panel(camera, name, x, y, width, height, material, z=-5.55):
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    obj = bpy.context.object
    obj.name = name
    obj.scale = (width, height, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return camera_overlay(obj, camera, x, y, z)


def build_phone():
    root = bpy.data.objects.new("Generic classic handset (illustrative)", None)
    bpy.context.collection.objects.link(root)
    root.location = (0.0, 0.0, -0.08)
    body_mat = mat("Graphite polymer", GRAPHITE, metallic=0.28, roughness=0.3)
    trim_mat = mat("Brushed trim", TRIM, metallic=0.55, roughness=0.28)
    screen_mat = mat("Dark display glass", GLASS, roughness=0.2)
    key_mat = mat("Soft silver keys", (0.48, 0.57, 0.65, 1.0), metallic=0.22)

    parts = [
        box("Old-style phone shell", (0.0, 0.0, 0.0), (0.96, 0.22, 2.24),
            body_mat, 0.105),
        box("Display bezel", (0.0, -0.125, 0.61), (0.64, 0.06, 0.62),
            trim_mat, 0.055),
        box("Small monochrome display", (0.0, -0.163, 0.61), (0.52, 0.018, 0.48),
            screen_mat, 0.025),
        box("Earpiece", (0.0, -0.14, 0.99), (0.29, 0.04, 0.045), trim_mat, 0.02),
        box("Navigation key", (0.0, -0.15, 0.08), (0.32, 0.075, 0.15), trim_mat, 0.05),
    ]
    for row in range(4):
        for col in range(3):
            x = (col - 1) * 0.23
            z = -0.22 - row * 0.22
            parts.append(box(f"Key {row + 1}-{col + 1}", (x, -0.156, z),
                             (0.15, 0.07, 0.13), key_mat, 0.035))
    for part in parts:
        parent_keep_world(part, root)
    return root


def build_single_character():
    """One faceless silhouette only; no crowd or second human figure."""
    root = bpy.data.objects.new("One generic user silhouette", None)
    bpy.context.collection.objects.link(root)
    root.location = (0.0, 0.2, -0.10)
    silhouette = mat("Single silhouette", (0.018, 0.028, 0.044, 1.0),
                     metallic=0.1, roughness=0.42)
    rim = mat("Cool silhouette detail", (0.15, 0.28, 0.38, 1.0),
              metallic=0.18, roughness=0.32)
    parts = [
        box("Figure torso", (1.75, 0.2, -0.28), (0.66, 0.36, 1.08), silhouette, 0.19),
        sphere("Figure head", (1.75, 0.20, 0.55), (0.28, 0.27, 0.34), silhouette),
        box("Figure legs", (1.75, 0.22, -0.92), (0.52, 0.30, 0.42), silhouette, 0.14),
        # One bent arm reaches toward the abstract game pixels; it does not hold
        # or reproduce a second handset.
        box("Reaching arm", (1.18, -0.02, 0.38), (0.78, 0.18, 0.15), silhouette, 0.07),
        sphere("Hand", (0.77, -0.08, 0.39), (0.12, 0.11, 0.10), rim),
        box("Shoulder rim", (1.47, -0.205, 0.37), (0.31, 0.035, 0.13), rim, 0.05),
    ]
    for part in parts:
        parent_keep_world(part, root)
        for frame, hidden in ((1, True), (192, True), (193, False)):
            part.hide_render = hidden
            part.keyframe_insert(data_path="hide_render", frame=frame)
    return root


def build_snake_display():
    """A free-floating game graphic, not a second handset or a product model."""
    root = bpy.data.objects.new("Abstract Snake-era game display", None)
    bpy.context.collection.objects.link(root)
    dark = mat("Game display", (0.006, 0.025, 0.026, 1.0), roughness=0.35)
    grid = mat("Dim game grid", (0.035, 0.15, 0.11, 1.0), emission=0.18)
    bright = mat("Snake pixels", GREEN, emission=1.1)
    rim = mat("Game display border", TRIM, metallic=0.25)
    parts = [box("Floating game panel", (0.18, -0.58, 0.80),
                 (1.28, 0.08, 0.94), dark, 0.065),
             box("Game panel rim", (0.18, -0.53, 0.80),
                 (1.34, 0.035, 1.00), rim, 0.07)]
    # Fine grid strokes and a bright, recognizable segmented path. This is a
    # stylized screen graphic, not a claim about a real Nokia game screen.
    for i in range(1, 5):
        x = 0.18 - 0.52 + i * 0.208
        z = 0.80 - 0.38 + i * 0.152
        parts.append(box(f"Grid column {i}", (x, -0.645, 0.80),
                         (0.008, 0.008, 0.76), grid, 0.002))
        parts.append(box(f"Grid row {i}", (0.18, -0.645, z),
                         (1.04, 0.008, 0.008), grid, 0.002))
    snake_coords = [(-0.24, 0.65), (-0.04, 0.65), (0.16, 0.65),
                    (0.16, 0.80), (0.16, 0.95)]
    for i, (x, z) in enumerate(snake_coords[:-1]):
        pixel = box(f"Snake segment {i + 1}", (x, -0.66, z),
                    (0.14, 0.022, 0.105), bright, 0.012)
        parts.append(pixel)
    head = box("Moving snake head",
               (snake_coords[-1][0], -0.66, snake_coords[-1][1]),
               (0.14, 0.025, 0.105), bright, 0.015)
    # The ordered path above is written out for the animated head positions.
    for part in parts:
        parent_keep_world(part, root)
    parent_keep_world(head, root)
    for frame, scale in ((1, 0.0), (187, 0.0), (207, 1.0), (FRAMES, 1.0)):
        root.scale = (scale, scale, scale)
        root.keyframe_insert(data_path="scale", frame=frame)
    for frame, x, z in ((207, 0.16, 0.95), (250, 0.16, 0.80),
                        (295, 0.16, 0.65), (330, -0.04, 0.65),
                        (FRAMES, -0.24, 0.65)):
        head.location.x = x
        head.location.z = z
        head.keyframe_insert(data_path="location", frame=frame)
    return root


def voice_and_sound(output_dir: Path):
    from ckd.voice.kokoro_engine import KokoroEngine

    # Kokoro runs locally on CPU. The npm-hosted package supplies open model
    # weights; inference itself is not a hosted API call.
    engine = KokoroEngine("am_michael", speed=1.0)
    result = engine.synthesize(NARRATION, "en")
    audio = np.asarray(result.audio, dtype=np.float32).reshape(-1)
    sentence_word_counts = [len(sentence.split()) for sentence in NARRATION.split(". ")]
    sentence_ends = []
    word_offset = 0
    for count in sentence_word_counts:
        word_offset += count
        sentence_ends.append(result.timings[min(word_offset - 1, len(result.timings) - 1)].end)
    voice_path = output_dir / "nokia-opening-voice.wav"
    with wave.open(str(voice_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes((np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes())

    # Original, synthesized two-note chime (not a recording of Nokia's ringtone)
    # plus a very soft low pulse near the end of this 15-second review cut.
    sfx_rate = 48_000
    duration = FRAMES / FPS
    time = np.arange(int(sfx_rate * duration), dtype=np.float64) / sfx_rate
    fx = np.zeros_like(time)
    for start, frequency in ((0.55, 740.0), (0.88, 880.0), (1.65, 740.0),
                             (1.98, 880.0), (3.15, 660.0), (3.48, 830.0),
                             (5.00, 740.0), (5.33, 880.0)):
        length = 0.28
        mask = (time >= start) & (time < start + length)
        local = time[mask] - start
        env = np.sin(np.pi * local / length) ** 1.5
        fx[mask] += 0.12 * env * (np.sin(2 * np.pi * frequency * local)
                                  + 0.22 * np.sin(4 * np.pi * frequency * local))
    pulse = (time >= 14.25) & (time < 15.0)
    local = time[pulse] - 14.25
    fx[pulse] += 0.035 * np.exp(-2.8 * local) * np.sin(2 * np.pi * 56.0 * local)
    sfx_path = output_dir / "nokia-opening-sound.wav"
    stereo = np.column_stack((fx, fx))
    with wave.open(str(sfx_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sfx_rate)
        wav.writeframes((np.clip(stereo, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return len(audio) / SR, sentence_ends, voice_path, sfx_path


def build_scene(output_dir: Path):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.materials):
        bpy.data.materials.remove(block)

    floor_mat = mat("Midnight studio", NAVY, roughness=0.78)
    box("Studio floor", (0.0, 0.0, -1.24), (200.0, 200.0, 0.1), floor_mat, 0.01)
    phone = build_phone()
    build_single_character()
    build_snake_display()

    world = bpy.data.worlds.new("Deep navy world")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = NAVY
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.12

    # A single key light slowly reveals the generic phone from near-black.
    light_data = bpy.data.lights.new("Phone reveal spotlight", "AREA")
    light_data.energy = 0.0
    light_data.color = (0.66, 0.79, 1.0)
    light_data.shape = "DISK"
    light_data.size = 3.2
    key_light = bpy.data.objects.new("Phone reveal spotlight", light_data)
    bpy.context.collection.objects.link(key_light)
    key_light.location = (-2.8, -4.2, 4.0)
    face_camera(key_light, (0.0, 0.0, 0.0))
    for frame, power in ((1, 0.0), (18, 0.0), (64, 620.0), (190, 620.0),
                         (220, 380.0), (FRAMES, 380.0)):
        light_data.energy = power
        light_data.keyframe_insert(data_path="energy", frame=frame)
    warm_data = bpy.data.lights.new("Soft warm edge", "AREA")
    warm_data.energy = 0.0
    warm_data.color = (1.0, 0.43, 0.18)
    warm_data.size = 3.0
    warm = bpy.data.objects.new("Soft warm edge", warm_data)
    bpy.context.collection.objects.link(warm)
    warm.location = (3.4, 0.8, 2.2)
    face_camera(warm, (0.0, 0.0, 0.0))
    for frame, power in ((1, 0.0), (190, 0.0), (226, 420.0), (FRAMES, 420.0)):
        warm_data.energy = power
        warm_data.keyframe_insert(data_path="energy", frame=frame)

    camera_data = bpy.data.cameras.new("Opening camera")
    camera = bpy.data.objects.new("Opening camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera_data.lens = 52
    camera_data.clip_start = 0.1
    camera_data.clip_end = 200.0
    bpy.context.scene.camera = camera
    for frame, location, target in (
        (1, (0.0, -7.8, 2.0), (0.0, 0.0, 0.12)),
        (180, (0.0, -7.8, 2.0), (0.0, 0.0, 0.12)),
        (225, (0.45, -10.0, 2.65), (0.65, 0.0, 0.18)),
        (FRAMES, (0.45, -10.0, 2.65), (0.65, 0.0, 0.18)),
    ):
        camera.location = location
        face_camera(camera, target)
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)

    # Synthesize the two complete opening sentences first; measured clip timing
    # keeps the sentence-level visual cut aligned with the narrated line.
    output_dir.mkdir(parents=True, exist_ok=True)
    voice_duration, sentence_ends, voice_path, sfx_path = voice_and_sound(output_dir)

    # Caption/title overlays live in camera space so they remain readable while
    # the camera pulls back. Sentences appear one at a time; copy is exact.
    white = mat("Warm white typography", PAPER, roughness=0.4, emission=0.55)
    muted = mat("Disclosure typography", MUTED, roughness=0.4, emission=0.3)
    black = mat("Caption scrim", (0.004, 0.009, 0.018, 1.0), roughness=0.9, emission=0.02)
    title = text_obj("NOKIA: THE RISE AND FALL", "Opening title", white, size=0.20)
    camera_overlay(title, camera, 0.0, 0.90, -5.8)
    disclosure = text_obj("ILLUSTRATIVE 3D - NOT ARCHIVAL\nFOOTAGE OR A REAL PRODUCT MODEL",
                          "Honesty disclosure", muted, size=0.06, align="LEFT")
    camera_overlay(disclosure, camera, -1.88, 0.66, -5.8)

    # Kokoro word timings are estimated, not forced-aligned; sentence ends are
    # taken from that estimate, and the video keeps the full second sentence.
    ends = [max(1, min(FRAMES, round(seconds * FPS))) for seconds in sentence_ends]
    starts = [1] + [end + 1 for end in ends[:-1]]
    for idx, (copy, start, end) in enumerate(zip(SENTENCES, starts, ends), start=1):
        panel_obj = panel(camera, f"Caption panel {idx}", 0.0, -0.95, 3.6, 0.66, black, z=-5.62)
        caption = text_obj(copy, f"Narration caption {idx}", white, size=0.112)
        camera_overlay(caption, camera, 0.0, -0.80, -5.55)
        for frame, scale in ((1, 0.0), (start, 0.0), (start + 3, 1.0),
                             (end - 3, 1.0), (end, 0.0), (FRAMES, 0.0)):
            caption.scale = (scale, scale, scale)
            caption.keyframe_insert(data_path="scale", frame=frame)
        for frame, scale in ((1, 0.0), (start, 0.0), (start + 3, 1.0),
                             (end - 3, 1.0), (end, 0.0), (FRAMES, 0.0)):
            panel_obj.scale = (scale, scale, 1.0)
            panel_obj.keyframe_insert(data_path="scale", frame=frame)

    # Fade the handset out once; the later game beat uses one silhouette and a
    # separate abstract display, never a second copy of the device.
    for frame, scale in ((1, 1.0), (175, 1.0), (202, 0.0), (FRAMES, 0.0)):
        phone.scale = (scale, scale, scale)
        phone.keyframe_insert(data_path="scale", frame=frame)

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 1
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 720
    scene.render.resolution_y = 404
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 8
    scene.render.filepath = str(output_dir / "frame_")
    scene.render.use_file_extension = True
    scene.frame_start = 1
    scene.frame_end = FRAMES
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    for obj in bpy.context.scene.objects:
        if obj.animation_data and obj.animation_data.action:
            for fcurve in obj.animation_data.action.fcurves:
                for point in fcurve.keyframe_points:
                    point.interpolation = "LINEAR"

    print(f"Kokoro voice duration: {voice_duration:.2f}s; output clip: 15.00s")
    bpy.ops.render.render(animation=True)
    print(f"Voice: {voice_path}; sound design: {sfx_path}")


def main():
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    output_dir = Path("output")
    for idx, arg in enumerate(args):
        if arg == "--output-dir" and idx + 1 < len(args):
            output_dir = Path(args[idx + 1])
            break
    build_scene(output_dir.resolve())


if __name__ == "__main__":
    main()
