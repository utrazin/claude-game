"""Create a project (recipes included) from a .bbmodel that was not made by a recipe."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.edit_diff import compare
from Tools.recipe_emit import build_scene, describe, emit
from lib.recipe_capture import capture_recipe
from Tools._resolve import resolve_asset

HEADER = '''"""{title} recipe imported from {source}.

Every part is written out explicitly: geometry, bones and weights copied from the file, so this
recipe rebuilds the imported model exactly. Replace parts with constructors whenever you like.
UVs, textures and animations are rebuilt by their own stages.
"""
from __future__ import annotations

from pathlib import Path
import sys

for _root in Path(__file__).resolve().parents:
    if (_root / "Tools" / "__init__.py").is_file():
        sys.path.insert(0, str(_root))
        break
from Tools.recipe_context import recipe_paths

'''

MODEL_TEMPLATE = HEADER + '''from lib import ModelBuilder

ASSET_BUILD_GEOMETRY = "manual"


def build_{ident}_model() -> ModelBuilder:
    # check_coplanar and integer dimensions are off: the file was not authored under the builder's rules.
    builder = ModelBuilder({name!r}, modeling_mode={mode!r}, check_coplanar=False, require_integer_dimensions=False)
{body}
    return builder


def main():
    model_path = recipe_paths(__file__).model
    build_{ident}_model().export_bbmodel(model_path)
    print("[model] Exported to", model_path)


if __name__ == "__main__":
    main()
'''

ANIMATION_TEMPLATE = HEADER + '''from lib import AnimationEditor


def main():
    model_path = recipe_paths(__file__).model
    editor = AnimationEditor.from_bbmodel(model_path)
{body}
    editor.save()
    print("[animation] saved to", model_path)


if __name__ == "__main__":
    main()
'''


def _fail(message, **extra):
    return {"status": "fail", "issues": [message], "skipped": [], "differences": [], **extra}


def _verify(script, model_path, scene, clips):
    try:
        capture = capture_recipe(script)
        gen = build_scene(capture.documents[model_path.resolve()], clips=clips)
    except (Exception, SystemExit) as exc:
        return [f"{script.name} does not run: {type(exc).__name__}: {exc}"]
    changed, new, removed = compare(gen, scene)
    return ([f"{k[0]} {k[1]}: " + "; ".join(describe(k[0], gen.entities[k].sig, scene.entities[k].sig))
             for k in changed]
            + [f"{k[0]} {k[1]} is in the file but the recipe does not build it" for k in new]
            + [f"{k[0]} {k[1]} is built by the recipe but is not in the file" for k in removed])


def import_bbmodel(source, project, *, force=False):
    source = Path(source)
    doc = json.loads(source.read_text(encoding="utf-8"))
    model_format = doc.get("meta", {}).get("model_format", "free")
    if model_format != "free":
        return _fail(f"model_format is {model_format!r}: in Blockbench use File > Convert Project > Free Model, then import again")
    if "#" in str(project) or (Path(project) / "project.json").exists():
        context = resolve_asset(project)
        project, scripts, model_path = context.directory, context.scripts, context.model
    else:
        from Tools.project_manifest import identifier, write_project
        root = Path(project).resolve()
        asset_id = identifier(root.name)
        write_project(root, {"schema": 1, "id": asset_id, "name": root.name, "assets": {
            asset_id: {"name": asset_id, "model": f"assets/{asset_id}/model.bbmodel",
                       "scripts": f"scripts/{asset_id}", "variants": {}}}})
        context = resolve_asset(f"{root}#{asset_id}")
        project, scripts, model_path = context.directory, context.scripts, context.model
    taken = [p for p in (scripts / "generate_model.py", scripts / "generate_animation.py", model_path)
             if p.exists() and p.resolve() != source.resolve()]
    if taken and not force:
        return _fail("already exists: " + ", ".join(str(p) for p in taken) + " (use --force to overwrite)")
    try:
        scene = build_scene(doc)
    except ValueError as exc:
        return _fail(f"the builder cannot read this file: {exc}")
    backup = None
    if taken:   # only reachable with --force: keep what is about to be overwritten
        backup = context.project / "history" / f"import_{datetime.now():%Y%m%d-%H%M%S}"
        backup.mkdir(parents=True, exist_ok=True)
        for p in taken:
            shutil.copyfile(p, backup / p.name)
    mode = scene.mode
    code, blockers = emit(scene, list(scene.entities), mode)
    name = doc.get("name") or project.name
    ident = re.sub(r"\W+", "_", project.name).strip("_").lower() or "model"
    scripts.mkdir(parents=True, exist_ok=True)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != model_path.resolve():
        shutil.copyfile(source, model_path)
    if not (context.project / "source.bbmodel").exists():
        shutil.copyfile(source, context.project / "source.bbmodel")
    model_script = scripts / "generate_model.py"
    model_script.write_text(MODEL_TEMPLATE.format(
        title="Model", source=source.name, ident=ident, name=name, mode=mode,
        body=textwrap.indent(code, "    ")), encoding="utf-8")
    report = {"status": "pass", "issues": [], "skipped": blockers, "differences": [],
              "notes": list(scene.notes), "written": [str(model_script)],
              "backup": str(backup) if backup else None}
    report["differences"] += _verify(model_script, model_path, scene, clips=False)
    clips = build_scene(doc, clips=True)
    if clips.entities:
        clip_code, clip_blockers = emit(clips, list(clips.entities), mode)
        report["skipped"] += clip_blockers
        if clip_code:
            animation_script = scripts / "generate_animation.py"
            animation_script.write_text(ANIMATION_TEMPLATE.format(
                title="Animation", source=source.name,
                body=textwrap.indent(clip_code, "    ")), encoding="utf-8")
            report["written"].append(str(animation_script))
            report["differences"] += _verify(animation_script, model_path, clips, clips=True)
    if report["differences"] and any("does not run" in d for d in report["differences"]):
        report["status"] = "fail"
        report["issues"] = [d for d in report["differences"] if "does not run" in d]
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import a .bbmodel as a project with generate_model.py (and clips).")
    parser.add_argument("source", help="path to the .bbmodel to import")
    parser.add_argument("project", help="projects/<name> to create")
    parser.add_argument("--asset", help="Registered destination asset id")
    parser.add_argument("--force", action="store_true", help="replace an existing model and recipes (backup in history/)")
    args = parser.parse_args(argv)
    target = f"{args.project}#{args.asset}" if args.asset else args.project
    report = import_bbmodel(args.source, target, force=args.force)
    if report.get("backup"):
        print(f"[import] the files it overwrote were copied to {report['backup']}")
    for path in report.get("written", []):
        print(f"[import] wrote {path}")
    for line in report["issues"]:
        print(f"[import] FAIL {line}", file=sys.stderr)
    for line in report.get("notes", []):
        print(f"[import] NOTE {line}")
    for line in report["skipped"]:
        print(f"[import] SKIPPED {line}")
    for line in report["differences"]:
        print(f"[import] DIFF {line}")
    if report["status"] == "pass":
        verdict = "verified identical" if not report["differences"] and not report["skipped"] else "written with the notes above"
        print(f"[import] PASS {verdict}. Continue from the imported BBModel with only the requested stages. "
              "The model recipe is marked manual for the build shortcut. Explicit model regeneration replaces "
              "geometry, UVs, clips and texture registration; imported pixels remain in source.bbmodel.")
    return 0 if report["status"] == "pass" and not report["differences"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
