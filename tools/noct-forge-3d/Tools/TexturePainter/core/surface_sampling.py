"""Deterministic UV-to-surface sampling for declarative texture painting.

This module reads finalized geometry and UVs.  It never changes geometry, UV
coordinates, packing metadata, or texture registration.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import numpy as np

from lib.geometry_validation import rotate, world_point
from lib.model_builder import ModelBuilder


EPSILON = 1e-9
COVERAGE_EPSILON = 1e-9


def _sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _unit(value, label):
    length = math.sqrt(sum(component * component for component in value))
    if length <= EPSILON:
        raise ValueError(f"{label}: degenerate surface normal")
    return tuple(component / length for component in value)


def _barycentric(point, a, b, c, clamp=False):
    """Weights of point in abc; clamp=True snaps round-off overshoot for points
    known to lie inside (e.g. centroids of clipped sliver triangles)."""
    denominator = ((b[1] - c[1]) * (a[0] - c[0]) +
                   (c[0] - b[0]) * (a[1] - c[1]))
    if abs(denominator) <= EPSILON:
        return None
    first = ((b[1] - c[1]) * (point[0] - c[0]) +
             (c[0] - b[0]) * (point[1] - c[1])) / denominator
    second = ((c[1] - a[1]) * (point[0] - c[0]) +
              (a[0] - c[0]) * (point[1] - c[1])) / denominator
    third = 1.0 - first - second
    if min(first, second, third) < -EPSILON:
        if not clamp:
            return None
        weights = tuple(max(0.0, value) for value in (first, second, third))
        total = sum(weights)
        return tuple(value / total for value in weights)
    return first, second, third


def _interpolate(weights, points):
    return tuple(sum(weight * point[index] for weight, point in zip(weights, points))
                 for index in range(3))


def _triangulation_indices(points):
    """Temporary decomposition for sampling; quads use Blockbench A-C."""
    from lib.polygon_decomposition import temporary_triangle_indices
    return temporary_triangle_indices(tuple((point[0],point[1],0.0) for point in points))


def _clip_polygon_rect(polygon, left, top, right, bottom):
    clipped = list(polygon)
    for axis, boundary, keep_greater in ((0,left,True),(0,right,False),
                                          (1,top,True),(1,bottom,False)):
        output = []
        for start, end in zip(clipped, clipped[1:] + clipped[:1]):
            start_inside = start[axis] >= boundary-EPSILON if keep_greater else start[axis] <= boundary+EPSILON
            end_inside = end[axis] >= boundary-EPSILON if keep_greater else end[axis] <= boundary+EPSILON
            if start_inside != end_inside:
                amount = (boundary-start[axis])/(end[axis]-start[axis])
                output.append(tuple(start[i]+amount*(end[i]-start[i]) for i in range(2)))
            if end_inside:
                output.append(end)
        clipped = output
        if not clipped:
            break
    return tuple(clipped)


def _polygon_area_centroid(polygon):
    cross_sum = 0.0
    cx = cy = 0.0
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        cross = start[0]*end[1]-end[0]*start[1]
        cross_sum += cross
        cx += (start[0]+end[0])*cross
        cy += (start[1]+end[1])*cross
    if abs(cross_sum) <= EPSILON:
        return 0.0, None
    return abs(cross_sum)/2.0, (cx/(3*cross_sum), cy/(3*cross_sum))


def _rotate_vector(vector, angles):
    return _sub(rotate(vector, (0, 0, 0), angles), (0, 0, 0))


def _model_vector(builder, element, vector):
    vector = _rotate_vector(vector, element.rotation)
    if getattr(element, "parent_kind", "group") == "armature":
        return vector
    parent = element.parent
    seen = set()
    while parent is not None:
        if parent in seen:
            raise ValueError("Group hierarchy cycle during surface sampling")
        seen.add(parent)
        if parent not in builder._groups:
            break
        bone = builder._groups[parent]
        vector = _rotate_vector(vector, bone.rotation)
        parent = bone.parent
    return vector


def _canvas_to_atlas(info, x, y):
    """Map an upright canvas pixel center through the compose-atlas transform."""
    sx, sy = x + 0.5, y + 0.5
    width, height = info["w"], info["h"]
    rotation = info["rotation"]
    if rotation == 0:
        ax, ay = sx, sy
    elif rotation == 90:
        ax, ay = width - sy, sx
    elif rotation == 180:
        ax, ay = width - sx, height - sy
    else:
        ax, ay = sy, height - sx
    if info["flip_x"]:
        ax = width - ax
    if info["flip_y"]:
        ay = height - ay
    return info["x"] + ax, info["y"] + ay


def _cube_point(element, face_name, u, v):
    low, high = element.from_, element.to_
    if high is None:
        raise ValueError(f"{element.name}: cube is missing bounds")
    inflate = element.inflate
    x0, y0, z0 = (value - inflate for value in low)
    x1, y1, z1 = (value + inflate for value in high)
    faces = {
        "north": ((x0 + u * (x1 - x0), y1 - v * (y1 - y0), z0), (0, 0, -1)),
        "south": ((x1 - u * (x1 - x0), y1 - v * (y1 - y0), z1), (0, 0, 1)),
        "east": ((x1, y1 - v * (y1 - y0), z0 + u * (z1 - z0)), (1, 0, 0)),
        "west": ((x0, y1 - v * (y1 - y0), z1 - u * (z1 - z0)), (-1, 0, 0)),
        "up": ((x0 + u * (x1 - x0), y1, z0 + v * (z1 - z0)), (0, 1, 0)),
        "down": ((x0 + u * (x1 - x0), y0, z1 - v * (z1 - z0)), (0, -1, 0)),
    }
    if face_name not in faces:
        raise ValueError(f"{element.name}.{face_name}: unsupported cube face")
    return faces[face_name]


@dataclass(frozen=True)
class SurfaceSample:
    pixel: tuple[int, int]
    face_uv: tuple[float, float]
    element_position: tuple[float, float, float]
    model_position: tuple[float, float, float]
    element_normal: tuple[float, float, float]
    model_normal: tuple[float, float, float]
    normalized_position: tuple[float, float, float]
    element_name: str
    face_name: str
    tags: tuple[str, ...]
    coverage_uv_polygon: tuple = ()
    coverage_model_points: tuple = ()
    coverage_model_polygons: tuple = ()
    coverage_fraction: float = 1.0


_COVERAGE_FIELDS = ("coverage_uv_polygon", "coverage_model_points", "coverage_model_polygons")


def _lazy_coverage_property(name):
    def get(self):
        cache = self.__dict__.get("_coverage")
        if cache is None:
            cache = self.__dict__["_coverage_source"]()
            self.__dict__["_coverage"] = cache
        return cache[name]

    def ignore_default(self, value):
        # The dataclass __init__ assigns field defaults; coverage is resolved on demand.
        pass

    return property(get, ignore_default)


class _LazyCoverageSample(SurfaceSample):
    """A SurfaceSample whose coverage geometry is computed on first access.

    Coverage is only read by geometry fields (creases, contacts) and rare
    callbacks; computing it eagerly for every texel dominated painting time.
    """
    coverage_uv_polygon = _lazy_coverage_property("coverage_uv_polygon")
    coverage_model_points = _lazy_coverage_property("coverage_model_points")
    coverage_model_polygons = _lazy_coverage_property("coverage_model_polygons")


# ---------------------------------------------------------------- vectorized geometry
# These mirror the scalar helpers above operation by operation, so the arrays hold the
# same floating point values the per-texel code produces.

def _rotate_rows(points, pivot, angles):
    x = points[:, 0] - pivot[0]
    y = points[:, 1] - pivot[1]
    z = points[:, 2] - pivot[2]
    rx, ry, rz = map(math.radians, angles)
    y, z = math.cos(rx)*y-math.sin(rx)*z, math.sin(rx)*y+math.cos(rx)*z
    x, z = math.cos(ry)*x+math.sin(ry)*z, -math.sin(ry)*x+math.cos(ry)*z
    x, y = math.cos(rz)*x-math.sin(rz)*y, math.sin(rz)*x+math.cos(rz)*y
    return np.stack((x+pivot[0], y+pivot[1], z+pivot[2]), axis=1)


def _world_rows(builder, element, points):
    """Vectorized ``world_point`` for an (N, 3) array."""
    points = _rotate_rows(points, element.origin, element.rotation)
    if getattr(element, 'parent_kind', 'group') == 'armature':
        origin = builder._armatures[element.parent].origin
        return np.stack([points[:, i] + origin[i] for i in range(3)], axis=1)
    parent = element.parent
    seen = set()
    while parent is not None:
        if parent in seen:
            raise ValueError('Group hierarchy cycle during geometry validation')
        seen.add(parent)
        bone = builder._groups[parent]
        points = _rotate_rows(points, bone.pivot, bone.rotation)
        parent = bone.parent
    return points


def _canvas_to_atlas_rows(info, xs, ys):
    sx, sy = xs + 0.5, ys + 0.5
    width, height = info["w"], info["h"]
    rotation = info["rotation"]
    if rotation == 0:
        ax, ay = sx, sy
    elif rotation == 90:
        ax, ay = width - sy, sx
    elif rotation == 180:
        ax, ay = width - sx, height - sy
    else:
        ax, ay = sy, height - sx
    if info["flip_x"]:
        ax = width - ax
    if info["flip_y"]:
        ay = height - ay
    return np.stack((info["x"] + ax, info["y"] + ay), axis=1)


def _cube_rows(element, face_name, u, v):
    """Vectorized ``_cube_point`` positions."""
    low, high = element.from_, element.to_
    if high is None:
        raise ValueError(f"{element.name}: cube is missing bounds")
    inflate = element.inflate
    x0, y0, z0 = (value - inflate for value in low)
    x1, y1, z1 = (value + inflate for value in high)
    def full(value):
        return np.full(u.shape, value, dtype=float)
    columns = {
        "north": (x0 + u * (x1 - x0), y1 - v * (y1 - y0), full(z0)),
        "south": (x1 - u * (x1 - x0), y1 - v * (y1 - y0), full(z1)),
        "east": (full(x1), y1 - v * (y1 - y0), z0 + u * (z1 - z0)),
        "west": (full(x0), y1 - v * (y1 - y0), z1 - u * (z1 - z0)),
        "up": (x0 + u * (x1 - x0), full(y1), z0 + v * (z1 - z0)),
        "down": (x0 + u * (x1 - x0), full(y0), z1 - v * (z1 - z0)),
    }
    if face_name not in columns:
        raise ValueError(f"{element.name}.{face_name}: unsupported cube face")
    return np.stack(columns[face_name], axis=1)


def _barycentric_rows(points, a, b, c):
    """Vectorized ``_barycentric`` (no clamping); None when the triangle is degenerate."""
    denominator = ((b[1] - c[1]) * (a[0] - c[0]) +
                   (c[0] - b[0]) * (a[1] - c[1]))
    if abs(denominator) <= EPSILON:
        return None
    px, py = points[:, 0], points[:, 1]
    first = ((b[1] - c[1]) * (px - c[0]) +
             (c[0] - b[0]) * (py - c[1])) / denominator
    second = ((c[1] - a[1]) * (px - c[0]) +
              (a[0] - c[0]) * (py - c[1])) / denominator
    third = 1.0 - first - second
    return first, second, third



def _clip_rows(polygon, left, top, right, bottom, epsilon=EPSILON):
    """Vectorized ``_clip_polygon_rect`` of one polygon against N texel squares.

    Returns (xs, ys, counts): vertex coordinates (N, capacity) and vertex counts,
    in the order the scalar Sutherland-Hodgman produces them. A clip can at most
    double the vertices of a non-convex polygon, so capacity grows per half-plane.
    """
    count = len(left)
    xs = np.zeros((count, len(polygon)))
    ys = np.zeros((count, len(polygon)))
    for index, point in enumerate(polygon):
        xs[:, index], ys[:, index] = point[0], point[1]
    counts = np.full(count, len(polygon), dtype=np.int64)
    rows = np.arange(count)
    for axis, boundary, keep_greater in ((0, left, True), (0, right, False), (1, top, True), (1, bottom, False)):
        out_x = np.zeros((count, 2 * xs.shape[1]))
        out_y = np.zeros((count, 2 * xs.shape[1]))
        out_counts = np.zeros(count, dtype=np.int64)
        coord = xs if axis == 0 else ys
        for k in range(xs.shape[1]):
            valid = k < counts
            if not valid.any():
                break
            following = np.where(valid, (k + 1) % np.maximum(counts, 1), 0)
            start = (xs[:, k], ys[:, k])
            end = (xs[rows, following], ys[rows, following])
            start_axis, end_axis = coord[:, k], coord[rows, following]
            if keep_greater:
                start_inside = start_axis >= boundary - epsilon
                end_inside = end_axis >= boundary - epsilon
            else:
                start_inside = start_axis <= boundary + epsilon
                end_inside = end_axis <= boundary + epsilon
            crossing = valid & (start_inside != end_inside)
            if crossing.any():
                # Rows that do not cross may divide by zero; only crossing rows are kept.
                with np.errstate(divide="ignore", invalid="ignore"):
                    amount = (boundary - start_axis) / (end_axis - start_axis)
                    cut_x = start[0] + amount * (end[0] - start[0])
                    cut_y = start[1] + amount * (end[1] - start[1])
                position = out_counts[crossing]
                out_x[rows[crossing], position] = cut_x[crossing]
                out_y[rows[crossing], position] = cut_y[crossing]
                out_counts[crossing] += 1
            keep = valid & end_inside
            position = out_counts[keep]
            out_x[rows[keep], position] = end[0][keep]
            out_y[rows[keep], position] = end[1][keep]
            out_counts[keep] += 1
        xs, ys, counts = out_x, out_y, out_counts
    return xs, ys, counts


def _area_centroid_rows(xs, ys, counts):
    """Vectorized ``_polygon_area_centroid``: (area, cx, cy, valid)."""
    count = len(counts)
    rows = np.arange(count)
    cross_sum = np.zeros(count)
    cx = np.zeros(count)
    cy = np.zeros(count)
    for k in range(xs.shape[1]):
        valid = k < counts
        if not valid.any():
            break
        following = np.where(valid, (k + 1) % np.maximum(counts, 1), 0)
        sx, sy = xs[:, k], ys[:, k]
        ex, ey = xs[rows, following], ys[rows, following]
        cross = sx * ey - ex * sy
        cross_sum = np.where(valid, cross_sum + cross, cross_sum)
        cx = np.where(valid, cx + (sx + ex) * cross, cx)
        cy = np.where(valid, cy + (sy + ey) * cross, cy)
    valid = (counts >= 3) & (np.abs(cross_sum) > EPSILON)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (np.where(valid, np.abs(cross_sum) / 2.0, 0.0), cx / (3 * cross_sum),
                cy / (3 * cross_sum), valid)


def _conservative_rows(face_uv, tri_uv, tri_points):
    """Vectorized conservative branch of ``_mesh_texel`` for N texels.

    Returns (face_uv, point, normal_index, fraction, ok); ``ok`` is False where the
    scalar code would raise, so callers can defer to it for the exact error.
    """
    count = len(face_uv)
    left, top = face_uv[:, 0] - .5, face_uv[:, 1] - .5
    right, bottom = face_uv[:, 0] + .5, face_uv[:, 1] + .5
    areas, centroids, centers, present = [], [], [], []
    ok = np.ones(count, dtype=bool)
    for (a, b, c), points in zip(tri_uv, tri_points):
        xs, ys, counts = _clip_rows((a, b, c), left, top, right, bottom)
        area, cx, cy, valid = _area_centroid_rows(xs, ys, counts)
        piece = valid & (area > COVERAGE_EPSILON)
        centroid = np.stack((np.where(piece, cx, 0.0), np.where(piece, cy, 0.0)), axis=1)
        weights = _barycentric_rows(centroid, a, b, c)
        if weights is None:
            ok &= ~piece
            weights = (np.zeros(count),) * 3
        else:
            low = np.minimum(np.minimum(weights[0], weights[1]), weights[2]) < -EPSILON
            if low.any():
                clamped = [np.maximum(0.0, weight) for weight in weights]
                total = python_sum(clamped)
                weights = tuple(np.where(low, weight / np.where(total == 0, 1.0, total), original)
                                for weight, original in zip(clamped, weights))
        areas.append(np.where(piece, area, 0.0))
        centroids.append(centroid)
        centers.append(_interpolate_rows(weights, points))
        present.append(piece)
    total = python_sum(areas)
    ok &= total > COVERAGE_EPSILON
    safe = np.where(ok, total, 1.0)
    uv = np.stack([python_sum([areas[k] * centroids[k][:, i] for k in range(len(areas))]) / safe
                   for i in range(2)], axis=1)
    point = np.stack([python_sum([areas[k] * centers[k][:, i] for k in range(len(areas))]) / safe
                      for i in range(3)], axis=1)
    normal_index = np.zeros(count, dtype=np.int64)
    best = np.where(present[0], areas[0], -np.inf)
    for k in range(1, len(areas)):
        better = present[k] & (areas[k] > best)
        normal_index[better] = k
        best = np.where(better, areas[k], best)
    return uv, point, normal_index, np.minimum(1.0, total), ok


def python_sum(terms):
    """Elementwise equivalent of Python's ``sum(terms)`` over float arrays.

    Since Python 3.12 ``sum`` of floats is Neumaier-compensated: the first term is
    added to the integer start 0, the rest accumulate a compensation that is added
    at the end. Mirroring it keeps vectorized results bit-identical to the scalar code.
    """
    terms = [np.asarray(term, dtype=float) for term in terms]
    total = 0.0 + terms[0]
    compensation = np.zeros(np.broadcast(*terms).shape)
    for term in terms[1:]:
        step = total + term
        compensation = compensation + np.where(np.abs(total) >= np.abs(term),
                                               (total - step) + term, (term - step) + total)
        total = step
    return np.where((compensation != 0) & np.isfinite(compensation), total + compensation, total)


def _interpolate_rows(weights, points):
    return np.stack([python_sum([weights[k] * points[k][i] for k in range(3)]) for i in range(3)], axis=1)


class FaceSamples(Sequence):
    """The samples of one face (or a subset), as arrays in canvas row-major order.

    Bulk painting reads the arrays; iterating or indexing yields ``SurfaceSample``
    objects built on demand with the same values, for callbacks and predicates.
    """

    def __init__(self, element_name, face_name, tags, fields, coverage):
        self.element_name, self.face_name, self.tags = element_name, face_name, tags
        self.fields = fields
        self._coverage = coverage
        self._objects = None

    @property
    def x(self):
        return self.fields["x"]

    @property
    def y(self):
        return self.fields["y"]

    def __getattr__(self, name):
        # Field arrays read as attributes: rows.model_position, rows.normalized_position, ...
        fields = self.__dict__.get("fields")
        if fields is not None and name in fields:
            return fields[name]
        raise AttributeError(f"FaceSamples has no field {name!r}")

    def __len__(self):
        return len(self.fields["x"])

    def __getitem__(self, index):
        return self.objects()[index]

    def __iter__(self):
        return iter(self.objects())

    def subset(self, keep):
        """A new FaceSamples with the samples where boolean array ``keep`` is true."""
        part = FaceSamples(self.element_name, self.face_name, self.tags,
                           {key: value[keep] for key, value in self.fields.items()}, self._coverage)
        if self._objects is not None:
            part._objects = tuple(obj for obj, flag in zip(self._objects, keep.tolist()) if flag)
        return part

    def objects(self):
        if self._objects is None:
            f = self.fields
            xs, ys = f["x"].tolist(), f["y"].tolist()
            columns = [f[key].tolist() for key in ("face_uv", "element_position", "model_position",
                                                    "element_normal", "model_normal", "normalized_position")]
            fractions = f["coverage_fraction"].tolist()
            coverage = self._coverage
            objects = []
            new = object.__new__
            for i, (x, y) in enumerate(zip(xs, ys)):
                # Filling __dict__ directly skips the frozen dataclass __init__, which costs
                # one object.__setattr__ per field; the instance is otherwise identical.
                sample = new(_LazyCoverageSample)
                sample.__dict__.update(
                    pixel=(x, y), face_uv=tuple(columns[0][i]), element_position=tuple(columns[1][i]),
                    model_position=tuple(columns[2][i]), element_normal=tuple(columns[3][i]),
                    model_normal=tuple(columns[4][i]), normalized_position=tuple(columns[5][i]),
                    element_name=self.element_name, face_name=self.face_name, tags=self.tags,
                    coverage_fraction=fractions[i], _coverage_source=(lambda x=x, y=y: coverage(x, y)))
                objects.append(sample)
            self._objects = tuple(objects)
        return self._objects

    @classmethod
    def from_samples(cls, samples):
        """Arrays for an explicit tuple of SurfaceSample objects (one face)."""
        samples = tuple(samples)
        first = samples[0] if samples else None
        def column(name, width):
            return np.array([getattr(s, name) for s in samples], dtype=float).reshape(-1, width)
        fields = {
            "x": np.array([s.pixel[0] for s in samples], dtype=np.int64),
            "y": np.array([s.pixel[1] for s in samples], dtype=np.int64),
            "face_uv": column("face_uv", 2),
            "element_position": column("element_position", 3),
            "model_position": column("model_position", 3),
            "element_normal": column("element_normal", 3),
            "model_normal": column("model_normal", 3),
            "normalized_position": column("normalized_position", 3),
            "coverage_fraction": np.array([s.coverage_fraction for s in samples], dtype=float),
        }
        by_pixel = {s.pixel: s for s in samples}
        part = cls(first.element_name if first else "", first.face_name if first else "",
                   first.tags if first else (), fields,
                   lambda x, y: {name: getattr(by_pixel[x, y], name) for name in _COVERAGE_FIELDS})
        part._objects = samples
        return part


class SurfaceSampler:
    """Build immutable samples from the painter's validated model snapshot."""

    def __init__(self, document):
        self.document = document
        self.builder = ModelBuilder.from_bbmodel_data(document)
        self.elements = {element.name: element for element in self.builder._elements}
        self.bounds = {name: self._element_bounds(element)
                       for name, element in self.elements.items()}
        self._cache = {}
        self._affine = {}       # (element, face) -> per-triangle (uv a, b, c, element points) of mesh faces

    @staticmethod
    def _element_points(element):
        if element.kind == "cube":
            if element.to_ is None:
                return []
            inflate = element.inflate
            low = tuple(value - inflate for value in element.from_)
            high = tuple(value + inflate for value in element.to_)
            return [
                (x, y, z)
                for x in (low[0], high[0])
                for y in (low[1], high[1])
                for z in (low[2], high[2])
            ]
        if element.vertices:
            return [tuple(element.origin[index] + vertex[index] for index in range(3))
                    for vertex in element.vertices.values()]
        return []

    def _element_bounds(self, element):
        points = self._element_points(element)
        if not points:
            raise ValueError(f"{element.name}: cannot derive element bounds")
        low = tuple(min(point[index] for point in points) for index in range(3))
        high = tuple(max(point[index] for point in points) for index in range(3))
        return low, high

    def tags_for_element(self, name, *, include_ancestors=False):
        element = self.elements[name]
        tags = list(element.tags)
        if include_ancestors:
            parent = element.parent
            seen = set()
            while parent is not None:
                if parent in seen:
                    raise ValueError("Group hierarchy cycle during tag selection")
                seen.add(parent)
                if parent in self.builder._groups:
                    bone = self.builder._groups[parent]
                    tags.extend(bone.tags)
                    parent = bone.parent
                elif parent in self.builder._armatures:
                    armature = self.builder._armatures[parent]
                    tags.extend(armature.tags)
                    parent = armature.parent
                else:
                    break
        return tuple(dict.fromkeys(tags))

    def samples(self, element_name, face_name, face_painter):
        """FaceSamples of one face, built once per painter."""
        key = (element_name, face_name)
        if key not in self._cache:
            self._cache[key] = self._build_face(self.elements[element_name], face_name, face_painter)
        return self._cache[key]

    def _unit_normals(self, element, face_name, normal):
        label = f"{element.name}.{face_name}"
        element_normal = _unit(normal, label)
        return element_normal, _unit(_model_vector(self.builder, element, element_normal), label)

    def _build_face(self, element, face_name, face_painter):
        info = face_painter.uv_info
        canvas = face_painter.canvas
        width, height = canvas.width, canvas.height
        ys, xs = np.divmod(np.arange(width * height, dtype=np.int64), width)
        mask = getattr(canvas, "mask", None)
        if mask is not None:
            covered = np.asarray(mask, dtype=np.uint8).reshape(-1) > 0
            if element.kind == "cube":
                covered |= np.asarray(canvas.image.getchannel("A"), dtype=np.uint8).reshape(-1) > 0
            xs, ys = xs[covered], ys[covered]
        if element.kind == "cube":
            return self._cube_face(element, face_name, info, width, height, xs, ys)
        return self._mesh_face(element, face_name, info, xs, ys)

    def _finish(self, element, face_name, xs, ys, face_uv, points, element_normals, model_normals,
                fractions, coverage, frame=None):
        low, high = self.bounds[element.name]
        normalized = np.stack([
            np.zeros(len(xs)) if abs(high[i] - low[i]) <= EPSILON else (points[:, i] - low[i]) / (high[i] - low[i])
            for i in range(3)], axis=1) if len(xs) else np.zeros((0, 3))
        model = _world_rows(self.builder, element, points) if len(xs) else np.zeros((0, 3))
        fields = {
            "x": xs, "y": ys, "face_uv": face_uv, "element_position": points, "model_position": model,
            "element_normal": element_normals, "model_normal": model_normals,
            "normalized_position": normalized, "coverage_fraction": fractions,
        }
        fields.update(frame or {})
        return FaceSamples(element.name, face_name, tuple(element.tags), fields, coverage)

    @staticmethod
    def _texel_frame(info, xs, ys, at_atlas):
        """Per row, the element position at the texel centre and its change per canvas texel step along x and y
        (``at_atlas(uv) -> element positions``, affine on the row's piece of the face), with the same for the
        atlas UV: what ``shifted`` needs to place subsamples anywhere inside the texel square."""
        xs, ys = xs.astype(float), ys.astype(float)
        u0 = _canvas_to_atlas_rows(info, xs, ys)
        ux = _canvas_to_atlas_rows(info, xs + 1.0, ys) - u0
        uy = _canvas_to_atlas_rows(info, xs, ys + 1.0) - u0
        e0 = at_atlas(u0)
        return {"_u0": u0, "_ux": ux, "_uy": uy, "_e0": e0,
                "_ex": at_atlas(u0 + ux) - e0, "_ey": at_atlas(u0 + uy) - e0}

    def shifted(self, rows, offset):
        """FaceSamples of ``rows`` moved by ``offset`` = (dx, dy) canvas texels from each texel centre (positions,
        UVs and normalized positions; normals and pixels unchanged), or None when the rows carry no texel frame."""
        f = rows.fields
        if "_e0" not in f:
            return None
        dx, dy = offset
        element = self.elements[rows.element_name]
        uv = f["_u0"] + f["_ux"] * dx + f["_uy"] * dy
        points = f["_e0"] + f["_ex"] * dx + f["_ey"] * dy
        affine = self._affine.get((rows.element_name, rows.face_name))
        if affine is not None and len(points):
            # A subsample on the other side of a quad's diagonal follows that triangle (a non-planar quad bends
            # there): the position depends on the point, not on which triangle holds the texel centre.
            piece = np.full(len(points), -1, dtype=np.int64)
            for index, entry in enumerate(affine):
                if entry is None:
                    continue
                a, b, c, _corner = entry
                weights = _barycentric_rows(uv, a, b, c)
                inside = np.minimum(np.minimum(weights[0], weights[1]), weights[2]) >= -EPSILON
                piece[inside & (piece < 0)] = index
            piece = np.where(piece < 0, f["_piece"], piece)        # outside the face: its own triangle, extended
            points = points.copy()
            for index, entry in enumerate(affine):
                rows_on = piece == index
                if entry is not None and rows_on.any():
                    a, b, c, corner = entry
                    points[rows_on] = _interpolate_rows(_barycentric_rows(uv[rows_on], a, b, c), corner)
        low, high = self.bounds[element.name]
        normalized = np.stack([
            np.zeros(len(points)) if abs(high[i] - low[i]) <= EPSILON else (points[:, i] - low[i]) / (high[i] - low[i])
            for i in range(3)], axis=1) if len(points) else np.zeros((0, 3))
        fields = dict(f)
        fields.update(face_uv=f["_u0"] + f["_ux"] * dx + f["_uy"] * dy, element_position=points,
                      model_position=_world_rows(self.builder, element, points) if len(points) else np.zeros((0, 3)),
                      normalized_position=normalized)
        return FaceSamples(rows.element_name, rows.face_name, rows.tags, fields, rows._coverage)

    def _cube_face(self, element, face_name, info, width, height, xs, ys):
        u = (xs + 0.5) / width
        v = (ys + 0.5) / height
        points = _cube_rows(element, face_name, u, v)
        element_normal, model_normal = self._unit_normals(
            element, face_name, _cube_point(element, face_name, 0.5, 0.5)[1])
        count = len(xs)
        u0 = _canvas_to_atlas_rows(info, xs.astype(float), ys.astype(float))
        frame = {"_u0": u0, "_ux": _canvas_to_atlas_rows(info, xs + 1.0, ys.astype(float)) - u0,
                 "_uy": _canvas_to_atlas_rows(info, xs.astype(float), ys + 1.0) - u0, "_e0": points,
                 "_ex": _cube_rows(element, face_name, u + 1.0 / width, v) - points,
                 "_ey": _cube_rows(element, face_name, u, v + 1.0 / height) - points}

        def coverage(x, y):
            footprint = tuple(_cube_point(element, face_name, px/width, py/height)[0]
                              for px, py in ((x, y), (x+1, y), (x+1, y+1), (x, y+1)))
            world = tuple(world_point(self.builder, element, value) for value in footprint)
            return {"coverage_uv_polygon": (), "coverage_model_points": world,
                    "coverage_model_polygons": (world,)}

        return self._finish(element, face_name, xs, ys, _canvas_to_atlas_rows(info, xs, ys), points,
                            np.tile(element_normal, (count, 1)), np.tile(model_normal, (count, 1)),
                            np.ones(count), coverage, frame)

    def _mesh_geometry(self, element, face_name):
        raw_face = element.faces.get(face_name)
        if raw_face is None:
            raise ValueError(f"{element.name}.{face_name}: missing mesh face")
        order = raw_face.get("vertices", [])
        raw_uv = raw_face.get("uv")
        if len(order) not in (3, 4) or not isinstance(raw_uv, dict):
            raise ValueError(
                f"{element.name}.{face_name}: spatial painting requires canonical triangle or quad UVs")
        uv_points = [tuple(raw_uv[key]) for key in order]
        points = [tuple(element.origin[index] + element.vertices[key][index]
                        for index in range(3)) for key in order]
        return uv_points, points, _triangulation_indices(uv_points)

    def _mesh_face(self, element, face_name, info, xs, ys):
        uv_points, points, triangles = self._mesh_geometry(element, face_name)
        count = len(xs)
        face_uv = _canvas_to_atlas_rows(info, xs, ys)
        positions = np.zeros((count, 3))
        triangle_of = np.full(count, -1, dtype=np.int64)
        conservative = bool(info.get("conservative"))
        tri_uv = [tuple(uv_points[index] for index in triangle) for triangle in triangles]
        tri_points = [[points[index] for index in triangle] for triangle in triangles]

        if not conservative:
            for index, (a, b, c) in enumerate(tri_uv):
                weights = _barycentric_rows(face_uv, a, b, c)
                if weights is None:
                    continue
                inside = (np.minimum(np.minimum(weights[0], weights[1]), weights[2]) >= -EPSILON) & (triangle_of < 0)
                triangle_of[inside] = index
            if (triangle_of < 0).any():
                first = int(np.argmax(triangle_of < 0))
                raise ValueError(f"{element.name}.{face_name}: cannot sample covered UV pixel "
                                 f"{(int(xs[first]), int(ys[first]))}")

        for index, (a, b, c) in enumerate(tri_uv):
            rows = triangle_of == index
            if rows.any():
                weights = _barycentric_rows(face_uv[rows], a, b, c)
                positions[rows] = _interpolate_rows(weights, tri_points[index])

        normals = {}

        def unit_normals(normal):
            if normal not in normals:
                normals[normal] = self._unit_normals(element, face_name, normal)
            return normals[normal]

        element_normals = np.zeros((count, 3))
        model_normals = np.zeros((count, 3))
        for index, corner in enumerate(tri_points):
            rows = triangle_of == index
            if rows.any():
                normal = _cross(_sub(corner[1], corner[0]), _sub(corner[2], corner[0]))
                element_normals[rows], model_normals[rows] = unit_normals(normal)
        fractions = np.ones(count)

        texel = {}

        def exact(x, y):
            if (x, y) not in texel:
                texel[x, y] = _mesh_texel(element, face_name, info, x, y, uv_points, points, triangles)
            return texel[x, y]

        # Conservative faces clip every triangle to each texel square (vectorized); the
        # scalar version runs only where it raises, to report the same error.
        boundary = np.nonzero(triangle_of < 0)[0] if conservative else np.zeros(0, dtype=np.int64)
        if len(boundary):
            uv, point, normal_index, fraction, ok = _conservative_rows(face_uv[boundary], tri_uv, tri_points)
            for k, row in enumerate(boundary.tolist()):
                if not ok[k]:
                    # zero clipped area: the scalar sample (face centroid), or its error
                    texel_uv, texel_point, texel_normal, _, _, texel_fraction, _ = exact(int(xs[row]), int(ys[row]))
                    uv[k], point[k], fraction[k] = texel_uv, texel_point, texel_fraction
                    normal_index[k] = next(i for i, corner in enumerate(tri_points) if _cross(
                        _sub(corner[1], corner[0]), _sub(corner[2], corner[0])) == texel_normal)
            face_uv[boundary] = uv
            positions[boundary] = point
            fractions[boundary] = fraction
            for index, corner in enumerate(tri_points):
                rows = boundary[normal_index == index]
                if len(rows):
                    normal = _cross(_sub(corner[1], corner[0]), _sub(corner[2], corner[0]))
                    element_normals[rows], model_normals[rows] = unit_normals(normal)

        def coverage(x, y):
            if not conservative:
                return {"coverage_uv_polygon": (), "coverage_model_points": None,
                        "coverage_model_polygons": ()}
            _, point, _, coverage_uv, coverage_points, _, coverage_polygons = exact(x, y)
            world = tuple(world_point(self.builder, element, value) for value in coverage_points)
            return {"coverage_uv_polygon": tuple(coverage_uv),
                    "coverage_model_points": world or (tuple(world_point(self.builder, element, point)),),
                    "coverage_model_polygons": tuple(tuple(world_point(self.builder, element, value)
                                                           for value in polygon) for polygon in coverage_polygons)}

        # Each row's subsamples follow the affine map of its own triangle (the one holding its centre, or the
        # largest clipped piece of a boundary texel), extended past the triangle edge where the texel overhangs it.
        piece = triangle_of.copy()
        if len(boundary):
            piece[boundary] = normal_index
        affine = []
        for index, (a, b, c) in enumerate(tri_uv):
            if _barycentric_rows(np.zeros((1, 2)), a, b, c) is None:
                affine.append(None)
                continue
            affine.append((a, b, c, tri_points[index]))

        def at_atlas(uv):
            out = np.zeros((len(uv), 3))
            for index, entry in enumerate(affine):
                rows = piece == index
                if entry is not None and rows.any():
                    a, b, c, corner = entry
                    out[rows] = _interpolate_rows(_barycentric_rows(uv[rows], a, b, c), corner)
            return out

        frame = self._texel_frame(info, xs, ys, at_atlas) if count else None
        if frame is not None:
            frame["_piece"] = piece
            self._affine[(element.name, face_name)] = affine
        result = self._finish(element, face_name, xs, ys, face_uv, positions, element_normals,
                              model_normals, fractions, None, frame)
        model_rows = {}

        def resolved_coverage(x, y):
            values = coverage(x, y)
            if values["coverage_model_points"] is None:
                if not model_rows:
                    model_rows.update(zip(zip(result.x.tolist(), result.y.tolist()),
                                          map(tuple, result.fields["model_position"].tolist())))
                values["coverage_model_points"] = (model_rows[x, y],)
            return values

        result._coverage = resolved_coverage
        return result



def _mesh_texel(element, face_name, info, x, y, uv_points, points, triangles):
    """Exact sample of one mesh texel: (face_uv, point, normal, coverage_uv,
    coverage_points, coverage_fraction, coverage_polygons).

    Conservative faces clip every triangle to the texel square and average the
    pieces by area; other faces take the first triangle containing the center.
    """
    face_uv = _canvas_to_atlas(info, x, y)
    if info.get("conservative"):
        pieces = []
        footprint_points = []
        footprint_polygons = []
        for triangle in triangles:
            triangle_uv = tuple(uv_points[index] for index in triangle)
            clipped = _clip_polygon_rect(
                triangle_uv, face_uv[0]-.5, face_uv[1]-.5,
                face_uv[0]+.5, face_uv[1]+.5)
            area, centroid = _polygon_area_centroid(clipped) if len(clipped) >= 3 else (0.0,None)
            if area <= COVERAGE_EPSILON or centroid is None:
                continue
            triangle_points = [points[index] for index in triangle]
            weights = _barycentric(centroid, *triangle_uv, clamp=True)
            if weights is None:
                raise ValueError(f"{element.name}.{face_name}: invalid clipped UV centroid")
            center_point = _interpolate(weights, triangle_points)
            normal = _cross(_sub(triangle_points[1], triangle_points[0]),
                            _sub(triangle_points[2], triangle_points[0]))
            mapped = []
            for uv_point in clipped:
                vertex_weights = _barycentric(uv_point, *triangle_uv)
                if vertex_weights is not None:
                    mapped.append(_interpolate(vertex_weights, triangle_points))
            pieces.append((area, centroid, center_point, normal, clipped))
            footprint_points.extend(mapped)
            footprint_polygons.append(tuple(mapped))
        total_area = sum(piece[0] for piece in pieces)
        if total_area <= COVERAGE_EPSILON:
            # The face owns a texel it only touches (at a point, or along an edge): no clipped area to
            # average, so sample the face at its centroid (on its largest triangle) instead.
            triangle = max(triangles, key=lambda t: abs(_polygon_area_centroid(
                [uv_points[i] for i in t])[0]))
            triangle_points = [points[index] for index in triangle]
            point = _interpolate((1 / 3, 1 / 3, 1 / 3), triangle_points)
            normal = _cross(_sub(triangle_points[1], triangle_points[0]),
                            _sub(triangle_points[2], triangle_points[0]))
            return face_uv, point, normal, (), (point,), 1.0, ()
        face_uv = tuple(sum(piece[0]*piece[1][i] for piece in pieces)/total_area
                        for i in range(2))
        point = tuple(sum(piece[0]*piece[2][i] for piece in pieces)/total_area
                      for i in range(3))
        normal = max(pieces, key=lambda piece: piece[0])[3]
        coverage_uv = tuple(uv for piece in pieces for uv in piece[4])
        return (face_uv, point, normal, coverage_uv, tuple(footprint_points),
                min(1.0, total_area), tuple(footprint_polygons))
    for triangle in triangles:
        weights = _barycentric(face_uv, *(uv_points[index] for index in triangle))
        if weights is not None:
            triangle_points = [points[index] for index in triangle]
            point = _interpolate(weights, triangle_points)
            normal = _cross(_sub(triangle_points[1], triangle_points[0]),
                            _sub(triangle_points[2], triangle_points[0]))
            return face_uv, point, normal, (), (), 1.0, ()
    raise ValueError(f"{element.name}.{face_name}: cannot sample covered UV pixel {(x, y)}")
