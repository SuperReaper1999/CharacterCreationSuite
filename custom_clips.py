"""User-authored preset animations, round-tripped through the Blender
preview window's "Save as Preset Animation" panel (see blender_preview.py).

Built-in clips live as Python data in animation_library.py. Custom ones
saved from the editor live here as JSON, one file per clip, so editing
and re-saving an animation never means touching the codebase. Rotation
values are stored in degrees for human-readability, matching the r()
helper's convention in animation_library.py; animation_library.clips()
converts them to radians on load, same as every built-in clip.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from character_config import ALL_BONE_NAMES, safe_id

ROOT = Path(__file__).resolve().parent
CUSTOM_CLIPS_DIR = ROOT / "presets" / "animations"


def _degrees_to_radians_pose(pose: dict[str, list[float]]) -> dict[str, tuple[float, float, float]]:
    return {
        bone: tuple(math.radians(float(component)) for component in rotation)
        for bone, rotation in pose.items()
        if bone in ALL_BONE_NAMES
    }


def list_custom_clips() -> dict[str, dict[str, Any]]:
    """Load every JSON preset in presets/animations/ into the same shape
    animation_library.clips() uses: {"frames": int, "loop": bool, "poses": {frame: {bone: (rx, ry, rz)}}}."""
    result: dict[str, dict[str, Any]] = {}
    if not CUSTOM_CLIPS_DIR.is_dir():
        return result
    for path in sorted(CUSTOM_CLIPS_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            poses = {int(frame): _degrees_to_radians_pose(pose) for frame, pose in raw["poses"].items()}
            result[path.stem] = {"frames": int(raw["frames"]), "loop": bool(raw.get("loop", True)), "poses": poses}
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
    return result


def custom_clip_names() -> tuple[str, ...]:
    return tuple(list_custom_clips())


def save_custom_clip(name: str, frames: int, loop: bool, poses_degrees: dict[int, dict[str, tuple[float, float, float]]]) -> Path:
    clip_name = safe_id(name)
    CUSTOM_CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": clip_name,
        "frames": int(frames),
        "loop": bool(loop),
        "poses": {
            str(frame): {bone: [round(component, 3) for component in rotation] for bone, rotation in pose.items()}
            for frame, pose in sorted(poses_degrees.items())
        },
    }
    path = CUSTOM_CLIPS_DIR / f"{clip_name}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
