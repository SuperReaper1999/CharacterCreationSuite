"""Data contract shared by the Character Creation Suite UI and Blender worker."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

CONFIG_VERSION = 2
BUILTIN_CLIPS = (
    "Idle", "Walk", "Run", "Sprint", "StrafeLeft", "StrafeRight", "Jump", "Crouch", "CrouchWalkRifle", "Prone", "Crawl", "Sit",
    "MeleeAttack", "HarvestSwing", "Punch", "Kick", "Throw", "Fire", "PistolIdle", "PistolFire", "Reload", "HitReact", "Death",
    "Wave", "Point", "ThumbsUp", "MiddleFinger", "Peace", "OKSign", "Handshake", "Talk", "PickUp", "Interact",
    "ZombieWalk", "ZombieAttack",
    "SitChair", "SitBench", "SitTyping", "Drive", "DriveSteerLeft", "DriveSteerRight", "LieDown",
    "PhoneCall", "PhoneLook", "Drink", "CarryIdle", "CarryWalk", "OpenDoor", "PullLever", "Kneel", "ClimbLadder",
)
# Suffix older configs used for the 52-bone versions of the built-in clips
# (e.g. "IdleExtended"), from when a 16-bone rig also existed. Those
# versions are now the only ones and use the plain names; validate_config
# maps the old names over.
LEGACY_CLIP_SUFFIX = "Extended"
# The 52-bone authoring skeleton (authoring_skeleton.py) that the built-in
# clips are written against: body bones, then 3 segments per
# finger (Proximal=1, Intermediate=2, Distal=3), named
# "<Finger><segment>.<L|R>" (the Unity Humanoid finger convention).
FINGER_BONE_NAMES = tuple(f"{finger}{segment}.{side}" for side in ("L", "R") for finger in ("Thumb", "Index", "Middle", "Ring", "Little") for segment in (1, 2, 3))
BONE_NAMES = (
    "Hips", "Spine", "Chest", "UpperChest", "Neck", "Head",
    "Shoulder.L", "UpperArm.L", "Forearm.L", "Hand.L", "Shoulder.R", "UpperArm.R", "Forearm.R", "Hand.R",
    "UpperLeg.L", "LowerLeg.L", "Foot.L", "Toe.L", "UpperLeg.R", "LowerLeg.R", "Foot.R", "Toe.R",
) + FINGER_BONE_NAMES


def supported_clips() -> tuple[str, ...]:
    """Built-in clips (see animation_library.py) plus any user-saved preset
    animations (see custom_clips.py), de-duplicated so a preset can
    deliberately override a built-in of the same name."""
    from custom_clips import custom_clip_names
    return tuple(dict.fromkeys((*BUILTIN_CLIPS, *custom_clip_names())))


def default_config() -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "character_id": "NewCharacter",
        "display_name": "New Character",
        "target_height_m": 1.75,
        # MakeHuman body macros, 0-1: gender (0 female, 1 male), age
        # (0.5 = 25 years), muscle and weight (0.5 = average).
        "body": {"gender": 1.0, "age": 0.5, "muscle": 0.5, "weight": 0.5},
        # MPFB asset names (folder names in MPFB's data/skins, data/hair,
        # data/clothes). Empty hair/outfit/shoes = none.
        "skin": "young_caucasian_male",
        "hair": "short02",
        "outfit": "male_casualsuit01",
        "shoes": "shoes01",
        "proportions": {"shoulder_width": 1.0, "torso_length": 1.0, "arm_length": 1.0, "leg_length": 1.0, "head_scale": 1.0, "body_width": 1.0},
        # Colour slots, linear RGBA. Alpha is the strength: 0 keeps the
        # asset's own texture colours, 1 applies the colour fully (skin is
        # multiplied with the skin texture; top/bottom/shoes recolour the
        # fabric while keeping its shading).
        "materials": {
            "skin": [1.0, 1.0, 1.0, 0.0], "top": [0.10, 0.35, 0.90, 0.0],
            "bottom": [0.05, 0.05, 0.12, 0.0], "shoes": [0.02, 0.02, 0.02, 0.0],
        },
        "clips": ["Idle", "Run", "Jump", "MeleeAttack", "HarvestSwing", "Fire", "Sit"],
        "output_root": "build",
        "export_preview_glb": True,
        "export_separate_animations": True,
        # Key a vertical Root offset so the character's lowest point stays on
        # the floor in every frame (see retarget.ground_clip).
        "ground_contact": True,
    }


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value).strip()).strip("_-")
    return cleaned or "Character"


def _number(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def _current_clip_name(name: str) -> str:
    """Map an older config's "<Clip>Extended" name to "<Clip>" when that
    clip is built in; any other name (including custom clips) is kept."""
    base = name[:-len(LEGACY_CLIP_SUFFIX)]
    return base if name.endswith(LEGACY_CLIP_SUFFIX) and base in BUILTIN_CLIPS else name


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    config = default_config()
    config.update({key: value for key, value in raw.items() if key not in ("proportions", "materials", "clips", "body")})
    config["character_id"] = safe_id(config["character_id"])
    config["display_name"] = str(config["display_name"]).strip() or config["character_id"]
    # "archetype" was a label nothing read; it was removed. Drop it from
    # older configs so it isn't carried forward when they are re-saved.
    config.pop("archetype", None)
    # "rig_type" chose between two old procedural rigs; characters are now
    # always built by MPFB, so older configs' value is dropped.
    config.pop("rig_type", None)
    config["target_height_m"] = _number(config["target_height_m"], 0.8, 2.8, 1.75)
    body = raw.get("body", {}) if isinstance(raw.get("body", {}), dict) else {}
    config["body"] = {key: _number(body.get(key, value), 0.0, 1.0, value) for key, value in default_config()["body"].items()}
    for key in ("skin", "hair", "outfit", "shoes"):
        value = str(config.get(key) or "").strip()
        config[key] = re.sub(r"[^A-Za-z0-9_-]+", "", value)
    if not config["skin"]:
        config["skin"] = default_config()["skin"]
    config["output_root"] = str(config["output_root"] or "build")
    config["export_preview_glb"] = bool(config["export_preview_glb"])
    config["export_separate_animations"] = bool(config["export_separate_animations"])
    config["ground_contact"] = bool(config["ground_contact"])
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
    selected = [_current_clip_name(str(clip)) for clip in selected] if isinstance(selected, list) else []
    config["clips"] = [clip for clip in dict.fromkeys(selected) if clip in available_clips]
    if not config["clips"]:
        config["clips"] = ["Idle"]
    config["version"] = CONFIG_VERSION
    return config


def load_config(path: str | Path) -> dict[str, Any]:
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))


def save_config(path: str | Path, config: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(validate_config(copy.deepcopy(config)), indent=2), encoding="utf-8")
