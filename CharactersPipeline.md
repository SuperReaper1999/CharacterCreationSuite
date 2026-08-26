# Character Pipeline — Current State

## Character Creation Suite

`character_suite.py` is the current configurable entry point. It uses shared
config, rig, mesh, animation, and export logic instead of maintaining a copied
player generator and zombie generator. Run `Run Character Creation Suite.bat`,
load a preset from `presets/`, then generate a Unity-ready FBX into
`build/<character-id>/`.

The suite deliberately preserves the old pipeline's hard constraints: fixed
humanoid topology (16-bone "standard", or the newer 22-bone "extended" rig
with Spine/UpperChest/Shoulder/Toe added — both configurable per character,
never mixed at build time), metres, Blender Z-up authoring, Unity FBX axis
conversion, rotation-only clips, no Animation Events, and no leaf bones.
Generated build folders are disposable; the JSON preset is the editable source
of truth. The old scripts below remain as legacy references until the new FBX
assets have been imported and verified in Unity.

**Status: partially integrated.** `RagdollController.cs` is live
(`Assets/Scripts/HealthScripts/`), wired to Player and Zombie. The rest of
this pipeline's own deliverables are unconfirmed against what's actually in
the project.

## What's live
- `RagdollController` on Player and Zombie, subscribed to `Health.OnDied`,
  `componentsToDisableOnDeath` set. **Ragdoll physics itself is inert** —
  zero `Rigidbody`/`Collider` components exist on either skeleton; the
  Ragdoll Wizard has never been run.

## Unresolved
- Whether `Assets/CharacterModels/PlayerCharacterRig.fbx` and
  `ZombieRig.fbx` (already in the project) **are** this pipeline's output
  (`animated_box_humanoid_rigged.fbx`/`animated_zombie_rigged.fbx`) under
  different names, or a separate asset entirely. Checked directly, couldn't
  tell from the files alone.
- `create_zombie_and_animations.py` has never been run/confirmed in this
  project — keep this script, it's still the only way to verify or
  regenerate that rig.

## If you do run the generator scripts — known gotchas
1. Blender 5.0 moved `Action.fcurves` into a layered structure
   (`action.layers[].strips[].channelbags[].fcurves`). Both scripts check
   for `fcurves` first, fall back to the layered path.
2. Author bone/box coordinates with height on **Z**, not Y — Blender is
   Z-up internally regardless of which axis the data is authored against,
   and authoring height on Y produces a character lying on its side in
   Blender itself, before export ever touches it.
3. Root/bones never keyframe translation — Idle/Run/Jump/Attack are pure
   bone rotations, so Unity's own movement/AI script fully owns displacement
   without fighting baked motion.

## Unity-side setup, if regenerating
- Only the animated FBX needs importing — the GLB is a static bind-pose
  preview, not needed in-project.
- Ragdoll Wizard bone mapping is direct: Hips→Pelvis, Chest→Middle Spine,
  Head→Head, UpperArm.L/R→Left/Right Arm, Forearm.L/R→Left/Right Elbow,
  UpperLeg.L/R→Left/Right Hips, LowerLeg.L/R→Left/Right Knee.

## Still open
- Player has no Attack clip (only zombie does).
- Push-force ragdolls need `Health.TakeDamage` extended to carry a hit
  direction.
- The "random icosphere" reported once, never reproduced or explained —
  watch for it.
