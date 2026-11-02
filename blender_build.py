"""Headless Blender worker for Character Creation Suite: builds the character
and writes <id>.blend (primary output) plus FBX/GLB exports.

Run only through Blender: blender --background --python blender_build.py -- config.json [--thumbnail-only]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from animation_library import clips
from character_config import load_config, safe_id
from retarget import GROUND_BONE, bake_clips
from rig_builder import action_fcurves, bake_export_materials, build_character, export_textures


def after_double_dash() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def save_blend(blend_path: Path, armature, clip_names: list[str]) -> None:
    """Save the current scene as a self-contained .blend.

    - Every clip Action gets a fake user, so all of them survive the save
      even though only one can be assigned to the armature at a time; pick
      any of them in Blender's Action Editor.
    - The first selected clip is left assigned, with the scene frame range
      set to it, so the file opens ready to play.
    - Material textures are packed into the file (like the FBX's embedded
      textures), so the .blend still shows the right colours if it's moved
      away from its Textures/ folder.
    """
    for clip_name in clip_names:
        bpy.data.actions[clip_name].use_fake_user = True
    first = bpy.data.actions[clip_names[0]]
    armature.animation_data.action = first
    scene = bpy.context.scene
    scene.frame_start = int(first.frame_start)
    scene.frame_end = int(first.frame_end)
    scene.frame_set(scene.frame_start)
    for image in bpy.data.images:
        if image.filepath_raw and not image.packed_file:
            image.pack()
    # Drop leftovers (Blender's startup scene, MPFB build helpers, the
    # export-only baked images). Fake-user Actions and everything the
    # character uses are kept.
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)


THUMBNAIL_SIZE = (350, 510)  # the app's preview panel, in pixels
THUMBNAIL_BACKGROUND = (0.010, 0.014, 0.024)  # linear; matches the app's #1a202b panel


def thumbnail_paths(output_dir: Path, character_id: str) -> tuple[Path, Path]:
    """The rendered preview image, and the config it was rendered from (the
    app compares that with its current settings to show "out of date")."""
    return output_dir / f"{character_id}_Thumbnail.png", output_dir / f"{character_id}_Thumbnail.json"


def render_thumbnail(config: dict, armature, meshes, output_dir: Path, frame: int = 1) -> Path:
    """Render a front three-quarter view of the character as posed at
    `frame` (Cycles on the CPU, low sample count), framed to its evaluated
    bounds. The camera, lights and world are created for the render only."""
    import math
    from mathutils import Vector
    scene = bpy.context.scene
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        points.extend(obj.matrix_world @ vertex.co for vertex in mesh.vertices)
        evaluated.to_mesh_clear()
    low = Vector(tuple(min(point[axis] for point in points) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in points) for axis in range(3)))
    centre, size = (low + high) / 2, high - low

    created = []
    camera_data = bpy.data.cameras.new("_ccs_thumbnail_camera")
    camera_data.lens = 50
    camera = bpy.data.objects.new("_ccs_thumbnail_camera", camera_data)
    # MPFB characters face -Y: view from front-left, slightly above.
    direction = Vector((0.45, -1.0, 0.18)).normalized()
    width, height = THUMBNAIL_SIZE
    vertical_fov = 2 * math.atan(camera_data.sensor_width / 2 / camera_data.lens * min(1.0, height / width))
    extent = max(size.z, size.x * height / width, 0.5) * 1.12
    camera.location = centre + direction * (extent / 2 / math.tan(vertical_fov / 2) + max(size.x, size.y) / 2)
    camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()
    created.append(camera)
    for name, kind, energy, rotation in (("_ccs_key", "SUN", 3.5, (math.radians(50), 0, math.radians(-35))),
                                         ("_ccs_fill", "SUN", 1.2, (math.radians(70), 0, math.radians(140)))):
        light_data = bpy.data.lights.new(name, kind)
        light_data.energy = energy
        light = bpy.data.objects.new(name, light_data)
        light.rotation_euler = rotation
        created.append(light)
    for obj in created:
        scene.collection.objects.link(obj)
    previous = (scene.camera, scene.world, scene.render.engine, scene.render.resolution_x, scene.render.resolution_y,
                scene.render.resolution_percentage, scene.render.filepath, scene.render.film_transparent)
    world = bpy.data.worlds.new("_ccs_thumbnail_world")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    if background:
        background.inputs["Color"].default_value = (*THUMBNAIL_BACKGROUND, 1.0)
        background.inputs["Strength"].default_value = 1.0
    scene.camera, scene.world = camera, world
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.render.resolution_x, scene.render.resolution_y = THUMBNAIL_SIZE
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    image_path, config_path = thumbnail_paths(output_dir, config["character_id"])
    scene.render.filepath = str(image_path)
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    (scene.camera, scene.world, scene.render.engine, scene.render.resolution_x, scene.render.resolution_y,
     scene.render.resolution_percentage, scene.render.filepath, scene.render.film_transparent) = previous
    for obj in created:
        data, is_camera = obj.data, obj.type == "CAMERA"
        bpy.data.objects.remove(obj, do_unlink=True)
        (bpy.data.cameras if is_camera else bpy.data.lights).remove(data)
    bpy.data.worlds.remove(world)
    return image_path


def build_thumbnail_only(config_path: Path) -> None:
    """Quick preview for the app: build the character, put it in its Idle
    pose (grounded), render the thumbnail. No exports, no .blend."""
    config = load_config(config_path)
    output_dir = (ROOT / config["output_root"] / safe_id(config["character_id"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    armature, meshes, _bones = build_character(config)
    bake_clips(armature, {"Idle": clips()["Idle"]}, ground_meshes=meshes if config["ground_contact"] else None)
    image_path = render_thumbnail(config, armature, meshes, output_dir)
    print("CHARACTER_SUITE_THUMBNAIL " + json.dumps({"thumbnail": str(image_path)}))


def build(config_path: Path) -> None:
    config = load_config(config_path)
    output_dir = (ROOT / config["output_root"] / safe_id(config["character_id"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    armature, meshes, bones = build_character(config)
    # Original asset textures, copied next to the build (the .blend's
    # materials use these; colour slots are shader effects on top).
    texture_paths = export_textures(output_dir)
    # Baked final colours, used by the FBX/GLB exports below.
    baked_paths, restore_materials = bake_export_materials(meshes, output_dir / "Textures")

    def select_exportables():
        bpy.ops.object.select_all(action="DESELECT")
        for mesh in meshes:
            mesh.select_set(True)
        armature.select_set(True)
        bpy.context.view_layer.objects.active = armature

    select_exportables()
    preview_path = output_dir / f"{config['character_id']}_Preview.glb"
    if config["export_preview_glb"]:
        # export_apply=True so the GLB carries the same modifier-applied
        # geometry as the FBX exports (subdivision, and the masks that hide
        # MPFB's helper geometry and the body skin under clothes). The
        # exporter keeps the Armature modifier out of the apply and exports
        # it as a skin.
        bpy.ops.export_scene.gltf(filepath=str(preview_path), export_format="GLB", use_selection=True, export_apply=True)

    # Bind-pose model FBX, no animation, exported before any clip Actions
    # exist; it shares the armature object with the combined-take FBX
    # below, so bone names, hierarchy, and bind pose stay identical.
    model_path = output_dir / f"{config['character_id']}_Model.fbx"
    if config["export_separate_animations"]:
        select_exportables()
        bpy.ops.export_scene.fbx(filepath=str(model_path), use_selection=True, object_types={"ARMATURE", "MESH"}, axis_forward="-Z", axis_up="Y", add_leaf_bones=False, bake_anim=False, path_mode="COPY", embed_textures=True)

    available = clips()
    bake_clips(armature, {clip_name: available[clip_name] for clip_name in config["clips"]}, ground_meshes=meshes if config["ground_contact"] else None)

    # Bones only rotate; the one allowed location channel is the Root bone's
    # ground-contact offset.
    location_curves = [curve.data_path for action in bpy.data.actions for curve in action_fcurves(action)
                       if "location" in curve.data_path and curve.data_path != f'pose.bones["{GROUND_BONE}"].location']
    if location_curves:
        raise RuntimeError(f"Animation contract violated (only the {GROUND_BONE} ground offset may move location): {location_curves}")

    select_exportables()
    fbx_path = output_dir / f"{config['character_id']}.fbx"
    bpy.ops.export_scene.fbx(filepath=str(fbx_path), use_selection=True, object_types={"ARMATURE", "MESH"}, axis_forward="-Z", axis_up="Y", add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0, path_mode="COPY", embed_textures=True)

    # Per-clip animation-only FBX files: skeleton only (no mesh), one baked
    # action each. Exported from the same armature object as the model FBX
    # above, so the bone hierarchy matches exactly and other apps can
    # retarget each clip onto the model.
    #
    # Each clip is exported through a single temporary NLA strip named after
    # the clip (bake_anim_use_nla_strips=True). The FBX exporter names that
    # take after the strip and starts its keys at time 0 — the same timing
    # as the combined FBX's takes. The previous approach (exporting the
    # active action over the scene range) named every take "Scene" and
    # started its keys at frame 1 instead of 0.
    animation_paths: dict[str, str] = {}
    if config["export_separate_animations"]:
        animations_dir = output_dir / "Animations"
        animations_dir.mkdir(parents=True, exist_ok=True)
        armature.animation_data.action = None
        for clip_name in config["clips"]:
            action = bpy.data.actions[clip_name]
            track = armature.animation_data.nla_tracks.new()
            track.name = clip_name
            strip = track.strips.new(clip_name, int(action.frame_start), action)
            strip.name = clip_name
            bpy.ops.object.select_all(action="DESELECT"); armature.select_set(True); bpy.context.view_layer.objects.active = armature
            clip_path = animations_dir / f"{clip_name}.fbx"
            bpy.ops.export_scene.fbx(filepath=str(clip_path), use_selection=True, object_types={"ARMATURE"}, axis_forward="-Z", axis_up="Y", add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=True, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0)
            armature.animation_data.nla_tracks.remove(track)
            animation_paths[clip_name] = str(clip_path)

    # The .blend is the primary output: the rigged character as built
    # (modifiers live), its original, editable materials (the export
    # wiring is undone first), and every selected clip as a named Action.
    restore_materials()
    blend_path = output_dir / f"{config['character_id']}.blend"
    save_blend(blend_path, armature, config["clips"])
    # Rendered after the save, so the temporary camera/lights never end up
    # in the .blend. Shows the first clip's first frame.
    thumbnail_path = render_thumbnail(config, armature, meshes, output_dir)

    manifest = {"character_id": config["character_id"], "blend": str(blend_path), "thumbnail": str(thumbnail_path), "fbx": str(fbx_path), "model_fbx": str(model_path) if config["export_separate_animations"] else None, "animation_fbx": animation_paths, "preview_glb": str(preview_path) if config["export_preview_glb"] else None, "textures": texture_paths, "baked_textures": baked_paths, "bones": list(bones), "clips": config["clips"], "ground_contact": config["ground_contact"], "unit_scale_m": 1.0}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("CHARACTER_SUITE_SUCCESS " + json.dumps(manifest))


if __name__ == "__main__":
    args = after_double_dash()
    if not args: raise SystemExit("Usage: blender --background --python blender_build.py -- config.json [--thumbnail-only]")
    if "--thumbnail-only" in args:
        build_thumbnail_only(Path(args[0]).resolve())
    else:
        build(Path(args[0]).resolve())
