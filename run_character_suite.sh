#!/usr/bin/env bash
# Linux / macOS launcher for the Character Creation Suite
# (Windows: "Run Character Creation Suite.bat").
# Checks the two things the app needs from your system, then starts it.
cd "$(dirname "$0")" || exit 1
PY="${PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "Python 3 wasn't found. Install python3 (3.9 or newer)." >&2
    exit 1
fi

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
    echo "This Python has no tkinter (the app's GUI toolkit). Install it:" >&2
    echo "  Debian/Ubuntu/Mint:  sudo apt install python3-tk" >&2
    echo "  Fedora:              sudo dnf install python3-tkinter" >&2
    echo "  Arch/Manjaro:        sudo pacman -S tk" >&2
    echo "  openSUSE:            sudo zypper install python3-tk" >&2
    exit 1
fi

# Report what was found (the app shows the same in its Build tab).
"$PY" blender_locator.py
if ! "$PY" -c "import sys, blender_locator; sys.exit(0 if blender_locator.find_blender() else 1)"; then
    echo "Warning: Blender wasn't found, so Generate / Render preview won't work yet." >&2
    echo "  Put 'blender' on your PATH, or run:  CCS_BLENDER=/path/to/blender $0" >&2
fi

exec "$PY" character_suite.py "$@"
