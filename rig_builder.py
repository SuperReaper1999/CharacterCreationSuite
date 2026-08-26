"""Shared rig/mesh construction for the Character Creation Suite.

Used by both the headless export worker (blender_build.py) and the
interactive per-clip preview (blender_preview.py), so both always build
the exact same armature and skin from a config — there is only one place
that defines what "the rig" is.

Two rig types are supported (config["rig_type"]):
- "standard" (default): the original fixed 16-bone humanoid.
- "extended": the same skeleton with Spine, UpperChest, Shoulder.L/R,
  Toe.L/R, and full 3-bone-per-finger hands (Thumb/Index/Middle/Ring/
  Little, each split into Proximal/Intermediate/Distal — Unity's own
  Humanoid finger convention, named "<Finger>1/2/3.<L|R>") added — all
  standard bone names still exist at the same positions, so every clip
  authored for "standard" bakes correctly on "extended" too; it just
  leaves the new bones at rest.
"""

from __future__ import annotations

from typing import Any

import bpy


def action_fcurves(action):
    """Compatibility shim for Blender <=4.x and Blender 4.4+/5.x Actions."""
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                yield from getattr(channelbag, "fcurves", [])


def bake_pose_action(armature, clip_name: str, clip: dict[str, Any]):
    """Bake one clip's keyframed poses onto armature as a new Action.

    Bone names the clip references that don't exist on this armature are
    skipped rather than raising — this is what lets an "Extended"-suffixed
    clip (or a custom preset saved from the extended rig) be selected
    safely even for a "standard" build; the extra bones just don't animate.
    """
    action = bpy.data.actions.new(clip_name)
    action.use_frame_range = True
    action.frame_start = 1
    action.frame_end = clip["frames"]
    armature.animation_data.action = action
    for frame, pose in clip["poses"].items():
        bpy.context.scene.frame_set(frame)
        for bone in armature.pose.bones:
            bone.rotation_mode = "XYZ"; bone.rotation_euler = (0, 0, 0)
        for bone_name, rotation in pose.items():
            if bone_name in armature.pose.bones:
                armature.pose.bones[bone_name].rotation_euler = rotation
        for bone in armature.pose.bones:
            bone.keyframe_insert(data_path="rotation_euler", frame=frame)
    for curve in action_fcurves(action):
        for point in curve.keyframe_points:
            point.interpolation = "BEZIER"
    return action


def _standard_bones(scale, shoulder, leg_x, arm_length, leg_length):
    return {
        "Hips": ((0, 0, .90 * scale), (0, 0, 1.15 * scale), None), "Chest": ((0, 0, 1.15 * scale), (0, 0, 1.95 * scale), "Hips"),
        "Neck": ((0, 0, 1.95 * scale), (0, 0, 2.05 * scale), "Chest"), "Head": ((0, 0, 2.05 * scale), (0, 0, 2.56 * scale), "Neck"),
        "UpperArm.L": ((-shoulder, 0, 1.92 * scale), (-shoulder, 0, 1.92 * scale - arm_length), "Chest"), "Forearm.L": ((-shoulder, 0, 1.92 * scale - arm_length), (-shoulder, 0, 1.92 * scale - arm_length * 2), "UpperArm.L"), "Hand.L": ((-shoulder, 0, 1.92 * scale - arm_length * 2), (-shoulder, 0, 1.92 * scale - arm_length * 2 - .18 * scale), "Forearm.L"),
        "UpperArm.R": ((shoulder, 0, 1.92 * scale), (shoulder, 0, 1.92 * scale - arm_length), "Chest"), "Forearm.R": ((shoulder, 0, 1.92 * scale - arm_length), (shoulder, 0, 1.92 * scale - arm_length * 2), "UpperArm.R"), "Hand.R": ((shoulder, 0, 1.92 * scale - arm_length * 2), (shoulder, 0, 1.92 * scale - arm_length * 2 - .18 * scale), "Forearm.R"),
        "UpperLeg.L": ((-leg_x, 0, .90 * scale), (-leg_x, 0, .90 * scale - leg_length), "Hips"), "LowerLeg.L": ((-leg_x, 0, .90 * scale - leg_length), (-leg_x, 0, .90 * scale - leg_length * 2), "UpperLeg.L"), "Foot.L": ((-leg_x, 0, .90 * scale - leg_length * 2), (-leg_x, .35 * scale, .90 * scale - leg_length * 2), "LowerLeg.L"),
        "UpperLeg.R": ((leg_x, 0, .90 * scale), (leg_x, 0, .90 * scale - leg_length), "Hips"), "LowerLeg.R": ((leg_x, 0, .90 * scale - leg_length), (leg_x, 0, .90 * scale - leg_length * 2), "UpperLeg.R"), "Foot.R": ((leg_x, 0, .90 * scale - leg_length * 2), (leg_x, .35 * scale, .90 * scale - leg_length * 2), "LowerLeg.R"),
    }


# Anatomical order outward (away from body) to inward (toward body):
# Little is furthest from the midline, Thumb is closest and also the one
# that sits higher on the hand and angles forward instead of hanging
# straight down. Values are offsets in units of `gap`, applied in the
# hand's own outward direction (mirrored per side by the `sign` in
# _finger_bones/_finger_parts), not raw signed coordinates.
_FINGER_OFFSETS = {"Little": 1.5, "Ring": 0.5, "Middle": -0.5, "Index": -1.5, "Thumb": -2.4}
# Proximal/Intermediate/Distal, as fractions of the finger's total length —
# Unity's full 3-bone-per-finger convention, tapering like a real finger.
_FINGER_SEGMENT_FRACTIONS = (0.45, 0.35, 0.20)


def _finger_geometry(scale, shoulder, arm_length, side):
    """Shared per-finger start point + full-length direction vector, used
    by both _finger_bones and _finger_parts so the two can't drift apart."""
    sign = -1 if side == "L" else 1
    hand_x = sign * shoulder
    hand_bottom_z = 1.92 * scale - arm_length * 2 - .18 * scale
    gap = .065 * scale
    length = .095 * scale
    thumb_length = .075 * scale
    geometry = {}
    for finger, offset in _FINGER_OFFSETS.items():
        x = hand_x + sign * offset * gap
        if finger == "Thumb":
            start = (x, .04 * scale, hand_bottom_z + .05 * scale)
            direction = (sign * .03 * scale, .03 * scale, -thumb_length)
        else:
            start = (x, 0, hand_bottom_z)
            direction = (0, 0, -length)
        geometry[finger] = (start, direction)
    return geometry


def _finger_bones(scale, shoulder, arm_length, side):
    bones = {}
    for finger, (start, direction) in _finger_geometry(scale, shoulder, arm_length, side).items():
        point = start
        parent = f"Hand.{side}"
        for index, fraction in enumerate(_FINGER_SEGMENT_FRACTIONS, start=1):
            end = tuple(point[axis] + direction[axis] * fraction for axis in range(3))
            name = f"{finger}{index}.{side}"
            bones[name] = (point, end, parent)
            parent = name
            point = end
    return bones


def _finger_parts(scale, shoulder, arm_length, side):
    box = .035 * scale
    parts = []
    for finger, (start, direction) in _finger_geometry(scale, shoulder, arm_length, side).items():
        point = start
        for index, fraction in enumerate(_FINGER_SEGMENT_FRACTIONS, start=1):
            end = tuple(point[axis] + direction[axis] * fraction for axis in range(3))
            center = tuple((point[axis] + end[axis]) / 2 for axis in range(3))
            size = (box, box, max(abs(direction[2]) * fraction, box))
            name = f"{finger}{index}.{side}"
            parts.append((name, size, center, "skin", name))
            point = end
    return parts


def _extended_bones(scale, shoulder, leg_x, arm_length, leg_length):
    # Same overall silhouette as the standard rig (Hips at .90-1.15, torso
    # top at 1.95, shoulders at 1.92, feet at .90-leg_length*2) — the torso
    # is just subdivided into Spine/Chest/UpperChest instead of one bone,
    # arms hang off a Shoulder bone instead of straight off the torso, and
    # feet gain a Toe bone. Every standard bone name/position is preserved
    # exactly, so standard-authored clips still bake correctly here.
    bones = {
        "Hips": ((0, 0, .90 * scale), (0, 0, 1.15 * scale), None),
        "Spine": ((0, 0, 1.15 * scale), (0, 0, 1.35 * scale), "Hips"),
        "Chest": ((0, 0, 1.35 * scale), (0, 0, 1.65 * scale), "Spine"),
        "UpperChest": ((0, 0, 1.65 * scale), (0, 0, 1.95 * scale), "Chest"),
        "Neck": ((0, 0, 1.95 * scale), (0, 0, 2.05 * scale), "UpperChest"), "Head": ((0, 0, 2.05 * scale), (0, 0, 2.56 * scale), "Neck"),
        "Shoulder.L": ((0, 0, 1.92 * scale), (-shoulder, 0, 1.92 * scale), "UpperChest"),
        "UpperArm.L": ((-shoulder, 0, 1.92 * scale), (-shoulder, 0, 1.92 * scale - arm_length), "Shoulder.L"), "Forearm.L": ((-shoulder, 0, 1.92 * scale - arm_length), (-shoulder, 0, 1.92 * scale - arm_length * 2), "UpperArm.L"), "Hand.L": ((-shoulder, 0, 1.92 * scale - arm_length * 2), (-shoulder, 0, 1.92 * scale - arm_length * 2 - .18 * scale), "Forearm.L"),
        "Shoulder.R": ((0, 0, 1.92 * scale), (shoulder, 0, 1.92 * scale), "UpperChest"),
        "UpperArm.R": ((shoulder, 0, 1.92 * scale), (shoulder, 0, 1.92 * scale - arm_length), "Shoulder.R"), "Forearm.R": ((shoulder, 0, 1.92 * scale - arm_length), (shoulder, 0, 1.92 * scale - arm_length * 2), "UpperArm.R"), "Hand.R": ((shoulder, 0, 1.92 * scale - arm_length * 2), (shoulder, 0, 1.92 * scale - arm_length * 2 - .18 * scale), "Forearm.R"),
        "UpperLeg.L": ((-leg_x, 0, .90 * scale), (-leg_x, 0, .90 * scale - leg_length), "Hips"), "LowerLeg.L": ((-leg_x, 0, .90 * scale - leg_length), (-leg_x, 0, .90 * scale - leg_length * 2), "UpperLeg.L"), "Foot.L": ((-leg_x, 0, .90 * scale - leg_length * 2), (-leg_x, .35 * scale, .90 * scale - leg_length * 2), "LowerLeg.L"),
        "Toe.L": ((-leg_x, .35 * scale, .90 * scale - leg_length * 2), (-leg_x, .55 * scale, .90 * scale - leg_length * 2), "Foot.L"),
        "UpperLeg.R": ((leg_x, 0, .90 * scale), (leg_x, 0, .90 * scale - leg_length), "Hips"), "LowerLeg.R": ((leg_x, 0, .90 * scale - leg_length), (leg_x, 0, .90 * scale - leg_length * 2), "UpperLeg.R"), "Foot.R": ((leg_x, 0, .90 * scale - leg_length * 2), (leg_x, .35 * scale, .90 * scale - leg_length * 2), "LowerLeg.R"),
        "Toe.R": ((leg_x, .35 * scale, .90 * scale - leg_length * 2), (leg_x, .55 * scale, .90 * scale - leg_length * 2), "Foot.R"),
    }
    bones.update(_finger_bones(scale, shoulder, arm_length, "L"))
    bones.update(_finger_bones(scale, shoulder, arm_length, "R"))
    return bones


def _standard_parts(scale, shoulder, leg_x, arm_length, leg_length, body, torso, head):
    return [
        ("Hips", (.55 * scale * body, .28 * scale, .25 * scale), (0, 0, 1.00 * scale), "bottom", "Hips"), ("Torso", (.60 * scale * body, .30 * scale, .80 * scale * torso), (0, 0, 1.55 * scale), "top", "Chest"),
        ("Neck", (.18 * scale, .18 * scale, .15 * scale), (0, 0, 2.00 * scale), "skin", "Neck"), ("Head", (.42 * scale * head, .42 * scale * head, .42 * scale * head), (0, 0, 2.30 * scale), "skin", "Head"),
        ("UpperArm.L", (.22 * scale, .22 * scale, arm_length), (-shoulder, 0, 1.92 * scale - arm_length / 2), "top", "UpperArm.L"), ("Forearm.L", (.20 * scale, .20 * scale, arm_length * .9375), (-shoulder, 0, 1.92 * scale - arm_length * 1.5), "skin", "Forearm.L"), ("Hand.L", (.22 * scale, .22 * scale, .18 * scale), (-shoulder, 0, 1.92 * scale - arm_length * 2 - .09 * scale), "skin", "Hand.L"),
        ("UpperArm.R", (.22 * scale, .22 * scale, arm_length), (shoulder, 0, 1.92 * scale - arm_length / 2), "top", "UpperArm.R"), ("Forearm.R", (.20 * scale, .20 * scale, arm_length * .9375), (shoulder, 0, 1.92 * scale - arm_length * 1.5), "skin", "Forearm.R"), ("Hand.R", (.22 * scale, .22 * scale, .18 * scale), (shoulder, 0, 1.92 * scale - arm_length * 2 - .09 * scale), "skin", "Hand.R"),
        ("UpperLeg.L", (.23 * scale * body, .24 * scale, leg_length), (-leg_x, 0, .90 * scale - leg_length / 2), "bottom", "UpperLeg.L"), ("LowerLeg.L", (.21 * scale * body, .22 * scale, leg_length), (-leg_x, 0, .90 * scale - leg_length * 1.5), "bottom", "LowerLeg.L"), ("Foot.L", (.25 * scale * body, .45 * scale, .16 * scale), (-leg_x, .175 * scale, .90 * scale - leg_length * 2), "shoes", "Foot.L"),
        ("UpperLeg.R", (.23 * scale * body, .24 * scale, leg_length), (leg_x, 0, .90 * scale - leg_length / 2), "bottom", "UpperLeg.R"), ("LowerLeg.R", (.21 * scale * body, .22 * scale, leg_length), (leg_x, 0, .90 * scale - leg_length * 1.5), "bottom", "LowerLeg.R"), ("Foot.R", (.25 * scale * body, .45 * scale, .16 * scale), (leg_x, .175 * scale, .90 * scale - leg_length * 2), "shoes", "Foot.R"),
    ]


def _extended_parts(scale, shoulder, leg_x, arm_length, leg_length, body, torso, head):
    # Same Torso footprint (.60*body x .30 x .80*torso, spanning z 1.15-1.95)
    # as the standard rig, just split into three stacked boxes matching the
    # Spine/Chest/UpperChest bone ranges (heights .20/.30/.30, summing to
    # the standard rig's .80) so subdividing the spine actually deforms the
    # torso instead of leaving one rigid box. Arm/leg boxes are identical to
    # the standard rig — they bind by bone name, which exists unchanged
    # here, only the parent chain above them differs.
    parts = [
        ("Hips", (.55 * scale * body, .28 * scale, .25 * scale), (0, 0, 1.00 * scale), "bottom", "Hips"),
        ("Spine", (.58 * scale * body, .29 * scale, .20 * scale * torso), (0, 0, 1.25 * scale), "top", "Spine"),
        ("Chest", (.60 * scale * body, .30 * scale, .30 * scale * torso), (0, 0, 1.50 * scale), "top", "Chest"),
        ("UpperChest", (.60 * scale * body, .30 * scale, .30 * scale * torso), (0, 0, 1.80 * scale), "top", "UpperChest"),
        ("Neck", (.18 * scale, .18 * scale, .15 * scale), (0, 0, 2.00 * scale), "skin", "Neck"), ("Head", (.42 * scale * head, .42 * scale * head, .42 * scale * head), (0, 0, 2.30 * scale), "skin", "Head"),
        ("UpperArm.L", (.22 * scale, .22 * scale, arm_length), (-shoulder, 0, 1.92 * scale - arm_length / 2), "top", "UpperArm.L"), ("Forearm.L", (.20 * scale, .20 * scale, arm_length * .9375), (-shoulder, 0, 1.92 * scale - arm_length * 1.5), "skin", "Forearm.L"), ("Hand.L", (.22 * scale, .22 * scale, .18 * scale), (-shoulder, 0, 1.92 * scale - arm_length * 2 - .09 * scale), "skin", "Hand.L"),
        ("UpperArm.R", (.22 * scale, .22 * scale, arm_length), (shoulder, 0, 1.92 * scale - arm_length / 2), "top", "UpperArm.R"), ("Forearm.R", (.20 * scale, .20 * scale, arm_length * .9375), (shoulder, 0, 1.92 * scale - arm_length * 1.5), "skin", "Forearm.R"), ("Hand.R", (.22 * scale, .22 * scale, .18 * scale), (shoulder, 0, 1.92 * scale - arm_length * 2 - .09 * scale), "skin", "Hand.R"),
        ("UpperLeg.L", (.23 * scale * body, .24 * scale, leg_length), (-leg_x, 0, .90 * scale - leg_length / 2), "bottom", "UpperLeg.L"), ("LowerLeg.L", (.21 * scale * body, .22 * scale, leg_length), (-leg_x, 0, .90 * scale - leg_length * 1.5), "bottom", "LowerLeg.L"), ("Foot.L", (.25 * scale * body, .45 * scale, .16 * scale), (-leg_x, .175 * scale, .90 * scale - leg_length * 2), "shoes", "Foot.L"),
        ("Toe.L", (.20 * scale * body, .20 * scale, .10 * scale), (-leg_x, .45 * scale, .90 * scale - leg_length * 2), "shoes", "Toe.L"),
        ("UpperLeg.R", (.23 * scale * body, .24 * scale, leg_length), (leg_x, 0, .90 * scale - leg_length / 2), "bottom", "UpperLeg.R"), ("LowerLeg.R", (.21 * scale * body, .22 * scale, leg_length), (leg_x, 0, .90 * scale - leg_length * 1.5), "bottom", "LowerLeg.R"), ("Foot.R", (.25 * scale * body, .45 * scale, .16 * scale), (leg_x, .175 * scale, .90 * scale - leg_length * 2), "shoes", "Foot.R"),
        ("Toe.R", (.20 * scale * body, .20 * scale, .10 * scale), (leg_x, .45 * scale, .90 * scale - leg_length * 2), "shoes", "Toe.R"),
    ]
    parts += _finger_parts(scale, shoulder, arm_length, "L")
    parts += _finger_parts(scale, shoulder, arm_length, "R")
    return parts


def build_character(config: dict[str, Any]) -> tuple[Any, Any, dict[str, tuple]]:
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
    extended = config.get("rig_type") == "extended"
    bones = (_extended_bones if extended else _standard_bones)(scale, shoulder, leg_x, arm_length, leg_length)

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
    parts = (_extended_parts if extended else _standard_parts)(scale, shoulder, leg_x, arm_length, leg_length, body, torso, head)
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

    return armature, mesh, bones


def export_material_textures(config: dict[str, Any], output_dir) -> dict[str, str]:
    """Bake each of the 4 material colours (skin/top/bottom/shoes) out as a
    small standalone solid-colour PNG under output_dir/Textures/, and wire
    that image into the material's Base Color so the body parts using it
    are backed by an actual texture asset, not just a flat material value —
    for Unity texture-based shaders, and so the colour is something an
    artist can open and paint over later. Every body part already maps to
    one of these 4 materials (see _standard_parts/_extended_parts), so
    texturing the material automatically textures every part that uses
    it — this doesn't generate one file per body part name, since most of
    those would be pixel-identical duplicates of each other.

    Only call this from the real export path (blender_build.py) — it
    writes files, which the interactive preview deliberately never does.
    Must run after build_character() (the materials it looks up by name
    are created there) and before any FBX export (so the export picks up
    the texture-carrying materials).
    """
    textures_dir = output_dir / "Textures"
    textures_dir.mkdir(parents=True, exist_ok=True)
    texture_paths: dict[str, str] = {}
    for key, color in config["materials"].items():
        material_name = f"{config['character_id']}_{key}"
        material = bpy.data.materials.get(material_name)
        if material is None:
            continue
        image = bpy.data.images.new(f"{material_name}_Texture", width=8, height=8, alpha=True)
        image.pixels = list(color) * (image.size[0] * image.size[1])
        path = textures_dir / f"{material_name}.png"
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()

        material.use_nodes = True
        nodes = material.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        texture_node = nodes.new("ShaderNodeTexImage")
        texture_node.image = image
        if bsdf:
            texture_node.location = (bsdf.location.x - 300, bsdf.location.y)
            material.node_tree.links.new(texture_node.outputs["Color"], bsdf.inputs["Base Color"])
        texture_paths[key] = str(path)
    return texture_paths
