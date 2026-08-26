"""Interactive single-clip preview for the Character Creation Suite.

Opens a normal (non-headless) Blender window, builds the character from a
config the same way blender_build.py does (same rig_builder, so what you
see is the actual export rig — not a stand-in), bakes one clip's action,
and loops playback so you can orbit/inspect it live.

Run only through Blender, WITHOUT --background:
    blender --python blender_preview.py -- config.json ClipName
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from animation_library import clips
from character_config import load_config
from rig_builder import bake_pose_action, build_character


def after_double_dash() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def frame_view(armature, mesh) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True); armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    for area in bpy.context.window.screen.areas:
        if area.type == "VIEW_3D":
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            with bpy.context.temp_override(area=area, region=region):
                for space in area.spaces:
                    if space.type == "VIEW_3D":
                        space.shading.type = "MATERIAL"
                bpy.ops.view3d.view_selected()


def preview(config_path: Path, clip_name: str) -> None:
    config = load_config(config_path)
    available = clips()
    if clip_name not in available:
        raise SystemExit(f"Unknown clip '{clip_name}'. Known clips: {', '.join(available)}")
    clip = available[clip_name]

    armature, mesh, _bones = build_character(config)
    armature.animation_data_create()
    bake_pose_action(armature, clip_name, clip)

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = clip["frames"]
    scene.frame_current = 1

    def loop_handler(current_scene):
        if current_scene.frame_current >= current_scene.frame_end:
            current_scene.frame_current = current_scene.frame_start

    bpy.app.handlers.frame_change_pre.append(loop_handler)

    if not bpy.app.background:
        frame_view(armature, mesh)
        bpy.ops.screen.animation_play()
    else:
        print(f"PREVIEW_BUILT_HEADLESS {clip_name} frames={clip['frames']}")


if __name__ == "__main__":
    args = after_double_dash()
    if len(args) < 2:
        raise SystemExit("Usage: blender --python blender_preview.py -- config.json ClipName")
    preview(Path(args[0]).resolve(), args[1])
