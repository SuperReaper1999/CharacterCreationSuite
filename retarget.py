"""Bake suite clips onto the MPFB character's rig.

Built-in clips (and older custom clips) are authored as local Euler
rotations on the suite's authoring skeleton (authoring_skeleton.py: faces
+Y, arms hanging straight down). The character uses MPFB's game_engine rig
(faces -Y, arms in an A-pose, different bone names and bone rolls). For
each keyed frame this module:

1. poses a temporary authoring armature with the clip's rotations;
2. takes each authoring bone's rotation relative to its rest pose, in
   world space, turned 180 degrees about Z into the character's facing;
3. applies that rotation to the matching game_engine bone. Arm, hand and
   finger bones are first aligned to the authoring skeleton's rest
   direction (arms down, fingers straight), because that is what the
   clips assume "rest" looks like; spine, legs, feet, neck and head keep
   their own anatomical rest direction (re-aligning those would distort
   the body's natural curves);
4. keys the resulting local rotations as quaternions. Rotation only: no
   location keys are ever written.

Because the transfer is done in world space, bone rolls and naming
conventions of the two rigs don't matter, and the result adapts to each
character's own proportions.

Clips saved from the Blender preview editor are already in game_engine
bone space (custom_clips.py "native" clips); bake_native_clip keys those
directly.
"""

from __future__ import annotations

import math
from typing import Any

import bpy
from mathutils import Matrix, Quaternion

from authoring_skeleton import authoring_bones

_SIDES = {"L": "l", "R": "r"}
_FINGERS = {"Thumb": "thumb", "Index": "index", "Middle": "middle", "Ring": "ring", "Little": "pinky"}


def _bone_map() -> dict[str, str]:
    """Authoring bone -> game_engine bone."""
    mapping = {"Hips": "pelvis", "Spine": "spine_01", "Chest": "spine_02", "UpperChest": "spine_03", "Neck": "neck_01", "Head": "head"}
    for side, suffix in _SIDES.items():
        for source, target in (("Shoulder", "clavicle"), ("UpperArm", "upperarm"), ("Forearm", "lowerarm"), ("Hand", "hand"),
                               ("UpperLeg", "thigh"), ("LowerLeg", "calf"), ("Foot", "foot"), ("Toe", "ball")):
            mapping[f"{source}.{side}"] = f"{target}_{suffix}"
        for finger, target in _FINGERS.items():
            for segment in (1, 2, 3):
                mapping[f"{finger}{segment}.{side}"] = f"{target}_0{segment}_{suffix}"
    return mapping


BONE_MAP = _bone_map()
# Target bones re-aligned to the authoring skeleton's rest direction.
ALIGNED_TARGETS = {target for source, target in BONE_MAP.items()
                   if source.split(".")[0].rstrip("123") in ("UpperArm", "Forearm", "Hand", *_FINGERS)}
# Authoring space faces +Y, MPFB faces -Y: a half turn about Z maps one onto the other.
_FACING = Matrix.Rotation(math.pi, 3, "Z")


# The authoring skeleton's arms hang straight down from wide-set shoulders.
# MPFB shoulders sit closer to the body, so straight-down arms would pass
# through the hips; tilting the whole arm chain this far outward (about the
# character's front-back axis) gives a natural relaxed hang instead.
ARM_ABDUCTION_DEG = 10.0


def _arm_abduction(head) -> Matrix:
    """Outward tilt for an arm bone on the character's left (+X) or right (-X)."""
    side = 1.0 if head.x >= 0 else -1.0
    return Matrix.Rotation(-side * math.radians(ARM_ABDUCTION_DEG), 3, "Y")


def _hierarchy_order(armature) -> list[Any]:
    ordered = []

    def visit(bone):
        ordered.append(bone)
        for child in bone.children:
            visit(child)

    for bone in armature.data.bones:
        if bone.parent is None:
            visit(bone)
    return ordered


class Retargeter:
    """Holds a temporary authoring armature; use as a context manager so
    it is always removed again."""

    def __init__(self, target_armature):
        self.target = target_armature
        self.source = None

    def __enter__(self):
        data = bpy.data.armatures.new("_ccs_authoring_skeleton")
        self.source = bpy.data.objects.new("_ccs_authoring_skeleton", data)
        bpy.context.scene.collection.objects.link(self.source)
        previous_active = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = self.source
        bpy.ops.object.mode_set(mode="EDIT")
        bones = authoring_bones()
        created = {}
        for name, (head, tail, _parent) in bones.items():
            bone = data.edit_bones.new(name)
            bone.head, bone.tail = head, tail
            created[name] = bone
        for name, (_head, _tail, parent) in bones.items():
            if parent:
                created[name].parent = created[parent]
                created[name].use_connect = False
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.context.view_layer.objects.active = previous_active
        for pose_bone in self.source.pose.bones:
            pose_bone.rotation_mode = "XYZ"

        self.source_rest = {bone.name: bone.matrix_local.to_3x3() for bone in data.bones}
        self.target_rest = {bone.name: bone.matrix_local.to_3x3() for bone in self.target.data.bones}
        self.order = _hierarchy_order(self.target)
        self.source_for = {target: source for source, target in BONE_MAP.items()}
        # Aligned rest frames, computed down the hierarchy: each aligned
        # bone first moves rigidly with its (already aligned) parent, then
        # swings about its head to point the way the authoring bone points.
        # Carrying the parent's motion keeps the arm's natural twist — the
        # A-pose palms face down, and lowering the arm turns them toward
        # the thighs, as on the authoring skeleton.
        aligned: dict[str, Matrix] = {}
        self.alignment = {}
        for bone in self.order:
            name, rest = bone.name, self.target_rest[bone.name]
            if name in ALIGNED_TARGETS:
                parent = bone.parent.name
                carried = aligned[parent] @ self.target_rest[parent].inverted() @ rest if parent in aligned else rest
                wanted = _arm_abduction(self.target.data.bones[name].head_local) @ _FACING @ self.source_rest[self.source_for[name]].col[1]
                aligned[name] = carried.col[1].rotation_difference(wanted).to_matrix() @ carried
                self.alignment[name] = aligned[name] @ rest.inverted()
            elif name in self.source_for:
                self.alignment[name] = Matrix.Identity(3)
        return self

    def __exit__(self, *exc):
        data = self.source.data
        bpy.data.objects.remove(self.source, do_unlink=True)
        bpy.data.armatures.remove(data)
        return False

    def local_rotations(self, pose: dict[str, tuple[float, float, float]]) -> dict[str, Quaternion]:
        """Game_engine local rotations (pose-bone space) for one authoring pose."""
        for pose_bone in self.source.pose.bones:
            pose_bone.rotation_euler = pose.get(pose_bone.name, (0.0, 0.0, 0.0))
        bpy.context.view_layer.update()
        source_pose = {pose_bone.name: pose_bone.matrix.to_3x3() for pose_bone in self.source.pose.bones}

        desired: dict[str, Matrix] = {}
        local: dict[str, Quaternion] = {}
        for bone in self.order:
            name = bone.name
            rest = self.target_rest[name]
            parent_rest = self.target_rest[bone.parent.name] if bone.parent else Matrix.Identity(3)
            parent_desired = desired[bone.parent.name] if bone.parent else Matrix.Identity(3)
            follow = parent_desired @ parent_rest.inverted() @ rest
            source_name = self.source_for.get(name)
            if source_name is None:
                desired[name] = follow
            else:
                delta = source_pose[source_name] @ self.source_rest[source_name].inverted()
                desired[name] = _FACING @ delta @ _FACING.inverted() @ self.alignment[name] @ rest
            local[name] = (follow.inverted() @ desired[name]).to_quaternion()
        return local


def _new_action(armature, clip_name: str, frames: int):
    action = bpy.data.actions.new(clip_name)
    action.use_frame_range = True
    action.frame_start = 1
    action.frame_end = frames
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action
    for pose_bone in armature.pose.bones:
        pose_bone.rotation_mode = "QUATERNION"
        pose_bone.location = (0.0, 0.0, 0.0)
        pose_bone.scale = (1.0, 1.0, 1.0)
    return action


def _key_frames(armature, action, keyed: dict[int, dict[str, Quaternion]]):
    previous: dict[str, Quaternion] = {}
    for frame in sorted(keyed):
        for pose_bone in armature.pose.bones:
            rotation = keyed[frame].get(pose_bone.name, Quaternion())
            # Keep consecutive keys in the same hemisphere so interpolation
            # takes the short way round.
            if pose_bone.name in previous and previous[pose_bone.name].dot(rotation) < 0:
                rotation = -rotation
            previous[pose_bone.name] = rotation
            pose_bone.rotation_quaternion = rotation
            pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    from rig_builder import action_fcurves
    for curve in action_fcurves(action):
        for point in curve.keyframe_points:
            point.interpolation = "BEZIER"
    return action


def bake_clips(armature, clips: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Bake several clips onto the character's armature as Actions, one per
    clip, named after it. Authoring-skeleton clips are retargeted; native
    (game_engine) clips are keyed directly."""
    actions = {}
    authoring = {name: clip for name, clip in clips.items() if clip.get("skeleton", "authoring") == "authoring"}
    if authoring:
        with Retargeter(armature) as retargeter:
            for name, clip in authoring.items():
                keyed = {frame: retargeter.local_rotations(pose) for frame, pose in clip["poses"].items()}
                actions[name] = _key_frames(armature, _new_action(armature, name, clip["frames"]), keyed)
    for name, clip in clips.items():
        if name not in authoring:
            keyed = {frame: {bone: Quaternion(rotation) for bone, rotation in pose.items()} for frame, pose in clip["poses"].items()}
            actions[name] = _key_frames(armature, _new_action(armature, name, clip["frames"]), keyed)
    return actions
