"""Desktop UI for building configurable rigged characters in Blender."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

from character_config import BUILTIN_CLIPS, default_config, load_config, safe_id, save_config, supported_clips, validate_config

ROOT = Path(__file__).resolve().parent


def find_blender() -> str | None:
    return shutil.which("blender") or next((str(path) for path in (
        Path(r"D:\Program Files\Blender Foundation\Blender 5.0\blender.exe"), Path(r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"), Path(r"C:\Program Files\Blender Foundation\Blender\blender.exe"),
    ) if path.exists()), None)


def mpfb_data_dirs() -> list[Path]:
    """MPFB user data folders (data/skins, data/clothes, ...) in this user's
    Blender config, newest Blender version first. Searched on disk because
    the GUI runs outside Blender."""
    bases = []
    if os.name == "nt":
        bases.append(Path(os.environ.get("APPDATA", "")) / "Blender Foundation" / "Blender")
    elif sys.platform == "darwin":
        bases.append(Path.home() / "Library" / "Application Support" / "Blender")
    else:
        bases.append(Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "blender")
    found = [path for base in bases if base.is_dir() for path in base.glob("*/extensions/.user/*/mpfb/data") if path.is_dir()]
    return sorted(found, key=lambda path: path.parts[-6], reverse=True)


def mpfb_asset_names(subdir: str, startswith: str = "") -> list[str]:
    """Installed MPFB asset folder names, e.g. ("skins") or ("clothes", "shoes")."""
    for data in mpfb_data_dirs():
        folder = data / subdir
        if folder.is_dir():
            return sorted(path.name for path in folder.iterdir() if path.is_dir() and path.name.startswith(startswith))
    return []


class CharacterSuite:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root; root.title("Character Creation Suite"); root.minsize(930, 720)
        self.vars: dict[str, tk.Variable] = {}; self.proportions: dict[str, tk.StringVar] = {}; self.colors: dict[str, list[tk.StringVar]] = {}; self.clip_vars: dict[str, tk.BooleanVar] = {}
        self.color_swatches: dict[str, tk.Label] = {}
        self.status = tk.StringVar(value="Ready. Load a preset or adjust the character.")
        self._build(); self._watch_preview(); self.load_state(default_config())

    def _field(self, parent: ttk.Frame, row: int, column: int, label: str, key: str, width: int = 12) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=column, sticky="w", padx=(0, 4), pady=3)
        value = tk.StringVar(); self.vars[key] = value
        ttk.Entry(parent, textvariable=value, width=width).grid(row=row, column=column + 1, sticky="w", padx=(0, 12), pady=3)

    def _build(self) -> None:
        self.root.columnconfigure(0, weight=1); self.root.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self.root, padding=8); toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Button(toolbar, text="New", command=lambda: self.load_state(default_config())).pack(side="left")
        ttk.Button(toolbar, text="Load preset", command=self.load_preset).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Open config", command=self.open_config).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Save config", command=self.save_config).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Generate character", command=self.generate).pack(side="right")
        tabs = ttk.Notebook(self.root); tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        identity = ttk.Frame(tabs, padding=12); proportions = ttk.Frame(tabs, padding=12); materials = ttk.Frame(tabs, padding=12); animations = ttk.Frame(tabs, padding=12); output = ttk.Frame(tabs, padding=12)
        tabs.add(identity, text="Character"); tabs.add(proportions, text="Proportions"); tabs.add(materials, text="Materials"); tabs.add(animations, text="Animations"); tabs.add(output, text="Build")
        identity.columnconfigure(2, weight=1)
        self._field(identity, 0, 0, "Character ID", "character_id", 24); self._field(identity, 1, 0, "Display name", "display_name", 24)
        self._field(identity, 2, 0, "Target height (metres)", "target_height_m", 10)
        clothes = mpfb_asset_names("clothes")
        for row, (key, label, values) in enumerate((
            ("skin", "Skin", mpfb_asset_names("skins")),
            ("hair", "Hair", ["", *mpfb_asset_names("hair")]),
            ("outfit", "Outfit", ["", *(name for name in clothes if "suit" in name)]),
            ("shoes", "Shoes", ["", *(name for name in clothes if name.startswith("shoes"))]),
        ), start=3):
            ttk.Label(identity, text=label).grid(row=row, column=0, sticky="w", pady=3)
            self.vars[key] = tk.StringVar()
            # Editable, so a name can still be typed if MPFB's folder wasn't found.
            ttk.Combobox(identity, textvariable=self.vars[key], values=values, width=28).grid(row=row, column=1, sticky="w")
        note = "Built with MPFB (MakeHuman): a realistic body with skin texture, eyes, hair and clothing, rigged with 53 bones including 3-segment fingers."
        if not mpfb_data_dirs():
            note += " MPFB's asset folder wasn't found for this user — run setup_mpfb.py (see README) or type asset names."
        ttk.Label(identity, text=note, wraplength=390).grid(row=8, column=0, columnspan=2, sticky="w", pady=(18, 0))
        preview = ttk.LabelFrame(identity, text="Live character preview", padding=6); preview.grid(row=0, column=2, rowspan=9, sticky="nsew", padx=(22, 0))
        self.preview_canvas = tk.Canvas(preview, width=350, height=510, background="#1a202b", highlightthickness=0); self.preview_canvas.pack(fill="both", expand=True)
        ttk.Label(preview, text="Fast visual guide — final geometry is generated by Blender.").pack(anchor="w", pady=(6, 0))
        for row, (key, label) in enumerate((("shoulder_width", "Shoulder width"), ("torso_length", "Torso length"), ("arm_length", "Arm length"), ("leg_length", "Leg length"), ("head_scale", "Head size"), ("body_width", "Body width"))):
            ttk.Label(proportions, text=label).grid(row=row, column=0, sticky="w", pady=4); value = tk.StringVar(); self.proportions[key] = value; ttk.Scale(proportions, from_=.55, to=1.8, orient="horizontal", variable=value).grid(row=row, column=1, sticky="ew", padx=(0, 8)); ttk.Entry(proportions, textvariable=value, width=8).grid(row=row, column=2, sticky="w")
        self.body: dict[str, tk.StringVar] = {}
        for row, (key, label) in enumerate((("gender", "Gender (0 female – 1 male)"), ("age", "Age (0.5 = 25 years)"), ("muscle", "Muscle"), ("weight", "Weight")), start=8):
            ttk.Label(proportions, text=label).grid(row=row, column=0, sticky="w", pady=4); value = tk.StringVar(); self.body[key] = value; ttk.Scale(proportions, from_=0.0, to=1.0, orient="horizontal", variable=value).grid(row=row, column=1, sticky="ew", padx=(0, 8)); ttk.Entry(proportions, textvariable=value, width=8).grid(row=row, column=2, sticky="w")
        proportions.columnconfigure(1, weight=1)
        ttk.Label(proportions, text="All dimensions are ratios. The .blend stays Blender-native (Z-up); only the FBX export converts axes (-Z forward, Y up) for other apps.", wraplength=650).grid(row=13, column=0, columnspan=3, sticky="w", pady=(18, 0))
        for row, label in enumerate(("skin", "top", "bottom", "shoes")):
            ttk.Label(materials, text=label.title()).grid(row=row, column=0, sticky="w", pady=5)
            values = [tk.StringVar() for _ in range(4)]; self.colors[label] = values
            for index, value in enumerate(values): ttk.Entry(materials, textvariable=value, width=7).grid(row=row, column=index + 1, padx=3)
            ttk.Button(materials, text="Pick colour", command=lambda name=label: self.pick_colour(name)).grid(row=row, column=5, padx=(9, 4))
            swatch = tk.Label(materials, width=5, relief=tk.SUNKEN); swatch.grid(row=row, column=6, padx=3); self.color_swatches[label] = swatch
        ttk.Label(materials, text="RGBA channels use 0–1 values (linear). Alpha is the strength: 0 keeps the asset's own texture colours, 1 applies the colour fully. Skin multiplies the skin texture; top, bottom and shoes recolour the fabric while keeping its shading. Picking a colour sets alpha to 1.", wraplength=650).grid(row=6, column=0, columnspan=5, sticky="w", pady=(18, 0))
        header = ttk.Frame(animations); header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="Select rotation-only clips to bake as Blender Actions (also exported as FBX takes). Root translation and Animation Events are deliberately unavailable.", wraplength=560).pack(side="left")
        ttk.Button(header, text="Refresh clip list", command=self.refresh_clips).pack(side="right")
        ttk.Label(animations, text="Edit a clip's pose in the Blender preview, then save it there as a preset — it shows up here after Refresh.", wraplength=680, foreground="#5a6b8c").pack(anchor="w", pady=(0, 10))
        self.clip_rows_frame = ttk.Frame(animations); self.clip_rows_frame.pack(fill="both", expand=True)
        self.log = tk.Text(output, height=27, wrap="word", state="disabled", background="#151922", foreground="#e6edf3"); self.log.pack(fill="both", expand=True)
        ttk.Label(self.root, textvariable=self.status, relief=tk.SUNKEN, anchor="w", padding=(8, 4)).grid(row=2, column=0, sticky="ew")

    def state(self) -> dict:
        raw = {key: value.get() for key, value in self.vars.items()}
        raw["proportions"] = {key: value.get() for key, value in self.proportions.items()}; raw["body"] = {key: value.get() for key, value in self.body.items()}; raw["materials"] = {key: [value.get() for value in values] for key, values in self.colors.items()}; raw["clips"] = [name for name, value in self.clip_vars.items() if value.get()]
        return validate_config(raw)

    def _watch_preview(self) -> None:
        for variable in [*self.vars.values(), *self.proportions.values(), *(value for values in self.colors.values() for value in values)]:
            variable.trace_add("write", lambda *_args: self.draw_preview())

    def _rgba(self, name: str) -> tuple[int, int, int]:
        try:
            return tuple(max(0, min(255, round(float(value.get()) * 255))) for value in self.colors[name][:3])
        except ValueError:
            return 128, 128, 128

    def _hex_colour(self, name: str) -> str:
        return "#%02x%02x%02x" % self._rgba(name)

    def pick_colour(self, name: str) -> None:
        rgb, _ = colorchooser.askcolor(color=self._hex_colour(name), title=f"Choose {name} colour", parent=self.root)
        if rgb is None:
            return
        for variable, channel in zip(self.colors[name][:3], rgb):
            variable.set(f"{channel / 255:.3f}")
        self.colors[name][3].set("1.0")

    def draw_preview(self) -> None:
        if not hasattr(self, "preview_canvas"):
            return
        canvas = self.preview_canvas; canvas.delete("all")
        width, height = max(20, canvas.winfo_width()), max(20, canvas.winfo_height())
        canvas.create_text(width / 2, 18, text=self.vars.get("display_name", tk.StringVar(value="Character")).get() or "Character", fill="#e6edf3", font=("Segoe UI", 12, "bold"))
        try:
            p = {key: float(value.get()) for key, value in self.proportions.items()}
        except ValueError:
            p = {"shoulder_width": 1, "torso_length": 1, "arm_length": 1, "leg_length": 1, "head_scale": 1, "body_width": 1}
        base_x, ground = width / 2, height - 28
        leg_h, torso_h, arm_h, head = 112 * p["leg_length"], 128 * p["torso_length"], 76 * p["arm_length"], 44 * p["head_scale"]
        body_w, shoulder = 72 * p["body_width"], 96 * p["shoulder_width"]
        leg_w, arm_w = max(12, body_w * .30), max(13, body_w * .25)
        skin, top, bottom, shoes = (self._hex_colour(name) for name in ("skin", "top", "bottom", "shoes"))
        def rect(cx: float, cy: float, w: float, h: float, colour: str) -> None:
            canvas.create_rectangle(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, fill=colour, outline="#0d1117")
        rect(base_x - leg_w * .62, ground - leg_h / 2, leg_w, leg_h, bottom); rect(base_x + leg_w * .62, ground - leg_h / 2, leg_w, leg_h, bottom)
        rect(base_x - leg_w * .62, ground - 4, leg_w * 1.1, 17, shoes); rect(base_x + leg_w * .62, ground - 4, leg_w * 1.1, 17, shoes)
        hips_y = ground - leg_h - 12; rect(base_x, hips_y, body_w * .82, 30, bottom)
        torso_y = hips_y - torso_h / 2 - 13; rect(base_x, torso_y, body_w, torso_h, top)
        arm_y = torso_y - torso_h * .10; rect(base_x - shoulder / 2, arm_y, arm_w, arm_h, top); rect(base_x + shoulder / 2, arm_y, arm_w, arm_h, top)
        rect(base_x - shoulder / 2, arm_y + arm_h * .52, arm_w * .9, arm_h * .85, skin); rect(base_x + shoulder / 2, arm_y + arm_h * .52, arm_w * .9, arm_h * .85, skin)
        neck_y = torso_y - torso_h / 2 - 9; rect(base_x, neck_y, 20 * p["head_scale"], 18 * p["head_scale"], skin)
        rect(base_x, neck_y - head * .55, head, head, skin)
        for name, swatch in self.color_swatches.items(): swatch.configure(background=self._hex_colour(name))

    def _build_clip_rows(self) -> None:
        previously_checked = {clip for clip, value in self.clip_vars.items() if value.get()}
        for child in self.clip_rows_frame.winfo_children(): child.destroy()
        self.clip_vars = {}
        custom_label_shown = False
        for clip in supported_clips():
            if clip not in BUILTIN_CLIPS and not custom_label_shown:
                custom_label_shown = True
                ttk.Label(self.clip_rows_frame, text="Custom presets (presets/animations/)", font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))
            var = tk.BooleanVar(value=clip in previously_checked); self.clip_vars[clip] = var
            row = ttk.Frame(self.clip_rows_frame); row.pack(fill="x", pady=3)
            ttk.Checkbutton(row, text=clip, variable=var).pack(side="left")
            ttk.Button(row, text="View anim in Blender", command=lambda clip=clip: self.preview_clip(clip)).pack(side="left", padx=(10, 0))

    def refresh_clips(self) -> None:
        self._build_clip_rows()
        self.status.set("Refreshed clip list from presets/animations/.")

    def load_state(self, config: dict) -> None:
        config = validate_config(config)
        self._build_clip_rows()
        for key, value in self.vars.items(): value.set(str(config[key]))
        for key, value in self.proportions.items(): value.set(str(config["proportions"][key]))
        for key, value in self.body.items(): value.set(str(config["body"][key]))
        for key, values in self.colors.items():
            for variable, channel in zip(values, config["materials"][key]): variable.set(str(channel))
        for clip, value in self.clip_vars.items(): value.set(clip in config["clips"])

    def load_preset(self) -> None:
        path = filedialog.askopenfilename(title="Load character preset", initialdir=str(ROOT / "presets"), filetypes=(("Character config", "*.json"),))
        if path: self.load_state(load_config(path)); self.status.set(f"Loaded {Path(path).name}")

    def open_config(self) -> None:
        path = filedialog.askopenfilename(title="Open character config", initialdir=str(ROOT), filetypes=(("Character config", "*.json"),))
        if path: self.load_state(load_config(path)); self.status.set(f"Opened {Path(path).name}")

    def save_config(self) -> None:
        config = self.state(); path = filedialog.asksaveasfilename(title="Save character config", initialdir=str(ROOT / "presets"), initialfile=f"{config['character_id']}.json", defaultextension=".json", filetypes=(("Character config", "*.json"),))
        if path: save_config(path, config); self.status.set(f"Saved {Path(path).name}")

    def _write_log(self, text: str) -> None:
        self.log.configure(state="normal"); self.log.insert("end", text); self.log.see("end"); self.log.configure(state="disabled")

    def preview_clip(self, clip_name: str) -> None:
        blender = find_blender()
        if not blender: messagebox.showerror("Character Creation Suite", "Blender 5.0 was not found. Install Blender or add it to PATH."); return
        config = self.state()
        config_path = ROOT / config["output_root"] / "_preview" / "character_config.json"; save_config(config_path, config)
        self.status.set(f"Opening {clip_name} preview in Blender…")
        command = [blender, "--python", str(ROOT / "blender_preview.py"), "--", str(config_path), clip_name]
        subprocess.Popen(command, cwd=ROOT)

    def generate(self) -> None:
        config = self.state(); blender = find_blender()
        if not blender: messagebox.showerror("Character Creation Suite", "Blender 5.0 was not found. Install Blender or add it to PATH."); return
        config_path = ROOT / config["output_root"] / safe_id(config["character_id"]) / "character_config.json"; save_config(config_path, config)
        self.status.set("Generating in headless Blender…"); self._write_log(f"\n> {config['character_id']}\n")
        def worker():
            command = [blender, "--background", "--python", str(ROOT / "blender_build.py"), "--", str(config_path)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.root.after(0, lambda: self._finish_generation(result, config_path))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_generation(self, result: subprocess.CompletedProcess, config_path: Path) -> None:
        self._write_log(result.stdout + result.stderr + "\n")
        manifest_path = config_path.parent / "manifest.json"
        if result.returncode == 0 and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")); self.status.set(f"Built {Path(manifest['blend']).name} with {len(manifest['clips'])} clips")
            messagebox.showinfo("Character Creation Suite", f"Generated Blender file:\n{manifest['blend']}\n\nFBX: {manifest['fbx']}\n\nClips: {', '.join(manifest['clips'])}")
        else: self.status.set("Build failed — see Build tab log"); messagebox.showerror("Character Creation Suite", "Blender did not complete the build. See the Build tab log.")


if __name__ == "__main__":
    root = tk.Tk(); CharacterSuite(root); root.mainloop()
