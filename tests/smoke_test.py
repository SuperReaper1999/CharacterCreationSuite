"""Headless smoke test for the Character Creation Suite.

Builds every preset in presets/ plus an "every clip" build, using the
real export worker (blender_build.py) in a fresh Blender
process per build, exactly as the GUI's "Generate character" does. Then it
inspects the outputs from inside Blender (tests/_blender_checks.py):

- every file listed in manifest.json exists;
- the .blend (primary output): one armature with 53 bones including all 30
  finger bones; body, eyes, eyebrows, eyelashes, hair, outfit and shoes,
  all parented to and deformed by it; one fake-user Action per clip
  (bones only rotate, plus a Root ground offset), the first clip assigned; packed textures; body height
  equal to target_height_m (within 1%);
- colour slots with alpha 1 show up in the baked export textures;
- 53 bones in the combined, model and per-clip FBX; the combined FBX
  embeds the textures; no moving location curves in any take;
- one take per selected clip in the combined FBX, and per-clip FBX takes
  named after the clip with the same frame range as the combined take;
- the GLB preview is skinned, textured and carries the modifier-applied
  geometry;
- Prone/Crawl lie face-down with natural elbow bend; Idle faces forward;
- ground contact: the lowest point stays on the floor every frame;
- retarget accuracy: every arm, hand and finger bone follows the authored
  clips on every keyed frame.

Needs MPFB and the MakeHuman system assets installed in the Blender used
(run setup_mpfb.py once).

All output goes to a temporary folder; nothing is written under build/.

Usage (either a Blender executable, or a Python with `pip install bpy`):
    python tests/smoke_test.py                       # finds blender on PATH / default install paths
    python tests/smoke_test.py --blender "C:\\Program Files\\Blender Foundation\\Blender 5.0\\blender.exe"
    python tests/smoke_test.py --bpy-python path/to/python-with-bpy

Exit code 0 means every check passed.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from character_config import load_config, save_config, supported_clips  # noqa: E402

CHECKS_SCRIPT = ROOT / "tests" / "_blender_checks.py"
BUILD_SCRIPT = ROOT / "blender_build.py"

# Same search order as character_suite.find_blender(); duplicated here so
# the test doesn't import the tkinter GUI module.
DEFAULT_BLENDER_PATHS = (
    Path(r"D:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"),
    Path(r"C:\Program Files\Blender Foundation\Blender\blender.exe"),
)


def find_blender() -> str | None:
    return shutil.which("blender") or next((str(path) for path in DEFAULT_BLENDER_PATHS if path.exists()), None)


def make_runner(args: argparse.Namespace):
    if args.bpy_python:
        return lambda script, script_args: [args.bpy_python, str(script), "--", *script_args]
    blender = args.blender or find_blender()
    if not blender:
        raise SystemExit("Blender not found. Pass --blender PATH, or --bpy-python PATH for a Python with the bpy module.")
    # No --factory-startup: MPFB is an extension installed in the user's prefs.
    return lambda script, script_args: [blender, "--background", "--python", str(script), "--", *script_args]


def run(command: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--blender", help="Path to a Blender executable.")
    parser.add_argument("--bpy-python", help="Path to a Python interpreter with the bpy module installed.")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary output folder and print its path.")
    args = parser.parse_args()
    runner = make_runner(args)

    temp_dir = Path(tempfile.mkdtemp(prefix="ccs_smoke_"))
    failures: list[str] = []
    try:
        configs: list[Path] = []
        for preset in sorted((ROOT / "presets").glob("*.json")):
            config = load_config(preset)
            config["output_root"] = str(temp_dir)
            path = temp_dir / "configs" / preset.name
            save_config(path, config)
            configs.append(path)
        config = load_config(ROOT / "presets" / "player.json")
        config.update(character_id="AllClips", clips=list(supported_clips()), output_root=str(temp_dir))
        path = temp_dir / "configs" / "all_clips.json"
        save_config(path, config)
        configs.append(path)

        for config_path in configs:
            config = load_config(config_path)
            label = f"build {config_path.stem} ({len(config['clips'])} clips)"
            result = run(runner(BUILD_SCRIPT, [str(config_path)]))
            if result.returncode != 0 or "CHARACTER_SUITE_SUCCESS" not in result.stdout:
                failures.append(label)
                print(f"FAIL {label}\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}")
                continue
            print(f"PASS {label}")
            result = run(runner(CHECKS_SCRIPT, ["outputs", str(config_path), str(temp_dir / config["character_id"])]))
            failures += report(result, f"outputs {config['character_id']}")

        result = run(runner(CHECKS_SCRIPT, ["poses", str(ROOT / "presets" / "player.json")]))
        failures += report(result, "pose orientation")
    finally:
        if args.keep:
            print(f"Outputs kept in {temp_dir}")
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)

    print("\n" + ("ALL CHECKS PASSED" if not failures else f"{len(failures)} FAILED:\n  " + "\n  ".join(failures)))
    return 0 if not failures else 1


def report(result: subprocess.CompletedProcess, label: str) -> list[str]:
    """Echo the check script's PASS/FAIL/INFO lines; return failure labels."""
    lines = [line for line in result.stdout.splitlines() if line.startswith(("PASS ", "FAIL ", "INFO "))]
    for line in lines:
        print(f"  {line}")
    failed = [f"{label}: {line[5:]}" for line in lines if line.startswith("FAIL ")]
    if result.returncode != 0 or not lines:
        failed.append(f"{label}: check script exited {result.returncode}")
        print(f"  FAIL check script exited {result.returncode}\n{result.stdout[-3000:]}\n{result.stderr[-3000:]}")
    return failed


if __name__ == "__main__":
    sys.exit(main())
