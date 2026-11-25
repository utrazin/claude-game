"""Shared path resolution for all Tools CLIs.

Every mutating CLI requires a registered project (``project.json``)::

  projects/<name>              (project directory, single asset)
  projects/<name>#<asset>      (explicit asset)
  projects/<name>/assets/<id>/model.bbmodel  (exact registered model)

Read-only viewers additionally accept an explicit ``.bbmodel`` file outside
any project via :func:`resolve_direct_model`; that file carries no asset
identity (no recipes, no variants). Unregistered directories are rejected:
register them with ``Tools.forge project init`` instead.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from Tools.project_manifest import find_project, inside, load_project


@dataclass(frozen=True)
class AssetContext:
    project: Path
    asset_id: str
    model: Path
    scripts: Path
    record: dict

    @property
    def directory(self):
        return self.model.parent

    @property
    def texture_filter(self):
        return self.record.get("texture_filter", "nearest")

    @property
    def texture(self):
        variant = self.record.get("default_variant")
        if variant:
            return inside(self.project, self.record["variants"][variant]["path"])
        return self.model.parent / "texture.png"


def resolve_asset(arg: str | Path, asset_id: str | None = None) -> AssetContext:
    raw = str(arg)
    if "#" in raw:
        raw, selected = raw.rsplit("#", 1)
        if asset_id and asset_id != selected:
            raise ValueError("Conflicting asset selectors")
        asset_id = selected
    path = Path(raw).resolve()
    root = find_project(path)
    if root:
        data = load_project(root)
        matches = [key for key, record in data["assets"].items()
                   if inside(root, record["model"]) == path or inside(root, record["model"]).parent == path
                   or inside(root, record["scripts"]) == path]
        if not asset_id:
            if len(matches) == 1:
                asset_id = matches[0]
            elif path == root and len(data["assets"]) == 1:
                asset_id = next(iter(data["assets"]))
            elif path.suffix.lower() != ".bbmodel":
                raise ValueError("Select an asset explicitly with project#asset-id or --asset; assets: " + ", ".join(data["assets"]))
        if asset_id:
            if asset_id not in data["assets"]:
                raise ValueError(f"Unknown asset {asset_id!r}")
            record = data["assets"][asset_id]
            return AssetContext(root, asset_id, inside(root, record["model"]), inside(root, record["scripts"]), record)
    if asset_id:
        raise ValueError("Asset selection requires a registered project.json")
    raise ValueError(f"Not a registered project asset: {arg} "
                     "(create one with `Tools.forge project init`)")


def resolve_direct_model(arg: str | Path) -> Path:
    """Return an explicit ``.bbmodel`` file for read-only viewers.

    No asset identity, no recipes, no variants: inspection only.
    """
    path = Path(str(arg).rsplit("#", 1)[0]).resolve()
    if path.is_file() and path.suffix.lower() == ".bbmodel":
        return path
    raise ValueError(f"Expected an existing .bbmodel file: {arg}")


def resolve_read_model(arg: str | Path) -> tuple[Path, Path]:
    """Read-only resolution: a registered asset, or an explicit ``.bbmodel`` file.

    Manifest errors stay precise: an explicit ``#asset`` selector never falls
    back to direct-file mode.
    """
    raw = str(arg)
    if "#" not in raw:
        path = Path(raw)
        if path.suffix.lower() == ".bbmodel" and path.exists():
            direct = path.resolve()
            if find_project(direct) is None:
                return direct.parent, direct
    context = resolve_asset(arg)
    return context.project, context.model


def resolve_model_target(arg: str | Path) -> tuple[Path, Path]:
    """Return (project_root, model_path) for a registered asset selector."""
    context = resolve_asset(arg)
    return context.project, context.model


def resolve_recipe(arg: str | Path, stage: str, override=None) -> Path:
    context = resolve_asset(arg)
    twin = context.record.get("twin_of")
    if twin and stage == "model":
        raise ValueError(f"{context.asset_id} is a twin of {twin}: its geometry is {twin}'s model; edit {twin}, then "
                         f"run forge asset twin {context.project.name} --asset {context.asset_id} --sync")
    if override is None:
        if twin:          # a twin paints and animates with its source's recipes
            return resolve_asset(context.project, twin).scripts / f"generate_{stage}.py"
        return context.scripts / f"generate_{stage}.py"
    path = Path(override)
    return path.resolve() if path.is_absolute() else (context.project / path).resolve()
