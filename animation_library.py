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
        for name, clip in {**_authored_clips(), **_more_clips()}.items()
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
    Fingers a frame doesn't key get a fixed relaxed-hand curl; frames that
    key finger bones (see _hand) keep their own hand shape.
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
        # Relaxed curl only for finger bones the clip doesn't key itself, so
        # hand shapes (fist, point, thumbs up...) authored per frame win.
        for finger in ("Index", "Middle", "Ring", "Little"):
            for segment, curl in enumerate(_FINGER_CURL, start=1):
                expanded.setdefault(f"{finger}{segment}.{side}", _curl(curl, side))
        for segment, curl in enumerate(_THUMB_CURL, start=1):
            expanded.setdefault(f"Thumb{segment}.{side}", _curl(curl, side))
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


# ---------------------------------------------------------------- composed rotations

def _matrix(axis: str, degrees: float) -> list[list[float]]:
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
            "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
            "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[axis]


def _multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _compose(*steps: tuple[str, float]) -> tuple[float, float, float]:
    """Euler XYZ (radians, like r()) for rotations applied one after another
    about the bone's own, already-rotated axes. E.g. _compose(("x", 90),
    ("y", -80)) bends the elbow 90 degrees, then twists the forearm about
    its own length. (A plain r(x, y, z) applies X first and then Y and Z
    about the parent's axes, which swings a bent forearm sideways instead.)"""
    m = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    for axis, degrees in steps:
        m = _multiply(m, _matrix(axis, degrees))
    # Blender's XYZ Euler is Rz @ Ry @ Rx.
    y = math.asin(max(-1.0, min(1.0, -m[2][0])))
    x = math.atan2(m[2][1], m[2][2])
    z = math.atan2(m[1][0], m[0][0])
    return x, y, z


def _side(side: str, x: float, y: float, z: float) -> tuple[float, float, float]:
    """A left-side rotation in degrees, mirrored for the right side."""
    return r(x, y, z) if side == "L" else r(x, -y, -z)


# ---------------------------------------------------------------- hand shapes
#
# Per-finger curl in degrees for (Proximal, Intermediate, Distal), applied
# with _curl (into the palm). _hand turns a shape into finger-bone keys.
_FINGERS = ("Index", "Middle", "Ring", "Little")
_STRAIGHT = (0, 0, 0)
_CURLED = (80, 95, 60)
# Thumb poses are full (x, y, z) rotations in degrees per segment, written
# for the left hand and mirrored for the right (see _side). Curling a thumb
# about Z alone only swings it sideways out of the palm; to fold it over
# curled fingers it also swings back toward the little finger (-X). These
# values were picked by rendering candidates from three angles.
_THUMB_OPEN = ((0, 0, 0), (0, 0, 0), (0, 0, 0))
_THUMB_TUCKED = ((-70, 0, -20), (0, 0, -40), (0, 0, -30))
_HAND_SHAPES = {
    "open": {"fingers": {finger: _STRAIGHT for finger in _FINGERS}, "thumb": _THUMB_OPEN},
    "fist": {"fingers": {finger: _CURLED for finger in _FINGERS}, "thumb": _THUMB_TUCKED},
    "point": {"fingers": {"Index": _STRAIGHT, "Middle": _CURLED, "Ring": _CURLED, "Little": _CURLED}, "thumb": _THUMB_TUCKED},
    "thumbs_up": {"fingers": {finger: _CURLED for finger in _FINGERS}, "thumb": ((0, 0, 10), (0, 0, 0), (0, 0, 0))},
    "middle_finger": {"fingers": {"Index": _CURLED, "Middle": _STRAIGHT, "Ring": _CURLED, "Little": _CURLED}, "thumb": _THUMB_TUCKED},
    "grip": {"fingers": {"Index": (25, 25, 15), "Middle": (70, 85, 55), "Ring": (70, 85, 55), "Little": (70, 85, 55)}, "thumb": ((-45, 0, -20), (0, 0, -30), (0, 0, -20))},
    "handshake": {"fingers": {finger: (30, 30, 20) for finger in _FINGERS}, "thumb": ((0, 0, 0), (0, 0, -10), (0, 0, -10))},
}


def _hand(side: str, shape: str) -> dict[str, tuple[float, float, float]]:
    spec = _HAND_SHAPES[shape]
    keys = {}
    for finger, curls in spec["fingers"].items():
        for segment, degrees in enumerate(curls, start=1):
            keys[f"{finger}{segment}.{side}"] = _curl(degrees, side)
    for segment, rotation in enumerate(spec["thumb"], start=1):
        keys[f"Thumb{segment}.{side}"] = _side(side, *rotation)
    return keys


def _mirror(pose: dict[str, tuple[float, float, float]]) -> dict[str, tuple[float, float, float]]:
    """Left/right mirror of a pose: swap .L/.R bones and negate the Y and Z
    Euler components (the authoring skeleton's left and right bones share
    the same local axes, so a mirror across the body's centre plane keeps
    rotations about X and flips the other two)."""
    mirrored = {}
    for bone, (x, y, z) in pose.items():
        if bone.endswith(".L"):
            bone = bone[:-2] + ".R"
        elif bone.endswith(".R"):
            bone = bone[:-2] + ".L"
        mirrored[bone] = (x, -y, -z)
    return mirrored


def _merge(*parts: dict) -> dict:
    merged = {}
    for part in parts:
        merged.update(part)
    return merged


def _cycle(keys: tuple[int, ...], poses: list[dict]) -> dict[int, dict]:
    return dict(zip(keys, poses))


def _more_clips() -> dict[str, dict[str, Any]]:
    """Clips added after the original 12. Same conventions as above
    (authoring skeleton faces +Y): +X on UpperArm/Forearm/UpperLeg swings
    forward / flexes; -X on LowerLeg bends the knee; -X on Chest/Head bends
    forward / looks down; +Z abducts the left arm or leg and -Z the right."""
    clips: dict[str, dict[str, Any]] = {}

    # --- Locomotion -------------------------------------------------------
    # Walk: contact, passing, opposite contact, passing, loop. Arms swing
    # opposite to the legs; the torso stays upright.
    walk_contact = {
        "Chest": r(-2, 3), "UpperLeg.L": r(25), "LowerLeg.L": r(-5), "Foot.L": r(10),
        "UpperLeg.R": r(-15), "LowerLeg.R": r(-12), "Foot.R": r(-15),
        "UpperArm.L": r(-15), "UpperArm.R": r(15), "Forearm.L": r(8), "Forearm.R": r(15),
    }
    walk_passing = {
        "Chest": r(-2), "UpperLeg.L": r(-2), "LowerLeg.L": r(-5),
        "UpperLeg.R": r(12), "LowerLeg.R": r(-45), "Foot.R": r(10),
        "UpperArm.L": r(0), "UpperArm.R": r(0), "Forearm.L": r(10), "Forearm.R": r(10),
    }
    clips["Walk"] = {"frames": 33, "loop": True, "poses": _cycle((1, 9, 17, 25, 33), [walk_contact, walk_passing, _mirror(walk_contact), _mirror(walk_passing), walk_contact])}

    # Sprint: a faster, deeper Run with a forward lean and bent, pumping arms.
    sprint_drive = {
        "Chest": r(-14, 6), "Head": r(8),
        "UpperLeg.L": r(65), "LowerLeg.L": r(-70), "Foot.L": r(10),
        "UpperLeg.R": r(-30), "LowerLeg.R": r(-25), "Foot.R": r(-25),
        "UpperArm.L": r(-45), "UpperArm.R": r(60), "Forearm.L": r(70), "Forearm.R": r(90),
        **_hand("L", "fist"), **_hand("R", "fist"),
    }
    sprint_flight = {
        "Chest": r(-14), "Head": r(8),
        "UpperLeg.L": r(15), "LowerLeg.L": r(-30), "UpperLeg.R": r(10), "LowerLeg.R": r(-100), "Foot.R": r(15),
        "UpperArm.L": r(5), "UpperArm.R": r(5), "Forearm.L": r(80), "Forearm.R": r(80),
        **_hand("L", "fist"), **_hand("R", "fist"),
    }
    clips["Sprint"] = {"frames": 25, "loop": True, "poses": _cycle((1, 7, 13, 19, 25), [sprint_drive, sprint_flight, _mirror(sprint_drive), _mirror(sprint_flight), sprint_drive])}

    # Strafe right: the right leg steps out, the stance widens, the left leg
    # follows in. Strafe left is its mirror.
    strafe = [
        {"UpperLeg.L": r(0, 0, 2), "UpperLeg.R": r(0, 0, -2), "Forearm.L": r(10), "Forearm.R": r(10)},
        {"UpperLeg.R": r(10, 0, -20), "LowerLeg.R": r(-25), "Foot.R": r(10), "UpperLeg.L": r(0, 0, -4), "LowerLeg.L": r(-8), "Chest": r(0, 0, 3), "Forearm.L": r(10), "Forearm.R": r(10)},
        {"UpperLeg.R": r(0, 0, -14), "UpperLeg.L": r(0, 0, 10), "LowerLeg.L": r(-4), "LowerLeg.R": r(-4), "Forearm.L": r(10), "Forearm.R": r(10)},
        {"UpperLeg.L": r(10, 0, 4), "LowerLeg.L": r(-25), "Foot.L": r(10), "UpperLeg.R": r(0, 0, -8), "LowerLeg.R": r(-8), "Chest": r(0, 0, -3), "Forearm.L": r(10), "Forearm.R": r(10)},
    ]
    clips["StrafeRight"] = {"frames": 33, "loop": True, "poses": _cycle((1, 9, 17, 25, 33), [*strafe, strafe[0]])}
    clips["StrafeLeft"] = {"frames": 33, "loop": True, "poses": _cycle((1, 9, 17, 25, 33), [_mirror(p) for p in (*strafe, strafe[0])])}

    # Zombie walk: slow shamble, arms raised forward with limp wrists, head
    # lolling, the right leg dragging with a shorter step.
    zombie_arms = {"UpperArm.L": r(80, 0, 4), "UpperArm.R": r(75, 0, -6), "Forearm.L": r(10), "Forearm.R": r(15), "Hand.L": r(-25), "Hand.R": r(-30)}
    zombie = [
        {**zombie_arms, "Chest": r(-10, 4, 5), "Head": r(-10, 0, 15), "UpperLeg.L": r(22), "LowerLeg.L": r(-8), "UpperLeg.R": r(-8), "LowerLeg.R": r(-10), "Foot.R": r(-20)},
        {**zombie_arms, "Chest": r(-12, 0, 3), "Head": r(-12, 0, 18), "UpperLeg.L": r(0), "LowerLeg.L": r(-5), "UpperLeg.R": r(6), "LowerLeg.R": r(-20), "Foot.R": r(-15)},
        {**zombie_arms, "Chest": r(-10, -4, 5), "Head": r(-10, 0, 15), "UpperLeg.L": r(-12), "LowerLeg.L": r(-15), "Foot.L": r(-10), "UpperLeg.R": r(12), "LowerLeg.R": r(-8), "Foot.R": r(-10)},
        {**zombie_arms, "Chest": r(-12, 0, 6), "Head": r(-12, 0, 12), "UpperLeg.L": r(10), "LowerLeg.L": r(-40), "UpperLeg.R": r(0), "LowerLeg.R": r(-6), "Foot.R": r(-15)},
    ]
    clips["ZombieWalk"] = {"frames": 49, "loop": True, "poses": _cycle((1, 13, 25, 37, 49), [*zombie, zombie[0]])}

    # --- Hand gestures (right hand) ---------------------------------------
    rest = {}
    thumbs = {"UpperArm.R": r(35, 0, -5), "Forearm.R": r(85), **_hand("R", "thumbs_up")}
    clips["ThumbsUp"] = {"frames": 50, "loop": False, "poses": {1: rest, 10: thumbs, 40: thumbs, 50: rest}}

    # Forearm raised, then turned 80 degrees about its own length (split
    # between forearm and wrist) so the back of the hand faces forward.
    middle = {"UpperArm.R": r(50, 0, -10), "Forearm.R": _compose(("x", 100), ("y", 40)), "Hand.R": r(0, 40, 0), **_hand("R", "middle_finger"), "Head": r(-3, 0, -5)}
    clips["MiddleFinger"] = {"frames": 50, "loop": False, "poses": {1: rest, 10: middle, 40: middle, 50: rest}}

    def shake(forearm):
        # Turned 20 degrees (forearm + wrist) so the hand stands vertical, thumb up.
        return {"UpperArm.R": r(50, 0, 6), "Forearm.R": _compose(("x", forearm), ("y", -10)), "Hand.R": r(0, -10, 0), **_hand("R", "handshake")}
    clips["Handshake"] = {"frames": 50, "loop": False, "poses": {1: rest, 10: shake(55), 16: shake(42), 22: shake(65), 28: shake(42), 34: shake(60), 42: shake(55), 50: rest}}

    def wave(side_angle):
        return {"UpperArm.R": r(10, 0, -140), "Forearm.R": r(0, 0, side_angle), "Hand.R": r(0), **_hand("R", "open"), "Head": r(0, 0, -4)}
    clips["Wave"] = {"frames": 50, "loop": False, "poses": {1: rest, 10: wave(-20), 17: wave(20), 24: wave(-20), 31: wave(20), 38: wave(-10), 50: rest}}

    point = {"UpperArm.R": r(85, 0, 4), "Forearm.R": r(0), **_hand("R", "point"), "Chest": r(0, -6), "Head": r(0, -4)}
    clips["Point"] = {"frames": 40, "loop": False, "poses": {1: rest, 10: point, 32: point, 40: rest}}

    # Talk: looping conversational gestures with both hands, small nods and
    # a little torso movement; the hands open and relax in turn.
    talk = [
        {"UpperArm.L": r(15, 0, 8), "UpperArm.R": r(20, 0, -8), "Forearm.L": r(70), "Forearm.R": r(75), **_hand("L", "open"), **_hand("R", "open"), "Head": r(-3), "Chest": r(0, 3)},
        {"UpperArm.L": r(12, 0, 6), "UpperArm.R": r(28, 0, -14), "Forearm.L": r(60), "Forearm.R": r(90, -30), **_hand("R", "open"), "Head": r(4, 5), "Chest": r(-2, -4)},
        {"UpperArm.L": r(25, 0, 14), "UpperArm.R": r(14, 0, -6), "Forearm.L": r(85, 30), "Forearm.R": r(65), **_hand("L", "open"), "Head": r(-4, -4), "Chest": r(0, 5)},
        {"UpperArm.L": r(18, 0, 10), "UpperArm.R": r(22, 0, -10), "Forearm.L": r(75), "Forearm.R": r(80), "Head": r(2, 2), "Chest": r(-1)},
    ]
    clips["Talk"] = {"frames": 97, "loop": True, "poses": _cycle((1, 25, 49, 73, 97), [*talk, talk[0]])}

    # --- Combat -----------------------------------------------------------
    guard = {
        # Upper arms forward, then turned inward about their length so the
        # bent forearms bring both fists up in front of the chin.
        "UpperArm.L": _compose(("x", 50), ("y", 30)), "UpperArm.R": _compose(("x", 45), ("y", -30)), "Forearm.L": r(110), "Forearm.R": r(115),
        "UpperLeg.L": r(12), "LowerLeg.L": r(-14), "UpperLeg.R": r(-6), "LowerLeg.R": r(-10), "Chest": r(-6),
        **_hand("L", "fist"), **_hand("R", "fist"),
    }
    jab = _merge(guard, {"UpperArm.L": r(85, 0, -8), "Forearm.L": r(5), "Chest": r(-8, -15)})
    cross = _merge(guard, {"UpperArm.R": r(88, 0, 8), "Forearm.R": r(5), "Chest": r(-10, 25), "UpperLeg.R": r(-10, 15), "LowerLeg.R": r(-14)})
    clips["Punch"] = {"frames": 32, "loop": False, "poses": {1: guard, 6: jab, 11: guard, 18: cross, 26: guard, 32: guard}}

    chamber = _merge(guard, {"UpperLeg.R": r(90), "LowerLeg.R": r(-110), "Foot.R": r(-10), "Chest": r(8), "UpperLeg.L": r(0), "LowerLeg.L": r(-8)})
    extend = _merge(guard, {"UpperLeg.R": r(85), "LowerLeg.R": r(-5), "Foot.R": r(-35), "Chest": r(14), "UpperLeg.L": r(0), "LowerLeg.L": r(-6)})
    clips["Kick"] = {"frames": 32, "loop": False, "poses": {1: guard, 8: chamber, 13: extend, 18: chamber, 26: guard, 32: guard}}

    aim = {"UpperArm.R": r(85, 0, 10), "Forearm.R": r(0), "Hand.R": r(0), **_hand("R", "grip"), "Chest": r(0, -10), "Head": r(0, -6)}
    clips["PistolIdle"] = {"frames": 60, "loop": True, "poses": {1: aim, 30: _merge(aim, {"UpperArm.R": r(84, 0, 10), "Chest": r(1, -10)}), 60: aim}}
    squeeze = _merge(aim, {"Index1.R": _curl(40, "R"), "Index2.R": _curl(40, "R")})
    recoil = _merge(squeeze, {"UpperArm.R": r(93, 0, 10), "Forearm.R": r(14), "Hand.R": r(12), "Chest": r(3, -10)})
    clips["PistolFire"] = {"frames": 12, "loop": False, "poses": {1: aim, 2: squeeze, 3: recoil, 8: aim, 12: aim}}

    ready = {"UpperArm.R": r(35, 0, 10), "Forearm.R": r(80), **_hand("R", "grip"), "UpperArm.L": r(50, 0, -10), "Forearm.L": r(60), **_hand("L", "grip"), "Head": r(-15)}
    to_mag = _merge(ready, {"UpperArm.L": r(30, 0, -15), "Forearm.L": r(70), **_hand("L", "fist"), "Head": r(-25)})
    pouch = _merge(ready, {"UpperArm.L": r(-5, 0, 10), "Forearm.L": r(50), **_hand("L", "fist"), "Head": r(-20, 10)})
    charge = _merge(ready, {"UpperArm.L": r(45, 0, -20), "Forearm.L": r(100), **_hand("L", "fist"), "Head": r(-18)})
    clips["Reload"] = {"frames": 55, "loop": False, "poses": {1: ready, 10: to_mag, 18: pouch, 28: to_mag, 38: charge, 46: ready, 55: ready}}

    # Arm raised to the side, then rotated about its own length so the bent
    # forearm points up behind the head (cocked).
    throw_windup = {"UpperArm.R": _compose(("z", -95), ("y", 80)), "Forearm.R": r(100), **_hand("R", "fist"), "UpperArm.L": r(70, 0, 10), "Forearm.L": r(10),
                    "Chest": r(6, -35), "UpperLeg.L": r(25), "LowerLeg.L": r(-10), "UpperLeg.R": r(-10), "LowerLeg.R": r(-15)}
    throw_release = {"UpperArm.R": r(120, 0, -15), "Forearm.R": r(20), **_hand("R", "open"), "UpperArm.L": r(10, 0, 15), "Forearm.L": r(40),
                     "Chest": r(-12, 25), "UpperLeg.L": r(25), "LowerLeg.L": r(-15), "UpperLeg.R": r(-15), "LowerLeg.R": r(-25)}
    throw_follow = {"UpperArm.R": r(60, 0, 25), "Forearm.R": r(15), **_hand("R", "open"), "UpperArm.L": r(-10, 0, 10), "Forearm.L": r(30),
                    "Chest": r(-25, 30), "UpperLeg.L": r(25), "LowerLeg.L": r(-20), "UpperLeg.R": r(-15), "LowerLeg.R": r(-35)}
    clips["Throw"] = {"frames": 36, "loop": False, "poses": {1: rest, 10: throw_windup, 16: throw_release, 24: throw_follow, 36: rest}}

    hit = {"Chest": r(22, 8), "Head": r(18, 0, 6), "UpperArm.L": r(25, 0, 15), "UpperArm.R": r(30, 0, -15), "Forearm.L": r(35), "Forearm.R": r(40), "UpperLeg.L": r(8), "LowerLeg.L": r(-12), **_hand("L", "open"), **_hand("R", "open")}
    clips["HitReact"] = {"frames": 20, "loop": False, "poses": {1: rest, 4: hit, 10: _merge(rest, {"Chest": r(6), "Head": r(4)}), 20: rest}}

    # Death: knees buckle, the body tips backwards and ends lying on its
    # back, arms splayed. Rotation-only like Prone: it pivots around the
    # hips, so whatever plays it has to lower the character to the ground.
    buckle = {"UpperLeg.L": r(30), "UpperLeg.R": r(25), "LowerLeg.L": r(-60), "LowerLeg.R": r(-55), "Foot.L": r(20), "Foot.R": r(20), "Chest": r(-15), "Head": r(-20),
              "UpperArm.L": r(20, 0, 10), "UpperArm.R": r(15, 0, -10), "Forearm.L": r(30), "Forearm.R": r(25)}
    falling = {"Hips": r(45), "UpperLeg.L": r(40), "UpperLeg.R": r(30), "LowerLeg.L": r(-50), "LowerLeg.R": r(-40), "Chest": r(10), "Head": r(15),
               "UpperArm.L": r(40, 0, 50), "UpperArm.R": r(35, 0, -50), "Forearm.L": r(20), "Forearm.R": r(20), **_hand("L", "open"), **_hand("R", "open")}
    lying = {"Hips": r(85), "UpperLeg.L": r(10, 0, 8), "UpperLeg.R": r(5, 0, -10), "LowerLeg.L": r(-15), "LowerLeg.R": r(-5), "Head": r(-10, 25),
             "UpperArm.L": r(0, 0, 70), "UpperArm.R": r(10, 0, -60), "Forearm.L": r(25), "Forearm.R": r(15), **_hand("L", "open"), **_hand("R", "open")}
    clips["Death"] = {"frames": 45, "loop": False, "poses": {1: rest, 8: buckle, 20: falling, 30: lying, 45: lying}}

    # --- Interaction ------------------------------------------------------
    crouch_reach = {"UpperLeg.L": r(75), "UpperLeg.R": r(65), "LowerLeg.L": r(-110), "LowerLeg.R": r(-100), "Foot.L": r(35), "Foot.R": r(35),
                    "Chest": r(-45), "Head": r(-15), "UpperArm.R": r(55, 0, 5), "Forearm.R": r(10), "UpperArm.L": r(20, 0, 10), "Forearm.L": r(40)}
    grab = _merge(crouch_reach, _hand("R", "fist"))
    holding = {"UpperArm.R": r(25, 0, 5), "Forearm.R": r(70), **_hand("R", "fist")}
    clips["PickUp"] = {"frames": 40, "loop": False, "poses": {1: rest, 14: _merge(crouch_reach, _hand("R", "open")), 18: grab, 32: holding, 40: holding}}

    reach = {"UpperArm.R": r(55, 0, 5), "Forearm.R": r(45), **_hand("R", "point"), "Head": r(-8)}
    press = _merge(reach, {"UpperArm.R": r(65, 0, 5), "Forearm.R": r(25)})
    clips["Interact"] = {"frames": 30, "loop": False, "poses": {1: rest, 8: reach, 12: press, 18: reach, 30: rest}}

    return clips
