"""List, check and draw a project's theme: py -3.12 -m Tools.forge theme PROJECT [--sheet OUT.png] [--init].

The theme is ``projects/<p>/theme.py`` (``Tools.TexturePainter.theme``). Without options the command prints every
token by kind and fails when the theme does not check. ``--sheet`` draws a sample sheet: the palette, every tip
at growing pressure, every brush as strokes on a flat plate, and every line style along a wave. ``--init`` writes
theme.py and STYLE.md templates into a project that has none.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import tempfile

import numpy as np
from PIL import Image, ImageDraw

PX = 24              # sheet pixels per model unit on the plates
LABEL = 150          # width of the label column


def _project(target: str) -> Path:
    path = Path(target.split("#", 1)[0]).resolve()
    if not (path / "project.json").is_file():
        raise ValueError(f"not a project folder (no project.json): {path}")
    return path


def _plate(folder, width, height, scale=16):
    """A flat plate facing +z (``width`` x ``height`` units), packed at ``scale`` texels per unit."""
    from lib import ModelBuilder
    from lib.geometry_types import MeshFace, MeshGeometry
    from Tools.TexturePainter import TexturePainter
    from Tools.uv_builder import UVBuilder
    path = Path(folder) / "plate.bbmodel"
    verts = {"a": (0, 0, 0), "b": (width, 0, 0), "c": (width, height, 0), "d": (0, height, 0)}
    builder = ModelBuilder("plate", require_integer_dimensions=False).add_group("root")
    builder.add_mesh("plate", "root", MeshGeometry.create(verts, {"plate": MeshFace(("a", "b", "c", "d"), "plate")}))
    builder.export_bbmodel(path)
    UVBuilder(path, start_size=(256, 256), uv_scale=scale, island_padding=2, layout="charts",
              require_integer_uvs=False).save()
    return TexturePainter.from_bbmodel(str(path), render="smooth")


def _plate_image(painter, width, height):
    """The plate's painted texels as an image (model x right, y up)."""
    view = painter.surface()
    atlas = np.asarray(painter.compose_atlas()).astype(float)
    rgba = atlas[view.y, view.x]
    img = np.full((int(height * PX), int(width * PX), 3), 255.0)
    xs = np.clip((view.centre[:, 0] * PX).astype(int), 0, img.shape[1] - 1)
    ys = np.clip(((height - view.centre[:, 1]) * PX).astype(int), 0, img.shape[0] - 1)
    a = rgba[:, 3:4] / 255.0
    # every texel paints the sheet pixels of its square (texels are larger than sheet pixels at low density)
    cell = max(1, int(math.ceil(PX / 16)))
    for dy in range(cell):
        for dx in range(cell):
            yy, xx = np.clip(ys + dy, 0, img.shape[0] - 1), np.clip(xs + dx, 0, img.shape[1] - 1)
            img[yy, xx] = img[yy, xx] * (1 - a) + rgba[:, :3] * a
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


def _row(label, image, width):
    row = Image.new("RGB", (width, image.height + 8), (255, 255, 255))
    ImageDraw.Draw(row).text((6, 6), label, fill=(0, 0, 0))
    row.paste(image, (LABEL, 4))
    return row


def _tip_image(tip, seed=0, w=240, h=48):
    """Ink of a tip from no pressure (left) to full (right), at the default density."""
    if tip.motif is not None:
        motif = Image.fromarray(tip.motif, "RGBA").resize((h, h))
        out = Image.new("RGB", (w, h), (255, 255, 255))
        out.paste(motif, (0, 0), motif)
        return out
    rank = tip.field(seed)
    if rank is None:
        return Image.new("RGB", (w, h), (30, 30, 30))
    size = rank.shape[0]
    ys, xs = np.mgrid[0:h, 0:w]
    g = rank[ys % size, xs % size]
    ink = g > 1.0 - 0.8 * (xs / (w - 1))
    return Image.fromarray(np.where(ink, 30, 255).astype(np.uint8), "L").convert("RGB")


def sheet(theme, out: Path):
    from Tools.TexturePainter.ink import curve
    from Tools.TexturePainter.marks import Pattern, Tip
    width = LABEL + 8 * PX + 20
    rows = []
    swatches = Image.new("RGB", (8 * PX, 28), (255, 255, 255))
    draw = ImageDraw.Draw(swatches)
    for i, name in enumerate(sorted(theme.palette)):
        if i >= 8 * PX // 26:
            break
        draw.rectangle([i * 26, 0, i * 26 + 22, 22], fill=tuple(theme.color(name)[:3]))
    if theme.palette:
        rows.append(_row("palette", swatches, width))
    for name, tip in sorted(theme.tips.items()):
        rows.append(_row(f"tip {name}", _tip_image(tip), width))
    default_tip = theme.tips.get("chalk") or next(iter(theme.tips.values()), Tip.grain())
    with tempfile.TemporaryDirectory() as folder:
        for name, brush in sorted(theme.brushes.items()):
            painter = _plate(folder, 8, 2)
            painter.fill_all((255, 255, 255, 255))
            painter.stamp(Pattern.scatter(coverage=2.0), tip=default_tip, brush=brush,
                          colors=[(40, 40, 60)], seed=1)
            rows.append(_row(f"brush {name}", _plate_image(painter, 8, 2), width))
        for name, line_style in sorted(theme.lines.items()):
            painter = _plate(folder, 8, 2)
            painter.fill_all((255, 255, 255, 255))
            painter.paint_strokes([line_style(curve([(0.5, 0.6), (2.5, 1.5), (5.0, 0.5), (7.5, 1.4)]))])
            rows.append(_row(f"line {name}", _plate_image(painter, 8, 2), width))
    height = sum(r.height for r in rows) + 30
    page = Image.new("RGB", (width, max(height, 40)), (255, 255, 255))
    ImageDraw.Draw(page).text((6, 8), f"theme {theme.name}", fill=(0, 0, 0))
    y = 30
    for row in rows:
        page.paste(row, (0, y))
        y += row.height
    out.parent.mkdir(parents=True, exist_ok=True)
    page.save(out)
    return out


THEME_TEMPLATE = '''"""Theme of the {name} project: the visual tokens its assets paint with (see STYLE.md)."""
from Tools.TexturePainter.ink import style
from Tools.TexturePainter.looks import PaintLayer
from Tools.TexturePainter.marks import Brush, Tip
from Tools.TexturePainter.theme import define_theme

INK = "#0e1222"

THEME = define_theme(
    "{name}",
    palette={{"ink": INK}},
    tips={{"chalk": Tip.grain(speck=0.9, cluster=5.0, clump=0.55, scale=1 / 11)}},
    brushes={{"chalk": Brush(radius=(0.5, 0.9), length=(3, 7))}},
    lines={{"thick": style(width=2, color=INK), "fine": style(width=1, color=INK)}},
    layers=(PaintLayer("texture"), PaintLayer("shading"), PaintLayer("lighting")),
)
'''

STYLE_TEMPLATE = """# Style: {name}

The art direction of every asset in this project, in words; the tokens are in [`theme.py`](theme.py).

## Look

- Surfaces:
- Shading and light:
- Lines:

## Specifications the theme cannot express

- Resolution and filtering (pixel art or smooth, texels per unit):
- Edge treatment (hard texels, soft edges, feathered lines):
- Layering rules (what sits above what):
"""


def init(project: Path):
    """Write theme.py and STYLE.md templates into ``project``; existing files are kept."""
    for filename, template in (("theme.py", THEME_TEMPLATE), ("STYLE.md", STYLE_TEMPLATE)):
        path = project / filename
        if path.exists():
            print(f"[theme] kept {path}")
        else:
            path.write_text(template.format(name=project.name), encoding="utf-8")
            print(f"[theme] wrote {path}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", help="the project folder (projects/<p>)")
    parser.add_argument("--sheet", type=Path, help="draw the tokens into this PNG")
    parser.add_argument("--init", action="store_true", help="write theme.py and STYLE.md templates if missing")
    args = parser.parse_args(argv)
    from Tools.TexturePainter.theme import load_theme
    if args.init:
        init(_project(args.project))
    theme = load_theme(_project(args.project))
    print(theme.summary())
    problems = theme.problems()
    if problems:
        print("[theme] FAIL\n  " + "\n  ".join(problems))
        return 1
    print("[theme] PASS")
    if args.sheet:
        print(f"[theme] sheet: {sheet(theme, args.sheet)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
