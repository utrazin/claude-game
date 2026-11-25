import tempfile
import unittest
import warnings
from pathlib import Path

import numpy as np

from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.ink import line, stroke
from Tools.TexturePainter.marks import Brush, Tip
from tests.fixtures_projection import sheets_model


class FeatherAndStampedLineTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.model = sheets_model(Path(temp.name) / "s.bbmodel")

    def alpha_across(self, mode, width=2, **style):
        """Alpha of the front sheet's texels by distance from a horizontal line at y = 2."""
        painter = TexturePainter.from_bbmodel(self.model, render=mode)
        painter.paint_strokes([stroke(line(((0.5, 2.0), (5.5, 2.0))), width=width, groups="front", **style)])
        view = painter.surface()
        front = np.flatnonzero(view.select(groups="front") & (np.abs(view.centre[:, 0] - 3) < 1.5))
        atlas = np.asarray(painter.compose_atlas()).astype(int)
        alpha = atlas[view.y[front], view.x[front], 3]
        return np.abs(view.centre[front, 1] - 2.0), alpha

    def test_feather_widens_a_soft_edge(self):
        d0, sharp = self.alpha_across("smooth", width=6)
        d1, soft = self.alpha_across("smooth", width=6, feather=4)
        partial_sharp = int(((sharp > 0) & (sharp < 255)).sum())
        partial_soft = int(((soft > 0) & (soft < 255)).sum())
        self.assertGreater(partial_soft, 2 * partial_sharp)
        order = np.argsort(d1)
        ramp = soft[order][(d1[order] > 0.1) & (d1[order] < 0.7)]
        self.assertTrue(np.all(np.diff(ramp.astype(int)) <= 30))        # eases off instead of a cut
        self.assertEqual(int(soft[d1 < 0.07].min()), 255)                # the core stays solid

    def test_zero_feather_is_unchanged(self):
        _, plain = self.alpha_across("smooth")
        _, zero = self.alpha_across("smooth", feather=0)
        np.testing.assert_array_equal(plain, zero)

    def test_pixel_art_ignores_feather(self):
        _, plain = self.alpha_across("pixel")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _, feathered = self.alpha_across("pixel", feather=4)
        np.testing.assert_array_equal(plain, feathered)
        self.assertTrue(any("feather" in str(w.message) for w in caught))

    def test_stamped_line_follows_the_path_with_grain(self):
        chalk = Tip.grain(scale=0.03)
        for mode in ("pixel", "smooth"):
            with self.subTest(mode=mode):
                d, alpha = self.alpha_across(mode, tip=chalk, color=(20, 20, 20))
                self.assertGreater(int((alpha > 0).sum()), 20)
                self.assertTrue(np.all(d[alpha > 0] < 0.25))               # within the width (2 texels of 8/unit)
                core = alpha[d < 0.07]
                self.assertGreater(int((core == 0).sum()), 0)               # the grain leaves gaps
                solid_d, solid = self.alpha_across(mode, tip=Tip.solid(), color=(20, 20, 20))
                self.assertGreater(int((solid > 0).sum()), int((alpha > 0).sum()))

    def test_chalk_line_keeps_a_solid_outline_under_it(self):
        painter = TexturePainter.from_bbmodel(self.model, render='smooth')
        painter.paint_strokes([stroke(line(((0.5, 2.0), (5.5, 2.0))), width=2, groups='front',
                                      tip=Tip.grain(scale=0.03), color=(250, 200, 0), outline=(0, 0, 0))])
        view = painter.surface()
        sel = np.flatnonzero(view.select(groups='front') & (np.abs(view.centre[:, 1] - 2.0) < 0.07)
                             & (np.abs(view.centre[:, 0] - 3.0) < 1.5))
        atlas = np.asarray(painter.compose_atlas()).astype(int)[view.y[sel], view.x[sel]]
        self.assertTrue(np.all(atlas[:, 3] == 255))                       # the band under the line is solid
        self.assertTrue((atlas[:, 0] > 200).any() and (atlas[:, 0] < 50).any())   # gold grain over the dark band

    def test_side_offset_moves_the_line_alongside_its_path(self):
        for kw in ({}, {"tip": Tip.solid()}):
            with self.subTest(chalk=bool(kw)):
                d_plain, plain = self.alpha_across("smooth", **kw)
                painter = TexturePainter.from_bbmodel(self.model, render="smooth")
                painter.paint_strokes([stroke(line(((0.5, 2.0), (5.5, 2.0))), width=2, groups="front",
                                              side_offset=4, **kw)])
                view = painter.surface()
                front = np.flatnonzero(view.select(groups="front") & (np.abs(view.centre[:, 0] - 3) < 1.5))
                alpha = np.asarray(painter.compose_atlas()).astype(int)[view.y[front], view.x[front], 3]
                inked = view.centre[front][alpha > 128, 1]
                self.assertGreater(len(inked), 10)
                self.assertAlmostEqual(float(np.median(inked)), 2.0 + 4 / 8, delta=0.1)   # 4 texels to the left
        with self.assertRaises(ValueError):
            stroke(line(((0, 0), (1, 1))), side_offset=float("nan"))

    def test_stamped_line_brush_and_checks(self):
        tapered = Brush(radius=(1, 1), length=(1, 1), spacing=0.25, turn=0, spread=0, align=1, taper=0.9,
                        size_jitter=(1, 1), jitter=(0, 0, 0))
        d, alpha = self.alpha_across("smooth", tip=Tip.solid(), brush=tapered, color=(0, 0, 0))
        self.assertGreater(int((alpha > 0).sum()), 0)
        with self.assertRaises(ValueError):
            stroke(line(((0, 0), (1, 1))), tip=Tip.solid(), color=lambda rows: np.zeros((len(rows), 3)))
        with self.assertRaises(TypeError):
            stroke(line(((0, 0), (1, 1))), tip="chalk")
        with self.assertRaises(ValueError):
            stroke(line(((0, 0), (1, 1))), feather=-1)


if __name__ == "__main__":
    unittest.main()
