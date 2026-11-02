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
    # Sign convention, checked by measuring the posed skeleton: the spine
    # and head bones point up, so -X on Chest/Head bends forward and +X
    # leans back (the opposite of the arm and leg bones, which point down,
    # where +X swings forward). Run, MeleeAttack, HarvestSwing, Fire and
    # ZombieAttack originally had the Chest sign reversed (Run leaned back,
    # the attacks leaned back on the strike and forward on the wind-up);
    # those values were flipped.
    run = {}
    for frame, phase in ((1, 1), (9, 0), (16, -1), (24, 0), (31, 1)):
        pose = {"Chest": r(-6)}  # slight forward lean
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
    # Upper arms solved on the MPFB character for a 42 cm hand gap (support
    # hand forward on the handguard), as for MeleeAttack below.
    crouch_walk = {}
    for frame, phase in ((1, 1), (9, 0), (16, -1), (24, 0), (31, 1)):
        crouch_walk[frame] = {
            "Chest": r(-6),
            "UpperArm.L": r(71.4, 1.6, 6.6), "Forearm.L": r(18),
            "UpperArm.R": r(79.6, -2.0, -8.0), "Forearm.R": r(16),
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
        # A deliberate two-handed overhead heavy strike: wind-up with the
        # tool raised overhead (frame 8; the original swung both arms straight
        # back behind the body at shoulder height, which can't hold a handle),
        # strike down in front (15), recover (22). The wind-up was picked by a
        # search on the MPFB character for no arm-into-head contact with the
        # hands under 30 cm apart and the arms not crossing (raised past the
        # shoulder, a +Z "outward" value crosses the arms over the face);
        # HarvestSwing's wind-up (9) likewise. Upper-arm values on frames
        # 15/22 (and HarvestSwing 16/24) were solved on the MPFB character by swinging
        # each upper arm toward the midline until the hands are 25 cm apart,
        # as on one handle; the original values left them 60-90 cm apart.
        "MeleeAttack": {"frames": 30, "loop": False, "poses": {
            1: {},
            8: {"Chest": r(10, -18), "UpperArm.L": r(150, 0, -8), "Forearm.L": r(30), "UpperArm.R": r(155, 0, 8), "Forearm.R": r(25)},
            15: {"Chest": r(-18, 22), "UpperArm.L": r(74.4, 11.2, 4.2), "Forearm.L": r(22), "UpperArm.R": r(80.8, -11.6, -6.3), "Forearm.R": r(18)},
            22: {"Chest": r(-6, 5), "UpperArm.L": r(21.2, 7.9, -15.7), "Forearm.L": r(12), "UpperArm.R": r(25.1, -9.2, 15.1), "Forearm.R": r(12)},
            30: {},
        }},
        # A controlled two-handed downward tool stroke. Contact is frame 16
        # (0.5 seconds at 30fps).
        "HarvestSwing": {"frames": 32, "loop": False, "poses": {
            1: {},
            9: {"Chest": r(8, -14), "UpperArm.L": r(140, 0, -8), "Forearm.L": r(30), "UpperArm.R": r(145, 0, 8), "Forearm.R": r(25)},
            16: {"Chest": r(-14, 18), "UpperArm.L": r(60.9, 15.1, -0.6), "Forearm.L": r(18, 0, 4), "UpperArm.R": r(80.5, -18.2, -6.2), "Forearm.R": r(16, 0, -4)},
            24: {"Chest": r(-5, 4), "UpperArm.L": r(23.3, 6.8, -16.3), "Forearm.L": r(10), "UpperArm.R": r(29.2, -9.0, 15.5), "Forearm.R": r(12)},
            32: {},
        }},
        "Fire": {"frames": 12, "loop": False, "poses": {1: {}, 3: {"UpperArm.R": r(-18), "Forearm.R": r(-12), "Chest": r(4)}, 12: {}}},
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
        # rotated up to look forward. The rotations pivot around the hips;
        # ground contact (retarget.ground_clip) then lowers the character
        # so it lies on the floor.
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
        "ZombieAttack": {"frames": 30, "loop": False, "poses": {1: {"Chest": r(-10)}, 8: {"Chest": r(18), "UpperArm.L": r(-55), "UpperArm.R": r(-55), "Forearm.L": r(-35), "Forearm.R": r(-35)}, 15: {"Chest": r(-28), "UpperArm.L": r(70), "UpperArm.R": r(70), "Forearm.L": r(20), "Forearm.R": r(20)}, 23: {"Chest": r(-8), "UpperArm.L": r(18), "UpperArm.R": r(18)}, 30: {"Chest": r(-10)}}},
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
# Tight curl for fists. Checked by rendering: at 80/95/60 a fingertip pushes
# through the palm and its nail shows on the back of the hand.
_CURLED = (70, 90, 50)
# Thumb poses are (x, y, z) degrees per segment, written for the left hand
# and mirrored for the right (see _side). retarget.py reads them as anatomy
# on the character's own thumb: segment 1 -Z swings it toward the palm and
# -X across toward the little finger; segments 2-3 -Z bend it. Values were
# found by searching on the MPFB character for thumb-tip skin resting on the
# curled fingers (or, for "ok", on the index tip) with the least overlap,
# then checked by rendering.
_THUMB_OPEN = ((0, 0, 0), (0, 0, 0), (0, 0, 0))
_THUMB_TUCKED = ((-50, 0, 0), (0, 0, -20), (0, 0, -40))  # across the index/middle middle segments
_HAND_SHAPES = {
    "open": {"fingers": {finger: _STRAIGHT for finger in _FINGERS}, "thumb": _THUMB_OPEN},
    "fist": {"fingers": {finger: _CURLED for finger in _FINGERS}, "thumb": _THUMB_TUCKED},
    "point": {"fingers": {"Index": _STRAIGHT, "Middle": _CURLED, "Ring": _CURLED, "Little": _CURLED}, "thumb": _THUMB_TUCKED},
    "thumbs_up": {"fingers": {finger: _CURLED for finger in _FINGERS}, "thumb": ((0, 0, 10), (0, 0, 0), (0, 0, 0))},
    "middle_finger": {"fingers": {"Index": _CURLED, "Middle": _STRAIGHT, "Ring": _CURLED, "Little": _CURLED}, "thumb": ((-50, 0, 0), (0, 0, 0), (0, 0, -40))},
    "grip": {"fingers": {"Index": (25, 25, 15), "Middle": (70, 85, 55), "Ring": (70, 85, 55), "Little": (70, 85, 55)}, "thumb": _THUMB_TUCKED},
    "handshake": {"fingers": {finger: (30, 30, 20) for finger in _FINGERS}, "thumb": ((0, 0, 0), (0, 0, -10), (0, 0, -10))},
    # V sign: index and middle up and fanned apart, the others held down by the thumb.
    "peace": {"fingers": {"Index": _STRAIGHT, "Middle": _STRAIGHT, "Ring": _CURLED, "Little": _CURLED}, "thumb": _THUMB_TUCKED,
              "spread": {"Index": 10, "Middle": -10}},
    # Thumb and index tips meeting in a ring, the other three up and fanned.
    # Index/thumb from a numeric search on the MPFB character: of the
    # candidates whose fingertip skin touches (under 1 mm), the one with the
    # least overlap.
    # Holding shapes for the seated/utility clips.
    "relaxed_open": {"fingers": {finger: (15, 20, 12) for finger in _FINGERS}, "thumb": ((-15, 0, -5), (0, 0, -10), (0, 0, -5))},
    # Flat for hands resting on a surface (a curled little finger dips into it).
    "resting": {"fingers": {finger: (5, 8, 5) for finger in _FINGERS}, "thumb": ((-15, 0, -5), (0, 0, -5), (0, 0, -5))},
    "wheel": {"fingers": {finger: (60, 70, 45) for finger in _FINGERS}, "thumb": ((-30, 0, -10), (0, 0, -15), (0, 0, -10))},
    "cup": {"fingers": {finger: (40, 45, 30) for finger in _FINGERS}, "thumb": ((-35, 0, -20), (0, 0, -15), (0, 0, -10))},
    "phone": {"fingers": {finger: (35, 45, 30) for finger in _FINGERS}, "thumb": ((-20, 0, -10), (0, 0, -10), (0, 0, -10))},
    "typing": {"fingers": {finger: (25, 30, 20) for finger in _FINGERS}, "thumb": ((-20, 0, -10), (0, 0, -10), (0, 0, -5))},
    "ok": {"fingers": {"Index": (40, 55, 40), "Middle": (5, 8, 5), "Ring": (8, 10, 6), "Little": (10, 12, 8)},
           "thumb": ((-10, 0, -30), (0, 0, -30), (0, 0, -30)), "spread": {"Middle": -3, "Ring": -8, "Little": -14}},
}


def _hand(side: str, shape: str) -> dict[str, tuple[float, float, float]]:
    """Finger-bone keys for a named hand shape. An optional "spread" (degrees
    per finger, applied at the knuckle about the finger's local X) fans the
    fingers apart within the plane of the palm: positive moves a finger
    toward the thumb side, negative toward the little finger."""
    spec = _HAND_SHAPES[shape]
    spread = spec.get("spread", {})
    keys = {}
    for finger, curls in spec["fingers"].items():
        for segment, degrees in enumerate(curls, start=1):
            if segment == 1 and spread.get(finger):
                keys[f"{finger}{segment}.{side}"] = _compose(("x", spread[finger]), ("z", -degrees if side == "L" else degrees))
            else:
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


_RAISED_UPPER_ARM_R = r(41.9, 21.6, -30.9)


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
    # Arms held 8 degrees out so the hand clears the thigh as the leg swings
    # out (measured: the right hand sank ~1 cm into the thigh without it).
    strafe = [{**pose, "UpperArm.L": r(0, 0, 8), "UpperArm.R": r(0, 0, -8)} for pose in strafe]
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
    # Raised-hand gestures (MiddleFinger, Peace, OKSign) share this upper arm:
    # forward 50 degrees, then swung 30 degrees out from the midline, so the
    # hand sits beside the face (26 cm out from its centre line, measured on
    # the MPFB character) instead of in front of it.
    rest = {}
    thumbs = {"UpperArm.R": r(35, 0, -5), "Forearm.R": r(85), **_hand("R", "thumbs_up")}
    clips["ThumbsUp"] = {"frames": 50, "loop": False, "poses": {1: rest, 10: thumbs, 40: thumbs, 50: rest}}

    # Forearm raised, then turned 80 degrees about its own length (split
    # between forearm and wrist) so the back of the hand faces forward.
    middle = {"UpperArm.R": _RAISED_UPPER_ARM_R, "Forearm.R": _compose(("x", 100), ("y", 40)), "Hand.R": r(0, 40, 0), **_hand("R", "middle_finger"), "Head": r(-3, 0, -5)}
    clips["MiddleFinger"] = {"frames": 50, "loop": False, "poses": {1: rest, 10: middle, 40: middle, 50: rest}}

    # Raised hand turned about the forearm (split between forearm and wrist):
    # Peace with the palm toward the viewer, OK with the thumb side toward
    # the viewer so the ring is seen face-on.
    def raised(shape, twist):
        return {"UpperArm.R": _RAISED_UPPER_ARM_R, "Forearm.R": _compose(("x", 100), ("y", twist / 2)), "Hand.R": r(0, twist / 2, 0), **_hand("R", shape)}
    peace, ok = raised("peace", -80), raised("ok", -30)
    clips["Peace"] = {"frames": 50, "loop": False, "poses": {1: rest, 10: peace, 40: peace, 50: rest}}
    clips["OKSign"] = {"frames": 50, "loop": False, "poses": {1: rest, 10: ok, 40: ok, 50: rest}}

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
    # back, arms splayed. Like Prone it pivots around the hips; ground
    # contact brings the body down onto the floor.
    buckle = {"UpperLeg.L": r(30), "UpperLeg.R": r(25), "LowerLeg.L": r(-60), "LowerLeg.R": r(-55), "Foot.L": r(20), "Foot.R": r(20), "Chest": r(-15), "Head": r(-20),
              "UpperArm.L": r(20, 0, 10), "UpperArm.R": r(15, 0, -10), "Forearm.L": r(30), "Forearm.R": r(25)}
    falling = {"Hips": r(45), "UpperLeg.L": r(40), "UpperLeg.R": r(30), "LowerLeg.L": r(-50), "LowerLeg.R": r(-40), "Chest": r(10), "Head": r(15),
               "UpperArm.L": r(40, 0, 50), "UpperArm.R": r(35, 0, -50), "Forearm.L": r(20), "Forearm.R": r(20), **_hand("L", "open"), **_hand("R", "open")}
    lying = {"Hips": r(85), "UpperLeg.L": r(10, 0, 8), "UpperLeg.R": r(5, 0, -10), "LowerLeg.L": r(-15), "LowerLeg.R": r(-5), "Head": r(-10, 25),
             "UpperArm.L": r(0, 0, 70), "UpperArm.R": r(10, 0, -60), "Forearm.L": r(25), "Forearm.R": r(15), **_hand("L", "open"), **_hand("R", "open")}
    clips["Death"] = {"frames": 45, "loop": False, "poses": {1: rest, 8: buckle, 20: falling, 30: lying, 45: lying}}

    # --- Interaction ------------------------------------------------------
    crouch_reach = {"UpperLeg.L": r(75), "UpperLeg.R": r(65), "LowerLeg.L": r(-110), "LowerLeg.R": r(-100), "Foot.L": r(35), "Foot.R": r(35),
                    "Chest": r(-45), "Head": r(-15), "UpperArm.R": r(55, 0, -12), "Forearm.R": r(10), "UpperArm.L": r(20, 0, 10), "Forearm.L": r(40)}
    grab = _merge(crouch_reach, _hand("R", "fist"))
    holding = {"UpperArm.R": r(25, 0, 5), "Forearm.R": r(70), **_hand("R", "fist")}
    clips["PickUp"] = {"frames": 40, "loop": False, "poses": {1: rest, 14: _merge(crouch_reach, _hand("R", "open")), 18: grab, 32: holding, 40: holding}}

    reach = {"UpperArm.R": r(55, 0, 5), "Forearm.R": r(45), **_hand("R", "point"), "Head": r(-8)}
    press = _merge(reach, {"UpperArm.R": r(65, 0, 5), "Forearm.R": r(25)})
    clips["Interact"] = {"frames": 30, "loop": False, "poses": {1: rest, 8: reach, 12: press, 18: reach, 30: rest}}

    # --- Seated and utility ---------------------------------------------
    # Arm angles marked "solved" were found with an IK search on the MPFB
    # character: upper arm and elbow chosen so the centre of the palm lands
    # on a target point (wheel rim, ear, mouth, keyboard, box sides, door
    # handle, lever, knee), with the elbow kept below the hand. Bones only
    # rotate, so ground contact sets the seat height: for a chair the feet
    # are on the floor and the hips end up at seat height. There is no
    # chair, wheel or phone; the hands mime them.
    def arms(left=None, right=None):
        """(upper arm xyz, forearm x) per side -> arm keys."""
        keys = {}
        for side, values in (("L", left), ("R", right)):
            if values:
                (x, y, z), forearm = values
                keys[f"UpperArm.{side}"] = r(x, y, z)
                keys[f"Forearm.{side}"] = r(forearm)
        return keys

    def hands(shape_left, shape_right=None):
        return {**_hand("L", shape_left), **_hand("R", shape_right or shape_left)}

    seat = {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90)}
    chair = {**seat, "Chest": r(-4), **arms(((-24.3, 14.2, -5.3), 110.8), ((-24.3, -14.2, 5.3), 110.8)), **hands("resting")}  # solved: hands on the thighs
    clips["SitChair"] = {"frames": 60, "loop": True, "poses": {1: chair, 30: _merge(chair, {"Chest": r(-5), "Head": r(-2)}), 60: chair}}

    bench = {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-85), "LowerLeg.R": r(-85), "Chest": r(-28), "Head": r(14),
             **arms(((38.9, 6.9, -15.1), 67.7), ((38.9, -6.9, 15.1), 67.7)), **hands("relaxed_open")}  # solved: forearms on the knees, hands in front
    clips["SitBench"] = {"frames": 60, "loop": True, "poses": {1: bench, 30: _merge(bench, {"Chest": r(-29), "Head": r(12, 4)}), 60: bench}}

    typing_base = {**seat, "Chest": r(-6), "Head": r(-12), **arms(((3.2, 7.7, -11.4), 81.3), ((3.2, -7.7, 11.4), 81.3))}  # solved: hands on a desk keyboard

    def taps(left_finger, right_finger):
        keys = hands("typing")
        for side, finger in (("L", left_finger), ("R", right_finger)):
            for segment, degrees in enumerate((40, 40, 25), start=1):
                keys[f"{finger}{segment}.{side}"] = _curl(degrees, side)
        return keys
    clips["SitTyping"] = {"frames": 25, "loop": True, "poses": {
        1: {**typing_base, **taps("Index", "Middle")}, 7: {**typing_base, **taps("Middle", "Index")},
        13: {**typing_base, **taps("Ring", "Ring")}, 19: {**typing_base, **taps("Index", "Little")}, 25: {**typing_base, **taps("Index", "Middle")}}}

    car_seat = {"Chest": r(14), "UpperLeg.L": r(70), "UpperLeg.R": r(70), "LowerLeg.L": r(-45), "LowerLeg.R": r(-45), "Foot.L": r(15), "Foot.R": r(15), **hands("wheel")}
    drive = {**car_seat, **arms(((21.2, 3.6, -11.0), 52.5), ((21.2, -3.6, 11.0), 52.5))}  # solved: hands at 10 and 2 on a 38 cm wheel
    steer_left = {**car_seat, **arms(((14.5, -5.0, -15.0), 44.6), ((31.0, -17.5, 11.6), 56.3))}  # solved: wheel turned 45 degrees left
    steer_right = {**car_seat, **arms(((31.0, 17.5, -11.6), 56.3), ((14.5, 5.1, 15.0), 44.6))}  # solved: wheel turned 45 degrees right
    clips["Drive"] = {"frames": 60, "loop": True, "poses": {1: drive, 30: _merge(drive, {"Head": r(-1, 3)}), 60: drive}}
    clips["DriveSteerLeft"] = {"frames": 30, "loop": True, "poses": {1: steer_left, 30: steer_left}}
    clips["DriveSteerRight"] = {"frames": 30, "loop": True, "poses": {1: steer_right, 30: steer_right}}

    lying = {"Hips": r(88), "Head": r(-12), "UpperArm.L": r(0, 0, 15), "UpperArm.R": r(0, 0, -15), "Forearm.L": r(10), "Forearm.R": r(10), **hands("relaxed_open")}
    clips["LieDown"] = {"frames": 60, "loop": True, "poses": {1: lying, 30: _merge(lying, {"Chest": r(1)}), 60: lying}}

    phone_call = {"Head": r(-4, 0, -8), **arms(right=((47.9, 8.0, -8.0), 150.0)), **_hand("R", "phone")}  # solved: phone at the right ear
    clips["PhoneCall"] = {"frames": 90, "loop": True, "poses": {1: phone_call, 45: _merge(phone_call, {"Head": r(-6, 4, -8)}), 90: phone_call}}

    def phone_look(thumb_bend):
        pose = {"Head": r(-28), "Chest": r(-4), **arms(((15.1, 17.5, -12.3), 80.5), ((14.1, -15.4, 9.3), 89.1)), **hands("phone")}  # solved: phone held in front of the chest
        pose["Thumb3.R"] = _side("R", 0, 0, -thumb_bend)
        return pose
    clips["PhoneLook"] = {"frames": 40, "loop": True, "poses": {1: phone_look(10), 10: phone_look(35), 20: phone_look(10), 30: phone_look(30), 40: phone_look(10)}}

    sip = {"Head": r(6), **arms(right=((59.3, -17.2, -13.6), 125.0)), **_hand("R", "cup")}  # solved: cup just in front of the mouth
    holding_cup = {"UpperArm.R": r(15, 0, 4), "Forearm.R": r(80), **_hand("R", "cup")}
    clips["Drink"] = {"frames": 50, "loop": False, "poses": {1: holding_cup, 14: sip, 28: _merge(sip, {"Head": r(12)}), 38: holding_cup, 50: holding_cup}}

    carry = {"Chest": r(4), **arms(((-9.5, -2.4, -8.8), 66.3), ((-9.5, 2.4, 8.8), 66.3)), **hands("relaxed_open")}  # solved: hands on the sides of a 40 cm box
    clips["CarryIdle"] = {"frames": 60, "loop": True, "poses": {1: carry, 30: _merge(carry, {"Chest": r(5)}), 60: carry}}
    legs_only = lambda pose: {bone: value for bone, value in pose.items() if bone.split(".")[0] in ("UpperLeg", "LowerLeg", "Foot")}
    carry_walk = [{**legs_only(pose), **carry} for pose in (walk_contact, walk_passing, _mirror(walk_contact), _mirror(walk_passing))]
    clips["CarryWalk"] = {"frames": 33, "loop": True, "poses": _cycle((1, 9, 17, 25, 33), [*carry_walk, carry_walk[0]])}

    door_reach = {"Chest": r(-6, -10), **arms(right=((23.5, 3.8, 20.3), 40.0))}  # solved: handle at waist height, front right
    door_pull = {"Chest": r(2, -14), **arms(right=((2.0, 2.8, 12.0), 52.6))}  # solved: handle pulled back toward the hip
    clips["OpenDoor"] = {"frames": 40, "loop": False, "poses": {1: rest, 10: {**door_reach, **_hand("R", "open")}, 14: {**door_reach, **_hand("R", "grip")},
                                                                  26: {**door_pull, **_hand("R", "grip")}, 32: {**door_pull, **_hand("R", "open")}, 40: rest}}

    lever_grab = {"Chest": r(4), **arms(((57.3, 12.9, 4.4), 100.9), ((57.3, -12.9, -4.4), 100.9)), **hands("fist")}  # solved: lever above the head, in front
    lever_pulled = {"Chest": r(-10), "UpperLeg.L": r(20), "UpperLeg.R": r(20), "LowerLeg.L": r(-30), "LowerLeg.R": r(-30), "Foot.L": r(10), "Foot.R": r(10),
                    **arms(((24.8, 14.2, -13.2), 72.6), ((24.8, -14.2, 13.2), 72.6)), **hands("fist")}  # solved: pulled down to chest height
    clips["PullLever"] = {"frames": 40, "loop": False, "poses": {1: rest, 10: lever_grab, 22: lever_pulled, 30: lever_pulled, 40: rest}}

    kneel = {"UpperLeg.L": r(90), "LowerLeg.L": r(-90), "UpperLeg.R": r(-5), "LowerLeg.R": r(-90), "Foot.R": r(-40), "Chest": r(-10),
             **arms(left=((15.0, 2.5, -13.6), 77.2)), **hands("relaxed_open")}  # solved: left forearm resting on the left knee
    clips["Kneel"] = {"frames": 60, "loop": True, "poses": {1: kneel, 30: _merge(kneel, {"Chest": r(-11), "Head": r(-3)}), 60: kneel}}

    ladder = {"UpperLeg.L": r(55), "LowerLeg.L": r(-85), "Foot.L": r(20), "UpperLeg.R": r(15), "LowerLeg.R": r(-25),
              **arms(((75.4, -5.1, -4.2), 104.0), ((-7.5, -6.3, 3.0), 129.4)), **hands("grip")}  # solved: hands on rungs 40 cm apart
    clips["ClimbLadder"] = {"frames": 31, "loop": True, "poses": {1: ladder, 16: _mirror(ladder), 31: ladder}}

    return clips
