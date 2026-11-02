"""Bake suite clips onto the MPFB character's rig.

Built-in clips (and older custom clips) are authored as local Euler
rotations on the suite's authoring skeleton (authoring_skeleton.py: faces
+Y, arms hanging straight down). The character uses MPFB's game_engine rig
(faces -Y, arms in an A-pose, different bone names and bone rolls). For
each keyed frame this module:

1. poses a temporary authoring armature with the clip's rotations;
2. takes each authoring bone's rotation relative to its rest pose, in
   world space, turned 180 degrees about Z into the character's facing;
3. applies that rotation to the matching game_engine bone (fingers and
   thumbs are the exception, see FINGER_TARGETS). Arm and hand bones are
   first aligned to the authoring skeleton's rest
   direction (arms down), because that is what the
   clips assume "rest" looks like; spine, legs, feet, neck and head keep
   their own anatomical rest direction (re-aligning those would distort
   the body's natural curves);
4. keys the resulting local rotations as quaternions.

Bone motion is rotation-only. The one exception is optional ground
contact (ground_clip): a vertical offset keyed on the rig's Root bone so
the character's lowest point stays on the floor in every frame.

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
from mathutils import Matrix, Quaternion, Vector

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
                   if source.split(".")[0] in ("UpperArm", "Forearm", "Hand")}
# Finger and thumb bones are not world-transferred. They keep MPFB's own
# natural rest hand (spread, arch, thumb position) and follow the hand; the
# clip's finger values are read as anatomy instead (see _finger_rotation):
#   fingers: local Z = curl into the palm (signed per side, as _curl writes
#            it), local X = spread toward the thumb side;
#   thumb:   segment 1 local Z = swing toward the palm, local X (negative) =
#            swing across toward the little finger; segments 2-3 local Z =
#            bend.
# and applied about each MPFB bone's own hinge axes, derived from the hand.
FINGER_TARGETS = {target: source for source, target in BONE_MAP.items() if source.split(".")[0].rstrip("123") in _FINGERS}
# Authoring space faces +Y, MPFB faces -Y: a half turn about Z maps one onto the other.
_FACING = Matrix.Rotation(math.pi, 3, "Z")


# The authoring skeleton's arms hang straight down from wide-set shoulders.
# MPFB shoulders sit closer to the body, so straight-down arms would pass
# through the hips; the whole arm chain is tilted this far outward (about the
# character's front-back axis) while the arm hangs. The tilt fades out as the
# upper arm leaves the hanging position (full when pointing down along the
# torso, none once at right angles to it or raised): with the arms reaching forward it would
# only splay the hands apart (in two-handed swings by ~20 cm).
ARM_ABDUCTION_DEG = 10.0


def _arm_side(head) -> float:
    """+1 for a bone on the character's left (+X), -1 for its right."""
    return 1.0 if head.x >= 0 else -1.0


def _arm_abduction(side: float, weight: float = 1.0, axis: Vector = Vector((0.0, 1.0, 0.0))) -> Matrix:
    """Outward tilt for the character's left (+1) or right (-1) arm, about the
    torso's front-back axis (world Y at rest; it turns with the torso)."""
    return Matrix.Rotation(-side * math.radians(ARM_ABDUCTION_DEG) * weight, 3, axis)


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
        self.finger_axes = self._finger_axes()
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
                wanted = _FACING @ self.source_rest[self.source_for[name]].col[1]
                aligned[name] = carried.col[1].rotation_difference(wanted).to_matrix() @ carried
                self.alignment[name] = aligned[name] @ rest.inverted()
            elif name in self.source_for:
                self.alignment[name] = Matrix.Identity(3)
        return self

    def _finger_axes(self) -> dict[str, dict[str, Vector]]:
        """Per finger/thumb bone, its hinge axes in its own rest-local frame,
        from the character's rest hand: palm normal n (out of the palm),
        `across` (pinky -> index, toward the thumb side) and, for the thumb,
        `toward_pinky` (thumb base -> little finger base)."""
        bones = self.target.data.bones
        axes: dict[str, dict[str, Vector]] = {}
        for suffix, sign in (("l", 1.0), ("r", -1.0)):
            if f"hand_{suffix}" not in bones:
                continue
            head = lambda name: bones[f"{name}_{suffix}"].head_local
            direction = (head("middle_01") - head("hand")).normalized()
            across = (head("index_01") - head("pinky_01")).normalized()
            normal = direction.cross(across).normalized() * sign
            toward_pinky = (head("pinky_01") - head("thumb_01")).normalized()
            for target, source in FINGER_TARGETS.items():
                if not target.endswith("_" + suffix) or target not in bones:
                    continue
                rest = self.target_rest[target]
                y = rest.col[1].normalized()
                to_local = rest.inverted()

                def hinge(toward: Vector) -> Vector:
                    """Axis about which a positive rotation swings the bone toward `toward`."""
                    perpendicular = (toward - y * y.dot(toward)).normalized()
                    return (to_local @ y.cross(perpendicular)).normalized()

                if source.startswith("Thumb"):
                    axes[target] = {"palm": hinge(normal), "across": hinge(toward_pinky), "bend": hinge(toward_pinky)}
                else:
                    axes[target] = {"curl": hinge(normal), "spread": hinge(across)}
        return axes

    def _finger_rotation(self, target: str, source: str, euler) -> Matrix:
        """Local rotation of a finger/thumb bone from the clip's anatomical
        values (see FINGER_TARGETS)."""
        x, _y, z = euler
        inward = -z if source.endswith(".L") else z  # _curl / _side write left as -Z, right as +Z
        axes = self.finger_axes.get(target)
        if axes is None:
            return Matrix.Identity(3)
        if "curl" in axes:
            return Matrix.Rotation(x, 3, axes["spread"]) @ Matrix.Rotation(inward, 3, axes["curl"])
        if source.startswith("Thumb1"):
            return Matrix.Rotation(-x, 3, axes["across"]) @ Matrix.Rotation(inward, 3, axes["palm"])
        return Matrix.Rotation(inward, 3, axes["bend"])

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
            elif name in ALIGNED_TARGETS:
                delta = source_pose[source_name] @ self.source_rest[source_name].inverted()
                side = _arm_side(bone.head_local)
                upper_arm = source_pose["UpperArm." + ("L" if side > 0 else "R")].col[1]
                torso_up = source_pose["UpperChest"].col[1]
                # 1 hanging along the torso, 0 once at right angles to it or raised
                # (relative to the torso, so lying poses like Prone still count as hanging).
                hanging = max(0.0, -upper_arm.dot(torso_up))
                torso_turn = _FACING @ (source_pose["UpperChest"] @ self.source_rest["UpperChest"].inverted()) @ _FACING.inverted()
                tilt = _arm_abduction(side, hanging, torso_turn @ Vector((0.0, 1.0, 0.0)))
                desired[name] = tilt @ _FACING @ delta @ _FACING.inverted() @ self.alignment[name] @ rest
            elif name in FINGER_TARGETS:
                desired[name] = follow @ self._finger_rotation(name, source_name, pose.get(source_name, (0.0, 0.0, 0.0)))
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


GROUND_BONE = "Root"
GROUND_SAMPLE_STEP = 1


def _lowest_point(meshes) -> float:
    """Lowest world-space Z over the evaluated (posed) meshes."""
    import numpy
    depsgraph = bpy.context.evaluated_depsgraph_get()
    lowest = math.inf
    for obj in meshes:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        count = len(mesh.vertices)
        if count:
            coordinates = numpy.empty(count * 3, dtype=numpy.float32)
            mesh.vertices.foreach_get("co", coordinates)
            coordinates = coordinates.reshape(count, 3)
            matrix = numpy.array(obj.matrix_world)
            z = coordinates @ matrix[2, :3] + matrix[2, 3]
            lowest = min(lowest, float(z.min()))
        evaluated.to_mesh_clear()
    return lowest


def ground_clip(armature, action, meshes, keyed_frames) -> None:
    """Key a vertical offset on the Root bone so the lowest point of the
    character's meshes (shoes, body, clothes, hair) sits at Z = 0 in every
    sampled frame: every GROUND_SAMPLE_STEP frames, plus the clip's own
    keyed frames and its last frame. In-place loops stay in place; poses
    that pivot around the hips (Prone, Crawl, Death, Crouch, Sit...) come
    down to the floor instead of hovering."""
    root = armature.pose.bones.get(GROUND_BONE)
    if root is None:
        return
    scene = bpy.context.scene
    armature.animation_data.action = action
    root.location = (0.0, 0.0, 0.0)
    # World Z -> the Root bone's own (rest) axes, which pose-bone location uses.
    to_local = (armature.matrix_world.to_3x3() @ root.bone.matrix_local.to_3x3()).inverted()
    last = int(action.frame_end)
    frames = sorted(set(range(1, last + 1, GROUND_SAMPLE_STEP)) | {int(frame) for frame in keyed_frames} | {last})
    offsets = []
    for frame in frames:
        scene.frame_set(frame)
        offsets.append((frame, -_lowest_point(meshes)))
    for frame, offset in offsets:
        root.location = to_local @ Vector((0.0, 0.0, offset))
        root.keyframe_insert(data_path="location", frame=frame, group=GROUND_BONE)
    root.location = (0.0, 0.0, 0.0)


def bake_clips(armature, clips: dict[str, dict[str, Any]], ground_meshes=None) -> dict[str, Any]:
    """Bake several clips onto the character's armature as Actions, one per
    clip, named after it. Authoring-skeleton clips are retargeted; native
    (game_engine) clips are keyed directly. With ground_meshes, each clip
    also gets ground contact (see ground_clip)."""
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
    if ground_meshes:
        for name, action in actions.items():
            ground_clip(armature, action, ground_meshes, clips[name]["poses"].keys())
    return actions
