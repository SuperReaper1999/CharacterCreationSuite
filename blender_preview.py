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
from character_config import BUILTIN_CLIPS, load_config, safe_id
from custom_clips import save_custom_clip
from retarget import GROUND_BONE, bake_clips
from rig_builder import action_fcurves, build_character


def after_double_dash() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def find_armature():
    return next(obj for obj in bpy.data.objects if obj.type == "ARMATURE")


class CCS_OT_save_preset(bpy.types.Operator):
    """Sample the current action's keyframes and save them as a reusable
    preset animation JSON under presets/animations/: rotation-only, as
    local quaternions on the character's own rig bones."""
    bl_idname = "ccs.save_preset"
    bl_label = "Save as Preset Animation"

    def execute(self, context):
        scene = context.scene
        name = scene.ccs_preset_name.strip()
        if not name:
            self.report({"ERROR"}, "Enter a preset name before saving.")
            return {"CANCELLED"}

        armature = find_armature()
        action = armature.animation_data.action if armature.animation_data else None
        if action is None:
            self.report({"ERROR"}, "No action on the armature to save.")
            return {"CANCELLED"}

        rotation_paths = ("rotation_quaternion", "rotation_euler", "rotation_axis_angle")
        # The Root location channel is the automatic ground-contact offset;
        # it isn't saved (builds recompute it for each character).
        ground_path = f'pose.bones["{GROUND_BONE}"].location'
        rotation_curves = [c for c in action_fcurves(action) if c.data_path.endswith(rotation_paths)]
        bad_curves = [c.data_path for c in action_fcurves(action) if not c.data_path.endswith(rotation_paths) and c.data_path != ground_path]
        if bad_curves:
            self.report({"ERROR"}, f"Only bone rotation can be saved (rotation-only rig contract). Remove keys on: {', '.join(sorted(set(bad_curves)))}")
            return {"CANCELLED"}
        if not rotation_curves:
            self.report({"ERROR"}, "No keyframes found on this action.")
            return {"CANCELLED"}

        significant_frames = sorted({round(point.co.x) for curve in rotation_curves for point in curve.keyframe_points})
        original_frame = scene.frame_current
        poses: dict[int, dict[str, tuple[float, float, float, float]]] = {}
        for frame in significant_frames:
            scene.frame_set(frame)
            # matrix_basis works whatever rotation mode the bone was keyed in.
            poses[frame] = {bone.name: tuple(bone.matrix_basis.to_quaternion()) for bone in armature.pose.bones}
        scene.frame_set(original_frame)

        frames = significant_frames[-1]
        saved_path = save_custom_clip(name, frames, scene.ccs_preset_loop, poses)
        safe_name = safe_id(name)
        message = f"Saved preset '{safe_name}' ({frames} frames, {len(significant_frames)} keyframes) to {saved_path}"
        if safe_name in BUILTIN_CLIPS:
            message += f" — this overrides the built-in '{safe_name}' clip."
        self.report({"INFO"}, message)
        return {"FINISHED"}


class CCS_PT_panel(bpy.types.Panel):
    bl_idname = "CCS_PT_panel"
    bl_label = "Character Suite"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Character Suite"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Edit the pose in Pose Mode (I to keyframe),")
        layout.label(text="then save it as a reusable preset:")
        layout.prop(context.scene, "ccs_preset_name", text="Preset name")
        layout.prop(context.scene, "ccs_preset_loop", text="Loops")
        layout.operator(CCS_OT_save_preset.bl_idname, icon="EXPORT")


_CLASSES = (CCS_OT_save_preset, CCS_PT_panel)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ccs_preset_name = bpy.props.StringProperty(name="Preset name", default="")
    bpy.types.Scene.ccs_preset_loop = bpy.props.BoolProperty(name="Loops", default=True)


def frame_view(armature, meshes) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for mesh in meshes:
        mesh.select_set(True)
    armature.select_set(True)
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

    register()

    armature, meshes, _bones = build_character(config)
    bake_clips(armature, {clip_name: clip}, ground_meshes=meshes if config["ground_contact"] else None)

    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = clip["frames"]
    scene.frame_current = 1
    scene.ccs_preset_name = clip_name
    scene.ccs_preset_loop = bool(clip.get("loop", True))

    def loop_handler(current_scene):
        if current_scene.frame_current >= current_scene.frame_end:
            current_scene.frame_current = current_scene.frame_start

    bpy.app.handlers.frame_change_pre.append(loop_handler)

    if not bpy.app.background:
        frame_view(armature, meshes)
        bpy.ops.screen.animation_play()
    else:
        print(f"PREVIEW_BUILT_HEADLESS {clip_name} frames={clip['frames']}")


if __name__ == "__main__":
    args = after_double_dash()
    if len(args) < 2:
        raise SystemExit("Usage: blender --python blender_preview.py -- config.json ClipName")
    preview(Path(args[0]).resolve(), args[1])
