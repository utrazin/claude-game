"""Scaffold canonical generator recipes for a new or existing asset project.

Usage:
  py -3.12 -m Tools.asset_init projects/<name> [--mode free|box|mixed] [--force]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_FREE_GEOMETRY = '''    # EXAMPLE ONLY - replace this torso with your own shapes (delete it if the asset is not a character):
    builder.add_capsule("torso", "body", radius=2.0, height=5.0, segments=6, rings=1, axis="Y")
    # builder.stack_on("head", "torso", axis="+Y", offset=0.2)
    # builder.mirror("arm_L")   # creates arm_R (a name with a side suffix mirrors automatically)'''

_BOX_GEOMETRY = '''    # EXAMPLE ONLY - replace this torso with your own shapes (delete it if the asset is not a character):
    builder.add_box("torso", "body", size=(6, 8, 4), at=(0, 4, 0))
    # builder.stack_on("head", "torso", axis="+Y", offset=0.0)'''

_MIXED_GEOMETRY = '''    # EXAMPLE ONLY - replace these shapes with your own (delete them if the asset is not a character):
    builder.add_box("torso", "body", size=(6, 8, 4), at=(0, 4, 0))
    builder.add_capsule("limb", "body", radius=1.0, height=4.0, segments=6, rings=1, axis="Y")'''


def _clean_identifier(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if cleaned and cleaned[0].isdigit():
        cleaned = f"asset_{cleaned}"
    return cleaned or "asset"


def generate_model_template(asset_name: str, mode: str = "free") -> str:
    clean_name = _clean_identifier(asset_name)
    if mode == "box":
        geo = _BOX_GEOMETRY
    elif mode == "mixed":
        geo = _MIXED_GEOMETRY
    else:
        geo = _FREE_GEOMETRY

    req_int = ", require_integer_dimensions=False" if mode in ("free", "mixed") else ""
    return f'''"""Model authoring recipe for {asset_name}."""
from __future__ import annotations

from pathlib import Path
import sys

for _root in Path(__file__).resolve().parents:
    if (_root / "Tools" / "__init__.py").is_file():
        sys.path.insert(0, str(_root))
        break

from lib.model_builder import ModelBuilder
from lib.geometry_types import Placement
from Tools.recipe_context import recipe_paths

ASSET_BUILD_GEOMETRY = "recipe"


def build_{clean_name}_model() -> ModelBuilder:
    builder = ModelBuilder("{asset_name}", modeling_mode="{"free" if mode == "mixed" else mode}"{req_int})

    # 1. Define group hierarchy with functional pivots
    builder.add_group("root") \\
           .add_transform_group("body", "root", pivot=(0, 0, 0))

    # 2. Add geometry ({mode} modeling)
{geo}

    return builder


def main():
    model_path = recipe_paths(__file__).model
    builder = build_{clean_name}_model()
    builder.export_bbmodel(model_path)
    print(f"[model] Exported to {{model_path}}")


if __name__ == "__main__":
    main()
'''


def generate_texture_template(asset_name: str) -> str:
    return f'''"""Pixel-art texture authoring recipe for {asset_name}."""
from __future__ import annotations

from pathlib import Path
import sys

for _root in Path(__file__).resolve().parents:
    if (_root / "Tools" / "__init__.py").is_file():
        sys.path.insert(0, str(_root))
        break

from Tools.TexturePainter import TexturePainter
from Tools.recipe_context import recipe_paths


def paint():
    paths = recipe_paths(__file__)
    model_path, texture_path = paths.model, paths.texture

    painter = TexturePainter.from_bbmodel(model_path)

    # 1. Base solid coat
    painter.fill_all((70, 75, 85, 255))

    # 2. Geometric crease shadows
    creases = painter.creases(max_internal_angle=100)
    creases.paint(lambda hit: (20, 20, 30, 160), blend="multiply")

    # 3. Save and register texture (edge_dilation=1 fills 1px island padding)
    painter.save(texture_path, edge_dilation=1)
    print(f"[texture] Saved to {{texture_path}}")


if __name__ == "__main__":
    paint()
'''


def generate_animation_template(asset_name: str) -> str:
    return f'''"""Animation authoring recipe for {asset_name}."""
from __future__ import annotations

from pathlib import Path
import sys

for _root in Path(__file__).resolve().parents:
    if (_root / "Tools" / "__init__.py").is_file():
        sys.path.insert(0, str(_root))
        break

from lib.animation import AnimationEditor
from Tools.recipe_context import recipe_paths


def animate():
    model_path = recipe_paths(__file__).model

    editor = AnimationEditor.from_bbmodel(model_path)

    # 1. Idle loop
    idle = editor.animation("idle", duration=2.0, loop=True)
    if "body" in editor.group_names:
        idle.group("body").key(0.0, position=(0, 0, 0)) \\
                          .key(1.0, position=(0, -0.2, 0), interpolation="catmullrom") \\
                          .key(2.0, position=(0, 0, 0), interpolation="catmullrom")

    editor.save()
    print(f"[animation] Saved clips to {{model_path}}")


if __name__ == "__main__":
    animate()
'''


def init_project(
    project_target: str | Path,
    *,
    mode: str = "free",
    animation: bool = False,
    force: bool = False,
    asset_id: str | None = None,
) -> dict[str, str]:
    """Create directory structure and canonical recipe files for a project."""
    target_path = Path(project_target)
    if not target_path.is_absolute():
        if not str(project_target).startswith("projects"):
            target_path = REPO_ROOT / "projects" / target_path
        else:
            target_path = REPO_ROOT / target_path

    from Tools.project_manifest import project_lock
    target_path = target_path.resolve()
    with project_lock(target_path):
        return _init_registered_asset(target_path, mode=mode, animation=animation, force=force, asset_id=asset_id)


def _init_registered_asset(target_path, *, mode, animation, force, asset_id):
    from Tools.project_manifest import identifier, load_project, write_project, inside
    if not (target_path / "project.json").exists() and ((target_path / "model.bbmodel").exists() or (target_path / "scripts/generate_model.py").exists()):
        raise ValueError("Directory holds model files but no project.json; move them into a registered project instead of initializing over them")
    if (target_path / "project.json").exists():
        manifest = load_project(target_path)
        if asset_id is None:
            if len(manifest["assets"]) != 1:
                raise ValueError("Select --asset explicitly for a project with multiple assets")
            asset_id = next(iter(manifest["assets"]))
    else:
        manifest = {"schema": 1, "id": identifier(target_path.name), "name": target_path.name, "assets": {}}
    asset_name = identifier(asset_id or target_path.name)
    if asset_name not in manifest["assets"]:
        manifest["assets"][asset_name] = {
            "name": asset_name, "model": f"assets/{asset_name}/model.bbmodel",
            "scripts": f"scripts/{asset_name}", "variants": {
                "default": {"path": f"assets/{asset_name}/texture.png"}}, "default_variant": "default"}
    record = manifest["assets"][asset_name]
    scripts_dir = inside(target_path, record["scripts"])
    scripts_dir.mkdir(parents=True, exist_ok=True)
    inside(target_path, record["model"]).parent.mkdir(parents=True, exist_ok=True)
    (target_path / "references").mkdir(exist_ok=True)
    write_project(target_path, manifest)

    model_recipe = scripts_dir / "generate_model.py"
    texture_recipe = scripts_dir / "generate_texture.py"
    anim_recipe = scripts_dir / "generate_animation.py"

    created = {}

    if not model_recipe.exists() or force:
        model_recipe.write_text(generate_model_template(asset_name, mode), encoding="utf-8")
        created["generate_model"] = str(model_recipe)
    else:
        created["generate_model"] = "EXISTS"

    if not texture_recipe.exists() or force:
        texture_recipe.write_text(generate_texture_template(asset_name), encoding="utf-8")
        created["generate_texture"] = str(texture_recipe)
    else:
        created["generate_texture"] = "EXISTS"

    if animation:
        if not anim_recipe.exists() or force:
            anim_recipe.write_text(generate_animation_template(asset_name), encoding="utf-8")
            created["generate_animation"] = str(anim_recipe)
        else:
            created["generate_animation"] = "EXISTS"

    export_config = scripts_dir / "exports.json"
    if not export_config.exists():
        export_config.write_text(json.dumps({"targets": [{"id": "default", "format": "glb",
            "output": f"{asset_name}/exports/{asset_name}.glb", "runtime_role": "default"}]}, indent=2)+"\n", encoding="utf-8")
        created["exports"] = str(export_config)

    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold canonical Python recipes for a NoctAssetForge3D asset."
    )
    parser.add_argument("project", help="Project path (e.g. projects/<name> or <name>)")
    parser.add_argument("--asset", help="Asset identifier within the project")
    parser.add_argument(
        "--mode", choices=["free", "box", "mixed"], default="free",
        help="Initial modeling mode paradigm (default: free)",
    )
    parser.add_argument("--animation", action="store_true", help="Scaffold generate_animation.py with example idle clip")
    parser.add_argument("--force", action="store_true", help="Overwrite existing recipe files")
    args = parser.parse_args(argv)

    results = init_project(args.project, mode=args.mode, animation=args.animation, force=args.force, asset_id=args.asset)

    project_str = args.project
    print(f"[init] Project scaffolded for '{project_str}' (mode: {args.mode}):")
    for key, path_or_status in results.items():
        if path_or_status == "EXISTS":
            print(f"  - scripts/{key}.py: already exists (skipped, use --force to overwrite)")
        else:
            try:
                rel = Path(path_or_status).relative_to(REPO_ROOT)
            except ValueError:
                rel = Path(path_or_status)
            print(f"  - {rel}: created")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
