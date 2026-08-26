"""Fixed-topology, rotation-only animation definitions for the suite."""

from __future__ import annotations

import math
from typing import Any


def r(x: float, y: float = 0.0, z: float = 0.0) -> tuple[float, float, float]:
    return math.radians(x), math.radians(y), math.radians(z)


def clips() -> dict[str, dict[str, Any]]:
    run = {}
    for frame, phase in ((1, 1), (9, 0), (16, -1), (24, 0), (31, 1)):
        pose = {"Chest": r(6)}
        if phase:
            pose.update({"UpperLeg.L": r(42 * phase), "UpperLeg.R": r(-42 * phase), "LowerLeg.L": r(-32 * phase), "LowerLeg.R": r(32 * phase), "UpperArm.L": r(-38 * phase), "UpperArm.R": r(38 * phase)})
        else:
            pose.update({"LowerLeg.L": r(10), "LowerLeg.R": r(10)})
        run[frame] = pose
    return {
        "Idle": {"frames": 60, "loop": True, "poses": {1: {}, 30: {"Chest": r(1), "Head": r(-1)}, 60: {}}},
        "Run": {"frames": 31, "loop": True, "poses": run},
        "Jump": {"frames": 46, "loop": False, "poses": {1: {}, 9: {"UpperLeg.L": r(-25), "UpperLeg.R": r(-25), "LowerLeg.L": r(35), "LowerLeg.R": r(35), "UpperArm.L": r(-25), "UpperArm.R": r(-25)}, 19: {"UpperLeg.L": r(12), "UpperLeg.R": r(12), "LowerLeg.L": r(-10), "LowerLeg.R": r(-10), "UpperArm.L": r(65), "UpperArm.R": r(65)}, 33: {"UpperLeg.L": r(8), "UpperLeg.R": r(8), "UpperArm.L": r(25), "UpperArm.R": r(25)}, 46: {}}},
        # A deliberate two-handed heavy strike for the sledgehammer. The
        # support arm stays involved, so Unity must retain LeftGripPoint IK.
        "MeleeAttack": {"frames": 30, "loop": False, "poses": {
            1: {},
            8: {"Chest": r(-8, -18), "UpperArm.L": r(-72, 8, 16), "Forearm.L": r(-48, 0, -8), "UpperArm.R": r(-78, -10, -16), "Forearm.R": r(-52, 0, 8)},
            15: {"Chest": r(18, 22), "UpperArm.L": r(72, -8, 10), "Forearm.L": r(22), "UpperArm.R": r(78, 8, -10), "Forearm.R": r(18)},
            22: {"Chest": r(6, 5), "UpperArm.L": r(22, 0, 4), "Forearm.L": r(12), "UpperArm.R": r(26, 0, -4), "Forearm.R": r(12)},
            30: {},
        }},
        # A controlled two-handed stroke for pickaxes, axes, and shovels.
        # Contact is frame 16 (0.5 seconds at 30fps).
        "HarvestSwing": {"frames": 32, "loop": False, "poses": {
            1: {},
            9: {"Chest": r(-6, -14), "UpperArm.L": r(-58, 12, 20), "Forearm.L": r(-44, 0, -12), "UpperArm.R": r(-72, -12, -18), "Forearm.R": r(-54, 0, 10)},
            16: {"Chest": r(14, 18), "UpperArm.L": r(58, -10, 14), "Forearm.L": r(18, 0, 4), "UpperArm.R": r(76, 10, -12), "Forearm.R": r(16, 0, -4)},
            24: {"Chest": r(5, 4), "UpperArm.L": r(18, 0, 5), "Forearm.L": r(10), "UpperArm.R": r(24, 0, -5), "Forearm.R": r(12)},
            32: {},
        }},
        "Fire": {"frames": 12, "loop": False, "poses": {1: {}, 3: {"UpperArm.R": r(-18), "Forearm.R": r(-12), "Chest": r(-4)}, 12: {}}},
        "Sit": {"frames": 30, "loop": True, "poses": {1: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(8)}, 15: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(9), "Head": r(-1)}, 30: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(8)}}},
        # Held combat crouch: hips back, knees bent, torso braced forward.
        # Rig-relative only, like every other clip here — feet do not plant
        # in place since there is no IK, matching the fidelity of Jump/Sit.
        "Crouch": {"frames": 30, "loop": True, "poses": {
            1: {"UpperLeg.L": r(-48), "UpperLeg.R": r(-48), "LowerLeg.L": r(70), "LowerLeg.R": r(70), "Chest": r(10), "UpperArm.L": r(-18), "UpperArm.R": r(-18), "Forearm.L": r(25), "Forearm.R": r(25)},
            15: {"UpperLeg.L": r(-48), "UpperLeg.R": r(-48), "LowerLeg.L": r(70), "LowerLeg.R": r(70), "Chest": r(11), "UpperArm.L": r(-18), "UpperArm.R": r(-18), "Forearm.L": r(25), "Forearm.R": r(25), "Head": r(-1)},
            30: {"UpperLeg.L": r(-48), "UpperLeg.R": r(-48), "LowerLeg.L": r(70), "LowerLeg.R": r(70), "Chest": r(10), "UpperArm.L": r(-18), "UpperArm.R": r(-18), "Forearm.L": r(25), "Forearm.R": r(25)},
        }},
        # Held prone: Hips pitches the whole rig ~horizontal, head counter-
        # rotated up to look forward. Rotation-only, so this pivots around
        # the hip bone's rest height rather than lying flat on the ground —
        # see README "Design boundaries" for what the Unity side must do
        # about that before this is usable as an actual prone stance.
        "Prone": {"frames": 30, "loop": True, "poses": {
            1: {"Hips": r(80), "Forearm.L": r(-15), "Forearm.R": r(-15), "Head": r(-25)},
            15: {"Hips": r(80), "Forearm.L": r(-15), "Forearm.R": r(-15), "Head": r(-24)},
            30: {"Hips": r(80), "Forearm.L": r(-15), "Forearm.R": r(-15), "Head": r(-25)},
        }},
        "ZombieAttack": {"frames": 30, "loop": False, "poses": {1: {"Chest": r(10)}, 8: {"Chest": r(-18), "UpperArm.L": r(-55), "UpperArm.R": r(-55), "Forearm.L": r(-35), "Forearm.R": r(-35)}, 15: {"Chest": r(28), "UpperArm.L": r(70), "UpperArm.R": r(70), "Forearm.L": r(20), "Forearm.R": r(20)}, 23: {"Chest": r(8), "UpperArm.L": r(18), "UpperArm.R": r(18)}, 30: {"Chest": r(10)}}},
    }
