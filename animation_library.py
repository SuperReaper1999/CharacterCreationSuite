"""Fixed-topology, rotation-only animation definitions for the suite.

Clips are authored on the main body bones (Hips, Chest, Neck, Head, arms,
legs, feet) in _authored_clips(). builtin_clips() then fills in the rest of
the 52-bone authoring skeleton (Spine/UpperChest, Shoulders, Toes, fingers) from those
values with _expand_pose(), so the extra joints follow the authored motion
instead of being keyed by hand in 12 places. retarget.py then transfers
the result onto the character's MPFB rig.
"""

from __future__ import annotations

import math
from typing import Any


def r(x: float, y: float = 0.0, z: float = 0.0) -> tuple[float, float, float]:
    return math.radians(x), math.radians(y), math.radians(z)


# Relaxed-hand curl per segment (Proximal, Intermediate, Distal) — curls
# more at the middle knuckle than the tip, like a hand actually at rest,
# rather than an equal bend at every joint.
# Degrees. Applied about each finger bone's local Z axis (world +Y on the
# authoring skeleton, whose palms face the thighs), signed per side so the
# fingers bend into the palm. (An earlier version bent them about X, which
# swings the fingertips forward toward the thumb instead.)
_FINGER_CURL = (12, 20, 14)
_THUMB_CURL = (8, 14, 10)


def _curl(degrees: float, side: str) -> tuple[float, float, float]:
    return r(0, 0, -degrees if side == "L" else degrees)


def clips() -> dict[str, dict[str, Any]]:
    """Built-in clips, overlaid with any user-saved preset animations from
    presets/animations/ (see custom_clips.py) so a preset with the same
    name deliberately replaces a built-in."""
    from custom_clips import list_custom_clips
    return {**builtin_clips(), **list_custom_clips()}


def builtin_clips() -> dict[str, dict[str, Any]]:
    """The built-in clips, expanded onto every bone of the rig."""
    return {
        name: {
            "frames": clip["frames"],
            "loop": clip["loop"],
            "poses": {frame: _expand_pose(pose) for frame, pose in clip["poses"].items()},
        }
        for name, clip in _authored_clips().items()
    }


def _expand_pose(pose: dict[str, tuple[float, float, float]]) -> dict[str, tuple[float, float, float]]:
    """Fill in the rig's secondary joints from an authored main-body pose,
    without changing any authored bone's other values.

    Chest's rotation is split across Spine/Chest/UpperChest (fractions
    0.35/0.35/0.30, summing to 1) so a torso lean or twist reads as a
    curved spine instead of one rigid hinge — the cumulative bend at the
    top of the chain still matches the original Chest rotation exactly,
    since the three segments are a serial chain and their local rotations
    add. Shoulder and Toe get a fraction of whichever axis UpperArm/Foot
    use (falling back to LowerLeg for Toe when a clip doesn't key Foot),
    as a subtle follow-through rather than an independently authored pose.
    Fingers get a fixed relaxed-hand curl in every frame of every clip —
    a static baseline rather than something reactive per pose, since nothing
    upstream signals "gripping" vs "open hand" reliably enough to vary it.
    """
    expanded = dict(pose)
    if "Chest" in pose:
        x, y, z = pose["Chest"]
        expanded["Spine"] = (x * 0.35, y * 0.35, z * 0.35)
        expanded["Chest"] = (x * 0.35, y * 0.35, z * 0.35)
        expanded["UpperChest"] = (x * 0.30, y * 0.30, z * 0.30)
    for side in ("L", "R"):
        upper_arm = pose.get(f"UpperArm.{side}")
        if upper_arm:
            expanded[f"Shoulder.{side}"] = tuple(component * 0.15 for component in upper_arm)
        foot = pose.get(f"Foot.{side}")
        lower_leg = pose.get(f"LowerLeg.{side}")
        if foot:
            expanded[f"Toe.{side}"] = tuple(component * 0.4 for component in foot)
        elif lower_leg:
            expanded[f"Toe.{side}"] = tuple(component * 0.15 for component in lower_leg)
        for finger in ("Index", "Middle", "Ring", "Little"):
            for segment, curl in enumerate(_FINGER_CURL, start=1):
                expanded[f"{finger}{segment}.{side}"] = _curl(curl, side)
        for segment, curl in enumerate(_THUMB_CURL, start=1):
            expanded[f"Thumb{segment}.{side}"] = _curl(curl, side)
    return expanded


def _authored_clips() -> dict[str, dict[str, Any]]:
    run = {}
    for frame, phase in ((1, 1), (9, 0), (16, -1), (24, 0), (31, 1)):
        pose = {"Chest": r(6)}
        if phase:
            pose.update({"UpperLeg.L": r(42 * phase), "UpperLeg.R": r(-42 * phase), "LowerLeg.L": r(-32 * phase), "LowerLeg.R": r(32 * phase), "UpperArm.L": r(-38 * phase), "UpperArm.R": r(38 * phase)})
        else:
            pose.update({"LowerLeg.L": r(10), "LowerLeg.R": r(10)})
        run[frame] = pose

    # Crouch-walk stride: legs alternate around the Crouch base bend
    # (UpperLeg/LowerLeg/Foot rotate on the same X axis as Crouch itself,
    # since Hips carries no base rotation here — no parent-composition risk,
    # see Crawl's comment below for when that stops being true). Arms hold
    # a fixed two-handed rifle-ready pose, reusing MeleeAttack's proven
    # extended-arm values, since a held weapon shouldn't swing with the gait.
    crouch_walk = {}
    for frame, phase in ((1, 1), (9, 0), (16, -1), (24, 0), (31, 1)):
        crouch_walk[frame] = {
            "Chest": r(-6),
            "UpperArm.L": r(70, -8, 10), "Forearm.L": r(18),
            "UpperArm.R": r(78, 8, -10), "Forearm.R": r(16),
            "UpperLeg.L": r(45 + 14 * phase), "UpperLeg.R": r(45 - 14 * phase),
            "LowerLeg.L": r(-80 - 12 * phase), "LowerLeg.R": r(-80 + 12 * phase),
            "Foot.L": r(35 + 8 * phase), "Foot.R": r(35 - 8 * phase),
        }

    # Prone crawl stride. Hips carries the full ~80 degree pitch here, and
    # composing more rotation on an already 80-degree-pitched parent on the
    # SAME axis (X) doesn't add — it swings wildly (verified by rendering:
    # a 12-degree X addition on UpperLeg flung the leg into the air, not a
    # subtle drag). Y/Z rotations on the arms/legs stayed controlled under
    # the same parent pitch, so the stride swing is authored on those axes
    # instead, purely by rendering candidates and keeping what didn't break.
    # Body pitch, head lift, and elbow bend match Prone below (face-down).
    crawl = {}
    for frame, phase in ((1, 1), (9, 0), (16, -1), (24, 0), (31, 1)):
        crawl[frame] = {
            "Hips": r(-80), "Head": r(55),
            "Forearm.L": r(15), "Forearm.R": r(15),
            "UpperArm.L": r(0, 22 * phase), "UpperArm.R": r(0, -22 * phase),
            "UpperLeg.L": r(0, 0, 18 * -phase), "UpperLeg.R": r(0, 0, 18 * phase),
        }

    return {
        "Idle": {"frames": 60, "loop": True, "poses": {1: {}, 30: {"Chest": r(1), "Head": r(-1)}, 60: {}}},
        "Run": {"frames": 31, "loop": True, "poses": run},
        "Jump": {"frames": 46, "loop": False, "poses": {1: {}, 9: {"UpperLeg.L": r(-25), "UpperLeg.R": r(-25), "LowerLeg.L": r(35), "LowerLeg.R": r(35), "UpperArm.L": r(-25), "UpperArm.R": r(-25)}, 19: {"UpperLeg.L": r(12), "UpperLeg.R": r(12), "LowerLeg.L": r(-10), "LowerLeg.R": r(-10), "UpperArm.L": r(65), "UpperArm.R": r(65)}, 33: {"UpperLeg.L": r(8), "UpperLeg.R": r(8), "UpperArm.L": r(25), "UpperArm.R": r(25)}, 46: {}}},
        # A deliberate two-handed overhead heavy strike; both arms stay
        # involved throughout.
        "MeleeAttack": {"frames": 30, "loop": False, "poses": {
            1: {},
            8: {"Chest": r(-8, -18), "UpperArm.L": r(-72, 8, 16), "Forearm.L": r(-48, 0, -8), "UpperArm.R": r(-78, -10, -16), "Forearm.R": r(-52, 0, 8)},
            15: {"Chest": r(18, 22), "UpperArm.L": r(72, -8, 10), "Forearm.L": r(22), "UpperArm.R": r(78, 8, -10), "Forearm.R": r(18)},
            22: {"Chest": r(6, 5), "UpperArm.L": r(22, 0, 4), "Forearm.L": r(12), "UpperArm.R": r(26, 0, -4), "Forearm.R": r(12)},
            30: {},
        }},
        # A controlled two-handed downward tool stroke. Contact is frame 16
        # (0.5 seconds at 30fps).
        "HarvestSwing": {"frames": 32, "loop": False, "poses": {
            1: {},
            9: {"Chest": r(-6, -14), "UpperArm.L": r(-58, 12, 20), "Forearm.L": r(-44, 0, -12), "UpperArm.R": r(-72, -12, -18), "Forearm.R": r(-54, 0, 10)},
            16: {"Chest": r(14, 18), "UpperArm.L": r(58, -10, 14), "Forearm.L": r(18, 0, 4), "UpperArm.R": r(76, 10, -12), "Forearm.R": r(16, 0, -4)},
            24: {"Chest": r(5, 4), "UpperArm.L": r(18, 0, 5), "Forearm.L": r(10), "UpperArm.R": r(24, 0, -5), "Forearm.R": r(12)},
            32: {},
        }},
        "Fire": {"frames": 12, "loop": False, "poses": {1: {}, 3: {"UpperArm.R": r(-18), "Forearm.R": r(-12), "Chest": r(-4)}, 12: {}}},
        "Sit": {"frames": 30, "loop": True, "poses": {1: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(8)}, 15: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(9), "Head": r(-1)}, 30: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(8)}}},
        # Held combat crouch: knees bent forward (same sign convention as
        # Sit's hip/knee fold, verified by rendering — the original release
        # used the opposite sign, which put the knee bend backwards and left
        # the feet dangling at the wrong angle instead of flat on the
        # ground). Feet get a small counter-rotation so they stay planted
        # rather than inheriting the knee's full tilt.
        "Crouch": {"frames": 30, "loop": True, "poses": {
            1: {"UpperLeg.L": r(45), "UpperLeg.R": r(45), "LowerLeg.L": r(-80), "LowerLeg.R": r(-80), "Foot.L": r(35), "Foot.R": r(35), "Chest": r(-8), "UpperArm.L": r(-18), "UpperArm.R": r(-18), "Forearm.L": r(25), "Forearm.R": r(25)},
            15: {"UpperLeg.L": r(45), "UpperLeg.R": r(45), "LowerLeg.L": r(-80), "LowerLeg.R": r(-80), "Foot.L": r(35), "Foot.R": r(35), "Chest": r(-7), "UpperArm.L": r(-18), "UpperArm.R": r(-18), "Forearm.L": r(25), "Forearm.R": r(25), "Head": r(-1)},
            30: {"UpperLeg.L": r(45), "UpperLeg.R": r(45), "LowerLeg.L": r(-80), "LowerLeg.R": r(-80), "Foot.L": r(35), "Foot.R": r(35), "Chest": r(-8), "UpperArm.L": r(-18), "UpperArm.R": r(-18), "Forearm.L": r(25), "Forearm.R": r(25)},
        }},
        "CrouchWalkRifle": {"frames": 31, "loop": True, "poses": crouch_walk},
        "Crawl": {"frames": 31, "loop": True, "poses": crawl},
        # Held prone: Hips pitches the whole rig ~horizontal, head counter-
        # rotated up to look forward. Rotation-only, so this pivots around
        # the hip bone's rest height rather than lying flat on the ground —
        # see README "Design boundaries" for what whatever plays it must do
        # about that before this is usable as an actual prone stance.
        #
        # Sign conventions (checked numerically and by rendering — see
        # tests/smoke_test.py, which asserts the facing direction):
        # Hips -80 on X tips the body forward so the chest faces the
        # ground (+80 tips it backwards onto its back, which an earlier
        # release shipped by mistake). Head +55 lifts the face to look
        # ahead, ~25 degrees below horizontal. Forearm +15 bends the elbow
        # the natural way (same sign as Crouch/Sit); -15 hyperextends it.
        "Prone": {"frames": 30, "loop": True, "poses": {
            1: {"Hips": r(-80), "Forearm.L": r(15), "Forearm.R": r(15), "Head": r(55)},
            15: {"Hips": r(-80), "Forearm.L": r(15), "Forearm.R": r(15), "Head": r(54)},
            30: {"Hips": r(-80), "Forearm.L": r(15), "Forearm.R": r(15), "Head": r(55)},
        }},
        "ZombieAttack": {"frames": 30, "loop": False, "poses": {1: {"Chest": r(10)}, 8: {"Chest": r(-18), "UpperArm.L": r(-55), "UpperArm.R": r(-55), "Forearm.L": r(-35), "Forearm.R": r(-35)}, 15: {"Chest": r(28), "UpperArm.L": r(70), "UpperArm.R": r(70), "Forearm.L": r(20), "Forearm.R": r(20)}, 23: {"Chest": r(8), "UpperArm.L": r(18), "UpperArm.R": r(18)}, 30: {"Chest": r(10)}}},
    }
