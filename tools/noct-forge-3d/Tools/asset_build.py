"""Optional shortcut for explicitly selected, independent asset stages."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

from Tools._resolve import resolve_model_target, resolve_recipe
from Tools.asset_status import asset_status, print_status
from Tools.model_export import model_export
from Tools.texture_export import texture_export
from Tools.animation_export import animation_export
from Tools.uv_packer import BoxUVPacker, run_uv_recipe, uv_recipe

STAGES = ("model", "uv", "texture", "animation")


def geometry_policy(recipe: Path) -> str:
    """Inspect a literal without importing or executing arbitrary recipe code."""
    if not recipe.exists():
        return "recipe"
    for node in ast.parse(recipe.read_text(encoding="utf-8-sig"), filename=str(recipe)).body:
        targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        if any(isinstance(target, ast.Name) and target.id == "ASSET_BUILD_GEOMETRY" for target in targets):
            try:
                policy = ast.literal_eval(node.value)
            except (ValueError, TypeError) as exc:
                raise ValueError("ASSET_BUILD_GEOMETRY must be the literal 'recipe' or 'manual'") from exc
            if policy not in ("recipe", "manual"):
                raise ValueError("ASSET_BUILD_GEOMETRY must be 'recipe' or 'manual'")
            return policy
    return "recipe"


def asset_build(project: str | Path, *, stages: str | list[str] | tuple[str, ...] = (),
                recipe_model=None, recipe_texture=None, recipe_animation=None,
                checks="standard", lint=False) -> dict[str, Any]:
    """Execute only selected stages; never infer execution from status or recipes."""
    selected = stages.split(",") if isinstance(stages, str) else list(stages)
    selected = [item.strip() for item in selected]
    if not selected or any(stage not in STAGES for stage in selected):
        raise ValueError(f"Select stages explicitly: --stages {','.join(STAGES)}")
    project_dir, model = resolve_model_target(project)
    steps, skipped = [], []
    model_recipe = resolve_recipe(project, "model", recipe_model)
    for stage in STAGES:
        if stage not in selected:
            continue
        if stage == "model" and geometry_policy(model_recipe) == "manual":
            skipped.append({"stage": stage, "reason": "ASSET_BUILD_GEOMETRY=manual"})
            if not model.is_file():
                return {"status": "fail", "stage": "model", "steps": steps, "skipped": skipped,
                        "errors": [{"stage": "model", "report": {"status": "fail", "error": "Manual BBModel is missing; restore/import it explicitly"}}],
                        "final_status": asset_status(project)}
            continue
        steps.append(stage)
        try:
            if stage == "model":
                report = model_export(project, recipe=model_recipe, checks=checks, lint=lint)
            elif stage == "uv" and uv_recipe(project) is not None:
                report = run_uv_recipe(project)
            elif stage == "uv":
                size, stats = BoxUVPacker.apply_to_bbmodel(model, island_padding=BoxUVPacker.remembered_options(model).get("island_padding", 1))
                report = {"status": "pass", "width": size.width, "height": size.height, **stats}
            elif stage == "texture":
                report = texture_export(project, recipe=recipe_texture)
            else:
                report = animation_export(project, recipe=recipe_animation)
        except Exception as exc:
            report = {"status": "fail", "error": str(exc)}
        if report["status"] != "pass":
            return {"status": "fail", "stage": stage, "steps": steps, "skipped": skipped,
                    "errors": [{"stage": stage, "report": report}], "final_status": asset_status(project)}
    return {"status": "pass", "steps": steps, "skipped": skipped, "final_status": asset_status(project)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--stages", required=True, help="Comma-separated explicit stages: model,uv,texture,animation")
    for stage in ("model", "texture", "animation"):
        parser.add_argument(f"--recipe-{stage}")
    parser.add_argument("--checks", choices=("geometry", "standard", "strict"), default="standard")
    parser.add_argument("--lint", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = asset_build(args.project, stages=args.stages, recipe_model=args.recipe_model,
                             recipe_texture=args.recipe_texture, recipe_animation=args.recipe_animation,
                             checks=args.checks, lint=args.lint)
    except Exception as exc:
        report = {"status": "fail", "error": str(exc)}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[build] {report['status'].upper()} executed={','.join(report.get('steps', [])) or 'none'}")
        if report.get("error"):
            print(report["error"])
        for error in report.get("errors", []):
            print(json.dumps(error, ensure_ascii=False))
        print_status(report.get("final_status", {}))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
