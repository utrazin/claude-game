"""The vectorized painting engine must match the per-texel definitions bit for bit."""
import json
import math
import random
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from lib import ModelBuilder
from lib.geometry_types import MeshFace, MeshGeometry
from lib.geometry_validation import world_point
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.core.polygon_face_canvas import _conservative_pixel, polygon_mask
from Tools.TexturePainter.core.surface_sampling import (
    _canvas_to_atlas, _clip_polygon_rect, _clip_rows, _cube_point, _mesh_texel, _model_vector,
    _unit, python_sum)
from Tools.TexturePainter.painter import SharedFacePainter, _dilate_rgba
from Tools.uv_builder import UVBuilder


def reference_mask(width, height, points, conservative):
    mask = np.zeros((height, width), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            if conservative:
                inside = _conservative_pixel(list(points), x, y)
            else:
                inside, j = False, len(points) - 1
                for i in range(len(points)):
                    (xi, yi), (xj, yj) = points[i], points[j]
                    if (yi > y + 0.5) != (yj > y + 0.5) and x + 0.5 < (xj - xi) * (y + 0.5 - yi) / (yj - yi) + xi:
                        inside = not inside
                    j = i
            mask[y, x] = 255 if inside else 0
    return mask


def reference_dilate(image, distance):
    expanded = Image.new("RGBA", (image.width + 2 * distance, image.height + 2 * distance))
    expanded.paste(image, (distance, distance))
    for _ in range(distance):
        src, dst = expanded.copy().load(), expanded.load()
        additions = []
        for y in range(expanded.height):
            for x in range(expanded.width):
                if src[x, y][3]:
                    continue
                for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < expanded.width and 0 <= ny < expanded.height and src[nx, ny][3]:
                        additions.append((x, y, src[nx, ny]))
                        break
        for x, y, color in additions:
            dst[x, y] = color
    return expanded


class VectorizedPrimitiveTests(unittest.TestCase):
    def test_python_sum_matches_builtin_sum(self):
        rng = random.Random(4)
        for _ in range(200):
            count = rng.randint(1, 5)
            rows = [[rng.choice((0.0, -0.0, 1e-17, -3.0)) if rng.random() < 0.2 else rng.uniform(-1e3, 1e3)
                     for _ in range(count)] for _ in range(20)]
            expected = [sum(row) for row in rows]
            actual = python_sum([np.array([row[k] for row in rows]) for k in range(count)]).tolist()
            self.assertEqual([repr(v) for v in actual], [repr(v) for v in expected])

    def test_clip_rows_matches_scalar_clip(self):
        rng = random.Random(5)
        for _ in range(100):
            triangle = tuple((rng.uniform(0, 8), rng.uniform(0, 8)) for _ in range(3))
            centers = [(rng.randint(0, 7) + 0.5, rng.randint(0, 7) + 0.5) for _ in range(30)]
            uv = np.array(centers)
            xs, ys, counts = _clip_rows(triangle, uv[:, 0] - .5, uv[:, 1] - .5, uv[:, 0] + .5, uv[:, 1] + .5)
            for row, (cx, cy) in enumerate(centers):
                expected = _clip_polygon_rect(triangle, cx - .5, cy - .5, cx + .5, cy + .5)
                actual = tuple(zip(xs[row, :counts[row]].tolist(), ys[row, :counts[row]].tolist()))
                self.assertEqual(actual, expected)

    def test_polygon_masks_match_per_pixel_definition(self):
        rng = random.Random(6)
        for _ in range(300):
            width, height = rng.randint(1, 12), rng.randint(1, 12)
            points = [(rng.randint(0, width), rng.randint(0, height)) if rng.random() < 0.5 else
                      (round(rng.uniform(0, width), 3), round(rng.uniform(0, height), 3))
                      for _ in range(rng.choice((3, 4)))]
            for conservative in (False, True):
                np.testing.assert_array_equal(np.asarray(polygon_mask(width, height, points, conservative)),
                                              reference_mask(width, height, points, conservative))

    def test_dilation_matches_neighbor_order(self):
        rng = random.Random(7)
        for _ in range(60):
            image = Image.new("RGBA", (rng.randint(1, 9), rng.randint(1, 9)))
            for _ in range(rng.randint(0, 20)):
                image.putpixel((rng.randrange(image.width), rng.randrange(image.height)),
                               (rng.randrange(256), rng.randrange(256), rng.randrange(256), rng.randint(1, 255)))
            for distance in (1, 2):
                self.assertEqual(_dilate_rgba(image, distance).tobytes(), reference_dilate(image, distance).tobytes())


    def test_texel_touched_with_zero_area_samples_face_centroid(self):
        """A conservative face may own a texel it only touches at a corner: sample its centroid, don't raise."""
        element = type("Element", (), {"name": "flap"})()
        info = {"x": 0, "y": 0, "w": 4, "h": 4, "rotation": 0, "flip_x": False, "flip_y": False,
                "conservative": True}
        uv_points = [(1.0, 1.0), (3.0, 1.0), (1.0, 3.0)]
        points = [(0.0, 0.0, 0.0), (3.0, 0.0, 0.0), (0.0, 3.0, 0.0)]
        face_uv, point, normal, _, _, fraction, _ = _mesh_texel(
            element, "q1", info, 0, 0, uv_points, points, [(0, 1, 2)])
        self.assertEqual(tuple(face_uv), (0.5, 0.5))
        self.assertEqual(point, (1.0, 1.0, 0.0))
        self.assertEqual(normal, (0.0, 0.0, 9.0))
        self.assertEqual(fraction, 1.0)


class SurfaceSampleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def build(self, name, builder, **uv):
        model = self.root / f"{name}.bbmodel"
        builder.export_bbmodel(model)
        UVBuilder(model, **uv).save()
        return TexturePainter.from_bbmodel(model)

    def reference(self, painter, element, face_name, face, x, y):
        """Per-texel sample computed with the scalar helpers."""
        sampler = painter.surface_sampler
        item = sampler.elements[element]
        info = face.uv_info
        if item.kind == "cube":
            canvas = face.canvas
            point, normal = _cube_point(item, face_name, (x + .5) / canvas.width, (y + .5) / canvas.height)
            face_uv, fraction = _canvas_to_atlas(info, x, y), 1.0
        else:
            face_uv, point, normal, _, _, fraction, _ = _mesh_texel(
                item, face_name, info, x, y, *sampler._mesh_geometry(item, face_name))
        element_normal = _unit(normal, "n")
        low, high = sampler.bounds[element]
        return {
            "face_uv": tuple(face_uv), "element_position": tuple(point),
            "model_position": tuple(world_point(sampler.builder, item, point)),
            "element_normal": element_normal,
            "model_normal": _unit(_model_vector(sampler.builder, item, element_normal), "n"),
            "normalized_position": tuple(0.0 if abs(high[i] - low[i]) <= 1e-9 else (point[i] - low[i]) / (high[i] - low[i])
                                         for i in range(3)),
            "coverage_fraction": float(fraction),
        }

    def assert_samples_exact(self, painter):
        checked = 0
        for element in painter.all_elements():
            for face_name, face in element.faces.items():
                if isinstance(face, SharedFacePainter):
                    continue
                for sample in painter.surface_sampler.samples(element.name, face_name, face):
                    expected = self.reference(painter, element.name, face_name, face, *sample.pixel)
                    for field, value in expected.items():
                        self.assertEqual(getattr(sample, field), value, (element.name, face_name, sample.pixel, field))
                    checked += 1
        self.assertGreater(checked, 0)

    def test_cubes_in_rotated_groups(self):
        builder = (ModelBuilder("cubes").add_group("root")
                   .add_transform_group("tilt", "root", pivot=(1, 0, 0), rotation=(10, 22.5, -5))
                   .add_cube("body", "tilt", from_=(0, 0, 0), to_=(5, 3, 2), inflate=0.15)
                   .add_cube("arm", "root", from_=(5, 1, 0), to_=(7, 2, 1), rotation=(0, 0, 45), origin=(5, 1.5, .5))
                   .add_axis_quad("badge", "root", from_=(0, 0, -0.2), size=(2, 2), normal="-Z"))
        self.assert_samples_exact(self.build("cubes", builder, start_size=(64, 32), uv_scale=3, island_padding=1))

    def test_conservative_polygons_and_fractional_uvs(self):
        builder = ModelBuilder("poly", require_integer_dimensions=False).add_group("root")
        points = {"a": (0, 0, 0), "b": (4, 0, 1), "c": (3, 2.5, 0), "d": (1, 3, -0.5)}
        builder.add_mesh("leaf", "root", MeshGeometry.create(points, {"surface": MeshFace(("a", "b", "c", "d"))}))
        builder.add_mesh("tri", "root", MeshGeometry.create(points, {"surface": MeshFace(("a", "b", "c"))}), origin=(6, 0, 0),
                         allow_triangles=True)
        self.assert_samples_exact(self.build("poly", builder, start_size=(64, 32), uv_scale=5,
                                             island_padding=1, require_integer_uvs=False))

    def test_lazy_coverage_matches_scalar_texel(self):
        builder = ModelBuilder("poly", require_integer_dimensions=False).add_group("root")
        points = {"a": (0, 0, 0), "b": (4, 0, 0), "c": (3, 2, 0), "d": (1, 3, 0)}
        builder.add_mesh("leaf", "root", MeshGeometry.create(points, {"surface": MeshFace(("a", "b", "c", "d"))}))
        painter = self.build("cover", builder, start_size=(32, 16), uv_scale=4, island_padding=1)
        item = painter.surface_sampler.elements["leaf"]
        face = painter.leaf.faces["surface"]
        for sample in painter.surface_sampler.samples("leaf", "surface", face):
            _, _, _, uv, model_points, _, polygons = _mesh_texel(
                item, "surface", face.uv_info, *sample.pixel, *painter.surface_sampler._mesh_geometry(item, "surface"))
            self.assertEqual(sample.coverage_uv_polygon, tuple(uv))
            self.assertEqual(sample.coverage_model_points,
                             tuple(world_point(painter.surface_sampler.builder, item, p) for p in model_points))
            self.assertEqual(len(sample.coverage_model_polygons), len(polygons))


class ArrayPaintingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        model = Path(temp.name) / "model.bbmodel"
        (ModelBuilder("box").add_group("root").add_cube("body", "root", from_=(0, 0, 0), to_=(4, 4, 4))
         .export_bbmodel(model))
        UVBuilder(model, start_size=(64, 32), uv_scale=2).save()
        self.painter = TexturePainter.from_bbmodel(model)

    def test_paint_surface_arrays_matches_per_sample_callback(self):
        def color(position):
            return (int(position[0] * 30) % 256, int(position[1] * 30) % 256, 90, 255)

        self.painter.body.paint_surface(lambda s: color(s.model_position) if s.model_position[2] > 2 else None)
        expected = self.painter.compose_atlas().tobytes()
        self.painter.fill_all((0, 0, 0, 0))

        def arrays(rows):
            colors = np.array([color(p) for p in rows.model_position.tolist()], dtype=float)
            return colors, rows.model_position[:, 2] > 2

        self.painter.body.paint_surface_arrays(arrays)
        self.assertEqual(self.painter.compose_atlas().tobytes(), expected)

    def test_paint_surface_arrays_validates_colors(self):
        with self.assertRaisesRegex(ValueError, "shape"):
            self.painter.body.paint_surface_arrays(lambda rows: np.zeros((1, 3)))
        with self.assertRaisesRegex(ValueError, "0-255"):
            self.painter.body.paint_surface_arrays(lambda rows: np.full((len(rows), 4), 300.0))


if __name__ == "__main__":
    unittest.main()
