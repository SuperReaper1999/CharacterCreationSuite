# Character Creation Suite

A Blender character generator: it builds a rigged, animated low-poly humanoid from a JSON preset and saves it as a `.blend`. FBX and GLB exports are written alongside for use in other apps.

Double-click `Run Character Creation Suite.bat` (or run `python character_suite.py`; Blender 5.0 must be on PATH or in its default install folder), load a preset from `presets/` (`player` or `zombie`), customise it, then select **Generate character**.

The Character tab includes a fast live silhouette preview for proportions and
palette changes. The Materials tab has native colour pickers and swatches; the
generated `.blend` is the authoritative final result (the GLB carries the same geometry).

Each clip in the Animations tab has a **View anim in Blender** button. It opens an interactive Blender window on the character as currently configured in the tabs (proportions, materials, height) with that one clip baked and looping, so you can orbit and inspect it before committing to a build — it's the exact same rig code path as the real export (`rig_builder.py`), not a separate stand-in. Close the window when you're done; it only writes a scratch `build/_preview/character_config.json`, never anything under the character's own `build/<character-id>/` output folder.

The preview window is also an editor. Enter Pose Mode, adjust the bones, insert keyframes as usual (`I` with all bones selected keys the whole pose, matching how every clip here is authored), then use the **Character Suite** panel in the 3D viewport's side tab (`N`) to name it and hit **Save as Preset Animation**. That samples every frame that has a keyframe on any bone and writes a rotation-only JSON to `presets/animations/<name>.json` — reusing that same name overrides a built-in clip of the same name (you'll get a warning, not a block); a new name adds a new one. Saving is rejected if the action has any location/scale keys, so the rotation-only contract below can't be broken from the editor either. Back in the suite, click **Refresh clip list** (or reload a config) to pick up anything saved or changed since the window opened.

## Output

The suite writes all generated output to `build/<character-id>/`:

- `<character-id>.blend` — **the primary output.** The rigged character as built (the Bevel modifier is left live, not applied), its materials with textures packed into the file, and every selected clip as a named Action. Each Action has a fake user so all of them are kept; switch between them in the Action Editor. The first selected clip is assigned on open, with the scene frame range set to it. Blender-native axes (Z-up), 30 fps.
- `<character-id>.fbx` — FBX export with every selected clip baked in as a take, for game engines and other apps (axes converted to `-Z` forward, `Y` up).
- `<character-id>_Model.fbx` — the same mesh and rig with no animation, for pipelines that import the model and clips as separate assets.
- `Animations/<clip-name>.fbx` — one skeleton-only FBX per selected clip, no mesh. Each shares the exact bone names and hierarchy of `<character-id>_Model.fbx`, so retargeting maps cleanly onto the model. Each file's single take is named after the clip (e.g. `Run`) and starts at frame 0, the same timing as the matching take in `<character-id>.fbx`.
- `<character-id>_Preview.glb` — bind-pose preview with no animation, exported with modifiers applied so it has the same bevelled geometry as the FBX.
- `Textures/<character-id>_<material>.png` — one small solid-colour texture per material (`skin`/`top`/`bottom`/`shoes`), wired into that material's Base Color. The `.blend` packs these; `<character-id>.fbx` and `<character-id>_Model.fbx` embed them (`embed_textures=True`) as well as referencing the standalone files, so the FBX alone shows the right colours even without the `Textures/` folder next to it.
- `character_config.json` — reproducible build configuration.
- `manifest.json` — generated asset contract and validation metadata, including `blend`, `model_fbx`, `animation_fbx`, and `textures` paths.

The model and per-clip animation FBX files are on by default (`export_separate_animations` in the config); set it to `false` to skip them and only produce the combined `<character-id>.fbx`. Set `export_preview_glb` to `false` to skip the GLB.

## The rig

Every character uses the same fixed 52-bone humanoid: `Hips`, `Spine`/`Chest`/`UpperChest`, `Neck`, `Head`, `Shoulder`/`UpperArm`/`Forearm`/`Hand` per side, `UpperLeg`/`LowerLeg`/`Foot`/`Toe` per side, and full fingers — `Thumb`/`Index`/`Middle`/`Ring`/`Little`, each split into 3 segments named `<Finger>1/2/3.<L|R>` for Proximal/Intermediate/Distal (the Unity Humanoid finger convention), 30 bones across both hands. Height, proportions (shoulder width, torso length, arm length, leg length, head size, body width) and the four material colours are configurable per character.

The mesh is built from simple primitives: the neck, arms, legs, toes, and every finger segment are cylinders; the torso is three stacked boxes matching the `Spine`/`Chest`/`UpperChest` bones so bending the spine deforms it; the head is a sphere. The whole mesh gets a bevel modifier (`offset_type="PERCENT"`, 25%, angle-limited) plus smooth shading. PERCENT scales the bevel to each edge's own length, so the same modifier rounds both the torso boxes and the tiny finger segments proportionally — a fixed absolute width sized for the torso would swallow a whole finger segment, and one sized for fingers would barely dent the torso. The bevel modifier is added *before* the Armature modifier, so it rounds the rest-pose geometry once and the armature deforms that already-rounded result per frame — adding it after would mean re-bevelling posed geometry on every frame, including at extreme bends where it could self-intersect.

The head has a simple face: two eyes (white sphere + smaller dark pupil sphere), a nose (a small forward-pointing cone — the only rotated primitive in the rig; it's rotated -90° about X after creation so its point aims along +Y), and a mouth (a thin dark box). All of it is geometry, not a texture. Eyes/pupils/mouth use two fixed materials (`eye_white`, `eye_dark`) that aren't part of `config["materials"]` — an eye colour isn't a clothing choice the way skin/top/bottom/shoes are, so it doesn't go through the configurable palette and isn't included in the per-material texture export. All five face parts are bound directly to the `Head` bone, since none of them move independently of the head.

## Animations

12 built-in clips, all rotation-only:

| Clip | Frames | Loops | Notes |
|---|---|---|---|
| `Idle` | 60 | yes | Subtle breathing sway. |
| `Run` | 31 | yes | Alternating leg/arm stride. |
| `Jump` | 46 | no | Crouch, launch, land. |
| `MeleeAttack` | 30 | no | Two-handed overhead heavy strike. |
| `HarvestSwing` | 32 | no | Two-handed downward tool stroke; contact at frame 16 (0.5 s at 30 fps). |
| `Fire` | 12 | no | Short right-arm recoil. |
| `Sit` | 30 | yes | Seated, knees at 90°. |
| `Crouch` | 30 | yes | Held crouch, feet flat. |
| `CrouchWalkRifle` | 31 | yes | Crouched stride with both arms held in a two-handed rifle-ready pose (the arms don't swing with the gait). |
| `Prone` | 30 | yes | Lying face-down (see below). |
| `Crawl` | 31 | yes | Stride cycle on the face-down pose (see below). |
| `ZombieAttack` | 30 | no | Two-armed lunge. |

The player preset selects `Idle`, `Run`, `Jump`, `MeleeAttack`, `HarvestSwing`, `Fire`, and `Sit`; tick any others in the Animations tab to include them in a build.

**How clips are authored.** Each clip is keyed on the main body bones (`Hips`, `Chest`, `Neck`, `Head`, arms, legs, feet) in `animation_library._authored_clips`. `animation_library._expand_pose` then fills in the rest of the rig from those values, so the extra joints follow the authored motion rather than being keyed by hand: the `Chest` rotation is split 0.35/0.35/0.30 across `Spine`/`Chest`/`UpperChest` (the fractions sum to 1, so the total bend at the top of the spine matches the authored value, just arriving as a curve instead of one hinge); `Shoulder.L`/`R` gets 15% of `UpperArm.L`/`R`'s rotation; `Toe.L`/`R` gets 40% of `Foot`'s rotation (or 15% of `LowerLeg`'s, for clips that don't key `Foot`). Fingers get a fixed relaxed-hand curl in every frame of every clip (heavier at the middle knuckle than the tip) — a static baseline, since nothing in a pose signals "gripping" vs "open hand" reliably enough to vary it.

**Prone and Crawl.** `Prone` tips the whole rig forward ~80° around the hip bone's rest height so the character lies face-down (chest toward the ground, head lifted to look ahead, elbows slightly bent). Because clips are rotation-only (see below), the pose cannot carry the downward offset needed to put the body on the ground: for a 1.75 m-tall character the hip pivot sits at `target_height_m * (0.90 / 2.69)` ≈ 0.59 m, so the posed mesh spans roughly 0.12–1.01 m above the ground until whatever plays the clip lowers the character by that offset while it's prone — in Blender, move the armature object down; in a game engine, the root transform (and collider). This range is measured by `tests/smoke_test.py` (it prints it as an `INFO` line). `Crawl` is a stride cycle on top of that same face-down pose; its arm/leg swing is authored on different rotation axes than the other clips (Y/Z instead of X), because an X-axis stride swing on top of the Hips' 80° pitch lifts the limbs off the ground instead of sweeping them along it.

## Testing

`tests/smoke_test.py` is a headless end-to-end check. It builds every preset in `presets/` plus an "every clip" character, each through the real `blender_build.py` in a fresh Blender process (the same path as **Generate character**), then inspects the outputs from inside Blender:

- every file listed in `manifest.json` exists;
- the `.blend` opens with the armature (52 bones), mesh, one fake-user Action per clip (rotation-only), the first clip assigned, and packed textures;
- 52 bones in the combined, model, and per-clip FBX;
- no take has moving location keys (the rotation-only contract);
- the combined FBX has one take per clip, and each per-clip FBX has one take named after its clip with the same frame range;
- the GLB is skinned and carries the modifier-applied geometry;
- `Prone`/`Crawl` face the ground with naturally bent elbows, and `Idle` faces forward.

```
python tests/smoke_test.py                                  # finds blender on PATH or the default install paths
python tests/smoke_test.py --blender "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
python tests/smoke_test.py --bpy-python <python with "pip install bpy">
```

It writes only to a temporary folder (pass `--keep` to keep it) and exits non-zero if any check fails. It needs no tkinter. It does not test the GUI, the interactive Blender preview/editor, or how other apps import the FBX.

## Design boundaries

- One fixed 52-bone rig hierarchy. Proportions, materials, height, and clip selection are configurable.
- Every generated clip has rotation-only bone keys. Root translation/root motion is never authored — this is why `Prone` needs the character lowered by the scene or engine rather than having it baked into the clip (see above).
- Animation events/markers for game engines are not generated.
- The `.blend` is Blender-native. Only the FBX export converts axes: `-Z` forward, `Y` up, all Actions as takes, and no leaf bones.
- Each of the 4 configurable materials (`skin`/`top`/`bottom`/`shoes`) is backed by a small solid-colour PNG texture, not just a flat material value, and every body part except the face uses one of those 4 — there's no per-body-part texture, since parts sharing a material would just be pixel-identical duplicates of it.
- Older configs still load: a `rig_type` value is dropped, and clip names ending in `Extended` (e.g. `IdleExtended`, from when a second, 16-bone rig existed) are mapped to the plain name.
