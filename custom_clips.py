"""User-authored preset animations, round-tripped through the Blender
preview window's "Save as Preset Animation" panel (see blender_preview.py).

Built-in clips live as Python data in animation_library.py. Custom ones
live here as JSON, one file per clip, so editing and re-saving an
animation never means touching the codebase.

Two formats are read:
- "game_engine" (written by the preview editor): local rotations of the
  character's own rig bones (MPFB game_engine names such as "upperarm_l"),
  as quaternions [w, x, y, z]. Keyed directly onto the character.
- legacy "authoring" (written by earlier versions; no "skeleton" key):
  local Euler rotations in degrees on the authoring skeleton (names such
  as "UpperArm.L"), converted to radians and retargeted like the built-in
  clips (see retarget.py).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from character_config import BONE_NAMES, safe_id

ROOT = Path(__file__).resolve().parent
CUSTOM_CLIPS_DIR = ROOT / "presets" / "animations"
NATIVE_SKELETON = "game_engine"


def _authoring_pose(pose: dict[str, list[float]]) -> dict[str, tuple[float, float, float]]:
    return {
        bone: tuple(math.radians(float(component)) for component in rotation)
        for bone, rotation in pose.items()
        if bone in BONE_NAMES
    }


def _native_pose(pose: dict[str, list[float]]) -> dict[str, tuple[float, float, float, float]]:
    return {bone: tuple(float(component) for component in rotation) for bone, rotation in pose.items() if len(rotation) == 4}


def list_custom_clips() -> dict[str, dict[str, Any]]:
    """Load every JSON preset in presets/animations/ into the shape
    animation_library.clips() uses: {"frames", "loop", "skeleton", "poses"}."""
    result: dict[str, dict[str, Any]] = {}
    if not CUSTOM_CLIPS_DIR.is_dir():
        return result
    for path in sorted(CUSTOM_CLIPS_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            native = raw.get("skeleton") == NATIVE_SKELETON
            convert = _native_pose if native else _authoring_pose
            poses = {int(frame): convert(pose) for frame, pose in raw["poses"].items()}
            result[path.stem] = {"frames": int(raw["frames"]), "loop": bool(raw.get("loop", True)),
                                 "skeleton": NATIVE_SKELETON if native else "authoring", "poses": poses}
        except (json.JSONDecodeError, KeyError, ValueError, TypeError, AttributeError):
            continue
    return result


def custom_clip_names() -> tuple[str, ...]:
    return tuple(list_custom_clips())


def save_custom_clip(name: str, frames: int, loop: bool, poses: dict[int, dict[str, tuple[float, float, float, float]]]) -> Path:
    """Save a clip keyed on the character's own rig: {frame: {bone: (w, x, y, z)}}."""
    clip_name = safe_id(name)
    CUSTOM_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": clip_name,
        "skeleton": NATIVE_SKELETON,
        "rotation": "quaternion_wxyz",
        "frames": int(frames),
        "loop": bool(loop),
        "poses": {
            str(frame): {bone: [round(component, 6) for component in rotation] for bone, rotation in pose.items()}
            for frame, pose in sorted(poses.items())
        },
    }
    path = CUSTOM_CLIPS_DIR / f"{clip_name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
