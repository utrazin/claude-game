import json
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.ink import boundary, line, stroke
from Tools.TexturePainter.render_mode import RenderMode, from_record, preset
from Tools.uv_builder import UVBuilder
from tests.test_uv_charts import plate_model

SCALE = 8


def atlas(painter):
    return np.asarray(painter.compose_atlas()).astype(int)


class RenderModeRecordTests(unittest.TestCase):
    def test_the_texture_filter_picks_the_mode_and_render_overrides_it(self):
        self.assertEqual(from_record({}), RenderMode())
        smooth = from_record({"texture_filter": "linear"})
        self.assertTrue(smooth.smooth)
        self.assertEqual((smooth.density, smooth.padding, smooth.aa, smooth.samples), (16, 4, 1.0, 4))
        self.assertEqual(from_record({"texture_filter": "linear", "render": {"samples": 2}}).samples, 2)
        for bad in ({"samples": 0}, {"aa": -1}, {"density": 1.5}, {"nope": 1}):
            with self.assertRaises(ValueError):
                from_record({"texture_filter": "linear", "render": bad})

    def test_widths_follow_the_reference_density(self):
        self.assertEqual(RenderMode().width_scale(32), 1.0)
        self.assertEqual(preset("smooth", reference=8).width_scale(16), 2.0)
        self.assertEqual(len(preset("smooth").offsets()), 16)
        self.assertEqual(preset("pixel").offsets(), ((0.0, 0.0),))


class SmoothPaintingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.bbmodel"
        plate_model(self.model)
        UVBuilder(self.model, start_size=(128, 128), uv_scale=SCALE, island_padding=1, layout="charts",
                  require_integer_uvs=False).save()
        self.box = self.plate_box()

    def plate_box(self):
        data = json.loads(self.model.read_text(encoding="utf-8"))
        uv = np.array([p for f in data["elements"][0]["faces"].values() for p in f["uv"].values()])
        x0, y0 = np.floor(uv.min(axis=0)).astype(int)
        x1, y1 = np.ceil(uv.max(axis=0)).astype(int)
        return x0, y0, x1, y1

    def painter(self, mode="smooth", **overrides):
        render = preset(mode, **overrides) if overrides else mode
        painter = TexturePainter.from_bbmodel(self.model, render=render)
        painter.fill_all((255, 255, 255, 255))
        return painter

    def ink(self, painter):
        """Ink fraction (white 0 .. black 1) on a (rows y, columns x) grid of the plate's texels, indexed by
        model position: column floor(x * SCALE), row floor(y * SCALE)."""
        grid = np.full((6 * SCALE, 12 * SCALE), np.nan)
        for face, rows in painter.element("plate")._surface_region()._entries:
            centre = np.asarray(rows.fields["_e0"])        # texel centres (element space = model space here)
            rgba = face.canvas.read_pixels(rows.x, rows.y)
            cx, cy = np.floor(centre[:, 0] * SCALE).astype(int), np.floor(centre[:, 1] * SCALE).astype(int)
            grid[cy, cx] = 1.0 - rgba[:, 0] / 255.0
        self.assertFalse(np.isnan(grid).any())
        return grid

    def test_a_smooth_line_covers_its_exact_width_with_one_texel_of_transition(self):
        painter = self.painter()
        # A slanted line 2 texels wide across the plate (model units: x 0..12, y 0..6).
        painter.paint_strokes([stroke(line(((0.5, 1.2), (11.5, 4.9))), width=2, color=(0, 0, 0))]).require_nonempty()
        ink = self.ink(painter)
        slope = (4.9 - 1.2) / 11.0
        expected = 2.0 * math.sqrt(1 + slope ** 2)          # vertical extent of a 2-texel band at that slope
        for column in range(2 * SCALE, 10 * SCALE):
            values = ink[:, column]
            self.assertAlmostEqual(values.sum(), expected, delta=0.15)
            partial = values[(values > 0.02) & (values < 0.98)]
            self.assertLessEqual(len(partial), 4)              # a thin anti-aliased edge each side, no ramp
        self.assertTrue(((ink > 0.02) & (ink < 0.98)).any())   # it is anti-aliased, not a hard mask

    def test_pixel_mode_still_draws_hard_pixels(self):
        painter = self.painter("pixel")
        painter.paint_strokes([stroke(line(((0.5, 1.2), (11.5, 4.9))), width=2, color=(0, 0, 0))])
        ink = self.ink(painter)
        self.assertTrue(np.isin(np.round(ink, 6), (0.0, 1.0)).all())

    def test_widths_are_reference_texels(self):
        painter = self.painter(reference=4)                     # 2 reference texels = 4 texels at 8 px/unit
        painter.paint_strokes([stroke(line(((0.5, 3.0), (11.5, 3.0))), width=2, color=(0, 0, 0))])
        ink = self.ink(painter)
        self.assertAlmostEqual(ink[:, 6 * SCALE].sum(), 4.0, delta=0.1)

    def test_inside_alignment_keeps_the_full_width_on_one_side(self):
        painter = self.painter()
        painter.paint_strokes([stroke(boundary("plate", "a", "b"), width=2, color=(0, 0, 0), groups="a",
                                      align="inside")]).require_nonempty()
        ink = self.ink(painter)
        edge = 6 * SCALE                                         # the a|b edge at x = 6
        self.assertFalse((ink[:, edge:] > 0.01).any())          # nothing on group b
        row = ink[SCALE, :edge]
        self.assertAlmostEqual(row.sum(), 2.0, delta=0.05)      # the whole width, on group a

    def test_smooth_base_painting_averages_each_texel_area(self):
        painter = self.painter()
        cut = 5.3                                                # model x of a hard colour change
        painter.element("plate").paint_surface_arrays(lambda rows: np.where(
            (np.asarray(rows.model_position)[:, 0] < cut)[:, None], (0, 0, 0, 255), (255, 255, 255, 255)))
        ink = self.ink(painter)
        column = int(math.floor(cut * SCALE))
        fraction = cut * SCALE - column
        self.assertTrue(np.allclose(ink[:, :column], 1.0))
        self.assertTrue(np.allclose(ink[:, column + 1:], 0.0))
        self.assertTrue(np.allclose(ink[:, column], fraction, atol=1 / 8 + 0.01))   # 4 x 4 subsamples

    def test_a_smooth_fill_is_anti_aliased_too(self):
        painter = self.painter()
        square = ((2.03, 1.03), (5.97, 1.03), (5.97, 4.97), (2.03, 4.97))
        painter.paint_strokes([stroke(line(square, closed=True), width=1, color=(0, 0, 0),
                                      fill=(0, 0, 0))])
        ink = self.ink(painter)
        inside = ink[int(2.0 * SCALE):int(4.0 * SCALE), int(3.0 * SCALE):int(5.0 * SCALE)]
        self.assertTrue(np.allclose(inside, 1.0))
        self.assertAlmostEqual(ink.sum(), (5.97 - 2.03 + 1 / SCALE) * (4.97 - 1.03 + 1 / SCALE) * SCALE ** 2,
                               delta=2.0)


if __name__ == "__main__":
    unittest.main()
