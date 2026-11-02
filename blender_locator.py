"""Find Blender, and MPFB's asset folder, on Windows, Linux and macOS.

Used by the app (character_suite.py) and the test runner (tests/smoke_test.py),
so it doesn't import tkinter. Blender is returned as a command prefix (a
list), because a Flatpak install is started as "flatpak run
org.blender.Blender" rather than as a single executable.

Search order for Blender:
1. the CCS_BLENDER environment variable (a path to the executable);
2. "blender" on PATH (official tarball added to PATH, distro package, Snap);
3. standard install folders (Windows Program Files; Linux /opt, ~/blender*,
   ~/Applications, /snap/bin; macOS /Applications) — newest version first;
4. Flatpak (org.blender.Blender), on Linux.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

FLATPAK_ID = "org.blender.Blender"


def _version_key(path: Path) -> tuple:
    """Sort key so 'blender-5.10' ranks above 'blender-5.9'."""
    return tuple(int(part) for part in re.findall(r"\d+", str(path))) or (0,)


def _install_candidates() -> list[Path]:
    home = Path.home()
    if os.name == "nt":
        roots = [Path(os.environ.get(name, "")) / "Blender Foundation" for name in ("ProgramFiles", "ProgramFiles(x86)")]
        roots += [Path(r"D:\Program Files\Blender Foundation")]
        found = [path for root in roots if root.is_dir() for path in root.glob("Blender*/blender.exe")]
    elif sys.platform == "darwin":
        found = [Path(path) for pattern in ("/Applications/Blender*.app/Contents/MacOS/Blender", str(home / "Applications/Blender*.app/Contents/MacOS/Blender"))
                 for path in glob.glob(pattern)]
    else:
        found = []
        for base, pattern in ((Path("/opt"), "blender*/blender"), (home, "blender*/blender"), (home / "Applications", "blender*/blender"),
                              (home / ".local" / "opt", "blender*/blender"), (home / ".local" / "share", "blender*/blender")):
            if base.is_dir():
                found += [path for path in base.glob(pattern) if path.is_file() and os.access(path, os.X_OK)]
        found += [path for path in (Path("/snap/bin/blender"),) if path.exists()]
    return sorted(found, key=_version_key, reverse=True)


def flatpak_installed() -> bool:
    if not shutil.which("flatpak"):
        return False
    try:
        result = subprocess.run(["flatpak", "info", FLATPAK_ID], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def find_blender() -> list[str] | None:
    """Command prefix that starts Blender, e.g. ["/usr/bin/blender"] or
    ["flatpak", "run", "org.blender.Blender"]; None if Blender isn't found."""
    override = os.environ.get("CCS_BLENDER")
    if override:
        return [override]
    on_path = shutil.which("blender")
    if on_path:
        return [on_path]
    installed = _install_candidates()
    if installed:
        return [str(installed[0])]
    if sys.platform.startswith("linux") and flatpak_installed():
        return ["flatpak", "run", FLATPAK_ID]
    return None


def describe(command: list[str] | None) -> str:
    return " ".join(command) if command else "not found"


def blender_config_dirs() -> list[Path]:
    """Blender's per-user config roots (each holds one folder per version)."""
    home = Path.home()
    if os.name == "nt":
        return [Path(os.environ.get("APPDATA", "")) / "Blender Foundation" / "Blender"]
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Blender"]
    return [Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "blender",
            home / ".var" / "app" / FLATPAK_ID / "config" / "blender"]  # Flatpak


def mpfb_data_dirs() -> list[Path]:
    """MPFB user data folders (data/skins, data/clothes, ...), newest Blender
    version first."""
    found = [path for base in blender_config_dirs() if base.is_dir()
             for path in base.glob("*/extensions/.user/*/mpfb/data") if path.is_dir()]
    return sorted(found, key=lambda path: _version_key(path.parts[-6]), reverse=True)


if __name__ == "__main__":
    print("Blender:", describe(find_blender()))
    print("MPFB data:", ", ".join(map(str, mpfb_data_dirs())) or "not found")
