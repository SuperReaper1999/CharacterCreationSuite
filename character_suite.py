"""Desktop UI for building configurable rigged characters in Blender (Windows, Linux, macOS)."""

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
from tkinter import font as tkfont

from blender_locator import describe, find_blender, mpfb_data_dirs
from character_config import BUILTIN_CLIPS, default_config, load_config, safe_id, save_config, supported_clips, validate_config

ROOT = Path(__file__).resolve().parent


def mpfb_asset_names(subdir: str, startswith: str = "") -> list[str]:
    """Installed MPFB asset folder names, e.g. ("skins") or ("clothes", "shoes")."""
    for data in mpfb_data_dirs():
        folder = data / subdir
        if folder.is_dir():
            return sorted(path.name for path in folder.iterdir() if path.is_dir() and path.name.startswith(startswith))
    return []


BLENDER_NOT_FOUND = ("Blender wasn't found. Install Blender 5.0+ and put 'blender' on your PATH, "
                     "or set the CCS_BLENDER environment variable to the Blender executable. "
                     "(Searched: PATH, standard install folders, and Flatpak org.blender.Blender.)")
# Settings that change how the character looks; the preview is marked out of
# date when any of these differ from what the thumbnail was rendered with.
APPEARANCE_KEYS = ("character_id", "target_height_m", "body", "skin", "hair", "outfit", "shoes", "proportions", "materials", "ground_contact")


# First installed family wins: Segoe UI on Windows, common Linux/macOS sans
# fonts otherwise, then Tk's own default.
UI_FONTS = ("Segoe UI", "Noto Sans", "DejaVu Sans", "Cantarell", "Ubuntu", "Liberation Sans", "Helvetica Neue", "Helvetica", "Arial")


def pick_ui_font(root) -> str:
    try:
        installed = set(tkfont.families(root))
    except tk.TclError:
        installed = set()
    return next((family for family in UI_FONTS if family in installed), "TkDefaultFont")


class CharacterSuite:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root; root.title("Character Creation Suite"); root.minsize(930, 720)
        self.vars: dict[str, tk.Variable] = {}; self.proportions: dict[str, tk.StringVar] = {}; self.colors: dict[str, list[tk.StringVar]] = {}; self.clip_vars: dict[str, tk.BooleanVar] = {}
        self.color_swatches: dict[str, tk.Label] = {}
        self.status = tk.StringVar(value="Ready. Load a preset or adjust the character.")
        self.ui_font = pick_ui_font(root)
        self._build(); self._watch_preview(); self.load_state(default_config())
        data = mpfb_data_dirs()
        self._write_log(f"Blender: {describe(find_blender())}\nMPFB assets: {data[0] if data else 'not found (run setup_mpfb.py, see README)'}\n")

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
        preview = ttk.LabelFrame(identity, text="Character preview", padding=6); preview.grid(row=0, column=2, rowspan=9, sticky="nsew", padx=(22, 0))
        self.preview_canvas = tk.Canvas(preview, width=350, height=510, background="#1a202b", highlightthickness=0); self.preview_canvas.pack(fill="both", expand=True)
        preview_bar = ttk.Frame(preview); preview_bar.pack(fill="x", pady=(6, 0))
        self.preview_button = ttk.Button(preview_bar, text="Render preview", command=self.render_preview); self.preview_button.pack(side="left")
        ttk.Label(preview_bar, text="Rendered by Blender (Idle pose).").pack(side="left", padx=(8, 0))
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
        ttk.Label(header, text="Select clips to bake as Blender Actions (also exported as FBX takes). Bones only rotate; the character is kept on the floor by an automatic vertical Root offset (ground_contact in the config). Animation events aren't generated.", wraplength=560).pack(side="left")
        ttk.Button(header, text="Refresh clip list", command=self.refresh_clips).pack(side="right")
        ttk.Label(animations, text="Edit a clip's pose in the Blender preview, then save it there as a preset — it shows up here after Refresh.", wraplength=680, foreground="#5a6b8c").pack(anchor="w", pady=(0, 10))
        self.clip_rows_frame = ttk.Frame(animations); self.clip_rows_frame.pack(fill="both", expand=True)
        self.log = tk.Text(output, height=27, wrap="word", state="disabled", background="#151922", foreground="#e6edf3"); self.log.pack(fill="both", expand=True)
        ttk.Label(self.root, textvariable=self.status, relief=tk.SUNKEN, anchor="w", padding=(8, 4)).grid(row=2, column=0, sticky="ew")

    def state(self) -> dict:
        # Keys without a widget (output_root, export switches, ground_contact)
        # come from the last loaded config instead of resetting to defaults.
        raw = {**getattr(self, "_loaded_extras", {}), **{key: value.get() for key, value in self.vars.items()}}
        raw["proportions"] = {key: value.get() for key, value in self.proportions.items()}; raw["body"] = {key: value.get() for key, value in self.body.items()}; raw["materials"] = {key: [value.get() for value in values] for key, values in self.colors.items()}; raw["clips"] = [name for name, value in self.clip_vars.items() if value.get()]
        return validate_config(raw)

    def _watch_preview(self) -> None:
        self._rendering = False; self._thumbnail = None; self._thumbnail_key = None
        for variable in [*self.vars.values(), *self.proportions.values(), *self.body.values(), *(value for values in self.colors.values() for value in values)]:
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

    def thumbnail_files(self, config: dict) -> tuple[Path, Path]:
        """The last rendered preview for this character (written by
        blender_build.py, by a full build or Render preview), and the config
        it was rendered from."""
        folder = ROOT / config["output_root"] / safe_id(config["character_id"])
        return folder / f"{config['character_id']}_Thumbnail.png", folder / f"{config['character_id']}_Thumbnail.json"

    @staticmethod
    def _appearance(config: dict) -> str:
        return json.dumps({key: config.get(key) for key in APPEARANCE_KEYS}, sort_keys=True)

    def draw_preview(self) -> None:
        for name, swatch in self.color_swatches.items(): swatch.configure(background=self._hex_colour(name))
        if not hasattr(self, "preview_canvas") or not hasattr(self, "_rendering"):
            return
        canvas = self.preview_canvas; canvas.delete("all")
        width, height = max(20, canvas.winfo_width()), max(20, canvas.winfo_height())
        config = self.state()
        image_path, config_path = self.thumbnail_files(config)
        if image_path.is_file():
            key = (str(image_path), image_path.stat().st_mtime)
            if key != self._thumbnail_key:
                try:
                    self._thumbnail = tk.PhotoImage(file=str(image_path)); self._thumbnail_key = key
                except tk.TclError:
                    self._thumbnail = None; self._thumbnail_key = None
        else:
            self._thumbnail = None; self._thumbnail_key = None
        if self._thumbnail is not None:
            canvas.create_image(width / 2, height / 2, image=self._thumbnail)
            try:
                stale = self._appearance(json.loads(config_path.read_text(encoding="utf-8"))) != self._appearance(config)
            except (OSError, ValueError):
                stale = True
            if stale and not self._rendering:
                canvas.create_rectangle(0, 0, width, 30, fill="#3d2f12", outline="")
                canvas.create_text(width / 2, 15, text="Out of date — click Render preview", fill="#f2cc60", font=(self.ui_font, 10, "bold"))
        elif not self._rendering:
            canvas.create_text(width / 2, height / 2, text="No preview yet.\n\nClick Render preview (about 15–30 s),\nor Generate character.", fill="#8b98a9", font=(self.ui_font, 11), justify="center")
        if self._rendering:
            canvas.create_rectangle(0, height - 30, width, height, fill="#12304d", outline="")
            canvas.create_text(width / 2, height - 15, text="Rendering in Blender…", fill="#9fd0ff", font=(self.ui_font, 10, "bold"))

    def render_preview(self) -> None:
        if self._rendering:
            return
        blender = find_blender()
        if not blender: messagebox.showerror("Character Creation Suite", BLENDER_NOT_FOUND); return
        config = self.state()
        config_path = ROOT / config["output_root"] / "_preview" / f"{config['character_id']}_thumbnail_config.json"; save_config(config_path, config)
        self._rendering = True; self.preview_button.state(["disabled"]); self.status.set("Rendering preview in headless Blender…"); self.draw_preview()
        def worker():
            command = [*blender, "--background", "--python", str(ROOT / "blender_build.py"), "--", str(config_path), "--thumbnail-only"]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.root.after(0, lambda: self._finish_preview(result))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_preview(self, result: subprocess.CompletedProcess) -> None:
        self._rendering = False; self.preview_button.state(["!disabled"])
        if result.returncode == 0 and "CHARACTER_SUITE_THUMBNAIL" in result.stdout:
            self.status.set("Preview rendered.")
        else:
            self._write_log("\n> Render preview\n" + result.stdout + result.stderr + "\n")
            self.status.set("Preview render failed — see Build tab log")
        self.draw_preview()

    def _build_clip_rows(self) -> None:
        previously_checked = {clip for clip, value in self.clip_vars.items() if value.get()}
        for child in self.clip_rows_frame.winfo_children(): child.destroy()
        self.clip_vars = {}
        custom_label_shown = False
        for clip in supported_clips():
            if clip not in BUILTIN_CLIPS and not custom_label_shown:
                custom_label_shown = True
                ttk.Label(self.clip_rows_frame, text="Custom presets (presets/animations/)", font=(self.ui_font, 9, "bold")).pack(anchor="w", pady=(10, 2))
            var = tk.BooleanVar(value=clip in previously_checked); self.clip_vars[clip] = var
            row = ttk.Frame(self.clip_rows_frame); row.pack(fill="x", pady=3)
            ttk.Checkbutton(row, text=clip, variable=var).pack(side="left")
            ttk.Button(row, text="View anim in Blender", command=lambda clip=clip: self.preview_clip(clip)).pack(side="left", padx=(10, 0))

    def refresh_clips(self) -> None:
        self._build_clip_rows()
        self.status.set("Refreshed clip list from presets/animations/.")

    def load_state(self, config: dict) -> None:
        config = validate_config(config)
        self._loaded_extras = {key: config[key] for key in ("output_root", "export_preview_glb", "export_separate_animations", "ground_contact")}
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
        if not blender: messagebox.showerror("Character Creation Suite", BLENDER_NOT_FOUND); return
        config = self.state()
        config_path = ROOT / config["output_root"] / "_preview" / "character_config.json"; save_config(config_path, config)
        self.status.set(f"Opening {clip_name} preview in Blender…")
        command = [*blender, "--python", str(ROOT / "blender_preview.py"), "--", str(config_path), clip_name]
        subprocess.Popen(command, cwd=ROOT)

    def generate(self) -> None:
        config = self.state(); blender = find_blender()
        if not blender: messagebox.showerror("Character Creation Suite", BLENDER_NOT_FOUND); return
        config_path = ROOT / config["output_root"] / safe_id(config["character_id"]) / "character_config.json"; save_config(config_path, config)
        self.status.set("Generating in headless Blender…"); self._write_log(f"\n> {config['character_id']}\n")
        def worker():
            command = [*blender, "--background", "--python", str(ROOT / "blender_build.py"), "--", str(config_path)]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.root.after(0, lambda: self._finish_generation(result, config_path))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_generation(self, result: subprocess.CompletedProcess, config_path: Path) -> None:
        self._write_log(result.stdout + result.stderr + "\n")
        manifest_path = config_path.parent / "manifest.json"
        if result.returncode == 0 and manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")); self.status.set(f"Built {Path(manifest['blend']).name} with {len(manifest['clips'])} clips"); self.draw_preview()
            messagebox.showinfo("Character Creation Suite", f"Generated Blender file:\n{manifest['blend']}\n\nFBX: {manifest['fbx']}\n\nClips: {', '.join(manifest['clips'])}")
        else: self.status.set("Build failed — see Build tab log"); messagebox.showerror("Character Creation Suite", "Blender did not complete the build. See the Build tab log.")


if __name__ == "__main__":
    root = tk.Tk(); CharacterSuite(root); root.mainloop()
