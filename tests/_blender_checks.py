"""Checks run inside Blender by tests/smoke_test.py. Not meant to be run directly.

    <blender> --background --python tests/_blender_checks.py -- outputs <config.json> <output_dir>
    <blender> --background --python tests/_blender_checks.py -- poses <config.json>

Prints one "PASS <check>" / "FAIL <check>: <detail>" / "INFO <note>" line per check.
"""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

import bpy  # must come first: with the pip "bpy" module, addon_utils/mathutils only resolve after it
import addon_utils
from mathutils import Vector

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from animation_library import _builtin_clips, _extended_clips  # noqa: E402
from character_config import BONE_NAMES, ALL_BONE_NAMES, load_config  # noqa: E402
from rig_builder import action_fcurves, bake_pose_action, build_character  # noqa: E402

FBX_TIME_PER_SECOND = 46186158000
FPS = 30
failed = False


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    failed |= not ok
    print(f"PASS {name}" if ok else f"FAIL {name}: {detail}")


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def fbx_takes(path: Path) -> dict[str, tuple[float, float]]:
    """Take (AnimationStack) name -> (LocalStart, LocalStop) in frames, read
    from the raw FBX — the names and ranges Unity's importer sees."""
    addon_utils.enable("io_scene_fbx")
    from io_scene_fbx import parse_fbx
    root, _version = parse_fbx.parse(str(path))
    takes = {}
    for element in root.elems:
        if element.id != b"Objects":
            continue
        for obj in element.elems:
            if obj.id != b"AnimationStack":
                continue
            name = obj.props[1].split(b"\x00")[0].decode()
            start = stop = 0.0
            for props70 in obj.elems:
                for prop in props70.elems:
                    if prop.props and prop.props[0] == b"LocalStart":
                        start = prop.props[4] / FBX_TIME_PER_SECOND * FPS
                    if prop.props and prop.props[0] == b"LocalStop":
                        stop = prop.props[4] / FBX_TIME_PER_SECOND * FPS
            takes[name] = (round(start, 3), round(stop, 3))
    return takes


def import_fbx(path: Path):
    reset()
    bpy.ops.import_scene.fbx(filepath=str(path))
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    return armatures, meshes


def moving_location_curves() -> list[str]:
    return [f"{action.name}:{curve.data_path}" for action in bpy.data.actions for curve in action_fcurves(action)
            if "location" in curve.data_path and len({round(point.co.y, 5) for point in curve.keyframe_points}) > 1]


def glb_summary(path: Path) -> dict:
    data = path.read_bytes()
    json_length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_length])
    primitives = [primitive for mesh in gltf.get("meshes", []) for primitive in mesh["primitives"]]
    return {
        "vertices": sum(gltf["accessors"][primitive["attributes"]["POSITION"]]["count"] for primitive in primitives),
        "skinned": bool(primitives) and all("JOINTS_0" in primitive["attributes"] for primitive in primitives),
        "joints": [len(skin["joints"]) for skin in gltf.get("skins", [])],
    }


def check_outputs(config_path: Path, output_dir: Path) -> None:
    config = load_config(config_path)
    character = config["character_id"]
    expected_bones = len(ALL_BONE_NAMES) if config["rig_type"] == "extended" else len(BONE_NAMES)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    listed = [manifest["fbx"], manifest["model_fbx"], manifest["preview_glb"], *manifest["animation_fbx"].values(), *manifest["textures"].values()]
    missing = [path for path in listed if path and not Path(path).is_file()]
    check(f"{character}: manifest files exist", not missing, f"missing {missing}")
    check(f"{character}: manifest clips match config", manifest["clips"] == config["clips"], f"{manifest['clips']} != {config['clips']}")

    # Combined FBX: bones, one take per clip, rotation-only.
    combined_takes = fbx_takes(Path(manifest["fbx"]))
    clip_of_take = {take.rsplit("|", 1)[-1]: frame_range for take, frame_range in combined_takes.items()}
    check(f"{character}: combined FBX has one take per clip", sorted(clip_of_take) == sorted(config["clips"]), f"takes {sorted(combined_takes)}")
    armatures, _meshes = import_fbx(Path(manifest["fbx"]))
    bones = len(armatures[0].data.bones) if armatures else 0
    check(f"{character}: combined FBX has {expected_bones} bones", bones == expected_bones, f"found {bones}")
    moving = moving_location_curves()
    check(f"{character}: combined FBX is rotation-only", not moving, f"{moving[:5]}")

    if manifest["model_fbx"]:
        armatures, meshes = import_fbx(Path(manifest["model_fbx"]))
        bones = len(armatures[0].data.bones) if armatures else 0
        check(f"{character}: model FBX has {expected_bones} bones and a mesh", bones == expected_bones and bool(meshes), f"bones {bones}, meshes {len(meshes)}")
        check(f"{character}: model FBX has no takes", not fbx_takes(Path(manifest["model_fbx"])), f"{list(fbx_takes(Path(manifest['model_fbx'])))}")

    # Per-clip FBX: armature only, one take named after the clip, same range as the combined take.
    bad_clips = []
    for clip, path in manifest["animation_fbx"].items():
        takes = fbx_takes(Path(path))
        if list(takes) != [clip]:
            bad_clips.append(f"{clip}: takes {list(takes)}")
        elif takes[clip] != clip_of_take.get(clip):
            bad_clips.append(f"{clip}: range {takes[clip]} != combined {clip_of_take.get(clip)}")
    check(f"{character}: per-clip FBX takes named after the clip, same range as combined", not bad_clips, "; ".join(bad_clips[:5]))
    if manifest["animation_fbx"]:
        bad_contents = []
        for clip, path in manifest["animation_fbx"].items():
            armatures, meshes = import_fbx(Path(path))
            if len(armatures) != 1 or meshes:
                bad_contents.append(f"{clip}: {len(armatures)} armatures, {len(meshes)} meshes")
            elif len(armatures[0].data.bones) != expected_bones:
                bad_contents.append(f"{clip}: {len(armatures[0].data.bones)} bones")
            elif moving_location_curves():
                bad_contents.append(f"{clip}: moving location curves")
        check(f"{character}: per-clip FBX are skeleton-only, {expected_bones} bones, rotation-only", not bad_contents, "; ".join(bad_contents[:5]))

    # GLB: skinned, and carries modifier-applied geometry. glTF can split
    # vertices (normals/UV seams) but never merges them, so the GLB must have
    # at least as many vertices as the evaluated (bevelled) Blender mesh.
    if manifest["preview_glb"]:
        reset()
        _armature, mesh, _bones = build_character(config)
        evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        evaluated_vertices = len(evaluated.vertices)
        summary = glb_summary(Path(manifest["preview_glb"]))
        check(f"{character}: GLB is skinned with {expected_bones} joints", summary["skinned"] and summary["joints"] == [expected_bones], f"{summary}")
        check(f"{character}: GLB has modifier-applied geometry", summary["vertices"] >= evaluated_vertices,
              f"GLB {summary['vertices']} vertices < evaluated mesh {evaluated_vertices}")


def front_direction(pose_bone) -> Vector:
    """World direction the bone's rest-pose 'forward' (+Y, the way the
    character faces) points to in the current pose."""
    delta = pose_bone.matrix.to_3x3() @ pose_bone.bone.matrix_local.to_3x3().inverted()
    return (delta @ Vector((0, 1, 0))).normalized()


def elbow_flex_toward_front(pose_bones, side: str) -> float:
    """> 0 when the elbow bends the anatomical way (forearm toward the
    body's front); < 0 when it hyperextends."""
    upper = pose_bones[f"Forearm.{side}"].head - pose_bones[f"UpperArm.{side}"].head
    lower = pose_bones[f"Hand.{side}"].head - pose_bones[f"Forearm.{side}"].head
    perpendicular = lower - upper.normalized() * lower.dot(upper.normalized())
    if perpendicular.length < 1e-6:
        return 0.0
    return perpendicular.normalized().dot(front_direction(pose_bones["Chest"]))


def check_poses(config_path: Path) -> None:
    builtin = _builtin_clips()
    clips = {**builtin, **_extended_clips(builtin)}
    for rig_type, suffix in (("standard", ""), ("extended", "Extended")):
        reset()
        config = load_config(config_path)
        config["rig_type"] = rig_type
        armature, mesh, _bones = build_character(config)
        armature.animation_data_create()
        for clip_name in (f"Idle{suffix}", f"Prone{suffix}", f"Crawl{suffix}"):
            bake_pose_action(armature, clip_name, clips[clip_name])
            bpy.context.scene.frame_set(1)
            pose_bones = armature.pose.bones
            chest = front_direction(pose_bones["Chest"])
            head = front_direction(pose_bones["Head"])
            if clip_name.startswith("Idle"):
                check(f"{rig_type} {clip_name}: chest faces forward (+Y)", chest.y > 0.95, f"chest front {tuple(round(c, 2) for c in chest)}")
                continue
            check(f"{rig_type} {clip_name}: chest faces the ground", chest.z < -0.9, f"chest front {tuple(round(c, 2) for c in chest)}")
            check(f"{rig_type} {clip_name}: head looks ahead, not up", head.z < 0 and head.y > 0.5, f"head front {tuple(round(c, 2) for c in head)}")
            flex = min(elbow_flex_toward_front(pose_bones, "L"), elbow_flex_toward_front(pose_bones, "R"))
            check(f"{rig_type} {clip_name}: elbows bend the natural way", flex > 0, f"flex {flex:.2f}")
            evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
            heights = [(mesh.matrix_world @ vertex.co).z for vertex in evaluated.vertices]
            print(f"INFO {rig_type} {clip_name} frame 1 mesh height range: {min(heights):.2f}..{max(heights):.2f} m (target_height_m {config['target_height_m']})")


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if arguments[:1] == ["outputs"] and len(arguments) == 3:
        check_outputs(Path(arguments[1]), Path(arguments[2]))
    elif arguments[:1] == ["poses"] and len(arguments) == 2:
        check_poses(Path(arguments[1]))
    else:
        raise SystemExit(__doc__)
    sys.exit(1 if failed else 0)
