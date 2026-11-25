"""Connected UV charts: neighbouring mesh faces unfolded together on one continuous texel grid.

With one island per face (the ``faces`` layout) every face has its own grid orientation and phase, so the
pixel grid breaks at every edge and a pixel-art line cannot continue from one face to the next. The ``charts``
layout grows islands across shared edges instead:

* each face keeps its true shape and size (rigid unfolding: one texel is ``1 / uv_scale`` model units on
  every face, no stretching), and a shared edge is the very same UV segment in both faces, so the grid of one
  face continues into the next;
* a face joins a chart across an edge when the fold there is at most ``max_fold`` degrees, it fits the
  vertices the chart already placed (closing a loop) within ``tolerance`` texels, it does not overlap the
  chart and the chart stays within ``max_extent`` texels; otherwise it starts or joins another chart;
* each chart is rotated so the element's up (+Y) points up in the texture, then packed as one rectangle.

Charts are written as fractional per-vertex UVs plus ``model_as_code_chart`` on each face; the texture painter
gives every texel a chart touches to exactly one of its faces (``bbmodel_parser``).
"""
from __future__ import annotations

import heapq
import math

import numpy as np

DEFAULT_MAX_FOLD = 50.0      # degrees between neighbouring face normals inside one chart
DEFAULT_TOLERANCE = 1.0      # texels a closing vertex may miss its already placed position by (the face
                             # absorbs it as a slight shear; shared vertices stay exact, so the grid stays continuous)
DEFAULT_MAX_EXTENT = 512     # texels, longest chart side
DEFAULT_MAX_TWIST = 24.0     # degrees the up direction may turn across one chart


class _Face:
    __slots__ = ("name", "order", "points", "normal", "area", "local", "index")


def _newell(points):
    normal = np.zeros(3)
    for a, b in zip(points, np.roll(points, -1, axis=0)):
        normal += ((a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1]))
    length = float(np.linalg.norm(normal))
    return normal / length if length > 1e-12 else None, length / 2.0


def _faces(elem):
    vertices = elem.get("vertices", {})
    out = []
    for index, (name, face) in enumerate(elem.get("faces", {}).items()):
        if "texture" in face and face["texture"] is None:
            continue
        order = list(face.get("vertices", ()))
        if len(order) not in (3, 4) or len(set(order)) != len(order) or any(k not in vertices for k in order):
            raise ValueError(f"{elem.get('name')}/{name}: every mesh face needs three or four distinct vertices")
        points = np.array([vertices[k] for k in order], dtype=float)
        normal, area = _newell(points)
        if normal is None:
            raise ValueError(f"{elem.get('name')}/{name}: degenerate mesh face")
        u_axis = points[1] - points[0]
        u_axis -= normal * (u_axis @ normal)
        u_axis /= np.linalg.norm(u_axis)
        v_axis = np.cross(normal, u_axis)
        info = _Face()
        info.name, info.order, info.points, info.normal, info.area, info.index = name, order, points, normal, area, index
        info.local = np.stack([(points - points[0]) @ u_axis, (points - points[0]) @ v_axis], axis=1)
        out.append(info)
    return out


def _rigid_fit(source, target):
    """Rotation + translation (no reflection, no scale) taking source (n, 2) onto target (n, 2)."""
    sc, tc = source.mean(axis=0), target.mean(axis=0)
    s, t = source - sc, target - tc
    cov = s.T @ t
    angle = math.atan2(cov[0, 1] - cov[1, 0], cov[0, 0] + cov[1, 1])
    rot = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    return lambda p: (p - sc) @ rot.T + tc


def _triangles(polygon):
    return [polygon[[0, 1, 2]]] if len(polygon) == 3 else [polygon[[0, 1, 2]], polygon[[0, 2, 3]]]


def _overlap(tri_a, tri_b, margin):
    """True when two triangles overlap by more than ``margin`` (separating axis test; touching is fine)."""
    for tri in (tri_a, tri_b):
        for i in range(3):
            edge = tri[(i + 1) % 3] - tri[i]
            axis = np.array((-edge[1], edge[0]))
            length = np.linalg.norm(axis)
            if length < 1e-12:
                continue
            axis /= length
            pa, pb = tri_a @ axis, tri_b @ axis
            if pa.max() <= pb.min() + margin or pb.max() <= pa.min() + margin:
                return False
    return True


class _Chart:
    def __init__(self, cell):
        self.placed = {}          # vertex -> 2D position, model units
        self.faces = {}           # face name -> polygon (n, 2)
        self.tris = []            # (face name, triangle)
        self.grid = {}            # spatial hash cell -> triangle indices
        self.cell = cell
        self.lo = np.array([np.inf, np.inf])
        self.hi = np.array([-np.inf, -np.inf])

    def _cells(self, tri):
        lo, hi = np.floor(tri.min(axis=0) / self.cell), np.floor(tri.max(axis=0) / self.cell)
        return [(i, j) for i in range(int(lo[0]), int(hi[0]) + 1) for j in range(int(lo[1]), int(hi[1]) + 1)]

    def overlaps(self, polygon, margin):
        for tri in _triangles(polygon):
            seen = set()
            for cell in self._cells(tri):
                for k in self.grid.get(cell, ()):
                    if k not in seen:
                        seen.add(k)
                        if _overlap(tri, self.tris[k][1], margin):
                            return True
        return False

    def add(self, face, polygon):
        self.faces[face.name] = polygon
        for vertex, point in zip(face.order, polygon):
            self.placed.setdefault(vertex, point)
        for tri in _triangles(polygon):
            self.tris.append((face.name, tri))
            for cell in self._cells(tri):
                self.grid.setdefault(cell, []).append(len(self.tris) - 1)
        self.lo, self.hi = np.minimum(self.lo, polygon.min(axis=0)), np.maximum(self.hi, polygon.max(axis=0))


_UP = np.array((0.0, 1.0, 0.0))


def _up_angle(face, polygon, up=_UP):
    """Direction (degrees) of the element's +Y on this face in chart coordinates; None on (near) flat faces."""
    projected = up - face.normal * (up @ face.normal)
    if np.linalg.norm(projected) < 0.3:
        return None
    e3 = np.stack([face.points[1] - face.points[0], face.points[-1] - face.points[0]])
    e2 = np.stack([polygon[1] - polygon[0], polygon[-1] - polygon[0]])
    direction = np.linalg.lstsq(e3.T, projected, rcond=None)[0] @ e2
    return math.degrees(math.atan2(direction[1], direction[0]))


def _orient(chart, faces_by_name, up=_UP):
    """Rotate the chart so the element's +Y points to -v (up in the image)."""
    total = np.zeros(2)
    for name, polygon in chart.faces.items():
        face = faces_by_name[name]
        projected = up - face.normal * (up @ face.normal)
        strength = float(np.linalg.norm(projected))
        if strength < 1e-6:
            continue
        # The face's linear map 3D -> chart: solve from its first edge pair.
        e3 = np.stack([face.points[1] - face.points[0], face.points[-1] - face.points[0]])
        e2 = np.stack([polygon[1] - polygon[0], polygon[-1] - polygon[0]])
        coeffs = np.linalg.lstsq(e3.T, projected, rcond=None)[0]
        direction = coeffs @ e2
        length = np.linalg.norm(direction)
        if length > 1e-9:
            total += direction / length * strength * face.area
    if np.linalg.norm(total) < 1e-9:
        return
    angle = math.atan2(-1.0, 0.0) - math.atan2(total[1], total[0])
    rot = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    for name in chart.faces:
        chart.faces[name] = chart.faces[name] @ rot.T



def _mirror(elem, faces):
    """Vertex and face correspondences under x -> -x in element coordinates, or None when the element is not
    mirror-symmetric (every vertex and every face must have a mirror image)."""
    names = list(elem.get("vertices", {}))
    if not names:
        return None
    points = np.array([elem["vertices"][k] for k in names], dtype=float)
    size = float(np.abs(points).max()) or 1.0
    eps = 1e-5 * size
    mirrored = points * np.array((-1.0, 1.0, 1.0))
    vertex = {}
    for i, name in enumerate(names):
        distance = np.abs(points - mirrored[i]).max(axis=1)
        j = int(np.argmin(distance))
        if distance[j] > eps:
            return None
        vertex[name] = names[j]
    by_set = {frozenset(face.order): face.name for face in faces}
    face_map = {}
    for face in faces:                      # faces without a mirror image (an asymmetric cap) stay unpaired
        other = by_set.get(frozenset(vertex[v] for v in face.order))
        if other is not None:
            face_map[face.name] = other
    return vertex, face_map, eps


def _grow(faces, by_name, edges, members, *, uv_scale, cos_fold, tolerance, max_extent, max_twist, front, refuse):
    """Charts over the faces named in ``members``: a list of {face name: polygon (n, 2), model units}."""
    texel = 1.0 / uv_scale
    assigned = set()
    charts = []
    for seed in sorted((f for f in faces if f.name in members),
                       key=lambda f: (-round(float(f.normal @ front), 1), -f.area, f.index)):
        if seed.name in assigned:
            continue
        chart = _Chart(cell=8 * texel)
        chart.add(seed, seed.local.copy())
        assigned.add(seed.name)
        frontier, counter = [], 0
        reference = [_up_angle(seed, seed.local)]

        def push(face):
            nonlocal counter
            for a, b in zip(face.order, face.order[1:] + face.order[:1]):
                for other in edges[frozenset((a, b))]:
                    if other in members and other not in assigned:
                        fold = float(face.normal @ by_name[other].normal)
                        if fold >= cos_fold:
                            counter += 1
                            heapq.heappush(frontier, (-fold, by_name[other].index, counter, other))

        push(seed)
        while frontier:
            _, _, _, name = heapq.heappop(frontier)
            if name in assigned:
                continue
            face = by_name[name]
            known = [i for i, vertex in enumerate(face.order) if vertex in chart.placed]
            if len(known) < 2:
                continue
            target = np.array([chart.placed[face.order[i]] for i in known])
            transform = _rigid_fit(face.local[known], target)
            polygon = transform(face.local)
            if np.abs(polygon[known] - target).max() > tolerance * texel:
                refuse("closing")
                continue
            polygon[known] = target                          # shared vertices are exactly the chart's
            lo, hi = np.minimum(chart.lo, polygon.min(axis=0)), np.maximum(chart.hi, polygon.max(axis=0))
            if ((hi - lo) * uv_scale > max_extent).any():
                refuse("extent")
                continue
            angle = _up_angle(face, polygon)
            if angle is not None:
                if reference[0] is None:
                    reference[0] = angle
                elif abs((angle - reference[0] + 180.0) % 360.0 - 180.0) > max_twist / 2.0:
                    refuse("twist")
                    continue
            if chart.overlaps(polygon, margin=1e-6 * texel + 1e-9):
                refuse("overlap")
                continue
            chart.add(face, polygon)
            assigned.add(name)
            push(face)
        _orient(chart, by_name)
        charts.append(dict(chart.faces))
    return charts


def build_charts(elem, uv_scale, *, max_fold=DEFAULT_MAX_FOLD, tolerance=DEFAULT_TOLERANCE,
                 max_extent=DEFAULT_MAX_EXTENT, max_twist=DEFAULT_MAX_TWIST, front=(0.0, 0.0, 1.0), reasons=None,
                 symmetric=True):
    """Charts of one mesh element: a list of (width, height, {face name: {vertex: [u, v]}}) in texels.

    ``max_twist`` bounds how much the up direction may turn across one chart (an unrolled cone or a sphere
    fans out): within it the texel grid stays aligned with the model's vertical, as pixel art needs.
    Charts grow from the faces turned most toward ``front`` first, so the most visible side of a part is one
    chart and the cuts fall on its sides. ``reasons`` (a dict) counts why faces were refused, for diagnosis.

    Mirror symmetry (``symmetric``): when the element is its own mirror image across x = 0, charts are grown on
    the +x half only and the -x half gets their exact reflections; faces crossing the plane get charts of their
    own. Every chart's texel grid is anchored on a vertex (one on the mirror plane when the chart has one), so the
    two halves have mirror-identical grids and the plane runs on texel boundaries there."""
    front = np.asarray(front, dtype=float)
    reasons = {} if reasons is None else reasons

    def refuse(reason):
        reasons[reason] = reasons.get(reason, 0) + 1

    faces = _faces(elem)
    by_name = {face.name: face for face in faces}
    edges = {}
    for face in faces:
        for a, b in zip(face.order, face.order[1:] + face.order[:1]):
            edges.setdefault(frozenset((a, b)), []).append(face.name)
    options = dict(uv_scale=uv_scale, cos_fold=math.cos(math.radians(max_fold)), tolerance=tolerance,
                   max_extent=max_extent, max_twist=max_twist, front=front, refuse=refuse)
    mirror = _mirror(elem, faces) if symmetric else None
    local = {k: np.asarray(v, dtype=float) for k, v in elem.get("vertices", {}).items()}
    planned = []          # ("chart", {face: polygon}, anchor vertex) or ("mirror", source entry, {face: source face}, vertex map)
    if mirror is None:
        for chart in _grow(faces, by_name, edges, set(by_name), **options):
            planned.append(("chart", chart, None))
    else:
        vertex_map, face_map, eps = mirror
        centre = {f.name: float(f.points[:, 0].mean()) for f in faces}
        positive = {n for n, x in centre.items() if x > eps and face_map.get(n, n) != n}
        middle = {n for n in by_name if n not in positive and face_map.get(n) not in positive}
        for chart in _grow(faces, by_name, edges, positive, **options):
            names = {v for n in chart for v in by_name[n].order}
            planned.append(("chart", chart, min(names, key=lambda v: (abs(local[v][0]), v))))
            planned.append(("mirror", len(planned) - 1, {face_map[n]: n for n in chart}, vertex_map))
        for chart in _grow(faces, by_name, edges, middle, **options):
            planned.append(("chart", chart, None))

    out = []
    for entry in planned:
        if entry[0] == "mirror":
            _, source, faces_of, mapping = entry
            out.append(_reflected(out[source], faces_of, mapping, by_name, source))
            continue
        _, chart, anchor = entry
        pixels = {name: quantize(polygon * uv_scale) for name, polygon in chart.items()}
        if anchor is None:
            anchor = by_name[next(iter(pixels))].order[0]
        anchor_xy = next(dict(zip(by_name[n].order, p))[anchor] for n, p in pixels.items() if anchor in by_name[n].order)
        lo = np.min([p.min(axis=0) for p in pixels.values()], axis=0)
        base = anchor_xy - np.ceil(anchor_xy - lo - 1e-9)       # the anchor sits on a texel corner
        hi = np.max([p.max(axis=0) for p in pixels.values()], axis=0)
        width, height = (max(1, int(math.ceil(v - 1e-9))) for v in hi - base)
        layout = {name: {vertex: [float(u), float(v)] for vertex, (u, v) in zip(by_name[name].order, polygon - base)}
                  for name, polygon in pixels.items()}
        out.append((width, height, layout, None))
    return out


QUANTUM = 2.0 ** -16      # texels: chart coordinates are multiples of it, so a reflection is exact float arithmetic


def quantize(coords):
    """Round to the QUANTUM grid (dyadic numbers: sums, differences and ``width - u`` are exact in floats)."""
    return np.round(np.asarray(coords, dtype=float) / QUANTUM) * QUANTUM


def _reflected(source, faces_of, vertex_map, by_name, source_number):
    """The exact mirror image of a finished chart: u -> width - u, v unchanged (bit-exact on the QUANTUM grid),
    so both cover exactly the same texels, mirrored. ``faces_of``: mirror face -> source face."""
    width, height, layout, _ = source
    reflected = {}
    for face, source_face in faces_of.items():
        corners = layout[source_face]
        reflected[face] = {v: [width - corners[vertex_map[v]][0], corners[vertex_map[v]][1]]
                           for v in by_name[face].order}
    return width, height, reflected, ("self", source_number, dict(faces_of))


def _world_vertices(elem):
    origin = np.asarray(elem.get("origin", (0.0, 0.0, 0.0)), dtype=float)
    return {k: origin + np.asarray(v, dtype=float) for k, v in elem.get("vertices", {}).items()}


def mirror_partner(source, target):
    """Vertex map target -> source when ``target`` is ``source`` reflected across the model's x = 0 plane (a left /
    right pair such as arm_L / arm_R), else None. Rotated elements are not paired."""
    if any(abs(r) > 1e-9 for e in (source, target) for r in e.get("rotation", (0, 0, 0)) or (0, 0, 0)):
        return None
    if len(source.get("vertices", {})) != len(target.get("vertices", {})) or \
            len(source.get("faces", {})) != len(target.get("faces", {})):
        return None
    src, tgt = _world_vertices(source), _world_vertices(target)
    if not src:
        return None
    names = list(src)
    points = np.array([src[k] for k in names])
    eps = 1e-5 * (float(np.abs(points).max()) or 1.0)
    vertex_map = {}
    for key, point in tgt.items():
        distance = np.abs(points - point * (-1.0, 1.0, 1.0)).max(axis=1)
        j = int(np.argmin(distance))
        if distance[j] > eps:
            return None
        vertex_map[key] = names[j]
    source_faces = {frozenset(f.get("vertices", ())): n for n, f in source["faces"].items()}
    for face in target["faces"].values():
        if frozenset(vertex_map[v] for v in face.get("vertices", ())) not in source_faces:
            return None
    return vertex_map


def reflect_charts(charts, source, target, vertex_map):
    """The charts of ``target`` as exact reflections of ``source``'s charts: same widths, every face the mirror
    image of its source face, texel boundaries mirrored (u -> width - u, exact on the QUANTUM grid)."""
    source_faces = {frozenset(f.get("vertices", ())): n for n, f in source["faces"].items()}
    target_of = {}
    for name, face in target["faces"].items():
        target_of[source_faces[frozenset(vertex_map[v] for v in face.get("vertices", ()))]] = name
    out = []
    for width, height, layout, _ in charts:
        reflected, sources = {}, {}
        for source_face, corners in layout.items():
            target_face = target_of[source_face]
            reflected[target_face] = {w: [width - corners[vertex_map[w]][0], corners[vertex_map[w]][1]]
                                      for w in target["faces"][target_face]["vertices"]}
            sources[target_face] = source_face
        out.append((width, height, reflected, ("element", source.get("name"), sources)))
    return out
