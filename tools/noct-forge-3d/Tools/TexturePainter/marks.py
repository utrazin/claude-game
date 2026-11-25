"""Visual tokens of painted marks: what a stamp leaves (``Tip``), how a stroke of stamps moves (``Brush``), where
strokes start (``Pattern``) and which way they go (``Direction``).

The same tokens drive every mark the painter lays on a model: brush layers over a material, scattered or regular
prints (spots, stars, scales), a single print, and stamped lines (``ink.stroke(..., tip=, brush=)``). A project
declares its tokens once in its theme (``Tools.TexturePainter.theme``) and derives variations with ``with_``::

    CHALK = Tip.grain(speck=0.9, cluster=5.0, clump=0.55, scale=0.08)
    DRAPE = Brush(radius=(0.4, 0.7), length=(8, 14), spacing=0.3, turn=2, spread=8, align=1)
    region.stamp(Pattern.scatter(coverage=0.6), tip=CHALK, brush=DRAPE.with_(direction=Direction.fall()), ...)

Sizes are model units, so a token looks the same at any texture density.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
import math
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

import numpy as np
from PIL import Image


# ---------------------------------------------------------------- grain
def _kernel(sigma):
    radius = int(math.ceil(3 * sigma))
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-x * x / (2 * sigma * sigma))
    return x, kernel / kernel.sum()


def _blur(image, sigma):
    """Separable gaussian blur with wrap-around (the grain tiles). ``sigma``: one value, or (rows, columns) for an
    anisotropic blur (streaky grains: fibres, charcoal)."""
    sigmas = (sigma, sigma) if np.isscalar(sigma) else tuple(sigma)
    out = image
    for axis, s in zip((0, 1), sigmas):
        if s <= 0:
            continue
        x, kernel = _kernel(s)
        out = sum(np.roll(out, shift, axis=axis) * w for shift, w in zip(x, kernel))
    return out


def _ranks(values):
    flat = np.asarray(values, dtype=float).ravel()
    rank = np.empty(flat.size)
    rank[np.argsort(flat, kind="stable")] = np.arange(flat.size) / (flat.size - 1)
    return rank.reshape(np.shape(values))


def grain_field(size=256, seed=7, speck=0.9, cluster=5.0, clump=0.55):
    """A tiling grain as a rank field in 0..1: fine speckles (blurred white noise of ``speck`` px) gathered in
    clusters (a coarser noise of ``cluster`` px, weighted by ``clump``). Sizes may be (rows, columns) pairs for
    streaks. A texel takes ink where the field is above ``1 - pressure``: light pressure leaves scattered hard specks,
    full pressure covers; the grain is never blurred, only thinned."""
    rng = np.random.default_rng(seed)
    fine = _blur(rng.random((size, size)), speck)
    coarse = _blur(rng.random((size, size)), cluster)
    fine = (fine - fine.mean()) / (fine.std() + 1e-9)
    coarse = (coarse - coarse.mean()) / (coarse.std() + 1e-9)
    return _ranks(fine + clump * coarse)


def _frozen(value):
    return tuple(_frozen(v) for v in value) if isinstance(value, (list, tuple)) else value


@lru_cache(maxsize=64)
def _cached_grain(size, seed, speck, cluster, clump):
    return grain_field(size, seed, speck, cluster, clump)


# ---------------------------------------------------------------- tip
@dataclass(frozen=True)
class Tip:
    """What one stamp leaves.

    Build one with ``Tip.grain(...)``, ``Tip.solid()`` or ``Tip.image(...)``.
    ``texture``: the options of a tiling grain (``grain_field``) laid inside the stamp, turned with it; None for
    solid ink. ``scale``: model units per grain pixel. ``motif``: an RGBA array; the stamp is that image fitted to
    the stamp's square (its alpha is the shape), else the stamp is a disc with a slightly ragged outline (``ragged``,
    0 round). ``colored``: the motif keeps its own colours instead of taking the brush's colours.
    ``seed``: a fixed grain seed (the same grain in every pass); None takes each pass's seed."""
    texture: Optional[dict] = None
    scale: float = 0.08
    motif: Optional[np.ndarray] = field(default=None, compare=False, repr=False)
    colored: bool = False
    ragged: float = 0.14
    seed: Optional[int] = None
    name: str = ""

    @classmethod
    def grain(cls, *, speck=0.9, cluster=5.0, clump=0.55, scale=0.08, seed=None, size=256, ragged=0.14,
                 name="grain"):
        """A grainy tip (chalk, dry brush, sponge, fibre): see ``grain_field``."""
        return cls(texture=dict(speck=_frozen(speck), cluster=_frozen(cluster), clump=float(clump), size=int(size)),
                   scale=float(scale), seed=seed, ragged=float(ragged), name=name).checked()

    @classmethod
    def solid(cls, ragged=0.0, name="solid"):
        """Solid ink in a round (``ragged`` 0) or ragged disc."""
        return cls(texture=None, ragged=float(ragged), name=name).checked()

    @classmethod
    def image(cls, source, *, colored=True, grain=None, name=""):
        """A printed motif: the image (path, PIL image or RGBA array) is the stamp, fitted to its square; its alpha is
        the shape. ``colored`` keeps the image's colours, else it is a mask tinted with the brush's colours.
        ``grain``: an optional grain ``Tip`` breaking it."""
        if isinstance(source, (str, Path)):
            source = Image.open(source)
        if isinstance(source, Image.Image):
            source = np.asarray(source.convert("RGBA"))
        array = np.asarray(source)
        if array.ndim != 3 or array.shape[2] != 4:
            raise ValueError("Tip.image: an RGBA image")
        base = grain if grain is not None else cls()
        return cls(texture=base.texture, scale=base.scale, motif=array.astype(np.uint8), colored=bool(colored),
                   ragged=0.0, seed=base.seed, name=name or "image").checked()

    def checked(self):
        """The tip itself, or ValueError listing its problems."""
        problems = self.problems("tip")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def problems(self, label):
        """Problems of this tip as messages prefixed with ``label`` (empty: valid)."""
        out = []
        if not self.scale > 0:
            out.append(f"{label}: scale must be positive model units per grain pixel")
        if not 0 <= self.ragged < 1:
            out.append(f"{label}: ragged must be in [0, 1)")
        if self.texture is not None:
            unknown = set(self.texture) - {"speck", "cluster", "clump", "size"}
            if unknown:
                out.append(f"{label}: unknown grain options {sorted(unknown)}")
        return out

    def with_(self, **changes) -> "Tip":
        """A copy with some parameters changed; grain options (speck, cluster, clump, size) change the grain."""
        grain = dict(self.texture or {})
        for key in ("speck", "cluster", "clump", "size"):
            if key in changes:
                grain[key] = _frozen(changes.pop(key))
        return replace(self, texture=grain or self.texture, **changes).checked()

    def field(self, seed):
        """The grain's rank field for a pass of ``seed`` (a fixed ``seed`` wins); None for solid ink."""
        if self.texture is None:
            return None
        g = self.texture
        s = self.seed if self.seed is not None else seed + 101
        return _cached_grain(g.get("size", 256), int(s), g["speck"], g["cluster"], g["clump"])

    def on_surface(self, position, normal, seed, *, scale=None):
        """The grain sampled on a surface, projected along each point's dominant normal axis (a box projection),
        in -0.5..0.5 (0 for solid ink): breaks the edge of an overlay or a gradient with the same grain."""
        rank = self.field(seed)
        if rank is None:
            return np.zeros(len(position))
        cell = self.scale if scale is None else scale
        axis = np.argmax(np.abs(normal), axis=1)
        plane = np.array([[1, 2], [0, 2], [0, 1]])[axis]
        rows = np.arange(len(position))
        a = np.floor(position[rows, plane[:, 0]] / cell).astype(np.int64)
        b = np.floor(position[rows, plane[:, 1]] / cell).astype(np.int64)
        size = rank.shape[0]
        return rank[a % size, b % size] - 0.5




# ---------------------------------------------------------------- direction
class Direction:
    """Which way strokes run at each surface point: ``direction(positions (K, 3), normals (K, 3)) -> (K, 3)``
    (projected on the surface by the painter). Directions are tokens: give them names in a theme."""

    def __init__(self, function: Callable, label: str):
        self.function, self.label = function, label

    def __call__(self, positions, normals):
        return np.asarray(self.function(np.asarray(positions, float), np.asarray(normals, float)), dtype=float)

    def __repr__(self):
        return f"Direction.{self.label}"

    @classmethod
    def around(cls, up=(0.0, 1.0, 0.0)):
        """Around the form, perpendicular to ``up`` (horizontal bands on an upright body)."""
        up = np.asarray(up, dtype=float)

        def f(positions, normals):
            d = np.cross(up, normals)
            bad = np.linalg.norm(d, axis=1) < 1e-3
            d[bad] = np.array([1.0, 0.0, 0.0])
            return d
        return cls(f, "around()")

    @classmethod
    def fall(cls, up=(0.0, 1.0, 0.0)):
        """Down the surface, the way cloth hangs."""
        up = np.asarray(up, dtype=float)
        around = cls.around(up)

        def f(positions, normals):
            d = up - normals * (normals @ up)[:, None]
            bad = np.linalg.norm(d, axis=1) < 1e-3
            d[bad] = around(positions[bad], normals[bad])
            return d
        return cls(f, "fall()")

    @classmethod
    def diagonal(cls, up=(0.0, 1.0, 0.0)):
        """Half way between around the form and down it (hatching)."""
        a, b = cls.around(up), cls.fall(up)

        def f(positions, normals):
            x, y = a(positions, normals), b(positions, normals)
            x /= np.linalg.norm(x, axis=1, keepdims=True)
            y /= np.linalg.norm(y, axis=1, keepdims=True)
            return x + y
        return cls(f, "diagonal()")

    @classmethod
    def away(cls, origin):
        """Out from a model point (fur growing out of a muzzle, rays from a centre)."""
        origin = np.asarray(origin, dtype=float)
        if origin.shape != (3,):
            raise ValueError("Direction.away: origin is a model point (x, y, z)")
        return cls(lambda positions, normals: positions - origin, f"away({tuple(origin.tolist())})")

    @classmethod
    def toward(cls, origin):
        """Toward a model point."""
        origin = np.asarray(origin, dtype=float)
        return cls(lambda positions, normals: origin - positions, f"toward({tuple(origin.tolist())})")

    @classmethod
    def fixed(cls, vector):
        """One model direction everywhere (projected on the surface)."""
        v = np.asarray(vector, dtype=float)
        if v.shape != (3,) or not np.linalg.norm(v):
            raise ValueError("Direction.fixed: a non-zero (x, y, z)")
        return cls(lambda positions, normals: np.tile(v, (len(positions), 1)), f"fixed({tuple(v.tolist())})")


# ---------------------------------------------------------------- brush
@dataclass(frozen=True)
class Brush:
    """How a stroke of stamps is made; the same parameters for painted strokes and stamped lines.

    radius    stamp radius in model units (min, max); a line's stamps take the line's width and a look's
              passes their size class instead
    size      multiplies the stamp radius, wherever it comes from (this radius, a size class, a line width)
    grain     multiplies the tip's grain size (2.5 shows streaks and blotches of the same grain)
    length    stamps per stroke (min, max): (1, 1) prints single stamps
    spacing   stamp spacing as a fraction of the radius
    turn      tip rotation per stamp in degrees (the grain turns as the stroke moves)
    direction a ``Direction`` (default: around the form); ``spread`` the random deviation from it, degrees
    align     0: the grain starts at a random angle; 1: it follows the stroke (streaky grains read as strokes)
    density   how much ink full pressure lays (0..1)
    taper     0: every stamp of a stroke is full size; up to 1: the stroke thins to both ends (hairs)
    taper_length  lines: thin only within this many model units of each end, to a point (None: the whole
              line tapers from its middle); a closed line has no ends
    swell     lines: the width varies smoothly along the path by up to this fraction (0.15: +-15 %), in waves
              about ``swell_length`` model units long (a hand's pressure, not per-stamp jitter)
    size_jitter  random size factor of each stamp (min, max)
    jitter    colour variation per stroke (hue degrees, saturation, value)
    falloff   share of the radius over which the pressure fades to the outline (the stamp ends in scattered grain)
    coverage  multiplies the coverage of the look passes painted with this brush (how densely strokes overlap)"""
    radius: Tuple[float, float] = (0.35, 0.6)
    size: float = 1.0
    grain: float = 1.0
    length: Tuple[int, int] = (3, 7)
    spacing: float = 0.45
    turn: float = 9.0
    direction: Optional[Direction] = None
    spread: float = 25.0
    align: float = 0.0
    density: float = 0.8
    taper: float = 0.0
    taper_length: Optional[float] = None
    swell: float = 0.0
    swell_length: float = 1.5
    size_jitter: Tuple[float, float] = (0.85, 1.1)
    jitter: Tuple[float, float, float] = (4.0, 0.06, 0.05)
    falloff: float = 0.45
    coverage: float = 1.0
    name: str = ""

    def __post_init__(self):
        problems = self.problems(self.name or "brush")
        if problems:
            raise ValueError("; ".join(problems))

    def problems(self, label):
        """Problems of this brush as messages prefixed with ``label`` (empty: valid)."""
        out = []
        if not (len(self.radius) == 2 and 0 < self.radius[0] <= self.radius[1]):
            out.append(f"{label}: radius must be (min, max) model units with 0 < min <= max")
        if not (len(self.length) == 2 and 1 <= self.length[0] <= self.length[1]):
            out.append(f"{label}: length must be (min, max) stamps with 1 <= min <= max")
        if not self.spacing > 0:
            out.append(f"{label}: spacing must be positive")
        if not self.size > 0 or not self.grain > 0 or not self.coverage > 0:
            out.append(f"{label}: size, grain and coverage must be positive")
        if not 0 <= self.align <= 1 or not 0 < self.density <= 1:
            out.append(f"{label}: align in 0..1 and density in (0, 1]")
        if not 0 <= self.taper < 1:
            out.append(f"{label}: taper must be in [0, 1)")
        if self.taper_length is not None and not self.taper_length > 0:
            out.append(f"{label}: taper_length must be positive model units")
        if not 0 <= self.swell < 1 or not self.swell_length > 0:
            out.append(f"{label}: swell in [0, 1) and a positive swell_length")
        if not (len(self.size_jitter) == 2 and 0 < self.size_jitter[0] <= self.size_jitter[1]):
            out.append(f"{label}: size_jitter must be (min, max) factors")
        if not 0 < self.falloff <= 1:
            out.append(f"{label}: falloff must be in (0, 1]")
        if self.direction is not None and not callable(self.direction):
            out.append(f"{label}: direction must be a Direction")
        return out

    def with_(self, **changes) -> "Brush":
        """A copy with some parameters changed (a variation of a theme's brush token)."""
        return replace(self, **changes)

    def scaled(self, factor) -> "Brush":
        """The same brush with stamps ``factor`` times larger."""
        return replace(self, size=self.size * factor)

    def stamp_radius(self, radius=None):
        """(min, max) stamp radius: ``radius`` (default the brush's own) times ``size``."""
        lo, hi = self.radius if radius is None else radius
        return (lo * self.size, hi * self.size)


# ---------------------------------------------------------------- pattern
@dataclass(frozen=True)
class Pattern:
    """Where strokes (or single prints) start on the surface.

    ``scatter``: random, by a weight (a Field of the surface, an array over the texels, or a function of the view):
    ``coverage`` sets how much of the weighted area the strokes cover, or ``count`` gives the number of strokes.
    ``lattice``: one stroke per cell of a 3D grid of ``spacing`` model units, nudged by ``jitter`` (0 regular, 1 a
    whole cell), on the texel nearest the cell's point: polka dots, scales, rows of stitches.
    ``at``: strokes at given model points (each snapped to the nearest texel): a single print.
    ``along``: strokes along polylines, used by stamped lines."""
    kind: str
    coverage: Optional[float] = None
    count: Optional[int] = None
    weight: object = None
    spacing: float = 1.0
    jitter: float = 0.0
    points: tuple = ()
    offset: Tuple[float, float, float] = (0.0, 0.0, 0.0)

    @classmethod
    def scatter(cls, coverage=None, *, count=None, weight=None):
        """Random starts by ``weight``: ``coverage`` of the weighted area, or exactly ``count`` strokes."""
        if (coverage is None) == (count is None):
            raise ValueError("Pattern.scatter: give coverage or count")
        if coverage is not None and not coverage > 0:
            raise ValueError("Pattern.scatter: coverage must be positive")
        if count is not None and not (isinstance(count, int) and count >= 0):
            raise ValueError("Pattern.scatter: count must be a non-negative integer")
        return cls("scatter", coverage=coverage, count=count, weight=weight)

    @classmethod
    def even(cls, coverage, *, weight=None):
        """Evenly spread random starts (a jittered grid, no clumps or holes) at the density ``scatter`` would give for
        ``coverage``; ``weight`` thins them out where it falls."""
        if not coverage > 0:
            raise ValueError("Pattern.even: coverage must be positive")
        return cls("even", coverage=float(coverage), weight=weight)

    @classmethod
    def lattice(cls, spacing, *, jitter=0.0, offset=(0.0, 0.0, 0.0), weight=None):
        """One start per cell of a 3D grid of ``spacing`` units, nudged by ``jitter``."""
        if not spacing > 0 or not 0 <= jitter <= 1:
            raise ValueError("Pattern.lattice: spacing > 0 and jitter in 0..1")
        return cls("lattice", spacing=float(spacing), jitter=float(jitter), offset=tuple(map(float, offset)),
                   weight=weight)

    @classmethod
    def at(cls, *points):
        """One start at the texel nearest each model point."""
        pts = tuple(tuple(map(float, p)) for p in points)
        if not pts or any(len(p) != 3 for p in pts):
            raise ValueError("Pattern.at: one or more model points (x, y, z)")
        return cls("at", points=pts)

    def with_(self, **changes) -> "Pattern":
        """A copy with some parameters changed."""
        return replace(self, **changes)

    def weights(self, view, where):
        """Per texel 0..1 start weight (0 outside ``where``)."""
        from .fields import Field
        w = self.weight
        if w is None:
            values = np.ones(view.count)
        elif isinstance(w, Field):
            values = w(view.position[:, 0], view.position[:, 1], view.position[:, 2], normal=view.normal)
        elif callable(w):
            values = w(view)
        else:
            values = w
        values = np.clip(np.asarray(values, dtype=float).reshape(-1), 0.0, 1.0)
        if len(values) != view.count:
            raise ValueError(f"pattern weight has {len(values)} values for {view.count} texels")
        return np.where(where, values, 0.0)

    def starts(self, view, where, rng, stroke_area, texel_area):
        """Texel indices where strokes start."""
        weight = self.weights(view, where)
        if self.kind == "scatter":
            total = float(weight.sum())
            if total <= 0:
                return np.zeros(0, dtype=np.int64)
            n = self.count if self.count is not None else int(round(self.coverage * total * texel_area / stroke_area))
            if n <= 0:
                return np.zeros(0, dtype=np.int64)
            return rng.choice(view.count, size=n, p=weight / total)
        if self.kind in ("lattice", "even"):
            idx = np.flatnonzero(weight > 0)
            if not len(idx):
                return np.zeros(0, dtype=np.int64)
            even = self.kind == "even"
            spacing = math.sqrt(stroke_area / self.coverage) if even else self.spacing
            jitter = 1.0 if even else self.jitter
            p = view.centre[idx] - np.asarray(self.offset)
            cells = np.floor(p / spacing).astype(np.int64)
            keys, inverse = np.unique(cells, axis=0, return_inverse=True)
            inverse = inverse.reshape(-1)
            cell_rng = np.random.default_rng(int(rng.integers(1 << 31)))
            targets = (keys + 0.5 + jitter * (cell_rng.random(keys.shape) - 0.5)) * spacing
            distance = np.linalg.norm(p - targets[inverse], axis=1)
            order = np.lexsort((distance, inverse))
            first = np.r_[True, inverse[order][1:] != inverse[order][:-1]]
            chosen = order[first]
            keep = chosen if even else chosen[distance[chosen] <= 0.5 * spacing]
            keep = keep[cell_rng.random(len(keep)) < weight[idx][keep]]
            return idx[keep]
        if self.kind == "at":
            idx = np.flatnonzero(where)
            if not len(idx):
                return np.zeros(0, dtype=np.int64)
            out = [idx[int(np.argmin(np.linalg.norm(view.centre[idx] - np.asarray(pt), axis=1)))]
                   for pt in self.points]
            return np.asarray(out, dtype=np.int64)
        raise ValueError(f"pattern {self.kind!r} has no surface starts")
