"""Data contract shared by the Character Creation Suite UI and Blender worker."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

CONFIG_VERSION = 1
SUPPORTED_CLIPS = ("Idle", "Run", "Jump", "MeleeAttack", "Fire", "Sit", "ZombieAttack")


def default_config() -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "character_id": "NewCharacter",
        "display_name": "New Character",
        "archetype": "humanoid",
        "target_height_m": 1.75,
        "proportions": {"shoulder_width": 1.0, "torso_length": 1.0, "arm_length": 1.0, "leg_length": 1.0, "head_scale": 1.0, "body_width": 1.0},
        "materials": {
            "skin": [0.90, 0.65, 0.45, 1.0], "top": [0.10, 0.35, 0.90, 1.0],
            "bottom": [0.05, 0.05, 0.12, 1.0], "shoes": [0.02, 0.02, 0.02, 1.0],
        },
        "clips": ["Idle", "Run", "Jump", "MeleeAttack", "Fire", "Sit"],
        "output_root": "build",
        "export_preview_glb": True,
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
    config["target_height_m"] = _number(config["target_height_m"], 0.8, 2.8, 1.75)
    config["output_root"] = str(config["output_root"] or "build")
    config["export_preview_glb"] = bool(config["export_preview_glb"])
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
    config["clips"] = [clip for clip in selected if clip in SUPPORTED_CLIPS] if isinstance(selected, list) else []
    if not config["clips"]:
        config["clips"] = ["Idle"]
    config["version"] = CONFIG_VERSION
    return config


def load_config(path: str | Path) -> dict[str, Any]:
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))


def save_config(path: str | Path, config: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(validate_config(copy.deepcopy(config)), indent=2), encoding="utf-8")
