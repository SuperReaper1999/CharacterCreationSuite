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
        "MeleeAttack": {"frames": 24, "loop": False, "poses": {1: {}, 6: {"UpperArm.R": r(-60, 0, -15), "Forearm.R": r(-70), "Chest": r(-5, -10)}, 12: {"UpperArm.R": r(75, 0, 10), "Forearm.R": r(20), "Chest": r(12, 10)}, 18: {"UpperArm.R": r(20), "Forearm.R": r(10), "Chest": r(4)}, 24: {}}},
        "Fire": {"frames": 12, "loop": False, "poses": {1: {}, 3: {"UpperArm.R": r(-18), "Forearm.R": r(-12), "Chest": r(-4)}, 12: {}}},
        "Sit": {"frames": 30, "loop": True, "poses": {1: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(8)}, 15: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(9), "Head": r(-1)}, 30: {"UpperLeg.L": r(90), "UpperLeg.R": r(90), "LowerLeg.L": r(-90), "LowerLeg.R": r(-90), "UpperArm.L": r(25), "UpperArm.R": r(25), "Forearm.L": r(55), "Forearm.R": r(55), "Chest": r(8)}}},
        "ZombieAttack": {"frames": 30, "loop": False, "poses": {1: {"Chest": r(10)}, 8: {"Chest": r(-18), "UpperArm.L": r(-55), "UpperArm.R": r(-55), "Forearm.L": r(-35), "Forearm.R": r(-35)}, 15: {"Chest": r(28), "UpperArm.L": r(70), "UpperArm.R": r(70), "Forearm.L": r(20), "Forearm.R": r(20)}, 23: {"Chest": r(8), "UpperArm.L": r(18), "UpperArm.R": r(18)}, 30: {"Chest": r(10)}}},
    }
