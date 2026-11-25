"""Small models that reproduce projection problems in about a second: a plate, a grazing ramp and a flared collar."""
import json
import math
from pathlib import Path

import numpy as np

from lib import ModelBuilder
from lib.geometry_types import MeshFace, MeshGeometry
from Tools.TexturePainter import TexturePainter
from Tools.uv_builder import UVBuilder

SCALE = 8


def build(path, name, verts, faces, scale=SCALE):
    """Write a one-mesh BBModel and pack it as charts at ``scale`` texels per unit."""
    builder = ModelBuilder(name, require_integer_dimensions=False).add_group("root")
    builder.add_mesh(name, "root", MeshGeometry.create(verts, faces))
    builder.export_bbmodel(path)
    UVBuilder(path, start_size=(128, 128), uv_scale=scale, island_padding=1, layout="charts",
              require_integer_uvs=False).save()
    return Path(path)


def ramp_model(path, scale=SCALE):
    """A wall facing +z (y 0..4) and a ramp leaving its top edge backwards and upwards, nearly parallel to the
    viewing direction (its normal faces the front by about 0.12, below the default normal_min of 0.15)."""
    verts = {"w0": (0, 0, 0), "w1": (6, 0, 0), "w2": (6, 4, 0), "w3": (0, 4, 0),
             "r2": (6, 5, -8), "r3": (0, 5, -8)}
    faces = {"wall": MeshFace(("w0", "w1", "w2", "w3"), "wall"),
             "ramp": MeshFace(("w3", "w2", "r2", "r3"), "ramp")}
    return build(path, "ramp", verts, faces, scale)


def collar_model(path, scale=SCALE, segments=8, arc=100.0):
    """A flared two-wall collar seen from the front: an outer wall and an inner wall (a thin sheet) that widen
    upwards, joined by a lip facing down. Groups: ``outer`` (faces the front), ``inner`` (faces the back) and
    ``lip`` (faces down). The shape is a front arc of ``arc`` degrees."""
    verts, faces = {}, {}
    thickness, height = 0.4, 3.0
    rings = {"ob": (4.0, 0.0), "ot": (5.5, height), "ib": (4.0 - thickness, 0.0), "it": (5.5 - thickness, height)}
    for tag, (radius, y) in rings.items():
        for i in range(segments + 1):
            angle = math.radians(-arc / 2 + arc * i / segments)
            verts[f"{tag}{i}"] = (radius * math.sin(angle), y, radius * math.cos(angle))
    for i in range(segments):
        faces[f"outer{i}"] = MeshFace((f"ob{i}", f"ob{i + 1}", f"ot{i + 1}", f"ot{i}"), "outer")
        faces[f"inner{i}"] = MeshFace((f"ib{i + 1}", f"ib{i}", f"it{i}", f"it{i + 1}"), "inner")
        faces[f"lip{i}"] = MeshFace((f"ob{i}", f"ib{i}", f"ib{i + 1}", f"ob{i + 1}"), "lip")
    return build(path, "collar", verts, faces, scale)


def region_normals(model, group, render="pixel"):
    """(count, mean model normal) of the texels of one face group, from the painter's own samples."""
    painter = TexturePainter.from_bbmodel(model, render=render)
    normals = []
    for face, rows in painter.element(painter.all_elements()[0].name)._surface_region()._entries:
        if face.uv_info.get("group") == group:
            normals.append(np.asarray(rows.model_normal))
    normals = np.concatenate(normals)
    return len(normals), normals.mean(axis=0)


def painted_by_group(painter, element):
    """{group: texels with alpha > 0} on one element."""
    out = {}
    for face, rows in painter.element(element)._surface_region()._entries:
        group = face.uv_info.get("group")
        out[group] = out.get(group, 0) + int((face.canvas.read_pixels(rows.x, rows.y)[:, 3] > 0).sum())
    return out


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sheets_model(path, scale=SCALE, gap=0.3):
    """Two parallel sheets facing +z, the front one ``gap`` units in front of the back one (a cloak over a robe).
    Groups: ``front`` and ``back``."""
    verts = {"b0": (0, 0, 0), "b1": (6, 0, 0), "b2": (6, 4, 0), "b3": (0, 4, 0),
             "f0": (0, 0, gap), "f1": (6, 0, gap), "f2": (6, 4, gap), "f3": (0, 4, gap)}
    faces = {"back": MeshFace(("b0", "b1", "b2", "b3"), "back"),
             "front": MeshFace(("f0", "f1", "f2", "f3"), "front")}
    return build(path, "sheets", verts, faces, scale)


def mirrored_pairs_differ(painter):
    """(texels whose mirror image has another colour, mirrored texels), from the UV charts' mirror table."""
    atlas = np.asarray(painter.compose_atlas()).astype(int)
    differ = total = 0
    for (elem, face), (_source, k, d) in painter.parser.chart_mirrors.items():
        info = painter.parser.elements[elem]["faces"][face]
        ys, xs = np.nonzero(info["owned_mask"])
        xs, ys = xs + info["x"], ys + info["y"]
        delta = np.abs(atlas[ys, xs] - atlas[ys - d, k - 1 - xs]).max(axis=1)
        total += len(delta)
        differ += int((delta > 0).sum())
    return differ, total
