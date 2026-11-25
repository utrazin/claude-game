"""Export selected products into explicit paths under the project's assets directory."""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import tempfile
from pathlib import Path

from Tools._resolve import resolve_asset
from Tools.gltf_export import GLBWriter
from Tools.project_manifest import inside, load_project

def selected_document(data, *, include=(), exclude=(), animations=None):
    """Select geometry non-destructively; retain ancestor transforms and skeletons."""
    result = copy.deepcopy(data)
    elements = {e["uuid"]: e for e in data.get("elements", [])}
    groups = {g["uuid"]: g for g in data.get("groups", [])}
    descendants, names, paths = {}, {}, {}
    visited = set()

    def visit(raw, prefix=()):
        uid = raw if isinstance(raw, str) else raw.get("uuid")
        if uid in visited:
            raise ValueError(f"Duplicate/cyclic hierarchy id {uid}")
        visited.add(uid)
        item = groups.get(uid) or elements.get(uid) or raw
        if not isinstance(item, dict):
            raise ValueError(f"Missing outliner item {uid}")
        name = item.get("name", uid)
        path = (*prefix, name)
        names.setdefault(name, []).append(uid)
        paths["/".join(path)] = uid
        found = {uid} if item.get("type", "cube") in ("cube", "mesh") and uid in elements else set()
        children = raw.get("children", item.get("children", [])) if isinstance(raw, dict) else item.get("children", [])
        for child in children:
            found |= visit(child, path)
        descendants[uid] = found
        return found

    for node in data.get("outliner", []):
        visit(node)
    for uid in elements:
        if uid not in visited:
            visit(uid)
    def resolve(selector):
        if selector in descendants:
            return selector
        if selector in paths:
            return paths[selector]
        matches = names.get(selector, [])
        if len(matches) != 1:
            raise ValueError(f"Unknown or ambiguous part selector {selector!r}; use UUID or full hierarchy path")
        return matches[0]
    geometry = {uid for uid, e in elements.items() if e.get("type", "cube") in ("cube", "mesh")}
    chosen = set().union(*(descendants[resolve(name)] for name in include)) if include else geometry
    chosen -= set().union(*(descendants[resolve(name)] for name in exclude)) if exclude else set()
    if not chosen:
        raise ValueError("Part selection contains no geometry")
    retained = set(elements)-geometry | chosen
    result["elements"] = [e for e in result["elements"] if e["uuid"] in retained]
    for e in result["elements"]:
        if "children" in e:
            e["children"] = [child for child in e["children"] if child in retained or child in groups]
    def prune(nodes):
        filtered = []
        for node in nodes:
            if isinstance(node, str):
                if node in retained or node in groups:
                    filtered.append(node)
            else:
                if node.get("uuid") in geometry and node["uuid"] not in chosen:
                    continue
                node["children"] = prune(node.get("children", []))
                filtered.append(node)
        return filtered
    result["outliner"] = prune(result.get("outliner", []))
    if animations is not None:
        missing = set(animations)-{clip["name"] for clip in result.get("animations", [])}
        if missing:
            raise ValueError(f"Unknown animation clips: {sorted(missing)}")
        result["animations"] = [clip for clip in result.get("animations", []) if clip["name"] in animations]
    for clip in result.get("animations", []):
        clip["animators"] = {uid: track for uid, track in clip.get("animators", {}).items()
                             if uid not in geometry or uid in chosen}
    return result


def output_path(context, output):
    if not (context.project / "project.json").is_file():
        raise ValueError("Export requires a registered project (project.json with assets)")
    path = inside(context.project / "assets", output)
    if not path.is_relative_to(context.project.resolve()):
        raise ValueError("Export assets directory resolves outside the selected project")
    for asset in load_project(context.project)["assets"].values():
        if path == inside(context.project, asset["model"]) or path.is_relative_to(inside(context.project, asset["scripts"])):
            raise ValueError("Export destination collides with a source model or recipe directory")
        if any(path == inside(context.project, record["path"]) for record in asset.get("variants", {}).values()):
            raise ValueError("Export destination collides with a source texture variant")
        source = inside(context.project, asset["model"])
        if source.is_file():
            try:
                textures = json.loads(source.read_text(encoding="utf-8")).get("textures", [])
            except ValueError:
                textures = []
            for texture in textures:
                reference = texture.get("relative_path") or texture.get("path")
                if reference and path == (source.parent / reference).resolve():
                    raise ValueError("Export destination collides with a linked source texture")
    return path


def _prepare_export(target, *, output, format=None, variant=None, include=(), exclude=(),
                 animations=None, overwrite=False, scale=1/16, fps=60):
    context = resolve_asset(target)
    destination = output_path(context, output)
    kind = format or destination.suffix.lstrip(".").lower()
    if kind not in ("glb", "png", "bbmodel") or destination.suffix.lower() != f".{kind}":
        raise ValueError("Output extension must match glb, png or bbmodel")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output exists; use --overwrite explicitly: {destination}")
    original = context.model.read_bytes()
    document = json.loads(original)
    texture = None
    variant_textures = None
    packed_slots = document.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {}).get("textures")
    if variant:
        if variant not in context.record.get("variants", {}):
            raise ValueError(f"Unknown texture variant {variant!r}")
        texture = inside(context.project, context.record["variants"][variant]["path"])
        if isinstance(packed_slots, list) and packed_slots:
            from Tools.TexturePainter.export import TextureExporter
            v_slots = TextureExporter.model_slot_png_paths(document, texture)
            d_slots = TextureExporter.model_slot_png_paths(document, context.texture)
            if not any(vp.is_file() for _, vp in v_slots):
                raise ValueError(f"Texture variant does not exist: {texture}; run texture stage explicitly")
            variant_textures = [vp if vp.is_file() else dp for (_, vp), (_, dp) in zip(v_slots, d_slots)]
            if any(not p.is_file() for p in variant_textures):
                raise ValueError(f"Texture variant does not exist: {texture}; run texture stage explicitly")
            texture = variant_textures[0]
        elif not texture.is_file():
            raise ValueError(f"Texture variant does not exist: {texture}; run texture stage explicitly")
    if kind == "png":
        if include or exclude or animations is not None:
            raise ValueError("PNG export copies an atlas; part/animation filters apply to model exports")
        if texture:
            payload = texture.read_bytes()
        elif document.get("textures"):
            record = document["textures"][0]
            if record.get("source", "").startswith("data:image/"):
                payload = base64.b64decode(record["source"].split(",", 1)[1], validate=True)
            else:
                reference = record.get("relative_path") or record.get("path")
                if not reference:
                    raise ValueError("Active BBModel texture has no file reference")
                path = (context.model.parent / reference).resolve()
                if not path.is_relative_to(context.project):
                    raise ValueError("Active texture leaves project")
                payload = path.read_bytes()
        else:
            payload = context.texture.read_bytes()
        import io
        from PIL import Image
        with Image.open(io.BytesIO(payload)) as image:
            if image.format != "PNG":
                raise ValueError("PNG export requires a PNG source")
            image.verify()
    else:
        document = selected_document(document, include=include, exclude=exclude, animations=animations)
        if kind == "bbmodel":
            for texture_info in document.get("textures", []):
                source = texture_info.get("relative_path")
                if source:
                    path = (context.model.parent / source).resolve()
                    if not path.is_relative_to(context.project):
                        raise ValueError("Texture leaves project")
                    texture_info["relative_path"] = Path(os.path.relpath(path, destination.parent)).as_posix()
            if texture:
                if variant_textures is not None:
                    current_list = document.get("textures", [])
                    document["textures"] = [
                        {
                            **(current_list[idx] if idx < len(current_list) else {}),
                            "id": str(idx),
                            "relative_path": Path(os.path.relpath(v_path, destination.parent)).as_posix(),
                            "path": str(v_path),
                            "name": v_path.name,
                            "width": slot["width"],
                            "height": slot["height"],
                            "uv_width": slot["width"],
                            "uv_height": slot["height"],
                        }
                        for idx, (slot, v_path) in enumerate(zip(packed_slots, variant_textures))
                    ]
                    for tex_entry in document["textures"]:
                        tex_entry.pop("source", None)
                elif len(document.get("textures", [])) > 1:
                    raise ValueError("A single texture variant cannot replace multiple native atlas materials")
                else:
                    current = document.get("textures", [{}])[0]
                    document["textures"] = [{**current, "id": "0", "relative_path": Path(os.path.relpath(texture, destination.parent)).as_posix(), "path": str(texture), "name": texture.name}]
                    document["textures"][0].pop("source", None)
                if False:
                    raise ValueError("A single texture variant cannot replace multiple native atlas materials")
                    if False:
                        current = document.get("textures", [{}])[0]
                    if False:
                        document["textures"] = [{**current, "id": "0", "relative_path": Path(os.path.relpath(texture, destination.parent)).as_posix(), "path": str(texture), "name": texture.name}]
                    if False:
                        document["textures"][0].pop("source", None)
            payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        else:
            payload = GLBWriter(document, texture=variant_textures if variant_textures is not None else texture, scope=context.project, scale=scale, fps=fps,
                                texture_filter=context.texture_filter).build(context.model)
    if context.model.read_bytes() != original:
        raise ValueError("BBModel changed during export; retry with the new document")
    return context, destination, kind, payload, original, variant


def _render_product(prepared, temp):
    context, destination, kind, payload, original, variant = prepared
    temp.write_bytes(payload)
    if context.model.read_bytes() != original:
        raise ValueError("BBModel changed during export; source was not overwritten")


def _publish_product(prepared, temp, overwrite):
    context, destination, kind, payload, original, variant = prepared
    if context.model.read_bytes() != original:
        raise ValueError("BBModel changed during export; source was not overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        os.replace(temp, destination)
    else:
        # Hard link publishes without replacing a concurrently created output.
        os.link(temp, destination)
        temp.unlink()
    return {"status": "pass", "output": str(destination), "format": kind, "asset": context.asset_id, "variant": variant}


def asset_export(target, *, output, format=None, variant=None, include=(), exclude=(),
                 animations=None, overwrite=False, scale=1/16, fps=60):
    prepared = _prepare_export(target, output=output, format=format, variant=variant, include=include,
                               exclude=exclude, animations=animations, overwrite=overwrite, scale=scale, fps=fps)
    destination = prepared[1]
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix=destination.suffix)
    os.close(fd)
    temp = Path(temporary)
    try:
        temp.unlink()
        _render_product(prepared, temp)
        return _publish_product(prepared, temp, overwrite)
    finally:
        temp.unlink(missing_ok=True)


def export_targets(target, configuration=None, *, targets=(), overwrite=False):
    context = resolve_asset(target)
    path = inside(context.project, configuration) if configuration else context.scripts / "exports.json"
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("targets"), list):
        raise ValueError("Export configuration requires a targets list")
    jobs = config["targets"]
    allowed = {"id", "source_asset", "format", "output", "texture_variant", "include", "exclude", "animations", "scale", "fps", "runtime_role"}
    for job in jobs:
        if not isinstance(job, dict) or not isinstance(job.get("id"), str) or not job["id"]:
            raise ValueError("Each export target requires a nonempty id")
        if set(job)-allowed:
            raise ValueError(f"Unknown export target fields: {sorted(set(job)-allowed)}")
        if job.get("source_asset", context.asset_id) != context.asset_id:
            raise ValueError("Targets must use the explicitly selected source asset")
    ids = [job["id"] for job in jobs]
    if len(ids) != len(set(ids)) or set(targets)-set(ids):
        raise ValueError("Duplicate or unknown export target ids")
    jobs = [job for job in jobs if not targets or job["id"] in targets]
    if not jobs:
        raise ValueError("No export targets selected")
    defaults = [job for job in config.get("targets", []) if job.get("runtime_role") == "default"]
    if len(defaults) > 1:
        raise ValueError("Only one export target per source asset may be the runtime default")
    destinations = [output_path(context, job["output"]) for job in jobs]
    if len(destinations) != len(set(destinations)):
        raise ValueError("Export targets must have distinct destinations")
    for destination in destinations:
        if destination.exists() and not overwrite:
            raise FileExistsError(f"Output exists: {destination}")
    # Validate every payload and perform all conversions before publishing products.
    prepared = [
        _prepare_export(target, output=job["output"], format=job.get("format"), variant=job.get("texture_variant"),
            include=job.get("include", ()), exclude=job.get("exclude", ()), animations=job.get("animations"),
            overwrite=overwrite, scale=job.get("scale", 1/16), fps=job.get("fps", 60)) for job in jobs]
    reports = []
    assets_dir = context.project / "assets"
    assets_dir.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=assets_dir, prefix=".export-") as staging:
        staged = [Path(staging) / f"{index}.{item[2]}" for index, item in enumerate(prepared)]
        for item, temporary in zip(prepared, staged):
            _render_product(item, temporary)
        for item in prepared:
            if item[0].model.read_bytes() != item[4]:
                raise ValueError("BBModel changed while preparing export batch; no products published")
        for job, item, temporary in zip(jobs, prepared, staged):
            try:
                report = _publish_product(item, temporary, overwrite)
            except (OSError, ValueError) as exc:
                raise RuntimeError(f"Export publication failed after {len(reports)} products: {exc}") from exc
            reports.append({"id": job["id"], "runtime_role": job.get("runtime_role"), **report})
    return {"status": "pass", "targets": reports}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?")
    parser.add_argument("--output", help="Destination relative to project assets/")
    parser.add_argument("--format", choices=("glb", "png", "bbmodel"))
    parser.add_argument("--variant")
    parser.add_argument("--include", action="append", default=[], help="Group/element UUID, name or hierarchy path; repeatable")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--animations", help="Comma-separated clips; an empty string exports no clips")
    parser.add_argument("--config", help="Target JSON path relative to project (default: asset recipe directory exports.json)")
    parser.add_argument("--target", action="append", default=[])
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--scale", type=float, default=1/16)
    parser.add_argument("--fps", type=float, default=60)
    parser.add_argument("--capabilities", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.capabilities:
            report = {"formats": ["glb", "png", "bbmodel"]}
        elif not args.project:
            parser.error("Project is required")
        elif args.output:
            report = asset_export(args.project, output=args.output, format=args.format, variant=args.variant,
                include=args.include, exclude=args.exclude, animations=args.animations.split(",") if args.animations else ([] if args.animations == "" else None),
                overwrite=args.overwrite, scale=args.scale, fps=args.fps)
        else:
            report = export_targets(args.project, args.config, targets=args.target, overwrite=args.overwrite)
    except (ValueError, OSError, KeyError, RuntimeError) as exc:
        report = {"status": "fail", "error": str(exc)}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if report.get("status") == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
