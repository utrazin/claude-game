"""Twin assets: the same model in another render mode (pixel art and smooth side by side).

``forge asset twin PROJECT --asset SOURCE --id TWIN [--mode smooth]`` registers TWIN with a copy of SOURCE's
current model (never regenerated), packs its own UVs at the mode's density and padding, and points every
variant at SOURCE's texture recipes: one recipe set paints both, each in its asset's render mode.

``forge asset twin PROJECT --asset TWIN --sync`` copies SOURCE's current model again (geometry, rig, manual
edits and animations) and repacks it with the twin's own remembered UV options. Paint afterwards with
``forge texture PROJECT --asset TWIN``.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from Tools._resolve import resolve_asset
from Tools.project_manifest import identifier, inside, load_project, project_lock, write_project
from Tools.TexturePainter.render_mode import MODES, PRESETS
from Tools.uv_packer import BoxUVPacker

MAX_ATLAS = 8192


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _pack(model: Path, options: dict):
    size, stats = BoxUVPacker.apply_to_bbmodel(str(model), **options, backup=False)
    print(f"[twin] UV atlas={size.width}x{size.height} {stats['uv_scale']} px/unit "
          f"padding={stats['island_padding']} islands={stats['element_count']}")


def create(project, source_id: str, twin_id: str, mode: str) -> Path:
    source = resolve_asset(project, source_id)
    root = source.project
    identifier(twin_id)
    if source.record.get("twin_of"):
        raise ValueError(f"{source_id} is itself a twin of {source.record['twin_of']}; twin the source asset")
    with project_lock(root):
        data = load_project(root)
        if twin_id in data["assets"]:
            raise ValueError(f"Asset {twin_id} already exists; use --sync to update its model")
        directory = root / "assets" / twin_id
        model = directory / "model.bbmodel"
        variants = {}
        for name, record in source.record.get("variants", {}).items():
            recipe = record.get("recipe") or _relative(root, source.scripts / "generate_texture.py")
            variants[name] = {"path": f"assets/{twin_id}/{Path(record['path']).name}", "recipe": recipe}
        if not variants:
            variants["default"] = {"path": f"assets/{twin_id}/texture.png",
                                   "recipe": _relative(root, source.scripts / "generate_texture.py")}
        record = {"name": twin_id, "model": f"assets/{twin_id}/model.bbmodel", "scripts": f"scripts/{twin_id}",
                  "twin_of": source_id, "texture_filter": "linear" if mode == "smooth" else "nearest",
                  "variants": variants,
                  "default_variant": source.record.get("default_variant") or next(iter(variants))}
        if mode == "smooth" and source.record.get("texture_filter", "nearest") == "nearest":
            # Stroke widths were written in the pixel source's texels: keep their size on the model.
            options = BoxUVPacker.remembered_options(source.model)
            record["render"] = {"reference": options.get("uv_scale", PRESETS["pixel"]["density"])}
        data["assets"][twin_id] = record
        directory.mkdir(parents=True, exist_ok=False)
        shutil.copy2(source.model, model)
        try:
            preset = PRESETS[mode]
            _pack(model, dict(uv_scale=preset["density"], island_padding=preset["padding"], max_size=MAX_ATLAS))
            write_project(root, data)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise
    print(f"[twin] PASS {twin_id} ({mode}) twin of {source_id}: paint with forge texture {root.name} --asset {twin_id}")
    return model


def sync(project, twin_id: str) -> Path:
    twin = resolve_asset(project, twin_id)
    source_id = twin.record.get("twin_of")
    if not source_id:
        raise ValueError(f"{twin_id} is not a twin asset (no twin_of)")
    source = resolve_asset(twin.project, source_id)
    options = BoxUVPacker.remembered_options(twin.model)
    keep = {key: options[key] for key in ("uv_scale", "island_padding", "max_size") if key in options}
    with project_lock(twin.project):
        shutil.copy2(twin.model, str(twin.model) + ".bak")
        shutil.copy2(source.model, twin.model)
        _pack(twin.model, keep)
    print(f"[twin] PASS {twin_id} synced from {source_id}; repaint with forge texture --asset {twin_id}")
    return twin.model


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("project", help="Project path (projects/<name>)")
    parser.add_argument("--asset", required=True, help="Source asset to twin, or the twin to --sync")
    parser.add_argument("--id", help="New twin asset identifier")
    parser.add_argument("--mode", choices=MODES, default="smooth", help="Render mode of the twin (default smooth)")
    parser.add_argument("--sync", action="store_true", help="Copy the source's current model into the twin again")
    args = parser.parse_args(argv)
    if args.sync:
        if args.id:
            raise ValueError("--sync updates the twin named by --asset; do not pass --id")
        sync(args.project, args.asset)
    else:
        if not args.id:
            raise ValueError("Give the new twin's identifier with --id")
        create(args.project, args.asset, args.id, args.mode)
    return 0
