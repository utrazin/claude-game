"""Context for saved recipes, supplied by the CLI or discovered from project.json."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from Tools._resolve import resolve_asset
from Tools.project_manifest import find_project, inside, load_project

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class RecipePaths:
    project: Path
    asset: Path
    model: Path
    texture: Path
    variant: str
    register_texture: bool = True

    def texture_for(self, slot: str = "default") -> Path:
        """Path for texture slot ``slot`` (``self.texture`` for ``'default'``, else ``<stem>_<slot>.png``)."""
        if not slot or slot == "default":
            return self.texture
        return self.texture.with_name(f"{self.texture.stem}_{slot}{self.texture.suffix}")

    def theme(self):
        """The project's theme (``projects/<p>/theme.py``): its visual tokens (``Tools.TexturePainter.theme``)."""
        from Tools.TexturePainter.theme import load_theme
        return load_theme(self.project)


def recipe_paths(script: str | Path) -> RecipePaths:
    """Resolve recipe file paths for a saved recipe file.

    Inside a CLI run, paths come from the ``FORGE_*`` environment; otherwise
    the registered asset owning ``script`` is discovered in ``project.json``.
    Recipes outside a registered project are rejected.
    """
    script = Path(script).resolve()
    if os.environ.get("FORGE_MODEL"):
        return RecipePaths(Path(os.environ["FORGE_PROJECT"]), Path(os.environ["FORGE_ASSET_DIR"]),
                           Path(os.environ["FORGE_MODEL"]), Path(os.environ["FORGE_TEXTURE"]),
                           os.environ.get("FORGE_VARIANT", "default"),
                           os.environ.get("FORGE_REGISTER_TEXTURE", "1") == "1")
    root = find_project(script)
    if not root:
        raise ValueError(f"Recipe is not inside a registered project: {script}")
    records = load_project(root)["assets"]
    for key, asset in sorted(records.items(), key=lambda item: len(inside(root, item[1]["scripts"]).parts), reverse=True):
        if inside(root, asset["scripts"]) == script.parent or script.is_relative_to(inside(root, asset["scripts"])):
            context = resolve_asset(f"{root}#{key}")
            return RecipePaths(root, context.directory, context.model, context.texture,
                               asset.get("default_variant", "default"))
    raise ValueError(f"Recipe is not registered in project.json: {script}")


def recipe_environment(target, *, texture=None, variant=None, register_texture=True) -> dict:
    """Build the ``FORGE_*`` environment a CLI uses to run a saved recipe for one asset target."""
    context = resolve_asset(target)
    return dict(os.environ, PYTHONPATH=str(REPO_ROOT), FORGE_REPO=str(REPO_ROOT),
                FORGE_PROJECT=str(context.project), FORGE_ASSET_DIR=str(context.directory),
                FORGE_MODEL=str(context.model), FORGE_TEXTURE=str(texture or context.texture),
                FORGE_VARIANT=str(variant or context.record.get("default_variant", "default")),
                FORGE_REGISTER_TEXTURE="1" if register_texture else "0")
