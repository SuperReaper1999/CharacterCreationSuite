"""Checks run inside Blender by tests/smoke_test.py. Not meant to be run directly.

    <blender> --background --python tests/_blender_checks.py -- outputs <config.json> <output_dir>
    <blender> --background --python tests/_blender_checks.py -- poses <config.json>

Prints one "PASS <check>" / "FAIL <check>: <detail>" / "INFO <note>" line per check.
Needs MPFB installed in this Blender (setup_mpfb.py) for the "poses" checks.
"""

from __future__ import annotations

import json
import math
import struct
import sys
from pathlib import Path

import bpy  # must come first: with the pip "bpy" module, addon_utils/mathutils only resolve after it
import addon_utils
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from animation_library import builtin_clips  # noqa: E402
from character_config import load_config  # noqa: E402
from retarget import ALIGNED_TARGETS, ARM_ABDUCTION_DEG, BONE_MAP, GROUND_BONE, Retargeter, _lowest_point, bake_clips  # noqa: E402
from rig_builder import REGION_ATTRIBUTE, action_fcurves, body_height, build_character  # noqa: E402

FBX_TIME_PER_SECOND = 46186158000
FPS = 30
EXPECTED_BONES = 53  # MPFB game_engine rig: Root + 52, including 3 bones per finger
FINGER_BONES = [f"{finger}_0{segment}_{side}" for side in ("l", "r") for finger in ("thumb", "index", "middle", "ring", "pinky") for segment in (1, 2, 3)]
CHARACTER_FRONT = Vector((0, -1, 0))  # MPFB characters face -Y
failed = False


def check(name: str, ok: bool, detail: str = "") -> None:
    global failed
    failed |= not ok
    print(f"PASS {name}" if ok else f"FAIL {name}: {detail}")


def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def fbx_takes(path: Path) -> dict[str, tuple[float, float]]:
    """Take (AnimationStack) name -> (LocalStart, LocalStop) in frames, read
    from the raw FBX — the names and ranges an importer sees."""
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
    """Location channels that actually move, other than the Root bone's
    ground-contact offset (bones themselves only rotate)."""
    return [f"{action.name}:{curve.data_path}" for action in bpy.data.actions for curve in action_fcurves(action)
            if "location" in curve.data_path and f'"{GROUND_BONE}"' not in curve.data_path
            and len({round(point.co.y, 5) for point in curve.keyframe_points}) > 1]


def glb_summary(path: Path) -> dict:
    data = path.read_bytes()
    json_length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_length])
    primitives = [primitive for mesh in gltf.get("meshes", []) for primitive in mesh["primitives"]]
    return {
        "vertices": sum(gltf["accessors"][primitive["attributes"]["POSITION"]]["count"] for primitive in primitives),
        "skinned": bool(primitives) and all("JOINTS_0" in primitive["attributes"] for primitive in primitives),
        "joints": [len(skin["joints"]) for skin in gltf.get("skins", [])],
        "textures": len(gltf.get("images", [])),
    }


def srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def baked_region_colour(obj, image_path: str, region: float) -> Vector | None:
    """Mean linear colour of a baked texture over one colour-slot region's UVs."""
    image = bpy.data.images.load(image_path)
    width, height = image.size
    pixels = image.pixels[:]
    uvs = obj.data.uv_layers.active.data
    mask = obj.data.color_attributes[REGION_ATTRIBUTE].data
    total, count = Vector((0.0, 0.0, 0.0)), 0
    for polygon in obj.data.polygons:
        for loop_index in polygon.loop_indices:
            if abs(mask[loop_index].color[0] - region) > 0.5:
                continue
            u, v = uvs[loop_index].uv
            offset = (min(height - 1, int((v % 1) * height)) * width + min(width - 1, int((u % 1) * width))) * 4
            total += Vector([srgb_to_linear(pixels[offset + channel]) for channel in range(3)])
            count += 1
    bpy.data.images.remove(image)
    return total / count if count else None


def check_outputs(config_path: Path, output_dir: Path) -> None:
    config = load_config(config_path)
    character = config["character_id"]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))

    listed = [manifest["blend"], manifest["thumbnail"], manifest["fbx"], manifest["model_fbx"], manifest["preview_glb"], *manifest["animation_fbx"].values(),
              *manifest["textures"].values(), *manifest["baked_textures"].values()]
    missing = [path for path in listed if path and not Path(path).is_file()]
    check(f"{character}: manifest files exist", not missing, f"missing {missing}")
    check(f"{character}: manifest clips match config", manifest["clips"] == config["clips"], f"{manifest['clips']} != {config['clips']}")

    # .blend (primary output).
    reset()
    bpy.ops.wm.open_mainfile(filepath=manifest["blend"])
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    armature = armatures[0] if len(armatures) == 1 else None
    bones = set(armature.data.bones.keys()) if armature else set()
    check(f"{character}: .blend has one armature with {EXPECTED_BONES} bones incl. all 30 finger bones",
          armature is not None and len(bones) == EXPECTED_BONES and set(FINGER_BONES) <= bones,
          f"armatures {len(armatures)}, bones {len(bones)}, missing fingers {sorted(set(FINGER_BONES) - bones)[:5]}")
    expected_parts = {".body", ".high-poly", ".eyebrow001", ".eyelashes01"} | {f".{config[key]}" for key in ("hair", "outfit", "shoes") if config[key]}
    found = {part for part in expected_parts if any(obj.name.endswith(part) for obj in meshes)}
    rigged = all(obj.parent == armature and any(m.type == "ARMATURE" and m.object == armature for m in obj.modifiers) for obj in meshes)
    check(f"{character}: .blend has body, eyes, brows, lashes, hair, outfit, shoes, all rigged", found == expected_parts and rigged,
          f"missing {sorted(expected_parts - found)}, all rigged {rigged}")
    actions = {action.name: action for action in bpy.data.actions}
    check(f"{character}: .blend has one fake-user Action per clip", sorted(actions) == sorted(config["clips"]) and all(action.use_fake_user for action in actions.values()),
          f"actions {[(name, action.use_fake_user) for name, action in actions.items()]}")
    active = armature.animation_data.action.name if armature and armature.animation_data and armature.animation_data.action else None
    check(f"{character}: .blend opens with the first clip assigned", active == config["clips"][0], f"active {active}")
    moving = moving_location_curves()
    check(f"{character}: .blend Actions only rotate bones (plus the Root ground offset)", not moving, f"{moving[:5]}")
    if config["ground_contact"]:
        grounded = all(any(curve.data_path == f'pose.bones["{GROUND_BONE}"].location' for curve in action_fcurves(action)) for action in actions.values())
        check(f"{character}: every Action has a Root ground-contact channel", grounded, "missing on some actions")
    textures = [image for image in bpy.data.images if image.filepath]
    check(f"{character}: .blend textures are packed", bool(textures) and all(image.packed_file for image in textures),
          f"{[(image.name, bool(image.packed_file)) for image in textures]}")
    if armature:
        armature.data.pose_position = "REST"
        bpy.context.view_layer.update()
        height = body_height(armature)
        check(f"{character}: body height matches target_height_m", abs(height - config["target_height_m"]) <= 0.01 * config["target_height_m"],
              f"{height:.3f} m vs {config['target_height_m']} m")
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated_vertices = 0
        for obj in meshes:
            evaluated = obj.evaluated_get(depsgraph)
            evaluated_vertices += len(evaluated.to_mesh().vertices)
            evaluated.to_mesh_clear()

    # Colour slots: the baked export textures must carry the configured colours.
    slots = [("top", 1.0, config["outfit"]), ("bottom", 0.0, config["outfit"]), ("shoes", 0.0, config["shoes"])]
    for slot, region, item in slots:
        colour = config["materials"][slot]
        if not item or colour[3] < 0.99:
            continue
        obj = next((o for o in meshes if o.name.endswith("." + item)), None)
        baked = manifest["baked_textures"].get(obj.active_material.name) if obj else None
        mean = baked_region_colour(obj, baked, region) if baked else None
        target = Vector(colour[:3])
        similar = mean is not None and mean.length > 0 and mean.normalized().dot(target.normalized()) > 0.97 and 0.4 < mean.length / target.length < 1.6
        check(f"{character}: {slot} colour slot shows in the baked texture", similar,
              f"mean {tuple(round(c, 3) for c in mean) if mean else None} vs target {tuple(colour[:3])}")

    # Combined FBX: bones, one take per clip, rotation-only, textures embedded.
    combined_takes = fbx_takes(Path(manifest["fbx"]))
    clip_of_take = {take.rsplit("|", 1)[-1]: frame_range for take, frame_range in combined_takes.items()}
    check(f"{character}: combined FBX has one take per clip", sorted(clip_of_take) == sorted(config["clips"]), f"takes {sorted(combined_takes)}")
    armatures, fbx_meshes = import_fbx(Path(manifest["fbx"]))
    bone_count = len(armatures[0].data.bones) if armatures else 0
    check(f"{character}: combined FBX has {EXPECTED_BONES} bones and {len(meshes)} meshes", bone_count == EXPECTED_BONES and len(fbx_meshes) == len(meshes),
          f"bones {bone_count}, meshes {len(fbx_meshes)}")
    moving = moving_location_curves()
    check(f"{character}: combined FBX only rotates bones (plus the Root ground offset)", not moving, f"{moving[:5]}")
    embedded = [image for image in bpy.data.images if image.packed_file or image.has_data]
    check(f"{character}: combined FBX embeds a base-colour texture per material", len(embedded) >= len(manifest["baked_textures"]),
          f"{len(embedded)} images for {len(manifest['baked_textures'])} materials")

    if manifest["model_fbx"]:
        armatures, model_meshes = import_fbx(Path(manifest["model_fbx"]))
        bone_count = len(armatures[0].data.bones) if armatures else 0
        check(f"{character}: model FBX has {EXPECTED_BONES} bones and the meshes", bone_count == EXPECTED_BONES and len(model_meshes) == len(meshes),
              f"bones {bone_count}, meshes {len(model_meshes)}")
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
            armatures, clip_meshes = import_fbx(Path(path))
            if len(armatures) != 1 or clip_meshes:
                bad_contents.append(f"{clip}: {len(armatures)} armatures, {len(clip_meshes)} meshes")
            elif len(armatures[0].data.bones) != EXPECTED_BONES:
                bad_contents.append(f"{clip}: {len(armatures[0].data.bones)} bones")
            elif moving_location_curves():
                bad_contents.append(f"{clip}: moving location curves")
        check(f"{character}: per-clip FBX are skeleton-only, {EXPECTED_BONES} bones, bones only rotate", not bad_contents, "; ".join(bad_contents[:5]))

    # GLB: skinned, textured, and carrying the modifier-applied geometry
    # (glTF can split vertices but never merges them).
    if manifest["preview_glb"]:
        summary = glb_summary(Path(manifest["preview_glb"]))
        check(f"{character}: GLB is skinned with {EXPECTED_BONES} joints and has textures", summary["skinned"] and summary["joints"] == [EXPECTED_BONES] and summary["textures"] > 0, f"{summary}")
        check(f"{character}: GLB has modifier-applied geometry", summary["vertices"] >= evaluated_vertices,
              f"GLB {summary['vertices']} vertices < evaluated meshes {evaluated_vertices}")


def front_direction(pose_bone) -> Vector:
    """World direction the bone's rest-pose 'forward' (the way the character
    faces, -Y) points to in the current pose."""
    delta = pose_bone.matrix.to_3x3() @ pose_bone.bone.matrix_local.to_3x3().inverted()
    return (delta @ CHARACTER_FRONT).normalized()


def elbow_flex_toward_front(pose_bones, side: str) -> float:
    """> 0 when the elbow bends the anatomical way (forearm toward the
    body's front); < 0 when it hyperextends."""
    upper = pose_bones[f"lowerarm_{side}"].head - pose_bones[f"upperarm_{side}"].head
    lower = pose_bones[f"hand_{side}"].head - pose_bones[f"lowerarm_{side}"].head
    perpendicular = lower - upper.normalized() * lower.dot(upper.normalized())
    if perpendicular.length < 1e-6:
        return 0.0
    return perpendicular.normalized().dot(front_direction(pose_bones["spine_03"]))


def check_poses(config_path: Path) -> None:
    clips = builtin_clips()
    reset()
    config = load_config(config_path)
    armature, meshes, _bones = build_character(config)
    actions = bake_clips(armature, clips, ground_meshes=meshes)
    body = next(obj for obj in meshes if obj.name.endswith(".body"))

    for clip_name in ("Idle", "Prone", "Crawl"):
        armature.animation_data.action = actions[clip_name]
        bpy.context.scene.frame_set(1)
        bpy.context.view_layer.update()
        pose_bones = armature.pose.bones
        chest = front_direction(pose_bones["spine_03"])
        head = front_direction(pose_bones["head"])
        if clip_name == "Idle":
            check(f"{clip_name}: chest faces forward (-Y)", chest.y < -0.95, f"chest front {tuple(round(c, 2) for c in chest)}")
            continue
        check(f"{clip_name}: chest faces the ground", chest.z < -0.9, f"chest front {tuple(round(c, 2) for c in chest)}")
        check(f"{clip_name}: head looks ahead, not up", head.z < 0 and head.y < -0.5, f"head front {tuple(round(c, 2) for c in head)}")
        flex = min(elbow_flex_toward_front(pose_bones, "l"), elbow_flex_toward_front(pose_bones, "r"))
        check(f"{clip_name}: elbows bend the natural way", flex > 0, f"flex {flex:.2f}")
        evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
        heights = [(body.matrix_world @ vertex.co).z for vertex in evaluated.vertices]
        print(f"INFO {clip_name} frame 1 body height range: {min(heights):.2f}..{max(heights):.2f} m (target_height_m {config['target_height_m']})")

    # Ground contact: on every frame, the character's lowest point is on the
    # floor, including poses that pivot around the hips; and the Root offset
    # only ever moves the character vertically.
    root = armature.pose.bones[GROUND_BONE]
    for clip_name in ("Idle", "Walk", "Sprint", "Prone", "Crawl", "Death", "Crouch", "Sit", "PickUp", "Kick"):
        armature.animation_data.action = actions[clip_name]
        worst, sideways = 0.0, 0.0
        for frame in range(1, int(actions[clip_name].frame_end) + 1):
            bpy.context.scene.frame_set(frame)
            worst = max(worst, abs(_lowest_point(meshes)))
            offset = armature.matrix_world.to_3x3() @ root.bone.matrix_local.to_3x3() @ root.location
            sideways = max(sideways, abs(offset.x), abs(offset.y))
        check(f"ground contact: {clip_name} stays on the floor every frame, Root moves only vertically", worst <= 0.005 and sideways <= 1e-4,
              f"lowest point off the floor by up to {worst * 100:.1f} cm, sideways offset {sideways:.5f}")

    # Hands. An open hand keeps MPFB's own sculpted hand (no finger or thumb
    # bone rotated); fingers don't fuse (skin between neighbouring middle
    # segments stays apart); a fist curls every fingertip back past its
    # knuckle; the OK sign's thumb and index skin actually touch. The first
    # two checks fail on the earlier retarget that forced fingers straight
    # and parallel (gaps of 2-7 mm, open-hand rotations up to 66 degrees).
    import numpy
    pose_bones = armature.pose.bones
    hand_bones = [name for name in pose_bones.keys() if name.endswith("_r") and name.split("_")[0] in ("thumb", "index", "middle", "ring", "pinky")]

    def at(clip_name, frame):
        armature.animation_data.action = actions[clip_name]
        bpy.context.scene.frame_set(frame)
        bpy.context.view_layer.update()

    def skin():
        hidden = [modifier for modifier in body.modifiers if modifier.type in ("MASK", "SUBSURF") and modifier.show_viewport]
        for modifier in hidden:
            modifier.show_viewport = False
        evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        coordinates = numpy.empty(len(mesh.vertices) * 3, dtype=numpy.float32)
        mesh.vertices.foreach_get("co", coordinates)
        evaluated.to_mesh_clear()
        for modifier in hidden:
            modifier.show_viewport = True
        return coordinates.reshape(-1, 3)

    def group(coordinates, name):
        index = body.vertex_groups[name].index
        return coordinates[[vertex.index for vertex in body.data.vertices if any(g.group == index and g.weight > 0.5 for g in vertex.groups)]]

    def skin_gap(coordinates, a, b):
        first, second = group(coordinates, a), group(coordinates, b)
        return float(numpy.sqrt(((first[:, None, :] - second[None, :, :]) ** 2).sum(-1)).min())

    at("Wave", 17)
    largest = max(math.degrees(pose_bones[name].rotation_quaternion.angle) for name in hand_bones)
    check("hands: Wave open hand keeps MPFB's natural hand (finger/thumb bones at rest)", largest <= 1.0, f"a finger bone is rotated {largest:.1f} deg")
    for clip_name, frame in (("Wave", 17), ("Idle", 1)):
        at(clip_name, frame)
        coordinates = skin()
        gaps = [skin_gap(coordinates, f"{a}_02_r", f"{b}_02_r") for a, b in (("index", "middle"), ("middle", "ring"), ("ring", "pinky"))]
        check(f"hands: {clip_name} fingers not fused (skin between neighbours >= 6 mm)", min(gaps) >= 0.006, f"gaps {[round(g * 1000, 1) for g in gaps]} mm")
    at("Punch", 1)
    wrist = pose_bones["hand_r"].head
    loose = [finger for finger in ("index", "middle", "ring", "pinky")
             if (pose_bones[f"{finger}_03_r"].tail - wrist).length >= (pose_bones[f"{finger}_01_r"].head - wrist).length]
    check("hands: Punch fist curls every fingertip back past its knuckle", not loose, f"not curled: {loose}")
    at("OKSign", 20)
    gap = skin_gap(skin(), "index_03_r", "thumb_03_r")
    check("hands: OKSign thumb and index fingertips touch (skin within 3 mm)", gap <= 0.003, f"gap {gap * 1000:.1f} mm")

    # Retarget accuracy: on every keyed frame of every clip, each arm and
    # hand bone must point where the authoring bone points (turned to
    # the character's facing), give or take the deliberate outward tilt.
    facing = Matrix.Rotation(math.pi, 3, "Z")
    worst = (0.0, "", 0, "")
    with Retargeter(armature) as retargeter:
        for clip_name, clip in clips.items():
            armature.animation_data.action = actions[clip_name]
            for frame, pose in clip["poses"].items():
                for pose_bone in retargeter.source.pose.bones:
                    pose_bone.rotation_euler = pose.get(pose_bone.name, (0.0, 0.0, 0.0))
                bpy.context.scene.frame_set(frame)
                bpy.context.view_layer.update()
                for source, target in BONE_MAP.items():
                    if target not in ALIGNED_TARGETS:
                        continue
                    wanted = facing @ retargeter.source.pose.bones[source].matrix.to_3x3().col[1]
                    actual = armature.pose.bones[target].matrix.to_3x3().col[1]
                    angle = math.degrees(wanted.angle(actual))
                    if angle > worst[0]:
                        worst = (angle, clip_name, frame, target)
    check("retarget: arm and hand directions match the authored clips (all clips, all keys)", worst[0] <= ARM_ABDUCTION_DEG + 1.0,
          f"worst {worst[0]:.1f} deg at {worst[1]} frame {worst[2]} {worst[3]}")


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if arguments[:1] == ["outputs"] and len(arguments) == 3:
        check_outputs(Path(arguments[1]), Path(arguments[2]))
    elif arguments[:1] == ["poses"] and len(arguments) == 2:
        check_poses(Path(arguments[1]))
    else:
        raise SystemExit(__doc__)
    sys.exit(1 if failed else 0)
