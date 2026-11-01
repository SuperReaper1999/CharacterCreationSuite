# Character Creation Suite

A Blender character generator: it builds a rigged, animated low-poly humanoid from a JSON preset and saves it as a `.blend`. FBX and GLB exports are written alongside for use in other apps.

Double-click `Run Character Creation Suite.bat` (or run `python character_suite.py`; Blender 5.0 must be on PATH or in its default install folder), load a preset from `presets/`, customise it, then select **Generate character**.

The Character tab includes a fast live silhouette preview for proportions and
palette changes. The Materials tab has native colour pickers and swatches; the
generated `.blend` is the authoritative final result (the GLB carries the same geometry).

Each clip in the Animations tab has a **View anim in Blender** button. It opens an interactive Blender window on the character as currently configured in the tabs (proportions, materials, height) with that one clip baked and looping, so you can orbit and inspect it before committing to a build — it's the exact same rig code path as the real export (`rig_builder.py`), not a separate stand-in. Close the window when you're done; it only writes a scratch `build/_preview/character_config.json`, never anything under the character's own `build/<character-id>/` output folder.

The preview window is also an editor. Enter Pose Mode, adjust the bones, insert keyframes as usual (`I` with all bones selected keys the whole pose, matching how every clip here is authored), then use the **Character Suite** panel in the 3D viewport's side tab (`N`) to name it and hit **Save as Preset Animation**. That samples every frame that has a keyframe on any bone and writes a rotation-only JSON to `presets/animations/<name>.json` — reusing that same name overrides a built-in clip of the same name (you'll get a warning, not a block); a new name adds a new one. Saving is rejected if the action has any location/scale keys, so the rotation-only contract below can't be broken from the editor either. Back in the suite, click **Refresh clip list** (or reload a config) to pick up anything saved or changed since the window opened.

The suite writes all generated output to `build/<character-id>/`:

- `<character-id>.blend` — **the primary output.** The rigged character as built (on `extended`, the Bevel modifier is left live, not applied), its materials with textures packed into the file, and every selected clip as a named Action. Each Action has a fake user so all of them are kept; switch between them in the Action Editor. The first selected clip is assigned on open, with the scene frame range set to it. Blender-native axes (Z-up), 30 fps.
- `<character-id>.fbx` — FBX export with every selected clip baked in as a take, for game engines and other apps (axes converted to `-Z` forward, `Y` up).
- `<character-id>_Model.fbx` — the same mesh and rig with no animation, for pipelines that import the model and clips as separate assets.
- `Animations/<clip-name>.fbx` — one skeleton-only FBX per selected clip, no mesh. Each shares the exact bone names and hierarchy of `<character-id>_Model.fbx`, so retargeting (e.g. Unity's "copy from other Avatar") maps cleanly onto the model. Each file's single take is named after the clip (e.g. `Run`) and starts at frame 0, the same timing as the matching take in `<character-id>.fbx`. (Earlier builds named every per-clip take `Scene` and started it at frame 1.)
- `<character-id>_Preview.glb` — bind-pose preview with no animation. It is exported with modifiers applied, so on `extended` builds it includes the same bevelled geometry as the FBX. (Earlier builds exported the un-bevelled mesh here.)
- `Textures/<character-id>_<material>.png` — one small solid-colour texture per material (`skin`/`top`/`bottom`/`shoes`), wired into that material's Base Color. `<character-id>.fbx` and `<character-id>_Model.fbx` embed these directly (`embed_textures=True`) as well as referencing the standalone files, so the FBX alone shows the right colours even without the `Textures/` folder next to it. The `.blend` packs them too.
- `character_config.json` — reproducible build configuration.
- `manifest.json` — generated asset contract and validation metadata, including `blend`, `model_fbx`, `animation_fbx`, and `textures` paths.

The model and per-clip animation FBX files are on by default (`export_separate_animations` in the config); set it to `false` to skip them and only produce the combined `<character-id>.fbx`.

The player preset includes two distinct two-handed tool clips: `MeleeAttack` for the sledgehammer and `HarvestSwing` for pickaxes, axes, and shovels. Both preserve a credible support-hand pose; gameplay should apply the harvest at `HarvestSwing` frame 16 (0.5 seconds at 30fps).

`Crouch`, `CrouchWalkRifle`, `Prone`, and `Crawl` are available as selectable clips in the Animations tab (off by default, same as `ZombieAttack` — check the box to include them in a build). `CrouchWalkRifle` is a looping crouched stride with both arms locked into a two-handed rifle-ready pose (the arms don't swing with the gait, since a held weapon shouldn't). `Crouch`'s knee bend was fixed after an initial release had the sign backwards, which folded the knee the wrong way and left the feet dangling at a broken-looking angle instead of flat on the ground — the fix (and every stride clip added alongside it) was validated by rendering the pose in headless Blender before shipping it, not just by eyeballing the numbers.

`Prone` tips the whole rig forward ~80° around the hip bone's rest height so the character lies face-down (chest toward the ground, head lifted to look ahead, elbows slightly bent), rather than lying flat on the ground: because clips are rotation-only (see below), the pose cannot carry the downward offset needed to put the body at ground level. For a 1.75 m-tall character the hip pivot sits at `target_height_m * (0.90 / 2.69)` ≈ 0.59 m, so the posed mesh spans roughly 0.21–1.04 m above the ground on `standard` (0.12–1.01 m on `extended`, whose toes reach lower) until whatever plays the clip lowers the character by that offset while it's prone — in Blender, move the armature object down; in a game engine, the root transform (and collider). Clips never position the root; that's always left to the scene or engine. These ranges are measured by `tests/smoke_test.py` (it prints them as `INFO` lines). An earlier release had the pitch sign backwards, which laid the character face-up with hyperextended elbows; the test now asserts the facing direction and elbow bend. `Crawl` is a stride cycle on top of that same face-down pose; its arm/leg swing is authored on different rotation axes than every other clip in this file (Y/Z instead of X) because composing an X-axis stride swing onto Hips' already-80-degree X pitch doesn't add cleanly — it flings the limb, confirmed by rendering it before ruling it out.

### Rig types

The Character tab has a **Rig type** selector: `standard` (the original 16 bones) or `extended` (52 bones — adds `Spine`, `UpperChest`, `Shoulder.L`/`Shoulder.R`, `Toe.L`/`Toe.R`, and full Unity Humanoid-convention fingers: `Thumb`/`Index`/`Middle`/`Ring`/`Little`, each split into 3 segments — `<Finger>1/2/3.<L|R>` for Proximal/Intermediate/Distal, 30 bones across both hands). Both are plain Unity-compatible hierarchies; Unity's Humanoid Avatar doesn't require any particular bone count, only a sane parent chain, so `extended` isn't a special case on the Unity side. Every standard bone keeps the same name and rest position on `extended` — `MeleeAttack` and every other standard-rig clip bakes correctly on an `extended` character too, it just leaves the new bones at rest (`rig_builder.build_character` picks the hierarchy; `bake_pose_action` skips any bone a clip references that the current armature doesn't have, so a clip never crashes a build over a rig mismatch — it just quietly doesn't animate what isn't there).

Fingers get a fixed relaxed-hand curl in every frame of every `Extended` clip (heavier at the middle knuckle than the tip, like an actual relaxed hand) rather than something that varies with the pose — there's no reliable signal in a pose dict for "gripping" vs "open hand" to react to, so it's a static baseline layered on top of whatever the rest of the pose is doing.

`extended` also looks meaningfully less blocky than `standard`: the neck, arms, legs, toes, and every finger segment are built as cylinders instead of cubes; the head is a sphere, not a cube; and the whole mesh gets a bevel modifier (`offset_type="PERCENT"`, 25%, angle-limited) plus smooth shading. PERCENT scales the bevel to each edge's own length, so the same modifier rounds both the torso boxes and the tiny finger segments proportionally — a fixed absolute width sized for the torso would swallow a whole finger segment, and one sized for fingers would barely dent the torso. The bevel modifier is added to the mesh *before* the Armature modifier, so it rounds the rest-pose geometry once and the armature deforms that already-rounded result per frame — adding it after would mean re-bevelling posed geometry on every frame, including at extreme bends where it could self-intersect (checked directly: rendered a full-extension attack pose and the bevel held up clean). `standard` is untouched — this is `extended`-only, gated the same way finger curl and the extra bones are.

The head also gets a simple face: two eyes (white sphere + smaller dark pupil sphere), a nose (a small forward-pointing cone — the only rotated primitive in the rig; every other shape is built axis-aligned and this one gets rotated -90° about X after creation so its point aims along +Y instead of +Z), and a mouth (a thin dark box). All of it is geometry, not a texture — there's no UV-mapped decal here. Eyes/pupils/mouth use two fixed materials (`eye_white`, `eye_dark`) that exist only on `extended` builds and aren't part of `config["materials"]` — an eye colour isn't a clothing choice the way skin/top/bottom/shoes are, so it doesn't go through the same configurable palette, and isn't included in the per-material texture export either. All five face parts are bound directly to the `Head` bone; there was no need for separate bones since none of them move independently of the head.

Every built-in clip has an `Extended`-suffixed sibling (`IdleExtended`, `RunExtended`, …) generated from the original by `animation_library._extend_pose`, not hand-authored separately — hand-authoring 12 parallel clips would drift from the originals the first time one got tuned. The transform: a clip's `Chest` rotation is split 0.35/0.35/0.30 across `Spine`/`Chest`/`UpperChest` (the fractions sum to 1, so the total bend at the top of the spine matches the original exactly, just arrives as a curve instead of one hinge); `Shoulder.L`/`R` gets 15% of whichever axis `UpperArm.L`/`R` uses, and `Toe.L`/`R` gets 40% of `Foot`'s rotation (or 15% of `LowerLeg`'s, for clips that don't key `Foot`) as a following motion. Original bones are never altered by this. Validated by rendering `CrouchExtended`, `MeleeAttackExtended`, `ProneExtended`, and `CrawlExtended` in headless Blender — the last two mattered most, since that's where a naive addition would have hit the same X-axis-under-heavy-pitch problem `Crawl` itself did; the transform stayed on the already-safe axes and rendered clean.

## Testing

`tests/smoke_test.py` is a headless end-to-end check. It builds every preset in `presets/` plus an "every clip" character on both rig types, each through the real `blender_build.py` in a fresh Blender process (the same path as **Generate character**), then inspects the outputs from inside Blender:

- every file listed in `manifest.json` exists;
- the `.blend` opens with the armature, mesh, one fake-user Action per clip (rotation-only), the first clip assigned, and packed textures;
- bone counts are right (16 `standard`, 52 `extended`) in the combined and model FBX;
- no take has moving location keys (the rotation-only contract);
- the combined FBX has one take per clip, and each per-clip FBX has one take named after its clip with the same frame range;
- the GLB is skinned and carries the modifier-applied geometry;
- `Prone`/`Crawl` (and their `Extended` versions) face the ground with naturally bent elbows, and `Idle` faces forward.

```
python tests/smoke_test.py                                  # finds blender on PATH or the default install paths
python tests/smoke_test.py --blender "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
python tests/smoke_test.py --bpy-python <python with "pip install bpy">
```

It writes only to a temporary folder (pass `--keep` to keep it) and exits non-zero if any check fails. It needs no tkinter. It does not test the GUI, the interactive Blender preview/editor, or how other apps (e.g. game engines) import the FBX.

## Design boundaries

- Two selectable rig hierarchies (`rig_type`): fixed 16-bone `standard`, or 52-bone `extended` (adds a subdivided spine, shoulders, toes, and full 3-segment-per-finger hands). Proportions, materials, height, and clip selection are configurable on either.
- Every generated clip has rotation-only bone keys. Root translation/root motion is never authored — this is why `Prone` needs the character lowered by the scene or engine rather than having it baked into the clip (see above).
- Animation events/markers for game engines are intentionally not generated.
- The `.blend` is Blender-native. Only the FBX export converts axes, using Unity-style settings: `-Z` forward, `Y` up, all Actions as takes, and no leaf bones.
- Each of the 4 materials (`skin`/`top`/`bottom`/`shoes`) is backed by a small solid-colour PNG texture (see "Textures" below), not just a flat material value, and every body part is skinned to one of those 4 — there's no per-body-part texture, since most parts sharing a material would just be pixel-identical duplicates of it.
- The original `create_character_and_animations.py` and `create_zombie_and_animations.py` are retained unchanged as legacy references.
