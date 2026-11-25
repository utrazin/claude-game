"""Lineart for 3D surface painting: one stroke model for pixel art and for smooth painting.

A stroke is a path plus a style (``stroke`` or a reusable ``style``); ``paint_strokes`` (a method of the
painter, elements and selections) paints a list of them in order.

Paths
  ``line``, ``curve``, ``bezier``, ``arc``: points in model units, (x, y) projected along the stroke's ``side``
  or (x, y, z) on the surface.
  ``vertices(element, names)``: through named mesh vertices. ``boundary(element, group, other)``: along the
  mesh edges between two face groups (for example a cloak's ``outer`` faces and its ``edge`` faces). These two
  come from the geometry itself, so they follow it exactly and need no coordinates.

Pixel art (``soft == 0``, the default)
  The stroke is rasterized on the texture's own texel grid, where a UV chart (``forge uv --layout charts``) is
  one continuous grid across many faces:
  1. the path is sampled every quarter texel; each sample lands on the texel under it (the front-most surface
     for projected paths, the nearest for surface paths);
  2. the texels form an ordered pixel chain per chart, gaps closed with Bresenham;
  3. L-shaped corner pixels are removed (pixel-perfect line);
  4. the chain is thickened to exactly ``width`` texels across the line whatever its slope;
  5. ``outline`` is a border of ``outline_width`` texels around the fill.
  Every write stays on texels of the same chart that the stroke's filters accept. Alpha is 0 or 1.
  A chart seam (where the grid is cut) can break a line; on one chart it is a clean pixel line.

Smooth (the asset's render mode is smooth, or ``soft > 0``)
  Every texel is split into a grid of subsamples (``samples`` x ``samples`` over a ``soft``-texel box; the
  smooth render mode's default box is 1 texel: exact area coverage, a one-texel edge, no blur). Each subsample
  is tested exactly as a pixel would be: inside the line (``align`` included), the outline or the fill, and on
  a face the stroke may paint (the face under the subsample, so group and element edges are anti-aliased too,
  plus facing, depth and front-most surface). A layer's alpha is the share of subsamples it shows on top, so
  shapes that meet inside a texel add up exactly. Colour functions (``fill=iris``) are averaged over the
  subsamples of texels where they change. Mirrored strokes are drawn once and copied, as in pixel art.

Feathered edges (``feather``, smooth only)
  ``feather=w`` eases the line's (and outline's) edge over ``w`` texels centred on it instead of cutting it at
  the width: a soft, smoky edge at any texture density. Pixel art ignores it (a texel is ink or not).

Chalk and stamped lines (``tip`` and ``brush``)
  With a grain ``tip`` (``Tools.TexturePainter.marks.Tip``) in smooth mode the line stays the exact, anti-aliased
  line above, shaped by the tokens the painting uses: its width follows the ``brush``'s profile along the whole
  path (``taper`` to points within ``taper_length`` of the ends, a smooth ``swell``, ``size``) and the tip's grain,
  box-projected on the surface like the texture's, breaks the outer ``falloff`` of the half width (``density``).
  Fill and outline work as usual. With an image motif (``Tip.image``), or in pixel art, the line is a stroke of
  stamps along the path laid by the stamp engine (``Tools.TexturePainter.stamps``); a fill and an outline are
  then drawn under it as plain strokes.

Units: ``width``, ``outline_width`` and ``feather`` are texels at the render mode's ``reference`` density (pixel
art: the asset's own texels; a smooth twin of a pixel asset: the pixel asset's texels, so a line keeps its size on
the model); ``soft`` is texels.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass, replace
from typing import Optional, Sequence

import numpy as np

from .core.color import parse_color
from .projection import (LAYER_DEPTH, PLANE_REACH, SAMPLE_STEP, SURFACE_REACH, FaceLookup as _Faces,
                         SurfaceView as _Surface, front_layer as _front, inside_polygon as _inside_polygon,
                         region_view, resample as _resample)

__all__ = ["Path", "Stroke", "Style", "InkReport", "line", "curve", "bezier", "arc", "vertices", "boundary",
           "stroke", "style", "paint_strokes"]

_BLENDS = ("normal", "replace", "multiply", "screen", "overlay", "add")
_MIRRORS = {None: None, "x": 0, "y": 1, "z": 2}
_ALIGNS = ("center", "inside")
MAX_JUMP = 3            # texels: a larger jump between consecutive samples starts a new run


def _line_brush():
    from .marks import Brush
    # stamps a quarter of the width apart, the grain following the line, no size or colour jitter
    return Brush(radius=(1.0, 1.0), length=(1, 1), spacing=0.25, turn=0.0, spread=0.0, align=1.0,
                 size_jitter=(1.0, 1.0), jitter=(0.0, 0.0, 0.0), name="line")


# ---------------------------------------------------------------- paths
def _points(points, name):
    array = np.asarray(points, dtype=float)
    if array.ndim != 2 or array.shape[1] not in (2, 3) or len(array) < 2:
        raise ValueError(f"{name}: expected at least 2 points of (x, y) or (x, y, z)")
    if not np.isfinite(array).all():
        raise ValueError(f"{name}: points must be finite numbers")
    return array


def _bezier_points(p0, p1, p2, p3, max_error):
    """Cubic Bezier flattened so the polyline stays within ``max_error`` of the curve."""
    second = max(np.linalg.norm(p0 - 2 * p1 + p2), np.linalg.norm(p1 - 2 * p2 + p3))
    count = max(1, int(math.ceil(math.sqrt(0.75 * second / max_error)))) if second > 0 else 1
    t = np.linspace(0.0, 1.0, count + 1)[:, None]
    return ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)


@dataclass(frozen=True)
class Path:
    """A curve definition, flattened when painted so its tolerance follows the texel size."""
    kind: str
    data: tuple
    closed: bool = False
    max_error: float = 0.1          # texels
    dim: int = 2

    @property
    def on_surface(self) -> bool:
        """True for paths taken from the mesh (``vertices``, ``boundary``)."""
        return self.kind in ("vertices", "boundary")

    def flatten(self, texel: float) -> np.ndarray:
        """Polyline (K, dim) within ``max_error`` texels of the curve; closed paths repeat the first point."""
        if self.on_surface:
            raise ValueError(f"a {self.kind} path is resolved against the model when painted")
        tol = max(self.max_error * texel, 1e-9)
        points = np.asarray(self.data[0], dtype=float)
        if self.kind == "line":
            out = points
        elif self.kind == "curve":
            tension = self.data[1]
            n = len(points)
            ext = (lambda i: points[i % n]) if self.closed else (lambda i: points[min(max(i, 0), n - 1)])
            pieces = []
            for i in range(n if self.closed else n - 1):
                p0, p1, p2, p3 = ext(i - 1), ext(i), ext(i + 1), ext(i + 2)
                m1 = (1 - tension) * (p2 - p0) / 2.0
                m2 = (1 - tension) * (p3 - p1) / 2.0
                pieces.append(_bezier_points(p1, p1 + m1 / 3.0, p2 - m2 / 3.0, p2, tol)[:-1])
            end = points[0] if self.closed else points[-1]
            out = np.vstack(pieces + [end[None, :]])
        elif self.kind == "bezier":
            if len(points) == 3:    # quadratic -> cubic
                points = np.array([points[0], points[0] + 2 / 3 * (points[1] - points[0]),
                                   points[2] + 2 / 3 * (points[1] - points[2]), points[2]])
            out = _bezier_points(*points, tol)
        else:                       # arc
            center, rx, ry, start, end = self.data
            sweep = math.radians(end - start)
            radius = max(rx, ry)
            step = 2 * math.acos(max(-1.0, min(1.0, 1 - tol / radius))) if radius > tol else math.pi
            count = max(2, int(math.ceil(abs(sweep) / max(step, 1e-3))))
            angle = math.radians(start) + np.linspace(0.0, sweep, count + 1)
            out = np.zeros((len(angle), self.dim))
            out[:, 0] = center[0] + rx * np.cos(angle)
            out[:, 1] = center[1] + ry * np.sin(angle)
            if self.dim == 3:
                out[:, 2] = center[2]
        if self.closed and not np.allclose(out[0], out[-1]):
            out = np.vstack([out, out[:1]])
        return out

    def mirrored(self, axes, axis: int) -> "Path":
        """Copy reflected across model axis ``axis`` (a plane axis for 2D paths)."""
        if self.on_surface:
            raise ValueError(f"mirror is not available for {self.kind} paths: name the mirrored element instead")
        column = axis if self.dim == 3 else (axes.index(axis) if axis in axes else None)
        if column is None:
            raise ValueError(f"mirror axis {'xyz'[axis]} is not on the plane of a 2D stroke (axes {axes})")
        if self.kind == "arc":
            center, rx, ry, start, end = self.data
            center = _flip(center, column)
            if column == 0:     # x reflected: angle a -> 180 - a
                start, end = 180 - start, 180 - end
            elif column == 1:   # y reflected: angle a -> -a
                start, end = -start, -end
            return Path("arc", (tuple(center), rx, ry, start, end), self.closed, self.max_error, self.dim)
        data = (tuple(map(tuple, _flip(np.asarray(self.data[0], dtype=float), column))),) + tuple(self.data[1:])
        return Path(self.kind, data, self.closed, self.max_error, self.dim)


def _flip(array, column):
    array = np.array(array, dtype=float)
    if array.ndim == 1:
        array[column] = -array[column]
    else:
        array[:, column] = -array[:, column]
    return array


def line(points: Sequence, closed: bool = False, max_error: float = 0.1) -> Path:
    """Straight segments through ``points`` (x, y) or (x, y, z) in model units."""
    p = _points(points, "line")
    return Path("line", (tuple(map(tuple, p)),), bool(closed), max_error, p.shape[1])


def curve(points: Sequence, tension: float = 0.0, closed: bool = False, max_error: float = 0.1) -> Path:
    """Smooth spline through ``points``. ``tension`` 0 = Catmull-Rom (smooth), 1 = straight segments."""
    p = _points(points, "curve")
    if not 0.0 <= tension <= 1.0:
        raise ValueError("curve: tension must be between 0 and 1")
    if len(p) < 3 and closed:
        raise ValueError("curve: a closed curve needs at least 3 points")
    return Path("curve", (tuple(map(tuple, p)), float(tension)), bool(closed), max_error, p.shape[1])


def bezier(*points: Sequence, max_error: float = 0.1) -> Path:
    """Cubic Bezier from 4 points (start, control, control, end), quadratic from 3."""
    if len(points) not in (3, 4):
        raise ValueError("bezier: give 3 (quadratic) or 4 (cubic) points")
    p = _points(points, "bezier")
    return Path("bezier", (tuple(map(tuple, p)),), False, max_error, p.shape[1])


def arc(center: Sequence, rx: float, ry: Optional[float] = None, start: float = 0.0, end: float = 360.0,
        max_error: float = 0.1) -> Path:
    """Elliptical arc in the x/y plane of the stroke, angles in degrees (0 = +x, 90 = +y)."""
    c = np.asarray(center, dtype=float)
    if c.shape not in ((2,), (3,)) or not np.isfinite(c).all():
        raise ValueError("arc: center must be (x, y) or (x, y, z)")
    ry = rx if ry is None else ry
    if rx <= 0 or ry <= 0:
        raise ValueError("arc: radii must be positive")
    if end == start:
        raise ValueError("arc: start and end angles must differ")
    full = abs(end - start) >= 360.0
    return Path("arc", (tuple(c), float(rx), float(ry), float(start), float(end)), full, max_error, len(c))


def vertices(element: str, names: Sequence[str], closed: bool = False) -> Path:
    """Path through mesh vertices of ``element`` by name, in order (exact positions, no coordinates)."""
    names = tuple(str(name) for name in names)
    if len(names) < 2:
        raise ValueError("vertices: give at least two vertex names")
    return Path("vertices", (str(element), names), bool(closed), 0.1, 3)


def boundary(element: str, group: str, other: Optional[str] = None) -> Path:
    """The mesh edges of ``element`` between faces of ``group`` and faces of ``other`` (any other group or an
    open edge when None), chained into polylines: a trim along an opening, an outline along a hem."""
    return Path("boundary", (str(element), str(group), None if other is None else str(other)), False, 0.1, 3)


# ---------------------------------------------------------------- strokes
@dataclass(frozen=True)
class Stroke:
    path: Path
    width: float = 1.0
    color: object = (0, 0, 0)
    outline: object = None
    outline_width: float = 1.0
    soft: Optional[float] = None
    side: str = "front"
    on: Optional[tuple] = None
    groups: Optional[tuple] = None
    depth: Optional[tuple] = None
    normal_min: float = 0.15
    align: str = "center"
    opacity: float = 1.0
    blend: str = "normal"
    mirror: Optional[str] = None
    name: str = ""
    fill: object = None
    wrap: bool = False
    seam: Optional[str] = None
    feather: float = 0.0
    tip: object = None
    brush: object = None
    seed: int = 0
    side_offset: float = 0.0


def _color(value):
    if value is None or callable(value):
        return value
    return tuple(parse_color(value))


def _names(value):
    return None if value is None else ((value,) if isinstance(value, str) else tuple(value))


def stroke(path: Path, *, width: float = 1.0, color=(0, 0, 0), outline=None, outline_width: float = 1.0,
           soft: Optional[float] = None, side: str = "front", on=None, groups=None, depth=None,
           normal_min: float = 0.15, align: str = "center", opacity: float = 1.0, blend: str = "normal",
           mirror: Optional[str] = None, name: str = "", fill=None, wrap: bool = False,
           seam: Optional[str] = None, feather: float = 0.0, tip=None, brush=None, seed: int = 0,
           side_offset: float = 0.0) -> Stroke:
    """Style a path. Widths and ``soft`` are texels; ``soft=None`` inherits ``paint_strokes(soft=...)``.

    ``feather`` (texels, smooth mode): the edge eases over that width instead of being cut at the line's width.
    ``tip`` (a ``Tip``) and ``brush`` (a ``Brush``, optional): a stamped line, the same marks as brush layers
    (see the module notes); ``seed`` varies its grain and jitter.

    ``side_offset`` (texels, like ``width``; scaled by a chalk line's brush size like its width): draws the line
    parallel to the path, that far to one side: toward the side ``on``/``groups`` allow when they allow only one
    side of the path (a line along a boundary, inside it), else to the path's left (mirrored copies to their
    right). Lines side by side along one path (a trim edged by two ink lines) are separate strokes with offsets.

    ``wrap=True`` (2D paths): instead of painting only the texels that face the projection, lift the path onto
    every surface layer under it (inside ``on``/``groups``/``depth``) and paint everything within the stroke's
    width of the lifted path, whatever way it faces: a line across a funnel-shaped collar also reaches the
    flared, grazing and underside faces that a projection cannot see. With ``fill`` the shape is the projected
    polygon: every texel under it, on every surface layer, is inside.

    ``seam`` (pixel art): each chart draws its own chain, so a thick line is cut at a chart edge and thins out there.
    ``"fill"`` adds the texels of the neighbouring chart that lie within the line (and outline) width of the path
    and touch a drawn texel across the seam; ``"none"`` leaves the chains as they are. Default: ``"fill"`` for surface
    paths (``wrap``, ``vertices``, ``boundary``, (x, y, z) points), ``"none"`` for projected 2D lines.

    ``color``/``outline``/``fill``: RGB(A), hex, or a function receiving the FaceSamples of the painted texels
    and returning a (K, 3) or (K, 4) array of 0-255 values. ``fill`` paints the inside of a closed path first
    (pixel art: the texels its line encloses on the grid, so a shape and its outline always match).
    Where it paints: ``on`` element name prefixes, ``groups`` face groups (``model_as_code_group``, such as a
    cloak's ``outer``); 2D paths are projected along ``side`` (front, back, east, west, top, bottom) onto
    texels facing it (``normal_min``) inside the optional ``depth=(lo, hi)`` window along that direction.
    ``align="inside"`` puts the whole width on the allowed side of a boundary (use it with ``groups``/``on``
    that keep one side). ``mirror="x"|"y"|"z"`` also draws the reflection across that model axis.
    """
    if not isinstance(path, Path):
        raise TypeError("stroke: path must come from line(), curve(), bezier(), arc(), vertices() or boundary()")
    if not (width > 0 and math.isfinite(width)):
        raise ValueError("stroke: width must be a positive number of texels")
    if outline is not None and not (outline_width > 0 and math.isfinite(outline_width)):
        raise ValueError("stroke: outline_width must be a positive number of texels")
    if soft is not None and not (soft >= 0 and math.isfinite(soft)):
        raise ValueError("stroke: soft must be 0 or a positive number of texels")
    if not 0.0 <= opacity <= 1.0:
        raise ValueError("stroke: opacity must be between 0 and 1")
    if str(blend).lower() not in _BLENDS:
        raise ValueError(f"stroke: blend must be one of {', '.join(_BLENDS)}")
    if mirror not in _MIRRORS:
        raise ValueError("stroke: mirror must be None, 'x', 'y' or 'z'")
    if mirror not in (None, "x") and path.on_surface:
        raise ValueError(f"stroke: {path.kind} paths mirror across x only (mirror=\"x\")")
    if align not in _ALIGNS:
        raise ValueError(f"stroke: align must be one of {', '.join(_ALIGNS)}")
    if depth is not None and (len(depth) != 2 or not depth[0] <= depth[1]):
        raise ValueError("stroke: depth must be (lo, hi) with lo <= hi")
    if fill is not None and not (path.closed or (path.kind == "vertices" and path.closed)):
        raise ValueError("stroke: fill needs a closed path (closed=True, or a full arc)")
    if seam not in (None, "fill", "none"):
        raise ValueError("stroke: seam must be None, 'fill' or 'none'")
    if wrap and (path.on_surface or path.dim != 2):
        raise ValueError("stroke: wrap lifts a 2D path (points (x, y)) onto the surface; vertices(), boundary() "
                         "and (x, y, z) paths are already on it")
    if not math.isfinite(side_offset):
        raise ValueError("stroke: side_offset must be a number of texels")
    if not (feather >= 0 and math.isfinite(feather)):
        raise ValueError("stroke: feather must be 0 or a positive number of texels")
    if tip is not None or brush is not None:
        from .marks import Brush, Tip
        if not isinstance(tip, Tip):
            raise TypeError("stroke: a stamped line needs tip=Tip (Tip.grain, Tip.solid or Tip.image)")
        if brush is not None and not isinstance(brush, Brush):
            raise TypeError("stroke: brush must be a Brush")
        if callable(color):
            raise ValueError("stroke: a stamped line (tip) takes one colour (fill and outline may be functions)")
    return Stroke(path, float(width), _color(color), _color(outline), float(outline_width),
                  None if soft is None else float(soft), str(side).lower(), _names(on), _names(groups),
                  None if depth is None else (float(depth[0]), float(depth[1])),
                  float(normal_min), align, float(opacity), str(blend).lower(), mirror, str(name), _color(fill),
                  bool(wrap), seam, float(feather), tip, brush, int(seed), float(side_offset))


class Style:
    """Stroke settings declared once and reused: ``thick = style(width=2, color=INK)`` then
    ``thick(curve(...), on="head")``. Extra keywords override; ``.but(...)`` derives a new style."""

    def __init__(self, **defaults):
        import inspect
        known = set(inspect.signature(stroke).parameters) - {"path"}
        unknown = sorted(set(defaults) - known)
        if unknown:
            raise TypeError(f"style: unknown stroke options {unknown}; valid: {sorted(known)}")
        stroke(line(((0, 0), (1, 1))), **{k: v for k, v in defaults.items() if k != "mirror"})   # validate now
        self.defaults = dict(defaults)

    def __call__(self, path: Path, **overrides) -> Stroke:
        return stroke(path, **{**self.defaults, **overrides})

    def but(self, **overrides) -> "Style":
        return Style(**{**self.defaults, **overrides})

    def __repr__(self):
        return f"Style({', '.join(f'{k}={v!r}' for k, v in self.defaults.items())})"


def style(**defaults) -> Style:
    """Declare a reusable stroke style (any ``stroke`` option except the path)."""
    return Style(**defaults)


# ---------------------------------------------------------------- report
class InkReport:
    """Texels written per stroke by one ``paint_strokes`` call."""

    def __init__(self):
        self.entries = []        # (name, texels)

    @property
    def total(self) -> int:
        return sum(count for _, count in self.entries)

    @property
    def empty(self) -> list:
        return [name for name, count in self.entries if count == 0]

    def warn_empty(self) -> "InkReport":
        for name in self.empty:
            warnings.warn(f"[ink] stroke {name!r} wrote no texels", stacklevel=3)
        return self

    def require_nonempty(self) -> "InkReport":
        if self.empty:
            raise ValueError(f"strokes wrote no texels: {self.empty}")
        return self

    def __str__(self):
        lines = [f"{name}: {count}" for name, count in self.entries]
        return f"[ink] {len(self.entries)} strokes, {self.total} texels\n" + "\n".join(lines)


def _hits(surface, candidates, samples, coords, plane, direction, texel):
    """(texel index, continuous x, continuous y) under each sample (index -1 when none): the front-most surface
    for projected samples, the nearest texel for surface samples, among ``candidates`` with ``coords``."""
    index_out = np.full(len(samples), -1)
    fx_out, fy_out = np.zeros(len(samples)), np.zeros(len(samples))
    if not len(candidates):
        return index_out, fx_out, fy_out
    reach = (PLANE_REACH if plane else SURFACE_REACH) * texel
    cell = reach
    keys = np.floor(coords / cell).astype(np.int64)
    buckets = {}
    for index, key in enumerate(map(tuple, keys)):
        buckets.setdefault(key, []).append(index)
    depth = surface.position[candidates] @ direction if plane else None
    span = range(-1, 2)
    for i, point in enumerate(samples):
        base = np.floor(point / cell).astype(np.int64)
        near = []
        if plane:
            for dx in span:
                for dy in span:
                    near.extend(buckets.get((base[0] + dx, base[1] + dy), ()))
        else:
            for dx in span:
                for dy in span:
                    for dz in span:
                        near.extend(buckets.get((base[0] + dx, base[1] + dy, base[2] + dz), ()))
        if not near:
            continue
        near = np.array(near)
        distance = np.linalg.norm(coords[near] - point, axis=1)
        close = distance <= reach
        if not close.any():
            continue
        near, distance = near[close], distance[close]
        if plane:
            front = depth[near].max()
            layer = depth[near] >= front - LAYER_DEPTH * texel
            near, distance = near[layer], distance[layer]
        index_out[i], fx_out[i], fy_out[i] = surface.refine(candidates[near[np.argmin(distance)]], point, plane)
    return index_out, fx_out, fy_out


def _bresenham(a, b):
    (x0, y0), (x1, y1) = a, b
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    out = []
    while True:
        out.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return out
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


class _Run:
    """An ordered pixel chain on one chart, with the continuous centre of each sampled pixel and the pixels that
    hold a sharp corner of the path."""
    __slots__ = ("chart", "chain", "centers", "corners")

    def __init__(self, chart):
        self.chart, self.chain, self.centers, self.corners = chart, [], {}, set()


def _runs(surface, hits, corners):
    """Ordered pixel chains (``_Run``) from the per-sample hits."""
    indices, fxs, fys = hits
    runs, run = [], None
    for index, fx, fy, corner in zip(indices, fxs, fys, corners):
        if index < 0:
            if run is not None:
                runs.append(run)
            run = None
            continue
        pixel = (int(surface.x[index]), int(surface.y[index]))
        this = int(surface.chart[index])
        if run is not None and (this != run.chart or max(abs(pixel[0] - run.chain[-1][0]),
                                                         abs(pixel[1] - run.chain[-1][1])) > MAX_JUMP):
            runs.append(run)
            run = None
        if run is None:
            run = _Run(this)
            run.chain.append(pixel)
        elif pixel != run.chain[-1]:
            if len(run.chain) >= 2 and pixel == run.chain[-2]:      # jitter back onto the previous texel
                run.chain.pop()
            else:
                run.chain.extend(_bresenham(run.chain[-1], pixel)[1:])
        sums = run.centers.setdefault(pixel, [0.0, 0.0, 0])
        sums[0] += fx
        sums[1] += fy
        sums[2] += 1
        if corner:
            run.corners.add(pixel)
    if run is not None:
        runs.append(run)
    for run in runs:
        run.centers = {p: (s[0] / s[2], s[1] / s[2]) for p, s in run.centers.items()}
    return runs


def pixel_perfect(chain, keep=()):
    """Drop the corner pixel of every L (a, b, c where a and c are diagonal neighbours), except pixels in
    ``keep`` (the sharp corners of the path itself, which a shape needs)."""
    if len(chain) < 3:
        return list(chain)
    out = [chain[0]]
    for i in range(1, len(chain) - 1):
        a, b, c = out[-1], chain[i], chain[i + 1]
        if (b not in keep and abs(a[0] - c[0]) == 1 and abs(a[1] - c[1]) == 1
                and (b == (a[0], c[1]) or b == (c[0], a[1]))):
            continue
        out.append(b)
    out.append(chain[-1])
    return out


def _across(dx, dy):
    """Axis (0 = x, 1 = y) a line travelling along (dx, dy) is thickened along: y for horizontal-ish lines,
    x for vertical-ish and diagonal ones, so every row or column gets the same count."""
    adx, ady = abs(dx), abs(dy)
    return 1 if adx >= ady and not (adx and ady / adx > 0.6) else 0


def _thicken(chain, width, centers):
    """A ``width`` x ``width`` square brush stamped on every pixel of the (already pixel-perfect) chain: the
    pixel-art way to draw a thick line, whose edges are regular staircases at any slope and along curves.
    Odd widths centre the brush on the chain pixel; even widths put the extra row/column on the side the line's
    continuous position leans to, once for the whole chain (so a line on a texel boundary straddles it)."""
    if width == 1:
        return set(chain)
    if width % 2:
        offsets = (-(width // 2), -(width // 2))
    else:
        lean = []
        for axis in (0, 1):
            fractions = [centers[p][axis] - p[axis] for p in chain if p in centers]
            mean = sum(fractions) / len(fractions) if fractions else 0.5
            lean.append(-(width // 2) + (1 if mean >= 0.5 else 0))
        offsets = tuple(lean)
    cells = set()
    for x, y in chain:
        for i in range(width):
            for j in range(width):
                cells.add((x + offsets[0] + i, y + offsets[1] + j))
    return cells


# Outlines grow across edges only (4-neighbourhood): around a staircase this gives the clean pixel-art
# border; diagonal growth would fatten every step corner.
_NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _keep(surface, cells, chart, allowed):
    """Texel indices of ``cells`` that are on ``chart`` and allowed."""
    out = []
    for x, y in cells:
        index = surface.at(x, y)
        if index >= 0 and surface.chart[index] == chart and allowed[index]:
            out.append(index)
    return out


def _enclosed(chain):
    """Pixels a closed pixel chain encloses (not on the chain): flood the outside from the bounding box border."""
    cells = set(chain)
    xs, ys = [x for x, _ in cells], [y for _, y in cells]
    x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
    outside, todo = set(), [(x0, y0)]
    while todo:
        x, y = todo.pop()
        if (x, y) in outside or (x, y) in cells or not (x0 <= x <= x1 and y0 <= y <= y1):
            continue
        outside.add((x, y))
        todo.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)} - outside - cells


def _sealed_fill(surface, inside, drawn, allowed):
    """Fill texels: those inside the shape, minus the line, minus anything that touches the outside of the line
    on the same chart (repeated until stable), so the fill never peeks out of a cleaned pixel corner."""
    inside = set(int(i) for i in inside)
    fill = inside - drawn
    peeking = set()
    for index in fill:            # one pass: a fill texel touching the outside of the shape past the line
        x, y, chart = int(surface.x[index]), int(surface.y[index]), surface.chart[index]
        for dx, dy in _NEIGHBOURS:
            other = surface.at(x + dx, y + dy)
            if (other >= 0 and surface.chart[other] == chart and allowed[other]
                    and other not in inside and other not in drawn):
                peeking.add(index)
                break
    return fill - peeking


def _pixel_layers(surface, item, runs, allowed, inside=None):
    """(color, texel indices, counts) for the fill, the outline and the line of one path, in drawing order.
    ``inside``: texels whose centre is inside the closed shape (projected paths), for ``fill``."""
    width = max(1, int(round(item.width)))
    brush = 2 * width - 1 if item.align == "inside" else width
    ow = int(round(item.outline_width)) if item.outline is not None else 0
    line_cells, edge, enclosed = [], [], []
    for run in runs:
        clean = pixel_perfect(run.chain, run.corners)
        if item.fill is not None and inside is None and len(clean) >= 3:
            enclosed.extend(_keep(surface, _enclosed(clean), run.chart, allowed))
        kept = _keep(surface, _thicken(clean, brush, run.centers), run.chart, allowed)
        line_cells.extend(kept)
        if ow:
            on = {(int(surface.x[i]), int(surface.y[i])) for i in kept}
            grown = set(on)
            for _ in range(ow):
                grown |= {(a + dx, b + dy) for a, b in grown for dx, dy in _NEIGHBOURS}
            edge.extend(_keep(surface, grown - on, run.chart, allowed))
    layers = []
    if item.fill is not None:
        if inside is not None:
            enclosed = sorted(_sealed_fill(surface, inside, set(line_cells) | set(edge), allowed))
        layers.append((item.fill, np.unique(np.asarray(enclosed, dtype=np.int64)), False))
    if ow:
        layers.append((item.outline, np.unique(np.asarray(edge, dtype=np.int64)), False))
    layers.append((item.color, np.unique(np.asarray(line_cells, dtype=np.int64)), True))
    return layers


def _seam_extend(surface, item, layers, polylines, coords, candidates, texel):
    """Complete a pixel line across chart seams. Each chart's chain is thickened on its own grid, so the brush is cut
    at the chart edge and the line thins out at a seam. Texels of another chart that lie within the line's half
    width (and the outline's) of the path and touch a drawn texel across the seam are added to that layer. The pixel
    chains inside each chart are not changed."""
    layers = list(layers)
    if not polylines or not len(candidates):
        return layers
    a = np.concatenate([p[:-1] for p in polylines])
    b = np.concatenate([p[1:] for p in polylines])
    distance = _distance_to_segments(coords[candidates], a, b)
    taken = set()
    for _color, indices, _main in layers:
        taken.update(int(i) for i in indices)
    reach_across = 1.5 * texel

    def extend(base, radius):
        base = np.asarray(base, dtype=np.int64)
        if not len(base):
            return base
        pool = candidates[distance <= radius]
        pool = np.array([i for i in pool.tolist() if i not in taken], dtype=np.int64)
        if not len(pool):
            return base
        added = []
        for start in range(0, len(pool), 256):
            chunk = pool[start:start + 256]
            apart = np.linalg.norm(coords[chunk][:, None, :] - coords[base][None, :, :], axis=2)
            across = (apart <= reach_across) & (surface.chart[chunk][:, None] != surface.chart[base][None, :])
            added.extend(chunk[across.any(axis=1)].tolist())
        taken.update(added)
        return np.union1d(base, np.array(added, dtype=np.int64)) if added else base

    half = item.width / 2.0 * texel
    layers[-1] = (layers[-1][0], extend(layers[-1][1], half), True)
    if item.outline is not None:
        outline = [k for k, layer in enumerate(layers[:-1]) if layer[0] is item.outline][-1]
        layers[outline] = (layers[outline][0],
                           extend(layers[outline][1], half + item.outline_width * texel), False)
    return layers


# ---------------------------------------------------------------- surface paths
def _surface_polylines(path, texture_painter, shift):
    """Stroke-space 3D polylines of a vertices/boundary path."""
    from .core.surface_sampling import _world_rows
    sampler = texture_painter.surface_sampler
    name = path.data[0]
    if name not in sampler.elements:
        raise KeyError(f"{path.kind}: no element {name!r}")
    element = sampler.elements[name]
    raw = next(e for e in texture_painter.parser.data["elements"] if e.get("name") == name)
    local = {key: np.add(element.origin, value) for key, value in element.vertices.items()}

    def world(keys):
        missing = [k for k in keys if k not in local]
        if missing:
            raise KeyError(f"{path.kind}: element {name!r} has no vertices {missing[:5]}")
        return _world_rows(sampler.builder, element, np.array([local[k] for k in keys], dtype=float)) \
            + np.asarray(shift(name), dtype=float)

    if path.kind == "vertices":
        keys = list(path.data[1]) + ([path.data[1][0]] if path.closed else [])
        return [world(keys)]
    _, group, other = path.data
    edges = {}
    for face in raw.get("faces", {}).values():
        order = face.get("vertices", [])
        for a, b in zip(order, order[1:] + order[:1]):
            edges.setdefault(frozenset((a, b)), []).append(face.get("model_as_code_group"))
    chosen = []
    for edge, groups in edges.items():
        if group not in groups:
            continue
        rest = [g for g in groups if g != group] if groups.count(group) == 1 else []
        if other is None:
            if len(groups) == 1 or any(g != group for g in groups):
                chosen.append(tuple(edge))
        elif other in rest:
            chosen.append(tuple(edge))
    if not chosen:
        raise ValueError(f"boundary: element {name!r} has no edge between groups {group!r} and {other!r}")
    neighbours = {}
    for a, b in chosen:
        neighbours.setdefault(a, []).append(b)
        neighbours.setdefault(b, []).append(a)
    unused = set(map(frozenset, chosen))
    polylines = []
    while unused:
        ends = [v for v, n in neighbours.items() if sum(frozenset((v, w)) in unused for w in n) == 1]
        start = min(ends) if ends else min(next(iter(unused)))
        chain = [start]
        while True:
            step = next((w for w in sorted(neighbours[chain[-1]]) if frozenset((chain[-1], w)) in unused), None)
            if step is None:
                break
            unused.discard(frozenset((chain[-1], step)))
            chain.append(step)
        polylines.append(world(chain))
    return polylines


# ---------------------------------------------------------------- smooth / hard (distance based)
def _distance_to_segments(points, a, b):
    """Distance from every row of ``points`` (N, k) to the nearest of the segments a[i]-b[i]."""
    ab = b - a
    length2 = np.maximum((ab * ab).sum(axis=1), 1e-18)
    best = np.full(len(points), np.inf)
    chunk = max(1, 200000 // max(1, len(a)))
    for start in range(0, len(points), chunk):
        p = points[start:start + chunk, None, :]
        t = np.clip(((p - a) * ab).sum(axis=2) / length2, 0.0, 1.0)
        nearest = a + ab * t[..., None]
        best[start:start + chunk] = np.sqrt(((p - nearest) ** 2).sum(axis=2)).min(axis=1)
    return best


# ---------------------------------------------------------------- smooth: area coverage on subsamples
def _grid(n, box):
    """``n`` x ``n`` subsample offsets (texels from the texel centre) over a ``box``-wide square."""
    if n <= 1 or box <= 0:
        return ((0.0, 0.0),)
    steps = [((i + 0.5) / n - 0.5) * box for i in range(n)]
    return tuple((dx, dy) for dy in steps for dx in steps)



def _coverage_layers(surface, faces, item, polylines, plane, axes, direction, texel, candidates, grid, face_ok,
                     eligible, polylines2d=None, profiles=None):
    """(color, texel indices, coverage, is the line) of the fill, outline and line of one stroke, from the
    fraction of each texel's subsamples inside each shape and on a face the stroke may paint. ``polylines2d``: for a
    wrapped fill, the projected polygons that decide what is inside (``polylines`` are then the lifted 3D lines).
    ``profiles`` (a chalk line, ``stroke(tip=...)``): per polyline (arc of each vertex along its whole line, the
    line's length, closed, line number); the width follows the brush's profile and the tip's grain breaks the
    edge of the line."""
    width = item.width * (2 if item.align == "inside" else 1)
    ow = item.outline_width if item.outline is not None else 0.0
    half = width / 2.0
    feather = getattr(item, "feather", 0.0)
    widest = half if profiles is None or item.brush is None else half * item.brush.size * (1 + item.brush.swell)
    reach = widest + ow + feather / 2.0 + max(abs(np.asarray(grid)).max(), 0.0) * math.sqrt(2) + 0.75
    wrap_fill = polylines2d is not None
    if polylines:
        a = np.concatenate([p[:-1] for p in polylines])
        b = np.concatenate([p[1:] for p in polylines])
    columns = list(axes) if plane else [0, 1, 2]
    centre = surface.centre[candidates][:, columns]
    near = (_distance_to_segments(centre, a, b) / texel <= reach) if polylines else np.zeros(len(candidates), bool)
    if item.fill is not None:
        centre2 = surface.centre[candidates][:, list(axes)] if wrap_fill else centre
        for polyline in (polylines2d if wrap_fill else polylines):
            near |= _inside_polygon(centre2, polyline)
    cand = candidates[near]
    if not len(cand):
        return []
    offsets = np.asarray(grid, dtype=float)
    s = len(offsets)
    sub = (surface.centre[cand][:, None, :] + surface.step_x[cand][:, None, :] * offsets[None, :, 0, None]
           + surface.step_y[cand][:, None, :] * offsets[None, :, 1, None])               # (N, S, 3)
    uv = (surface.uv0[cand][:, None, :] + surface.uvx[cand][:, None, :] * offsets[None, :, 0, None]
          + surface.uvy[cand][:, None, :] * offsets[None, :, 1, None])                  # (N, S, 2)
    on = faces.resolve(surface.face[cand], uv)
    known = on >= 0
    ok = np.zeros(on.shape, dtype=bool)
    ok[known] = face_ok[on[known]]
    if plane or item.wrap:
        if plane:
            normal = np.where((on == surface.face[cand][:, None])[..., None], surface.normal[cand][:, None, :],
                              faces.normal[np.maximum(on, 0)])
            ok &= (normal @ direction) >= item.normal_min
        if item.depth is not None:
            along = sub @ direction
            ok &= (along >= item.depth[0]) & (along <= item.depth[1])
    if plane:
        ok &= _front(surface, cand, surface.position[cand][:, list(axes)], direction, texel,
                     eligible[cand], slope=True)[:, None]
    points = sub[..., columns].reshape(-1, len(columns))
    d = ((_distance_to_segments(points, a, b) / texel).reshape(len(cand), s) if polylines
         else np.full((len(cand), s), np.inf))
    line_half, ink, outline_ink = half, True, True
    if profiles is not None and polylines:
        line_half, ink, rank, zone = _chalk(item, polylines, profiles, points, sub, surface.normal[cand], texel,
                                            half, (len(cand), s))
        if ow:              # the outline is a line too: as wide as the brush makes lines, its outer edge chalk
            brush = item.brush
            ow = ow * (brush.size if brush is not None else 1.0)
            density = brush.density if brush is not None else 0.8
            outer = np.clip((line_half + ow - d) / np.maximum(zone, 1e-9), 0.0, 1.0)
            outline_ink = (outer >= 1.0) | (rank > 1.0 - density * outer)    # solid inside, chalk at its edge
        d = np.where(np.isfinite(d), d, np.inf)
    masks = []                                   # (colour, subsample mask, is the line), bottom to top
    if item.fill is not None:
        if not (plane or wrap_fill):
            raise ValueError("stroke: a smooth fill needs a 2D (projected) path")
        fill_points = sub[..., list(axes)].reshape(-1, 2) if wrap_fill else points
        inside = np.zeros(len(points), dtype=bool)
        for polyline in (polylines2d if wrap_fill else polylines):
            inside |= _inside_polygon(fill_points, polyline)
        masks.append((item.fill, inside.reshape(len(cand), s) & ok, False))
    def edge(limit):               # inside ``limit`` texels of the path; ``feather`` eases the edge over that width
        if feather <= 0:
            return (d <= limit) & ok
        return np.clip((limit + feather / 2.0 - d) / feather, 0.0, 1.0) * ok

    if ow:
        outline = edge(line_half + ow)
        masks.append((item.outline, outline * outline_ink if feather > 0 else outline & outline_ink, False))
    masks.append((item.color, edge(line_half) * ink if feather > 0 else edge(line_half) & ink, True))
    # Each subsample shows the top-most layer covering it. Painting the layers in order with alpha
    # e_k / (1 - sum of the exclusive coverages above) reproduces exactly that mix (no colour bleeds under an
    # edge, and two half-covering layers that together cover a texel cover all of it).
    above = np.zeros((len(cand), s))
    exclusive = []
    for color, mask, main in reversed(masks):
        mask = mask.astype(float)       # a share of each subsample (0 or 1 unless feathered)
        share = mask * (1.0 - above)
        exclusive.append((color, share.mean(axis=1), mask.mean(axis=1), main))
        above += share
    layers, covered_above = [], np.zeros(len(cand))
    for color, share, own, main in exclusive:        # top to bottom
        rest = 1.0 - covered_above
        alpha = np.divide(share, rest, out=np.zeros_like(share), where=rest > 1e-12)
        keep = (alpha > 0) | (main & (own > 0))
        layers.append((color, cand[keep], np.clip(alpha[keep], 0.0, 1.0), main))
        covered_above = covered_above + share
    return layers[::-1]


def _chalk(item, polylines, profiles, points, sub, normals, texel, half, shape):
    """(half width per subsample in texels, ink per subsample, the grain's rank, the width of the chalky edge band)
    of a chalk line: the width follows the brush's
    profile along the whole line (pointed ends, a smooth swell) at the nearest point of the path, and the tip's
    grain (box-projected on the surface, as overlays are) breaks the outer ``falloff`` of the half width."""
    from .marks import Brush
    from .stamps import width_profile
    brush = item.brush or Brush(radius=(1.0, 1.0))
    a = np.concatenate([p[:-1] for p in polylines])
    b = np.concatenate([p[1:] for p in polylines])
    arc0 = np.concatenate([np.asarray(arc, float)[:-1] for arc, _t, _c, _n in profiles])
    arc1 = np.concatenate([np.asarray(arc, float)[1:] for arc, _t, _c, _n in profiles])
    owner = np.concatenate([np.full(len(p) - 1, k) for k, p in enumerate(polylines)])
    _dist, segment, t = _nearest_segments(points, a, b)
    arc = arc0[segment] + (arc1[segment] - arc0[segment]) * t
    factor = np.ones(len(points))
    for k, (_arc, total, closed, number) in enumerate(profiles):
        mine = owner[segment] == k
        if mine.any():
            phase = np.random.default_rng(item.seed * 7919 + number).uniform(0, 2 * math.pi, 2)
            factor[mine] = width_profile(brush, arc[mine], total, closed, phase)
    line_half = (half * brush.size * factor).reshape(shape)
    rank = item.tip.on_surface(sub.reshape(-1, 3), np.repeat(normals, shape[1], axis=0), item.seed,
                               scale=item.tip.scale * brush.grain).reshape(shape) + 0.5
    d = (_dist / texel).reshape(shape)
    pressure = np.clip((1.0 - d / np.maximum(line_half, 1e-9)) / brush.falloff, 0.0, 1.0)
    zone = brush.falloff * line_half                 # the chalky band at the edge, in texels
    return line_half, rank > 1.0 - brush.density * pressure, rank, zone


def _side_offset(surface, item, polylines, flipped, plane, axes, eligible, texel):
    """``polylines`` moved sideways by the stroke's ``side_offset``: on the surface (3D paths: sideways is across
    the path on the surface, from each point's normal) or in the projection plane (2D paths), with mitred corners.
    The side: the one where the stroke may paint, when only one side has eligible texels; else the left (the
    right for mirrored copies, so a mirrored pair stays symmetric)."""
    from .stamps import nearest_normals
    size = item.brush.size if (item.tip is not None and item.brush is not None) else 1.0
    distance = item.side_offset * texel * size
    columns = list(axes)
    places = (surface.position[:, columns] if plane else surface.position)[np.flatnonzero(eligible)]
    out = []
    for polyline, mirror in zip(polylines, flipped):
        p = np.asarray(polyline, dtype=float)
        if len(p) < 2:
            out.append(p)
            continue
        seg = np.diff(p, axis=0)
        seg /= np.maximum(np.linalg.norm(seg, axis=1, keepdims=True), 1e-12)
        if plane:
            seg_left = np.stack([-seg[:, 1], seg[:, 0]], axis=1)
        else:
            mids = 0.5 * (p[1:] + p[:-1])
            seg_left = np.cross(nearest_normals(surface, mids, where=eligible), seg)   # the painted surface's
            seg_left /= np.maximum(np.linalg.norm(seg_left, axis=1, keepdims=True), 1e-12)
        before = np.vstack([seg_left[:1], seg_left])          # each vertex between its two segments
        after = np.vstack([seg_left, seg_left[-1:]])
        left = before + after
        left /= np.maximum(np.linalg.norm(left, axis=1, keepdims=True), 1e-12)
        left /= np.clip((left * after).sum(axis=1, keepdims=True), 0.5, 1.0)   # mitre, at most twice as far
        sign = -1.0 if mirror else 1.0
        if len(places):
            k = len(p) // 2
            probe = [p[k] + s * left[k] * max(abs(distance), 2 * texel) for s in (1.0, -1.0)]
            near = [np.linalg.norm(places - q, axis=1).min() <= 0.75 * texel for q in probe]
            if near[0] != near[1]:
                sign = 1.0 if near[0] else -1.0
        out.append(p + sign * distance * left)
    return out


def _nearest_segments(points, a, b):
    """(distance, segment index, position 0..1 on it) of the nearest of the segments a[i]-b[i] to each point."""
    ab = b - a
    length2 = np.maximum((ab * ab).sum(axis=1), 1e-18)
    best = np.full(len(points), np.inf)
    index = np.zeros(len(points), dtype=np.int64)
    where = np.zeros(len(points))
    chunk = max(1, 200000 // max(1, len(a)))
    for start in range(0, len(points), chunk):
        p = points[start:start + chunk, None, :]
        t = np.clip(((p - a) * ab).sum(axis=2) / length2, 0.0, 1.0)
        distance = np.sqrt(((p - (a + ab * t[..., None])) ** 2).sum(axis=2))
        k = distance.argmin(axis=1)
        rows = np.arange(len(k))
        best[start:start + chunk], index[start:start + chunk] = distance[rows, k], k
        where[start:start + chunk] = t[rows, k]
    return best, index, where


# ---------------------------------------------------------------- painting
def _colors(color, painted, count):
    if callable(color):
        values = np.asarray(color(painted), dtype=float)
        if values.ndim != 2 or len(values) != count or values.shape[1] not in (3, 4):
            raise ValueError(f"stroke color function must return ({count}, 3 or 4) values, got {values.shape}")
        if values.shape[1] == 3:
            values = np.concatenate([values, np.full((count, 1), 255.0)], axis=1)
        if values.min() < 0 or values.max() > 255 or not np.isfinite(values).all():
            raise ValueError("stroke color function must return finite 0-255 values")
        return values
    return np.tile(np.asarray(color, dtype=float), (count, 1))


def _write(region, surface, indices, color, coverage, item, mirror_of=None, grid=None, painter=None):
    """Blend ``color`` on the texels ``indices`` (with optional per-texel coverage). With ``mirror_of``, each
    texel's mirror image gets the very same RGBA (copied, not re-evaluated), so both sides are identical.
    ``grid``: subsample offsets a colour function is averaged over (smooth strokes)."""
    indices = np.asarray(indices, dtype=np.int64)
    if not len(indices):
        return 0
    order = np.argsort(indices, kind="stable")
    indices = indices[order]
    coverage = None if coverage is None else np.asarray(coverage, dtype=float)[order]
    rgba = np.zeros((len(indices), 4))
    faces = surface.face[indices]
    for k in np.unique(faces):                      # evaluate colours per face, in each face's row order
        pick = np.flatnonzero(faces == k)
        _face, rows = surface.entries[int(k)]
        keep = np.zeros(len(rows), dtype=bool)
        keep[surface.row[indices[pick]]] = True
        count = int(keep.sum())
        if callable(color) and grid is not None and len(grid) > 1 and painter is not None:
            from .painter import supersample
            values, _ = supersample(painter, [rows.subset(keep)], lambda part: (
                _colors(color, part[0], len(part[0])), np.ones(len(part[0]), dtype=bool)), offsets=grid)
        else:
            values = _colors(color, rows.subset(keep) if callable(color) else None, count)
        position = {r: i for i, r in enumerate(np.flatnonzero(keep).tolist())}
        rgba[pick] = values[[position[r] for r in surface.row[indices[pick]].tolist()]]
    if coverage is not None:
        rgba[:, 3] = np.rint(rgba[:, 3] * coverage)
    count = len(indices)
    if mirror_of is not None:
        images = mirror_of[indices]
        ok = images >= 0
        indices, rgba = np.concatenate([indices, images[ok]]), np.concatenate([rgba, rgba[ok]])
    faces = surface.face[indices]
    for k in np.unique(faces):
        pick = np.flatnonzero(faces == k)
        face, rows = surface.entries[int(k)]
        rows_of = surface.row[indices[pick]]
        keep = np.zeros(len(rows), dtype=bool)
        keep[rows_of] = True
        by_row = np.zeros((len(rows), 4))
        by_row[rows_of] = rgba[pick]
        region._blend_into(face, rows, keep, np.rint(by_row[keep]).astype(np.int64), item.blend, item.opacity)
    return count


def _stamped(surface, item, polylines, plane, axes, direction, eligible, texel, smooth):
    """Paint a stamped line (``stroke(tip=...)``) and return the texels it wrote. A 2D path is lifted onto the
    surface under it first; the stamps are laid on a transparent layer (mirrored when the stroke is) and
    composited with the stroke's blend and opacity."""
    from .stamps import PathPiece, TexelLayer, path_strokes, stamp_hits
    closed = bool(item.path.closed)
    if plane:          # the lifted pieces keep their place along the 2D line, so the taper and swell follow it
        totals = [float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum()) for p in polylines]
        pieces = [PathPiece(points, arc, totals[number], closed, number)
                  for points, arc, number in surface.lift(polylines, axes, eligible, texel, with_arc=True)]
    else:
        pieces = [PathPiece.of(p, number) for number, p in enumerate(polylines)]
    if not pieces:
        return 0
    brush = item.brush or _line_brush()
    rng = np.random.default_rng(item.seed)
    grain = item.tip.field(item.seed)
    size = grain.shape[0] if grain is not None else 1
    color = np.asarray(item.color[:3], dtype=float)
    stamps, rgb = path_strokes(surface, pieces, brush, [color], rng, size, item.width * texel / 2.0)
    where = surface.eligible(item, direction, False)
    hits = stamp_hits(surface, stamps, rgb, item.tip, brush, item.seed, where=where,
                      edge="soft" if smooth else "hard")
    layer = TexelLayer(surface.count)
    alpha = (item.color[3] / 255.0 if len(item.color) > 3 else 1.0) * item.opacity
    layer.lay(hits.texel, hits.colors, hits.alpha * alpha)
    if item.mirror == "x":
        layer.mirror(*surface.mirror_of())
    indices, rgba = layer.rgba()
    if len(indices):
        surface.write(rgba, indices, blend=item.blend)
    return int(len(indices))


def _stroke_plan(item, call_soft, call_clean, vectors, warn):
    from .painter import decal_frame
    soft = call_soft if item.soft is None else item.soft
    clean = (soft == 0) if call_clean is None else bool(call_clean)
    if clean and soft > 0:
        warn("clean is ignored when soft > 0 (anti-aliased strokes are not cleaned)")
        clean = False
    _, direction, axes, _ = decal_frame(vectors, item.side)
    return soft, clean, np.asarray(direction, dtype=float), tuple(axes)


def paint_strokes(region, strokes: Sequence[Stroke], *, soft: Optional[float] = None, offset=(0.0, 0.0, 0.0),
                  clean: Optional[bool] = None) -> InkReport:
    """Paint ``strokes`` in list order on the texels of ``region`` (a SurfaceRegion).

    ``soft``: anti-aliasing box in texels for strokes that set none (default: the render mode's ``aa``, 0 in
    pixel art). ``offset``: added to every texel's model position (and to surface paths) before measuring: a
    tuple, or a function ``element_name -> tuple``, to paint in a shifted frame. ``clean``: pixel-art
    rasterization (default: on when soft is 0); off, a hard ``distance <= width / 2`` mask. Widths are scaled by
    the render mode's ``reference`` density. Returns an ``InkReport``; strokes that wrote nothing also warn.
    """
    if soft is not None and not (soft >= 0 and math.isfinite(soft)):
        raise ValueError("paint_strokes: soft must be 0 or a positive number of texels")
    strokes = list(strokes)
    for item in strokes:
        if not isinstance(item, Stroke):
            raise TypeError("paint_strokes: expected Stroke objects from stroke()")
    report = InkReport()
    entries = [(face, rows) for face, rows in region._entries if len(rows)]
    if not entries:
        for item in strokes:
            report.entries.append((item.name or item.path.kind, 0))
        return report.warn_empty()
    texture_painter = next((face.element_painter.texture_painter for face, _ in entries
                            if hasattr(getattr(face, "element_painter", None), "texture_painter")), None)
    vectors = region._direction_vectors()
    # The density of the faces this region paints (most of its texels when UV rules mix densities).
    uv_scale = (texture_painter.texel_density([(rows.element_name, rows.face_name, len(rows)) for _, rows in entries])
                if texture_painter is not None else 1.0)
    texel = 1.0 / uv_scale
    render = texture_painter.render
    if soft is None:
        soft = render.aa if render.smooth else 0.0
    scale = render.width_scale(uv_scale)
    samples = render.samples if render.smooth else 4
    shift = offset if callable(offset) else (lambda _name, value=tuple(offset): value)
    surface = region_view(texture_painter, entries, offset)
    surface.texel = texel
    faces = None
    notes = set()

    def warn(message):
        if message not in notes:
            notes.add(message)
            warnings.warn(f"[ink] {message}", stacklevel=4)

    for index, item in enumerate(strokes):
        name = item.name or f"{item.path.kind} #{index}"
        if scale != 1.0:          # widths are reference texels: the same size on the model at any density
            item = replace(item, width=item.width * scale, outline_width=item.outline_width * scale,
                           feather=item.feather * scale, side_offset=item.side_offset * scale)
        soft_value, clean_value, direction, axes = _stroke_plan(item, soft, clean, vectors, warn)
        if item.path.on_surface:
            polylines = _surface_polylines(item.path, texture_painter, shift)
            flipped = [False] * len(polylines)
            if item.mirror is not None:       # whichever side the path is on, it reaches the drawn side
                polylines += [polyline * np.array((-1.0, 1.0, 1.0)) for polyline in polylines]
                flipped += [True] * len(flipped)
        else:
            polylines = [item.path.flatten(texel)]
            flipped = [False]
            if item.mirror is not None:
                polylines.append(item.path.mirrored(axes, _MIRRORS[item.mirror]).flatten(texel))
                flipped.append(True)
        plane = polylines[0].shape[1] == 2
        eligible = allowed = surface.eligible(item, direction, plane)
        if item.side_offset:
            polylines = _side_offset(surface, item, polylines, flipped, plane, axes, eligible, texel)
        polylines2d = None
        # a chalk line in a smooth asset: the distance-based line even at soft=0 (then hard texels: one sample
        # per texel, as crisp as the painting's strokes), never a pixel-art chain
        chalk = item.tip is not None and item.tip.motif is None and (render.smooth or not clean_value)
        if chalk:
            clean_value = False
        profiles = None
        if chalk:                     # a chalk line: the plain line, its width and edge shaped by brush and tip
            closed = bool(item.path.closed) if not item.path.on_surface else None
            profiles = []
            for number, p in enumerate(polylines):
                arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
                ends_meet = len(p) > 2 and bool(np.allclose(p[0], p[-1]))
                profiles.append((arc, float(arc[-1]), ends_meet if closed is None else closed, number))
        if item.tip is not None and not chalk:   # a stamped line: stamps along the path (the stamp engine)
            if item.fill is not None or item.outline is not None:
                # under it, the plain stroke: its fill and its outline band (or the fill colour under the line)
                source = strokes[index]
                under = replace(source, tip=None, brush=None, outline=None,
                                color=source.outline if source.outline is not None else source.fill,
                                width=source.width + (2 * source.outline_width if source.outline is not None else 0))
                paint_strokes(region, [under], soft=soft, offset=offset, clean=clean)
            report.entries.append((name, _stamped(surface, item, polylines, plane, axes, direction, eligible,
                                                  texel, render.smooth)))
            continue
        if item.feather and clean_value:
            warn("feather is ignored in pixel art (a texel is ink or not)")
        if item.wrap:         # lift the 2D path onto every surface under it; from here on it is a 3D surface path
            lifted = surface.lift(polylines, axes, eligible, texel, with_arc=chalk)
            if chalk:          # the lifted pieces keep their place along the 2D line
                profiles = [(arc, profiles[number][1], profiles[number][2], number) for _p, arc, number in lifted]
                lifted = [points for points, _arc, _number in lifted]
            if item.fill is not None:
                polylines2d = polylines       # a wrapped shape is the projected polygon, on every layer
            elif not lifted:
                report.entries.append((name, 0))
                continue
            polylines, plane = lifted, False
        coords_all = surface.position[:, list(axes)] if plane else surface.position
        # Pixel lines on surface paths (wrap, vertices, boundary, 3D points) are completed across chart seams; 2D
        # projected lines only when asked (seam="fill"), so existing pixel art is not touched.
        seam_on = item.seam == "fill" or (item.seam is None and not plane)
        # Strokes mirrored across x = 0 are drawn on the +x half only and copied texel by texel onto their mirror
        # images, so both halves are identical by construction (texels without a mirror image, on an asymmetric
        # surface, are drawn directly).
        mirror = surface.mirror_of() if item.mirror == "x" else None
        mirror_of = None if mirror is None else mirror[0]
        source = np.ones(len(allowed), dtype=bool) if mirror is None else ~mirror[1]
        allowed = allowed & source
        surface.use(coords_all, allowed)
        written = 0
        reach = ((item.width * (2 if item.align == "inside" else 1) + 2 * item.outline_width) / 2.0
                 + soft_value / 2.0 + 3.0) * texel
        if not clean_value:
            # Smooth (or hard-edged) stroke: every layer's alpha is the area of the texel it covers.
            if faces is None:
                faces = _Faces(surface, texture_painter.parser)
            face_ok = np.ones(len(surface.entries), dtype=bool)
            if item.on:
                face_ok &= np.array([n.startswith(item.on) for n in surface.face_element])
            if item.groups:
                face_ok &= np.array([g in item.groups for g in surface.face_group])
            every = np.concatenate(polylines2d if polylines2d is not None else polylines)
            lo, hi = every.min(axis=0) - reach, every.max(axis=0) + reach
            centre = surface.centre[:, list(axes)] if (plane or polylines2d is not None) else surface.centre
            candidates = np.flatnonzero(source & (centre >= lo).all(axis=1) & (centre <= hi).all(axis=1))
            grid = _grid(samples, soft_value)
            if len(candidates):
                for color, indices, coverage, main in _coverage_layers(
                        surface, faces, item, polylines, plane, axes, direction, texel, candidates, grid, face_ok,
                        eligible, polylines2d, profiles):
                    count = _write(region, surface, indices, color, coverage, item, mirror_of, grid, texture_painter)
                    written += count if main else 0
            report.entries.append((name, written))
            continue
        if polylines2d is not None:
            # Wrapped shape: the lifted lines give the chains, the projected polygon decides what is inside, on
            # every layer; fill, outline and line are drawn once, in order, from all the chains together.
            coords2d = surface.position[:, list(axes)]
            runs, near_all = [], []
            for polyline in polylines:
                lo, hi = polyline.min(axis=0) - reach, polyline.max(axis=0) + reach
                near = allowed & (coords_all >= lo).all(axis=1) & (coords_all <= hi).all(axis=1)
                candidates = np.flatnonzero(near)
                near_all.append(candidates)
                if len(candidates):
                    samples_, corners = _resample(polyline, SAMPLE_STEP * texel)
                    runs.extend(_runs(surface, _hits(surface, candidates, samples_, coords_all[candidates], False,
                                                     direction, texel), corners))
            inside = []
            for polygon in polylines2d:
                lo, hi = polygon.min(axis=0), polygon.max(axis=0)
                near = allowed & (coords2d >= lo).all(axis=1) & (coords2d <= hi).all(axis=1)
                picked = np.flatnonzero(near)
                inside.append(picked[_inside_polygon(coords2d[picked], polygon)])
            inside = np.unique(np.concatenate(inside)) if inside else np.zeros(0, dtype=np.int64)
            layers = _pixel_layers(surface, item, runs, allowed, inside)
            if seam_on and polylines:
                layers = _seam_extend(surface, item, layers, polylines, coords_all,
                                      np.unique(np.concatenate(near_all)), texel)
            for color, indices, main in layers:
                count = _write(region, surface, indices, color, None, item, mirror_of)
                written += count if main else 0
            report.entries.append((name, written))
            continue
        for polyline in polylines:
            lo, hi = polyline.min(axis=0) - reach, polyline.max(axis=0) + reach
            near = allowed & (coords_all >= lo).all(axis=1) & (coords_all <= hi).all(axis=1)
            candidates = np.flatnonzero(near)
            if not len(candidates):
                continue
            samples_, corners = _resample(polyline, SAMPLE_STEP * texel)
            hits = _hits(surface, candidates, samples_, coords_all[candidates], plane, direction, texel)
            inside = None
            if item.fill is not None and plane:
                inside = candidates[_inside_polygon(coords_all[candidates], polyline)]
                if len(inside):            # the front-most surface at each point of the shape only
                    inside = inside[_front(surface, inside, coords_all[inside], direction, texel, slope=True)]
            layers = _pixel_layers(surface, item, _runs(surface, hits, corners), allowed, inside)
            if seam_on:
                layers = _seam_extend(surface, item, layers, [polyline], coords_all, candidates, texel)
            for color, indices, main in layers:
                count = _write(region, surface, indices, color, None, item, mirror_of)
                written += count if main else 0
        report.entries.append((name, written))
    return report.warn_empty()
