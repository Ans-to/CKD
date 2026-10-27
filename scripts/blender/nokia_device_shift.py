"""Render a short, explicitly illustrative 3D device-comparison graphic.

This is not a Nokia product replica, historical reconstruction, or product-accurate
engineering model. It is a procedural visual experiment for the documentary renderer.
Run with Blender in background mode, then encode the PNG sequence with FFmpeg.
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


NAVY = (0.012, 0.022, 0.050, 1.0)
INK = (0.025, 0.040, 0.075, 1.0)
GRAPHITE = (0.075, 0.095, 0.13, 1.0)
SCREEN = (0.018, 0.035, 0.062, 1.0)
GOLD = (1.0, 0.48, 0.12, 1.0)
CYAN = (0.22, 0.72, 0.88, 1.0)
PAPER = (0.86, 0.91, 0.96, 1.0)
MUTED = (0.43, 0.54, 0.67, 1.0)


def arguments() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--frames", type=int, default=96)
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args(argv)
    if not 24 <= args.frames <= 240:
        parser.error("frames must be between 24 and 240 (1–10 seconds at 24 fps)")
    if args.fps != 24:
        parser.error("this experiment is configured for 24 fps")
    return args


def material(name: str, color: tuple, *, metallic: float = 0.0,
             roughness: float = 0.5, emission: float = 0.0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    if emission:
        # Principled's emission inputs changed labels across Blender releases.
        if "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = color
        elif "Emission" in bsdf.inputs:
            bsdf.inputs["Emission"].default_value = color
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emission
    return mat


def rounded_box(name: str, location: tuple, scale: tuple, mat,
                bevel: float = 0.04):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel_mod = obj.modifiers.new("Soft manufactured edges", "BEVEL")
    bevel_mod.width = min(bevel, min(scale) * 0.22)
    bevel_mod.segments = 3
    normal_mod = obj.modifiers.new("Weighted corner normals", "WEIGHTED_NORMAL")
    obj.data.materials.append(mat)
    return obj


def parent_to(obj, root):
    world = obj.matrix_world.copy()
    obj.parent = root
    obj.matrix_world = world


def make_phone_root(name: str, center_x: float):
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.location = (center_x, 0.0, -0.15)
    return root


def make_keypad_phone(center_x: float, body_mat, trim_mat, screen_mat,
                      key_mats):
    root = make_phone_root("Generic keypad device", center_x)
    body = rounded_box("Keypad device shell", (center_x, 0.0, 0.02),
                       (0.88, 0.20, 2.18), body_mat, 0.10)
    parent_to(body, root)
    face_y = -0.112

    parts = [
        rounded_box("Small display bezel", (center_x, face_y, 0.62),
                    (0.62, 0.045, 0.60), trim_mat, 0.055),
        rounded_box("Small display", (center_x, face_y - 0.026, 0.62),
                    (0.51, 0.018, 0.46), screen_mat, 0.025),
        rounded_box("Earpiece", (center_x, face_y - 0.03, 0.98),
                    (0.26, 0.035, 0.045), trim_mat, 0.02),
        rounded_box("Navigation key", (center_x, face_y - 0.035, 0.10),
                    (0.30, 0.07, 0.16), trim_mat, 0.055),
    ]
    for row in range(4):
        for col in range(3):
            x = center_x + (col - 1) * 0.22
            z = -0.20 - row * 0.22
            parts.append(rounded_box(
                f"Key {row + 1}-{col + 1}", (x, face_y - 0.045, z),
                (0.15, 0.075, 0.13), key_mats[(row + col) % len(key_mats)], 0.035,
            ))
    for obj in parts:
        parent_to(obj, root)
    return root


def make_touch_phone(center_x: float, body_mat, trim_mat, screen_mat,
                     app_mats):
    root = make_phone_root("Generic touchscreen device", center_x)
    body = rounded_box("Touchscreen device shell", (center_x, 0.0, 0.02),
                       (1.12, 0.19, 2.30), body_mat, 0.12)
    parent_to(body, root)
    face_y = -0.108
    parts = [
        rounded_box("Touchscreen bezel", (center_x, face_y, 0.06),
                    (0.94, 0.045, 2.04), trim_mat, 0.085),
        rounded_box("Touchscreen glass", (center_x, face_y - 0.027, 0.06),
                    (0.84, 0.018, 1.92), screen_mat, 0.065),
        rounded_box("Front speaker", (center_x, face_y - 0.05, 0.99),
                    (0.25, 0.025, 0.035), trim_mat, 0.015),
    ]
    for row in range(4):
        for col in range(3):
            x = center_x + (col - 1) * 0.22
            z = 0.48 - row * 0.31
            icon = rounded_box(
                f"Abstract interface tile {row + 1}-{col + 1}",
                (x, face_y - 0.043, z), (0.13, 0.035, 0.13),
                app_mats[(row * 3 + col) % len(app_mats)], 0.045,
            )
            parts.append(icon)
    for obj in parts:
        parent_to(obj, root)
    return root


def text_object(body: str, name: str, location: tuple, size: float, mat,
                align: str = "CENTER"):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.align_x = align
    curve.extrude = 0.0015
    curve.bevel_depth = 0.0005
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    # Blender text lies in local XY; this turns its face toward the camera at -Y.
    obj.rotation_euler[0] = math.radians(90)
    obj.location = location
    obj.data.materials.append(mat)
    return obj


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def add_area_light(name: str, location: tuple, energy: float, color: tuple,
                   size: float, target=(0.0, 0.0, 0.0)):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color[:3]
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    aim(obj, target)
    return obj


def add_connector(mat, frames: int):
    curve = bpy.data.curves.new("Conceptual design-shift connector", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 2
    curve.bevel_depth = 0.018
    curve.bevel_resolution = 3
    curve.bevel_factor_start = 0.0
    curve.bevel_factor_end = 0.0
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (-1.05, 0.30, -0.18, 1.0)
    spline.points[1].co = (1.05, 0.30, -0.18, 1.0)
    obj = bpy.data.objects.new("Conceptual connector (not a data chart)", curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(mat)
    curve.bevel_factor_end = 0.0
    curve.keyframe_insert(data_path="bevel_factor_end", frame=1)
    curve.bevel_factor_end = 1.0
    curve.keyframe_insert(data_path="bevel_factor_end", frame=min(frames, 96))
    return obj


def animate(obj, path: str, points):
    for frame, value in points:
        setattr(obj, path, value)
        obj.keyframe_insert(data_path=path, frame=frame)


def build_scene(args: argparse.Namespace):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.materials:
        bpy.data.materials.remove(block)

    graphite = material("Satin graphite polymer", GRAPHITE, metallic=0.35, roughness=0.28)
    trim = material("Brushed dark trim", (0.14, 0.19, 0.25, 1.0), metallic=0.72, roughness=0.24)
    screen = material("Inky glass", SCREEN, metallic=0.12, roughness=0.16)
    keys = [material("Keypad silver", (0.42, 0.50, 0.58, 1.0), metallic=0.3),
            material("Keypad accent", (0.26, 0.35, 0.43, 1.0), metallic=0.28)]
    apps = [material("Interface cyan", CYAN, metallic=0.12, roughness=0.3),
            material("Interface gold", GOLD, metallic=0.12, roughness=0.3),
            material("Interface pale", (0.65, 0.81, 0.91, 1.0), metallic=0.08, roughness=0.34),
            material("Interface blue", (0.19, 0.39, 0.72, 1.0), metallic=0.1, roughness=0.32)]
    gold_glow = material("Warm connector glow", GOLD, roughness=0.25, emission=1.8)
    title_mat = material("Typography warm white", PAPER, roughness=0.35, emission=0.4)
    muted_mat = material("Typography muted blue", MUTED, roughness=0.4, emission=0.25)

    # Matte ground gives the objects a readable contact shadow without pretending
    # this is a photographed Nokia product or a mechanically accurate model.
    floor_mat = material("Midnight studio floor", NAVY, roughness=0.72)
    rounded_box("Studio floor", (0.0, 0.0, -1.45), (200.0, 200.0, 0.10), floor_mat, 0.01)

    classic = make_keypad_phone(-1.72, graphite, trim, screen, keys)
    touch = make_touch_phone(1.72, graphite, trim, screen, apps)
    add_connector(gold_glow, args.frames)

    text_object("THE SMARTPHONE SHIFT", "Title", (0.0, -0.75, 1.74), 0.34, title_mat)
    text_object("KEYPAD", "Keypad label", (-1.72, -0.62, -1.31), 0.18, title_mat)
    text_object("TOUCHSCREEN", "Touchscreen label", (1.72, -0.62, -1.31), 0.18, title_mat)
    text_object("ILLUSTRATIVE 3D SCHEMATIC - NOT A REAL PRODUCT MODEL",
                "Disclosure footer", (0.0, -0.80, 1.43), 0.105, muted_mat)

    world = bpy.data.worlds.new("Midnight blue environment")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = NAVY
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.28

    add_area_light("Large cool key", (0.0, -4.5, 5.5), 780.0, (0.72, 0.84, 1.0), 5.0)
    add_area_light("Warm edge light", (4.0, 1.2, 3.0), 1000.0, (1.0, 0.48, 0.18), 3.0)
    add_area_light("Soft fill", (-4.0, -2.0, 1.3), 520.0, (0.28, 0.62, 0.88), 4.0)

    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (-0.18, -9.2, 3.15)
    aim(camera, (0.0, 0.0, 0.04))
    camera_data.lens = 52
    bpy.context.scene.camera = camera
    animate(camera, "location", [
        (1, (-0.18, -9.2, 3.15)),
        (args.frames, (0.18, -9.2, 3.15)),
    ])
    aim(camera, (0.0, 0.0, 0.04))
    # Re-key a gentle pan without changing the vertical framing.
    for frame, x in ((1, -0.18), (args.frames, 0.18)):
        camera.location = (x, -9.2, 3.15)
        aim(camera, (x * 0.35, 0.0, 0.04))
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)

    for obj, z0, z1 in ((classic, -0.025, 0.025), (touch, 0.02, -0.02)):
        animate(obj, "rotation_euler", [
            (1, (0.0, 0.0, z0)),
            (args.frames // 2, (0.0, 0.0, -z0)),
            (args.frames, (0.0, 0.0, z1)),
        ])
        # A small vertical drift gives the product-card composition parallax;
        # it does not claim that either device transforms into the other.
        base_z = obj.location.z
        animate(obj, "location", [
            (1, (obj.location.x, obj.location.y, base_z)),
            (args.frames // 2, (obj.location.x, obj.location.y, base_z + 0.045)),
            (args.frames, (obj.location.x, obj.location.y, base_z)),
        ])

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 2
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 960
    scene.render.resolution_y = 540
    scene.render.resolution_percentage = 100
    scene.render.fps = args.fps
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.image_settings.compression = 8
    scene.render.filepath = str(Path(args.output_dir) / "frame_")
    scene.frame_start = 1
    scene.frame_end = args.frames
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2

    # Use linear interpolation for a calm camera drift; Blender's default Bezier
    # handles can overshoot a short motion at the beginning/end.
    for obj in (camera, classic, touch):
        if obj.animation_data and obj.animation_data.action:
            for fc in obj.animation_data.action.fcurves:
                for key in fc.keyframe_points:
                    key.interpolation = "LINEAR"

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.output_dir) / "nokia_shift.blend"))
    bpy.ops.render.render(animation=True)


def main():
    build_scene(arguments())


if __name__ == "__main__":
    main()
