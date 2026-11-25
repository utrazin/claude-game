"""Register named texture alternatives on one asset's existing UV atlas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from Tools._resolve import resolve_asset
from Tools.project_manifest import identifier, inside, load_project, write_project, project_lock


def register_variant(target, name, *, output=None, recipe=None, default=False):
    context = resolve_asset(target)
    with project_lock(context.project):
        return _register_variant(target, name, output=output, recipe=recipe, default=default)


def _register_variant(target, name, *, output=None, recipe=None, default=False):
    context = resolve_asset(target)
    name = identifier(name)
    manifest = load_project(context.project)
    asset = manifest["assets"][context.asset_id]
    if output is None:
        output = Path(f"{context.model.parent.relative_to(context.project).as_posix()}/textures/{name}.png")
        output = output.relative_to("assets").as_posix()
    path = inside(context.project / "assets", output)
    if path.suffix.lower() != ".png":
        raise ValueError("A texture variant must be a PNG")
    if path == context.model or path.is_relative_to(context.scripts):
        raise ValueError("A variant cannot replace source recipes or BBModel")
    record = {"path": path.relative_to(context.project).as_posix()}
    if recipe:
        record["recipe"] = inside(context.project, recipe).relative_to(context.project).as_posix()
    previous = asset.setdefault("variants", {}).get(name)
    if previous and previous != record:
        raise ValueError(f"Variant {name} is already registered differently")
    if any(key != name and value["path"] == record["path"] for key, value in asset["variants"].items()):
        raise ValueError("Texture variants must have distinct file paths")
    asset["variants"][name] = record
    if default:
        asset["default_variant"] = name
    write_project(context.project, manifest)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("name")
    parser.add_argument("--output", help="Path relative to assets/")
    parser.add_argument("--recipe", help="Recipe relative to the project")
    parser.add_argument("--default", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(register_variant(args.project, args.name, output=args.output,
                                      recipe=args.recipe, default=args.default), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
