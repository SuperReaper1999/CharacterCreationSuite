# Character Creation Suite

A Blender character generator. It builds a realistic, rigged, animated human from a JSON preset and saves it as a `.blend`. FBX and GLB exports are written alongside for other apps.

The character itself comes from [MPFB](https://extensions.blender.org/add-ons/mpfb/) (MakeHuman Plugin For Blender) and the MakeHuman system assets:

- a real body shaped by MakeHuman targets (gender, age, muscle, weight, height, proportions);
- a real skin texture, eyes, eyebrows, eyelashes and hair;
- a textured outfit and shoes, fitted to the body;
- MPFB's `game_engine` rig: 53 bones, including 3 bones per finger on both hands, with skin weights for the body and every clothing item.

The suite adds the config/preset workflow, colour slots, 51 built-in animations (converted onto the rig), the Blender preview/editor, and the exports.

## Setup

1. Install Blender 5.0 or newer.
2. Install MPFB and the MakeHuman system assets into that Blender, once:

   ```
   blender --background --python setup_mpfb.py
   ```

   This downloads two files, checks each one's SHA-256 against the versions the suite was tested with, installs the MPFB extension (v2.0.18) into Blender's `user_default` extension repository and enables it, and unpacks the asset pack (267 MB) into MPFB's user data folder. To use files you've already downloaded, pass `-- --mpfb-zip <path> --assets-zip <path>`. Running it again skips whatever is already installed (`--force` reinstalls).

   - MPFB: <https://extensions.blender.org/add-ons/mpfb/> — GPL-3.0-or-later, by Joel Palmius and the MakeHuman team. It is installed into your Blender, not included in this repository.
   - MakeHuman system assets: <https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html> — CC0 (skins, eyes, eyebrows, eyelashes, hair, clothes, shoes).

3. Start the app:
   - **Windows:** double-click `Run Character Creation Suite.bat`.
   - **Linux / macOS:** run `./run_character_suite.sh`. It checks that Python has tkinter (and prints the install command for your distro if not) and reports which Blender it found.
   - Or run `python character_suite.py` directly.

   Then load `presets/player.json` or `presets/zombie.json`, customise it, then select **Generate character**.

### Finding Blender

The app and the test runner look for Blender in this order (`blender_locator.py`):

1. the `CCS_BLENDER` environment variable, if set (path to the Blender executable);
2. `blender` on your PATH (official tarball added to PATH, a distro package, Snap);
3. standard install folders, newest version first: Windows `Program Files\Blender Foundation\Blender*`; Linux `/opt/blender*`, `~/blender*`, `~/Applications/blender*`, `~/.local/opt/blender*`, `~/.local/share/blender*`, `/snap/bin/blender`; macOS `/Applications/Blender*.app`;
4. Flatpak (`org.blender.Blender`), on Linux.

The Build tab shows which Blender and which MPFB asset folder were found when the app starts. You can also check from a terminal with `python3 blender_locator.py`.

**Linux notes.**
- tkinter is a separate package on many distros: `sudo apt install python3-tk` (Debian/Ubuntu/Mint), `sudo dnf install python3-tkinter` (Fedora), `sudo pacman -S tk` (Arch), `sudo zypper install python3-tk` (openSUSE).
- With the Flatpak, run the one-time setup as `flatpak run org.blender.Blender --background --python setup_mpfb.py`. If Blender can't read or write the suite's folder from inside its sandbox, grant access with `flatpak override --user --filesystem=/path/to/CharacterCreationSuite org.blender.Blender`. The app reads MPFB's asset list from the Flatpak's own config folder (`~/.var/app/org.blender.Blender/config/blender`).
- The app's UI font is the first one installed out of Segoe UI, Noto Sans, DejaVu Sans, Cantarell, Ubuntu, Liberation Sans, Helvetica and Arial; if none are, it uses Tk's default.

## The app

- **Character tab:** ID, display name, target height, and the MPFB assets to use: **Skin**, **Hair**, **Outfit**, **Shoes**. The lists are read from MPFB's asset folder in your Blender config; the fields are editable if it isn't found. The preview on the right is a real render of the character in its Idle pose. **Render preview** builds and renders just that (about 15–30 seconds, no exports), and every **Generate character** refreshes it too. When you change anything that affects the look (height, body, assets, proportions, colours), the preview is marked *out of date* until you render again. Images are saved as `build/<character-id>/<character-id>_Thumbnail.png`.
- **Proportions tab:** shoulder width, torso length, arm length, leg length, head size, body width (ratios, 1.0 = neutral), plus the MakeHuman body sliders gender (0 female – 1 male), age (0.5 = 25 years), muscle and weight.
- **Materials tab:** the colour slots (see below).
- **Animations tab:** pick clips to include. Each clip has a **View anim in Blender** button that opens an interactive Blender window on the character as currently configured, with that clip looping. It builds the character with the exact same code as the export, and only writes a scratch `build/_preview/character_config.json`.

The preview window is also an editor. Enter Pose Mode, adjust the bones, insert keyframes as usual (`I` with all bones selected keys the whole pose), then use the **Character Suite** panel in the 3D viewport's side tab (`N`) to name it and hit **Save as Preset Animation**. That samples every frame that has a keyframe and writes `presets/animations/<name>.json`, storing each bone's local rotation on the character's own rig as a quaternion. Reusing a built-in clip's name overrides it (you'll get a warning). Saving is rejected if the action has any location/scale keys, apart from the automatic `Root` ground offset, which is left out of the saved clip. Back in the suite, click **Refresh clip list** to pick it up.

## Config

A preset is a JSON file:

| Key | Meaning |
|---|---|
| `character_id`, `display_name` | Names; `character_id` is used for files and objects. |
| `target_height_m` | Barefoot body height in metres. MakeHuman's height slider is solved to reach it; anything beyond that slider's range is reached by uniform scaling. |
| `body` | `gender`, `age`, `muscle`, `weight`, each 0–1 (MakeHuman macros). |
| `skin`, `hair`, `outfit`, `shoes` | MPFB asset folder names (`data/skins/…`, `data/hair/…`, `data/clothes/…`). Empty hair/outfit/shoes = none. |
| `proportions` | Six ratios (0.55–1.8), mapped to MakeHuman measurement targets. |
| `materials` | Colour slots `skin`, `top`, `bottom`, `shoes`, as linear RGBA. |
| `clips` | Clip names to include. |
| `export_preview_glb`, `export_separate_animations` | Turn the GLB and the separate model/per-clip FBX files on or off. |

**Colour slots.** Alpha is the strength: 0 keeps the asset's own texture colours, 1 applies the colour fully. `skin` multiplies the skin texture by the colour (the zombie preset uses this to tint its skin green). `top`, `bottom` and `shoes` recolour the fabric while keeping its shading: the texture's brightness pattern is kept and rescaled so its average matches the colour. Top and bottom are told apart per UV island by height: islands whose average height is above the hips count as top. That works for every shirt/trousers, jacket/trousers and top/skirt outfit in the system pack. Bib-style garments such as `male_worksuit01` (overalls) have straps above the hips, which get the top colour.

Older configs still load: `rig_type` and `archetype` are dropped, and clip names ending in `Extended` map to the plain name. Their colour slots had alpha 1, so they recolour fully.

## Output

Everything goes to `build/<character-id>/`:

- `<character-id>.blend` — **the primary output.** The character as built: armature, body, eyes, eyebrows, eyelashes, hair, outfit and shoes, with MPFB's modifiers and the editable colour-slot shader nodes left live. Every selected clip is a named Action with a fake user, so all of them are kept; switch between them in the Action Editor. The first clip is assigned on open, with the scene frame range set to it. Textures are packed into the file, so expect it to be around 20–25 MB. Blender-native axes (Z-up, character facing −Y), 30 fps.
- `<character-id>.fbx` — FBX with every selected clip baked in as a take, textures embedded (axes converted to `-Z` forward, `Y` up).
- `<character-id>_Model.fbx` — the same meshes and rig with no animation.
- `Animations/<clip-name>.fbx` — one skeleton-only FBX per clip, no mesh, same bones and hierarchy as the model. Each file's single take is named after the clip and starts at frame 0, the same timing as the matching take in `<character-id>.fbx`.
- `<character-id>_Preview.glb` — bind-pose preview with no animation, textured, exported with modifiers applied.
- `Textures/` — the original asset textures (diffuse, normal, AO, …) that the `.blend` materials use, plus `<material>_basecolor.png`: each material's final colour (tints and recolours included), baked with Cycles. The FBX and GLB use the baked ones, because FBX can't carry shader node setups. Body skin hidden under clothing is masked out of the exported mesh, so those areas of the skin bake are left black.
- `character_config.json` — reproducible build configuration.
- `<character-id>_Thumbnail.png` (+ `.json`) — the app's preview render (first clip, first frame), and the config it was rendered from.
- `manifest.json` — asset contract: paths of everything above, bone names, clips, whether ground contact was on.

The model and per-clip animation FBX files are on by default (`export_separate_animations`); set it to `false` to only produce the combined FBX. A build takes about 30 seconds plus a few seconds per clip on a typical CPU, most of it baking the export textures.

## Animations

51 built-in clips. Bones only rotate, and the character is kept on the floor automatically (see Ground contact below). Gestures and one-handed actions use the right hand.

| Clip | Frames | Loops | Notes |
|---|---|---|---|
| **Locomotion** | | | |
| `Idle` | 60 | yes | Subtle breathing sway. |
| `Walk` | 33 | yes | Walk cycle: contact and passing poses, opposite arm swing. |
| `Run` | 31 | yes | Alternating leg/arm stride. |
| `Sprint` | 25 | yes | Deep, forward-leaning stride with pumping fists. |
| `StrafeLeft` / `StrafeRight` | 33 | yes | Side-stepping: one leg steps out, stance widens, the other follows. |
| `Jump` | 46 | no | Crouch, launch, land. |
| `Crouch` | 30 | yes | Held crouch, feet flat. |
| `CrouchWalkRifle` | 31 | yes | Crouched stride with both arms held forward in a two-handed rifle-ready pose. |
| `Prone` | 30 | yes | Lying face-down (see below). |
| `Crawl` | 31 | yes | Stride cycle on the face-down pose. |
| `Sit` | 30 | yes | Seated, knees at 90°. |
| `ZombieWalk` | 49 | yes | Shamble: arms raised forward, limp wrists, lolling head, dragging right leg. |
| **Combat and reactions** | | | |
| `MeleeAttack` | 30 | no | Two-handed overhead heavy strike. |
| `HarvestSwing` | 32 | no | Two-handed downward tool stroke; contact at frame 16 (0.5 s at 30 fps). |
| `Punch` | 32 | no | From a boxing guard: left jab (frame 6), back to guard, right cross (frame 18). |
| `Kick` | 32 | no | Right front kick from guard: chamber (8), extend (13), rechamber (18). |
| `Throw` | 36 | no | Overhand: arm cocked behind the head (10), release (16), follow-through (24). |
| `Fire` | 12 | no | Short right-arm recoil. |
| `PistolIdle` | 60 | yes | One-handed aim, arm extended, pistol grip with trigger finger. |
| `PistolFire` | 12 | no | Trigger squeeze (2) and recoil (3) from the PistolIdle aim. |
| `Reload` | 55 | no | Rifle held ready; left hand to the magazine, to the pouch, back, then the charging handle. |
| `HitReact` | 20 | no | Flinch: chest and head snap back, then recover. |
| `Death` | 45 | no | Knees buckle, falls backwards, ends lying on the back (see below). |
| `ZombieAttack` | 30 | no | Two-armed lunge. |
| **Gestures and interaction** | | | |
| `Wave` | 50 | no | Arm raised, open hand waving side to side. |
| `Point` | 40 | no | Arm extended, index finger pointing. |
| `ThumbsUp` | 50 | no | Fist with the thumb up, held, then lowered. |
| `MiddleFinger` | 50 | no | Forearm raised, back of the hand forward, middle finger up. |
| `Peace` | 50 | no | Hand raised, palm forward, index and middle fingers in a V. |
| `OKSign` | 50 | no | Hand raised, thumb and index tips touching in a ring (seen face-on), other fingers up. |
| `Handshake` | 50 | no | Vertical open hand at waist height, pumped three times. |
| `Talk` | 97 | yes | Conversational gestures with both hands, small nods and torso movement. |
| `PickUp` | 40 | no | Crouch and reach (14), grab (18), stand holding it (32). |
| `Interact` | 30 | no | Reach out with the index finger and press (12), e.g. a button. |
| **Seated and utility** | | | |
| `SitChair` | 60 | yes | Upright on a chair, hands resting on the thighs. |
| `SitBench` | 60 | yes | Leaning forward on a bench, forearms on the knees. |
| `SitTyping` | 25 | yes | Seated at a desk, hands on a keyboard, fingers tapping. |
| `Drive` | 60 | yes | Car seat (reclined, legs forward), hands at 10 and 2 on the wheel. |
| `DriveSteerLeft` / `DriveSteerRight` | 30 | yes | Same, wheel held turned 45° left / right. |
| `LieDown` | 60 | yes | Lying on the back (bed or ground). |
| `PhoneCall` | 90 | yes | Phone held at the right ear. |
| `PhoneLook` | 40 | yes | Phone held in front of the chest with both hands, looking down, thumb tapping. |
| `Drink` | 50 | no | Cup raised to just in front of the mouth (14), sip (28), lowered. |
| `CarryIdle` | 60 | yes | Holding a box (about 40 cm wide) in front with both hands. |
| `CarryWalk` | 33 | yes | `Walk` legs with the `CarryIdle` arms. |
| `OpenDoor` | 40 | no | Reach for a handle at waist height (10), grip (14), pull back (26), release (32). |
| `PullLever` | 40 | no | Grab a lever above the head with both hands (10), pull it down to chest height with a slight crouch (22). |
| `Kneel` | 60 | yes | Down on the right knee, left forearm resting on the left knee. |
| `ClimbLadder` | 31 | yes | In-place climb cycle: hands alternate on rungs, legs step. |

The player preset selects `Idle`, `Run`, `Jump`, `MeleeAttack`, `HarvestSwing`, `Fire` and `Sit`; tick any others in the Animations tab.

**How clips are authored.** Each clip is keyed as local Euler rotations on the suite's own *authoring skeleton* (`authoring_skeleton.py`: 52 bones, facing +Y, arms hanging straight down), on the main body bones only (`animation_library._authored_clips`). `animation_library._expand_pose` fills in the rest of that skeleton from those values: the `Chest` rotation is split 0.35/0.35/0.30 across `Spine`/`Chest`/`UpperChest`; `Shoulder` gets 15% of `UpperArm`'s rotation; `Toe` gets 40% of `Foot`'s (or 15% of `LowerLeg`'s); and any finger a frame doesn't key gets a fixed relaxed curl into the palm.

**Hand shapes.** Clips that key the fingers use named shapes from `animation_library._hand`: `open`, `fist`, `point`, `thumbs_up`, `middle_finger`, `peace`, `ok`, `grip` (pistol grip with trigger finger) and `handshake`. A shape can also fan fingers apart at the knuckle (`spread`). Finger values are anatomical: curl into the palm, and spread toward the thumb. The thumb has a swing toward the palm and a swing across toward the little finger at its base, plus a bend at the two joints. The thumb values for `fist`, `point`, `middle_finger`, `grip` and `ok` were found by numeric searches on the character: of the candidates whose thumb-tip skin rests on the curled fingers (or on the index tip, for `ok`), the one with the least overlap. They were then checked by rendering. The fist curl is capped at 70/90/50°: at 80/95/60 a fingertip pushes through the palm and its nail shows on the back of the hand. When a pose needs a bone turned about its own length after bending (the raised hand turned so its back faces forward in `MiddleFinger`, the vertical handshake hand, the cocked arm in `Throw`, the boxing guard), it uses `animation_library._compose`. A plain Euler `r(x, y, z)` turns a bent forearm about the upper arm's axis instead, swinging it sideways.

**Spine sign convention.** The spine and head bones point up, so −X on `Chest`/`Head` bends forward and +X leans back, the opposite of the arm and leg bones (which point down, so +X swings them forward). An earlier version had this reversed on five clips: `Run` leaned back, `MeleeAttack`, `HarvestSwing` and `ZombieAttack` leaned back on the strike and forward on the wind-up, and `Fire` leaned forward on recoil. Those were fixed after measuring the posed skeleton.

**How they get onto the character** (`retarget.py`). The authoring skeleton is never exported. For every keyed frame, a temporary authoring armature is posed with the clip. Each authoring bone's rotation relative to its rest pose is taken in world space, turned 180° to the character's facing, and applied to the matching `game_engine` bone, then keyed as a local quaternion. Before that, the character's arm and hand bones are aligned from MPFB's A-pose to the authoring rest pose. The arm is aligned as a chain (the upper arm swings down and the rest follows), which keeps the natural twist so the palms face the thighs. While an arm hangs along the torso it is also tilted 10° outward (`ARM_ABDUCTION_DEG`), because MPFB's shoulders sit closer to the body than the authoring skeleton's and straight-down arms would pass through the hips. The tilt fades out as the arm leaves the hanging position, and it turns with the torso, so lying poses keep it. Left on for arms reaching forward, it only splayed the hands about 20 cm further apart. Spine, legs, feet, neck and head keep their own anatomical rest direction. Fingers and thumbs are not transferred this way: they keep MPFB's own natural hand shape (spread, arch, thumb position) and follow the hand. The clip's finger values are applied as curl/spread (thumb: swing/bend) about each MPFB knuckle's own hinge axes, worked out from the hand's geometry. An earlier version forced the fingers straight and parallel like the authoring skeleton's, which fused them together and pushed the thumb into the palm. The transfer works in world space, so differences in bone naming and roll between the two rigs don't matter, and it adapts to each character's proportions. No location keys are ever written.

Custom clips saved from the preview editor are stored in the character's own bone space and keyed directly. Custom clips saved by earlier versions (Euler degrees on authoring bone names) are retargeted like the built-ins.

**Ground contact.** Bones only rotate, so poses that pivot around the hips (`Prone`, `Crawl`, `Death`, `Crouch`, `Sit`, `PickUp`, `Kick`…) would hover above the floor. So after each clip is baked, the build steps through every frame, finds the lowest point of the character's meshes (shoes, body, clothes, hair), and keys a vertical offset on the rig's `Root` bone so that point sits exactly at Z = 0 (`retarget.ground_clip`). In-place loops like `Walk` and `Run` stay in place and pick up a natural bob; nothing moves the character forward, and `Jump` has no airtime. This is the only location channel any clip has. Set `ground_contact` to `false` in the config to switch it off, and the clips are then purely rotations again. The preview editor doesn't save the `Root` channel; it's recomputed for each character.

**Hands placed by IK.** For the seated and utility clips, the arm angles were found with an IK search on the MPFB character. The upper arm and elbow are chosen so the centre of the palm lands on a target point (wheel rim, ear, mouth, keyboard, box sides, door handle, lever, rungs, knee), with the elbow kept below the hand and the hand clear of the body. The resulting angles are written into the clips with a "solved" comment. Seat height comes from ground contact: with the feet on the floor, the hips end up at seat height. There are no props; the hands mime the chair, wheel, phone, cup and box.

**Arm poses checked on the character.** Every keyframe of every clip was measured on the MPFB character for hand/forearm skin inside the torso, head or legs, and for hand spacing. As a result:
- The two-handed clips (`MeleeAttack`, `HarvestSwing`, `CrouchWalkRifle`) now keep both hands on the handle: about 25 cm apart for the tool swings, 42 cm for the rifle (support hand on the handguard). They were 60–90 cm apart.
- The `MeleeAttack` and `HarvestSwing` wind-ups raise the tool overhead, instead of swinging both arms straight back behind the body at shoulder height.
- `StrafeLeft`/`StrafeRight` hold the arms slightly out, so the hand clears the swinging thigh.
- The raised-hand gestures (`MiddleFinger`, `Peace`, `OKSign`) hold the hand beside the face.

One thing to know when writing raised arms: once an arm is above the shoulder, the "outward" Z value moves the hand inward (a raised pair of arms crosses over the face), so swing the arm about the vertical instead.

**Prone, Crawl and Death.** `Prone` tips the whole body forward ~80° around the pelvis so the character lies face-down (chest toward the ground, head lifted to look ahead, elbows slightly bent); ground contact then brings it down onto its toes and hands. `Crawl`'s limb swing is authored on Y/Z rotations rather than X, because an X-axis stride swing on top of the 80° pitch lifts the limbs off the ground instead of sweeping them along it. `Death` ends lying flat on its back.

## Testing

`tests/smoke_test.py` is a headless end-to-end check, and needs MPFB installed in the Blender it uses. It builds both presets plus an "every clip" character, each through the real `blender_build.py` in a fresh Blender process (the same path as **Generate character**), then checks:

- the `.blend`: one armature with 53 bones including all 30 finger bones; body, eyes, eyebrows, eyelashes, hair, outfit and shoes, all rigged; one fake-user Action per clip, the first one assigned, bones only rotating (plus the `Root` ground offset); packed textures; body height within 1% of `target_height_m`;
- that every colour slot with alpha 1 shows up in the baked texture over its region;
- the FBX files: 53 bones, all meshes, embedded textures, takes named after clips with matching frame ranges, no location channels other than the `Root` ground offset;
- the GLB: skinned with 53 joints, textured, with the modifier-applied geometry;
- `Prone`/`Crawl` face the ground with naturally bent elbows, and `Idle` faces forward;
- ground contact: on every frame of `Idle`, `Walk`, `Sprint`, `Prone`, `Crawl`, `Death`, `Crouch`, `Sit`, `PickUp` and `Kick`, the lowest point is within 5 mm of the floor, and the `Root` offset only moves vertically;
- retarget accuracy: on every keyed frame of every clip, every arm and hand bone points where the authored clip says, within the 10° outward tilt;
- hands: the `Wave` open hand keeps MPFB's natural hand (no finger or thumb bone rotated); on `Wave` and `Idle` the skin between neighbouring fingers stays at least 6 mm apart (not fused); every fingertip of the `Punch` fist curls back past its knuckle; the `OKSign` thumb and index fingertip skin touch (within 3 mm).
- arms: no hand/forearm skin inside the body on any keyed frame of any clip; `MeleeAttack`/`HarvestSwing` keep both hands within 30 cm and `CrouchWalkRifle` within 45 cm; the swing wind-ups don't cross the arms; the raised-hand gestures sit at least 20 cm out from the face's centre line.

```
python tests/smoke_test.py                                  # finds blender on PATH or the default install paths
python tests/smoke_test.py --blender "C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"
python tests/smoke_test.py --bpy-python <python with "pip install bpy" and MPFB set up>
```

It writes only to a temporary folder (`--keep` keeps it), exits non-zero if any check fails, and takes about 2 minutes. It does not test the GUI, the interactive preview/editor, or how other apps import the FBX.

## Design boundaries and known limitations

- One rig: MPFB `game_engine` (53 bones). Body shape, height, assets, colours and clip selection are configurable.
- Bones only rotate. The only location channel is the automatic vertical `Root` ground offset (`ground_contact`); there's no forward root motion.
- Animation events/markers for game engines are not generated.
- The top/bottom colour split is a height heuristic per UV island (see Colour slots).
- In the FBX/GLB, colours come from the baked textures: a snapshot taken at build time. In the `.blend` they are live shader nodes.
- Developed and tested headlessly with the Blender 5.1.2 Python module (`pip install bpy`) on Linux. Blender 5.0 itself, Windows, and the tkinter GUI weren't run during development.
