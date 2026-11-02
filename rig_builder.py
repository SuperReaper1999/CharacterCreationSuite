"""Character construction for the Character Creation Suite, built on MPFB.

MPFB (MakeHuman Plugin For Blender, GPL code, CC0 assets) generates the
actual character: a realistic body shaped by MakeHuman targets, a real
skin texture, eyes, eyebrows, eyelashes, hair, a textured outfit and
shoes, and MPFB's "game_engine" rig (53 bones, including 3 bones per
finger) with skin weights for the body and every clothing item.

This module turns a suite config into an MPFB character, then applies the
suite's colour slots on top of the MPFB materials:
- skin: multiplies the skin texture by the colour (alpha = strength);
- top / bottom: recolour the outfit's upper and lower parts, keeping the
  fabric texture's shading (alpha = strength, 0 keeps the original);
- shoes: the same for the shoes.

Used by both the headless export worker (blender_build.py) and the
interactive preview (blender_preview.py), so both always build the same
character from a config.

MPFB must be installed in the Blender that runs this, together with the
MakeHuman system asset pack; see setup_mpfb.py and the README.
"""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path
from typing import Any

import bpy

RIG_NAME = "game_engine"
EYES_ASSET = "high-poly/high-poly.mhclo"
EYEBROWS_ASSET = "eyebrow001/eyebrow001.mhclo"
EYELASHES_ASSET = "eyelashes01/eyelashes01.mhclo"
SKIN_MATERIAL_TYPE = "ENHANCED_SSS"
# MPFB's create_human scale: 0.1 turns MakeHuman decimetres into metres.
MPFB_METRE_SCALE = 0.1
REGION_ATTRIBUTE = "ccs_region"


class MpfbNotAvailable(RuntimeError):
    pass


def action_fcurves(action):
    """Compatibility shim for Blender <=4.x and Blender 4.4+/5.x Actions."""
    if hasattr(action, "fcurves"):
        yield from action.fcurves
        return
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for channelbag in getattr(strip, "channelbags", []):
                yield from getattr(channelbag, "fcurves", [])


# ---------------------------------------------------------------- MPFB access

def mpfb_package() -> str:
    """Enable MPFB and return its package name (e.g. bl_ext.user_default.mpfb
    or bl_ext.blender_org.mpfb, depending on how it was installed)."""
    import addon_utils
    candidates = [module.__name__ for module in addon_utils.modules() if module.__name__.split(".")[-1] == "mpfb"]
    if not candidates:
        raise MpfbNotAvailable(
            "MPFB is not installed in this Blender. Run once:\n"
            "  blender --background --python setup_mpfb.py\n"
            "(see README, 'Setup').")
    package = candidates[0]
    # default_set=True registers it in this session's preferences, which MPFB
    # needs for its own settings; nothing is saved to the user's prefs.
    addon_utils.enable(package, default_set=True)
    return package


def mpfb_service(name: str):
    """Import an MPFB service class, e.g. mpfb_service("HumanService")."""
    package = mpfb_package()
    module = importlib.import_module(f"{package}.services.{name.lower()}")
    return getattr(module, name)


def mpfb_asset_names(subdir: str) -> list[str]:
    """Names of installed MPFB assets in a subdirectory (skins, clothes, hair...)."""
    location = mpfb_service("LocationService")
    root = Path(location.get_user_data(subdir))
    return sorted(path.name for path in root.iterdir() if path.is_dir()) if root.is_dir() else []


# ---------------------------------------------------------------- config -> MPFB

def _signed_weight(value: float) -> float:
    """Map a suite proportion ratio (0.55-1.8, 1.0 = neutral) to a MakeHuman
    target weight in -1..1 (0.55 -> -1, 1.8 -> +1)."""
    weight = (value - 1.0) / (0.45 if value < 1.0 else 0.8)
    return max(-1.0, min(1.0, weight))


# Suite proportion -> MakeHuman targets (each has -decr / -incr variants).
_PROPORTION_TARGETS = {
    "shoulder_width": ("measure-shoulder-dist",),
    "torso_length": ("measure-napetowaist-dist",),
    "arm_length": ("measure-upperarm-length", "measure-lowerarm-length"),
    "leg_length": ("measure-upperleg-height", "measure-lowerleg-height"),
    "head_scale": ("head-scale-horiz", "head-scale-vert", "head-scale-depth"),
    "body_width": ("torso-scale-horiz", "measure-hips-circ"),
}


def _targets(config: dict[str, Any]) -> list[dict[str, Any]]:
    targets = []
    for key, names in _PROPORTION_TARGETS.items():
        weight = _signed_weight(config["proportions"][key])
        if abs(weight) < 1e-4:
            continue
        for name in names:
            targets.append({"target": f"{name}-{'incr' if weight > 0 else 'decr'}", "value": abs(weight)})
    return targets


def _asset(subdir_name: str) -> str:
    return f"{subdir_name}/{subdir_name}.mhclo" if subdir_name else ""


def _human_info(config: dict[str, Any], height_macro: float) -> dict[str, Any]:
    human_service = mpfb_service("HumanService")
    info = human_service._create_default_human_info_dict()
    body = config["body"]
    info["phenotype"].update(gender=body["gender"], age=body["age"], muscle=body["muscle"], weight=body["weight"], height=height_macro)
    info.update(
        name=config["character_id"],
        rig=RIG_NAME,
        eyes=EYES_ASSET, eyebrows=EYEBROWS_ASSET, eyelashes=EYELASHES_ASSET,
        hair=_asset(config["hair"]),
        clothes=[asset for asset in (_asset(config["outfit"]), _asset(config["shoes"])) if asset],
        skin_mhmat=f"{config['skin']}/{config['skin']}.mhmat",
        skin_material_type=SKIN_MATERIAL_TYPE,
        targets=_targets(config),
    )
    return info


def _check_assets(config: dict[str, Any]) -> None:
    missing = []
    for key, subdir in (("skin", "skins"), ("hair", "hair"), ("outfit", "clothes"), ("shoes", "clothes")):
        if config[key] and config[key] not in mpfb_asset_names(subdir):
            missing.append(f"{key} '{config[key]}' (installed {subdir}: {', '.join(mpfb_asset_names(subdir)) or 'none'})")
    if missing:
        raise MpfbNotAvailable("MPFB asset not found: " + "; ".join(missing) + ". Is the MakeHuman system asset pack installed? (setup_mpfb.py)")


def _evaluated_height(obj) -> float:
    """Height of the evaluated body mesh. MPFB adds a "Delete.<item>" mask
    per clothing item that removes body skin hidden under it (the shoes'
    one removes the feet), so those are switched off while measuring: the
    result is the barefoot body height."""
    clothing_masks = [modifier for modifier in obj.modifiers if modifier.type == "MASK" and modifier.name.startswith("Delete.") and modifier.show_viewport]
    for modifier in clothing_masks:
        modifier.show_viewport = False
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    heights = [(obj.matrix_world @ vertex.co).z for vertex in mesh.vertices]
    evaluated.to_mesh_clear()
    for modifier in clothing_masks:
        modifier.show_viewport = True
    return max(heights) - min(heights)


def body_height(armature) -> float:
    """Barefoot height of a built character's body mesh, in metres."""
    body = next(obj for obj in armature.children if obj.type == "MESH" and obj.name.endswith(".body"))
    return _evaluated_height(body)


def _clear_scene() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)


def _body_height(config: dict[str, Any], height_macro: float) -> float:
    """Height of the bare body (no rig/clothes) at MPFB metre scale."""
    human_service = mpfb_service("HumanService")
    info = _human_info(config, height_macro)
    basemesh = human_service.create_human(True, True, True, True, MPFB_METRE_SCALE, info["phenotype"])
    human_service._load_targets(info, basemesh)
    height = _evaluated_height(basemesh)
    _clear_scene()
    return height


def _solve_height(config: dict[str, Any]) -> tuple[float, float]:
    """Pick MakeHuman's height macro so the body matches target_height_m
    (bisection), and a uniform scale for whatever the macro can't reach."""
    target = config["target_height_m"]
    low, high = 0.0, 1.0
    low_height, high_height = _body_height(config, low), _body_height(config, high)
    if target <= low_height:
        return low, MPFB_METRE_SCALE * target / low_height
    if target >= high_height:
        return high, MPFB_METRE_SCALE * target / high_height
    macro, height = 0.5, None
    for _ in range(8):
        macro = (low + high) / 2
        height = _body_height(config, macro)
        if height < target:
            low = macro
        else:
            high = macro
    return macro, MPFB_METRE_SCALE * target / height


# ---------------------------------------------------------------- materials

def _skin_tint(basemesh, color) -> None:
    """Multiply the skin texture by the skin colour, alpha = strength. Uses
    the colorMixIn inputs MPFB's enhanced skin group already exposes."""
    material = basemesh.active_material
    for node in material.node_tree.nodes:
        group = getattr(node, "node_tree", None)
        if node.type == "GROUP" and group and "Mix" in group.nodes and "colorMixIn" in node.inputs:
            group.nodes["Mix"].blend_type = "MULTIPLY"
            node.inputs["colorMixIn"].default_value = (color[0], color[1], color[2], 1.0)
            node.inputs["colorMixInStrength"].default_value = color[3]
            return
    raise RuntimeError(f"Skin material {material.name} has no colorMixIn input to tint")


def _srgb_to_linear(channel):
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _uv_islands(mesh) -> list[int]:
    """Face index -> UV island id (faces joined by an edge whose UVs match)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(mesh)
    uv_layer = bm.loops.layers.uv.active
    bm.faces.ensure_lookup_table()

    def edge_uvs(loop):
        return {loop.vert.index: tuple(round(c, 5) for c in loop[uv_layer].uv),
                loop.link_loop_next.vert.index: tuple(round(c, 5) for c in loop.link_loop_next[uv_layer].uv)}

    island_of = [-1] * len(bm.faces)
    island = 0
    for face in bm.faces:
        if island_of[face.index] >= 0:
            continue
        island_of[face.index] = island
        stack = [face]
        while stack:
            current = stack.pop()
            for loop in current.loops:
                uvs = edge_uvs(loop)
                for other in loop.edge.link_loops:
                    neighbour = other.face
                    if island_of[neighbour.index] < 0 and edge_uvs(other) == uvs:
                        island_of[neighbour.index] = island
                        stack.append(neighbour)
        island += 1
    bm.free()
    return island_of


def _outfit_regions(obj, waist_z: float) -> list[float]:
    """Per face: 1.0 = top (upper body), 0.0 = bottom. Each UV island goes
    to the side its mean height falls on, relative to the hips; shirt and
    trousers are separate UV islands in every MakeHuman system outfit."""
    mesh = obj.data
    island_of = _uv_islands(mesh)
    sums: dict[int, list[float]] = {}
    for polygon in mesh.polygons:
        z = sum((obj.matrix_world @ mesh.vertices[index].co).z for index in polygon.vertices) / len(polygon.vertices)
        entry = sums.setdefault(island_of[polygon.index], [0.0, 0])
        entry[0] += z
        entry[1] += 1
    top = {island: (total / count) >= waist_z for island, (total, count) in sums.items()}
    return [1.0 if top[island_of[polygon.index]] else 0.0 for polygon in mesh.polygons]


def _mean_luminance(obj, image, face_regions: list[float]) -> dict[float, float]:
    """Mean linear luminance of the diffuse texture over each region's UVs."""
    width, height = image.size
    pixels = list(image.pixels)
    uv_layer = obj.data.uv_layers.active.data
    totals: dict[float, list[float]] = {}
    for polygon in obj.data.polygons:
        region = face_regions[polygon.index]
        for loop_index in polygon.loop_indices:
            u, v = uv_layer[loop_index].uv
            x = min(width - 1, max(0, int((u % 1.0) * width)))
            y = min(height - 1, max(0, int((v % 1.0) * height)))
            offset = (y * width + x) * 4
            r, g, b = (_srgb_to_linear(pixels[offset + channel]) for channel in range(3))
            entry = totals.setdefault(region, [0.0, 0])
            entry[0] += 0.2126 * r + 0.7152 * g + 0.0722 * b
            entry[1] += 1
    return {region: max(total / count, 1e-3) for region, (total, count) in totals.items()}


def _recolour(obj, face_regions: list[float], colours: dict[float, list[float]]) -> None:
    """Recolour a clothing material per region, keeping the fabric shading:
    colour * (texture luminance / region's mean luminance), blended over
    the original texture by the colour's alpha."""
    material = obj.active_material
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    bsdf = next(node for node in nodes if node.type == "BSDF_PRINCIPLED")
    base_link = next(link for link in links if link.to_node == bsdf and link.to_socket.name == "Base Color")
    source = base_link.from_socket
    image = nodes["diffuseTexture"].image

    attribute = obj.data.color_attributes.get(REGION_ATTRIBUTE) or obj.data.color_attributes.new(REGION_ATTRIBUTE, "FLOAT_COLOR", "CORNER")
    for polygon in obj.data.polygons:
        value = face_regions[polygon.index]
        for loop_index in polygon.loop_indices:
            attribute.data[loop_index].color = (value, value, value, 1.0)
    mean = _mean_luminance(obj, image, face_regions)

    def node(kind, x, y, **settings):
        result = nodes.new(kind)
        result.location = (bsdf.location.x + x, bsdf.location.y + y)
        for key, value in settings.items():
            setattr(result, key, value)
        return result

    mask = node("ShaderNodeAttribute", -900, -300, attribute_name=REGION_ATTRIBUTE, attribute_type="GEOMETRY")

    def by_region(kind, bottom, top, x, y):
        """A Mix node picking `bottom` (region 0) or `top` (region 1) by the mask."""
        mix = node("ShaderNodeMix", x, y, data_type=kind)
        links.new(mask.outputs["Fac"], mix.inputs["Factor"])
        inputs = [socket for socket in mix.inputs if socket.enabled and socket.name in ("A", "B")]
        inputs[0].default_value, inputs[1].default_value = bottom, top
        return [socket for socket in mix.outputs if socket.enabled][0]

    bottom, top = colours.get(0.0, colours.get(1.0)), colours.get(1.0, colours.get(0.0))
    mean_bottom, mean_top = mean.get(0.0, mean.get(1.0)), mean.get(1.0, mean.get(0.0))
    target = by_region("RGBA", (*bottom[:3], 1.0), (*top[:3], 1.0), -700, -300)
    inverse_mean = by_region("FLOAT", 1.0 / mean_bottom, 1.0 / mean_top, -700, -500)
    strength = by_region("FLOAT", bottom[3], top[3], -700, -700)
    luminance = node("ShaderNodeRGBToBW", -700, -100)
    links.new(source, luminance.inputs["Color"])
    scaled = node("ShaderNodeMath", -500, -200, operation="MULTIPLY")
    links.new(luminance.outputs["Val"], scaled.inputs[0])
    links.new(inverse_mean, scaled.inputs[1])
    recoloured = node("ShaderNodeVectorMath", -300, -250, operation="SCALE")
    links.new(target, recoloured.inputs[0])
    links.new(scaled.outputs["Value"], recoloured.inputs["Scale"])
    blend = node("ShaderNodeMix", -150, -150, data_type="RGBA", blend_type="MIX")
    blend_inputs = [socket for socket in blend.inputs if socket.enabled and socket.name in ("A", "B")]
    links.new(strength, blend.inputs["Factor"])
    links.new(source, blend_inputs[0])
    links.new(recoloured.outputs["Vector"], blend_inputs[1])
    links.new([socket for socket in blend.outputs if socket.enabled][0], bsdf.inputs["Base Color"])


def _apply_colours(config: dict[str, Any], armature, meshes) -> None:
    colours = config["materials"]
    body = next(obj for obj in meshes if obj.name.endswith(".body"))
    _skin_tint(body, colours["skin"])
    waist_z = (armature.matrix_world @ armature.data.bones["pelvis"].head_local).z
    for obj in meshes:
        if config["outfit"] and obj.name.endswith("." + config["outfit"]):
            _recolour(obj, _outfit_regions(obj, waist_z), {1.0: colours["top"], 0.0: colours["bottom"]})
        elif config["shoes"] and obj.name.endswith("." + config["shoes"]):
            _recolour(obj, [0.0] * len(obj.data.polygons), {0.0: colours["shoes"]})


# ---------------------------------------------------------------- build

def build_character(config: dict[str, Any]) -> tuple[Any, list[Any], list[str]]:
    """Build the character described by a validated config into the
    current scene (replacing anything in it). Returns (armature, meshes,
    bone names); every mesh is parented to and deformed by the armature."""
    _clear_scene()
    bpy.context.scene.render.fps = 30
    _check_assets(config)
    height_macro, scale = _solve_height(config)

    human_service = mpfb_service("HumanService")
    settings = human_service.get_default_deserialization_settings()
    settings["scale"] = scale
    basemesh = human_service.deserialize_from_dict(_human_info(config, height_macro), settings)
    armature = basemesh.parent
    armature.name = f"{config['character_id']}_Armature"
    meshes = [obj for obj in armature.children if obj.type == "MESH"]
    _apply_colours(config, armature, meshes)
    return armature, meshes, [bone.name for bone in armature.data.bones]


def _material_output(tree):
    return next(node for node in tree.nodes if node.type == "OUTPUT_MATERIAL" and node.is_active_output)


def bake_export_materials(meshes, textures_dir: Path):
    """Prepare the character's materials for FBX/GLB export.

    The colour slots and MPFB's materials are node setups (texture -> mix
    nodes -> BSDF, or a skin node group) that FBX can't carry: its exporter
    only picks up an image plugged straight into a Principled BSDF. So each
    material's final base colour (tints and recolours included) is baked
    with Cycles into Textures/<material>_basecolor.png, and the material is
    temporarily rewired to a plain Principled BSDF using that image (plus
    the original alpha and normal map, where there is one).

    Returns ({material name: baked png path}, restore). Call restore()
    after exporting to put the original, editable node setups back.
    """
    textures_dir = Path(textures_dir)
    textures_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    previous_engine = scene.render.engine
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.cycles.device = "CPU"
    baked: dict[str, str] = {}
    undo: list = []

    for obj in meshes:
        material = obj.active_material
        if material is None or material.name in baked or not material.use_nodes:
            continue
        tree = material.node_tree
        nodes, links = tree.nodes, tree.links
        diffuse = nodes.get("diffuseTexture") or next((node for node in nodes if node.type == "TEX_IMAGE" and node.image), None)
        if diffuse is None:
            for node in nodes:
                group = getattr(node, "node_tree", None)
                if node.type == "GROUP" and group:
                    diffuse = group.nodes.get("DiffuseTexture")
        size = tuple(diffuse.image.size) if diffuse is not None and diffuse.image else (1024, 1024)
        image = bpy.data.images.new(f"{material.name}_basecolor", width=size[0], height=size[1], alpha=False)
        target_node = nodes.new("ShaderNodeTexImage")
        target_node.image = image
        nodes.active = target_node
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=4, use_clear=True)
        path = textures_dir / f"{bpy.path.clean_name(material.name)}_basecolor.png"
        image.filepath_raw = str(path)
        image.file_format = "PNG"
        image.save()
        baked[material.name] = str(path)

        # Temporary export wiring: baked colour -> new Principled BSDF -> output.
        output = _material_output(tree)
        old_surface = output.inputs["Surface"].links[0].from_socket if output.inputs["Surface"].is_linked else None
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        links.new(target_node.outputs["Color"], bsdf.inputs["Base Color"])
        original = next((node for node in nodes if node.type == "BSDF_PRINCIPLED" and node != bsdf), None)
        if original is not None:
            bsdf.inputs["Roughness"].default_value = original.inputs["Roughness"].default_value
            for socket_name in ("Alpha", "Normal"):
                if original.inputs[socket_name].is_linked:
                    links.new(original.inputs[socket_name].links[0].from_socket, bsdf.inputs[socket_name])
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
        undo.append((tree, output, old_surface, (target_node, bsdf)))

    def restore():
        for tree, output, old_surface, temporary in undo:
            if old_surface is not None:
                tree.links.new(old_surface, output.inputs["Surface"])
            for node in temporary:
                tree.nodes.remove(node)
        scene.render.engine = previous_engine

    return baked, restore


def export_textures(output_dir: Path) -> dict[str, str]:
    """Copy every image file the character uses into output_dir/Textures/
    and point the images at those copies, so the .blend and FBX reference
    files next to the build instead of the MPFB install. Returns
    {image name: copied path}. Colour slots are shader effects on top of
    these originals."""
    textures_dir = Path(output_dir) / "Textures"
    textures_dir.mkdir(parents=True, exist_ok=True)
    copied: dict[str, str] = {}
    for image in bpy.data.images:
        source = Path(bpy.path.abspath(image.filepath)) if image.filepath else None
        if not source or not source.is_file():
            continue
        destination = textures_dir / source.name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        image.filepath = str(destination)
        copied[image.name] = str(destination)
    return copied
