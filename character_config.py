"""Data contract shared by the Character Creation Suite UI and Blender worker."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

CONFIG_VERSION = 1
RIG_TYPES = ("standard", "extended")
BUILTIN_CLIPS = ("Idle", "Run", "Jump", "MeleeAttack", "HarvestSwing", "Fire", "Sit", "Crouch", "CrouchWalkRifle", "Prone", "Crawl", "ZombieAttack")
EXTENDED_CLIP_SUFFIX = "Extended"
BONE_NAMES = (
    "Hips", "Chest", "Neck", "Head",
    "UpperArm.L", "Forearm.L", "Hand.L", "UpperArm.R", "Forearm.R", "Hand.R",
    "UpperLeg.L", "LowerLeg.L", "Foot.L", "UpperLeg.R", "LowerLeg.R", "Foot.R",
)
# Bones that only exist on rig_type "extended" — see rig_builder.py.
EXTENDED_ONLY_BONE_NAMES = ("Spine", "UpperChest", "Shoulder.L", "Shoulder.R", "Toe.L", "Toe.R")
ALL_BONE_NAMES = BONE_NAMES + EXTENDED_ONLY_BONE_NAMES


def supported_clips() -> tuple[str, ...]:
    """Built-in clips (each with an Extended-suffixed sibling for rig_type
    "extended" — see animation_library.py) plus any user-saved preset
    animations (see custom_clips.py), de-duplicated so a preset can
    deliberately override a built-in of the same name."""
    from custom_clips import custom_clip_names
    builtin_and_extended = (*BUILTIN_CLIPS, *(f"{name}{EXTENDED_CLIP_SUFFIX}" for name in BUILTIN_CLIPS))
    return tuple(dict.fromkeys((*builtin_and_extended, *custom_clip_names())))


def default_config() -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "character_id": "NewCharacter",
        "display_name": "New Character",
        "archetype": "humanoid",
        "rig_type": "standard",
        "target_height_m": 1.75,
        "proportions": {"shoulder_width": 1.0, "torso_length": 1.0, "arm_length": 1.0, "leg_length": 1.0, "head_scale": 1.0, "body_width": 1.0},
        "materials": {
            "skin": [0.90, 0.65, 0.45, 1.0], "top": [0.10, 0.35, 0.90, 1.0],
            "bottom": [0.05, 0.05, 0.12, 1.0], "shoes": [0.02, 0.02, 0.02, 1.0],
        },
        "clips": ["Idle", "Run", "Jump", "MeleeAttack", "HarvestSwing", "Fire", "Sit"],
        "output_root": "build",
        "export_preview_glb": True,
        "export_separate_animations": True,
    }


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value).strip()).strip("_-")
    return cleaned or "Character"


def _number(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = default_config()
    config.update({key: value for key, value in raw.items() if key not in ("proportions", "materials", "clips")})
    config["character_id"] = safe_id(config["character_id"])
    config["display_name"] = str(config["display_name"]).strip() or config["character_id"]
    config["archetype"] = str(config["archetype"]).lower()
    rig_type = str(config.get("rig_type", "standard")).lower()
    config["rig_type"] = rig_type if rig_type in RIG_TYPES else "standard"
    config["target_height_m"] = _number(config["target_height_m"], 0.8, 2.8, 1.75)
    config["output_root"] = str(config["output_root"] or "build")
    config["export_preview_glb"] = bool(config["export_preview_glb"])
    config["export_separate_animations"] = bool(config["export_separate_animations"])
    proportions = raw.get("proportions", {}) if isinstance(raw.get("proportions", {}), dict) else {}
    config["proportions"] = {key: _number(proportions.get(key, value), 0.55, 1.8, value) for key, value in default_config()["proportions"].items()}
    materials = raw.get("materials", {}) if isinstance(raw.get("materials", {}), dict) else {}
    config["materials"] = {}
    for key, fallback in default_config()["materials"].items():
        value = materials.get(key, fallback)
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            value = fallback
        config["materials"][key] = [_number(channel, 0.0, 1.0, fallback[index]) for index, channel in enumerate(value)]
    selected = raw.get("clips", default_config()["clips"])
    available_clips = supported_clips()
    config["clips"] = [clip for clip in selected if clip in available_clips] if isinstance(selected, list) else []
    if not config["clips"]:
        config["clips"] = ["Idle"]
    config["version"] = CONFIG_VERSION
    return config


def load_config(path: str | Path) -> dict[str, Any]:
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))


def save_config(path: str | Path, config: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(validate_config(copy.deepcopy(config)), indent=2), encoding="utf-8")
