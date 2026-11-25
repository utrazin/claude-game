import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from lib import ModelBuilder
from lib.geometry_types import MeshFace, MeshGeometry
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.core.polygon_face_canvas import polygon_mask
from Tools.TexturePainter.ink import boundary, line, stroke, vertices
from Tools.uv_builder import UVBuilder

SCALE = 8


def plate_model(path, columns=6, rows=3, cell=2.0):
    """A flat plate of quads facing +z; the left half is face group 'a', the right half 'b'."""
    verts, faces = {}, {}
    for i in range(columns + 1):
        for j in range(rows + 1):
            verts[f"v{i}_{j}"] = (i * cell, j * cell, 0)
    for i in range(columns):
        for j in range(rows):
            faces[f"q{i}_{j}"] = MeshFace((f"v{i}_{j}", f"v{i + 1}_{j}", f"v{i + 1}_{j + 1}", f"v{i}_{j + 1}"),
                                          "a" if i < columns // 2 else "b")
    builder = ModelBuilder("plate", require_integer_dimensions=False).add_group("root")
    builder.add_mesh("plate", "root", MeshGeometry.create(verts, faces))
    builder.export_bbmodel(path)


def charts(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out = {}
    for elem in data["elements"]:
        for name, face in elem.get("faces", {}).items():
            out[(elem["name"], name)] = face.get("model_as_code_chart")
    return data, out


class ChartLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.bbmodel"

    def pack(self, **options):
        UVBuilder(self.model, start_size=(128, 128), uv_scale=SCALE, island_padding=1, layout="charts",
                  require_integer_uvs=False, **options).save()
        return charts(self.model)

    def test_a_flat_plate_is_one_chart_with_shared_edges_and_exact_sizes(self):
        plate_model(self.model)
        data, chart_of = self.pack()
        self.assertEqual(len(set(chart_of.values())), 1)
        elem = data["elements"][0]
        uv_of = {}
        for name, face in elem["faces"].items():
            order = face["vertices"]
            for a, b in zip(order, order[1:] + order[:1]):     # every edge keeps its true length in texels
                length3 = np.linalg.norm(np.subtract(elem["vertices"][a], elem["vertices"][b])) * SCALE
                length2 = np.linalg.norm(np.subtract(face["uv"][a], face["uv"][b]))
                self.assertAlmostEqual(length2, length3, places=6)
            for vertex, uv in face["uv"].items():             # a shared vertex has one UV in the whole chart
                uv_of.setdefault(vertex, []).append(tuple(uv))
        self.assertTrue(all(len(set(values)) == 1 for values in uv_of.values()))
        self.assertEqual(data["unhandled_root_fields"]["model_as_code"]["uv_packing"]["layout"], "charts")

    def test_up_points_up_in_the_texture(self):
        plate_model(self.model)
        data, _ = self.pack()
        elem = data["elements"][0]
        low, high = elem["faces"]["q0_0"]["uv"]["v0_0"], elem["faces"]["q0_0"]["uv"]["v0_1"]
        self.assertAlmostEqual(low[0], high[0], places=6)      # model +y is a texture column
        self.assertGreater(low[1], high[1])                     # and points to smaller v (up in the image)

    def test_every_touched_texel_has_exactly_one_owner(self):
        plate_model(self.model)
        self.pack()
        painter = TexturePainter.from_bbmodel(self.model)
        claimed = painter.parser.claimed
        touched = np.zeros_like(claimed)
        data = json.loads(self.model.read_text(encoding="utf-8"))
        for face in data["elements"][0]["faces"].values():
            coords = np.array([face["uv"][k] for k in face["vertices"]])
            x0, y0 = np.floor(coords.min(axis=0)).astype(int)
            x1, y1 = np.ceil(coords.max(axis=0)).astype(int)
            mask = np.asarray(polygon_mask(x1 - x0, y1 - y0, (coords - (x0, y0)).tolist(), True)) > 0
            touched[y0:y1, x0:x1] |= mask
        self.assertTrue(np.array_equal(touched, claimed))
        painter.fill_all((200, 10, 10, 255))
        atlas = np.asarray(painter.compose_atlas(edge_dilation=1))
        self.assertTrue((atlas[claimed][:, 0] == 200).all())
        grown = (atlas[..., 3] > 0) & ~claimed                 # dilation only fills the padding ring
        ys, xs = np.nonzero(grown)
        for y, x in zip(ys, xs):
            self.assertTrue(claimed[max(0, y - 1):y + 2, max(0, x - 1):x + 2].any())

    def test_hard_folds_and_twist_split_charts(self):
        builder = ModelBuilder("tube", require_integer_dimensions=False).add_group("root")
        builder.add_cylinder("tube", "root", radius=2, height=4, segments=12)
        builder.export_bbmodel(self.model)
        data, chart_of = self.pack()
        faces = data["elements"][0]["faces"]
        caps = {chart_of[("tube", n)] for n, f in faces.items() if "cap" in (f.get("model_as_code_group") or n)}
        sides = {chart_of[("tube", n)] for n, f in faces.items() if "cap" not in (f.get("model_as_code_group") or n)}
        self.assertFalse(caps & sides)                         # a 90 degree fold is a chart seam

    def test_faces_layout_stays_the_default(self):
        plate_model(self.model)
        UVBuilder(self.model, start_size=(128, 128), uv_scale=SCALE, island_padding=1, require_integer_uvs=False).save()
        data, chart_of = charts(self.model)
        self.assertFalse(any(chart_of.values()))
        self.assertEqual(data["unhandled_root_fields"]["model_as_code"]["uv_packing"]["layout"], "faces")
        with self.assertRaisesRegex(ValueError, "no-require-integer-uvs"):
            UVBuilder(self.model, layout="charts", require_integer_uvs=True).save()


class SurfacePathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.bbmodel"
        plate_model(self.model)
        UVBuilder(self.model, start_size=(128, 128), uv_scale=SCALE, island_padding=1, layout="charts",
                  require_integer_uvs=False).save()
        self.painter = TexturePainter.from_bbmodel(self.model)

    def painted(self):
        out = []
        for face, rows in self.painter.element("plate")._surface_region()._entries:
            rgba = face.canvas.read_pixels(rows.x, rows.y)
            keep = rgba[:, 3] > 0
            out.extend((tuple(p), face.uv_info.get("group")) for p in np.asarray(rows.model_position)[keep])
        return out

    def test_boundary_inside_puts_the_whole_width_on_one_group(self):
        self.painter.paint_strokes([stroke(boundary("plate", "a", "b"), width=2, color=(255, 0, 0, 255),
                                           groups="a", align="inside")]).require_nonempty()
        texels = self.painted()
        self.assertTrue(all(group == "a" for _, group in texels))
        columns = {math.floor(p[0] * SCALE) for p, _ in texels}
        self.assertEqual(columns, {6 * SCALE - 2, 6 * SCALE - 1})     # two texels left of the a|b edge at x = 6

    def test_vertices_path_follows_named_vertices(self):
        self.painter.paint_strokes([stroke(vertices("plate", ["v0_1", "v6_1"]), width=1, color=(0, 0, 255, 255))])
        rows = {math.floor(p[1] * SCALE) for p, _ in self.painted()}
        self.assertLessEqual(len(rows), 2)
        self.assertTrue(rows <= {2 * SCALE - 1, 2 * SCALE})            # on the row of vertices at y = 2

    def test_surface_paths_reject_unknown_geometry_and_mirror(self):
        with self.assertRaises(KeyError):
            self.painter.paint_strokes([stroke(vertices("plate", ["v0_0", "nope"]))])
        with self.assertRaises(ValueError):
            self.painter.paint_strokes([stroke(boundary("plate", "a", "zzz"))])
        with self.assertRaises(ValueError):
            stroke(boundary("plate", "a", "b"), mirror="y")


if __name__ == "__main__":
    unittest.main()
