# create_character_and_animations.py
#
# Single entry point for the rigged box-humanoid pipeline.
#
# - Run it with your normal system Python: it finds Blender, launches it in
#   background mode pointed at this same file, and checks the outputs.
# - Blender then re-runs this file itself under bpy, which builds the mesh,
#   armature, skinning, and all three animations, and exports:
#     box_humanoid_rigged.glb          (static, bind pose)
#     animated_box_humanoid_rigged.fbx (Idle / Run / Jump as separate Takes)
#
# Same build logic as the previous two-file version (generate_rigged_box_humanoid.py
# + run_character_pipeline.py) - just merged into one file so there's a single
# command to run: `python create_character_and_animations.py`
#
# Design notes (unchanged from before):
#   - One mesh, one skeleton -> Unity can use Generic OR Humanoid rig type,
#     one draw call instead of 16.
#   - No object-level or root-bone TRANSLATION is keyframed anywhere.
#     Idle/Run/Jump are pure bone rotations, so Unity's "Apply Root Motion"
#     setting is a non-issue - nothing moves the root transform. Actual
#     displacement (including jump height) stays owned by your
#     CharacterController + movement script.
#   - Idle / Run / Jump are separate Blender Actions with a manual frame
#     range each, exported via bake_anim_use_all_actions=True so the FBX
#     contains three Takes - should import as three separate clips.
#
# NOTE: written without a local Blender to test against. Sanity-check bone
# weights, rest pose, and the three Take names on import.
#
# Run:
#   python create_character_and_animations.py

import os
import sys


try:
    import bpy
    RUNNING_IN_BLENDER = True
except ImportError:
    RUNNING_IN_BLENDER = False


# =====================================================================
# LAUNCHER - runs under plain system Python, re-invokes this file in Blender
# =====================================================================

def find_blender():
    import shutil

    blender_from_path = shutil.which("blender")
    if blender_from_path:
        return blender_from_path

    known_paths = [
        r"D:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.4\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.3\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
    ]

    for path in known_paths:
        if os.path.exists(path):
            return path

    return None


def run_launcher():
    import subprocess

    current_folder = os.path.dirname(os.path.abspath(__file__))
    this_script = os.path.abspath(__file__)

    static_output = os.path.join(current_folder, "box_humanoid_rigged.glb")
    animated_output = os.path.join(current_folder, "animated_box_humanoid_rigged.fbx")

    print("Rigged character pipeline")
    print("--------------------------")
    print(f"Working folder: {current_folder}")

    blender_path = find_blender()

    if blender_path is None:
        print()
        print("ERROR: Blender was not found.")
        print("Add Blender to PATH or add your blender.exe path to known_paths.")
        sys.exit(1)

    print(f"Found Blender: {blender_path}")

    print()
    print("=== Building rigged box humanoid (static GLB + animated FBX) ===")
    command = [blender_path, "--background", "--python", this_script]
    print("Running:", " ".join(f'"{x}"' if " " in x else x for x in command))

    try:
        result = subprocess.run(command, cwd=current_folder)
    except FileNotFoundError:
        print()
        print("ERROR: Could not launch Blender.")
        sys.exit(1)

    if result.returncode != 0:
        print()
        print("ERROR: Blender build step failed.")
        print(f"Exit code: {result.returncode}")
        sys.exit(result.returncode)

    print("Finished: Blender build step")

    for path, label in (
        (static_output, "box_humanoid_rigged.glb"),
        (animated_output, "animated_box_humanoid_rigged.fbx"),
    ):
        if not os.path.exists(path):
            print()
            print(f"ERROR: {label} was not created.")
            print(f"Missing file: {path}")
            sys.exit(1)
        print(f"Verified: {label}")

    print()
    print("All done!")
    print("Generated files:")
    print(f"- {static_output}")
    print(f"- {animated_output}")
    print()
    print("Takes in the FBX: Idle, Run, Jump, MeleeAttack, Fire, Sit")
    print("These should import as six separate clips - no manual splitting.")


# =====================================================================
# BUILD - runs under Blender's bpy
# =====================================================================

def run_build():
    import math

    # -----------------------------
    # Scene setup
    # -----------------------------

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    scene = bpy.context.scene
    scene.render.fps = 30

    try:
        bpy.ops.preferences.addon_enable(module="io_scene_gltf2")
    except Exception:
        pass  # already enabled in most Blender builds

    # -----------------------------
    # Materials
    # -----------------------------

    def create_material(name, color):
        mat = bpy.data.materials.new(name)
        mat.diffuse_color = color
        if mat.use_nodes:
            principled = mat.node_tree.nodes.get("Principled BSDF")
            if principled:
                principled.inputs["Base Color"].default_value = color
        return mat

    skin_mat = create_material("Skin", (0.9, 0.65, 0.45, 1.0))
    shirt_mat = create_material("Blue Shirt", (0.1, 0.35, 0.9, 1.0))
    trouser_mat = create_material("Dark Trousers", (0.05, 0.05, 0.12, 1.0))
    shoe_mat = create_material("Shoes", (0.02, 0.02, 0.02, 1.0))

    # -----------------------------
    # Bone rest layout
    # name: (head_pos, tail_pos, parent_name_or_None)
    # -----------------------------

    # NOTE: Blender's world space is always Z-up internally. These
    # coordinates are (x, y=depth, z=height) so the character actually
    # stands upright along Blender's real up axis - height must be the
    # 3rd component, not the 2nd.
    BONES = {
        "Hips":         ((0.0, 0.0, 0.90), (0.0, 0.0, 1.15), None),
        "Chest":        ((0.0, 0.0, 1.15), (0.0, 0.0, 1.95), "Hips"),
        "Neck":         ((0.0, 0.0, 1.95), (0.0, 0.0, 2.05), "Chest"),
        "Head":         ((0.0, 0.0, 2.05), (0.0, 0.0, 2.56), "Neck"),

        "UpperArm.L":   ((-0.52, 0.0, 1.92), (-0.52, 0.0, 1.44), "Chest"),
        "Forearm.L":    ((-0.52, 0.0, 1.44), (-0.52, 0.0, 0.96), "UpperArm.L"),
        "Hand.L":       ((-0.52, 0.0, 0.96), (-0.52, 0.0, 0.78), "Forearm.L"),

        "UpperArm.R":   ((0.52, 0.0, 1.92), (0.52, 0.0, 1.44), "Chest"),
        "Forearm.R":    ((0.52, 0.0, 1.44), (0.52, 0.0, 0.96), "UpperArm.R"),
        "Hand.R":       ((0.52, 0.0, 0.96), (0.52, 0.0, 0.78), "Forearm.R"),

        "UpperLeg.L":   ((-0.17, 0.0, 0.90), (-0.17, 0.0, 0.40), "Hips"),
        "LowerLeg.L":   ((-0.17, 0.0, 0.40), (-0.17, 0.0, -0.10), "UpperLeg.L"),
        "Foot.L":       ((-0.17, 0.0, -0.10), (-0.17, 0.35, -0.10), "LowerLeg.L"),

        "UpperLeg.R":   ((0.17, 0.0, 0.90), (0.17, 0.0, 0.40), "Hips"),
        "LowerLeg.R":   ((0.17, 0.0, 0.40), (0.17, 0.0, -0.10), "UpperLeg.R"),
        "Foot.R":       ((0.17, 0.0, -0.10), (0.17, 0.35, -0.10), "LowerLeg.R"),
    }

    # name: (size=(x,y=depth,z=height), center_position=(x,y=depth,z=height), material, bone)
    BOX_PARTS = {
        "Hips":       ((0.55, 0.28, 0.25), (0.0, 0.0, 1.00), trouser_mat, "Hips"),
        "Torso":      ((0.60, 0.30, 0.80), (0.0, 0.0, 1.55), shirt_mat, "Chest"),
        "Neck":       ((0.18, 0.18, 0.15), (0.0, 0.0, 2.00), skin_mat, "Neck"),
        "Head":       ((0.42, 0.42, 0.42), (0.0, 0.0, 2.30), skin_mat, "Head"),

        "UpperArm.L": ((0.22, 0.22, 0.48), (-0.52, 0.0, 1.68), shirt_mat, "UpperArm.L"),
        "Forearm.L":  ((0.20, 0.20, 0.45), (-0.52, 0.0, 1.20), skin_mat, "Forearm.L"),
        "Hand.L":     ((0.22, 0.22, 0.18), (-0.52, 0.0, 0.87), skin_mat, "Hand.L"),

        "UpperArm.R": ((0.22, 0.22, 0.48), (0.52, 0.0, 1.68), shirt_mat, "UpperArm.R"),
        "Forearm.R":  ((0.20, 0.20, 0.45), (0.52, 0.0, 1.20), skin_mat, "Forearm.R"),
        "Hand.R":     ((0.22, 0.22, 0.18), (0.52, 0.0, 0.87), skin_mat, "Hand.R"),

        "UpperLeg.L": ((0.23, 0.24, 0.50), (-0.17, 0.0, 0.65), trouser_mat, "UpperLeg.L"),
        "LowerLeg.L": ((0.21, 0.22, 0.50), (-0.17, 0.0, 0.15), trouser_mat, "LowerLeg.L"),
        "Foot.L":     ((0.25, 0.45, 0.16), (-0.17, 0.175, -0.10), shoe_mat, "Foot.L"),

        "UpperLeg.R": ((0.23, 0.24, 0.50), (0.17, 0.0, 0.65), trouser_mat, "UpperLeg.R"),
        "LowerLeg.R": ((0.21, 0.22, 0.50), (0.17, 0.0, 0.15), trouser_mat, "LowerLeg.R"),
        "Foot.R":     ((0.25, 0.45, 0.16), (0.17, 0.175, -0.10), shoe_mat, "Foot.R"),
    }

    # -----------------------------
    # Real-world scale correction
    # -----------------------------
    # BONES/BOX_PARTS above are authored at head-to-toe height 2.69m
    # (Head box top 2.30+0.42/2=2.51, Foot box bottom -0.10-0.16/2=-0.18)
    # - noticeably taller than a real adult. Rather than re-deriving every
    # coordinate by hand, scale the whole rig uniformly about the origin
    # (feet stay planted at z=0) down to a realistic average height, so
    # Unity import needs no manual scale correction afterward.
    _AUTHORED_HEIGHT_M = 2.69
    _TARGET_HEIGHT_M = 1.75
    _SCALE = _TARGET_HEIGHT_M / _AUTHORED_HEIGHT_M

    def _scale3(v):
        return (v[0] * _SCALE, v[1] * _SCALE, v[2] * _SCALE)

    BONES = {name: (_scale3(head), _scale3(tail), parent) for name, (head, tail, parent) in BONES.items()}
    BOX_PARTS = {name: (_scale3(size), _scale3(pos), mat, bone) for name, (size, pos, mat, bone) in BOX_PARTS.items()}

    # -----------------------------
    # Build armature
    # -----------------------------

    bpy.ops.object.armature_add(enter_editmode=True, location=(0, 0, 0))
    armature_obj = bpy.context.object
    armature_obj.name = "BoxHumanoid_Armature"
    armature_data = armature_obj.data
    armature_data.name = "BoxHumanoidSkeleton"

    edit_bones = armature_data.edit_bones
    edit_bones.remove(edit_bones[0])  # remove default bone

    created_edit_bones = {}
    for name, (head, tail, parent_name) in BONES.items():
        eb = edit_bones.new(name)
        eb.head = head
        eb.tail = tail
        created_edit_bones[name] = eb

    for name, (_, _, parent_name) in BONES.items():
        if parent_name:
            created_edit_bones[name].parent = created_edit_bones[parent_name]
            created_edit_bones[name].use_connect = False

    bpy.ops.object.mode_set(mode="OBJECT")

    # -----------------------------
    # Build mesh parts, assign vertex groups, join into one mesh
    # -----------------------------

    def make_box_object(name, size, position, material, bone_name):
        bpy.ops.mesh.primitive_cube_add(size=1, location=position)
        obj = bpy.context.object
        obj.name = name
        obj.dimensions = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(material)

        vg = obj.vertex_groups.new(name=bone_name)
        all_indices = [v.index for v in obj.data.vertices]
        vg.add(all_indices, 1.0, "REPLACE")

        return obj

    part_objects = []
    for name, (size, position, material, bone_name) in BOX_PARTS.items():
        part_objects.append(make_box_object(name, size, position, material, bone_name))

    bpy.ops.object.select_all(action="DESELECT")
    for obj in part_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = part_objects[0]
    bpy.ops.object.join()

    mesh_obj = bpy.context.object
    mesh_obj.name = "BoxHumanoid_Mesh"

    mesh_obj.parent = armature_obj
    armature_modifier = mesh_obj.modifiers.new(name="Armature", type="ARMATURE")
    armature_modifier.object = armature_obj

    # -----------------------------
    # Static bind-pose GLB export
    # -----------------------------

    bpy.ops.object.select_all(action="DESELECT")
    mesh_obj.select_set(True)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj

    bpy.ops.export_scene.gltf(
        filepath="box_humanoid_rigged.glb",
        export_format="GLB",
        use_selection=True,
    )

    print("Exported box_humanoid_rigged.glb (bind pose)")

    # -----------------------------
    # Animation helpers
    # -----------------------------

    armature_obj.animation_data_create()

    def reset_pose():
        for pb in armature_obj.pose.bones:
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = (0.0, 0.0, 0.0)

    def key_bone(bone_name, frame, rotation_euler=None):
        pb = armature_obj.pose.bones[bone_name]
        pb.rotation_mode = "XYZ"
        if rotation_euler is not None:
            pb.rotation_euler = rotation_euler
        pb.keyframe_insert(data_path="rotation_euler", frame=frame)

    def key_all_current_pose(frame):
        for pb in armature_obj.pose.bones:
            pb.rotation_mode = "XYZ"
            pb.keyframe_insert(data_path="rotation_euler", frame=frame)

    def new_action(name, frame_start, frame_end):
        action = bpy.data.actions.new(name)
        action.use_frame_range = True
        action.frame_start = frame_start
        action.frame_end = frame_end
        armature_obj.animation_data.action = action
        return action

    def set_interpolation(action, interpolation="BEZIER"):
        # Blender 4.x and older: fcurves live directly on the action.
        if hasattr(action, "fcurves"):
            for fcurve in action.fcurves:
                for kp in fcurve.keyframe_points:
                    kp.interpolation = interpolation
            return

        # Blender 4.4+ / 5.x layered actions: fcurves live under
        # layers -> strips -> channelbags.
        if hasattr(action, "layers"):
            for layer in action.layers:
                for strip in layer.strips:
                    if hasattr(strip, "channelbags"):
                        for channelbag in strip.channelbags:
                            for fcurve in channelbag.fcurves:
                                for kp in fcurve.keyframe_points:
                                    kp.interpolation = interpolation

    # -----------------------------
    # Idle: frames 1-60 (loop)
    # -----------------------------

    idle_action = new_action("Idle", 1, 60)
    scene.frame_start, scene.frame_end = 1, 60

    for frame in (1, 30, 60):
        scene.frame_set(frame)
        reset_pose()
        if frame == 30:
            key_bone("Chest", frame, (math.radians(1), 0, 0))
            key_bone("Head", frame, (math.radians(-1), 0, 0))
        key_all_current_pose(frame)

    set_interpolation(idle_action)

    # -----------------------------
    # Run: frames 1-31 (loop)
    # -----------------------------

    run_action = new_action("Run", 1, 31)
    scene.frame_start, scene.frame_end = 1, 31

    forward_leg = math.radians(42)
    back_leg = math.radians(-42)
    forward_arm = math.radians(38)
    back_arm = math.radians(-38)
    knee_bend = math.radians(32)

    run_frames = {1: "contact_a", 9: "passing", 16: "contact_b", 24: "passing", 31: "contact_a"}

    for frame, phase in run_frames.items():
        scene.frame_set(frame)
        reset_pose()

        if phase == "contact_a":
            key_bone("UpperLeg.L", frame, (forward_leg, 0, 0))
            key_bone("UpperLeg.R", frame, (back_leg, 0, 0))
            key_bone("LowerLeg.L", frame, (-knee_bend, 0, 0))
            key_bone("LowerLeg.R", frame, (knee_bend, 0, 0))
            key_bone("UpperArm.L", frame, (back_arm, 0, 0))
            key_bone("UpperArm.R", frame, (forward_arm, 0, 0))
        elif phase == "contact_b":
            key_bone("UpperLeg.L", frame, (back_leg, 0, 0))
            key_bone("UpperLeg.R", frame, (forward_leg, 0, 0))
            key_bone("LowerLeg.L", frame, (knee_bend, 0, 0))
            key_bone("LowerLeg.R", frame, (-knee_bend, 0, 0))
            key_bone("UpperArm.L", frame, (forward_arm, 0, 0))
            key_bone("UpperArm.R", frame, (back_arm, 0, 0))
        else:  # passing pose
            key_bone("LowerLeg.L", frame, (math.radians(10), 0, 0))
            key_bone("LowerLeg.R", frame, (math.radians(10), 0, 0))

        key_bone("Chest", frame, (math.radians(6), 0, 0))
        key_all_current_pose(frame)

    set_interpolation(run_action)

    # -----------------------------
    # Jump: frames 1-46 (no loop)
    # -----------------------------

    jump_action = new_action("Jump", 1, 46)
    scene.frame_start, scene.frame_end = 1, 46

    jump_poses = {
        1: {},  # neutral
        9: {  # crouch to launch
            "UpperLeg.L": (math.radians(-25), 0, 0),
            "UpperLeg.R": (math.radians(-25), 0, 0),
            "LowerLeg.L": (math.radians(35), 0, 0),
            "LowerLeg.R": (math.radians(35), 0, 0),
            "UpperArm.L": (math.radians(-25), 0, 0),
            "UpperArm.R": (math.radians(-25), 0, 0),
        },
        19: {  # airborne, legs tucked, arms up
            "UpperLeg.L": (math.radians(12), 0, 0),
            "UpperLeg.R": (math.radians(12), 0, 0),
            "LowerLeg.L": (math.radians(-10), 0, 0),
            "LowerLeg.R": (math.radians(-10), 0, 0),
            "UpperArm.L": (math.radians(65), 0, 0),
            "UpperArm.R": (math.radians(65), 0, 0),
        },
        33: {  # preparing to land
            "UpperLeg.L": (math.radians(8), 0, 0),
            "UpperLeg.R": (math.radians(8), 0, 0),
            "UpperArm.L": (math.radians(25), 0, 0),
            "UpperArm.R": (math.radians(25), 0, 0),
        },
        46: {},  # settled, neutral
    }

    for frame, pose in jump_poses.items():
        scene.frame_set(frame)
        reset_pose()
        for bone_name, rot in pose.items():
            key_bone(bone_name, frame, rot)
        key_all_current_pose(frame)

    set_interpolation(jump_action)

    # -----------------------------
    # MeleeAttack: frames 1-24 (no loop)
    # Right-arm-dominant (weapon sits in the right hand, see
    # PlayerWeaponController.cs) - wind-up -> swing -> recovery -> neutral.
    # Faster than the zombie's 30-frame swipe since this is player-controlled
    # and needs to feel responsive. DealMeleeDamage() is wired to an Animation
    # Event on the strike frame (frame 12) in Unity, not here - Blender has no
    # concept of Unity's Animation Event asset, that's added on the imported
    # clip in-editor.
    # -----------------------------

    melee_action = new_action("MeleeAttack", 1, 24)
    scene.frame_start, scene.frame_end = 1, 24

    melee_poses = {
        1: {},  # neutral
        6: {  # wind-up: right arm raised back, slight chest counter-twist
            "UpperArm.R": (math.radians(-60), 0, math.radians(-15)),
            "Forearm.R": (math.radians(-70), 0, 0),
            "Chest": (math.radians(-5), math.radians(-10), 0),
        },
        12: {  # strike: right arm swings forward/down hard, chest lunges into it
            "UpperArm.R": (math.radians(75), 0, math.radians(10)),
            "Forearm.R": (math.radians(20), 0, 0),
            "Chest": (math.radians(12), math.radians(10), 0),
        },
        18: {  # recovery
            "UpperArm.R": (math.radians(20), 0, 0),
            "Forearm.R": (math.radians(10), 0, 0),
            "Chest": (math.radians(4), 0, 0),
        },
        24: {},  # back to neutral
    }

    for frame, pose in melee_poses.items():
        scene.frame_set(frame)
        reset_pose()
        for bone_name, rot in pose.items():
            key_bone(bone_name, frame, rot)
        key_all_current_pose(frame)

    set_interpolation(melee_action)

    # -----------------------------
    # Fire: frames 1-12 (no loop)
    # Quick gun recoil - right arm kicks back and settles. Deliberately short:
    # PlayerWeaponController.cs's hitscan fires immediately on input, this
    # clip is cosmetic feedback only, not a timing gate.
    # -----------------------------

    fire_action = new_action("Fire", 1, 12)
    scene.frame_start, scene.frame_end = 1, 12

    fire_poses = {
        1: {},  # neutral
        3: {  # recoil kick
            "UpperArm.R": (math.radians(-18), 0, 0),
            "Forearm.R": (math.radians(-12), 0, 0),
            "Chest": (math.radians(-4), 0, 0),
        },
        12: {},  # settled back to neutral
    }

    for frame, pose in fire_poses.items():
        scene.frame_set(frame)
        reset_pose()
        for bone_name, rot in pose.items():
            key_bone(bone_name, frame, rot)
        key_all_current_pose(frame)

    set_interpolation(fire_action)

    # -----------------------------
    # Sit: frames 1-30 (loop) - static seated pose for chair interactions
    # (Assets/Scripts/ChairSystem/ChairSeat.cs sets the Animator's "IsSeated"
    # bool). Thighs swing forward to horizontal, knees bend back to bring the
    # shins vertical again (mirrors Run's "knee_bend compensates the thigh's
    # own swing" relationship, just a full 90 degrees instead of 32), chest
    # leans forward slightly, arms rest toward the lap. Same subtle mid-frame
    # sway Idle uses (Chest/Head +-1 degree) so it reads as a held pose, not
    # a frozen statue, while occupying a chair.
    # -----------------------------

    sit_action = new_action("Sit", 1, 30)
    scene.frame_start, scene.frame_end = 1, 30

    sit_thigh = math.radians(90)    # thigh: hanging down -> horizontal
    sit_knee = math.radians(-90)    # shin: compensates the thigh's swing, back to vertical
    sit_arm = math.radians(25)      # upper arm forward, toward the lap
    sit_forearm = math.radians(55)  # elbow bend, hand settles near the lap

    sit_base_pose = {
        "UpperLeg.L": (sit_thigh, 0, 0),
        "UpperLeg.R": (sit_thigh, 0, 0),
        "LowerLeg.L": (sit_knee, 0, 0),
        "LowerLeg.R": (sit_knee, 0, 0),
        "UpperArm.L": (sit_arm, 0, 0),
        "UpperArm.R": (sit_arm, 0, 0),
        "Forearm.L": (sit_forearm, 0, 0),
        "Forearm.R": (sit_forearm, 0, 0),
        "Chest": (math.radians(8), 0, 0),
    }

    for frame in (1, 15, 30):
        scene.frame_set(frame)
        reset_pose()
        for bone_name, rot in sit_base_pose.items():
            key_bone(bone_name, frame, rot)
        if frame == 15:
            key_bone("Chest", frame, (math.radians(9), 0, 0))
            key_bone("Head", frame, (math.radians(-1), 0, 0))
        key_all_current_pose(frame)

    set_interpolation(sit_action)

    # -----------------------------
    # Export animated FBX - all six actions as separate Takes
    # -----------------------------

    bpy.ops.object.select_all(action="DESELECT")
    mesh_obj.select_set(True)
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj

    bpy.ops.export_scene.fbx(
        filepath="animated_box_humanoid_rigged.fbx",
        use_selection=True,
        object_types={"ARMATURE", "MESH"},
        axis_forward="-Z",
        axis_up="Y",

        add_leaf_bones=False,
        path_mode="AUTO",

        bake_anim=True,
        bake_anim_use_all_actions=True,
        bake_anim_use_nla_strips=False,
        bake_anim_force_startend_keying=True,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
    )

    print("Exported animated_box_humanoid_rigged.fbx")
    print("Takes: Idle (1-60, loop), Run (1-31, loop), Jump (1-46, no loop), "
          "MeleeAttack (1-24, no loop), Fire (1-12, no loop), Sit (1-30, loop)")


# =====================================================================
# Entry point
# =====================================================================

if __name__ == "__main__":
    if RUNNING_IN_BLENDER:
        run_build()
    else:
        run_launcher()
