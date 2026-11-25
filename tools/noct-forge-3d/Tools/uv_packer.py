"""
Box UV 2D Bin Packing Engine for Blockbench models.

Packs voxel cubes into the tightest square power-of-two (POT) texture atlas
(32x32 -> 64x64 -> 128x128 -> 256x256...) using the MaxRects (Maximal Rectangles)
algorithm with Best Short Side Fit (BSSF) heuristics.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


DEFAULT_UV_SCALE = 1

REPO_ROOT = Path(__file__).resolve().parents[1]
import sys as _sys
if str(REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(REPO_ROOT))
from Tools._resolve import resolve_model_target


def _replace_file(source, target):
    """Tolerate short-lived Windows scanners holding a freshly written file."""
    for attempt in range(5):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (2 ** attempt))


def validate_uv_scale(value):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0 or value != int(value)):
        raise ValueError("uv_scale must be a positive integer (pixels per model unit)")
    return int(value)


def validate_island_padding(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("island_padding must be a non-negative integer pixel count")
    return value


def _geometry_dimension(value, label):
    if (not math.isfinite(value) or value <= 0
            or not math.isclose(value, round(value), rel_tol=0, abs_tol=1e-5)
            or round(value) < 1):
        raise ValueError(f"{label}: geometry size {value:g} must be a positive integer before applying density; correct the geometry explicitly")
    return round(value)


def _pixel_dimension(value, label):
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label}: pixel dimension must be positive and finite")
    pixels = round(value)
    if pixels < 1 or not math.isclose(value, pixels, rel_tol=0, abs_tol=1e-5):
        raise ValueError(f"{label}: {value:g} pixels is incompatible with integer pixels at this density; no rounding is applied")
    return pixels


@dataclass
class BoxUVItem:
    """Represents a cube or quad element to be packed in Box UV format."""
    name: str
    dx: int
    dy: int
    dz: int
    is_quad: bool = False
    uuid: Optional[str] = None
    u: int = 0
    v: int = 0
    padding: int = 0
    pin: Optional[Tuple[int, int]] = None     # fixed atlas position of the content (UV rule ``pin``)
    block: Optional[str] = None               # block the ``grouped`` packer keeps this island in
    texture: str = "default"                  # texture atlas slot name (UV rule ``texture``)

    @property
    def width(self) -> int:
        """Total required footprint width in the atlas."""
        if self.is_quad:
            content = max(1, self.dx)
        else:
            content = max(1, 2 * (self.dx + self.dz))
        return content + 2 * self.padding

    @property
    def height(self) -> int:
        """Total required footprint height in the atlas."""
        if self.is_quad:
            content = max(1, self.dy)
        else:
            content = max(1, self.dz + self.dy)
        return content + 2 * self.padding

    @property
    def area(self) -> int:
        return self.width * self.height

    def get_face_uvs(self) -> Dict[str, List[int]]:
        """
        Calculates canonical Blockbench face UV rectangles [u1, v1, u2, v2]
        based on the assigned uv_offset (u, v).
        """
        u, v = self.u + self.padding, self.v + self.padding
        dx, dy, dz = self.dx, self.dy, self.dz

        if self.is_quad:
            return {
                "quad": [u, v, u + dx, v + dy]
            }

        return {
            "up": [u + dz + dx, v + dz, u + dz, v],
            "down": [u + dz + 2 * dx, v, u + dz + dx, v + dz],
            "east": [u, v + dz, u + dz, v + dz + dy],
            "north": [u + dz, v + dz, u + dz + dx, v + dz + dy],
            "west": [u + dz + dx, v + dz, u + 2 * dz + dx, v + dz + dy],
            "south": [u + 2 * dz + dx, v + dz, u + 2 * (dz + dx), v + dz + dy],
        }


class MaxRectsPacker:
    """
    2D Bin Packer using Maximal Rectangles with Best Short Side Fit (BSSF).
    Finds compact placements in integer coordinates with zero overlap.
    """
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        # Free rectangles stored as (x, y, w, h)
        self.free_rects: List[Tuple[int, int, int, int]] = [(0, 0, width, height)]

    def find_position_bssf(self, w: int, h: int) -> Optional[Tuple[int, int]]:
        """Finds the best (x, y) placement that minimizes the leftover short side."""
        best_short_side = float("inf")
        best_long_side = float("inf")
        best_y = float("inf")
        best_x = float("inf")
        best_pos: Optional[Tuple[int, int]] = None

        for fx, fy, fw, fh in self.free_rects:
            if fw >= w and fh >= h:
                leftover_w = fw - w
                leftover_h = fh - h
                short_side = min(leftover_w, leftover_h)
                long_side = max(leftover_w, leftover_h)

                # Prioritize: smaller short side, smaller long side, lower Y (bottom-first), lower X
                score = (short_side, long_side, fy, fx)
                current_best = (best_short_side, best_long_side, best_y, best_x)
                if score < current_best:
                    best_short_side = short_side
                    best_long_side = long_side
                    best_y = fy
                    best_x = fx
                    best_pos = (fx, fy)

        return best_pos

    def place_rect(self, rx: int, ry: int, rw: int, rh: int) -> None:
        """Places a rectangle and splits/prunes intersecting free rectangles."""
        new_free_rects: List[Tuple[int, int, int, int]] = []

        for fx, fy, fw, fh in self.free_rects:
            # Check for intersection
            if not (rx >= fx + fw or rx + rw <= fx or ry >= fy + fh or ry + rh <= fy):
                # Intersects: generate up to 4 maximal subdivisions
                # 1. Top slice
                if ry > fy and ry < fy + fh:
                    new_free_rects.append((fx, fy, fw, ry - fy))
                # 2. Bottom slice
                if ry + rh < fy + fh:
                    new_free_rects.append((fx, ry + rh, fw, fy + fh - (ry + rh)))
                # 3. Left slice
                if rx > fx and rx < fx + fw:
                    new_free_rects.append((fx, fy, rx - fx, fh))
                # 4. Right slice
                if rx + rw < fx + fw:
                    new_free_rects.append((rx + rw, fy, fx + fw - (rx + rw), fh))
            else:
                new_free_rects.append((fx, fy, fw, fh))

        # Prune redundant rectangles (remove any rect that is entirely contained in another)
        self.free_rects = self._prune_contained(new_free_rects)

    @staticmethod
    def _prune_contained(rects: List[Tuple[int, int, int, int]]) -> List[Tuple[int, int, int, int]]:
        rects = list(dict.fromkeys(rects))
        pruned = []
        n = len(rects)
        for i in range(n):
            x1, y1, w1, h1 = rects[i]
            if w1 <= 0 or h1 <= 0:
                continue
            is_contained = False
            for j in range(n):
                if i == j:
                    continue
                x2, y2, w2, h2 = rects[j]
                if x1 >= x2 and y1 >= y2 and x1 + w1 <= x2 + w2 and y1 + h1 <= y2 + h2:
                    is_contained = True
                    break
            if not is_contained:
                pruned.append((x1, y1, w1, h1))
        return pruned


class AtlasSize(tuple):
    """Represents an atlas size as width and height."""
    def __new__(cls, w: int, h: int):
        return super().__new__(cls, (int(w), int(h)))

    @property
    def width(self) -> int:
        return self[0]

    @property
    def height(self) -> int:
        return self[1]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, int):
            return self[0] == other and self[1] == other
        return super().__eq__(other)

    def __int__(self) -> int:
        return max(self[0], self[1])


def _pinned_origin(item):
    """Top-left of a pinned item's footprint: the pin is where its content (inside the padding) starts."""
    u, v = item.pin[0] - item.padding, item.pin[1] - item.padding
    if u < 0 or v < 0:
        raise ValueError(f"{item.name}: pin {list(item.pin)} leaves no room for island_padding {item.padding}")
    return u, v


def _place_maxrects(items, width, height):
    """MaxRects (BSSF) placement, tallest first; pinned items are placed where they are pinned.
    Returns the placed items, or None when they do not fit."""
    rects = MaxRectsPacker(width, height)
    placed = []
    for item in items:
        if item.pin is not None:
            item.u, item.v = _pinned_origin(item)
            rects.place_rect(item.u, item.v, item.width, item.height)
            placed.append(item)
    for item in sorted((it for it in items if it.pin is None),
                       key=lambda it: (-it.height, -it.width, -it.area, it.name)):
        pos = rects.find_position_bssf(item.width, item.height)
        if pos is None:
            return None
        item.u, item.v = pos
        rects.place_rect(pos[0], pos[1], item.width, item.height)
        placed.append(item)
    return placed


def _place_shelf(items, width, height):
    """Rows left to right in document order, a new row when one is full; pinned items are obstacles."""
    pinned = [item for item in items if item.pin is not None]
    for item in pinned:
        item.u, item.v = _pinned_origin(item)
    placed = list(pinned)
    x = y = row = 0
    for item in (it for it in items if it.pin is None):
        while True:
            if x + item.width > width:
                x, y, row = 0, y + row, 0
            if y + item.height > height:
                return None
            hit = next((p for p in pinned if x < p.u + p.width and p.u < x + item.width
                        and y < p.v + p.height and p.v < y + item.height), None)
            if hit is None:
                break
            x = hit.u + hit.width
            row = max(row, 1)
        item.u, item.v = x, y
        x += item.width
        row = max(row, item.height)
        placed.append(item)
    return placed


def _block_layout(group):
    """Pack one block's items as tightly as MaxRects finds within a few widths; positions are block-relative."""
    area = sum(it.area for it in group)
    widest = max(it.width for it in group)
    tallest = sum(it.height for it in group)
    side = max(widest, math.ceil(math.sqrt(area)))
    best = None
    for width in sorted({side + k * max(1, side // 8) for k in range(12)} | {max(widest, sum(it.width for it in group))}):
        placed = _place_maxrects(group, width, tallest)
        if placed is None:
            continue
        used_w = max(it.u + it.width for it in placed)
        used_h = max(it.v + it.height for it in placed)
        score = (used_w * used_h, abs(used_w - used_h))
        if best is None or score < best[0]:
            best = (score, used_w, used_h, {id(it): (it.u, it.v) for it in placed})
    _, width, height, positions = best
    return width, height, positions


def _group_blocks(items):
    """Replace the items of every block by one block item; pinned items stay on their own."""
    out, blocks, members = [], {}, {}
    for item in items:
        if item.pin is not None:
            out.append(item)
        else:
            blocks.setdefault(item.block or "", []).append(item)
    for name, group in sorted(blocks.items()):
        width, height, positions = _block_layout(group)
        key = f"#block:{name}"
        out.append(BoxUVItem(name=key, dx=width, dy=height, dz=0, is_quad=True, uuid=key))
        members[key] = [(item, *positions[id(item)]) for item in group]
    return out, members


def _unpack_blocks(placed, members):
    out = []
    for item in placed:
        if item.uuid in members:
            for member, du, dv in members[item.uuid]:
                member.u, member.v = item.u + du, item.v + dv
                out.append(member)
        else:
            out.append(item)
    return out


PACKERS = {"maxrects": _place_maxrects, "shelf": _place_shelf, "grouped": _place_maxrects}


class BoxUVPacker:
    """
    High-level orchestrator for packing Blockbench elements into
    the minimum Power-of-Two (POT) atlas with independent width and height.
    """

    @staticmethod
    def create_item_from_cube(
        name: str,
        from_: Sequence[float],
        to_: Sequence[float],
        uuid: Optional[str] = None
    ) -> BoxUVItem:
        dx, dy, dz = (_pixel_dimension(abs(to_[i] - from_[i]), f"{name}/{axis}")
                      for i, axis in enumerate("XYZ"))
        return BoxUVItem(name=name, dx=dx, dy=dy, dz=dz, uuid=uuid)

    @staticmethod
    def create_item_from_quad(
        name: str,
        size: Sequence[float],
        uuid: Optional[str] = None
    ) -> BoxUVItem:
        w = _pixel_dimension(abs(size[0]), f"{name}/width")
        h = _pixel_dimension(abs(size[1]), f"{name}/height")
        return BoxUVItem(name=name, dx=w, dy=h, dz=0, is_quad=True, uuid=uuid)

    @staticmethod
    def _mesh_face_size(elem, face):
        """Rectangular planar quad edge lengths; UVs are never used as geometry."""
        order = face.get("vertices", [])
        vertices = elem.get("vertices", {})
        if len(order) != 4 or len(set(order)) != 4 or any(k not in vertices for k in order):
            raise ValueError(f"{elem['name']}: UV remapping supports rectangular four-vertex mesh faces only")
        points = [vertices[k] for k in order]
        if any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in points):
            raise ValueError(f"{elem['name']}: invalid mesh vertices")
        a = [points[1][i]-points[0][i] for i in range(3)]
        b = [points[3][i]-points[0][i] for i in range(3)]
        w, h = math.sqrt(sum(v*v for v in a)), math.sqrt(sum(v*v for v in b))
        if (min(w, h) <= 0 or abs(sum(x*y for x, y in zip(a, b))) > 1e-6*w*h
                or any(not math.isclose(points[2][i], points[0][i]+a[i]+b[i], abs_tol=1e-6)
                       for i in range(3))):
            raise ValueError(f"{elem['name']}: mesh face is not a planar rectangle")
        return w, h

    @staticmethod
    def _mesh_face_layout(elem, face, uv_scale, require_integer_uvs=True):
        """Return dimensions and orientation-stable per-vertex local UVs."""
        order = face.get("vertices", [])
        vertices = elem.get("vertices", {})
        if len(order) not in (3, 4) or len(set(order)) != len(order) or any(k not in vertices for k in order):
            raise ValueError(f"{elem['name']}: mesh face needs exactly three or four distinct valid vertices")
        points = [vertices[k] for k in order]
        if any(len(p) != 3 or any(not math.isfinite(v) for v in p) for p in points):
            raise ValueError(f"{elem['name']}: invalid mesh vertices")
        def sub(a,b): return [a[i]-b[i] for i in range(3)]
        def dot(a,b): return sum(a[i]*b[i] for i in range(3))
        def cross(a,b): return [a[1]*b[2]-a[2]*b[1],
                                a[2]*b[0]-a[0]*b[2],
                                a[0]*b[1]-a[1]*b[0]]
        def length(value): return math.sqrt(dot(value,value))
        edge = sub(points[1],points[0])
        if length(edge) <= 1e-8: raise ValueError(f"{elem['name']}: degenerate mesh face")
        normal=[0.0,0.0,0.0]
        for first,second in zip(points,points[1:]+points[:1]):
            normal[0]+=(first[1]-second[1])*(first[2]+second[2])
            normal[1]+=(first[2]-second[2])*(first[0]+second[0])
            normal[2]+=(first[0]-second[0])*(first[1]+second[1])
        n_len = math.sqrt(sum(v*v for v in normal))
        if n_len <= 1e-8: raise ValueError(f"{elem['name']}: degenerate mesh face")
        normal = [v/n_len for v in normal]
        offsets=[sub(point,points[0]) for point in points]
        nonplanar=any(abs(dot(delta,normal))>1e-5 for delta in offsets)
        if nonplanar:
            # Preserve a dense rectangular grid on an authored topological quad.
            # Triangles are necessarily planar, so this branch is quad-only.
            if len(points) != 4:
                raise ValueError(f"{elem['name']}: non-planar triangle")
            width=(length(sub(points[1],points[0]))+length(sub(points[2],points[3])))/2
            height=(length(sub(points[2],points[1]))+length(sub(points[3],points[0])))/2
            coords=[(0.0,0.0),(width,0.0),(width,height),(0.0,height)]
        else:
            dominant=max(range(3),key=lambda index:(abs(normal[index]),-index))
            preferred=(1.0,0.0,0.0) if dominant in (1,2) else (0.0,0.0,1.0)
            projection=[preferred[i]-dot(preferred,normal)*normal[i] for i in range(3)]
            projection_len=length(projection)
            if projection_len<=1e-8:
                raise ValueError(f"{elem['name']}: cannot derive canonical UV orientation")
            u_axis=[value/projection_len for value in projection]
            v_axis=cross(normal,u_axis)
            desired=(0.0,0.0,1.0) if dominant==1 else (0.0,-1.0,0.0)
            if dot(v_axis,desired)<0:
                v_axis=[-value for value in v_axis]
            coords=[(dot(delta,u_axis),dot(delta,v_axis)) for delta in offsets]
        min_u, min_v = min(x for x,_ in coords), min(y for _,y in coords)
        if not require_integer_uvs:
            width = (max(x for x, _ in coords)-min_u)*uv_scale
            height = (max(y for _, y in coords)-min_v)*uv_scale
            # Integer allocation centered on a half-pixel lattice; only translate.
            w, h = math.ceil(width), math.ceil(height)
            dx, dy = (w-width)/2, (h-height)/2
            return w, h, {key: [(u-min_u)*uv_scale+dx, (v-min_v)*uv_scale+dy]
                          for key, (u, v) in zip(order, coords)}
        pixels = {key: [int(round((uv[0]-min_u)*uv_scale)),
                        int(round((uv[1]-min_v)*uv_scale))]
                  for key, uv in zip(order, coords)}
        width = max(v[0] for v in pixels.values())
        height = max(v[1] for v in pixels.values())
        pixel_order = [pixels[key] for key in order]
        area2 = abs(sum(pixel_order[i][0]*pixel_order[(i+1)%len(pixel_order)][1] -
                        pixel_order[(i+1)%len(pixel_order)][0]*pixel_order[i][1]
                        for i in range(len(pixel_order))))
        if (width <= 0 or height <= 0 or area2 == 0
                or len({tuple(point) for point in pixel_order}) != len(pixel_order)):
            raise ValueError(f"{elem['name']}: polygon collapses at UV density {uv_scale:g} (face on vertices "
                             f"{', '.join(order)}): raise it with --uv-scale {uv_scale * 2:g}, or allow fractional "
                             "UVs with --no-require-integer-uvs")
        return width, height, pixels

    @classmethod
    def _document_items(cls, data, uv_scale, require_integer_uvs=True, layout="faces"):
        uv_scale = validate_uv_scale(uv_scale)
        items, targets, names = [], {}, set()
        chart_cache = {}           # element index -> its charts, for mirrored partners further down
        for index, elem in enumerate(data.get("elements", [])):
            kind = elem.get("type", "cube")
            if kind not in {"cube", "mesh"}:
                continue
            name = elem.get("name")
            if not name or name in names:
                raise ValueError(f"Missing or duplicate element name: {name!r}")
            names.add(name)
            if kind == "cube":
                start, end = elem.get("from"), elem.get("to")
                if not start or not end or len(start) != 3 or len(end) != 3:
                    raise ValueError(f"{name}: missing cube geometry")
                if any(not math.isfinite(v) for v in start + end):
                    raise ValueError(f"{name}: non-finite cube geometry")
                dims = [_geometry_dimension(abs(end[i]-start[i]), f"{name}/{axis}")*uv_scale
                        for i, axis in enumerate("XYZ")]
                key = str(index)
                item = cls.create_item_from_cube(name, (0, 0, 0), dims, uuid=key)
                items.append(item)
                targets[key] = ("box", index)
            elif kind == "mesh" and layout == "charts":
                if not elem.get("faces"):
                    raise ValueError(f"{name}: mesh has no faces")
                from .uv_charts import build_charts, mirror_partner, reflect_charts
                from lib.model_builder import _canonical_quad
                # A chart's UV is not an exact affine image of every quad (the unfolding closes within a texel),
                # so the A-C diagonal a quad is drawn with bends its texture: give every quad its canonical
                # diagonal (same shape, deterministic and mirror-consistent) before unfolding.
                local = {key: [v + o for v, o in zip(value, elem.get("origin", (0, 0, 0)))]
                         for key, value in (elem.get("vertices") or {}).items()}
                for face in elem["faces"].values():
                    order = face.get("vertices", ())
                    if len(order) == 4 and all(key in local for key in order):
                        face["vertices"] = _canonical_quad(order, local, planar=True)
                # A left/right pair (arm_L / arm_R) gets exactly reflected charts: same pixel space, mirrored.
                charts = None
                for source_index, source_charts in chart_cache.items():
                    source = data["elements"][source_index]
                    mapping = mirror_partner(source, elem)
                    if mapping is not None:
                        charts = reflect_charts(source_charts, source, elem, mapping)
                        break
                if charts is None:
                    charts = build_charts(elem, uv_scale)
                    chart_cache[index] = charts
                for number, (w, h, faces_layout, mirror) in enumerate(charts):
                    key = f"{index}:#chart{number}"
                    items.append(cls.create_item_from_quad(f"{name}/chart{number}", (w, h), uuid=key))
                    sources = {}
                    if mirror is not None:          # each mirrored face names the face it reflects
                        source_element = name if mirror[0] == "self" else mirror[1]
                        sources = {face: [source_element, src] for face, src in mirror[2].items()}
                    targets[key] = ("chart", index, faces_layout, f"{name}#{number}", sources)
            elif kind == "mesh":
                if not elem.get("faces"):
                    raise ValueError(f"{name}: mesh has no faces")
                for face_name, face in elem["faces"].items():
                    order = face.get("vertices", ())
                    vertices = elem.get("vertices", {})
                    if len(order) not in (3, 4) or len(set(order)) != len(order):
                        raise ValueError(f"{name}/{face_name}: every mesh face must have exactly three or four distinct vertices")
                    if any(vertex not in vertices for vertex in order):
                        raise ValueError(f"{name}/{face_name}: face references a missing vertex")
                    if "texture" in face and face["texture"] is None:
                        continue
                    w, h, corners = cls._face_island(elem, face_name, uv_scale, require_integer_uvs)
                    key = f"{index}:{face_name}"
                    items.append(cls.create_item_from_quad(f"{name}/{face_name}", (w, h), uuid=key))
                    targets[key] = ("face", index, face_name, corners, [])
            else:
                raise ValueError(f"{name}: unsupported element type {kind!r}; no file was changed")
        return items, targets

    @classmethod
    def _face_island(cls, elem, face_name, uv_scale, require_integer_uvs=True):
        """One face on its own: (width, height, corners) in pixels at ``uv_scale``.

        ``corners`` is None for a rectangle (cube faces, planar rectangular quads: the island's corners in vertex
        order), else the per-vertex pixel layout inside the island."""
        name = elem["name"]
        if elem.get("type", "cube") == "cube":
            start, end = elem["from"], elem["to"]
            x, y, z = (_geometry_dimension(abs(b - a), name) * uv_scale for a, b in zip(start, end))
            w, h = dict(north=(x, y), south=(x, y), east=(z, y), west=(z, y), up=(x, z), down=(x, z))[face_name]
            return w, h, None
        face = elem["faces"][face_name]
        if elem.get("model_as_code_mesh"):
            return cls._mesh_face_layout(elem, face, uv_scale, require_integer_uvs)
        try:
            w, h = cls._mesh_face_size(elem, face)
        except ValueError as rectangle_error:
            if "four-vertex" not in str(rectangle_error) and "not a planar rectangle" not in str(rectangle_error):
                raise
            return cls._mesh_face_layout(elem, face, uv_scale, require_integer_uvs)
        return (_geometry_dimension(w, f"{name}/{face_name}/width") * uv_scale,
                _geometry_dimension(h, f"{name}/{face_name}/height") * uv_scale, None)

    @classmethod
    def _shared_items(cls, data, links, uv_scale, require_integer_uvs=True):
        """One island per owner face; each follower is written into its owner's island (``share_uv``)."""
        from .uv_contract import face_sizes
        refs = list(face_sizes(data, uv_scale, require_integer_uvs))
        index_of = {elem.get("name"): index for index, elem in enumerate(data.get("elements", []))}
        items, targets = [], {}
        for number, ref in enumerate(r for r in refs if r not in links):
            elem = data["elements"][index_of[ref[0]]]
            w, h, corners = cls._face_island(elem, ref[1], uv_scale, require_integer_uvs)
            key = str(number)
            items.append(cls.create_item_from_quad(str(ref), (w, h), uuid=key))
            targets[key] = ("face", index_of[ref[0]], ref[1], corners, [])
        owner_key = {(data["elements"][t[1]]["name"], t[2]): key for key, t in targets.items()}
        for ref in refs:
            if ref in links:
                elem = data["elements"][index_of[ref[0]]]
                corners = cls._face_island(elem, ref[1], uv_scale, require_integer_uvs)[2]
                targets[owner_key[links[ref]]][4].append((index_of[ref[0]], ref[1], corners))
        return items, targets

    @classmethod
    def _fit_corners(cls, elem, face_name, w, h, *, flat, integer):
        """Corners of a face stretched over a w x h island (``fixed``), or on its corners (``flat``).

        None for a rectangle (cube faces, planar rectangular quads), else the per-vertex layout in the island."""
        if elem.get("type", "cube") == "cube":
            return None
        face = elem["faces"][face_name]
        if not elem.get("model_as_code_mesh"):
            try:
                cls._mesh_face_size(elem, face)
                return None
            except ValueError as error:
                if "four-vertex" not in str(error) and "not a planar rectangle" not in str(error):
                    raise
        order = list(face["vertices"])
        local = cls._mesh_face_layout(elem, face, 1, False)[2]
        xs, ys = [local[k][0] for k in order], [local[k][1] for k in order]
        span_x, span_y = (max(xs) - min(xs)) or 1.0, (max(ys) - min(ys)) or 1.0
        points = [((x - min(xs)) / span_x * w, (y - min(ys)) / span_y * h) for x, y in zip(xs, ys)]
        if flat:
            # One colour: every vertex on an island corner (always whole texels, in any UV mode).
            points = [(w if x * 2 >= w else 0, h if y * 2 >= h else 0) for x, y in points]
            if len(set(points)) != len(points):
                points = [(0, 0), (w, 0), (w, h), (0, h)][:len(order)]
        elif integer:
            points = [(round(x), round(y)) for x, y in points]
        area2 = sum(points[i][0] * points[(i + 1) % len(points)][1] - points[(i + 1) % len(points)][0] * points[i][1]
                    for i in range(len(points)))
        if len(set(points)) != len(points) or area2 == 0:
            raise ValueError(f"{elem['name']}/{face_name}: face collapses in a {w}x{h} fixed island; "
                             "use a larger size or fractional UVs")
        return {key: [x, y] for key, (x, y) in zip(order, points)}

    @classmethod
    def _rule_items(cls, data, specs, links, default_density, require_integer_uvs=True):
        """Islands for faces resolved by UV rules (``Tools.uv_rules``).

        Returns (items, targets, region links, texels per layout). Region links are the faces a ``flat`` island
        shares: written to ``uv_sharing`` with ``region: true`` so the painter knows their owner."""
        from .uv_charts import build_charts, mirror_partner, reflect_charts
        from .uv_rules import FaceSpec, textured_faces
        items, targets, owners, flat, region, layouts = [], {}, {}, {}, [], {}
        names = set()
        linked = set(links) | set(links.values())
        for ref in linked:
            if ref in specs and specs[ref].layout not in ("box", "faces"):
                raise ValueError(f"{ref}: share_uv needs the faces (or box) layout, not {specs[ref].layout}")
        for target, source in links.items():
            if target in specs and source in specs and specs[target] != specs[source]:
                raise ValueError(f"share_uv faces need the same UV rules: {target} -> {source}")

        def add(label, size, target, spec):
            """Island of a quad (w, h) or of a cube cross (dx, dy, dz)."""
            key = str(len(items))
            item = (cls.create_item_from_cube(label, (0, 0, 0), size, uuid=key) if len(size) == 3
                    else cls.create_item_from_quad(label, size, uuid=key))
            item.pin, item.block, item.texture = spec.pin, spec.block, spec.texture
            items.append(item)
            targets[key] = target
            layouts[spec.layout] = layouts.get(spec.layout, 0) + item.width * item.height
            return key

        chart_cache = {}             # element index -> (density, texture, charts) of elements charted whole
        for index, elem in enumerate(data.get("elements", [])):
            kind = elem.get("type", "cube")
            if kind not in ("cube", "mesh"):
                continue
            name = elem.get("name")
            if not name or name in names:
                raise ValueError(f"Missing or duplicate element name: {name!r}")
            names.add(name)
            if kind == "cube":
                start, end = elem.get("from"), elem.get("to")
                if not start or not end or len(start) != 3 or len(end) != 3:
                    raise ValueError(f"{name}: missing cube geometry")
                if any(not math.isfinite(v) for v in start + end):
                    raise ValueError(f"{name}: non-finite cube geometry")
            elif not elem.get("faces"):
                raise ValueError(f"{name}: mesh has no faces")
            else:
                for face_name, face in elem["faces"].items():
                    order = face.get("vertices", ())
                    if len(order) not in (3, 4) or len(set(order)) != len(order):
                        raise ValueError(f"{name}/{face_name}: every mesh face must have exactly three or four distinct vertices")
                    if any(vertex not in elem.get("vertices", {}) for vertex in order):
                        raise ValueError(f"{name}/{face_name}: face references a missing vertex")
            faces = [(face_name, specs[name, face_name]) for face_name in textured_faces(elem)]
            if kind == "cube":
                same = {(s.layout, s.density, s.pin, s.block, s.texture) for _, s in faces}
                if not faces or (len(same) == 1 and faces[0][1].layout == "box"
                                 and not any((name, f) in linked for f, _ in faces)):
                    spec = faces[0][1] if faces else FaceSpec(layout="box", density=default_density)
                    dims = [_geometry_dimension(abs(end[i] - start[i]), f"{name}/{axis}") * spec.density
                            for i, axis in enumerate("XYZ")]
                    add(name, dims, ("box", index), spec)
                    continue
                # Faces of one cube resolved differently: the cross splits into one island per face.
                faces = [(f, replace(s, layout="faces") if s.layout == "box" else s) for f, s in faces]
            charted = {}
            for face_name, spec in faces:
                ref = (name, face_name)
                if ref in links:
                    continue
                if spec.layout == "charts":
                    if require_integer_uvs:
                        raise ValueError("the charts layout unfolds faces with exact sizes: it needs "
                                         "--no-require-integer-uvs")
                    charted.setdefault((spec.density, spec.pin, spec.block, spec.texture), []).append(face_name)
                elif spec.layout in ("faces", "box"):
                    w, h, corners = cls._face_island(elem, face_name, spec.density, require_integer_uvs)
                    owners[ref] = add(f"{name}/{face_name}", (w, h), ("face", index, face_name, corners, []), spec)
                elif spec.layout == "fixed":
                    w, h = spec.size
                    corners = cls._fit_corners(elem, face_name, w, h, flat=False, integer=require_integer_uvs)
                    add(f"{name}/{face_name}", (w, h), ("face", index, face_name, corners, []), spec)
                else:
                    group = {"face": ref, "element": name, "rule": ("#rule", spec.flat_rule)}[spec.per]
                    flat.setdefault((group, spec.size, spec.pin, spec.block, spec.texture), []).append((index, face_name, spec))
            if charted:
                from lib.model_builder import _canonical_quad
                local = {key: [v + o for v, o in zip(value, elem.get("origin", (0, 0, 0)))]
                         for key, value in (elem.get("vertices") or {}).items()}
                for face in elem["faces"].values():
                    order = face.get("vertices", ())
                    if len(order) == 4 and all(key in local for key in order):
                        face["vertices"] = _canonical_quad(order, local, planar=True)
            whole = len(charted) == 1 and len(next(iter(charted.values()))) == len(elem["faces"])
            for (density, pin, block, tex), members in charted.items():
                charts = None
                if whole:
                    for source_index, (source_density, source_tex, source_charts) in chart_cache.items():
                        source = data["elements"][source_index]
                        mapping = (mirror_partner(source, elem)
                                   if (source_density == density and source_tex == tex) else None)
                        if mapping is not None:
                            charts = reflect_charts(source_charts, source, elem, mapping)
                            break
                if charts is None:
                    part = dict(elem, faces={face_name: elem["faces"][face_name] for face_name in members})
                    charts = build_charts(part, density)
                    if whole:
                        chart_cache[index] = (density, tex, charts)
                if pin is not None and len(charts) != 1:
                    raise ValueError(f"{name}: pin needs exactly one island, but these faces unfold into "
                                     f"{len(charts)} charts; pin a single face")
                spec = specs[name, members[0]]
                offset = sum(1 for t in targets.values() if t[0] == "chart" and t[1] == index)
                for number, (w, h, faces_layout, mirror) in enumerate(charts, start=offset):
                    sources = {}
                    if mirror is not None:
                        source_element = name if mirror[0] == "self" else mirror[1]
                        sources = {face: [source_element, src] for face, src in mirror[2].items()}
                    add(f"{name}/chart{number}", (w, h), ("chart", index, faces_layout, f"{name}#{number}", sources),
                        spec)
        for (_, (w, h), _, _, _), members in flat.items():
            # The owner is a face that covers the whole island (a rectangle or a quad on all four corners).
            corners = [cls._fit_corners(data["elements"][i], f, w, h, flat=True, integer=True) for i, f, _ in members]
            first = next((n for n, c in enumerate(corners) if c is None or len(c) == 4), 0)
            order = [first] + [n for n in range(len(members)) if n != first]
            index, face_name, spec = members[first]
            owner = (data["elements"][index]["name"], face_name)
            followers = [(members[n][0], members[n][1], corners[n]) for n in order[1:]]
            add(f"{owner[0]}/{face_name}", (w, h), ("face", index, face_name, corners[first], followers), spec)
            region.extend({"target": [data["elements"][i]["name"], f], "source": list(owner), "region": True}
                          for i, f, _ in followers)
        index_of = {elem.get("name"): index for index, elem in enumerate(data.get("elements", []))}
        for target, source in links.items():
            if source not in owners:
                raise ValueError(f"Missing or disabled UV face: {target} -> {source}")
            corners = cls._face_island(data["elements"][index_of[target[0]]], target[1], specs[source].density,
                                       require_integer_uvs)[2]
            targets[owners[source]][4].append((index_of[target[0]], target[1], corners))
        pinned = {}
        for item in items:
            if item.pin is not None:
                pinned.setdefault((item.texture, item.pin), []).append(item.name)
        for (_, pin), labels in pinned.items():
            if len(labels) > 1:
                raise ValueError(f"pin {list(pin)} selects {len(labels)} islands ({', '.join(labels[:3])}); "
                                 "a pin places exactly one island: select a single face or element")
        return items, targets, region, layouts

    @staticmethod
    def _split_cube(elem):
        """A cube whose faces are placed one by one: no box UV, faces in canonical order."""
        elem["box_uv"], elem["autouv"], elem["uv_offset"] = False, 0, [0, 0]
        faces = elem.setdefault("faces", {})
        for name in ("north", "south", "east", "west", "up", "down"):
            if faces.get(name, {}).get("texture", False) is not None:
                faces.setdefault(name, {})

    @staticmethod
    def _write_face(elem, face_name, rect, corners, texture=False):
        """Write one face into its island rectangle [u, v, u2, v2]."""
        u, v, u2, v2 = rect
        if elem.get("type", "cube") == "cube":
            face = elem.setdefault("faces", {}).setdefault(face_name, {})
            face["uv"] = [u, v, u2, v2]
        else:
            face = elem["faces"][face_name]
            face.pop("model_as_code_chart", None)
            face.pop("model_as_code_mirror", None)
            if corners is None:
                face["uv"] = dict(zip(face["vertices"], [[u, v], [u2, v], [u2, v2], [u, v2]]))
            else:
                face["uv"] = {key: [u + xy[0], v + xy[1]] for key, xy in corners.items()}
        face["rotation"], face["texture"] = 0, texture

    @classmethod
    def load_from_bbmodel(cls, filepath: str | Path):
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        options = data.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {})
        items, _ = cls._document_items(data, options.get("uv_scale", DEFAULT_UV_SCALE), options.get('require_integer_uvs', True))
        return items, data

    @classmethod
    def pack(
        cls,
        items: List[BoxUVItem],
        start_size: int | Sequence[int] = 32,
        max_size: int = 1024,
        allow_rectangular: bool = False,
        packer: str = "maxrects",
    ) -> Tuple[AtlasSize, List[BoxUVItem], Dict[str, Any]]:
        """
        Packs all items into the smallest power-of-two atlas starting from start_size.
        Supports independent width and height progression (e.g. 128x64, 64x128).
        ``packer``: ``maxrects`` (tightest), ``shelf`` (rows in document order) or ``grouped`` (each block
        packed together, see ``BoxUVItem.block``). Items with a ``pin`` keep their position in every packer.
        Returns: (atlas_size, packed_items, stats_report)
        """
        if packer not in PACKERS:
            raise ValueError(f"packer must be one of {', '.join(PACKERS)}")
        pins = [(it, *_pinned_origin(it)) for it in items if it.pin is not None]
        for number, (a, au, av) in enumerate(pins):
            for b, bu, bv in pins[number + 1:]:
                if au < bu + b.width and bu < au + a.width and av < bv + b.height and bv < av + a.height:
                    raise ValueError(f"pinned islands overlap (padding included): {a.name} and {b.name}")
        total_occupied_area = sum(it.area for it in items)
        members = None
        if packer == "grouped":
            items, members = _group_blocks(items)
            packer = "maxrects"
        place = PACKERS[packer]

        if isinstance(start_size, int):
            s = max(16, 1 << (start_size - 1).bit_length() if start_size > 0 else 32)
            start_w = start_h = s
        else:
            start_w = max(16, 1 << (int(start_size[0]) - 1).bit_length() if start_size[0] > 0 else 32)
            start_h = max(16, 1 << (int(start_size[1]) - 1).bit_length() if start_size[1] > 0 else 32)

        candidates = []
        min_exp_w = int(math.log2(start_w))
        min_exp_h = int(math.log2(start_h))
        max_exp = int(math.log2(max_size))

        if not allow_rectangular and start_w == start_h:
            min_exp = max(min_exp_w, min_exp_h)
            for exp in range(min_exp, max_exp + 1):
                s = 1 << exp
                candidates.append((s, s))
        else:
            for a in range(min_exp_w, max_exp + 1):
                for b in range(min_exp_h, max_exp + 1):
                    w = 1 << a
                    h = 1 << b
                    ratio = w / h
                    if 0.5 <= ratio <= 2.0:
                        candidates.append((w, h))

            # Sort candidates by:
            # 1. Total area (w * h)
            # 2. Closeness to square
            # 3. Width preference (expand sideways first, then height)
            candidates.sort(key=lambda c: (c[0] * c[1], abs(c[0] - c[1]), -c[0]))

        for canvas_w, canvas_h in candidates:
            if total_occupied_area > canvas_w * canvas_h:
                continue

            if any(it.width > canvas_w or it.height > canvas_h for it in items):
                continue
            if any(_pinned_origin(it)[0] + it.width > canvas_w or _pinned_origin(it)[1] + it.height > canvas_h
                   for it in items if it.pin is not None):
                continue

            packed = place(items, canvas_w, canvas_h)
            if packed is not None:
                if members is not None:
                    packed = _unpack_blocks(packed, members)
                cls._verify_no_overlap(packed)

                efficiency = (total_occupied_area / (canvas_w * canvas_h)) * 100.0
                stats = {
                    "canvas_size": (canvas_w, canvas_h),
                    "element_count": len(packed),
                    "total_occupied_pixels": total_occupied_area,
                    "total_canvas_pixels": canvas_w * canvas_h,
                    "efficiency_percent": round(efficiency, 2),
                }
                return AtlasSize(canvas_w, canvas_h), packed, stats

        raise RuntimeError(
            f"Could not fit {len(items)} elements within maximum texture size {max_size}x{max_size}."
        )

    @staticmethod
    def _verify_no_overlap(items: List[BoxUVItem]) -> None:
        """Collision check verifying that no two items overlap in the atlas."""
        n = len(items)
        for i in range(n):
            a = items[i]
            for j in range(i + 1, n):
                b = items[j]
                overlap = not (
                    a.u + a.width <= b.u
                    or b.u + b.width <= a.u
                    or a.v + a.height <= b.v
                    or b.v + b.height <= a.v
                )
                if overlap:
                    raise AssertionError(
                        f"UV Overlap detected between '{a.name}' at ({a.u}, {a.v}, {a.width}x{a.height}) "
                        f"and '{b.name}' at ({b.u}, {b.v}, {b.width}x{b.height})"
                    )

    @classmethod
    def pack_document(cls, source, *, start_size=None, allow_rectangular=None,
                      uv_scale=None, max_size=None, fixed_texture_size=None,
                      island_padding=None, require_integer_uvs=None, layout=None, packer=None):
        """Pure UV stage: return a mapped copy without touching files or geometry.

        ``layout``: ``faces`` (one island per face) or ``charts`` (neighbouring mesh faces unfolded together on
        one continuous texel grid, see ``Tools.uv_charts``; implies fractional UVs). ``packer``: ``maxrects``,
        ``shelf`` or ``grouped`` (see ``pack``). Rules saved in ``uv_packing.rules`` (``Tools.uv_rules``) choose
        density, layout and texture slot per region; without rules every face takes these defaults."""
        data = copy.deepcopy(source)
        model_format = data.get("meta", {}).get("model_format", "free")
        if model_format not in {"free", "hytale_character"}:
            raise ValueError(f"Code UV remapping does not support model format {model_format!r}")
        saved = data.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {})
        uv_layout = layout if layout is not None else saved.get("layout", "faces")
        if uv_layout not in ("faces", "charts"):
            raise ValueError("layout must be 'faces' or 'charts'")
        if uv_layout == "charts":
            if require_integer_uvs:
                raise ValueError("the charts layout unfolds faces with exact sizes: it needs --no-require-integer-uvs")
            require_integer_uvs = False
        require_integer_uvs = require_integer_uvs if require_integer_uvs is not None else saved.get('require_integer_uvs', True)
        if not isinstance(require_integer_uvs, bool):
            raise ValueError('require_integer_uvs must be a boolean')
        start_size = start_size if start_size is not None else saved.get("start_size", 32)
        allow_rectangular = allow_rectangular if allow_rectangular is not None else saved.get("allow_rectangular", True)
        uv_scale = validate_uv_scale(uv_scale if uv_scale is not None else saved.get("uv_scale", DEFAULT_UV_SCALE))
        max_size = max_size if max_size is not None else saved.get("max_size", 1024)
        fixed_texture_size = fixed_texture_size if fixed_texture_size is not None else saved.get("fixed_texture_size", False)
        island_padding = validate_island_padding(
            island_padding if island_padding is not None else saved.get("island_padding", 0))
        dims = [start_size, start_size] if isinstance(start_size, int) else list(start_size)
        if len(dims) != 2 or any(not isinstance(v, int) or v <= 0 for v in dims):
            raise ValueError("start_size must be a positive integer or width/height pair")
        if not isinstance(max_size, int) or max_size < max(dims) or max_size > 16384:
            raise ValueError("max_size must cover start_size and be at most 16384")
        packer = packer if packer is not None else saved.get("packer", "maxrects")
        if packer not in PACKERS:
            raise ValueError(f"packer must be one of {', '.join(PACKERS)}")
        from .uv_rules import ordered_textures, resolve_specs, validate_rules
        rules = validate_rules(saved.get("rules"))
        has_texture_rules = any("texture" in r for r in rules)
        declared = data.get("unhandled_root_fields", {}).get("model_as_code", {})
        sharing = declared.get("uv_sharing")
        if isinstance(sharing, list) and any(isinstance(link, dict) and link.get("region") for link in sharing):
            # Region links are derived from the rules on every packing: only share_uv declarations are kept.
            declared["uv_sharing"] = [link for link in sharing if not (isinstance(link, dict) and link.get("region"))]
        from .uv_contract import validate_sharing
        region, layouts = [], None
        # Islands: (packable item, target) pairs; the target says how the placed island is written back.
        if rules:
            specs = resolve_specs(data, rules, uv_scale=uv_scale, layout=uv_layout)
            slot_names = ordered_textures(specs, rules)
            links = validate_sharing(data, uv_scale, require_integer_uvs)
            items, targets, region, layouts = cls._rule_items(data, specs, links, uv_scale, require_integer_uvs)
            crosses = {target[1] for target in targets.values() if target[0] == "box"}
            for index, elem in enumerate(data.get("elements", [])):
                if elem.get("type", "cube") == "cube" and index not in crosses:
                    cls._split_cube(elem)
        else:
            slot_names = ["default"]
            items, targets = cls._document_items(data, uv_scale, require_integer_uvs, uv_layout)
            links = validate_sharing(data, uv_scale, require_integer_uvs)
            if links and uv_layout == "charts":
                raise ValueError("explicit UV sharing (share_uv) is not supported with the charts layout")
            if links:
                # Sharing places single faces, so cubes leave the box-UV cross for one island per face.
                items, targets = cls._shared_items(data, links, uv_scale, require_integer_uvs)
                for elem in data.get("elements", []):
                    if elem.get("type", "cube") == "cube":
                        cls._split_cube(elem)
        for item in items:
            item.padding = island_padding
        if not has_texture_rules and len(slot_names) == 1:
            size, packed, stats = cls.pack(items, start_size=dims, max_size=max_size,
                                           allow_rectangular=allow_rectangular, packer=packer)
            if fixed_texture_size and (size.width > dims[0] or size.height > dims[1]):
                raise ValueError(f"Packed UV size {size.width}x{size.height} exceeds fixed texture size {dims}")
            slot_index = None
            textures_meta = None
        else:
            slot_index = {name: idx for idx, name in enumerate(slot_names)}
            packed, textures_meta = [], []
            total_occupied = total_canvas = 0
            first_size = None
            for slot_name in slot_names:
                slot_items = [it for it in items if it.texture == slot_name]
                slot_size, slot_packed, slot_stats = cls.pack(
                    slot_items, start_size=dims, max_size=max_size,
                    allow_rectangular=allow_rectangular, packer=packer)
                if fixed_texture_size and (slot_size.width > dims[0] or slot_size.height > dims[1]):
                    raise ValueError(
                        f"Packed UV size {slot_size.width}x{slot_size.height} for texture {slot_name!r} "
                        f"exceeds fixed texture size {dims}")
                if first_size is None:
                    first_size = slot_size
                packed.extend(slot_packed)
                textures_meta.append({"name": slot_name, "width": slot_size.width, "height": slot_size.height})
                total_occupied += slot_stats["total_occupied_pixels"]
                total_canvas += slot_stats["total_canvas_pixels"]
            size = first_size or AtlasSize(dims[0], dims[1])
            efficiency = (total_occupied / total_canvas * 100.0) if total_canvas else 0.0
            stats = {
                "canvas_size": (size.width, size.height),
                "element_count": len(packed),
                "total_occupied_pixels": total_occupied,
                "total_canvas_pixels": total_canvas,
                "efficiency_percent": round(efficiency, 2),
                "textures": textures_meta,
            }
        cls._write_islands(data, packed, targets, slot_index=slot_index)
        if links:
            cls._write_followers(data, links, uv_scale, require_integer_uvs)
        data.setdefault("meta", {})["box_uv"] = False
        data["resolution"] = {"width": size.width, "height": size.height}
        data["textures"] = []
        metadata = data.setdefault("unhandled_root_fields", {}).setdefault("model_as_code", {})
        if region:
            metadata["uv_sharing"] = list(metadata.get("uv_sharing") or []) + region
        metadata["uv_packing"] = dict(start_size=dims, allow_rectangular=allow_rectangular,
                                      uv_scale=uv_scale, max_size=max_size,
                                      fixed_texture_size=fixed_texture_size,
                                      island_padding=island_padding, require_integer_uvs=require_integer_uvs,
                                      layout=uv_layout)
        if packer != "maxrects":
            metadata["uv_packing"]["packer"] = packer
        if rules:
            metadata["uv_packing"]["rules"] = rules
        if textures_meta is not None:
            metadata["uv_packing"]["textures"] = textures_meta
        stats["uv_scale"] = uv_scale
        stats["island_padding"] = island_padding
        if packer != "maxrects":
            stats["packer"] = packer
        if layouts is not None:
            stats["texels_by_layout"] = layouts
        metadata['uv_ready'] = True
        cls._validate_written_uvs(data, size, {**links, **{tuple(r["target"]): tuple(r["source"]) for r in region}})
        return data, size, stats

    @classmethod
    def _write_islands(cls, data, packed, targets, slot_index=None):
        """Write every placed island back into its faces."""
        for item in packed:
            target = targets[item.uuid]
            kind, elem = target[0], data["elements"][target[1]]
            tex_val = slot_index[item.texture] if slot_index is not None else False
            if kind == "chart":
                _, _, faces_layout, chart_id, sources = target
                u0, v0 = item.u + item.padding, item.v + item.padding
                for face_name, corners in faces_layout.items():
                    face = elem["faces"][face_name]
                    face["uv"] = {key: [u0 + xy[0], v0 + xy[1]] for key, xy in corners.items()}
                    face["rotation"], face["texture"] = 0, tex_val
                    face["model_as_code_chart"] = chart_id
                    if face_name in sources:
                        face["model_as_code_mirror"] = sources[face_name]
                    else:
                        face.pop("model_as_code_mirror", None)
            elif kind == "box":
                old_faces = elem.get("faces", {})
                elem["box_uv"], elem["autouv"] = False, 0
                elem["uv_offset"] = [item.u + item.padding, item.v + item.padding]
                elem["faces"] = {}
                for name, uv in item.get_face_uvs().items():
                    face = copy.deepcopy(old_faces.get(name, {}))
                    disabled = "texture" in face and face["texture"] is None
                    face.update(uv=uv, rotation=0, texture=None if disabled else tex_val)
                    elem["faces"][name] = face
            else:
                _, _, face_name, corners, followers = target
                rect = item.get_face_uvs()["quad"]
                for index, name, layout in [(target[1], face_name, corners)] + followers:
                    cls._write_face(data["elements"][index], name, rect, layout, texture=tex_val)

    @classmethod
    def _write_followers(cls, data, links, uv_scale, require_integer_uvs):
        """Followers use the owner's exact coordinates, including tolerated float noise."""
        from .uv_contract import validate_sharing
        mirrors = {}
        validate_sharing(data, uv_scale, require_integer_uvs, mirrors=mirrors)
        by_name = {element['name']: element for element in data['elements']}
        for target, source in links.items():
            follower = by_name[target[0]]['faces'][target[1]]
            owner = by_name[source[0]]['faces'][source[1]]
            if target in mirrors:
                follower['uv'] = cls._mirrored_uv(follower, owner, mirrors[target])
            elif isinstance(owner['uv'], dict) and isinstance(follower['uv'], dict):
                follower['uv'] = {a: list(owner['uv'][b]) for a, b in
                                  zip(follower['vertices'], owner['vertices'])}

    @staticmethod
    def _mirrored_uv(follower, owner, mapping):
        """Owner coordinates reached through the mirror correspondence."""
        uv = owner['uv']
        points = uv if isinstance(uv, dict) else dict(enumerate(
            ([uv[0], uv[1]], [uv[2], uv[1]], [uv[2], uv[3]], [uv[0], uv[3]])))
        if isinstance(follower['uv'], dict):
            return {key: list(points[mapping[key]]) for key in follower['vertices']}
        # A cube face keeps the rectangle form: the corner its index 0 reuses
        # becomes the rectangle's first point.
        (u1, v1), (u2, v2) = points[mapping[0]], points[mapping[2]]
        return [u1, v1, u2, v2]

    @staticmethod
    def _validate_written_uvs(data, size, links):
        """Validate final integer UV bounds and owner-region exclusivity."""
        if not data['unhandled_root_fields']['model_as_code']['uv_packing'].get('require_integer_uvs', True):
            from Tools.TexturePainter.core.bbmodel_parser import BlockbenchModelParser
            BlockbenchModelParser.from_document(data)
            return
        textures_meta = data.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {}).get("textures")
        occupied = {}
        for elem in data.get("elements", []):
            for face_name, face in elem.get("faces", {}).items():
                if face.get("texture", False) is None:
                    continue
                ref = (elem.get("name"), face_name)
                owner = links.get(ref, ref)
                tex_idx = face.get("texture", False)
                slot = 0 if tex_idx is False else int(tex_idx)
                if textures_meta and 0 <= slot < len(textures_meta):
                    limit_w, limit_h = textures_meta[slot]["width"], textures_meta[slot]["height"]
                else:
                    limit_w, limit_h = size.width, size.height
                uv = face.get("uv")
                coords = list(uv.values()) if isinstance(uv, dict) else (
                    [[uv[0], uv[1]], [uv[2], uv[1]], [uv[2], uv[3]], [uv[0], uv[3]]]
                    if isinstance(uv, list) and len(uv) == 4 else [])
                if len(coords) not in (3, 4) or any(len(p) != 2 or any(int(v) != v for v in p) for p in coords):
                    raise ValueError(f"{ref}: invalid final UV coordinates")
                area2 = sum(coords[index][0] * coords[(index + 1) % len(coords)][1] -
                            coords[(index + 1) % len(coords)][0] * coords[index][1]
                            for index in range(len(coords)))
                if len({tuple(point) for point in coords}) != len(coords) or area2 == 0:
                    raise ValueError(f"{ref}: degenerate final polygon UV")
                xs, ys = [int(p[0]) for p in coords], [int(p[1]) for p in coords]
                if min(xs) < 0 or min(ys) < 0 or max(xs) > limit_w or max(ys) > limit_h:
                    raise ValueError(f"{ref}: final UV outside atlas bounds")
                bounds = (min(xs), min(ys), max(xs), max(ys))
                slot_occupied = occupied.setdefault(slot, {})
                for prior_owner, prior_bounds in slot_occupied.items():
                    overlap = (min(bounds[2], prior_bounds[2]) > max(bounds[0], prior_bounds[0]) and
                               min(bounds[3], prior_bounds[3]) > max(bounds[1], prior_bounds[1]))
                    if overlap and prior_owner != owner:
                        raise ValueError(f"{ref}: final UV overlaps owner {prior_owner}")
                slot_occupied[owner] = bounds

    _REMEMBERED = ("start_size", "allow_rectangular", "uv_scale", "max_size", "fixed_texture_size",
                   "island_padding", "require_integer_uvs", "layout", "packer")

    @classmethod
    def remembered_options(cls, bbmodel_path):
        """Read packing options exclusively from the current BBModel."""
        try:
            document = json.loads(Path(bbmodel_path).read_text(encoding="utf-8"))
            data = document.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_packing", {})
        except (OSError, ValueError):
            return {}
        return {key: data[key] for key in cls._REMEMBERED if key in data}

    @classmethod
    def apply_to_bbmodel(cls, bbmodel_path, output_path=None, start_size=None,
                         allow_rectangular=None, *, uv_scale=None, max_size=None,
                         fixed_texture_size=None, island_padding=None, require_integer_uvs=None, layout=None, packer=None,
                         backup=True):
        """Remap the current file, never execute a modeling recipe or paint a PNG."""
        path = Path(bbmodel_path)
        original = path.read_bytes()
        source = json.loads(original)
        data, size, stats = cls.pack_document(
            source, start_size=start_size, allow_rectangular=allow_rectangular,
            uv_scale=uv_scale, max_size=max_size, fixed_texture_size=fixed_texture_size,
            island_padding=island_padding, require_integer_uvs=require_integer_uvs, layout=layout, packer=packer)
        target = Path(output_path) if output_path else path
        if path.read_bytes() != original:
            raise ValueError("BBModel changed during UV packing; retry with the current document")
        cls.write_document(data, target, backup=backup)
        return size, stats

    @staticmethod
    def write_document(data, target, backup=True):
        target = Path(target)
        if target.suffix.lower() != ".bbmodel":
            raise ValueError("UV output must use the .bbmodel extension")
        target.parent.mkdir(parents=True, exist_ok=True)
        if backup and target.exists():
            shutil.copy2(target, str(target) + ".bak")
        fd, temporary = tempfile.mkstemp(dir=target.parent, suffix=".bbmodel")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
            _replace_file(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def uv_recipe(target):
    """The asset's own ``generate_uv.py`` when it exists (a twin's, not its source's), else None."""
    from Tools._resolve import resolve_asset
    recipe = resolve_asset(target).scripts / "generate_uv.py"
    return recipe if recipe.exists() else None


def run_uv_recipe(target, *, dry_run=False):
    """Run the asset's UV recipe (it reads the current BBModel through ``UVBuilder`` and writes its UVs)."""
    import subprocess
    from Tools.recipe_context import recipe_environment
    recipe = uv_recipe(target)
    if recipe is None:
        return {"status": "fail", "error": "the asset has no generate_uv.py"}
    env = recipe_environment(target, register_texture=False)
    env["FORGE_UV_DRY_RUN"] = "1" if dry_run else "0"
    run = subprocess.run([sys.executable, str(recipe)], cwd=REPO_ROOT, env=env, capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    output = (run.stdout or "").strip()
    if run.returncode:
        lines = [line for line in (run.stderr or run.stdout or "").strip().splitlines() if line.strip()]
        return {"status": "fail", "recipe": str(recipe),
                "error": "\n".join(lines[-12:]) or f"recipe exited with code {run.returncode}"}
    return {"status": "dry-run" if dry_run else "pass", "recipe": str(recipe), "output": output}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Remap UVs in code from current .bbmodel geometry; never paint. "
                                                 "An asset with scripts/<asset>/generate_uv.py runs that recipe instead")
    parser.add_argument("bbmodel", help="Current model, including manual geometry edits")
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--out", "-o", help="Save a remapped copy to a different path instead of in-place")
    destination.add_argument("--dry-run", action="store_true", help="Preview packing result without writing any files")
    parser.add_argument("--json", action="store_true", help="Print the packing result as JSON")
    parser.add_argument("--start-size", type=int, help="Minimum square atlas size (otherwise reuse saved options)")
    parser.add_argument("--allow-rectangular", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--uv-scale", type=int, help="Global pixels per model unit: positive integer; explicit value > saved value > default 1. Does not edit the model recipe")
    parser.add_argument("--max-size", type=int, help="Maximum atlas side length")
    parser.add_argument("--fixed-texture-size", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--island-padding", type=int, help="Reserved pixels around each packed island; default reuses the saved value, else 1 (aligning with texture_export)")
    parser.add_argument('--require-integer-uvs', action=argparse.BooleanOptionalAction, default=None,
                        help='Require integer vertices, or allow fractions with half-pixel-aligned island centers')
    parser.add_argument('--layout', choices=('faces', 'charts'),
                        help='faces: one island per face; charts: neighbouring mesh faces unfolded together on one '
                             'continuous texel grid (pixel art across edges; implies fractional UVs). '
                             'Default reuses the saved value, else faces')
    parser.add_argument('--packer', choices=tuple(PACKERS),
                        help='maxrects: tightest atlas; shelf: rows in document order; grouped: islands of one '
                             'block (UV rule block, else parent group) kept together. Default reuses the saved value')
    parser.add_argument('--no-recipe', action='store_true',
                        help="Ignore the asset's generate_uv.py and pack with the saved options and rules")
    args = parser.parse_args(argv)
    _, model_path = resolve_model_target(args.bbmodel)
    recipe = uv_recipe(args.bbmodel)
    if recipe is not None and not args.no_recipe:
        flags = [name for name in ("out", "start_size", "allow_rectangular", "uv_scale", "max_size",
                                   "fixed_texture_size", "island_padding", "require_integer_uvs", "layout", "packer")
                 if getattr(args, name) is not None]
        if flags:
            print(f"[uv] FAIL {recipe.name} sets the packing; edit it, or pass --no-recipe to use "
                  f"--{flags[0].replace('_', '-')}", file=sys.stderr)
            raise SystemExit(1)
        report = run_uv_recipe(args.bbmodel, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(report))
        elif report["status"] == "fail":
            print(f"[uv] FAIL {report['error']}", file=sys.stderr)
        else:
            print(report["output"] or f"[uv] PASS {recipe.name}")
        if report["status"] == "fail":
            raise SystemExit(1)
        return
    saved = BoxUVPacker.remembered_options(model_path)
    cli_island_padding = args.island_padding
    if cli_island_padding is None and "island_padding" not in saved:
        cli_island_padding = 1
    options = dict(start_size=args.start_size, allow_rectangular=args.allow_rectangular,
                   uv_scale=args.uv_scale, max_size=args.max_size,
                   fixed_texture_size=args.fixed_texture_size, island_padding=cli_island_padding,
                   require_integer_uvs=args.require_integer_uvs, layout=args.layout, packer=args.packer)
    try:
        if args.dry_run:
            source = json.loads(model_path.read_text(encoding="utf-8"))
            _, size, stats = BoxUVPacker.pack_document(source, **options)
            print(json.dumps({"status": "dry-run", "width": size.width, "height": size.height, **stats}) if args.json else f"[uv] DRY-RUN atlas={size.width}x{size.height} {stats['uv_scale']} px/unit islands={stats['element_count']} efficiency={stats['efficiency_percent']}%")
            if not args.json:
                print("Dry run: no files changed. Remove --dry-run to apply.")
        else:
            size, stats = BoxUVPacker.apply_to_bbmodel(str(model_path), args.out, **options)
            print(json.dumps({"status": "pass", "width": size.width, "height": size.height, **stats}) if args.json else f"[uv] PASS atlas={size.width}x{size.height} {stats['uv_scale']} px/unit islands={stats['element_count']} efficiency={stats['efficiency_percent']}%")
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}) if args.json else f"[uv] FAIL {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
