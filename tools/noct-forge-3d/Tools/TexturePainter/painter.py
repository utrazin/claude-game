import os
import hashlib
import math
import random
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import numpy as np
from PIL import Image

from .core.color import (
    ColorType,
    blend_colors,
    blend_rows,
    clamp_byte,
    clamp_bytes,
    color_add_noise,
    color_lerp,
    lerp_rows,
    parse_color,
)
from .core.face_canvas import FaceCanvas
from .core.polygon_face_canvas import PolygonFaceCanvas
from .core.bbmodel_parser import BlockbenchModelParser
from .core.surface_sampling import FaceSamples, SurfaceSampler, python_sum
from .core.contact_fields import ContactFieldDetector
from .export import TextureExporter
from .standalone import DecalCanvas
from .fields import Field, Frame, Shader


_FACE_FOR_VECTOR = {
    (1, 0, 0): "east", (-1, 0, 0): "west",
    (0, 1, 0): "up", (0, -1, 0): "down",
    (0, 0, 1): "south", (0, 0, -1): "north",
}

_SIDE_AXES = {
    "front": (0, 1),
    "back": (0, 1),
    "east": (2, 1),
    "west": (2, 1),
    "top": (0, 2),
    "bottom": (0, 2),
}


_DEFAULT_VECTORS = {
    "front": (0, 0, 1), "back": (0, 0, -1),
    "top": (0, 1, 0), "bottom": (0, -1, 0),
    "east": (1, 0, 0), "west": (-1, 0, 0),
}


def decal_frame(vectors, side):
    """Projection of a side: (side, facing vector, (u axis, v axis), v_flipped).

    Image u grows with the u axis; with ``v_flipped`` the image top is the high end
    of the v axis (every side except bottom). Shared by decals, planar tiling and
    art request guides so all use one convention.
    """
    clean_side = str(side).lower()
    aliases = {alias: name for alias, vector in (("north", (0, 0, -1)), ("south", (0, 0, 1)),
                                                 ("up", (0, 1, 0)), ("down", (0, -1, 0)))
               for name in [next((k for k, v in vectors.items() if tuple(v) == vector), None)] if name}
    clean_side = aliases.get(clean_side, clean_side)
    definitions = {
        "front": (vectors["front"], (0, 1)),
        "back": (vectors["back"], (0, 1)),
        "east": ((1, 0, 0), (2, 1)),
        "west": ((-1, 0, 0), (2, 1)),
        "top": (vectors["top"], (0, 2)),
        "bottom": (vectors["bottom"], (0, 2)),
    }
    if clean_side not in definitions:
        raise ValueError(f"side must be front (north), back (south), east, west, top (up), or bottom (down); got {side!r}")
    direction, axes = definitions[clean_side]
    return clean_side, direction, axes, clean_side != "bottom"


def _orientation_contract(document):
    """Return semantic face aliases and vectors from persisted orientation."""
    data = document.get("unhandled_root_fields", {}).get("model_as_code", {}).get("orientation", {})
    names = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0),
             "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1)}
    up = names.get(str(data.get("up", "+Y")).upper())
    front = names.get(str(data.get("front", "+Z")).upper())
    if up is None or front is None or sum(a * b for a, b in zip(up, front)):
        raise ValueError("model_as_code.orientation requires perpendicular cardinal up/front axes")
    right = (up[1] * front[2] - up[2] * front[1],
             up[2] * front[0] - up[0] * front[2],
             up[0] * front[1] - up[1] * front[0])
    back = tuple(-value for value in front)
    bottom = tuple(-value for value in up)
    left = tuple(-value for value in right)
    vectors = {"front": front, "back": back, "right": right, "left": left,
               "top": up, "bottom": bottom}
    aliases = {"front": _FACE_FOR_VECTOR[front], "back": _FACE_FOR_VECTOR[back],
               "top": _FACE_FOR_VECTOR[up], "bottom": _FACE_FOR_VECTOR[bottom]}
    return aliases, vectors


def _dilate_rgba(image: Image.Image, distance: int) -> Image.Image:
    """Extend edge colors into a transparent gutter using deterministic neighbors."""
    if distance <= 0:
        return image
    expanded = Image.new("RGBA", (image.width + 2 * distance, image.height + 2 * distance))
    expanded.paste(image, (distance, distance))
    pixels = np.array(expanded)
    height, width = pixels.shape[:2]
    for _ in range(distance):
        source = pixels.copy()
        filled = source[..., 3] > 0
        # Each transparent texel takes its first opaque neighbor in this order.
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1),
                       (-1, -1), (1, -1), (-1, 1), (1, 1)):
            neighbor = np.zeros_like(source)
            neighbor[max(0, -dy):height - max(0, dy), max(0, -dx):width - max(0, dx)] = \
                source[max(0, dy):height - max(0, -dy), max(0, dx):width - max(0, -dx)]
            take = ~filled & (neighbor[..., 3] > 0)
            pixels[take] = neighbor[take]
            filled |= take
    return Image.fromarray(pixels, "RGBA")


def _derived_seed(seed, element, face):
    if seed is None:
        return None
    digest = hashlib.sha256(f"{seed}:{element}:{face}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _pattern_to_image(pattern: Sequence[str], palette: Dict[str, ColorType]) -> Image.Image:
    if not pattern or any(not isinstance(r, str) for r in pattern):
        raise ValueError("Pattern must contain text rows")
    w = len(pattern[0])
    h = len(pattern)
    if w == 0 or any(len(r) != w for r in pattern):
        raise ValueError("Pattern rows must have uniform non-zero width")
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for y, row in enumerate(pattern):
        for x, char in enumerate(row):
            if char in palette:
                col = parse_color(palette[char])
                if col[3] > 0:
                    img.putpixel((x, y), col)
    return img


def _resolve_decal_image(source: Union[str, Path, Image.Image, Tuple[Any, Any], List[str], FaceCanvas],
                         palette: Optional[Dict[str, ColorType]] = None) -> Image.Image:
    if isinstance(source, (str, Path)):
        path = Path(source).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Decal image not found: {path}")
        return Image.open(path).convert("RGBA")
    if isinstance(source, Image.Image):
        return source.convert("RGBA")
    if hasattr(source, "to_image"):
        return source.to_image().convert("RGBA")
    if hasattr(source, "image") and isinstance(source.image, Image.Image):
        return source.image.copy().convert("RGBA")
    if isinstance(source, tuple) and len(source) == 2 and isinstance(source[0], (list, tuple)):
        return _pattern_to_image(source[0], source[1])
    if isinstance(source, (list, tuple)) and palette is not None:
        return _pattern_to_image(source, palette)
    raise ValueError(f"Unsupported decal source type: {type(source).__name__}. "
                     "Expected file path, PIL Image, DecalCanvas, or (pattern, palette).")


def _sample_bilinear(img: Image.Image, u: float, v: float, wrap: bool = False) -> Tuple[int, int, int, int]:
    """Bilinear sample; ``wrap`` blends across the borders of a seamless tile instead of clamping."""
    w, h = img.width, img.height
    if wrap:
        x = (u * w - 0.5) % w
        y = (v * h - 0.5) % h
        x0, y0 = int(x), int(y)
        x1, y1 = (x0 + 1) % w, (y0 + 1) % h
    else:
        x = max(0.0, min(float(w - 1), u * (w - 1)))
        y = max(0.0, min(float(h - 1), v * (h - 1)))
        x0 = int(math.floor(x))
        y0 = int(math.floor(y))
        x1 = min(w - 1, x0 + 1)
        y1 = min(h - 1, y0 + 1)
    fx = x - x0
    fy = y - y0

    p00 = img.getpixel((x0, y0))
    p10 = img.getpixel((x1, y0))
    p01 = img.getpixel((x0, y1))
    p11 = img.getpixel((x1, y1))

    channels = []
    for i in range(4):
        top = p00[i] * (1.0 - fx) + p10[i] * fx
        bot = p01[i] * (1.0 - fx) + p11[i] * fx
        val = top * (1.0 - fy) + bot * fy
        channels.append(clamp_byte(val))
    return tuple(channels)


def _face_rows(samples) -> FaceSamples:
    return samples if isinstance(samples, FaceSamples) else FaceSamples.from_samples(samples)


def _image_rows(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGBA"), dtype=np.int64)


def _sample_nearest_rows(image: np.ndarray, u, v) -> np.ndarray:
    """Row version of nearest lookup: min(size - 1, max(0, int(t * size)))."""
    height, width = image.shape[:2]
    columns = np.minimum(width - 1, np.maximum(0, (u * width).astype(np.int64)))
    lines = np.minimum(height - 1, np.maximum(0, (v * height).astype(np.int64)))
    return image[lines, columns]


def _sample_bilinear_rows(image: np.ndarray, u, v, wrap: bool = False) -> np.ndarray:
    """Row version of _sample_bilinear."""
    height, width = image.shape[:2]
    if wrap:
        x = (u * width - 0.5) % width
        y = (v * height - 0.5) % height
        x0, y0 = x.astype(np.int64) % width, y.astype(np.int64) % height
        x1, y1 = (x0 + 1) % width, (y0 + 1) % height
    else:
        x = np.maximum(0.0, np.minimum(float(width - 1), u * (width - 1)))
        y = np.maximum(0.0, np.minimum(float(height - 1), v * (height - 1)))
        x0, y0 = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
        x1, y1 = np.minimum(width - 1, x0 + 1), np.minimum(height - 1, y0 + 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    top = image[y0, x0] * (1.0 - fx) + image[y0, x1] * fx
    bottom = image[y1, x0] * (1.0 - fx) + image[y1, x1] * fx
    return clamp_bytes(top * (1.0 - fy) + bottom * fy)


def _patch_rows(rows: FaceSamples, direction, axes, center, half) -> np.ndarray:
    """Samples facing ``direction`` whose projected normalized position lies in the patch."""
    normal = rows.fields["element_normal"]
    keep = python_sum([normal[:, i] * direction[i] for i in range(3)]) > 1e-9
    for index in range(2):
        value = rows.fields["normalized_position"][:, axes[index]]
        keep &= (center[index] - half[index] - 1e-9 <= value) & (value <= center[index] + half[index] + 1e-9)
    return keep


class FacePainter:
    """Interface para desenhar em uma face específica de um elemento."""
    def __init__(self, element_painter: 'ElementPainter', face_name: str,
                 canvas: Optional[FaceCanvas] = None, uv_info: Optional[dict] = None):
        self.element_painter = element_painter
        self.face_name = face_name
        self._canvas = canvas
        self.uv_info = uv_info or {}

    @property
    def canvas(self) -> FaceCanvas:
        tp = getattr(self.element_painter, "texture_painter", None)
        if tp is not None and hasattr(tp, "get_active_canvas"):
            return tp.get_active_canvas(self.element_painter.name, self.face_name)
        if self._canvas is not None:
            return self._canvas
        raise RuntimeError(f"Canvas for {self.element_painter.name}.{self.face_name} not available")

    @canvas.setter
    def canvas(self, val: FaceCanvas):
        self._canvas = val

    @property
    def width(self) -> int:
        return self.canvas.width

    @property
    def height(self) -> int:
        return self.canvas.height

    def fill(self, color: ColorType) -> 'FacePainter':
        self.canvas.fill(color)
        return self

    def set_pixel(self, x: int, y: int, color: ColorType) -> 'FacePainter':
        self.canvas.set_pixel(x, y, color)
        return self

    def get_pixel(self, x: int, y: int):
        return self.canvas.get_pixel(x, y)

    def draw_rect(self, x: int, y: int, w: int, h: int, color: ColorType, fill: bool = True) -> 'FacePainter':
        self.canvas.draw_rect(x, y, w, h, color, fill=fill)
        return self

    def draw_line(self, x1: int, y1: int, x2: int, y2: int, color: ColorType) -> 'FacePainter':
        self.canvas.draw_line(x1, y1, x2, y2, color)
        return self

    def draw_circle(self, xc: int, yc: int, radius: int, color: ColorType, fill: bool = False) -> 'FacePainter':
        self.canvas.draw_circle(xc, yc, radius, color, fill=fill)
        return self

    def apply_noise(self, variance: int = 8, seed: Optional[int] = None) -> 'FacePainter':
        self.canvas.apply_noise(variance, seed=seed)
        return self

    def apply_gradient(self, top_color: ColorType, bottom_color: ColorType) -> 'FacePainter':
        self.canvas.apply_gradient(top_color, bottom_color)
        return self

    def draw_pattern(self, pattern: List[str], palette: Dict[str, ColorType]) -> 'FacePainter':
        self.canvas.draw_pattern(pattern, palette)
        return self

    def stamp(self, pattern: List[str], palette: Dict[str, ColorType], *,
              anchor: str = "center", offset_px=(0, 0), clip: bool = False) -> 'FacePainter':
        self.canvas.stamp(pattern, palette, anchor=anchor, offset_px=offset_px, clip=clip)
        return self

    def blit(self, source: Union[FaceCanvas, Image.Image, str, Path], x: int = 0, y: int = 0) -> 'FacePainter':
        self.canvas.blit(source, x, y)
        return self


class SharedFacePainter:
    """Ownership information only; paint the owner instead."""
    def __init__(self, info):
        self.uv_info = info
        self.owner = tuple(info['owner'])
        self.width, self.height = ((info['h'], info['w']) if info['rotation'] in (90, 270)
                                   else (info['w'], info['h']))

    def __getattr__(self, name):
        raise ValueError(f'Shared face is not paintable; paint owner {self.owner[0]}.{self.owner[1]}')


def _texture_painter_of(entries):
    for face, _ in entries:
        ep = getattr(face, "element_painter", None)
        if ep is not None and hasattr(ep, "texture_painter"):
            return ep.texture_painter
    return None


def _edges(rows_list, colors, keep):
    """Texels whose centre colour (or keep) differs from one of their 8 neighbours on the same face canvas: the
    only texels where a colour boundary can cross, so the only ones worth subsampling (costs no evaluation)."""
    out = np.zeros(len(keep), dtype=bool)
    start = 0
    for rows in rows_list:
        stop = start + len(rows)
        if stop > start:
            x, y = rows.x - rows.x.min() + 1, rows.y - rows.y.min() + 1
            w, h = int(x.max()) + 2, int(y.max()) + 2
            value = np.full((h, w, 5), -1.0)
            value[y, x, :4] = np.where(keep[start:stop, None], colors[start:stop], -2.0)
            value[y, x, 4] = keep[start:stop]
            mine = value[y, x]
            varies = np.zeros(stop - start, dtype=bool)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx or dy:
                        other = value[y + dy, x + dx]
                        present = other[:, 4] >= 0
                        varies |= present & (other != mine).any(axis=1)
            out[start:stop] = varies
        start = stop
    return out


def supersample(texture_painter, rows_list, evaluate, offsets=None, center=None):
    """Average ``evaluate`` over subsamples of each texel (smooth render mode).

    ``evaluate(rows_list) -> (colors (N, 4), keep (N,))`` over the rows of every FaceSamples in ``rows_list``,
    concatenated; it must colour each row from that row's own fields. The texel centre and the four corner
    subsamples are evaluated everywhere; texels where any of them differs (colour or keep) get the full
    ``offsets`` grid. Sums are taken over integer colours, so the result does not depend on the order of the
    subsamples (mirror-image texels average the same values). Returns (colors, coverage): float RGBA,
    alpha-weighted mean over the kept subsamples, and the kept fraction 0..1. ``center``: the result of
    ``evaluate(rows_list)`` when the caller already has it.
    """
    colors, keep = evaluate(rows_list) if center is None else center
    colors = np.rint(np.asarray(colors, dtype=float))
    keep = np.asarray(keep, dtype=bool)
    offsets = texture_painter.render.offsets() if offsets is None else offsets
    sampler = texture_painter.surface_sampler
    if len(offsets) <= 1 or not len(keep):
        return colors, keep.astype(float)
    if any("_e0" not in rows.fields for rows in rows_list):     # rows built from loose samples: no texel frame
        return colors, keep.astype(float)
    shifted = lambda part, offset: [sampler.shifted(rows, offset) for rows in part]
    varies = _edges(rows_list, colors, keep)
    coverage = keep.astype(float)
    if not varies.any():
        return colors, coverage
    starts = np.cumsum([0] + [len(rows) for rows in rows_list])
    parts = [rows.subset(varies[a:b]) for rows, a, b in zip(rows_list, starts[:-1], starts[1:])]
    kept = np.zeros(int(varies.sum()), dtype=np.int64)
    alpha = np.zeros(len(kept), dtype=np.int64)
    rgb = np.zeros((len(kept), 3), dtype=np.int64)
    for offset in offsets:
        c, k = evaluate(shifted(parts, offset))
        c = np.clip(np.rint(np.asarray(c, dtype=float)), 0, 255).astype(np.int64)
        k = np.asarray(k, dtype=bool)
        a = np.where(k, c[:, 3], 0)
        kept += k
        alpha += a
        rgb += c[:, :3] * a[:, None]
    out = np.zeros((len(kept), 4))
    some = alpha > 0
    out[some, :3] = rgb[some] / alpha[some, None]
    out[kept > 0, 3] = alpha[kept > 0] / kept[kept > 0]
    colors[varies] = out
    coverage[varies] = kept / float(len(offsets))
    return colors, coverage


def _write_coverage(face, rows, colors, coverage):
    """Write fully covered rows as they are (like pixel painting) and composite partly covered ones over the
    current pixels with their coverage."""
    full, part = coverage >= 1.0, (coverage > 0) & (coverage < 1.0)
    canvas = face.canvas
    if full.any():
        canvas.write_pixels(rows.x[full], rows.y[full], np.rint(colors[full]))
    if part.any():
        over = colors[part].copy()
        over[:, 3] = over[:, 3] * coverage[part]
        xs, ys = rows.x[part], rows.y[part]
        canvas.write_pixels(xs, ys, blend_rows(canvas.read_pixels(xs, ys), np.rint(over).astype(np.int64),
                                               mode="normal", opacity=1.0))


class SurfaceTarget:
    """
    Base class for declarative 3D surface operations.
    Unifies ElementPainter, FaceGroupPainter, ElementSelection, and SurfaceRegion.
    """
    def _to_surface_region(self) -> 'SurfaceRegion':
        raise NotImplementedError

    def fill(self, color: ColorType) -> 'SurfaceTarget':
        self._to_surface_region().fill(color)
        return self

    def apply_noise(self, variance: int = 8, seed: Optional[int] = None) -> 'SurfaceTarget':
        self._to_surface_region().apply_noise(variance, seed=seed)
        return self

    def apply_gradient(self, start_color: ColorType, end_color: ColorType, *, axis: str = "y") -> 'SurfaceTarget':
        self._to_surface_region().apply_gradient(start_color, end_color, axis=axis)
        return self

    def paint_surface(self, callback) -> 'SurfaceTarget':
        self._to_surface_region().paint_surface(callback)
        return self

    def paint_surface_arrays(self, callback) -> 'SurfaceTarget':
        """Vectorized paint_surface; see SurfaceRegion.paint_surface_arrays."""
        self._to_surface_region().paint_surface_arrays(callback)
        return self

    def paint_field(self, shader, *, space: str = "model", where=None, blend: str = "normal",
                    opacity: float = 1.0) -> 'SurfaceTarget':
        """Paint a procedural ``Shader`` (``field.ramp(...)`` / ``field.dither(...)``) on these texels.

        ``space`` is the coordinate system the field is evaluated in: ``model`` (model units,
        continuous across elements), ``element`` (the element's own units), ``normalized`` (0..1
        across each element) or ``uv`` (atlas pixels). ``where`` limits the paint: a ``Field``
        (soft mask multiplying the alpha) or a callable ``rows -> bool array``. ``blend`` and
        ``opacity`` work as in ``project_decal``. One batched evaluation covers every face.
        """
        self._to_surface_region().paint_field(shader, space=space, where=where, blend=blend, opacity=opacity)
        return self

    def paint_strokes(self, strokes, *, soft: Optional[float] = None, offset=(0.0, 0.0, 0.0), clean=None):
        """Paint lineart ``strokes`` (see ``Tools.TexturePainter.ink``) on these texels, in list order.

        ``soft``: anti-aliasing box in texels for strokes that do not set their own (default: the render mode's,
        0 in pixel art); ``offset`` shifts the texel positions the strokes are measured in (a tuple or
        ``element_name -> tuple``); ``clean`` removes corner pixels of one-texel lines (default: on for pixel
        strokes). Returns an ``InkReport``.
        """
        from .ink import paint_strokes
        return paint_strokes(self._to_surface_region(), strokes, soft=soft, offset=offset, clean=clean)

    def stamp(self, pattern, *, tip, brush, colors, opacity: float = 1.0, blend: str = "normal", mirror=None,
              offset=(0.0, 0.0, 0.0), **options):
        """Lay strokes of stamps on this surface (``Tools.TexturePainter.stamps``): ``pattern`` (a ``Pattern``:
        scatter, lattice, at) says where strokes start, ``brush`` (a ``Brush``) how each stroke moves, ``tip`` (a
        ``Tip``: a grain, solid ink or an image motif) what each stamp leaves; ``colors`` one or more colours the
        strokes pick from (``tip_colors``: the colours their far end reaches). The strokes go on a transparent layer
        composited with ``blend`` at ``opacity``; ``mirror="x"`` makes it exactly symmetric. Options: ``pressure``
        (0..1 per texel), ``seed``, ``occlusion`` (default True: a stamp paints only the surface layer it sits on),
        ``edge`` ("hard" grain or "soft"). Returns the ``Hits``."""
        from .projection import region_view
        from .stamps import paint
        entries = [(face, rows) for face, rows in self._to_surface_region()._entries if len(rows)]
        if not entries:
            raise ValueError("stamp: the region has no texels")
        view = region_view(_texture_painter_of(entries), entries, offset)
        return paint(view, pattern, tip=tip, brush=brush, colors=colors, opacity=opacity, blend=blend, mirror=mirror,
                     **options)

    def band(self, axis: str, start: float, end: float) -> 'SurfaceRegion':
        return self._to_surface_region().band(axis, start, end)

    def patch(self, side: str, center: Tuple[float, float] = (0.5, 0.5), size: Tuple[float, float] = (0.5, 0.5)) -> 'SurfaceRegion':
        return self._to_surface_region().patch(side, center, size)

    def project_decal(
        self,
        source: Union[str, Path, Image.Image, Tuple[List[str], Dict[str, ColorType]], List[str], FaceCanvas],
        *,
        side: str = "front",
        center: Tuple[float, float] = (0.5, 0.5),
        size: Tuple[float, float] = (0.5, 0.5),
        rotation: float = 0.0,
        filtering: str = "nearest",
        blend: str = "normal",
        opacity: float = 1.0,
        palette: Optional[Dict[str, ColorType]] = None,
        normal_threshold: float = 0.0,
        layers: str = "all",
        fade: Optional[Tuple[float, float]] = None,
        mirror: Optional[str] = None,
    ) -> 'SurfaceTarget':
        self._to_surface_region().project_decal(
            source, side=side, center=center, size=size, rotation=rotation,
            filtering=filtering, blend=blend, opacity=opacity, palette=palette,
            normal_threshold=normal_threshold, layers=layers, fade=fade, mirror=mirror
        )
        return self

    def project_planar(
        self,
        source: Union[str, Path, Image.Image, FaceCanvas],
        *,
        side: str = "front",
        scale: float = 1.0,
        offset: Tuple[float, float] = (0.0, 0.0),
        filtering: str = "nearest",
        blend: str = "normal",
        opacity: float = 1.0,
        normal_threshold: float = -1.0,
        layers: str = "all",
        fade: Optional[Tuple[float, float]] = None,
        mirror: Optional[str] = None,
    ) -> 'SurfaceTarget':
        self._to_surface_region().project_planar(
            source, side=side, scale=scale, offset=offset, filtering=filtering,
            blend=blend, opacity=opacity, normal_threshold=normal_threshold, layers=layers, fade=fade, mirror=mirror
        )
        return self

    def project_triplanar(
        self,
        source: Union[str, Path, Image.Image, FaceCanvas],
        *,
        scale: float = 1.0,
        blend_sharpness: float = 4.0,
        filtering: str = "nearest",
        blend: str = "normal",
        opacity: float = 1.0,
        mirror: Optional[str] = None,
    ) -> 'SurfaceTarget':
        self._to_surface_region().project_triplanar(
            source, scale=scale, blend_sharpness=blend_sharpness,
            filtering=filtering, blend=blend, opacity=opacity, mirror=mirror
        )
        return self


class SurfaceRegion(SurfaceTarget):
    """An explicit, reusable set of sampled texels.

    Entries pair a face with its FaceSamples. Bulk operations work on the sample
    arrays and write each face once; results match the per-texel definitions.
    """

    def __init__(self, entries):
        self._entries = tuple((face, _face_rows(samples)) for face, samples in entries)

    def _to_surface_region(self) -> 'SurfaceRegion':
        return self

    def __len__(self):
        return sum(len(samples) for _, samples in self._entries)

    def _direction_vectors(self):
        for face, _ in self._entries:
            ep = getattr(face, "element_painter", None)
            if ep and hasattr(ep, "texture_painter"):
                return ep.texture_painter.direction_vectors
        return _DEFAULT_VECTORS

    def _blend_into(self, face, rows, keep, colors, blend, opacity):
        """Blend overlay ``colors`` (kept rows only) over the face's current pixels."""
        if not keep.any():
            return
        xs, ys = rows.x[keep], rows.y[keep]
        canvas = face.canvas
        canvas.write_pixels(xs, ys, blend_rows(canvas.read_pixels(xs, ys), colors, mode=blend, opacity=opacity))

    def project_planar(self, source, *, side="front", scale=1.0, offset=(0.0, 0.0),
                       filtering="nearest", blend="normal", opacity=1.0, normal_threshold=-1.0, layers="all",
                       fade=None, mirror=None):
        """Tile a seamless image along one axis in model units, continuous across elements.

        ``layers="front"`` paints only the surface layer in front along ``side`` (a wall behind another, such as the
        inside of a collar, stays untouched); ``"all"`` paints every layer. ``fade=(f0, f1)`` replaces the hard
        ``normal_threshold`` cut: the image fades in linearly from facing ``f0`` (alpha 0) to ``f1`` (full), so a
        surface turning edge-on to the projection loses the image gradually instead of showing a stretched streak.

        ``scale`` is tiles per model unit (1/8 repeats every 8 units). Faces whose
        normal faces ``side`` less than ``normal_threshold`` are skipped (default:
        none, a box projection through the whole region).
        """
        if layers not in ("all", "front"):
            raise ValueError("layers must be 'all' or 'front'")
        if fade is not None and not (len(fade) == 2 and fade[0] < fade[1]):
            raise ValueError("fade must be (facing_start, facing_full) with facing_start < facing_full")
        image = _image_rows(_resolve_decal_image(source))
        _, direction, axes, flip_v = decal_frame(self._direction_vectors(), side)

        def evaluate(rows_list):
            colors_out, keep_out = [], []
            for rows in rows_list:
                normal = rows.fields["model_normal"]
                facing = python_sum([normal[:, i] * direction[i] for i in range(3)])
                keep = facing >= (normal_threshold if fade is None else fade[0])
                position = rows.fields["model_position"]
                pu = position[:, axes[0]] * scale + offset[0]
                pv = position[:, axes[1]] * scale + offset[1]
                u, v = pu % 1.0, ((1.0 - pv) if flip_v else pv) % 1.0
                colors = (_sample_bilinear_rows(image, u, v, wrap=True) if filtering == "bilinear"
                          else _sample_nearest_rows(image, u, v))
                keep &= colors[:, 3] != 0
                if fade is not None:        # the projection fades out as the surface turns edge-on to it
                    colors = colors.copy()
                    colors[:, 3] = np.rint(colors[:, 3] * np.clip((facing - fade[0]) / (fade[1] - fade[0]), 0.0, 1.0))
                    keep &= colors[:, 3] > 0
                colors_out.append(colors)
                keep_out.append(keep)
            return np.concatenate(colors_out), np.concatenate(keep_out)

        self._apply_projection(evaluate, blend, opacity, occlusion=(direction, axes) if layers == "front" else None,
                               mirror=mirror)
        return self

    @staticmethod
    def _front_mask(painter, rows_list, keep, direction, axes):
        """Boolean per texel (all rows): on the front-most layer among the texels ``keep`` selects."""
        from types import SimpleNamespace
        from .projection import front_layer
        texel = 1.0 / (painter.texel_density([(r.element_name, r.face_name, len(r)) for r in rows_list], fallback=8)
                       if painter is not None else 8.0)
        view = SimpleNamespace(position=np.concatenate([np.asarray(r.fields["model_position"]) for r in rows_list]),
                               normal=np.concatenate([np.asarray(r.fields["model_normal"]) for r in rows_list]))
        direction = np.asarray(direction, dtype=float)
        candidates = np.flatnonzero(keep)
        front = np.zeros(len(keep), dtype=bool)
        if len(candidates):
            front[candidates] = front_layer(view, candidates, view.position[candidates][:, list(axes)], direction,
                                            texel, slope=True)
        return front

    def _apply_projection(self, evaluate, blend, opacity, occlusion=None, mirror=None):
        """Paint a projection: ``evaluate(rows_list) -> (colors (N, 4), keep (N,))`` over the rows of the region's
        faces, concatenated. Pixel mode paints the texel centres; smooth mode averages each texel over its area
        (``supersample``), so edges of the projection and of the image are anti-aliased and an image larger than the
        texel is filtered instead of sampled at one point.

        ``occlusion=(direction, axes)``: keep only the texels on the front-most surface layer along ``direction``
        (axes: the two model axes of the projection plane), with the same slope-aware test strokes use.

        ``mirror="x"``: paint the source half only and copy each texel onto its mirror image (exact reflection of the
        UV charts, as strokes do), so both halves are identical by construction; texels with no mirror image on an
        asymmetric surface are painted directly. The projection must cover the source (+x) side."""
        if mirror not in (None, "x"):
            raise ValueError("mirror must be None or 'x'")
        entries = [(face, rows) for face, rows in self._entries if len(rows)]
        if not entries:
            return
        rows_list = [rows for _, rows in entries]
        painter = _texture_painter_of(entries)
        smooth = painter is not None and painter.render.smooth
        colors, keep = evaluate(rows_list)
        front = None
        if occlusion is not None:
            front = self._front_mask(painter, rows_list, keep, *occlusion)
        if smooth:
            colors, coverage = supersample(painter, rows_list, evaluate, center=(colors, keep))
            colors = np.array(colors, dtype=float)
            colors[:, 3] *= coverage * (1.0 if front is None else front)
            keep = colors[:, 3] > 0
            colors = np.clip(np.rint(colors), 0, 255).astype(np.int64)
        elif front is not None:
            keep = keep & front
        if mirror == "x":
            if painter is None:
                raise ValueError("mirror needs texels of a TexturePainter")
            from .projection import region_view
            partner, copy = region_view(painter, entries).mirror_of()
            has = copy & (partner >= 0)             # the mirrored side takes the exact RGBA of its source texel
            colors, keep = colors.copy(), keep.copy()
            colors[has], keep[has] = colors[partner[has]], keep[partner[has]]
        start = 0
        for face, rows in entries:
            stop = start + len(rows)
            self._blend_into(face, rows, keep[start:stop], colors[start:stop][keep[start:stop]], blend, opacity)
            start = stop

    def fill(self, color):
        c = np.array(parse_color(color))
        for face, rows in self._entries:
            if len(rows):
                face.canvas.write_pixels(rows.x, rows.y, np.tile(c, (len(rows), 1)))
        return self

    def paint_surface(self, callback):
        if not callable(callback):
            raise TypeError("paint_surface callback must be callable")
        parsed = {}  # callbacks repeat a few colors; validate each distinct value once
        for face, rows in self._entries:
            painted, colors = [], []
            for index, sample in enumerate(rows):
                color = callback(sample)
                if color is not None:
                    painted.append(index)
                    # Only exact int tuples and strings are cached: True == 1 must still be rejected.
                    cacheable = type(color) is str or (type(color) is tuple and all(type(v) is int for v in color))
                    rgba = parsed.get(color) if cacheable else None
                    if rgba is None:
                        rgba = parse_color(color)
                        if cacheable:
                            parsed[color] = rgba
                    colors.append(rgba)
            if painted:
                painted = np.array(painted)
                face.canvas.write_pixels(rows.x[painted], rows.y[painted], colors)
        return self

    def paint_surface_arrays(self, callback):
        """Vectorized paint_surface: ``callback(rows)`` gets one face's samples as arrays.

        ``rows`` has ``x``, ``y`` and (N, k) arrays ``face_uv``, ``element_position``,
        ``model_position``, ``element_normal``, ``model_normal``, ``normalized_position``,
        ``coverage_fraction``, plus ``element_name``, ``face_name`` and ``tags``. It returns
        an (N, 4) array of 0-255 RGBA values, ``(colors, keep)`` to paint only rows where the
        boolean ``keep`` is true, or None to leave the face unchanged.
        """
        if not callable(callback):
            raise TypeError("paint_surface_arrays callback must be callable")

        def evaluate(rows):
            result = callback(rows)
            if result is None:
                return None
            colors, keep = result if isinstance(result, tuple) else (result, None)
            colors = np.asarray(colors, dtype=float)
            if colors.shape != (len(rows), 4):
                raise ValueError(f"paint_surface_arrays: expected colors of shape ({len(rows)}, 4), got {colors.shape}")
            if not np.isfinite(colors).all() or colors.min() < 0 or colors.max() > 255:
                raise ValueError("paint_surface_arrays: colors must be finite 0-255 values")
            keep = np.ones(len(rows), dtype=bool) if keep is None else np.asarray(keep, dtype=bool)
            return colors, keep

        painter = _texture_painter_of(self._entries)
        smooth = painter is not None and painter.render.smooth
        for face, rows in self._entries:
            if not len(rows):
                continue
            result = evaluate(rows)
            if result is None:
                continue
            if smooth:
                # Smooth mode: the colour of a texel is the average over its area (anti-aliased shapes and edges).
                colors, coverage = supersample(painter, [rows], lambda part: evaluate(part[0]) or (
                    np.zeros((len(part[0]), 4)), np.zeros(len(part[0]), dtype=bool)), center=result)
                _write_coverage(face, rows, colors, coverage)
                continue
            colors, keep = result
            face.canvas.write_pixels(rows.x[keep], rows.y[keep], np.rint(colors[keep]))
        return self

    _FIELD_SPACES = {"model": ("model_position", "model_normal"), "element": ("element_position", "element_normal"),
                     "normalized": ("normalized_position", "element_normal"), "uv": ("face_uv", None)}

    def paint_field(self, shader, *, space="model", where=None, blend="normal", opacity=1.0):
        if not isinstance(shader, Shader):
            raise TypeError("paint_field needs a Shader: finish the field with .ramp(colors) or .dither(colors)")
        if space not in self._FIELD_SPACES:
            raise ValueError(f"space must be one of {', '.join(self._FIELD_SPACES)}")
        position_key, normal_key = self._FIELD_SPACES[space]
        entries = [(face, rows) for face, rows in self._entries if len(rows)]
        if not entries:
            return self
        if where is not None and not isinstance(where, Field) and not callable(where):
            raise TypeError("where must be a Field or a callable rows -> boolean array")

        def evaluate(rows_list):
            position = np.concatenate([np.asarray(rows.fields[position_key], dtype=float) for rows in rows_list])
            if position.shape[1] == 2:
                position = np.concatenate([position, np.zeros((len(position), 1))], axis=1)
            normal = None if normal_key is None else np.concatenate([rows.fields[normal_key] for rows in rows_list])
            pixels = (np.concatenate([rows.x for rows in rows_list]), np.concatenate([rows.y for rows in rows_list]))
            frame = Frame(position[:, 0], position[:, 1], position[:, 2], normal=normal, pixel=pixels)
            colors = np.array(shader.render(frame), dtype=float)
            if colors.shape != (len(position), 4):
                raise ValueError(f"paint_field: shader returned {colors.shape}, expected ({len(position)}, 4)")
            keep = colors[:, 3] > 0
            if isinstance(where, Field):
                colors[:, 3] *= where._eval(frame)
                keep &= colors[:, 3] > 0
            elif where is not None:
                keep &= np.concatenate([np.asarray(where(rows), dtype=bool) for rows in rows_list])
            return colors, keep

        rows_list = [rows for _, rows in entries]
        painter = _texture_painter_of(entries)
        if painter is not None and painter.render.smooth:
            colors, coverage = supersample(painter, rows_list, evaluate)
            colors[:, 3] *= coverage
            keep = colors[:, 3] > 0
        else:
            colors, keep = evaluate(rows_list)
        colors = np.clip(np.rint(colors), 0, 255).astype(np.int64)
        start = 0
        for face, rows in entries:
            stop = start + len(rows)
            face_keep = keep[start:stop]
            if face_keep.any():
                self._blend_into(face, rows, face_keep, colors[start:stop][face_keep], blend, opacity)
            start = stop
        return self

    def apply_noise(self, variance=8, seed=None):
        if isinstance(variance, bool) or not isinstance(variance, int) or variance < 0:
            raise ValueError("variance must be a non-negative integer")
        if variance == 0:
            return self
        for face, rows in self._entries:
            if not len(rows):
                continue
            canvas = face.canvas
            current = canvas.read_pixels(rows.x, rows.y)
            visible = np.nonzero(current[:, 3])[0]
            positions = rows.fields["element_position"][visible].tolist()
            deltas = []
            for position in positions:
                position = tuple(round(value, 9) for value in position)
                digest = hashlib.sha256(
                    f"{0 if seed is None else seed}:{rows.element_name}:{position}".encode("utf-8")
                ).digest()
                deltas.append(random.Random(int.from_bytes(digest[:8], "big")).randint(-variance, variance))
            noisy = current[visible].copy()
            noisy[:, :3] = clamp_bytes(noisy[:, :3] + np.array(deltas, dtype=np.int64)[:, None])
            canvas.write_pixels(rows.x[visible], rows.y[visible], noisy)
        return self

    def apply_gradient(self, start_color, end_color, *, axis="y"):
        normalized_axis = str(axis).lower()
        if normalized_axis not in ("x", "y", "z"):
            raise ValueError("gradient axis must be x, y, or z")
        index = "xyz".index(normalized_axis)
        for face, rows in self._entries:
            if len(rows):
                face.canvas.write_pixels(rows.x, rows.y, lerp_rows(
                    start_color, end_color, rows.fields["normalized_position"][:, index]))
        return self

    def band(self, axis, start, end):
        normalized_axis = str(axis).lower()
        if normalized_axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y, or z")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end)):
            raise ValueError("band start/end must be finite numbers")
        if not 0 <= start <= end <= 1:
            raise ValueError("band requires 0 <= start <= end <= 1")
        index = "xyz".index(normalized_axis)
        filtered = []
        for face, rows in self._entries:
            value = rows.fields["normalized_position"][:, index]
            keep = (start - 1e-9 <= value) & (value <= end + 1e-9)
            if keep.any():
                filtered.append((face, rows.subset(keep)))
        return SurfaceRegion(filtered)

    def patch(self, side, center=(0.5, 0.5), size=(0.5, 0.5)):
        aliases = {"north": "front", "south": "back", "up": "top", "down": "bottom"}
        side = aliases.get(str(side).lower(), str(side).lower())
        definitions = {
            "front": ((0, 0, 1), (0, 1)),
            "back": ((0, 0, -1), (0, 1)),
            "east": ((1, 0, 0), (2, 1)),
            "west": ((-1, 0, 0), (2, 1)),
            "top": ((0, 1, 0), (0, 2)),
            "bottom": ((0, -1, 0), (0, 2)),
        }
        if side not in definitions:
            raise ValueError("side must be front, back, east, west, top, or bottom")
        if (not isinstance(center, (tuple, list)) or len(center) != 2 or
                not isinstance(size, (tuple, list)) or len(size) != 2):
            raise ValueError("patch center and size must contain two numbers")
        values = tuple(center) + tuple(size)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
               not math.isfinite(value) for value in values):
            raise ValueError("patch center and size must contain finite numbers")
        if any(value <= 0 or value > 1 for value in size) or any(value < 0 or value > 1 for value in center):
            raise ValueError("patch center must be in [0,1] and size in (0,1]")

        direction, axes = definitions[side]
        half = (size[0] / 2.0, size[1] / 2.0)
        filtered = []
        for face, rows in self._entries:
            tp = getattr(getattr(face, "element_painter", None), "texture_painter", None)
            dir_vec = tp.direction_vectors.get(side, direction) if tp else direction
            keep = _patch_rows(rows, dir_vec, axes, center, half)
            if keep.any():
                filtered.append((face, rows.subset(keep)))
        return SurfaceRegion(filtered)

    def project_decal(
        self,
        source: Union[str, Path, Image.Image, Tuple[List[str], Dict[str, ColorType]], List[str], FaceCanvas],
        *,
        side: str = "front",
        center: Tuple[float, float] = (0.5, 0.5),
        size: Tuple[float, float] = (0.5, 0.5),
        rotation: float = 0.0,
        filtering: str = "nearest",
        blend: str = "normal",
        opacity: float = 1.0,
        palette: Optional[Dict[str, ColorType]] = None,
        normal_threshold: float = 0.0,
        layers: str = "all",
        fade: Optional[Tuple[float, float]] = None,
        mirror: Optional[str] = None,
    ) -> 'SurfaceRegion':
        """``layers="front"`` paints only the surface layer in front along ``side`` (a wall behind another, such as
        the inside of a collar, stays untouched); ``"all"`` (default) paints every facing layer."""
        if layers not in ("all", "front"):
            raise ValueError("layers must be 'all' or 'front'")
        if fade is not None and not (len(fade) == 2 and fade[0] < fade[1]):
            raise ValueError("fade must be (facing_start, facing_full) with facing_start < facing_full")
        image = _image_rows(_resolve_decal_image(source, palette=palette))
        clean_side, dir_vec, axes, flip_v = decal_frame(self._direction_vectors(), side)

        half_w = size[0] / 2.0
        half_h = size[1] / 2.0
        min_x = center[0] - half_w
        max_x = center[0] + half_w
        min_y = center[1] - half_h
        max_y = center[1] + half_h

        rot_rad = math.radians(-rotation) if rotation else 0.0
        cos_rot = math.cos(rot_rad) if rotation else 1.0
        sin_rot = math.sin(rot_rad) if rotation else 0.0

        def evaluate(rows_list):
            colors_out, keep_out = [], []
            for rows in rows_list:
                normal = rows.fields["element_normal"]
                facing = python_sum([normal[:, i] * dir_vec[i] for i in range(3)])
                keep = facing > (normal_threshold if fade is None else fade[0])
                px = rows.fields["normalized_position"][:, axes[0]]
                py = rows.fields["normalized_position"][:, axes[1]]
                keep &= (min_x - 1e-9 <= px) & (px <= max_x + 1e-9) & (min_y - 1e-9 <= py) & (py <= max_y + 1e-9)

                u = (px - min_x) / size[0]
                v = 1.0 - (py - min_y) / size[1] if flip_v else (py - min_y) / size[1]
                if rotation:
                    du = u - 0.5
                    dv = v - 0.5
                    u = 0.5 + (du * cos_rot - dv * sin_rot)
                    v = 0.5 + (du * sin_rot + dv * cos_rot)
                keep &= (0.0 <= u) & (u <= 1.0) & (0.0 <= v) & (v <= 1.0)

                u, v = np.where(keep, u, 0.0), np.where(keep, v, 0.0)
                colors = (_sample_bilinear_rows(image, u, v) if filtering == "bilinear"
                          else _sample_nearest_rows(image, u, v))
                keep &= colors[:, 3] != 0
                if fade is not None:        # the projection fades out as the surface turns edge-on to it
                    colors = colors.copy()
                    colors[:, 3] = np.rint(colors[:, 3] * np.clip((facing - fade[0]) / (fade[1] - fade[0]), 0.0, 1.0))
                    keep &= colors[:, 3] > 0
                colors_out.append(colors)
                keep_out.append(keep)
            return np.concatenate(colors_out), np.concatenate(keep_out)

        self._apply_projection(evaluate, blend, opacity, occlusion=(dir_vec, axes) if layers == "front" else None,
                               mirror=mirror)
        return self

    def project_triplanar(
        self,
        source: Union[str, Path, Image.Image, FaceCanvas],
        *,
        scale: float = 1.0,
        blend_sharpness: float = 4.0,
        filtering: str = "nearest",
        blend: str = "normal",
        opacity: float = 1.0,
        mirror: Optional[str] = None,
    ) -> 'SurfaceRegion':
        image = _image_rows(_resolve_decal_image(source))
        weight_cache = {}

        def axis_weights(normal):
            if normal not in weight_cache:
                nx, ny, nz = normal
                wx = abs(nx) ** blend_sharpness
                wy = abs(ny) ** blend_sharpness
                wz = abs(nz) ** blend_sharpness
                w_sum = wx + wy + wz
                if w_sum <= 1e-9:
                    wx, wy, wz = 1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0
                else:
                    wx /= w_sum
                    wy /= w_sum
                    wz /= w_sum
                weight_cache[normal] = (wx, wy, wz)
            return weight_cache[normal]

        sample = ((lambda u, v: _sample_bilinear_rows(image, u, v, wrap=True)) if filtering == "bilinear"
                  else (lambda u, v: _sample_nearest_rows(image, u, v)))
        def evaluate(rows_list):
            colors_out, keep_out = [], []
            for rows in rows_list:
                # Weights depend only on the normal; flat faces share a few distinct normals.
                unique, inverse = np.unique(rows.fields["model_normal"], axis=0, return_inverse=True)
                table = np.array([axis_weights(tuple(n)) for n in unique.tolist()]).reshape(-1, 3)
                weights = table[np.asarray(inverse).reshape(-1)]
                x, y, z = (rows.fields["model_position"][:, i] for i in range(3))
                cx = sample((z * scale) % 1.0, (1.0 - (y * scale)) % 1.0)
                cy = sample((x * scale) % 1.0, (z * scale) % 1.0)
                cz = sample((x * scale) % 1.0, (1.0 - (y * scale)) % 1.0)
                colors = clamp_bytes(cx * weights[:, 0:1] + cy * weights[:, 1:2] + cz * weights[:, 2:3])
                colors_out.append(colors)
                keep_out.append(colors[:, 3] != 0)
            return np.concatenate(colors_out), np.concatenate(keep_out)

        self._apply_projection(evaluate, blend, opacity, mirror=mirror)
        return self


class ElementSelection(SurfaceTarget):
    """Immutable semantic selection of complete elements."""

    def __init__(self, painter, elements, *, slot: Optional[int] = None):
        self.slot = slot
        self.painter = painter
        self.elements = tuple(elements)

    def _to_surface_region(self) -> SurfaceRegion:
        return SurfaceRegion(
            entry for element in self.elements
            for entry in element._surface_region(face_names=self._face_names_for(element))._entries
        )

    def __len__(self):
        return len(self.elements)

    def fill_all(self, color):
        for element in self.elements:
            face_names = self._face_names_for(element)
            if face_names is None:
                element.fill_all(color)
            else:
                for fname in face_names:
                    fp = element.faces[fname]
                    if not isinstance(fp, SharedFacePainter):
                        fp.fill(color)
        return self

    fill = fill_all

    def apply_noise(self, variance=8, seed=None):
        for element in self.elements:
            face_names = self._face_names_for(element)
            if face_names is None:
                element.apply_noise_all(variance, seed=_derived_seed(seed, element.name, "selection"))
            else:
                for fname in face_names:
                    fp = element.faces[fname]
                    if not isinstance(fp, SharedFacePainter):
                        fp.apply_noise(variance, seed=_derived_seed(seed, element.name, fname))

    def _face_names_for(self, element: 'ElementPainter') -> Optional[set]:
        if self.slot is None:
            return None
        return {fname for fname, face in element.faces.items() if face.uv_info.get("texture", 0) == self.slot}
        return self


class FaceGroupPainter(SurfaceTarget):
    """Apply one operation to the paintable owner faces in a semantic group."""
    def __init__(self, element_painter, name, faces):
        self.element_painter = element_painter
        self.name = name
        self.faces = tuple(faces)

    def _to_surface_region(self) -> SurfaceRegion:
        return self.element_painter._surface_region(
            face_names={face.face_name for face in self.faces}
        )

    def fill(self, color):
        for face in self.faces:
            face.fill(color)
        return self

    def apply_noise(self, variance=8, seed=None):
        for face in self.faces:
            face.apply_noise(variance, seed=_derived_seed(seed, self.element_painter.name, face.face_name))
        return self


class ElementPainter(SurfaceTarget):
    """Interface para manipular todas as faces de um cubo/elemento."""
    VALID_FACES = ['north', 'south', 'east', 'west', 'up', 'down']

    def __init__(self, texture_painter: 'TexturePainter', name: str, element_data: dict):
        self.texture_painter = texture_painter
        self.name = name
        self.element_data = element_data
        self.tags = tuple(element_data.get("tags", ()))
        self.faces: Dict[str, Union[FacePainter, SharedFacePainter]] = {}
        grouped = {}

        for face_name, face_info in element_data.get('faces', {}).items():
            if face_info.get('owner'):
                self.faces[face_name] = SharedFacePainter(face_info)
                continue
            self.faces[face_name] = FacePainter(self, face_name, uv_info=face_info)
            if face_info.get('group'):
                grouped.setdefault(face_info['group'], []).append(self.faces[face_name])
        self.groups = {group: FaceGroupPainter(self, group,
                       sorted(faces, key=lambda face: face.face_name))
                       for group, faces in grouped.items()}

    def _to_surface_region(self) -> SurfaceRegion:
        return self._surface_region()

    def face(self, face_name: str) -> FacePainter:
        face_name = face_name.lower()
        alias_map = self.texture_painter.direction_aliases
        if 'quad' in self.faces and face_name in ('quad', 'mesh', 'front', 'north'):
            face_name = 'quad'
        else:
            face_name = alias_map.get(face_name, face_name)
        if face_name not in self.faces:
            raise KeyError(f"Face '{face_name}' does not exist on element '{self.name}'. Available: {list(self.faces.keys())}")
        return self.faces[face_name]

    def group(self, group_name: str) -> FaceGroupPainter:
        if group_name not in self.groups:
            raise KeyError(f"Group '{group_name}' does not exist in element '{self.name}'. Available: {list(self.groups)}")
        return self.groups[group_name]

    def __getattr__(self, item: str) -> FacePainter:
        alias_map = self.texture_painter.direction_aliases
        if 'quad' in self.faces and item.lower() in ('quad', 'mesh', 'front', 'north'):
            key = 'quad'
        else:
            key = alias_map.get(item.lower(), item)
        if key in self.faces:
            return self.faces[key]
        raise AttributeError(f"Element '{self.name}' has no attribute or face '{item}'")

    def fill_all(self, color: ColorType) -> 'ElementPainter':
        """Fill all faces with the specified color."""
        for face_painter in self.faces.values():
            if not isinstance(face_painter, SharedFacePainter):
                face_painter.fill(color)
        return self

    fill = fill_all

    def apply_noise_all(self, variance: int = 8, seed: Optional[int] = None) -> 'ElementPainter':
        """Apply noise to all faces."""
        for face_name, face_painter in self.faces.items():
            if isinstance(face_painter, SharedFacePainter):
                continue
            face_painter.apply_noise(variance, seed=_derived_seed(seed, self.name, face_name))
        return self

    apply_noise = apply_noise_all

    def fill_box(self,
                 top: Optional[ColorType] = None,
                 bottom: Optional[ColorType] = None,
                 sides: Optional[ColorType] = None,
                 north: Optional[ColorType] = None,
                 south: Optional[ColorType] = None,
                 east: Optional[ColorType] = None,
                 west: Optional[ColorType] = None,
                 front: Optional[ColorType] = None,
                 back: Optional[ColorType] = None,
                 up: Optional[ColorType] = None,
                 down: Optional[ColorType] = None) -> 'ElementPainter':
        """Atribuição rápida por lados (top, bottom, sides ou faces individuais)."""
        top = top if top is not None else up
        bottom = bottom if bottom is not None else down

        if sides:
            for side in ['north', 'south', 'east', 'west']:
                if side in self.faces:
                    self.faces[side].fill(sides)
        if top and self.texture_painter.direction_aliases['top'] in self.faces:
            self.faces[self.texture_painter.direction_aliases['top']].fill(top)
        if bottom and self.texture_painter.direction_aliases['bottom'] in self.faces:
            self.faces[self.texture_painter.direction_aliases['bottom']].fill(bottom)
        if front and self.texture_painter.direction_aliases['front'] in self.faces:
            self.faces[self.texture_painter.direction_aliases['front']].fill(front)
        if back and self.texture_painter.direction_aliases['back'] in self.faces:
            self.faces[self.texture_painter.direction_aliases['back']].fill(back)
        if north and 'north' in self.faces:
            self.faces['north'].fill(north)
        if south and 'south' in self.faces:
            self.faces['south'].fill(south)
        if east and 'east' in self.faces:
            self.faces['east'].fill(east)
        if west and 'west' in self.faces:
            self.faces['west'].fill(west)
        return self

    def _surface_entries(self, face_names=None):
        entries = []
        followers = []
        for face_name, face in self.faces.items():
            if face_names is not None and face_name not in face_names:
                continue
            if isinstance(face, SharedFacePainter):
                if not face.uv_info.get('region'):
                    followers.append((face_name, face.owner))
                # A flat UV region (one colour) shows its owner's island: painting the owner paints it.
                continue
            samples = self.texture_painter.surface_sampler.samples(self.name, face_name, face)
            entries.append((face, samples))
        if followers:
            refs = ", ".join(f"{self.name}.{name}->{owner[0]}.{owner[1]}"
                             for name, owner in followers[:3])
            raise ValueError(
                f"Spatial painting cannot evaluate shared UV followers ({refs}); "
                "paint the owner or request independent UVs")
        return entries

    def _surface_region(self, predicate=None, face_names=None, *, rows_predicate=None):
        """Region of this element; ``predicate`` tests SurfaceSample objects,
        ``rows_predicate`` tests a FaceSamples at once and returns a boolean array."""
        entries = []
        for face, samples in self._surface_entries(face_names):
            if rows_predicate is not None:
                keep = rows_predicate(samples)
            elif predicate is not None:
                keep = np.array([bool(predicate(sample)) for sample in samples], dtype=bool)
            else:
                keep = None
            selected = samples if keep is None else samples.subset(keep)
            if len(selected):
                entries.append((face, selected))
        return SurfaceRegion(entries)

    def _band(self, axis, start, end, face_names=None):
        normalized = str(axis).lower()
        if normalized not in ("x", "y", "z"):
            raise ValueError("axis must be x, y, or z")
        index = "xyz".index(normalized)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
               not math.isfinite(value) for value in (start, end)):
            raise ValueError("band start/end must be finite numbers")
        if not 0 <= start <= end <= 1:
            raise ValueError("band requires 0 <= start <= end <= 1")
        low, high = self.texture_painter.surface_sampler.bounds[self.name]
        if abs(high[index] - low[index]) <= 1e-9:
            raise ValueError(f"{self.name}: zero-size bounds along {axis}")
        def selected(rows):
            value = rows.fields["normalized_position"][:, index]
            return (start - 1e-9 <= value) & (value <= end + 1e-9)

        return self._surface_region(face_names=face_names, rows_predicate=selected)

    def band(self, axis, start, end):
        return self._band(axis, start, end)

    def _patch(self, side, center, size, face_names=None):
        vectors = self.texture_painter.direction_vectors
        aliases = {alias: name for alias, vector in (("north", (0, 0, -1)), ("south", (0, 0, 1)),
                                                     ("up", (0, 1, 0)), ("down", (0, -1, 0)))
                   for name in [next((k for k, v in vectors.items() if tuple(v) == vector), None)] if name}
        side = aliases.get(str(side).lower(), str(side).lower())
        definitions = {
            "front": (self.texture_painter.direction_vectors["front"], (0, 1)),
            "back": (self.texture_painter.direction_vectors["back"], (0, 1)),
            "east": ((1, 0, 0), (2, 1)),
            "west": ((-1, 0, 0), (2, 1)),
            "top": (self.texture_painter.direction_vectors["top"], (0, 2)),
            "bottom": (self.texture_painter.direction_vectors["bottom"], (0, 2)),
        }
        if side not in definitions:
            raise ValueError("side must be front (north), back (south), east, west, top (up) or bottom (down)")
        if (not isinstance(center, (tuple, list)) or len(center) != 2 or
                not isinstance(size, (tuple, list)) or len(size) != 2):
            raise ValueError("patch center and size must contain two numbers")
        values = tuple(center) + tuple(size)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or
               not math.isfinite(value) for value in values):
            raise ValueError("patch center and size must contain finite numbers")
        if any(value <= 0 or value > 1 for value in size) or any(value < 0 or value > 1 for value in center):
            raise ValueError("patch center must be in [0,1] and size in (0,1]")
        direction, axes = definitions[side]
        low, high = self.texture_painter.surface_sampler.bounds[self.name]
        if any(abs(high[index] - low[index]) <= 1e-9 for index in axes):
            raise ValueError(f"{self.name}: zero-size projected bounds for {side}")
        half = (size[0] / 2, size[1] / 2)
        return self._surface_region(face_names=face_names, rows_predicate=lambda rows: _patch_rows(
            rows, direction, axes, center, half))

    def patch(self, side, center=(0.5, 0.5), size=(0.5, 0.5)):
        return self._patch(side, center, size)


class TextureLayer:
    """Uma camada independente de pintura em memória com suas próprias faces."""
    def __init__(self, name: str, painter: 'TexturePainter'):
        self.name = name
        self.painter = painter
        self.visible = True
        self.opacity = 1.0
        self.blend_mode = "normal"
        self.canvases: Dict[Tuple[str, str], FaceCanvas] = {}
        self._init_canvases()

    def _init_canvases(self):
        for elem_name, elem_data in self.painter.parser.elements.items():
            for face_name, face_info in elem_data.get('faces', {}).items():
                if face_info.get('owner'):
                    continue
                rot = face_info['rotation']
                w = face_info['w']
                h = face_info['h']
                canvas_w, canvas_h = (h, w) if rot in (90, 270) else (w, h)
                if face_info.get('layout') == 'polygon':
                    canvas = PolygonFaceCanvas(canvas_w, canvas_h, face_info['canvas_points'],
                                               conservative=face_info.get('conservative', False),
                                               mask=face_info.get('owned_mask'))
                else:
                    canvas = FaceCanvas(canvas_w, canvas_h)
                self.canvases[(elem_name, face_name)] = canvas

    def get_canvas(self, elem_name: str, face_name: str) -> FaceCanvas:
        return self.canvases[(elem_name, face_name)]

    def clear(self, color=(0, 0, 0, 0)):
        for canvas in self.canvases.values():
            canvas.clear(color)
        return self

    def compose_atlas(self, edge_dilation: int = 0, *, slot: int = 0) -> Image.Image:
        """Gera a imagem deste layer específico como um atlas RGBA transparente."""
        slot_info = self.painter.parser.texture_slots[slot]
        layer_atlas = Image.new("RGBA", (slot_info["width"], slot_info["height"]), (0, 0, 0, 0))
        chart_boxes = []
        for (elem_name, face_name), canvas in self.canvases.items():
            elem_data = self.painter.parser.elements[elem_name]
            info = elem_data['faces'][face_name]
            if info.get('owner') or info.get('texture', 0) != slot:
                continue
            img = canvas.to_image()
            if info.get('chart'):
                # Chart faces own disjoint texels: paste them as they are and dilate the whole chart afterwards,
                # so a face never spills over its neighbour inside the chart.
                layer_atlas.alpha_composite(img, (info['x'], info['y']))
                chart_boxes.append((info['x'], info['y'], info['x'] + info['w'], info['y'] + info['h']))
                continue

            # 1. Rotação UV
            rot = info['rotation']
            if rot == 90:
                img = img.transpose(Image.ROTATE_270)
            elif rot == 180:
                img = img.transpose(Image.ROTATE_180)
            elif rot == 270:
                img = img.transpose(Image.ROTATE_90)

            # 2. Inversão Horizontal
            if info['flip_x']:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)

            # 3. Inversão Vertical
            if info['flip_y']:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)

            # 4. Cola no atlas do layer
            if info.get('layout') == 'polygon':
                if edge_dilation:
                    img = _dilate_rgba(img, edge_dilation)
                layer_atlas.alpha_composite(
                    img, (info['x'] - edge_dilation, info['y'] - edge_dilation))
            else:
                layer_atlas.paste(img, (info['x'], info['y']))

        if edge_dilation and chart_boxes:
            # Grow chart borders into the padding only: texels no face owns.
            dilated = np.asarray(_dilate_rgba(layer_atlas, edge_dilation))[
                edge_dilation:-edge_dilation, edge_dilation:-edge_dilation]
            claimed = self.painter.parser.claimed_by_slot[slot]
            zone = np.zeros(claimed.shape, dtype=bool)
            for x0, y0, x1, y1 in chart_boxes:
                zone[max(0, y0 - edge_dilation):y1 + edge_dilation, max(0, x0 - edge_dilation):x1 + edge_dilation] = True
            pixels = np.array(layer_atlas)
            take = zone & ~claimed & (pixels[..., 3] == 0)
            pixels[take] = dilated[take]
            layer_atlas = Image.fromarray(pixels, "RGBA")

        if self.opacity < 1.0:
            r, g, b, a = layer_atlas.split()
            a = a.point(lambda p: int(p * self.opacity))
            layer_atlas.putalpha(a)

        return layer_atlas


class LayerContext:
    """Context manager e proxy para direcionar operações para uma camada específica."""
    def __init__(self, painter: 'TexturePainter', layer_name: str):
        self.painter = painter
        self.layer_name = layer_name
        self.prev_layer_name = painter.active_layer_name

    def __enter__(self):
        self.painter.set_active_layer(self.layer_name)
        return self.painter

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.painter.set_active_layer(self.prev_layer_name)

    def __getattr__(self, item: str):
        self.painter.set_active_layer(self.layer_name)
        return getattr(self.painter, item)


def _face_densities(data):
    """(element, face) -> pixels per model unit under the document's UV rules; {} without rules.

    ``flat`` and ``fixed`` faces get the density their island gives their area."""
    packing = data.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {})
    if not packing.get("rules"):
        return {}
    from Tools.uv_rules import resolve_specs
    specs = resolve_specs(data, packing["rules"], uv_scale=packing.get("uv_scale", 1),
                          layout=packing.get("layout", "faces"))
    elements = {elem.get("name"): elem for elem in data.get("elements", [])}
    out = {}
    for (name, face), spec in specs.items():
        if spec.layout not in ("flat", "fixed"):
            out[name, face] = float(spec.density)
            continue
        elem = elements[name]
        if elem.get("type", "cube") == "cube":
            x, y, z = (abs(b - a) for a, b in zip(elem["from"], elem["to"]))
            area = dict(north=x * y, south=x * y, east=z * y, west=z * y, up=x * z, down=x * z)[face]
        else:
            points = np.array([elem["vertices"][key] for key in elem["faces"][face]["vertices"]], dtype=float)
            area = 0.5 * float(np.linalg.norm(sum(np.cross(a, b) for a, b in zip(points, np.roll(points, -1, axis=0)))))
        out[name, face] = math.sqrt(spec.size[0] * spec.size[1] / area) if area > 0 else float(spec.density)
    return out


class TexturePainter:
    """
    Main API for procedural creation and painting of textures for Blockbench models.
    Supports non-destructive layers, 3D decal projections, triplanar mapping,
    surface sampling, and verified export.
    """
    def __init__(self, bbmodel_path: str, base_image: Optional[Image.Image] = None, *, render=None):
        """``render``: the render mode (``pixel``/``smooth``, a ``RenderMode``); default: the asset's, from
        its ``texture_filter`` and ``render`` record in ``project.json`` (pixel art for an unregistered model)."""
        from .render_mode import RenderMode, for_model, preset
        self.bbmodel_path = os.path.abspath(bbmodel_path)
        self.render = (for_model(self.bbmodel_path) if render is None else
                       preset(render) if isinstance(render, str) else render)
        if not isinstance(self.render, RenderMode):
            raise TypeError("render must be 'pixel', 'smooth' or a RenderMode")
        self.parser = BlockbenchModelParser(self.bbmodel_path)
        self.surface_sampler = SurfaceSampler(self.parser.data)
        self.direction_aliases, self.direction_vectors = _orientation_contract(self.parser.data)
        self._geometry_fields = None
        self.width = self.parser.tex_width
        self.height = self.parser.tex_height
        self.atlases: Dict[int, Image.Image] = {
            idx: Image.new("RGBA", (slot["width"], slot["height"]), (0, 0, 0, 0))
            for idx, slot in enumerate(self.parser.texture_slots)
        }

        # Imagem base de fundo (geralmente transparente)
        if base_image:
            if base_image.size != (self.width, self.height):
                raise ValueError("Base image resolution must match the UV atlas; resizing is forbidden")
            self.atlas = base_image.copy().convert("RGBA")
        else:
            self.atlas = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))

        # Sistema de camadas
        self._layers: Dict[str, TextureLayer] = {}
        self.active_layer_name = "base"
        self.add_layer("base")

        # ElementPainters
        self.elements: Dict[str, ElementPainter] = {}
        for elem_name, elem_data in self.parser.elements.items():
            self.elements[elem_name] = ElementPainter(self, elem_name, elem_data)

    @classmethod
    def from_bbmodel(cls, bbmodel_path: str, load_existing_texture=None, *, render=None) -> 'TexturePainter':
        if load_existing_texture is not None:
            warnings.warn(
                "load_existing_texture is deprecated and has no effect; TexturePainter starts blank",
                DeprecationWarning,
                stacklevel=2,
            )
        return cls(bbmodel_path, render=render)

    @staticmethod
    def create_canvas(width: int, height: int, background: ColorType = (0, 0, 0, 0)) -> DecalCanvas:
        """Create an in-memory 2D canvas for decal drafts or procedural patterns."""
        return DecalCanvas(width, height, background=background)

    @property
    def atlas(self) -> Image.Image:
        return self.atlases[0]

    @atlas.setter
    def atlas(self, val: Image.Image):
        self.atlases[0] = val

    def _slot_index(self, texture: Union[int, str] = 0) -> int:
        slots = self.parser.texture_slots
        if not isinstance(texture, bool) and isinstance(texture, int):
            if 0 <= texture < len(slots):
                return texture
            raise ValueError(f"Unknown texture slot index {texture}; model has {len(slots)} slot(s)")
        if isinstance(texture, str) and texture:
            for idx, slot in enumerate(slots):
                if slot["name"] == texture:
                    return idx
            known = [s["name"] for s in slots]
            raise ValueError(f"Unknown texture slot {texture!r}; texture slots on this model: {known}")
        raise ValueError("texture must be a non-empty slot name or slot index")

    @property
    def active_layer(self) -> TextureLayer:
        return self._layers[self.active_layer_name]

    def add_layer(self, name: str, *, blend: Optional[str] = None, opacity: Optional[float] = None) -> TextureLayer:
        """The layer called ``name``, created on first use above the others. ``blend`` (normal, multiply, screen, overlay,
        add) and ``opacity`` set how it composites over the layers under it."""
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Layer name cannot be empty")
        if clean_name not in self._layers:
            self._layers[clean_name] = TextureLayer(clean_name, self)
        layer = self._layers[clean_name]
        if blend is not None:
            if blend not in ("normal", "multiply", "screen", "overlay", "add"):
                raise ValueError("layer blend must be normal, multiply, screen, overlay or add")
            layer.blend_mode = blend
        if opacity is not None:
            if not 0.0 <= float(opacity) <= 1.0:
                raise ValueError("layer opacity must be between 0 and 1")
            layer.opacity = float(opacity)
        return layer

    def set_active_layer(self, name: str) -> 'TexturePainter':
        self.add_layer(name)
        self.active_layer_name = str(name).strip()
        return self

    def layer(self, name: str, *, blend: Optional[str] = None, opacity: Optional[float] = None) -> LayerContext:
        """Paint on the layer called ``name`` (created on first use; ``blend``/``opacity``: see ``add_layer``):
        ``with painter.layer("shading", blend="multiply"): ...``."""
        self.add_layer(name, blend=blend, opacity=opacity)
        return LayerContext(self, str(name).strip())

    def clear_layer(self, name: Optional[str] = None) -> 'TexturePainter':
        target_name = self.active_layer_name if name is None else str(name).strip()
        if target_name in self._layers:
            self._layers[target_name].clear()
        return self

    def export_layers(self, output_dir: Union[str, Path], edge_dilation: int = 0, *,
                      texture: Union[int, str] = 0) -> Dict[str, str]:
        """Exporta cada camada visível como um arquivo PNG transparente independente."""
        out = Path(output_dir).resolve()
        out.mkdir(parents=True, exist_ok=True)
        slot = self._slot_index(texture)
        paths = {}
        for name, layer in self._layers.items():
            if not layer.visible:
                continue
            layer_img = layer.compose_atlas(edge_dilation=edge_dilation, slot=slot)
            layer_path = out / f"{name}.png"
            layer_img.save(layer_path, format="PNG")
            paths[name] = str(layer_path)
        return paths

    def get_active_canvas(self, element_name: str, face_name: str) -> FaceCanvas:
        return self.active_layer.get_canvas(element_name, face_name)

    def clear(self, color: ColorType = (0, 0, 0, 0)) -> 'TexturePainter':
        """Limpa o canvas de base e esvazia todas as camadas."""
        c = parse_color(color)
        for idx, slot in enumerate(self.parser.texture_slots):
            self.atlases[idx] = Image.new("RGBA", (slot["width"], slot["height"]), c)
        for layer in self._layers.values():
            layer.clear()
        return self

    def fill_all(self, color: ColorType) -> 'TexturePainter':
        """Fill all elements in the model with a solid color on the active layer."""
        for elem in self.elements.values():
            elem.fill_all(color)
        return self

    def texel_density(self, faces=None, *, fallback=1) -> float:
        """Pixels per model unit where ``faces`` ((element, face, texel count) triples; None: the whole model) are
        painted: the density of the faces holding most of these texels. Without UV rules it is the document's
        ``uv_packing.uv_scale`` everywhere (``fallback`` when the document has none); with rules
        (``Tools.uv_rules``) each face has its own."""
        densities = self.__dict__.get("_face_densities")
        if densities is None:
            densities = self._face_densities = _face_densities(self.parser.data)
        packing = self.parser.data.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {})
        default = float(packing.get("uv_scale", fallback) or fallback)
        if not densities:
            return default
        weight = {}
        for element, face, count in (faces if faces is not None else
                                     [(name, face, 1) for name, face in densities]):
            density = densities.get((element, face), default)
            weight[density] = weight.get(density, 0) + count
        return max(weight, key=lambda d: (weight[d], d)) if weight else default

    def element(self, name: str) -> ElementPainter:
        if name not in self.elements:
            raise KeyError(f"Element '{name}' does not exist in model. Available: {list(self.elements.keys())}")
        return self.elements[name]

    def select(self, *, tag=None, texture=None, include_ancestors=False):
        if tag is None and texture is None:
            raise ValueError("select requires tag and/or texture")
        if tag is None:
            selected = list(self.elements.values())
        else:
            if not isinstance(tag, str) or not tag:
                raise ValueError("tag must be a non-empty string")
            selected = [
                element for name, element in self.elements.items()
                if tag in self.surface_sampler.tags_for_element(
                    name, include_ancestors=include_ancestors)
            ]
            if not selected and not any(
                    tag in self.surface_sampler.tags_for_element(name, include_ancestors=True) for name in self.elements):
                known = sorted({t for name in self.elements
                                for t in self.surface_sampler.tags_for_element(name, include_ancestors=True)})
                raise ValueError(f"No element or group carries the tag {tag!r}; tags on this model: {known}")
        slot = None if texture is None else self._slot_index(texture)
        if slot is not None:
            selected = [
                element for element in selected
                if any(face.uv_info.get("texture", 0) == slot for face in element.faces.values())
            ]
        return ElementSelection(self, selected, slot=slot)

    def _select_legacy_unused(self, tag, include_ancestors=False):
        if not isinstance(tag, str) or not tag:
            raise ValueError("tag must be a non-empty string")
        selected = [
            element for name, element in self.elements.items()
            if tag in self.surface_sampler.tags_for_element(
                name, include_ancestors=include_ancestors)
        ]
        if not selected and not any(
                tag in self.surface_sampler.tags_for_element(name, include_ancestors=True) for name in self.elements):
            known = sorted({t for name in self.elements
                            for t in self.surface_sampler.tags_for_element(name, include_ancestors=True)})
            raise ValueError(f"No element or group carries the tag {tag!r}; tags on this model: {known}")
        return ElementSelection(self, selected)

    def creases(self, receivers=None, *, max_internal_angle=100, spread=1.0):
        if self._geometry_fields is None:
            self._geometry_fields = ContactFieldDetector(self)
        return self._geometry_fields.creases(
            receivers, max_internal_angle=max_internal_angle, spread=spread)

    def contacts(self, sources=None, receivers=None, *, tolerance, spread=1.0):
        if self._geometry_fields is None:
            self._geometry_fields = ContactFieldDetector(self)
        return self._geometry_fields.contacts(
            sources, receivers, tolerance=tolerance, spread=spread)

    def __getattr__(self, item: str) -> ElementPainter:
        if item in self.elements:
            return self.elements[item]
        raise AttributeError(f"TexturePainter has no element or attribute '{item}'")

    def all_elements(self) -> List[ElementPainter]:
        return list(self.elements.values())

    def surface(self, offset=(0.0, 0.0, 0.0)):
        """Every texel of the model as one ``SurfaceView`` (``Tools.TexturePainter.projection``): per texel the
        model position (``position``; ``centre`` is the texel centre), ``normal``, ``element``, face ``group``,
        ``chart``, the atlas pixel (``x``, ``y``), and ``write`` to paint them. ``offset``: a model shift, or a
        function ``element name -> shift``, applied to the positions (the space a recipe draws in). The view is
        cached until another region is viewed."""
        from .projection import region_view
        entries = [(face, rows) for element in self.elements.values()
                   for face, rows in element._surface_region()._entries if len(rows)]
        return region_view(self, entries, offset)

    def stamp(self, pattern, *, tip, brush, colors, opacity: float = 1.0, blend: str = "normal", mirror=None,
              offset=(0.0, 0.0, 0.0), where=None, **options):
        """``SurfaceTarget.stamp`` over the whole model; ``where`` (bool per texel of ``self.surface(offset)``)
        limits where strokes start and paint, e.g. ``materials.mask("fur")``."""
        from .stamps import paint
        return paint(self.surface(offset), pattern, tip=tip, brush=brush, colors=colors, opacity=opacity,
                     blend=blend, mirror=mirror, where=where, **options)

    def material_map(self, classify, *, offset=(0.0, 0.0, 0.0), key=()):
        """``classify(view) -> (names, material, value, fixed)`` over ``self.surface(offset)``, cached on disk
        (see ``Tools.TexturePainter.materials``). Returns a ``MaterialMap``."""
        from .materials import material_map
        return material_map(self, self.surface(offset), classify, key=key)

    def paint_strokes(self, strokes, *, soft: Optional[float] = None, offset=(0.0, 0.0, 0.0), clean=None):
        """Paint lineart ``strokes`` on every element (limit one with the strokes' ``on=``); see
        ``SurfaceTarget.paint_strokes`` and ``Tools.TexturePainter.ink``. Returns an ``InkReport``."""
        from .ink import paint_strokes
        region = SurfaceRegion(entry for element in self.elements.values()
                               for entry in element._surface_region()._entries)
        return paint_strokes(region, strokes, soft=soft, offset=offset, clean=clean)

    def art(self, request: str) -> Optional[Path]:
        """Delivered image of an ``art.json`` request for this model's asset.

        Returns ``assets/<asset>/art/<request>.png`` once ``forge art pull`` copied
        it, else ``None`` with a warning. The recipe decides how to print it
        (``project_decal``, ``project_triplanar``, ``project_planar``, ``blit``...).
        """
        from Tools._resolve import resolve_asset
        from Tools.art import delivered, load
        context = resolve_asset(self.bbmodel_path)
        if request not in load(context.project)["requests"]:
            raise KeyError(f"No art request {request!r} in art.json")
        return delivered(context, request)

    def compose_atlas(self, edge_dilation: int = 0, *, hide=(), texture: Union[int, str] = 0) -> Image.Image:
        """The atlas with every visible layer over it, in creation order. Each layer composites with its
        ``blend_mode`` (normal, multiply, screen, overlay, add) at its ``opacity``; ``hide`` leaves the named layers out
        (see the painting without its shading layer, for example). ``edge_dilation`` grows each chart's pixels."""
        if isinstance(edge_dilation, bool) or not isinstance(edge_dilation, int) or edge_dilation < 0:
            raise ValueError("edge_dilation must be a non-negative integer pixel count")
        if edge_dilation > self.parser.island_padding:
            raise ValueError(f"edge_dilation cannot exceed the UV island_padding: edge_dilation={edge_dilation} but the "
                             f"model was packed with island_padding={self.parser.island_padding}; run uv_packer with "
                             f"--island-padding {edge_dilation}, or lower edge_dilation")

        unknown = set(hide) - set(self._layers)
        if unknown:
            raise ValueError(f"compose_atlas: no layers {sorted(unknown)}; layers: {list(self._layers)}")
        slot = self._slot_index(texture)
        slot_info = self.parser.texture_slots[slot]
        slot_w, slot_h = slot_info["width"], slot_info["height"]
        result_atlas = self.atlases[slot].copy()
        for layer in self._layers.values():
            if not layer.visible or layer.name in hide:
                continue
            layer_img = layer.compose_atlas(edge_dilation=edge_dilation, slot=slot)
            if layer.blend_mode == "normal" and layer.opacity >= 1.0:
                result_atlas = Image.alpha_composite(result_atlas, layer_img)
                continue
            base = np.asarray(result_atlas, dtype=np.int64).reshape(-1, 4)
            over = np.asarray(layer_img, dtype=np.int64).reshape(-1, 4)
            mixed = blend_rows(base, over, mode=layer.blend_mode, opacity=layer.opacity)
            result_atlas = Image.fromarray(mixed.reshape(slot_h, slot_w, 4).astype(np.uint8), "RGBA")

        return result_atlas

    def save(self, output_png_path: str, overwrite: bool = True, backup: bool = True, *,
             register: bool | None = None, render_sides=None, edge_dilation: int = 0, hide=(),
             texture: Optional[Union[int, str]] = None) -> str:
        """Save an external PNG and optionally register it without changing face UVs; ``hide`` leaves layers out."""
        if register is None:
            register = os.environ.get("FORGE_REGISTER_TEXTURE", "1") == "1"
        valid_sides = ("auto", "front", "double")
        if render_sides is not None and (
            (isinstance(render_sides, dict) and any(v not in valid_sides for v in render_sides.values()))
            or (not isinstance(render_sides, dict) and render_sides not in valid_sides)
        ):
            raise ValueError("render_sides must be auto, front or double")
        if render_sides is not None and not register:
            raise ValueError("render_sides requires texture registration")
        if os.path.abspath(output_png_path) == self.bbmodel_path:
            raise ValueError("PNG and model must have different paths")
        TextureExporter.check_model(self.bbmodel_path, self.parser.data)
        if self.render.smooth:
            # A linearly filtered texture reads the padding around every island: fill all of it.
            edge_dilation = max(edge_dilation, self.parser.island_padding)
        slots = self.parser.texture_slots
        if len(slots) == 1 and slots[0]["name"] == "default" and texture is None:
            final_img = self.compose_atlas(edge_dilation=edge_dilation, hide=hide, texture=0)
            saved = TextureExporter.save_png(final_img, output_png_path, overwrite=overwrite, backup=backup)
            if register:
                TextureExporter.register_texture(saved, self.bbmodel_path, expected_data=self.parser.data,
                                                 backup=backup, render_sides=render_sides)
                self.parser = BlockbenchModelParser(self.bbmodel_path)
            return saved
        target_indices = [self._slot_index(texture)] if texture is not None else list(range(len(slots)))
        base_png = (TextureExporter.base_png_path(output_png_path, slots[target_indices[0]]["name"])
                    if texture is not None else Path(output_png_path))
        slot_pngs: Dict[int, str] = {}
        for idx in target_indices:
            slot_out = TextureExporter.slot_png_path(base_png, slots[idx]["name"])
            if os.path.abspath(slot_out) == self.bbmodel_path:
                raise ValueError("PNG and model must have different paths")
            final_img = self.compose_atlas(edge_dilation=edge_dilation, hide=hide, texture=idx)
            slot_pngs[idx] = TextureExporter.save_png(final_img, slot_out, overwrite=overwrite, backup=backup)
        if register:
            TextureExporter.register_textures(slot_pngs, self.bbmodel_path, base_png_path=base_png,
                                              expected_data=self.parser.data, backup=backup, render_sides=render_sides)
            self.parser = BlockbenchModelParser(self.bbmodel_path)
        return slot_pngs[target_indices[0]]

    def _save_legacy_unused(self, output_png_path, overwrite=True, backup=True, register=False,
                            render_sides=None, edge_dilation=0, hide=()):
        final_img = self.compose_atlas(edge_dilation=edge_dilation, hide=hide)
        saved = TextureExporter.save_png(final_img, output_png_path, overwrite=overwrite, backup=backup)
        if register:
            TextureExporter.register_texture(saved, self.bbmodel_path, expected_data=self.parser.data, backup=backup,
                                             render_sides=render_sides)
            self.parser = BlockbenchModelParser(self.bbmodel_path)
        return saved

    def save_temp(self, prefix: str = "tex_preview_") -> str:
        """Save a temporary copy and return the path to the PNG."""
        final_img = self.compose_atlas()
        return TextureExporter.save_temp(final_img, prefix=prefix)
