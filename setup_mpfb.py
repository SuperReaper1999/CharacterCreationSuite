"""One-time setup: install MPFB and the MakeHuman system assets into Blender.

The Character Creation Suite builds characters with MPFB (MakeHuman Plugin
For Blender). Run this once with the same Blender the suite uses:

    blender --background --python setup_mpfb.py

It downloads (or takes local copies of) two files, checks their SHA-256
against the versions the suite was tested with, then:

1. installs the MPFB extension (GPL-3.0-or-later, by Joel Palmius / the
   MakeHuman team) into Blender's "user_default" extension repository and
   enables it in your preferences;
2. unpacks the MakeHuman system asset pack (CC0: skins, eyes, eyebrows,
   eyelashes, hair, clothes, shoes) into MPFB's user data folder.

Options (after "--"):
    --mpfb-zip PATH     use a local add-on-mpfb-v2.0.18.zip instead of downloading
    --assets-zip PATH   use a local makehuman_system_assets_cc0.zip instead of downloading
    --force             reinstall even if MPFB and the assets are already present
    --skip-hash         accept files whose SHA-256 doesn't match (e.g. a newer release)

Sources: https://extensions.blender.org/add-ons/mpfb/ and
https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import bpy

MPFB_URL = "https://extensions.blender.org/download/sha256:c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad/add-on-mpfb-v2.0.18.zip"
MPFB_SHA256 = "c075b3e9b94b8e5556a5f03f4653602d02ea306de08126e8f55ed6dee28a2dad"
ASSETS_URL = "https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"
ASSETS_SHA256 = "b542127a8e25547c7c29c19f2d1d2adb9a664c80396ecd694095dbc8028a0107"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="setup_mpfb.py")
    parser.add_argument("--mpfb-zip")
    parser.add_argument("--assets-zip")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-hash", action="store_true")
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(local: str | None, url: str, expected: str, skip_hash: bool, workdir: Path) -> Path:
    if local:
        path = Path(local).expanduser().resolve()
    else:
        path = workdir / url.rsplit("/", 1)[-1]
        print(f"Downloading {url} ...")
        urllib.request.urlretrieve(url, path)
    actual = sha256(path)
    if actual != expected:
        message = f"SHA-256 mismatch for {path.name}: expected {expected}, got {actual}"
        if not skip_hash:
            raise SystemExit(message + " (pass --skip-hash to accept it anyway)")
        print("WARNING: " + message)
    return path


def installed_mpfb() -> str | None:
    import addon_utils
    return next((module.__name__ for module in addon_utils.modules() if module.__name__.split(".")[-1] == "mpfb"), None)


def main() -> None:
    args = arguments()
    with tempfile.TemporaryDirectory(prefix="ccs_mpfb_") as temp:
        workdir = Path(temp)
        package = installed_mpfb()
        if package and not args.force:
            print(f"MPFB already installed ({package}); skipping the extension (use --force to reinstall).")
        else:
            mpfb_zip = fetch(args.mpfb_zip, MPFB_URL, MPFB_SHA256, args.skip_hash, workdir)
            result = bpy.ops.extensions.package_install_files(filepath=str(mpfb_zip), repo="user_default", enable_on_install=True)
            if "FINISHED" not in result:
                raise SystemExit(f"Installing MPFB failed: {result}")
            package = installed_mpfb()
        import addon_utils
        addon_utils.enable(package, default_set=True)
        bpy.ops.wm.save_userpref()

        data_dir = Path(bpy.utils.extension_path_user(package, create=True)) / "data"
        if (data_dir / "skins").is_dir() and any((data_dir / "skins").iterdir()) and not args.force:
            print(f"MakeHuman system assets already present in {data_dir}; skipping (use --force to reinstall).")
        else:
            assets_zip = fetch(args.assets_zip, ASSETS_URL, ASSETS_SHA256, args.skip_hash, workdir)
            data_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(assets_zip) as archive:
                for member in archive.namelist():
                    target = (data_dir / member).resolve()
                    if data_dir.resolve() not in target.parents and target != data_dir.resolve():
                        raise SystemExit(f"Refusing to extract {member!r} outside {data_dir}")
                archive.extractall(data_dir)
            print(f"Installed MakeHuman system assets into {data_dir}")
    print("MPFB_SETUP_OK")


if __name__ == "__main__":
    main()
