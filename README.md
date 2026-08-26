# Character Creation Suite

Double-click `Run Character Creation Suite.bat`, load `presets/player.json` or `presets/zombie.json`, customise it, then select **Generate Unity FBX**.

The Character tab includes a fast live silhouette preview for proportions and
palette changes. The Materials tab has native colour pickers and swatches; the
generated Blender GLB remains the authoritative final geometry preview.

The suite writes all generated output to `build/<character-id>/`:

- `<character-id>.fbx` — Unity import asset with selected animation Takes.
- `<character-id>_Preview.glb` — bind-pose preview, not the Unity animation asset.
- `character_config.json` — reproducible build configuration.
- `manifest.json` — generated asset contract and validation metadata.

The player preset includes two distinct two-handed tool clips: `MeleeAttack` for the sledgehammer and `HarvestSwing` for pickaxes, axes, and shovels. Both preserve a credible support-hand pose; gameplay should apply the harvest at `HarvestSwing` frame 16 (0.5 seconds at 30fps).

## Design boundaries

- Fixed 16-bone humanoid hierarchy; proportions, materials, height, and clip selection are configurable.
- Every generated clip has rotation-only bone keys. Root translation/root motion is never authored.
- Unity Animation Events remain Unity-side concerns and are intentionally not generated.
- FBX export uses the known Unity settings: `-Z` forward, `Y` up, all Actions as Takes, and no leaf bones.
- The original `create_character_and_animations.py` and `create_zombie_and_animations.py` are retained unchanged as legacy references until this suite has been tested in Unity.
