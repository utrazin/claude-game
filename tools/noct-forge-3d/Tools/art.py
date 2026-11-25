"""Art requests: ask an external producer (person, tool or agent) for images.

Only when the user explicitly asks for external art; painting normally stays in
the recipe. The project's ``art.json`` describes each image and where it is
delivered; it never says how the recipe uses it::

  {
    "schema": 2,
    "source": "../forge2d/projects/hero/assets",
    "requests": {
      "face": {
        "asset": "hero",
        "description": "Angry glowing eyes, small nose and scowl. Soft painted style, no pixel art; transparent background; ...",
        "pixels": [512, 320],
        "guide": {"element": "head", "side": "front", "points": {"eye_L": [-2.4, 26.5]}}
      }
    }
  }

Per request: ``asset`` (receives the image), ``description`` (everything the
producer must know: subject, style such as pixel art or painted or vector,
transparency, tiling, palette, limits), ``pixels`` (exact delivered size),
optional ``file`` (path inside ``source``, default ``<id>.png``) and optional
``guide`` (``element``, ``side``, ``points`` as [u, v] in that side's axes, element
units). Other keys are kept and ignored.

``guide`` renders the element as seen from the side at the requested size and
records the canvas mapping and point pixels. ``prompt`` prints one ready-to-send
message per request. ``pull`` copies delivered images of the right size from
``source`` to ``assets/<asset>/art/<id>.png``, where recipes read them with
``painter.art(id)``.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import warnings
from pathlib import Path

from PIL import Image

from Tools._resolve import AssetContext, resolve_asset
from Tools.project_manifest import find_project, identifier, load_project, project_lock

MANIFEST = "art.json"
SCHEMA = 2
GUIDE_OUTPUTS = ("image", "mapping", "points_px")


def manifest_path(project: Path) -> Path:
    return Path(project) / MANIFEST


def load(project: Path) -> dict:
    path = manifest_path(project)
    if not path.is_file():
        raise ValueError(f"No {MANIFEST} in {project}")
    data = json.loads(path.read_text(encoding="utf-8"))
    validate(project, data)
    return data


def validate(project: Path, data: dict) -> None:
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("requests"), dict):
        raise ValueError(f"{MANIFEST} needs schema={SCHEMA} and a requests object")
    if "source" in data and not isinstance(data["source"], str):
        raise ValueError(f"{MANIFEST}: source must be a path string")
    assets = load_project(project)["assets"]
    for key, request in data["requests"].items():
        identifier(key)
        where = f"{MANIFEST} request {key}"
        if not isinstance(request, dict) or request.get("asset") not in assets:
            raise ValueError(f"{where}: asset must be one of {', '.join(assets)}")
        description = request.get("description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{where}: description must describe the image, its style and limits")
        pixels = request.get("pixels")
        if (not isinstance(pixels, list) or len(pixels) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in pixels)):
            raise ValueError(f"{where}: pixels must be [width, height] positive integers")
        file = Path(request.get("file", f"{key}.png"))
        if file.is_absolute() or ".." in file.parts or file.suffix.lower() != ".png":
            raise ValueError(f"{where}: file must be a relative .png path inside source")
        guide = request.get("guide")
        if guide is not None:
            if not isinstance(guide, dict) or not isinstance(guide.get("element"), str):
                raise ValueError(f"{where}: guide needs an element")
            if not isinstance(guide.get("side", "front"), str):
                raise ValueError(f"{where}: guide side must be a string")
            points = guide.get("points", {})
            if not isinstance(points, dict) or not all(
                    isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)
                    for p in points.values()):
                raise ValueError(f"{where}: guide points must be named [u, v] model coordinates")


def deliver_path(context: AssetContext, key: str) -> Path:
    return context.directory / "art" / f"{key}.png"


def source_path(data: dict, key: str) -> Path:
    if not data.get("source"):
        raise ValueError(f"{MANIFEST} has no source yet; set it to the folder where images are delivered")
    return Path(data["source"]) / data["requests"][key].get("file", f"{key}.png")


def _relative(project: Path, path: Path) -> str:
    return path.relative_to(project).as_posix()


def _view(painter, element: str, side: str, size: tuple[int, int], atlas: Image.Image | None) -> Image.Image:
    """The element seen from ``side`` in decal space, colored by the current texture."""
    from Tools.TexturePainter.painter import decal_frame
    from Tools.TexturePainter.core.surface_sampling import _canvas_to_atlas

    _, direction, axes, flip_v = decal_frame(painter.direction_vectors, side)
    depth_axis = 3 - axes[0] - axes[1]
    sign = 1 if direction[depth_axis] >= 0 else -1
    width, height = size
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    nearest = {}
    for _face, samples in painter.element(element)._surface_entries():
        for sample in samples:
            facing = sum(a * b for a, b in zip(sample.element_normal, direction))
            if facing <= 0:
                continue
            nu, nv = sample.normalized_position[axes[0]], sample.normalized_position[axes[1]]
            pixel = (min(width - 1, int(nu * width)), min(height - 1, int(((1 - nv) if flip_v else nv) * height)))
            depth = sample.normalized_position[depth_axis] * sign
            if nearest.get(pixel, -math.inf) >= depth:
                continue
            nearest[pixel] = depth
            color = None
            if atlas is not None:
                info = painter.parser.elements[element]["faces"][sample.face_name]
                ax, ay = _canvas_to_atlas(info, *sample.pixel)
                slot_atlas = atlas.get(info.get("texture", 0)) if isinstance(atlas, dict) else atlas
                color = (slot_atlas.getpixel((min(slot_atlas.width - 1, int(ax)), min(slot_atlas.height - 1, int(ay))))
                         if slot_atlas is not None else None)
            if not color or color[3] == 0:
                shade = int(90 + 120 * facing)
                color = (shade, shade, shade, 255)
            image.putpixel(pixel, color)
    return image


def guides(context: AssetContext, data: dict) -> dict[str, dict]:
    """Render the guide of every request of one asset that declares one."""
    from Tools.TexturePainter import TexturePainter
    from Tools.TexturePainter.painter import decal_frame

    painter = TexturePainter(str(context.model))
    from Tools.TexturePainter.export import TextureExporter
    slot_paths = TextureExporter.model_slot_png_paths(painter.parser.data, context.texture)
    atlas = {
        idx: Image.open(spath).convert("RGBA")
        for idx, (_, spath) in enumerate(slot_paths) if spath.is_file()
    } or None
    results = {}
    for key, request in data["requests"].items():
        guide = request.get("guide")
        if request["asset"] != context.asset_id or guide is None:
            continue
        element, side = painter.element(guide["element"]).name, guide.get("side", "front")
        _, _, axes, flip_v = decal_frame(painter.direction_vectors, side)
        low, high = painter.surface_sampler.bounds[element]
        u, v = (low[axes[0]], high[axes[0]]), (low[axes[1]], high[axes[1]])
        width, height = request["pixels"]

        def to_pixels(point):
            x = (point[0] - u[0]) / ((u[1] - u[0]) or 1) * width
            t = (point[1] - v[0]) / ((v[1] - v[0]) or 1)
            return [round(x, 2), round(((1 - t) if flip_v else t) * height, 2)]

        path = context.directory / "art" / "guides" / f"{key}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        # One guide pixel per texel, then scaled to the requested size.
        density = painter.texel_density([(element, face, 1) for face in painter.element(element).faces])
        native = (max(1, math.ceil((u[1] - u[0]) * density)), max(1, math.ceil((v[1] - v[0]) * density)))
        _view(painter, element, side, native, atlas).resize((width, height), Image.NEAREST).save(path)
        top, bottom = (v[1], v[0]) if flip_v else (v[0], v[1])
        guide.update(
            image=_relative(context.project, path),
            mapping=(f"{element} seen from {side}: canvas x 0..{width} = {'xyz'[axes[0]]} {u[0]:.3f}..{u[1]:.3f}, "
                     f"canvas y 0..{height} = {'xyz'[axes[1]]} {top:.3f}..{bottom:.3f} (element units)"),
            points_px={name: to_pixels(point) for name, point in guide.get("points", {}).items()})
        results[key] = guide
    return results


def prompt(project: Path, data: dict, key: str) -> str:
    """A self-contained message for whoever produces the image."""
    request = data["requests"][key]
    width, height = request["pixels"]
    lines = [f"Image request '{key}' for asset '{request['asset']}'.", "", request["description"].strip(), "",
             f"Size: exactly {width}x{height} px, PNG.",
             f"Save to: {source_path(data, key)}"]
    guide = request.get("guide") or {}
    if guide.get("image"):
        lines.append(f"Guide (same size, the surface it will cover): {Path(project) / guide['image']}")
        lines.append(f"Mapping: {guide['mapping']}")
        for name, (x, y) in guide.get("points_px", {}).items():
            lines.append(f"Point {name}: x={x}, y={y}")
    return "\n".join(lines)


def write(project: Path, data: dict) -> None:
    manifest_path(project).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pull(project: Path, data: dict, *, check=False) -> list[tuple[str, str, Path, Path]]:
    """Copy delivered PNGs from ``source``; returns (request, state, source, destination).

    States: copied, unchanged, missing, wrong_size (not copied), outdated (check only).
    """
    results = []
    for key, request in data["requests"].items():
        context = resolve_asset(f"{project}#{request['asset']}")
        origin, target = source_path(data, key), deliver_path(context, key)
        if not origin.is_file():
            state = "missing"
        else:
            with Image.open(origin) as image:
                if image.format != "PNG":
                    raise ValueError(f"{origin} is not a PNG")
                size = list(image.size)
            if size != request["pixels"]:
                state = "wrong_size"
            elif target.is_file() and target.read_bytes() == origin.read_bytes():
                state = "unchanged"
            elif check:
                state = "outdated"
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin, target)
                state = "copied"
        results.append((key, state, origin, target))
    return results


def delivered(context: AssetContext, key: str) -> Path | None:
    """The pulled image of a request, or None with a warning while it is missing."""
    path = deliver_path(context, key)
    if path.is_file():
        return path
    warnings.warn(f"Art request {key!r} not delivered yet ({_relative(context.project, path)}); skipped",
                  stacklevel=3)
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="forge art", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("guide", "prompt", "pull"),
                        help="guide: render guide images; prompt: print the message for each request; "
                             "pull: copy delivered PNGs")
    parser.add_argument("project", help="Project directory containing art.json (PROJECT --asset ID limits guide)")
    parser.add_argument("--request", help="prompt: only this request id")
    parser.add_argument("--check", action="store_true", help="pull: only report; exit 1 when something is not ready")
    args = parser.parse_args(argv)
    raw, _, asset_id = args.project.partition("#")
    project = find_project(Path(raw))
    if not project:
        raise ValueError(f"Not a registered project: {raw}")
    data = load(project)
    if args.action == "guide":
        assets = [asset_id] if asset_id else sorted({r["asset"] for r in data["requests"].values()})
        with project_lock(project):
            for asset in assets:
                for key, guide in guides(resolve_asset(f"{project}#{asset}"), data).items():
                    print(f"[art] {key}: guide {guide['image']}")
            write(project, data)
        return 0
    if args.action == "prompt":
        keys = [args.request] if args.request else list(data["requests"])
        for key in keys:
            if key not in data["requests"]:
                raise ValueError(f"No request {key!r} in {MANIFEST}")
        print("\n\n---\n\n".join(prompt(project, data, key) for key in keys))
        return 0
    results = pull(project, data, check=args.check)
    for key, state, origin, target in results:
        print(f"[art] {key}: {state} ({_relative(project, target)} <- {origin})")
    states = {state for _, state, _, _ in results}
    return 1 if states & {"wrong_size"} or (args.check and states & {"missing", "outdated"}) else 0
