import tempfile
import unittest
from pathlib import Path

import numpy as np

from lib import ModelBuilder
from lib.geometry_types import MeshFace, MeshGeometry
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.ink import line, stroke
from Tools.TexturePainter.render_mode import preset
from Tools.uv_builder import UVBuilder

SCALE = 8


def ramp_model(path):
    """Two quads: a wall facing +z (y 0..4) and a ramp leaving its top edge backwards and upwards, nearly parallel
    to the viewing direction (its normal faces the front by about 0.12, below the default normal_min of 0.15)."""
    verts = {"w0": (0, 0, 0), "w1": (6, 0, 0), "w2": (6, 4, 0), "w3": (0, 4, 0),
             "r2": (6, 5, -8), "r3": (0, 5, -8)}
    faces = {"wall": MeshFace(("w0", "w1", "w2", "w3"), "wall"),
             "ramp": MeshFace(("w3", "w2", "r2", "r3"), "ramp")}
    builder = ModelBuilder("ramp", require_integer_dimensions=False).add_group("root")
    builder.add_mesh("ramp", "root", MeshGeometry.create(verts, faces))
    builder.export_bbmodel(path)


class WrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.bbmodel"
        ramp_model(self.model)
        UVBuilder(self.model, start_size=(128, 128), uv_scale=SCALE, island_padding=1, layout="charts",
                  require_integer_uvs=False).save()

    def painted(self, painter, group):
        count = 0
        for face, rows in painter.element("ramp")._surface_region()._entries:
            if face.uv_info.get("group") == group:
                count += int((face.canvas.read_pixels(rows.x, rows.y)[:, 3] > 0).sum())
        return count

    def paint(self, mode, wrap):
        painter = TexturePainter.from_bbmodel(self.model, render=preset(mode, reference=SCALE, density=SCALE))
        # a vertical line up the wall and on over the ramp (projected along z, the ramp is nearly edge-on)
        painter.paint_strokes([stroke(line(((3.0, 0.5), (3.0, 4.8))), width=2, color=(255, 0, 0),
                                      wrap=wrap)])
        return painter

    def test_a_projected_line_skips_a_grazing_surface_and_a_wrapped_one_reaches_it(self):
        for mode in ("pixel", "smooth"):
            with self.subTest(mode=mode):
                plain, wrapped = self.paint(mode, False), self.paint(mode, True)
                self.assertGreater(self.painted(plain, "wall"), 0)
                self.assertEqual(self.painted(plain, "ramp"), 0)        # facing 0.12 < normal_min: nothing
                self.assertGreater(self.painted(wrapped, "ramp"), 0)     # lifted onto it
                self.assertGreaterEqual(self.painted(wrapped, "wall"), self.painted(plain, "wall"))

    def test_a_wrapped_fill_covers_the_shape_on_every_layer(self):
        square = ((1.0, 3.0), (5.0, 3.0), (5.0, 4.8), (1.0, 4.8))     # projected: the wall's top and the ramp's start
        for mode in ("pixel", "smooth"):
            with self.subTest(mode=mode):
                results = {}
                for wrap in (False, True):
                    painter = TexturePainter.from_bbmodel(self.model,
                                                          render=preset(mode, reference=SCALE, density=SCALE))
                    painter.paint_strokes([stroke(line(square, closed=True), width=1, color=(255, 0, 0),
                                                  fill=(0, 0, 255), wrap=wrap)])
                    results[wrap] = (self.painted(painter, "wall"), self.painted(painter, "ramp"))
                self.assertEqual(results[False][1], 0)                      # the grazing ramp is skipped
                self.assertGreater(results[True][1], 0)                     # a wrapped fill reaches it
                self.assertGreaterEqual(results[True][0], results[False][0] - 8)   # and keeps the wall

    def test_pixel_lines_are_completed_across_a_chart_seam(self):
        # the wall and the ramp are two charts; a thick line along their fold is cut at the chart edge on each side
        from Tools.TexturePainter.ink import boundary

        def painted_total(seam):
            painter = TexturePainter.from_bbmodel(self.model, render="pixel")
            painter.paint_strokes([stroke(boundary("ramp", "wall", "ramp"), width=6, color=(255, 0, 0),
                                          seam=seam)]).require_nonempty()
            groups = {}
            for face, rows in painter.element("ramp")._surface_region()._entries:
                group = face.uv_info.get("group")
                groups[group] = groups.get(group, 0) + int((face.canvas.read_pixels(rows.x, rows.y)[:, 3] > 0).sum())
            return groups

        plain, joined = painted_total("none"), painted_total(None)       # None: a surface path completes the seam
        self.assertEqual(joined, painted_total("fill"))
        self.assertGreater(sum(joined.values()), sum(plain.values()))
        self.assertTrue(all(joined[g] >= plain[g] for g in plain))          # only adds texels

    def test_seam_accepts_only_known_modes(self):
        with self.assertRaises(ValueError):
            stroke(line(((0, 0), (1, 1))), seam="always")

    def test_wrap_still_needs_a_flat_2d_path(self):
        with self.assertRaises(ValueError):
            stroke(line(((0, 0, 0), (1, 1, 1))), wrap=True)


if __name__ == "__main__":
    unittest.main()
