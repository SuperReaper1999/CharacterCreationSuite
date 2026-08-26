"""Headless Blender worker for Character Creation Suite.

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


def after_double_dash() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def action_fcurves(action):
    """Compatibility shim for Blender <=4.x and Blender 4.4+/5.x Actions."""
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                yield from getattr(channelbag, "fcurves", [])


def build(config_path: Path) -> None:
    config = load_config(config_path)
    output_dir = (ROOT / config["output_root"] / safe_id(config["character_id"])).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.render.fps = 30

    def mat(name, color):
        result = bpy.data.materials.new(name)
        result.diffuse_color = color
        result.use_nodes = True
        bsdf = result.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color
            bsdf.inputs["Roughness"].default_value = 0.72
        return result

    materials = {name: mat(f"{config['character_id']}_{name}", color) for name, color in config["materials"].items()}
    # This is the legacy Player rig authored at 2.69m, preserved exactly as
    # the default suite shape. Customisation is deliberately layered on it;
    # it never reconstructs the rest pose from a different coordinate model.
    p = config["proportions"]
    scale = config["target_height_m"] / 2.69
    shoulder = .52 * scale * p["shoulder_width"]
    leg_x = .17 * scale * p["body_width"]
    arm_length = .48 * scale * p["arm_length"]
    leg_length = .50 * scale * p["leg_length"]
    bones = {
        "Hips": ((0, 0, .90 * scale), (0, 0, 1.15 * scale), None), "Chest": ((0, 0, 1.15 * scale), (0, 0, 1.95 * scale), "Hips"),
        "Neck": ((0, 0, 1.95 * scale), (0, 0, 2.05 * scale), "Chest"), "Head": ((0, 0, 2.05 * scale), (0, 0, 2.56 * scale), "Neck"),
        "UpperArm.L": ((-shoulder, 0, 1.92 * scale), (-shoulder, 0, 1.92 * scale - arm_length), "Chest"), "Forearm.L": ((-shoulder, 0, 1.92 * scale - arm_length), (-shoulder, 0, 1.92 * scale - arm_length * 2), "UpperArm.L"), "Hand.L": ((-shoulder, 0, 1.92 * scale - arm_length * 2), (-shoulder, 0, 1.92 * scale - arm_length * 2 - .18 * scale), "Forearm.L"),
        "UpperArm.R": ((shoulder, 0, 1.92 * scale), (shoulder, 0, 1.92 * scale - arm_length), "Chest"), "Forearm.R": ((shoulder, 0, 1.92 * scale - arm_length), (shoulder, 0, 1.92 * scale - arm_length * 2), "UpperArm.R"), "Hand.R": ((shoulder, 0, 1.92 * scale - arm_length * 2), (shoulder, 0, 1.92 * scale - arm_length * 2 - .18 * scale), "Forearm.R"),
        "UpperLeg.L": ((-leg_x, 0, .90 * scale), (-leg_x, 0, .90 * scale - leg_length), "Hips"), "LowerLeg.L": ((-leg_x, 0, .90 * scale - leg_length), (-leg_x, 0, .90 * scale - leg_length * 2), "UpperLeg.L"), "Foot.L": ((-leg_x, 0, .90 * scale - leg_length * 2), (-leg_x, .35 * scale, .90 * scale - leg_length * 2), "LowerLeg.L"),
        "UpperLeg.R": ((leg_x, 0, .90 * scale), (leg_x, 0, .90 * scale - leg_length), "Hips"), "LowerLeg.R": ((leg_x, 0, .90 * scale - leg_length), (leg_x, 0, .90 * scale - leg_length * 2), "UpperLeg.R"), "Foot.R": ((leg_x, 0, .90 * scale - leg_length * 2), (leg_x, .35 * scale, .90 * scale - leg_length * 2), "LowerLeg.R"),
    }
    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    armature = bpy.context.object
    armature.name = str(config.get("rig_root_name") or f"{config['character_id']}_Armature")
    edit = armature.data.edit_bones
    edit.remove(edit[0])
    created = {}
    for name, (head_pos, tail_pos, _) in bones.items():
        bone = edit.new(name); bone.head = head_pos; bone.tail = tail_pos; created[name] = bone
    for name, (_, _, parent) in bones.items():
        if parent:
            created[name].parent = created[parent]
            created[name].use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")

    body = p["body_width"]
    torso = p["torso_length"]
    head = p["head_scale"]
    parts = [
        ("Hips", (.55 * scale * body, .28 * scale, .25 * scale), (0, 0, 1.00 * scale), "bottom", "Hips"), ("Torso", (.60 * scale * body, .30 * scale, .80 * scale * torso), (0, 0, 1.55 * scale), "top", "Chest"),
        ("Neck", (.18 * scale, .18 * scale, .15 * scale), (0, 0, 2.00 * scale), "skin", "Neck"), ("Head", (.42 * scale * head, .42 * scale * head, .42 * scale * head), (0, 0, 2.30 * scale), "skin", "Head"),
        ("UpperArm.L", (.22 * scale, .22 * scale, arm_length), (-shoulder, 0, 1.92 * scale - arm_length / 2), "top", "UpperArm.L"), ("Forearm.L", (.20 * scale, .20 * scale, arm_length * .9375), (-shoulder, 0, 1.92 * scale - arm_length * 1.5), "skin", "Forearm.L"), ("Hand.L", (.22 * scale, .22 * scale, .18 * scale), (-shoulder, 0, 1.92 * scale - arm_length * 2 - .09 * scale), "skin", "Hand.L"),
        ("UpperArm.R", (.22 * scale, .22 * scale, arm_length), (shoulder, 0, 1.92 * scale - arm_length / 2), "top", "UpperArm.R"), ("Forearm.R", (.20 * scale, .20 * scale, arm_length * .9375), (shoulder, 0, 1.92 * scale - arm_length * 1.5), "skin", "Forearm.R"), ("Hand.R", (.22 * scale, .22 * scale, .18 * scale), (shoulder, 0, 1.92 * scale - arm_length * 2 - .09 * scale), "skin", "Hand.R"),
        ("UpperLeg.L", (.23 * scale * body, .24 * scale, leg_length), (-leg_x, 0, .90 * scale - leg_length / 2), "bottom", "UpperLeg.L"), ("LowerLeg.L", (.21 * scale * body, .22 * scale, leg_length), (-leg_x, 0, .90 * scale - leg_length * 1.5), "bottom", "LowerLeg.L"), ("Foot.L", (.25 * scale * body, .45 * scale, .16 * scale), (-leg_x, .175 * scale, .90 * scale - leg_length * 2), "shoes", "Foot.L"),
        ("UpperLeg.R", (.23 * scale * body, .24 * scale, leg_length), (leg_x, 0, .90 * scale - leg_length / 2), "bottom", "UpperLeg.R"), ("LowerLeg.R", (.21 * scale * body, .22 * scale, leg_length), (leg_x, 0, .90 * scale - leg_length * 1.5), "bottom", "LowerLeg.R"), ("Foot.R", (.25 * scale * body, .45 * scale, .16 * scale), (leg_x, .175 * scale, .90 * scale - leg_length * 2), "shoes", "Foot.R"),
    ]
    objects = []
    for name, size, position, material_key, bone_name in parts:
        bpy.ops.mesh.primitive_cube_add(size=1, location=position)
        obj = bpy.context.object; obj.name = name; obj.dimensions = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(materials[material_key])
        group = obj.vertex_groups.new(name=bone_name)
        group.add([vertex.index for vertex in obj.data.vertices], 1.0, "REPLACE")
        objects.append(obj)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects: obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    mesh = bpy.context.object; mesh.name = f"{config['character_id']}_Mesh"; mesh.parent = armature
    modifier = mesh.modifiers.new(name="Armature", type="ARMATURE"); modifier.object = armature

    def select_exportables():
        bpy.ops.object.select_all(action="DESELECT"); mesh.select_set(True); armature.select_set(True); bpy.context.view_layer.objects.active = armature

    select_exportables()
    preview_path = output_dir / f"{config['character_id']}_Preview.glb"
    if config["export_preview_glb"]:
        bpy.ops.export_scene.gltf(filepath=str(preview_path), export_format="GLB", use_selection=True)

    # Bind-pose model FBX, no animation. Exported before any actions exist so
    # Unity has a clean model import that isn't coupled to the combined-take
    # FBX below; both reference this same armature object, so bone names,
    # hierarchy, and bind pose stay identical between them.
    model_path = output_dir / f"{config['character_id']}_Model.fbx"
    if config["export_separate_animations"]:
        select_exportables()
        bpy.ops.export_scene.fbx(filepath=str(model_path), use_selection=True, object_types={"ARMATURE", "MESH"}, axis_forward="-Z", axis_up="Y", add_leaf_bones=False, bake_anim=False)

    armature.animation_data_create()
    available = clips()
    for clip_name in config["clips"]:
        clip = available[clip_name]
        action = bpy.data.actions.new(clip_name); action.use_frame_range = True; action.frame_start = 1; action.frame_end = clip["frames"]
        armature.animation_data.action = action
        for frame, pose in clip["poses"].items():
            bpy.context.scene.frame_set(frame)
            for bone in armature.pose.bones:
                bone.rotation_mode = "XYZ"; bone.rotation_euler = (0, 0, 0)
            for bone_name, rotation in pose.items(): armature.pose.bones[bone_name].rotation_euler = rotation
            for bone in armature.pose.bones: bone.keyframe_insert(data_path="rotation_euler", frame=frame)
        for curve in action_fcurves(action):
            for point in curve.keyframe_points: point.interpolation = "BEZIER"

    location_curves = [curve.data_path for action in bpy.data.actions for curve in action_fcurves(action) if "location" in curve.data_path]
    if location_curves:
        raise RuntimeError(f"Rotation-only animation contract violated: {location_curves}")

    select_exportables()
    fbx_path = output_dir / f"{config['character_id']}.fbx"
    bpy.ops.export_scene.fbx(filepath=str(fbx_path), use_selection=True, object_types={"ARMATURE", "MESH"}, axis_forward="-Z", axis_up="Y", add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=True, bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0)

    # Per-clip animation-only FBX files: skeleton only (no mesh), one baked
    # action each. Exported from the same armature object as the model FBX
    # above, so the bone hierarchy matches exactly and Unity can retarget
    # each clip onto the model's avatar.
    animation_paths: dict[str, str] = {}
    if config["export_separate_animations"]:
        animations_dir = output_dir / "Animations"
        animations_dir.mkdir(parents=True, exist_ok=True)
        for clip_name in config["clips"]:
            armature.animation_data.action = bpy.data.actions[clip_name]
            bpy.ops.object.select_all(action="DESELECT"); armature.select_set(True); bpy.context.view_layer.objects.active = armature
            clip_path = animations_dir / f"{clip_name}.fbx"
            bpy.ops.export_scene.fbx(filepath=str(clip_path), use_selection=True, object_types={"ARMATURE"}, axis_forward="-Z", axis_up="Y", add_leaf_bones=False, bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False, bake_anim_force_startend_keying=True, bake_anim_step=1.0, bake_anim_simplify_factor=0.0)
            animation_paths[clip_name] = str(clip_path)

    manifest = {"character_id": config["character_id"], "fbx": str(fbx_path), "model_fbx": str(model_path) if config["export_separate_animations"] else None, "animation_fbx": animation_paths, "preview_glb": str(preview_path) if config["export_preview_glb"] else None, "bones": list(bones), "clips": config["clips"], "root_translation_keyframes": False, "unit_scale_m": 1.0, "unity_axes": {"forward": "-Z", "up": "Y"}}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("CHARACTER_SUITE_SUCCESS " + json.dumps(manifest))


if __name__ == "__main__":
    args = after_double_dash()
    if not args: raise SystemExit("Usage: blender --background --python blender_build.py -- config.json")
    build(Path(args[0]).resolve())
