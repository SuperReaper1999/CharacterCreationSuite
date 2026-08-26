# Character Creation Suite

Double-click `Run Character Creation Suite.bat`, load `presets/player.json` or `presets/zombie.json`, customise it, then select **Generate Unity FBX**.

The Character tab includes a fast live silhouette preview for proportions and
palette changes. The Materials tab has native colour pickers and swatches; the
generated Blender GLB remains the authoritative final geometry preview.

Each clip in the Animations tab has a **View anim in Blender** button. It opens an interactive Blender window on the character as currently configured in the tabs (proportions, materials, height) with that one clip baked and looping, so you can orbit and inspect it before committing to a build — it's the exact same rig code path as the real export (`rig_builder.py`), not a separate stand-in. Close the window when you're done; it only writes a scratch `build/_preview/character_config.json`, never anything under the character's own `build/<character-id>/` output folder.

The preview window is also an editor. Enter Pose Mode, adjust the bones, insert keyframes as usual (`I` with all bones selected keys the whole pose, matching how every clip here is authored), then use the **Character Suite** panel in the 3D viewport's side tab (`N`) to name it and hit **Save as Preset Animation**. That samples every frame that has a keyframe on any bone and writes a rotation-only JSON to `presets/animations/<name>.json` — reusing that same name overrides a built-in clip of the same name (you'll get a warning, not a block); a new name adds a new one. Saving is rejected if the action has any location/scale keys, so the rotation-only contract below can't be broken from the editor either. Back in the suite, click **Refresh clip list** (or reload a config) to pick up anything saved or changed since the window opened.

The suite writes all generated output to `build/<character-id>/`:

- `<character-id>.fbx` — Unity import asset with selected animation Takes baked in (unchanged legacy artifact).
- `<character-id>_Model.fbx` — the same mesh and rig with no animation, for pipelines that import the model and clips as separate Unity assets.
- `Animations/<clip-name>.fbx` — one skeleton-only FBX per selected clip, no mesh. Each shares the exact bone names and hierarchy of `<character-id>_Model.fbx`, so Unity's "copy from other Avatar" retargeting maps cleanly onto the model.
- `<character-id>_Preview.glb` — bind-pose preview, not the Unity animation asset.
- `character_config.json` — reproducible build configuration.
- `manifest.json` — generated asset contract and validation metadata, including `model_fbx` and `animation_fbx` paths.

The model and per-clip animation FBX files are on by default (`export_separate_animations` in the config); set it to `false` to skip them and only produce the combined `<character-id>.fbx`.

The player preset includes two distinct two-handed tool clips: `MeleeAttack` for the sledgehammer and `HarvestSwing` for pickaxes, axes, and shovels. Both preserve a credible support-hand pose; gameplay should apply the harvest at `HarvestSwing` frame 16 (0.5 seconds at 30fps).

`Crouch`, `CrouchWalkRifle`, `Prone`, and `Crawl` are available as selectable clips in the Animations tab (off by default, same as `ZombieAttack` — check the box to include them in a build). `CrouchWalkRifle` is a looping crouched stride with both arms locked into a two-handed rifle-ready pose (the arms don't swing with the gait, since a held weapon shouldn't). `Crouch`'s knee bend was fixed after an initial release had the sign backwards, which folded the knee the wrong way and left the feet dangling at a broken-looking angle instead of flat on the ground — the fix (and every stride clip added alongside it) was validated by rendering the pose in headless Blender before shipping it, not just by eyeballing the numbers.

`Prone` pitches the whole rig ~horizontal around the hip bone's rest height rather than lying flat on the ground: because clips are rotation-only (see below), the pose cannot carry the downward offset needed to put the body at ground level. For a 1.75 m-tall character the hip pivot sits at `target_height_m * (0.90 / 2.69)` ≈ 0.59 m, so the posed body floats roughly between 0.40 m and 1.00 m off the ground until the Unity side lowers the character's root transform (and collider height) by that offset while the Prone state is active — the same way Unity, not the clip, already owns all root positioning here. `Crawl` is a stride cycle on top of that same pitched pose; its arm/leg swing is authored on different rotation axes than every other clip in this file (Y/Z instead of X) because composing an X-axis stride swing onto Hips' already-80-degree X pitch doesn't add cleanly — it flings the limb, confirmed by rendering it before ruling it out.

### Rig types

The Character tab has a **Rig type** selector: `standard` (the original 16 bones) or `extended` (22 bones — adds `Spine`, `UpperChest`, `Shoulder.L`/`Shoulder.R`, and `Toe.L`/`Toe.R`). Both are plain Unity-compatible hierarchies; Unity's Humanoid Avatar doesn't require any particular bone count, only a sane parent chain, so `extended` isn't a special case on the Unity side. Every standard bone keeps the same name and rest position on `extended` — `MeleeAttack` and every other standard-rig clip bakes correctly on an `extended` character too, it just leaves the new bones at rest (`rig_builder.build_character` picks the hierarchy; `bake_pose_action` skips any bone a clip references that the current armature doesn't have, so a clip never crashes a build over a rig mismatch — it just quietly doesn't animate what isn't there).

Every built-in clip has an `Extended`-suffixed sibling (`IdleExtended`, `RunExtended`, …) generated from the original by `animation_library._extend_pose`, not hand-authored separately — hand-authoring 12 parallel clips would drift from the originals the first time one got tuned. The transform: a clip's `Chest` rotation is split 0.35/0.35/0.30 across `Spine`/`Chest`/`UpperChest` (the fractions sum to 1, so the total bend at the top of the spine matches the original exactly, just arrives as a curve instead of one hinge); `Shoulder.L`/`R` gets 15% of whichever axis `UpperArm.L`/`R` uses, and `Toe.L`/`R` gets 40% of `Foot`'s rotation (or 15% of `LowerLeg`'s, for clips that don't key `Foot`) as a following motion. Original bones are never altered by this. Validated by rendering `CrouchExtended`, `MeleeAttackExtended`, `ProneExtended`, and `CrawlExtended` in headless Blender — the last two mattered most, since that's where a naive addition would have hit the same X-axis-under-heavy-pitch problem `Crawl` itself did; the transform stayed on the already-safe axes and rendered clean.

## Design boundaries

- Two selectable rig hierarchies (`rig_type`): fixed 16-bone `standard`, or 22-bone `extended`. Proportions, materials, height, and clip selection are configurable on either.
- Every generated clip has rotation-only bone keys. Root translation/root motion is never authored — this is why `Prone` needs a Unity-side root offset rather than being baked into the clip (see above).
- Unity Animation Events remain Unity-side concerns and are intentionally not generated.
- FBX export uses the known Unity settings: `-Z` forward, `Y` up, all Actions as Takes, and no leaf bones.
- The original `create_character_and_animations.py` and `create_zombie_and_animations.py` are retained unchanged as legacy references until this suite has been tested in Unity.
