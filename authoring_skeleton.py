"""The skeleton the built-in clips are authored against.

The 12 built-in clips in animation_library.py are written as local Euler
rotations on this 52-bone skeleton (bone names like "UpperArm.L"). It is
never exported: rig_builder.py builds a temporary armature from it, poses
it, and retargets the motion onto the MPFB character's own rig (see
retarget.py). Only bone directions and parenting matter for that, so it is
built at fixed default proportions.

Coordinates: Blender Z-up, metres, the character faces +Y, its left side
is -X, arms hang straight down at rest. Authored in a 2.69 m-tall space
and scaled by `scale`.
"""

from __future__ import annotations

AUTHORING_HEIGHT_M = 1.75


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


def _bones(scale, shoulder, leg_x, arm_length, leg_length):
    # Hips at .90-1.15, torso (Spine/Chest/UpperChest) up to 1.95,
    # shoulders at 1.92, feet at .90-leg_length*2, in the 2.69 m authoring
    # space that build_character scales to target_height_m. Arms hang off a
    # Shoulder bone; feet end in a Toe bone.
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


def authoring_bones() -> dict[str, tuple]:
    """{bone name: (head, tail, parent name or None)} at default proportions."""
    scale = AUTHORING_HEIGHT_M / 2.69
    return _bones(scale, .52 * scale, .17 * scale, .48 * scale, .50 * scale)
