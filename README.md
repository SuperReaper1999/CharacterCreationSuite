# Character Creation Suite

Double-click `Run Character Creation Suite.bat`, load `presets/player.json` or `presets/zombie.json`, customise it, then select **Generate Unity FBX**.

The Character tab includes a fast live silhouette preview for proportions and
palette changes. The Materials tab has native colour pickers and swatches; the
generated Blender GLB remains the authoritative final geometry preview.

Each clip in the Animations tab has a **View anim in Blender** button. It opens an interactive Blender window on the character as currently configured in the tabs (proportions, materials, height) with that one clip baked and looping, so you can orbit and inspect it before committing to a build — it's the exact same rig code path as the real export (`rig_builder.py`), not a separate stand-in. Close the window when you're done; it only writes a scratch `build/_preview/character_config.json`, never anything under the character's own `build/<character-id>/` output folder.

The suite writes all generated output to `build/<character-id>/`:

- `<character-id>.fbx` — Unity import asset with selected animation Takes baked in (unchanged legacy artifact).
- `<character-id>_Model.fbx` — the same mesh and rig with no animation, for pipelines that import the model and clips as separate Unity assets.
- `Animations/<clip-name>.fbx` — one skeleton-only FBX per selected clip, no mesh. Each shares the exact bone names and hierarchy of `<character-id>_Model.fbx`, so Unity's "copy from other Avatar" retargeting maps cleanly onto the model.
- `<character-id>_Preview.glb` — bind-pose preview, not the Unity animation asset.
- `character_config.json` — reproducible build configuration.
- `manifest.json` — generated asset contract and validation metadata, including `model_fbx` and `animation_fbx` paths.

The model and per-clip animation FBX files are on by default (`export_separate_animations` in the config); set it to `false` to skip them and only produce the combined `<character-id>.fbx`.

The player preset includes two distinct two-handed tool clips: `MeleeAttack` for the sledgehammer and `HarvestSwing` for pickaxes, axes, and shovels. Both preserve a credible support-hand pose; gameplay should apply the harvest at `HarvestSwing` frame 16 (0.5 seconds at 30fps).

`Crouch` and `Prone` are available as selectable clips in the Animations tab (off by default, same as `ZombieAttack` — check the box to include them in a build). `Prone` pitches the whole rig ~horizontal around the hip bone's rest height rather than lying flat on the ground: because clips are rotation-only (see below), the pose cannot carry the downward offset needed to put the body at ground level. For a 1.75 m-tall character the hip pivot sits at `target_height_m * (0.90 / 2.69)` ≈ 0.59 m, so the posed body floats roughly between 0.40 m and 1.00 m off the ground until the Unity side lowers the character's root transform (and collider height) by that offset while the Prone state is active — the same way Unity, not the clip, already owns all root positioning here.

## Design boundaries

- Fixed 16-bone humanoid hierarchy; proportions, materials, height, and clip selection are configurable.
- Every generated clip has rotation-only bone keys. Root translation/root motion is never authored — this is why `Prone` needs a Unity-side root offset rather than being baked into the clip (see above).
- Unity Animation Events remain Unity-side concerns and are intentionally not generated.
- FBX export uses the known Unity settings: `-Z` forward, `Y` up, all Actions as Takes, and no leaf bones.
- The original `create_character_and_animations.py` and `create_zombie_and_animations.py` are retained unchanged as legacy references until this suite has been tested in Unity.
