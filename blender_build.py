"""Headless Blender worker for Character Creation Suite: builds the character
and writes <id>.blend (primary output) plus FBX/GLB exports.

Run only through Blender: blender --background --python blender_build.py -- config.json
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
from rig_builder import action_fcurves, bake_pose_action, build_character, export_material_textures


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
    # Drop leftovers from Blender's startup scene (e.g. the default cube's
    # mesh and "Material") that build_character's object delete orphaned.
    # Fake-user Actions and everything the character uses are kept.
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)


def build(config_path: Path) -> None:
    config = load_config(config_path)
    output_dir = (ROOT / config["output_root"] / safe_id(config["character_id"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    armature, mesh, bones = build_character(config)
    texture_paths = export_material_textures(config, output_dir)

    def select_exportables():
        bpy.ops.object.select_all(action="DESELECT"); mesh.select_set(True); armature.select_set(True); bpy.context.view_layer.objects.active = armature

    select_exportables()
    preview_path = output_dir / f"{config['character_id']}_Preview.glb"
    if config["export_preview_glb"]:
        # export_apply=True so the GLB carries the same modifier-applied
        # geometry as the FBX exports (the Bevel modifier);
        # without it the GLB showed the un-bevelled mesh. The exporter keeps
        # the Armature modifier out of the apply and exports it as a skin.
        bpy.ops.export_scene.gltf(filepath=str(preview_path), export_format="GLB", use_selection=True, export_apply=True)

    # Bind-pose model FBX, no animation. Exported before any actions exist so
    # Unity has a clean model import that isn't coupled to the combined-take
    # FBX below; both reference this same armature object, so bone names,
    # hierarchy, and bind pose stay identical between them.
    model_path = output_dir / f"{config['character_id']}_Model.fbx"
    if config["export_separate_animations"]:
        select_exportables()
        bpy.ops.export_scene.fbx(filepath=str(model_path), use_selection=True, object_types={"ARMATURE", "MESH"}, axis_forward="-Z", axis_up="Y", add_leaf_bones=False, bake_anim=False, path_mode="COPY", embed_textures=True)

    armature.animation_data_create()
    available = clips()
    for clip_name in config["clips"]:
        bake_pose_action(armature, clip_name, available[clip_name])

    location_curves = [curve.data_path for action in bpy.data.actions for curve in action_fcurves(action) if "location" in curve.data_path]
    if location_curves:
        raise RuntimeError(f"Rotation-only animation contract violated: {location_curves}")

    select_exportables()
    fbx_path = output_dir / f"{config['character_id']}.fbx"
    bpy.ops.export_scene.fbx(filepath=str(fbx_path), use_selection=True, object_types={"ARMATURE", "MESH"}, axis_forward="-Z", axis_up="Y", add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0, path_mode="COPY", embed_textures=True)

    # Per-clip animation-only FBX files: skeleton only (no mesh), one baked
    # action each. Exported from the same armature object as the model FBX
    # above, so the bone hierarchy matches exactly and Unity can retarget
    # each clip onto the model's avatar.
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
    # (Bevel modifier still live), its materials, and every
    # selected clip as a named Action. Saved last so it reflects the final
    # scene state after all exports.
    blend_path = output_dir / f"{config['character_id']}.blend"
    save_blend(blend_path, armature, config["clips"])

    manifest = {"character_id": config["character_id"], "blend": str(blend_path), "fbx": str(fbx_path), "model_fbx": str(model_path) if config["export_separate_animations"] else None, "animation_fbx": animation_paths, "preview_glb": str(preview_path) if config["export_preview_glb"] else None, "textures": texture_paths, "bones": list(bones), "clips": config["clips"], "root_translation_keyframes": False, "unit_scale_m": 1.0}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("CHARACTER_SUITE_SUCCESS " + json.dumps(manifest))


if __name__ == "__main__":
    args = after_double_dash()
    if not args: raise SystemExit("Usage: blender --background --python blender_build.py -- config.json")
    build(Path(args[0]).resolve())
