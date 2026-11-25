"""Reference expressions for procedural fields and a contact sheet that shows them.

Each recipe is a ``Field`` plus a palette. ``shader(name, style)`` turns it into pixel art
(``pixel``: dithered, only the palette colors) or a smooth painted look (``painted``). Copy an
expression into a texture recipe and change its numbers; see
``.agents/skills/forge-3d-texture/references/procedural-fields.md``.

  py -3.12 -m Tools.field_gallery OUT.png [--style pixel|painted|both] [--size 128] [--only stone,wood]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.TexturePainter.fields import Field, Shader  # noqa: E402

EXTENT = (4.0, 4.0)  # every recipe tiles over 4 x 4 units


def _stone():
    cracks = Field.cells(0.5, seed=1, mode="edge").invert().threshold(0.9, 0.1).warp(Field.gradient(1, seed=2), 0.25)
    return (Field.gradient(1, seed=3).fbm(4).mix(Field.cells(0.5, seed=1, mode="id"), 0.25) * 0.8 + 0.1) * (1.0 - cracks * 0.85)


def _wood():
    grain = Field.stripes(4, (1, 0, 0), shape="sine").warp(Field.gradient(0.5, seed=4, stretch=(1, 1, 1)).fbm(3), 0.7)
    return grain.mix(Field.value(8, seed=5, stretch=(0.25, 4, 1)), 0.25).contrast(1.2)


def _cloth():
    weave = Field.stripes(4, (1, 0, 0), shape="triangle") * Field.stripes(4, (0, 1, 0), shape="triangle")
    return weave.contrast(1.8).mix(Field.gradient(1, seed=6).fbm(3), 0.35)


def _rust():
    blotches = Field.gradient(1, seed=7).warp(Field.value(0.5, seed=8), 0.5).fbm(5).contrast(2.2, 0.55)
    return blotches * Field.height("y", 0, 4).invert().gamma(0.7) | Field.white(16, seed=9).threshold(0.93) * 0.8


def _moss():
    return Field.gradient(2, seed=10).fbm(4).contrast(1.6) * Field.height("y", 0, 4).gamma(0.8) | Field.white(12, seed=11).threshold(0.9) * 0.5


def _scales():
    return Field.cells(1, seed=12, jitter=0.35).invert().gamma(1.4).mix(Field.cells(1, seed=12, jitter=0.35, mode="id"), 0.25)


def _sand():
    return Field.white(24, seed=13).mix(Field.gradient(1, seed=14).stretch(1, 4, 1).fbm(3), 0.6).contrast(1.3)


def _fur():
    return Field.value(10, seed=15, stretch=(1, 0.2, 1)).mix(Field.gradient(2, seed=16).fbm(3), 0.4).contrast(1.5)


def _marble():
    veins = Field.stripes(1, (1, 0, 0), shape="sine").warp(Field.gradient(0.5, seed=17).fbm(4), 1.4)
    return veins.ridge(3).mix(Field.gradient(1, seed=18).fbm(3), 0.3)


def _leather():
    return Field.cells(2, seed=19, jitter=0.8).mix(Field.gradient(8, seed=20).fbm(2), 0.4).contrast(1.6)


def _clouds():
    return Field.value(0.5, seed=21).warp(Field.gradient(1, seed=22), 0.6).fbm(5).billow().invert().contrast(1.8, 0.55)


# name -> (field, palette dark to light)
RECIPES = {
    "stone": (_stone, ["#23222a", "#4a4954", "#7a7882", "#b0aeb6"]),
    "wood": (_wood, ["#2e1b10", "#5a3720", "#8b5a35", "#b88655"]),
    "cloth": (_cloth, ["#241b36", "#3d2d5c", "#5d4687", "#8a73b8"]),
    "rust": (_rust, ["#2b2623", "#59463a", "#9a5326", "#d98a3d"]),
    "moss": (_moss, ["#1b2616", "#33481f", "#587a2d", "#9ab94a"]),
    "scales": (_scales, ["#10282b", "#1c5058", "#2f8a8a", "#7fd0b8"]),
    "sand": (_sand, ["#6b5a3a", "#9c8758", "#cdb98a", "#efe2bd"]),
    "fur": (_fur, ["#2b2016", "#52391f", "#835a30", "#bd8f55"]),
    "marble": (_marble, ["#d9d6dd", "#a9a5b4", "#6e6a80", "#3b3850"]),
    "leather": (_leather, ["#1f130d", "#40251a", "#6a3f29", "#946243"]),
    "clouds": (_clouds, ["#2a3a63", "#4f6aa3", "#9cb4de", "#f1f6ff"]),
}
STYLES = ("pixel", "painted")


def shader(name: str, style: str = "painted", *, dither: str = "bayer4") -> Shader:
    """The recipe as a shader: ``pixel`` dithers between its palette colors, ``painted`` blends them smoothly."""
    if name not in RECIPES:
        raise ValueError(f"unknown recipe {name!r}; choose from {', '.join(RECIPES)}")
    make, colors = RECIPES[name]
    field = make()
    if style == "pixel":
        return field.dither(colors, dither)
    if style == "painted":
        return field.ramp(colors)
    raise ValueError("style must be pixel or painted")


def tile(name: str, style: str = "painted", size: int = 128) -> Image.Image:
    """A seamless tile of the recipe covering 4 x 4 units."""
    return shader(name, style).image((size, size), EXTENT, tileable=True)


def sheet(names, styles, size: int = 128) -> Image.Image:
    margin, label = 8, 14
    width = margin + len(names) * (size + margin)
    height = margin + len(styles) * (size + label + margin)
    image = Image.new("RGBA", (width, height), (24, 24, 28, 255))
    draw = ImageDraw.Draw(image)
    for row, style in enumerate(styles):
        for column, name in enumerate(names):
            x = margin + column * (size + margin)
            y = margin + row * (size + label + margin)
            image.paste(tile(name, style, size), (x, y + label))
            draw.text((x, y), f"{name} ({style})", fill=(220, 220, 230, 255))
    return image


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", help="PNG path for the contact sheet")
    parser.add_argument("--style", choices=("pixel", "painted", "both"), default="both")
    parser.add_argument("--size", type=int, default=128, help="pixels per tile (default 128)")
    parser.add_argument("--only", help="comma-separated recipe names (default: all)")
    args = parser.parse_args(argv)
    names = args.only.split(",") if args.only else list(RECIPES)
    unknown = [n for n in names if n not in RECIPES]
    if unknown:
        parser.error(f"unknown recipes {unknown}; choose from {', '.join(RECIPES)}")
    styles = STYLES if args.style == "both" else (args.style,)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet(names, styles, args.size).save(output)
    print(f"[fields] {len(names)} recipes x {len(styles)} styles -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
