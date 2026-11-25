import math
import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

from lib import ModelBuilder
from lib.geometry_types import MeshFace, MeshGeometry
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.ink import _distance_to_segments, arc, bezier, curve, line, stroke, style
from Tools.uv_builder import UVBuilder

TEXEL = 1 / 8          # uv_scale 8
COLUMNS, ROWS, CELL = 6, 3, 2.0
INK = (200, 30, 30, 255)


def plate_painter(directory, layout="charts"):
    """A flat 12 x 6 plate made of 18 separate 2 x 2 quad faces (each its own UV island), facing +z."""
    vertices, faces = {}, {}
    for i in range(COLUMNS + 1):
        for j in range(ROWS + 1):
            vertices[f"v{i}_{j}"] = (i * CELL, j * CELL, 0)
    for i in range(COLUMNS):
        for j in range(ROWS):
            faces[f"q{i}_{j}"] = MeshFace((f"v{i}_{j}", f"v{i + 1}_{j}", f"v{i + 1}_{j + 1}", f"v{i}_{j + 1}"), "plate")
    model = Path(directory) / "model.bbmodel"
    builder = ModelBuilder("ink-plate", require_integer_dimensions=False).add_group("root")
    builder.add_mesh("plate", "root", MeshGeometry.create(vertices, faces))
    builder.export_bbmodel(model)
    UVBuilder(model, start_size=(256, 256), uv_scale=8, island_padding=1, layout=layout,
              require_integer_uvs=layout == "faces").save()
    return TexturePainter.from_bbmodel(model)


def painted(painter, element="plate"):
    """Model positions (N, 3) and RGBA of every painted texel of an element."""
    positions, colors = [], []
    for face, rows in painter.element(element)._surface_region()._entries:
        rgba = face.canvas.read_pixels(rows.x, rows.y)
        keep = rgba[:, 3] > 0
        positions.append(np.asarray(rows.model_position)[keep])
        colors.append(rgba[keep])
    return np.concatenate(positions), np.concatenate(colors)


def interior(positions, colors, lo=1.0, hi=11.0):
    keep = (positions[:, 0] > lo) & (positions[:, 0] < hi)
    return positions[keep], colors[keep]


def grid(positions):
    """Integer texel coordinates on the plate's global grid."""
    return {(int(math.floor(x / TEXEL)), int(math.floor(y / TEXEL))) for x, y, _ in positions}


class InkPathTests(unittest.TestCase):
    def test_curves_stay_within_the_tolerance(self):
        tol = 0.1 * TEXEL
        arc_points = arc((0, 0), 3.0, 2.0, 0, 180).flatten(TEXEL)
        angles = np.arctan2(arc_points[:, 1] / 2.0, arc_points[:, 0] / 3.0)
        self.assertTrue(np.allclose((arc_points[:, 0] / 3.0) ** 2 + (arc_points[:, 1] / 2.0) ** 2, 1.0))
        mids = (arc_points[:-1] + arc_points[1:]) / 2
        sag = 1 - np.sqrt((mids[:, 0] / 3.0) ** 2 + (mids[:, 1] / 2.0) ** 2)
        self.assertLessEqual(float(sag.max()) * 3.0, tol * 1.5)
        self.assertAlmostEqual(float(angles[0]), 0.0)
        cubic = bezier((0, 0), (0, 4), (6, 4), (6, 0)).flatten(TEXEL)
        t = np.linspace(0, 1, 2001)[:, None]
        p = [np.array(v, float) for v in ((0, 0), (0, 4), (6, 4), (6, 0))]
        truth = (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t ** 2 * p[2] + t ** 3 * p[3]
        far = max(np.min(np.linalg.norm(truth - q, axis=1)) for q in cubic)
        self.assertLessEqual(far, tol * 1.5)
        self.assertTrue(np.allclose(cubic[0], (0, 0)) and np.allclose(cubic[-1], (6, 0)))

    def test_curve_passes_through_its_points_and_closes(self):
        pts = ((0, 0), (2, 3), (5, 3), (7, 0))
        flat = curve(pts).flatten(TEXEL)
        for q in pts:
            self.assertLess(np.min(np.linalg.norm(flat - q, axis=1)), 1e-9)
        ring = curve(((0, 0), (3, 0), (3, 3), (0, 3)), closed=True).flatten(TEXEL)
        self.assertTrue(np.allclose(ring[0], ring[-1]))
        straight = curve(pts, tension=1.0).flatten(TEXEL)
        control = np.asarray(pts, float)
        on_polygon = _distance_to_segments(straight, control[:-1], control[1:])
        self.assertLess(float(on_polygon.max()), 1e-9)      # tension 1 is the control polygon itself

    def test_validation(self):
        path = line(((0, 0), (1, 1)))
        with self.assertRaises(ValueError):
            stroke(path, width=0)
        with self.assertRaises(ValueError):
            stroke(path, soft=-1)
        with self.assertRaises(ValueError):
            stroke(path, mirror="w")
        with self.assertRaises(ValueError):
            stroke(path, blend="burn")
        with self.assertRaises(TypeError):
            stroke(((0, 0), (1, 1)))
        with self.assertRaises(ValueError):
            line(((0, 0),))
        with self.assertRaises(ValueError):
            bezier((0, 0), (1, 1))


class InkPaintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.painter = plate_painter(self.temp.name)

    def test_hard_width_is_constant_in_texels(self):
        y = 3.0 + TEXEL / 2                                 # centre of a texel row
        report = self.painter.paint_strokes([stroke(line(((0.5, y), (11.5, y))), width=3, color=INK, name="bar")])
        positions, _ = painted(self.painter)
        rows = {round(p[1] / TEXEL - 0.5) for p in positions}
        self.assertEqual(len(rows), 3)
        self.assertEqual(report.entries[0][0], "bar")
        self.assertEqual(report.total, len(positions))

    def test_thin_line_is_connected_across_faces_and_has_no_l_corners(self):
        for points in (((1, 0.7), (11, 5.3)), ((0.7, 1), (11.2, 1.6)), ((2, 0.5), (3.1, 5.5)),
                       ((1, 1), (11, 5))):
            painter = plate_painter(self.temp.name)
            painter.paint_strokes([stroke(line(points), width=1, color=INK)])
            texels, _ = painted(painter)
            cells = grid(texels)
            self.assertGreater(len(cells), 8)
            for (x, y) in cells:
                near = [(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                        if (dx or dy) and (x + dx, y + dy) in cells]
                self.assertTrue(near, f"isolated texel {(x, y)} on {points}")
                ortho = [n for n in near if n[0] == 0 or n[1] == 0]
                if len(near) == 2 and len(ortho) == 2 and ortho[0][0] != ortho[1][0] and ortho[0][1] != ortho[1][1]:
                    inner = (x + ortho[0][0] + ortho[1][0], y + ortho[0][1] + ortho[1][1])
                    self.assertIn(inner, cells, f"L corner at {(x, y)} on {points}")
            # no gap along the major axis, including at the 2-unit face borders
            (x0, y0), (x1, y1) = points
            major = 0 if abs(x1 - x0) >= abs(y1 - y0) else 1
            lo, hi = sorted((points[0][major], points[1][major]))
            bins = {c[major] for c in cells}
            for k in range(int(lo / TEXEL) + 1, int(hi / TEXEL)):
                self.assertIn(k, bins, f"gap at texel {k} on {points}")

    def test_pixel_width_is_constant_along_shallow_and_steep_lines(self):
        for width in (2, 3):
            for points, major in ((((1.0, 1.3), (11.0, 2.7)), 0), (((1.0, 0.7), (11.0, 3.4)), 0),
                                  (((3.0, 0.8), (4.4, 5.2)), 1), (((6.0, 0.6), (6.9, 5.4)), 1)):
                painter = plate_painter(self.temp.name)
                painter.paint_strokes([stroke(line(points), width=width, color=INK)])
                positions, _ = painted(painter)
                cells = grid(positions)
                lo, hi = sorted((points[0][major], points[1][major]))
                minor = 1 - major
                spans = {}
                for cell in cells:
                    spans.setdefault(cell[major], []).append(cell[minor])
                edges = []
                for k in range(int(lo / TEXEL) + 2, int(hi / TEXEL) - 1):
                    run = sorted(spans.get(k, []))
                    # square brush on a pixel-perfect chain: one contiguous run of width or width + 1 texels
                    self.assertTrue(run and run == list(range(run[0], run[-1] + 1)), (width, points, k, run))
                    self.assertIn(len(run), (width, width + 1), (width, points, k, run))
                    edges.append((run[0], run[-1]))
                for side in (0, 1):                  # both band edges are monotonic staircases (no bumps)
                    steps = [b[side] - a[side] for a, b in zip(edges, edges[1:])]
                    self.assertTrue(all(s >= 0 for s in steps) or all(s <= 0 for s in steps), (width, points, side))

    def test_diagonal_lines_are_solid_and_the_outline_surrounds_them_without_gaps(self):
        for points in (((1, 1), (9, 5)), ((2, 0.6), (8, 5.4)), ((1, 4), (9, 1))):
            painter = plate_painter(self.temp.name)
            painter.paint_strokes([stroke(line(points), width=2, color=INK, outline=(10, 10, 10, 255))])
            positions, colors = painted(painter)
            fill = {c for c, col in zip(map(lambda p: (int(math.floor(p[0] / TEXEL)), int(math.floor(p[1] / TEXEL))),
                                            positions), colors) if col[0] == INK[0]}
            edge = {c for c, col in zip(map(lambda p: (int(math.floor(p[0] / TEXEL)), int(math.floor(p[1] / TEXEL))),
                                            positions), colors) if col[0] == 10}
            self.assertGreater(len(fill), 20)
            for (x, y) in fill:                       # every neighbour of the fill is fill or outline (no leaks)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):    # pixel-art outline: across edges
                    cell = (x + dx, y + dy)
                    if 1.0 < (x * TEXEL) < 11.0 and 0.5 < (y * TEXEL) < 5.5:
                        self.assertTrue(cell in fill or cell in edge, (points, (x, y), cell))
            for (x, y) in edge:                       # and every outline texel touches the fill
                self.assertTrue(any((x + dx, y + dy) in fill for dx in (-1, 0, 1) for dy in (-1, 0, 1)))

    def test_styles_are_declared_once_and_reused(self):
        thick = style(width=2, color=INK, on="plate")
        fine = thick.but(width=1)
        s = thick(line(((1, 3), (5, 3))), name="a")
        self.assertEqual((s.width, s.color, s.on, s.name), (2.0, INK, ("plate",), "a"))
        self.assertEqual(fine(line(((1, 3), (5, 3)))).width, 1.0)
        self.assertEqual(thick(line(((1, 3), (5, 3))), width=3).width, 3.0)
        with self.assertRaises(TypeError):
            style(wdith=2)
        with self.assertRaises(ValueError):
            style(width=-1)
        self.painter.paint_strokes([thick(line(((1, 3.0625), (5, 3.0625))))]).require_nonempty()

    def test_soft_stroke_has_a_smooth_alpha_profile(self):
        y = 3.0 + TEXEL / 2
        self.painter.paint_strokes([stroke(line(((0.5, y), (11.5, y))), width=2, soft=2, color=INK)])
        positions, colors = interior(*painted(self.painter))     # the round caps at the ends fade out
        offsets = np.rint((positions[:, 1] - y) / TEXEL).astype(int)
        for offset, expected in ((0, 255), (1, 128), (-1, 128)):
            alpha = colors[offsets == offset][:, 3]
            self.assertTrue(len(alpha) and np.all(np.abs(alpha - expected) <= 1), (offset, set(alpha.tolist())))
        self.assertFalse(np.any(np.abs(offsets) >= 2))

    def test_soft_stroke_composites_over_the_existing_paint(self):
        self.painter.fill_all((0, 0, 255, 255))
        y = 3.0 + TEXEL / 2
        self.painter.paint_strokes([stroke(line(((0.5, y), (11.5, y))), width=2, soft=2, color=(255, 0, 0, 255))])
        positions, colors = interior(*painted(self.painter))
        offsets = np.rint((positions[:, 1] - y) / TEXEL).astype(int)
        edge = colors[offsets == 1]
        self.assertTrue(np.all(np.abs(edge[:, 0] - 128) <= 1) and np.all(np.abs(edge[:, 2] - 127) <= 1))
        self.assertTrue(np.all(colors[offsets == 3] == (0, 0, 255, 255)))

    def test_outline_surrounds_the_stroke(self):
        y = 3.0 + TEXEL / 2
        self.painter.paint_strokes([stroke(line(((0.5, y), (11.5, y))), width=1, color=INK,
                                           outline=(10, 10, 10, 255), outline_width=1)])
        positions, colors = interior(*painted(self.painter))
        offsets = np.rint((positions[:, 1] - y) / TEXEL).astype(int)
        self.assertTrue(np.all(colors[offsets == 0][:, 0] == INK[0]))
        self.assertTrue(np.all(colors[np.abs(offsets) == 1][:, 0] == 10))
        self.assertFalse(np.any(np.abs(offsets) >= 2))

    def test_three_dimensional_paths_follow_the_surface_across_faces(self):
        y = 3.0 + TEXEL / 2
        self.painter.paint_strokes([stroke(line(((0.5, y, 0), (11.5, y, 0))), width=1, color=INK)])
        positions, _ = painted(self.painter)
        xs = {math.floor(p[0] / TEXEL) for p in positions}
        for k in range(int(0.5 / TEXEL) + 1, int(11.5 / TEXEL)):
            self.assertIn(k, xs)

    def test_side_depth_and_element_filters_limit_the_paint(self):
        y = 3.0 + TEXEL / 2
        path = line(((0.5, y), (11.5, y)))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            report = self.painter.paint_strokes([
                stroke(path, color=INK, side="back", name="back"),
                stroke(path, color=INK, on=("other",), name="on"),
                stroke(path, color=INK, depth=(1, 2), name="depth"),
                stroke(path, color=INK, normal_min=1.1, name="normal"),
            ])
        self.assertEqual(report.empty, ["back", "on", "depth", "normal"])
        self.assertEqual(len(caught), 4)
        with self.assertRaises(ValueError):
            report.require_nonempty()
        self.painter.paint_strokes([stroke(path, color=INK, side="front", on="pla", depth=(-1, 1))]).require_nonempty()

    def test_mirror_and_offset_make_a_symmetric_drawing(self):
        offset = (-6.0, -3.0, 0.0)
        self.painter.paint_strokes([stroke(line(((-5.03, -2.02), (-3.01, 1.47))), width=1, color=INK, mirror="x")],
                                   offset=lambda name: offset)
        positions, _ = painted(self.painter)
        columns = {(math.floor((x - 6.0) / TEXEL), math.floor((y - 3.0) / TEXEL)) for x, y, _ in positions}
        self.assertGreater(len(columns), 10)
        # Pixel lines are mirror-symmetric up to one texel where a texel is equally close to two ideal positions.
        unmatched = [(i, j) for i, j in columns if not any((-1 - i + k, j) in columns for k in (-1, 0, 1))]
        self.assertEqual(unmatched, [])

    def test_layers_keep_the_base_untouched(self):
        self.painter.fill_all((40, 40, 40, 255))
        y = 3.0 + TEXEL / 2
        with self.painter.layer("lines") as layer:
            layer.paint_strokes([stroke(line(((0.5, y), (11.5, y))), color=INK)])
        positions, colors = painted(self.painter)
        self.assertTrue(np.all(colors == (40, 40, 40, 255)))
        atlas = np.asarray(self.painter.compose_atlas())
        self.assertTrue((atlas[..., 0] == INK[0]).any())

    def test_color_function_and_element_selection(self):
        y = 3.0 + TEXEL / 2
        self.painter.element("plate").paint_strokes([stroke(
            line(((0.5, y), (11.5, y))),
            color=lambda rows: np.tile((np.asarray(rows.model_position)[:, :1] * 20).clip(0, 255), (1, 3)))])
        positions, colors = painted(self.painter)
        order = np.argsort(positions[:, 0])
        self.assertTrue(np.all(np.diff(colors[order][:, 0]) >= -1))
        with self.assertRaisesRegex(ValueError, "color function"):
            self.painter.paint_strokes([stroke(line(((0.5, y), (11.5, y))), color=lambda rows: np.zeros((1, 3)))])

    def test_painting_is_deterministic(self):
        y = 3.0 + TEXEL / 2
        strokes = [stroke(curve(((1, 1), (4, 5), (8, 1), (11, 4))), width=1, color=INK),
                   stroke(arc((6, 3), 2, 1.5), width=2, soft=1, color=(10, 200, 10, 255))]
        images = []
        for _ in range(2):
            painter = plate_painter(self.temp.name)
            painter.paint_strokes(strokes)
            images.append(painter.compose_atlas().tobytes())
        self.assertEqual(images[0], images[1])

    def test_clean_is_ignored_with_soft(self):
        path = line(((1, 1), (11, 5)))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.painter.paint_strokes([stroke(path, color=INK)], soft=1.0, clean=True)
        self.assertTrue(any("clean is ignored" in str(w.message) for w in caught))


if __name__ == "__main__":
    unittest.main()
