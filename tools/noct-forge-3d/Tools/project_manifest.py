"""Project identities and explicit paths; contains no stage freshness state."""
from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

MANIFEST = "project.json"
# How viewers and GLB samplers filter an asset's texture: nearest keeps texels crisp, linear smooths.
TEXTURE_FILTERS = ("nearest", "linear")


def identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError("Identifiers must contain letters, digits, underscores or hyphens")
    if value.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("Reserved Windows identifier")
    return value


def inside(root: Path, relative: str | Path) -> Path:
    """Resolve and constrain a relative path, including junction/symlink traversal."""
    relative = Path(relative)
    if relative.is_absolute() or relative.drive or ".." in relative.parts or not relative.parts:
        raise ValueError(f"Expected a relative path inside {root}: {relative}")
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"Path leaves allowed directory: {relative}")
    return target


def find_project(path: Path) -> Path | None:
    path = path.resolve()
    start = path if path.is_dir() else path.parent
    for candidate in (start, *start.parents):
        if (candidate / MANIFEST).is_file():
            return candidate
    return None


def load_project(root: str | Path) -> dict:
    root = Path(root).resolve()
    data = json.loads((root / MANIFEST).read_text(encoding="utf-8-sig"))   # tolerate a BOM (PowerShell writes one)
    validate_project(root, data)
    return data


def validate_project(root: Path, data: dict) -> None:
    """Validate identities/paths without reading recipes or requiring built artifacts."""
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("assets"), dict):
        raise ValueError("Expected project.json with schema=1 and an assets object")
    identifier(data.get("id"))
    seen_models, seen_scripts, seen_textures = set(), set(), set()
    for key, asset in data["assets"].items():
        identifier(key)
        if not isinstance(asset, dict):
            raise ValueError(f"Invalid asset record: {key}")
        model = inside(root, asset["model"])
        scripts = inside(root, asset["scripts"])
        if model.suffix.lower() != ".bbmodel":
            raise ValueError(f"Asset {key}: model must end with .bbmodel")
        if model in seen_models or scripts in seen_scripts:
            raise ValueError("Assets must have distinct source models and recipe directories")
        seen_models.add(model)
        seen_scripts.add(scripts)
        if not model.is_relative_to((root / "assets").resolve()):
            raise ValueError(f"Asset {key}: source model must be under assets/")
        if not isinstance(asset.get("variants", {}), dict):
            raise ValueError(f"Asset {key}: variants must be an object")
        for variant, record in asset.get("variants", {}).items():
            identifier(variant)
            if not isinstance(record, dict):
                raise ValueError(f"Invalid variant record: {key}/{variant}")
            texture = inside(root, record["path"])
            if texture.suffix.lower() != ".png":
                raise ValueError("Texture variants must be PNGs")
            if not texture.is_relative_to((root / "assets").resolve()):
                raise ValueError("Texture variants must be under assets/")
            if record.get("recipe"):
                inside(root, record["recipe"])
            if texture in seen_textures:
                raise ValueError("Registered texture variants must have distinct file paths across assets")
            seen_textures.add(texture)
        if asset.get("texture_filter", "nearest") not in TEXTURE_FILTERS:
            raise ValueError(f"Asset {key}: texture_filter must be nearest (pixel art) or linear (painted)")
        from Tools.TexturePainter.render_mode import from_record
        try:
            from_record(asset)
        except ValueError as exc:
            raise ValueError(f"Asset {key}: {exc}") from exc
        twin = asset.get("twin_of")
        if twin is not None and (twin == key or twin not in data["assets"]
                                 or data["assets"][twin].get("twin_of") is not None):
            raise ValueError(f"Asset {key}: twin_of must name another asset that is not itself a twin")
        default = asset.get("default_variant")
        if default is not None and default not in asset.get("variants", {}):
            raise ValueError(f"Asset {key}: default_variant is not registered")
    if any(path.is_relative_to(directory) for path in seen_models | seen_textures for directory in seen_scripts):
        raise ValueError("Source model/texture paths cannot be inside a recipe directory")


@contextmanager
def project_lock(root: str | Path):
    """Nonblocking OS lock for a complete registration transaction, not stage state.

    The OS releases it after process termination, so a leftover file is not a lock.
    Cooperating writers reject contention before reading/modifying the manifest.
    """
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stream = (root / ".forge-project.lock").open("a+b")
    acquired = False
    try:
        if stream.seek(0, os.SEEK_END) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise ValueError("Another project registration is running; retry after it completes") from exc
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def write_project(root: str | Path, data: dict) -> Path:
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    validate_project(root, data)
    target = root / MANIFEST
    fd, temporary = tempfile.mkstemp(dir=root, suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target
