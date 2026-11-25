"""Shared projection services: the texels a region paints seen as one surface, and the questions every projecting
operation (strokes, shapes, decals) asks of it: which texel is under a point, which layers lie under a point, which
one is in front, which face a subsample falls on, and which texel mirrors which.

``SurfaceView`` is built once per region (and offset) and reused; ``front_layer`` is the occlusion test (a neighbour
hides a texel only beyond what its own slope explains); ``lift`` puts a 2D path on every surface layer under it.
"""
from __future__ import annotations

import math

import numpy as np

SAMPLE_STEP = 0.25      # texels between path samples
PLANE_REACH = 0.75      # texels: how far from a projected sample a texel centre may be
SURFACE_REACH = 1.0     # texels: same for surface (3D) samples
LAYER_DEPTH = 1.5       # texels: texels this close behind the front-most hit belong to the same surface


class SurfaceView:
    """Every texel the region paints: stroke-space position, normal, atlas pixel, face and chart."""

    def __init__(self, entries, shift, width, height, sampler=None):
        from .core.surface_sampling import _canvas_to_atlas_rows, _world_rows
        self.entries = entries
        positions, normals, xs, ys, faces, rows_of, charts = [], [], [], [], [], [], []
        centres, steps_x, steps_y, uv0, uvx, uvy = [], [], [], [], [], []
        chart_ids = {}
        self.face_element, self.face_group = [], []
        for k, (face, rows) in enumerate(entries):
            info = face.uv_info
            offset = np.asarray(shift(rows.element_name), dtype=float)
            positions.append(np.asarray(rows.model_position, dtype=float) + offset)
            normals.append(np.asarray(rows.model_normal, dtype=float))
            f = rows.fields
            if sampler is not None and "_e0" in f and len(rows):
                # The texel square in stroke space: its centre and the change per texel step along canvas x / y.
                element = sampler.elements[rows.element_name]
                centre = _world_rows(sampler.builder, element, f["_e0"])
                centres.append(centre + offset)
                steps_x.append(_world_rows(sampler.builder, element, f["_e0"] + f["_ex"]) - centre)
                steps_y.append(_world_rows(sampler.builder, element, f["_e0"] + f["_ey"]) - centre)
                uv0.append(f["_u0"])
                uvx.append(f["_ux"])
                uvy.append(f["_uy"])
            else:
                centres.append(positions[-1])
                steps_x.append(np.zeros((len(rows), 3)))
                steps_y.append(np.zeros((len(rows), 3)))
                uv0.append(np.asarray(rows.face_uv, dtype=float))
                uvx.append(np.zeros((len(rows), 2)))
                uvy.append(np.zeros((len(rows), 2)))
            atlas = np.floor(_canvas_to_atlas_rows(info, rows.x.astype(float), rows.y.astype(float))).astype(np.int64)
            xs.append(atlas[:, 0])
            ys.append(atlas[:, 1])
            faces.append(np.full(len(rows), k))
            rows_of.append(np.arange(len(rows)))
            key = info.get("chart") or (rows.element_name, rows.face_name)
            charts.append(np.full(len(rows), chart_ids.setdefault(key, len(chart_ids))))
            self.face_element.append(rows.element_name)
            self.face_group.append(info.get("group"))
        self.position, self.normal = np.concatenate(positions), np.concatenate(normals)
        self.centre, self.step_x, self.step_y = np.concatenate(centres), np.concatenate(steps_x), np.concatenate(steps_y)
        self.uv0, self.uvx, self.uvy = np.concatenate(uv0), np.concatenate(uvx), np.concatenate(uvy)
        self.x, self.y = np.concatenate(xs), np.concatenate(ys)
        self.face, self.row, self.chart = np.concatenate(faces), np.concatenate(rows_of), np.concatenate(charts)
        self.owner = np.full((height, width), -1, dtype=np.int64)
        inside = (self.x >= 0) & (self.y >= 0) & (self.x < width) & (self.y < height)
        self.owner[self.y[inside], self.x[inside]] = np.flatnonzero(inside)

    @property
    def count(self):
        return len(self.x)

    @property
    def element(self):
        """Element name of every texel."""
        if getattr(self, "_element", None) is None:
            self._element = np.array(self.face_element, dtype=object)[self.face]
        return self._element

    @property
    def group(self):
        """Face group (``model_as_code_group``) of every texel, None where the face has none."""
        if getattr(self, "_group", None) is None:
            self._group = np.array(self.face_group, dtype=object)[self.face]
        return self._group

    def select(self, on=None, groups=None):
        """Bool mask of the texels on elements whose name starts with one of ``on`` and/or in face ``groups``."""
        face_ok = np.ones(len(self.entries), dtype=bool)
        if on:
            prefixes = (on,) if isinstance(on, str) else tuple(on)
            face_ok &= np.array([name.startswith(prefixes) for name in self.face_element])
        if groups:
            wanted = (groups,) if isinstance(groups, str) else tuple(groups)
            face_ok &= np.array([group in wanted for group in self.face_group])
        return face_ok[self.face]

    def write(self, rgba, indices=None, *, coverage=None, blend=None, opacity=1.0):
        """Write RGBA rows (K, 4, 0-255) onto texels ``indices`` (default: every texel, in order) of the canvases of
        the painter's active layer.

        ``blend=None``: fully covered texels take the colour as it is; ``coverage`` (K,, 0..1) composites partly
        covered texels over what is there (normal blend, alpha times coverage). ``blend`` ('normal', 'multiply',
        'screen', 'add'): every texel composites over the canvas with that mode, alpha times coverage, at
        ``opacity``."""
        from .core.color import blend_rows
        rgba = np.asarray(rgba, dtype=float).reshape(-1, 4)
        indices = np.arange(self.count) if indices is None else np.asarray(indices, dtype=np.int64)
        if len(indices) != len(rgba):
            raise ValueError("write: one RGBA row per texel index")
        coverage = np.ones(len(indices)) if coverage is None else np.clip(np.asarray(coverage, float), 0.0, 1.0)
        order = np.argsort(self.face[indices], kind="stable")
        indices, rgba, coverage = indices[order], rgba[order], coverage[order]
        faces = self.face[indices]
        bounds = np.flatnonzero(np.r_[True, faces[1:] != faces[:-1], True])
        for a, b in zip(bounds[:-1], bounds[1:]):
            face, rows = self.entries[int(faces[a])]
            r = self.row[indices[a:b]]
            xs, ys = rows.x[r], rows.y[r]
            color, cov = rgba[a:b], coverage[a:b]
            canvas = face.canvas
            if blend is None:
                full, part = cov >= 1.0, (cov > 0) & (cov < 1.0)
                if full.any():
                    canvas.write_pixels(xs[full], ys[full], np.clip(np.rint(color[full]), 0, 255))
                if part.any():
                    over = color[part].copy()
                    over[:, 3] *= cov[part]
                    canvas.write_pixels(xs[part], ys[part],
                                        blend_rows(canvas.read_pixels(xs[part], ys[part]),
                                                   np.clip(np.rint(over), 0, 255).astype(np.int64)))
            else:
                some = cov > 0
                if some.any():
                    over = color[some].copy()
                    over[:, 3] *= cov[some]
                    canvas.write_pixels(xs[some], ys[some],
                                        blend_rows(canvas.read_pixels(xs[some], ys[some]),
                                                   np.clip(np.rint(over), 0, 255).astype(np.int64),
                                                   mode=blend, opacity=opacity))

    def eligible(self, item, direction, plane):
        """Texels the stroke may paint, by element, face group, facing and depth. A wrapped stroke ignores the
        facing (it reaches grazing and back-facing surfaces) but keeps the depth window."""
        face_ok = np.ones(len(self.entries), dtype=bool)
        if item.on:
            face_ok &= np.array([name.startswith(item.on) for name in self.face_element])
        if item.groups:
            face_ok &= np.array([group in item.groups for group in self.face_group])
        mask = face_ok[self.face]
        if plane or item.wrap:
            if not item.wrap:
                mask &= (self.normal @ direction) >= item.normal_min
            if item.depth is not None:
                along = self.position @ direction
                mask &= (along >= item.depth[0]) & (along <= item.depth[1])
        return mask

    def lift(self, polylines, axes, eligible, texel, *, with_arc=False):
        """3D polylines on every surface layer under 2D ``polylines`` (``wrap``). Each sample of a 2D polyline lands
        on the nearest eligible texel of every chart within reach (one chart is one continuous surface), at the
        exact point of that texel's plane under the sample; edge-on texels are skipped. A chart's run is cut where
        it has no texel under a sample. ``with_arc``: each run comes as (points, arc, index): the distance of each
        point along its 2D polyline and that polyline's index, so pieces of one line know where they lie on it."""
        columns = list(axes)
        coords = self.position[:, columns]
        indices = np.flatnonzero(eligible)
        cell = PLANE_REACH * texel
        buckets = {}
        for index, key in zip(indices.tolist(), map(tuple, np.floor(coords[indices] / cell).astype(np.int64).tolist())):
            buckets.setdefault(key, []).append(index)
        out = []
        for number, polyline in enumerate(polylines):
            samples, _ = resample(polyline, SAMPLE_STEP * texel)
            arcs = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(samples, axis=0), axis=1))]
            runs, run_arcs = {}, {}
            for point, arc in zip(samples, arcs.tolist()):
                base = np.floor(point / cell).astype(np.int64)
                near = [i for dx in (-1, 0, 1) for dy in (-1, 0, 1) for i in buckets.get((base[0] + dx, base[1] + dy), ())]
                best = {}
                if near:
                    near = np.array(near)
                    distance = np.linalg.norm(coords[near] - point, axis=1)
                    for i, d in zip(near.tolist(), distance.tolist()):
                        chart = int(self.chart[i])
                        if d <= PLANE_REACH * texel and (chart not in best or d < best[chart][0]):
                            best[chart] = (d, i)
                seen = set()
                for chart, (_, i) in best.items():
                    steps = np.stack([self.step_x[i][columns], self.step_y[i][columns]], axis=1)
                    if abs(np.linalg.det(steps)) < 0.1 * texel ** 2:       # edge-on to the projection
                        continue
                    offset = np.clip(np.linalg.solve(steps, point - self.centre[i][columns]), -1.0, 1.0)
                    runs.setdefault(chart, []).append(self.centre[i] + offset[0] * self.step_x[i]
                                                      + offset[1] * self.step_y[i])
                    run_arcs.setdefault(chart, []).append(arc)
                    seen.add(chart)
                for chart in [c for c in runs if c not in seen]:
                    out.append((np.array(runs.pop(chart)), np.array(run_arcs.pop(chart)), number))
            out.extend((np.array(runs[c]), np.array(run_arcs[c]), number) for c in runs)
        out = [run for run in out if len(run[0]) >= 2]
        return out if with_arc else [points for points, _arc, _number in out]

    def at(self, x, y):
        """Texel index at atlas pixel (x, y), -1 outside."""
        h, w = self.owner.shape
        if 0 <= x < w and 0 <= y < h:
            return int(self.owner[y, x])
        return -1

    def use(self, coords, allowed):
        """Coordinates the next ``refine`` calls measure in (projected 2D or 3D) and the allowed texels."""
        self.coords, self.allowed, self._steps = coords, allowed, {}

    def _texel_steps(self, index):
        """Change of the measuring coordinates per texel step along x and along y around one texel (same chart)."""
        if index not in self._steps:
            x, y, chart = int(self.x[index]), int(self.y[index]), self.chart[index]
            columns = []
            for dx, dy in ((1, 0), (0, 1)):
                ahead, behind = self.at(x + dx, y + dy), self.at(x - dx, y - dy)
                ahead = ahead if ahead >= 0 and self.chart[ahead] == chart else -1
                behind = behind if behind >= 0 and self.chart[behind] == chart else -1
                if ahead >= 0 and behind >= 0:
                    columns.append((self.coords[ahead] - self.coords[behind]) / 2.0)
                elif ahead >= 0:
                    columns.append(self.coords[ahead] - self.coords[index])
                elif behind >= 0:
                    columns.append(self.coords[index] - self.coords[behind])
                else:
                    columns = None
                    break
            self._steps[index] = None if columns is None else np.stack(columns, axis=1)
        return self._steps[index]

    def refine(self, index, point, plane):
        """(texel index, continuous x, continuous y) of the texel containing ``point``: the sample's position on
        the chart grid from the local texel steps around the nearest texel, floored. Consistent rounding along a
        line keeps a digital line straight on faces seen at an angle (nearest-centre picking alternates rows)."""
        x0, y0 = int(self.x[index]), int(self.y[index])
        steps = self._texel_steps(index)
        if steps is None:
            return index, x0 + 0.5, y0 + 0.5
        offset = np.linalg.lstsq(steps, point - self.coords[index], rcond=None)[0]
        fx, fy = x0 + 0.5 + float(offset[0]), y0 + 0.5 + float(offset[1])
        px, py = int(math.floor(fx)), int(math.floor(fy))
        if (px, py) == (x0, y0):
            return index, fx, fy
        other = self.at(px, py)
        if other >= 0 and self.chart[other] == self.chart[index] and self.allowed[other]:
            return other, fx, fy
        return index, min(max(fx, x0), x0 + 1 - 1e-9), min(max(fy, y0), y0 + 1 - 1e-9)

    def mirror_of(self):
        """(mirror texel index or -1, is-copy flag) per texel, from the UV charts' mirror metadata: a mirrored face's
        texel (x, y) is the exact image of its source texel (K - 1 - x, y - D). Copies are the mirrored side."""
        if getattr(self, "_mirror", None) is None:
            out = np.full(len(self.x), -1, dtype=np.int64)
            copy = np.zeros(len(self.x), dtype=bool)
            first = np.zeros(len(self.entries) + 1, dtype=np.int64)
            first[1:] = np.cumsum([len(rows) for _, rows in self.entries])
            for k, (face, _rows) in enumerate(self.entries):
                mirror = face.uv_info.get("mirror")
                if not mirror:
                    continue
                _source, kk, dd = mirror
                mine = np.arange(first[k], first[k + 1])
                sx, sy = kk - 1 - self.x[mine], self.y[mine] - dd
                h, w = self.owner.shape
                inside = (sx >= 0) & (sy >= 0) & (sx < w) & (sy < h)
                partner = np.full(len(mine), -1, dtype=np.int64)
                partner[inside] = self.owner[sy[inside], sx[inside]]
                ok = partner >= 0
                out[mine[ok]] = partner[ok]
                out[partner[ok]] = mine[ok]
                copy[mine[ok]] = True
            self._mirror = (out, copy)
        return self._mirror



def resample(polyline, step, corner_angle=30.0):
    """Points every ``step`` along a polyline (both ends included), and which of them are sharp corners of the
    polyline (turning by more than ``corner_angle`` degrees), whose pixel the clean-up must keep."""
    out, corners = [polyline[0]], [False]
    closed = len(polyline) > 2 and np.allclose(polyline[0], polyline[-1])
    limit = math.cos(math.radians(corner_angle))

    def sharp(i):
        n = len(polyline)
        if i in (0, n - 1) and not closed:
            return False
        before = polyline[i] - polyline[(i - 1) % (n - 1) if closed and i == 0 else i - 1]
        after = polyline[(i + 1) % (n - 1) if closed and i == n - 1 else i + 1] - polyline[i]
        lb, la = np.linalg.norm(before), np.linalg.norm(after)
        return bool(lb > 1e-12 and la > 1e-12 and (before @ after) / (lb * la) < limit)

    corners[0] = sharp(0)
    for k, (a, b) in enumerate(zip(polyline[:-1], polyline[1:])):
        length = float(np.linalg.norm(b - a))
        count = max(1, int(math.ceil(length / step)))
        t = np.linspace(0.0, 1.0, count + 1)[1:, None]
        out.extend(a + (b - a) * t)
        corners.extend([False] * (count - 1) + [sharp(k + 1)])
    return np.array(out), np.array(corners)



def inside_polygon(points, polygon):
    """Even-odd test of 2D points against a closed polyline."""
    inside = np.zeros(len(points), dtype=bool)
    px, py = points[:, 0], points[:, 1]
    for (xi, yi), (xj, yj) in zip(polygon[:-1], polygon[1:]):
        straddle = (yi > py) != (yj > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            crossing = (xj - xi) * (py - yi) / (yj - yi) + xi
        inside ^= straddle & (px < crossing)
    return inside



class FaceLookup:
    """UV polygons of every chart face (atlas texels), to tell which face a subsample falls on: a texel on the
    edge between two faces is owned by one of them, but its area is shared."""

    def __init__(self, surface, parser):
        index = {(rows.element_name, rows.face_name): k for k, (_face, rows) in enumerate(surface.entries)}
        self.polygon = [None] * len(surface.entries)
        self.by_chart = {}
        for name, elem in parser.elements.items():
            for face_name, info in elem.get("faces", {}).items():
                if not info.get("chart"):
                    continue
                poly = np.asarray(info["points"], dtype=float) + (info["x"], info["y"])
                poly = np.vstack([poly, poly[:1]])
                k = index.get((name, face_name), -1)
                if k >= 0:
                    self.polygon[k] = poly
                self.by_chart.setdefault(info["chart"], []).append(
                    (k, poly, poly.min(axis=0), poly.max(axis=0)))
        self.chart_of = [entry[0].uv_info.get("chart") for entry in surface.entries]
        normals = np.zeros((len(surface.entries), 3))
        np.add.at(normals, surface.face, surface.normal)
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        self.normal = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0)

    def resolve(self, owner, points):
        """Face (surface entry index; -1 for a face outside the painted region) under each subsample ``points``
        (N, S, 2 atlas) of texels owned by ``owner`` (N,): the owner where its polygon holds the point, else
        the chart face that does, else (padding) the owner."""
        n, s = points.shape[:2]
        out = np.full((n, s), -2, dtype=np.int64)
        for k in np.unique(owner):
            rows = np.flatnonzero(owner == k)
            poly = self.polygon[k]
            if poly is None:
                out[rows] = k
                continue
            inside = inside_polygon(points[rows].reshape(-1, 2), poly).reshape(len(rows), s)
            out[rows] = np.where(inside, k, -2)
        missing = out == -2
        if missing.any():
            rows, cols = np.nonzero(missing)
            charts = np.array([self.chart_of[k] or "" for k in owner[rows]], dtype=object)
            for chart in set(charts.tolist()):
                if not chart:
                    continue
                pick = np.flatnonzero(charts == chart)
                p = points[rows[pick], cols[pick]]
                found = np.full(len(pick), -2, dtype=np.int64)
                for k, poly, lo, hi in self.by_chart.get(chart, ()):
                    box = np.flatnonzero((found == -2) & (p >= lo).all(axis=1) & (p <= hi).all(axis=1))
                    if len(box):
                        hit = box[inside_polygon(p[box], poly)]
                        found[hit] = k
                out[rows[pick], cols[pick]] = found
            still = out == -2
            out[still] = np.broadcast_to(owner[:, None], out.shape)[still]
        return out


def front_layer(surface, candidates, coords, direction, texel, reference=None, slope=False):
    """Which ``candidates`` are on the front-most surface layer around them (projected strokes): their depth
    along ``direction`` is within LAYER_DEPTH texels of the front-most texel in the 3 x 3 cells around them
    (front-most among the candidates where the boolean ``reference`` is true; default all). ``slope``: also
    allow the depth change of the texel's own surface across those cells (a face seen at a grazing angle
    recedes quickly, and its own texels must not hide each other)."""
    if not len(candidates):
        return np.zeros(0, dtype=bool)
    depth = surface.position[candidates] @ direction
    cells = np.floor(coords / texel).astype(np.int64)
    use = np.ones(len(candidates), dtype=bool) if reference is None else reference
    if not slope:
        front = {}
        for cell, value, counted in zip(map(tuple, cells.tolist()), depth.tolist(), use.tolist()):
            if counted and value > front.get(cell, -np.inf):
                front[cell] = value
        nearest = np.array([max(front.get((c[0] + dx, c[1] + dy), -np.inf) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
                            for c in cells.tolist()])
        return depth >= nearest - LAYER_DEPTH * texel
    # Smooth: a neighbour occludes a texel only beyond what its own surface can explain. Across a crease the
    # neighbour's face can run steeply toward the viewer (depth changes by tan(angle) per texel of distance), so
    # its allowance grows with its own slope and its distance, not with the texel's.
    tan = np.sqrt(np.clip(1.0 - (surface.normal[candidates] @ direction) ** 2, 0.0, 1.0)) \
        / np.clip(np.abs(surface.normal[candidates] @ direction), 0.05, 1.0)
    members = {}
    for cell, value, slant, counted in zip(map(tuple, cells.tolist()), depth.tolist(), tan.tolist(), use.tolist()):
        if counted:
            members.setdefault(cell, []).append((value, slant))
    out = np.ones(len(candidates), dtype=bool)
    for i, (cell, value) in enumerate(zip(map(tuple, cells.tolist()), depth.tolist())):
        occluded = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                distance = math.hypot(dx, dy) * texel
                for other, slant in members.get((cell[0] + dx, cell[1] + dy), ()):
                    if other - (LAYER_DEPTH * texel + distance * slant) > value:
                        occluded = True
                        break
                if occluded:
                    break
            if occluded:
                break
        out[i] = not occluded
    return out


def region_view(texture_painter, entries, offset=(0.0, 0.0, 0.0)):
    """The ``SurfaceView`` of ``entries`` (a list of (face, rows)) under ``offset`` (a tuple, or a function
    ``element_name -> tuple``), reused by every operation that paints the same faces with the same offset."""
    shift = offset if callable(offset) else (lambda _name, value=tuple(offset): value)
    key = (tuple(id(rows) for _face, rows in entries), offset if callable(offset) else tuple(offset))
    views = texture_painter.__dict__.setdefault("_surface_views", {})
    view = views.get(key)
    if view is None:
        view = SurfaceView(entries, shift, texture_painter.width, texture_painter.height,
                           texture_painter.surface_sampler)
        views.clear()                       # one cached view: it holds large per-texel arrays
        views[key] = view
    return view
