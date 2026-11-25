"""Read-only stage existence and structural checks; never execute recipes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from Tools._resolve import resolve_model_target, resolve_asset, resolve_recipe


def asset_status(project: str | Path) -> dict:
    project_dir, model = resolve_model_target(project)
    result = {"project": str(project_dir), "all_pass": False}
    data = None
    try:
        if not model.exists():
            result["model"] = {"status": "MISSING", "action": "Request geometry explicitly or import a BBModel"}
        else:
            data = json.loads(model.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("elements"), list):
                raise ValueError("BBModel must contain an elements list")
            # Use the native builder validator where applicable, never recipes.
            from lib.model_builder import ModelBuilder
            validation = ModelBuilder.from_bbmodel_data(data).validate()
            result["model"] = {"status": "FAIL" if validation.get("errors") else "PASS",
                               "errors": validation.get("errors", []), "warnings": len(validation.get("warnings", []))}
    except Exception as exc:
        result["model"] = {"status": "FAIL", "error": str(exc)}
    if data is None:
        result["uv"] = {"status": "MISSING", "reason": "No readable BBModel"}
    else:
        try:
            from Tools.TexturePainter.core.bbmodel_parser import BlockbenchModelParser
            BlockbenchModelParser.from_document(data)
            result["uv"] = {"status": "PASS"}
            from Tools.uv_contract import filter_padding_warning
            warning = filter_padding_warning(resolve_asset(project).texture_filter, data)
            if warning:
                result["uv"]["warning"] = warning
        except Exception as exc:
            result["uv"] = {"status": "MISSING", "reason": str(exc), "action": "Run Tools.uv_packer explicitly"}
    texture = resolve_asset(project).texture
    from Tools.TexturePainter.export import TextureExporter
    slot_paths = TextureExporter.model_slot_png_paths(data or {}, texture)
    is_single_default = len(slot_paths) == 1 and slot_paths[0][0]["name"] == "default"
    if any(not spath.exists() for _, spath in slot_paths):
        result["texture"] = {"status": "MISSING", "action": "Run Tools.texture_export explicitly after UV"}
    else:
        try:
            from PIL import Image
            slot_resolutions = {}
            width = height = 0
            for idx, (slot, spath) in enumerate(slot_paths):
                with Image.open(spath) as image:
                    w, h = image.size
                    image.verify()
                if idx == 0:
                    width, height = w, h
                slot_resolutions[slot["name"]] = f"{w}x{h}"
            result["texture"] = {"status": "PASS", "resolution": f"{width}x{height}"}
            if not is_single_default:
                result["texture"]["textures"] = slot_resolutions
        except Exception as exc:
            result["texture"] = {"status": "FAIL", "error": str(exc)}
    result["animation"] = None
    result["texture_variants"] = {}
    context = resolve_asset(project)
    from Tools.project_manifest import inside
    for name, record in context.record.get("variants", {}).items():
        path = inside(context.project, record["path"])
        if is_single_default:
            ok = path.is_file()
        else:
            v_slots = TextureExporter.model_slot_png_paths(data or {}, path)
            ok = any(spath.is_file() for _, spath in v_slots)
        result["texture_variants"][name] = {"status": "PASS" if ok else "MISSING", "path": str(path)}
    if resolve_recipe(project, "animation").exists() or (data or {}).get("animations"):
        try:
            from lib.animation import validate_animations
            summary = validate_animations(data) if data else {"animations": 0}
            result["animation"] = {"status": "PASS" if summary["animations"] else "MISSING", "clips": summary["animations"]}
        except Exception as exc:
            result["animation"] = {"status": "FAIL", "error": str(exc)}
    result["all_pass"] = all((result[stage] or {"status": "PASS"})["status"] == "PASS"
                             for stage in ("model", "uv", "texture", "animation"))
    return result


def print_status(status):
    for stage in ("model", "uv", "texture", "animation"):
        info = status.get(stage)
        if info is None:
            continue
        print(f"[{stage}] {info['status']} {info.get('reason') or info.get('error') or ''}".rstrip())
        if info.get("warning"):
            print(f"  WARN {info['warning']}")
        if info.get("action"):
            print(f"  -> {info['action']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = asset_status(args.project)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print_status(report)
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
