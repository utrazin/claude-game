"""Procedural fields: composable noise, masks and dithering for pixel art and painted textures.

A ``Field`` is a function of position that returns values in [0, 1]. Build one from a
generator (``Field.value``, ``gradient``, ``cells``, ``stripes``...), reshape it with
operators (``fbm``, ``warp``, ``remap``, ``contrast``, ``mix``...), then turn it into
colors with an output (``ramp``, ``dither``). The same expression serves pixel art
(hard ``ramp``/``dither``, ``texture_filter`` nearest) and painted art (smooth ``ramp``,
linear filter).

    rock = (Field.cells(scale=0.8, mode="edge").invert().contrast(3)
            .warp(Field.gradient(scale=0.5), strength=1.2)
            .mix(Field.gradient(scale=3).fbm(4), 0.35))
    shader = rock.ramp(["#2b2a33", "#5b5963", "#9c99a4"])
    painter.cliff.paint_field(shader)                 # on the model, continuous across faces
    shader.image((256, 256), extent=(8, 8), tileable=True).save("rock.png")   # seamless tile

Determinism: the same expression and seeds give the same values on every machine and
version; a generator whose output must change gets a new name instead of a silent change.
Fields are evaluated on whole arrays (``paint_field`` batches every face at once).
Position units are the ones of the painted space (model units by default), and
``scale`` of a generator is features per unit.

Extend per project with ``Field.from_function(fn)`` (``fn(x, y, z)`` on arrays, values in
[0, 1]) or ``Field.from_frame_function(fn)`` (``fn(frame)`` with normals and pixels), and
combine the result with every operator and output here.
"""
from __future__ import annotations

import functools
import itertools
import math
from typing import Callable, Optional, Sequence, Union

import numpy as np
from PIL import Image

from .core.color import parse_color

_KEEP = object()
FieldLike = Union["Field", int, float]
DITHER_METHODS = ("bayer2", "bayer4", "bayer8", "blue", "white", "ign", "cluster", "lines", "diagonal",
                  "floyd", "atkinson")
CELL_MODES = ("f1", "f2", "edge", "id")
STRIPE_SHAPES = ("saw", "sine", "triangle", "square")
_DIFFUSION = {
    "floyd": ((1, 0, 7 / 16), (-1, 1, 3 / 16), (0, 1, 5 / 16), (1, 1, 1 / 16)),
    "atkinson": ((1, 0, 1 / 8), (2, 0, 1 / 8), (-1, 1, 1 / 8), (0, 1, 1 / 8), (1, 1, 1 / 8), (0, 2, 1 / 8)),
}


# ------------------------------------------------------------------ hashing

def hash_cells(ix, iy=0, iz=0, seed=0):
    """Deterministic 32-bit hash of integer cell coordinates (uint32 array).

    The building block of every generator; use it to write new ones in a project.
    """
    with np.errstate(over="ignore"):
        def lift(value):
            return np.asarray(value).astype(np.int64).astype(np.uint32)
        h = (lift(seed) * np.uint32(0x9E3779B1) + lift(ix) * np.uint32(0x85EBCA6B)
             + lift(iy) * np.uint32(0xC2B2AE35) + lift(iz) * np.uint32(0x27D4EB2F))
        h = h ^ (h >> np.uint32(16))
        h = h * np.uint32(0x7FEB352D)
        h = h ^ (h >> np.uint32(15))
        h = h * np.uint32(0x846CA68B)
        h = h ^ (h >> np.uint32(16))
    return h


def unit_hash(ix, iy=0, iz=0, seed=0):
    """``hash_cells`` as floats in [0, 1)."""
    return (hash_cells(ix, iy, iz, seed) >> np.uint32(8)).astype(np.float64) / 16777216.0


# ------------------------------------------------------------------ frame

class Frame:
    """The positions a field is evaluated at, plus optional surface data.

    ``x``, ``y``, ``z`` are float arrays of one shape; ``normal`` has shape (..., 3) when
    the surface is known; ``pixel`` is the (x, y) canvas pixel arrays used by dithering;
    ``wrap`` holds the tile length per axis (or None) while building a seamless tile.
    """
    __slots__ = ("x", "y", "z", "normal", "pixel", "wrap", "grid")

    def __init__(self, x, y=0.0, z=0.0, *, normal=None, pixel=None, wrap=None, grid=None):
        x, y, z = np.broadcast_arrays(*(np.asarray(v, dtype=np.float64) for v in (x, y, z)))
        self.x, self.y, self.z = x, y, z
        self.normal = None if normal is None else np.asarray(normal, dtype=np.float64)
        self.pixel = pixel
        self.wrap = wrap
        self.grid = grid

    def moved(self, *, x=None, y=None, z=None, wrap=_KEEP):
        """A copy with replaced coordinates and/or tile lengths."""
        frame = Frame.__new__(Frame)
        frame.x = self.x if x is None else x
        frame.y = self.y if y is None else y
        frame.z = self.z if z is None else z
        frame.normal, frame.pixel, frame.grid = self.normal, self.pixel, self.grid
        frame.wrap = self.wrap if wrap is _KEEP else wrap
        return frame

    @property
    def shape(self):
        return self.x.shape


def _scaled_wrap(wrap, factors):
    if wrap is None:
        return None
    return tuple(None if w is None else w * f for w, f in zip(wrap, factors))


# ------------------------------------------------------------------ lattice helpers

def _fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _lattice(frame, scale, stretch):
    """Scaled coordinates and, per axis, the number of cells per tile (or None)."""
    freq = [scale * s for s in stretch]
    points = [frame.x * freq[0], frame.y * freq[1], frame.z * freq[2]]
    cells = []
    for axis in range(3):
        length = None if frame.wrap is None else frame.wrap[axis]
        if length is None:
            cells.append(None)
            continue
        count = length * freq[axis]
        rounded = round(count)
        if rounded < 1 or abs(count - rounded) > 1e-6:
            raise ValueError(
                f"Seamless tile: {length:g} units x {freq[axis]:g} features/unit = {count:g} cells on axis "
                f"{'xyz'[axis]}; choose a tile length that is a whole number of cells (use integer "
                f"lacunarity, for example 2, with fbm)")
        cells.append(rounded)
    return points, cells


def _wrapped(index, count):
    return index if count is None else np.mod(index, count)


def _corner_hash(index, offset, cells, seed):
    return unit_hash(*(_wrapped(index[a] + offset[a], cells[a]) for a in range(3)), seed)


def _value_noise(frame, scale, seed, stretch):
    points, cells = _lattice(frame, scale, stretch)
    floor = [np.floor(p) for p in points]
    index = [f.astype(np.int64) for f in floor]
    fade = [_fade(p - f) for p, f in zip(points, floor)]
    total = 0.0
    for offset in itertools.product((0, 1), repeat=3):
        weight = 1.0
        for axis in range(3):
            weight = weight * (fade[axis] if offset[axis] else 1.0 - fade[axis])
        total = total + weight * _corner_hash(index, offset, cells, seed)
    return total


_GRADIENTS = np.array([(1, 1, 0), (-1, 1, 0), (1, -1, 0), (-1, -1, 0), (1, 0, 1), (-1, 0, 1),
                       (1, 0, -1), (-1, 0, -1), (0, 1, 1), (0, -1, 1), (0, 1, -1), (0, -1, -1)],
                      dtype=np.float64)
_GRADIENT_RANGE = 0.95  # raw gradient noise stays inside about +-0.94 for these vectors


def _gradient_noise(frame, scale, seed, stretch):
    points, cells = _lattice(frame, scale, stretch)
    floor = [np.floor(p) for p in points]
    index = [f.astype(np.int64) for f in floor]
    local = [p - f for p, f in zip(points, floor)]
    fade = [_fade(t) for t in local]
    total = 0.0
    for offset in itertools.product((0, 1), repeat=3):
        weight = 1.0
        for axis in range(3):
            weight = weight * (fade[axis] if offset[axis] else 1.0 - fade[axis])
        pick = (hash_cells(*(_wrapped(index[a] + offset[a], cells[a]) for a in range(3)), seed)
                % np.uint32(12)).astype(np.int64)
        dot = sum(_GRADIENTS[:, a].take(pick) * (local[a] - offset[a]) for a in range(3))
        total = total + weight * dot
    return np.clip(0.5 + 0.5 * total / _GRADIENT_RANGE, 0.0, 1.0)


def _cell_noise(frame, scale, seed, stretch, mode, jitter, metric):
    points, cells = _lattice(frame, scale, stretch)
    floor = [np.floor(p) for p in points]
    index = [f.astype(np.int64) for f in floor]
    first = np.full(frame.shape, np.inf)
    second = np.full(frame.shape, np.inf)
    winner = np.zeros(frame.shape, dtype=np.uint32)
    for offset in itertools.product((-1, 0, 1), repeat=3):
        h = hash_cells(*(_wrapped(index[a] + offset[a], cells[a]) for a in range(3)), seed)
        delta = []
        for a in range(3):                         # one 10-bit jitter per axis from the cell hash
            bits = ((h >> np.uint32(10 * a)) & np.uint32(1023)).astype(np.float64) / 1024.0
            delta.append(np.abs(points[a] - (floor[a] + offset[a] + 0.5 + jitter * (bits - 0.5))))
        if metric == "euclid":
            distance = delta[0] * delta[0] + delta[1] * delta[1] + delta[2] * delta[2]
        elif metric == "manhattan":
            distance = delta[0] + delta[1] + delta[2]
        else:
            distance = np.maximum(np.maximum(delta[0], delta[1]), delta[2])
        closer = distance < first
        second = np.where(closer, first, np.minimum(second, distance))
        winner = np.where(closer, h, winner)
        first = np.where(closer, distance, first)
    if metric == "euclid":
        first, second = np.sqrt(first), np.sqrt(second)
    if mode == "f1":
        return np.clip(first, 0.0, 1.0)
    if mode == "f2":
        return np.clip(second / 1.5, 0.0, 1.0)
    if mode == "edge":
        return np.clip(second - first, 0.0, 1.0)
    return unit_hash(winner, 0, 0, seed + 7)

def _wave(phase, shape, duty):
    phase = phase - np.floor(phase)
    if shape == "saw":
        return phase
    if shape == "sine":
        return 0.5 - 0.5 * np.cos(phase * 2.0 * math.pi)
    if shape == "triangle":
        return 1.0 - np.abs(2.0 * phase - 1.0)
    return (phase < duty).astype(np.float64)


# ------------------------------------------------------------------ the Field class

class Field:
    """Scalar field of values in [0, 1] over positions; compose with operators, finish with an output.

    Generators (class methods): ``value``, ``gradient``, ``cells``, ``stripes``, ``rings``,
    ``white``, ``constant``, ``height``, ``facing``, ``from_function``, ``from_frame_function``.
    Operators return new fields: ``fbm``, ``warp``, ``remap``, ``contrast``, ``gamma``, ``curve``,
    ``threshold``, ``steps``, ``invert``, ``ridge``, ``billow``, ``mix``, ``clip``, ``scale``,
    ``stretch``, ``offset``, ``rotate`` and the operators ``+ - * | & ~``. Outputs: ``ramp``,
    ``dither`` (shaders), ``image`` (grayscale).
    """

    def __init__(self, evaluate: Callable[[Frame], np.ndarray], label: str = "field"):
        self._evaluate = evaluate
        self.label = label

    def __repr__(self):
        return f"<Field {self.label}>"

    def _eval(self, frame: Frame) -> np.ndarray:
        value = np.asarray(self._evaluate(frame), dtype=np.float64)
        return np.broadcast_to(value, frame.shape)

    def __call__(self, x, y=0.0, z=0.0, *, normal=None) -> np.ndarray:
        """Values at positions (arrays of any shape); ``normal`` is only needed by ``facing``."""
        return np.array(self._eval(Frame(x, y, z, normal=normal)))

    # ---------------------------------------------------------------- generators
    @classmethod
    def value(cls, scale: float = 1.0, seed: int = 0, stretch: Sequence[float] = (1, 1, 1)) -> "Field":
        """Smooth blobs from interpolated random lattice values. ``scale`` is cells per unit;
        ``stretch`` multiplies the frequency per axis (``(1, 6, 1)`` gives horizontal streaks)."""
        _check_positive(scale, "scale")
        stretch = _triple(stretch, "stretch")
        return cls(lambda f: _value_noise(f, scale, seed, stretch), f"value({scale:g})")

    @classmethod
    def gradient(cls, scale: float = 1.0, seed: int = 0, stretch: Sequence[float] = (1, 1, 1)) -> "Field":
        """Perlin-style gradient noise: finer, less blobby than ``value``; good base for ``fbm``/``ridge``."""
        _check_positive(scale, "scale")
        stretch = _triple(stretch, "stretch")
        return cls(lambda f: _gradient_noise(f, scale, seed, stretch), f"gradient({scale:g})")

    @classmethod
    def cells(cls, scale: float = 1.0, seed: int = 0, stretch: Sequence[float] = (1, 1, 1), *,
              mode: str = "f1", jitter: float = 1.0, metric: str = "euclid") -> "Field":
        """Worley cells. ``mode``: ``f1`` distance to the nearest point (blobs, scales), ``f2``
        second nearest, ``edge`` gap between them (cracks, mortar: thresholding gives lines),
        ``id`` flat random value per cell (patches, tiles). ``jitter`` 0 gives a regular grid;
        ``metric``: euclid, manhattan or chebyshev."""
        _check_positive(scale, "scale")
        stretch = _triple(stretch, "stretch")
        if mode not in CELL_MODES:
            raise ValueError(f"mode must be one of {', '.join(CELL_MODES)}")
        if metric not in ("euclid", "manhattan", "chebyshev"):
            raise ValueError("metric must be euclid, manhattan or chebyshev")
        if not 0.0 <= jitter <= 1.0:
            raise ValueError("jitter must be between 0 and 1")
        return cls(lambda f: _cell_noise(f, scale, seed, stretch, mode, jitter, metric), f"cells({mode})")

    @classmethod
    def white(cls, scale: float = 1.0, seed: int = 0) -> "Field":
        """Independent random value per cell, no smoothing: fine grain, speckle, per-patch variation."""
        _check_positive(scale, "scale")

        def evaluate(frame):
            cells = []
            for axis, coordinate in enumerate((frame.x, frame.y, frame.z)):
                scaled = coordinate * scale
                cell = np.floor(scaled).astype(np.int64)
                if frame.wrap is not None and frame.wrap[axis] is not None:
                    count = round(frame.wrap[axis] * scale)
                    if count < 1 or abs(frame.wrap[axis] * scale - count) > 1e-6:
                        raise ValueError("Seamless tile: tile length must be a whole number of white cells")
                    cell = np.mod(cell, count)
                cells.append(cell)
            return unit_hash(*cells, seed)
        return cls(evaluate, f"white({scale:g})")

    @classmethod
    def stripes(cls, frequency: float = 1.0, direction: Sequence[float] = (1, 0, 0), *, shape: str = "saw",
                duty: float = 0.5, phase: float = 0.0) -> "Field":
        """Repeating bands along ``direction``: ``frequency`` repeats per unit. ``shape``: saw (ramp),
        sine, triangle, square (``duty`` is the filled share). Bend them with ``warp``."""
        _check_positive(frequency, "frequency")
        if shape not in STRIPE_SHAPES:
            raise ValueError(f"shape must be one of {', '.join(STRIPE_SHAPES)}")
        vector = np.array(_triple(direction, "direction"), dtype=np.float64)
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            raise ValueError("direction must not be zero")
        vector = vector / norm

        def evaluate(frame):
            if frame.wrap is not None:
                for axis in range(3):
                    length = frame.wrap[axis]
                    if length is not None:
                        repeats = length * frequency * abs(vector[axis])
                        if abs(repeats - round(repeats)) > 1e-6:
                            raise ValueError("Seamless tile: stripes must repeat a whole number of times per tile")
            coordinate = frame.x * vector[0] + frame.y * vector[1] + frame.z * vector[2]
            return _wave(coordinate * frequency + phase, shape, duty)
        return cls(evaluate, f"stripes({frequency:g})")

    @classmethod
    def rings(cls, center: Sequence[float] = (0, 0, 0), frequency: float = 1.0, *, shape: str = "sine",
              duty: float = 0.5, axis: Optional[str] = None) -> "Field":
        """Concentric bands around ``center`` (tree rings, ripples). ``axis`` ``"y"`` measures the
        distance in the plane around that axis only (cylinders). Not tileable."""
        _check_positive(frequency, "frequency")
        if shape not in STRIPE_SHAPES:
            raise ValueError(f"shape must be one of {', '.join(STRIPE_SHAPES)}")
        if axis not in (None, "x", "y", "z"):
            raise ValueError("axis must be x, y, z or None")
        origin = _triple(center, "center")

        def evaluate(frame):
            if frame.wrap is not None:
                raise ValueError("rings cannot be tiled; build the tile from stripes or noise")
            delta = [frame.x - origin[0], frame.y - origin[1], frame.z - origin[2]]
            if axis is not None:
                delta["xyz".index(axis)] = delta["xyz".index(axis)] * 0.0
            distance = np.sqrt(delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2)
            return _wave(distance * frequency, shape, duty)
        return cls(evaluate, f"rings({frequency:g})")

    @classmethod
    def constant(cls, value: float) -> "Field":
        """The same value everywhere (0..1); mix it with other fields to bias them."""
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("constant value must be between 0 and 1")
        return cls(lambda f: np.full(f.shape, float(value)), f"constant({value:g})")

    @classmethod
    def height(cls, axis: str = "y", low: float = 0.0, high: float = 1.0) -> "Field":
        """0 at ``low`` and 1 at ``high`` along an axis (clamped): vertical gradients, dripping, ground contact."""
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        if high == low:
            raise ValueError("high and low must differ")
        index = "xyz".index(axis)

        def evaluate(frame):
            coordinate = (frame.x, frame.y, frame.z)[index]
            return np.clip((coordinate - low) / (high - low), 0.0, 1.0)
        return cls(evaluate, f"height({axis})")

    @classmethod
    def facing(cls, direction: Sequence[float] = (0, 1, 0), power: float = 1.0) -> "Field":
        """How much the surface faces ``direction`` (1 facing it, 0 side-on or away): moss on top, dust, sun side.
        Needs surface normals, so use it inside ``paint_field``."""
        _check_positive(power, "power")
        vector = np.array(_triple(direction, "direction"), dtype=np.float64)
        norm = float(np.linalg.norm(vector))
        if norm == 0:
            raise ValueError("direction must not be zero")
        vector = vector / norm

        def evaluate(frame):
            if frame.normal is None:
                raise ValueError("facing needs surface normals; use it inside paint_field")
            return np.clip(frame.normal @ vector, 0.0, 1.0) ** power
        return cls(evaluate, "facing")

    @classmethod
    def light(cls, key: Sequence[float] = (0, 1, 0), *, fill: Optional[Sequence[float]] = None,
              fill_strength: float = 0.0, ambient: float = 0.48) -> "Field":
        """How lit the surface is by a key light from ``key`` (a direction towards the light): ``ambient`` where
        the surface is side-on, rising to 1 facing the light and falling to 0 facing away (``ambient +
        (1 - ambient) * n.key``, clamped). An optional ``fill`` light adds up to ``fill_strength`` only where the key
        light misses, so tops and fronts keep their values. The shading value painted layers follow (where the
        lights and shadows of a look land). Needs surface normals."""
        if not 0.0 <= ambient <= 1.0 or fill_strength < 0:
            raise ValueError("ambient must be in 0..1 and fill_strength non-negative")

        def unit(v, label):
            v = np.array(_triple(v, label), dtype=np.float64)
            n = float(np.linalg.norm(v))
            if n == 0:
                raise ValueError(f"{label} must not be zero")
            return v / n
        k = unit(key, "key")
        f = None if fill is None else unit(fill, "fill")

        def evaluate(frame):
            if frame.normal is None:
                raise ValueError("light needs surface normals; use it inside paint_field")
            facing = frame.normal @ k
            value = ambient + (1.0 - ambient) * facing
            if f is not None and fill_strength:
                away = np.clip(-2.0 * facing, 0.0, 1.0)
                value = value + fill_strength * np.maximum(0.0, frame.normal @ f) * away
            return np.clip(value, 0.0, 1.0)
        return cls(evaluate, "light")

    @classmethod
    def from_function(cls, function: Callable, label: str = "custom") -> "Field":
        """A project-specific generator: ``function(x, y, z)`` takes float arrays and returns values
        in [0, 1]. Not tileable (it receives no tile length)."""
        def evaluate(frame):
            if frame.wrap is not None:
                raise ValueError(f"{label} cannot be tiled; use Field.from_frame_function and honor frame.wrap")
            return _unit_range(function(frame.x, frame.y, frame.z), label)
        return cls(evaluate, label)

    @classmethod
    def from_frame_function(cls, function: Callable[[Frame], np.ndarray], label: str = "custom") -> "Field":
        """Like ``from_function`` but ``function(frame)`` also gets ``frame.normal``, ``frame.pixel`` and
        ``frame.wrap`` (tile lengths per axis, or None)."""
        return cls(lambda frame: _unit_range(function(frame), label), label)

    # ---------------------------------------------------------------- coordinate operators
    def scale(self, factor: float) -> "Field":
        """Evaluate at coordinates multiplied by ``factor`` (features get ``factor`` times smaller)."""
        _check_positive(factor, "factor")
        return Field(lambda f: self._eval(f.moved(x=f.x * factor, y=f.y * factor, z=f.z * factor,
                                                  wrap=_scaled_wrap(f.wrap, (factor,) * 3))), self.label)

    def stretch(self, x: float = 1.0, y: float = 1.0, z: float = 1.0) -> "Field":
        """Multiply coordinates per axis: ``stretch(y=4)`` squeezes the pattern into thin horizontal bands."""
        for value in (x, y, z):
            _check_positive(value, "stretch factor")
        return Field(lambda f: self._eval(f.moved(x=f.x * x, y=f.y * y, z=f.z * z,
                                                  wrap=_scaled_wrap(f.wrap, (x, y, z)))), self.label)

    def offset(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> "Field":
        """Shift the pattern by a distance in position units."""
        return Field(lambda f: self._eval(f.moved(x=f.x + x, y=f.y + y, z=f.z + z)), self.label)

    def rotate(self, degrees: float, axis: str = "z") -> "Field":
        """Rotate the pattern around an axis (degrees). Not tileable."""
        if axis not in ("x", "y", "z"):
            raise ValueError("axis must be x, y or z")
        cos, sin = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))

        def evaluate(frame):
            if frame.wrap is not None:
                raise ValueError("rotate cannot be tiled")
            a, b = {"z": (frame.x, frame.y), "y": (frame.z, frame.x), "x": (frame.y, frame.z)}[axis]
            ra, rb = a * cos - b * sin, a * sin + b * cos
            if axis == "z":
                return self._eval(frame.moved(x=ra, y=rb))
            if axis == "y":
                return self._eval(frame.moved(z=ra, x=rb))
            return self._eval(frame.moved(y=ra, z=rb))
        return Field(evaluate, self.label)

    def warp(self, by: "Field", strength: float = 0.25) -> "Field":
        """Domain warp: shift the sample position by ``by`` (up to ``strength`` units in each axis), which
        bends bands and blobs into organic shapes. Use a lower scale in ``by`` than in ``self``."""
        by = _as_field(by)
        shifts = ((0.0, 0.0, 0.0), (5.2, 1.3, 3.7), (9.1, 7.7, 2.1))

        def evaluate(frame):
            moved = []
            for coordinate, shift in zip((frame.x, frame.y, frame.z), shifts):
                probe = frame.moved(x=frame.x + shift[0], y=frame.y + shift[1], z=frame.z + shift[2])
                moved.append(coordinate + strength * 2.0 * (by._eval(probe) - 0.5))
            return self._eval(frame.moved(x=moved[0], y=moved[1], z=moved[2]))
        return Field(evaluate, f"warp({self.label})")

    def fbm(self, octaves: int = 4, lacunarity: float = 2.0, gain: float = 0.5) -> "Field":
        """Sum ``octaves`` copies of this field at ``lacunarity`` x the frequency and ``gain`` x the amplitude
        each (detail on detail). Fewer octaves read smoother; ``gain`` near 1 gives rougher results."""
        if not isinstance(octaves, int) or not 1 <= octaves <= 12:
            raise ValueError("octaves must be an integer from 1 to 12")
        _check_positive(lacunarity, "lacunarity")
        if gain <= 0:
            raise ValueError("gain must be positive")

        def evaluate(frame):
            total, amplitude, norm = 0.0, 1.0, 0.0
            for k in range(octaves):
                factor = lacunarity ** k
                step = frame.moved(x=frame.x * factor + 37.1 * k, y=frame.y * factor + 17.7 * k,
                                   z=frame.z * factor + 29.3 * k, wrap=_scaled_wrap(frame.wrap, (factor,) * 3))
                total = total + amplitude * self._eval(step)
                norm += amplitude
                amplitude *= gain
            return total / norm
        return Field(evaluate, f"fbm({self.label})")

    # ---------------------------------------------------------------- value operators
    def _map(self, function, label) -> "Field":
        return Field(lambda f: function(self._eval(f)), label)

    def remap(self, low: float, high: float) -> "Field":
        """Stretch the range [low, high] to [0, 1] and clamp: crop the dark/light ends of noise."""
        if high == low:
            raise ValueError("high and low must differ")
        return self._map(lambda v: np.clip((v - low) / (high - low), 0.0, 1.0), "remap")

    def contrast(self, amount: float = 2.0, pivot: float = 0.5) -> "Field":
        """Push values away from ``pivot`` (amount > 1) or toward it (< 1)."""
        if amount < 0:
            raise ValueError("amount must not be negative")
        return self._map(lambda v: np.clip((v - pivot) * amount + pivot, 0.0, 1.0), "contrast")

    def gamma(self, power: float) -> "Field":
        """Raise values to ``power``: above 1 darkens the mids, below 1 lightens them."""
        _check_positive(power, "power")
        return self._map(lambda v: v ** power, "gamma")

    def curve(self, points: Sequence[Sequence[float]]) -> "Field":
        """Piecewise-linear remap through ``(input, output)`` points sorted by input, e.g.
        ``[(0, 0), (0.4, 0.1), (0.6, 0.9), (1, 1)]`` for a steep middle."""
        pairs = sorted((float(a), float(b)) for a, b in points)
        if len(pairs) < 2 or len({a for a, _ in pairs}) != len(pairs):
            raise ValueError("curve needs at least two points with distinct inputs")
        xs, ys = zip(*pairs)
        return self._map(lambda v: np.clip(np.interp(v, xs, ys), 0.0, 1.0), "curve")

    def threshold(self, at: float = 0.5, softness: float = 0.0) -> "Field":
        """1 above ``at`` and 0 below; ``softness`` widens the edge (0 gives hard pixel-art shapes)."""
        if softness < 0:
            raise ValueError("softness must not be negative")

        def apply(v):
            if softness == 0:
                return (v >= at).astype(np.float64)
            t = np.clip((v - (at - softness / 2)) / softness, 0.0, 1.0)
            return t * t * (3.0 - 2.0 * t)
        return self._map(apply, "threshold")

    def steps(self, levels: int) -> "Field":
        """Quantize to ``levels`` evenly spaced values (posterize): cel-shaded bands."""
        if not isinstance(levels, int) or levels < 2:
            raise ValueError("levels must be an integer of at least 2")
        return self._map(lambda v: np.minimum(np.floor(v * levels), levels - 1) / (levels - 1), "steps")

    def invert(self) -> "Field":
        """1 - value."""
        return self._map(lambda v: 1.0 - v, "invert")

    def ridge(self, sharpness: float = 1.0) -> "Field":
        """Fold around 0.5 into sharp bright creases: ``1 - |2v - 1|`` (veins, mountain ridges, cracks) when
        followed by ``fbm``. ``sharpness`` raises the result to a power."""
        _check_positive(sharpness, "sharpness")
        return self._map(lambda v: (1.0 - np.abs(2.0 * v - 1.0)) ** sharpness, "ridge")

    def billow(self) -> "Field":
        """Fold into soft round lumps: ``|2v - 1|`` (clouds, puffy cloth, pillowed stone)."""
        return self._map(lambda v: np.abs(2.0 * v - 1.0), "billow")

    def clip(self, low: float = 0.0, high: float = 1.0) -> "Field":
        """Clamp to [low, high] without rescaling."""
        return self._map(lambda v: np.clip(v, low, high), "clip")

    def mix(self, other: FieldLike, by: FieldLike = 0.5) -> "Field":
        """Blend toward ``other`` by ``by`` (a number, or a field as a mask)."""
        other, by = _as_field(other), _as_field(by)
        return Field(lambda f: self._eval(f) * (1.0 - by._eval(f)) + other._eval(f) * by._eval(f), "mix")

    def _combine(self, other, function, label):
        other = _as_field(other)
        return Field(lambda f: np.clip(function(self._eval(f), other._eval(f)), 0.0, 1.0), label)

    def __add__(self, other):
        return self._combine(other, np.add, "add")

    __radd__ = __add__

    def __sub__(self, other):
        return self._combine(other, np.subtract, "sub")

    def __rsub__(self, other):
        return _as_field(other)._combine(self, np.subtract, "sub")

    def __mul__(self, other):
        return self._combine(other, np.multiply, "mul")

    __rmul__ = __mul__

    def __or__(self, other):
        return self._combine(other, np.maximum, "max")

    def __and__(self, other):
        return self._combine(other, np.minimum, "min")

    def __invert__(self):
        return self.invert()

    # ---------------------------------------------------------------- outputs
    def ramp(self, colors: Sequence, stops: Optional[Sequence[float]] = None, *, smooth: bool = True) -> "Shader":
        """Map values to colors (hex strings or 0-255 tuples; alpha allowed). ``smooth=False`` snaps to the
        color of the last stop below the value: hard bands for pixel art. ``stops`` are increasing values
        in [0, 1] (default evenly spaced)."""
        palette = _palette(colors)
        positions = np.linspace(0.0, 1.0, len(palette)) if stops is None else np.asarray(stops, dtype=np.float64)
        if len(positions) != len(palette) or np.any(np.diff(positions) < 0):
            raise ValueError("stops must be non-decreasing and match the number of colors")

        def render(frame):
            v = self._eval(frame)
            if smooth:
                return np.stack([np.interp(v, positions, palette[:, c]) for c in range(4)], axis=-1)
            pick = np.clip(np.searchsorted(positions, v, side="right") - 1, 0, len(palette) - 1)
            return palette[pick]
        return Shader(render, f"ramp({self.label})")

    def dither(self, colors: Sequence, method: str = "bayer4", *, scale: int = 1, strength: float = 1.0,
               seed: int = 0) -> "Shader":
        """Pick between neighboring colors by value with a threshold pattern, so gradients become pixel-art
        textures made only of ``colors``. ``method``: bayer2/4/8 (regular), blue (even, organic), white (random
        grain), ign (soft diagonal grain), cluster (halftone dots), lines, diagonal, and the error diffusions
        floyd and atkinson (images only: ``Shader.image``). ``scale`` makes pattern pixels ``scale`` canvas pixels
        wide; ``strength`` 0 gives hard bands, 1 full dithering."""
        palette = _palette(colors)
        if len(palette) < 2:
            raise ValueError("dither needs at least two colors")
        if method not in DITHER_METHODS:
            raise ValueError(f"method must be one of {', '.join(DITHER_METHODS)}")
        if not isinstance(scale, int) or scale < 1:
            raise ValueError("scale must be a positive integer")
        if strength < 0:
            raise ValueError("strength must not be negative")
        count = len(palette)

        def render(frame):
            v = self._eval(frame)
            if method in _DIFFUSION:
                if frame.grid is None:
                    raise ValueError(f"{method} diffusion needs an image; use Shader.image or another method")
                return palette[_diffuse(v, count, _DIFFUSION[method])]
            if frame.pixel is None:
                raise ValueError("dither needs canvas pixels; use it inside paint_field or Shader.image")
            threshold = 0.5 + (_threshold(method, frame.pixel[0] // scale, frame.pixel[1] // scale, seed) - 0.5) * strength
            position = np.clip(v, 0.0, 1.0) * (count - 1)
            base = np.minimum(np.floor(position), count - 2)
            return palette[(base + ((position - base) > threshold)).astype(np.int64)]
        return Shader(render, f"dither({method})")

    def image(self, size: Sequence[int], extent: Optional[Sequence[float]] = None, *, z: float = 0.0,
              tileable: bool = False) -> Image.Image:
        """Grayscale ('L') image of the field, for masks and previews. See ``Shader.image`` for the parameters."""
        grid, frame = _image_frame(size, extent, z, tileable)
        return Image.fromarray(np.rint(self._eval(frame) * 255.0).astype(np.uint8))


class Shader:
    """A field turned into colors (RGBA 0-255). Paint it with ``paint_field`` or render it with ``image``."""

    def __init__(self, render: Callable[[Frame], np.ndarray], label: str = "shader"):
        self._render = render
        self.label = label

    def __repr__(self):
        return f"<Shader {self.label}>"

    def render(self, frame: Frame) -> np.ndarray:
        """RGBA floats (0-255) of shape ``frame.shape + (4,)``."""
        return np.asarray(self._render(frame), dtype=np.float64)

    def masked(self, mask: FieldLike) -> "Shader":
        """Multiply the alpha by a field or number (0..1): paint only where the mask is high."""
        mask = _as_field(mask)

        def render(frame):
            colors = np.array(self.render(frame))
            colors[..., 3] = colors[..., 3] * mask._eval(frame)
            return colors
        return Shader(render, f"masked({self.label})")

    def over(self, below: "Shader") -> "Shader":
        """Composite this shader over ``below`` with alpha: stack several fields into one layered surface."""
        def render(frame):
            top, bottom = self.render(frame), below.render(frame)
            a1, a2 = top[..., 3:] / 255.0, bottom[..., 3:] / 255.0
            alpha = a1 + a2 * (1.0 - a1)
            safe = np.where(alpha > 0, alpha, 1.0)
            rgb = (top[..., :3] * a1 + bottom[..., :3] * a2 * (1.0 - a1)) / safe
            return np.concatenate([rgb, alpha * 255.0], axis=-1)
        return Shader(render, f"over({self.label})")

    def image(self, size: Sequence[int], extent: Optional[Sequence[float]] = None, *, z: float = 0.0,
              tileable: bool = False) -> Image.Image:
        """Render an RGBA image of ``size`` (width, height) pixels covering ``extent`` (width, height) position
        units (default one unit per pixel). Use ``extent=(tile_units, tile_units)`` and ``tileable=True`` for a
        seamless tile to project with ``project_triplanar(scale=1/tile_units)``; every generator must then fit a
        whole number of cells in the extent. ``z`` picks the slice of 3D fields."""
        grid, frame = _image_frame(size, extent, z, tileable)
        return Image.fromarray(np.clip(np.rint(self.render(frame)), 0, 255).astype(np.uint8))


# ------------------------------------------------------------------ helpers

def _check_positive(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be a positive number")


def _triple(values, label):
    values = tuple(float(v) for v in values)
    if len(values) != 3 or not all(math.isfinite(v) for v in values):
        raise ValueError(f"{label} must be three finite numbers")
    if label == "stretch" and any(v <= 0 for v in values):
        raise ValueError("stretch factors must be positive")
    return values


def _as_field(value) -> Field:
    if isinstance(value, Field):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"expected a Field or a number between 0 and 1, got {type(value).__name__}")
    return Field.constant(value)


def _unit_range(values, label):
    values = np.asarray(values, dtype=np.float64)
    if not np.isfinite(values).all() or values.min(initial=0.0) < -1e-9 or values.max(initial=0.0) > 1.0 + 1e-9:
        raise ValueError(f"{label}: field values must be finite and between 0 and 1")
    return np.clip(values, 0.0, 1.0)


def _palette(colors) -> np.ndarray:
    if isinstance(colors, (str, bytes)) or len(colors) < 1:
        raise ValueError("colors must be a list of at least one color")
    return np.array([parse_color(c) for c in colors], dtype=np.float64)


def _image_frame(size, extent, z, tileable):
    width, height = (int(v) for v in size)
    if width < 1 or height < 1:
        raise ValueError("size must be positive")
    ew, eh = (float(width), float(height)) if extent is None else (float(extent[0]), float(extent[1]))
    if ew <= 0 or eh <= 0:
        raise ValueError("extent must be positive")
    columns, rows = np.meshgrid(np.arange(width), np.arange(height))
    frame = Frame((columns + 0.5) * ew / width, (rows + 0.5) * eh / height, z, pixel=(columns, rows),
                  wrap=(ew, eh, None) if tileable else None, grid=(height, width))
    return (height, width), frame


@functools.lru_cache(maxsize=None)
def _bayer(size: int) -> np.ndarray:
    matrix = np.array([[0, 2], [3, 1]])
    while matrix.shape[0] < size:
        matrix = np.block([[4 * matrix, 4 * matrix + 2], [4 * matrix + 3, 4 * matrix + 1]])
    return matrix


_CLUSTER = np.array([[12, 5, 6, 13], [4, 0, 1, 7], [11, 3, 2, 8], [15, 10, 9, 14]])


@functools.lru_cache(maxsize=None)
def blue_noise_ranks(size: int = 64, sigma: float = 1.5) -> np.ndarray:
    """Blue-noise ranks 0..size*size-1 (void-and-cluster, tileable, deterministic), shape (size, size)."""
    total = size * size
    distance = np.minimum(np.arange(size), size - np.arange(size))
    squared = distance[:, None] ** 2 + distance[None, :] ** 2
    kernel = np.rint(np.exp(-squared / (2.0 * sigma * sigma)) * (1 << 20)).astype(np.int64)
    pattern = np.zeros(total, dtype=bool)
    pattern[np.argsort(hash_cells(np.arange(total), 0, 0, 99), kind="stable")[: total // 10]] = True
    energy = np.zeros((size, size), dtype=np.int64)

    def shift(index, sign):
        row, column = divmod(int(index), size)
        energy.__iadd__(sign * np.roll(kernel, (row, column), axis=(0, 1)))
        pattern[index] = sign > 0

    for index in np.flatnonzero(pattern):
        shift(index, 1)
    big = np.int64(1) << 60
    while True:                                     # relax the initial pattern
        cluster = int(np.argmax(np.where(pattern, energy.ravel(), -1)))
        shift(cluster, -1)
        void = int(np.argmin(np.where(pattern, big, energy.ravel())))
        shift(void, 1)
        if void == cluster:
            break
    ranks = np.zeros(total, dtype=np.int64)
    relaxed, relaxed_energy = pattern.copy(), energy.copy()
    ones = int(pattern.sum())
    for rank in range(ones - 1, -1, -1):            # phase 1: peel clusters off
        cluster = int(np.argmax(np.where(pattern, energy.ravel(), -1)))
        ranks[cluster] = rank
        shift(cluster, -1)
    pattern[:], energy[:] = relaxed, relaxed_energy
    for rank in range(ones, total):                 # phase 2: fill the largest voids
        void = int(np.argmin(np.where(pattern, big, energy.ravel())))
        ranks[void] = rank
        shift(void, 1)
    return ranks.reshape(size, size)


def _threshold(method, px, py, seed):
    px, py = np.asarray(px), np.asarray(py)
    if method in ("bayer2", "bayer4", "bayer8"):
        matrix = _bayer(int(method[5:]))
        n = matrix.shape[0]
        return (matrix[py % n, px % n] + 0.5) / (n * n)
    if method == "blue":
        ranks = blue_noise_ranks()
        return (ranks[py % ranks.shape[0], px % ranks.shape[1]] + 0.5) / ranks.size
    if method == "white":
        return unit_hash(px, py, 0, seed)
    if method == "ign":
        inner = (0.06711056 * px + 0.00583715 * py) % 1.0
        return (52.9829189 * inner) % 1.0
    if method == "cluster":
        return (_CLUSTER[py % 4, px % 4] + 0.5) / 16.0
    if method == "lines":
        return ((py % 4) + 0.5) / 4.0
    return (((px + py) % 4) + 0.5) / 4.0              # diagonal


def _diffuse(values, count, weights):
    """Error diffusion of a 2D value image onto ``count`` evenly spaced levels; returns level indices."""
    height, width = values.shape
    work = np.clip(values, 0.0, 1.0).astype(np.float64).copy()
    levels = np.zeros((height, width), dtype=np.int64)
    last = count - 1
    for y in range(height):
        for x in range(width):
            wanted = work[y, x]
            level = min(last, max(0, int(round(wanted * last))))
            levels[y, x] = level
            error = wanted - level / last
            for dx, dy, weight in weights:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and ny < height:
                    work[ny, nx] += error * weight
    return levels
