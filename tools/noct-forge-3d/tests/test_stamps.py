import tempfile
import unittest
from pathlib import Path

import numpy as np

from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.marks import Brush, Direction, Pattern, Tip
from Tools.TexturePainter.stamps import PathPiece, TexelLayer, lay, path_strokes, width_profile
from tests.fixtures_projection import collar_model, mirrored_pairs_differ, painted_by_group, sheets_model

CHALK = Tip.grain(speck=0.9, cluster=5.0, clump=0.55, scale=0.08)
DAB = Brush(radius=(0.5, 0.7), length=(2, 4), spacing=0.45)


class StampTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)

    def test_strokes_are_deterministic_and_stay_where_asked(self):
        painter = TexturePainter.from_bbmodel(collar_model(self.dir / "c.bbmodel"), render="pixel")
        view = painter.surface()
        outer = view.select(groups="outer")
        a = lay(view, Pattern.scatter(coverage=0.8), tip=CHALK, brush=DAB, colors=[(200, 50, 50)], where=outer, seed=4)
        b = lay(view, Pattern.scatter(coverage=0.8), tip=CHALK, brush=DAB, colors=[(200, 50, 50)], where=outer, seed=4)
        self.assertGreater(len(a.texel), 100)
        np.testing.assert_array_equal(a.texel, b.texel)
        np.testing.assert_array_equal(a.colors, b.colors)
        self.assertTrue(outer[a.texel].all())
        self.assertEqual(len(np.unique(a.texel)), len(a.texel))          # one hit per texel

    def test_more_pressure_more_ink(self):
        view = TexturePainter.from_bbmodel(collar_model(self.dir / "c.bbmodel"), render="pixel").surface()
        light = lay(view, Pattern.scatter(coverage=1.0), tip=CHALK, brush=DAB, colors=["#ffffff"], seed=1,
                    pressure=np.full(view.count, 0.3))
        full = lay(view, Pattern.scatter(coverage=1.0), tip=CHALK, brush=DAB, colors=["#ffffff"], seed=1)
        self.assertLess(len(light.texel), len(full.texel))

    def test_occlusion_keeps_a_stamp_on_its_own_layer(self):
        view = TexturePainter.from_bbmodel(sheets_model(self.dir / "s.bbmodel"), render="pixel").surface()
        on_back = Pattern.at((3.0, 2.0, 0.0))
        brush = Brush(radius=(1.0, 1.0), length=(1, 1), size_jitter=(1.0, 1.0))
        solid = Tip.solid()
        kept = lay(view, on_back, tip=solid, brush=brush, colors=[(0, 0, 0)])
        leaked = lay(view, on_back, tip=solid, brush=brush, colors=[(0, 0, 0)], occlusion=False)
        front = view.select(groups="front")
        self.assertEqual(int(front[kept.texel].sum()), 0)
        self.assertGreater(int(front[leaked.texel].sum()), 0)           # without it the front sheet is reached
        self.assertGreater(int((~front)[kept.texel].sum()), 50)

    def test_image_motif_prints_its_own_colours(self):
        view = TexturePainter.from_bbmodel(sheets_model(self.dir / "s.bbmodel"), render="pixel").surface()
        motif = np.zeros((4, 4, 4), dtype=np.uint8)
        motif[:, :2] = (255, 0, 0, 255)                                   # left half red, right half transparent
        hits = lay(view, Pattern.at((3.0, 2.0, 0.3)), tip=Tip.image(motif),
                   brush=Brush(radius=(1.0, 1.0), length=(1, 1), size_jitter=(1, 1), spread=0,
                               direction=Direction.fixed((1, 0, 0)), jitter=(0, 0, 0), align=1.0),
                   colors=[(0, 0, 255)])
        self.assertGreater(len(hits.texel), 20)
        np.testing.assert_allclose(hits.colors, np.tile([255.0, 0, 0], (len(hits.texel), 1)))
        self.assertTrue((view.centre[hits.texel][:, 0] < 3.05).all())     # only the opaque half

    def test_soft_edge_gives_partial_alpha(self):
        view = TexturePainter.from_bbmodel(collar_model(self.dir / "c.bbmodel"), render="pixel").surface()
        hard = lay(view, Pattern.scatter(coverage=0.6), tip=CHALK, brush=DAB, colors=[(0, 0, 0)], seed=2)
        soft = lay(view, Pattern.scatter(coverage=0.6), tip=CHALK, brush=DAB, colors=[(0, 0, 0)], seed=2,
                   edge="soft")
        self.assertTrue(np.all(hard.alpha == 1.0))
        self.assertTrue(((soft.alpha > 0) & (soft.alpha < 1)).any())

    def test_lattice_prints_regular_dots(self):
        view = TexturePainter.from_bbmodel(sheets_model(self.dir / "s.bbmodel"), render="pixel").surface()
        hits = lay(view, Pattern.lattice(1.5), tip=Tip.solid(), where=view.select(groups="front"),
                   brush=Brush(radius=(0.3, 0.3), length=(1, 1), size_jitter=(1, 1)), colors=[(0, 0, 0)])
        self.assertEqual(hits.strokes, 4 * 3)                            # 6 x 4 units in 1.5-unit cells

    def test_paint_composites_and_mirrors(self):
        model = collar_model(self.dir / "c.bbmodel")
        painter = TexturePainter.from_bbmodel(model, render="pixel")
        painter.fill_all((10, 10, 10, 255))
        side = painter.surface().centre[:, 0] > 0
        painter.stamp(Pattern.scatter(coverage=0.8), tip=CHALK, brush=DAB, colors=[(250, 250, 250)], where=side,
                      seed=3, mirror="x")
        differ, total = mirrored_pairs_differ(painter)
        self.assertGreater(total, 0)
        self.assertEqual(differ, 0)
        element = TexturePainter.from_bbmodel(model, render="pixel")
        element.element("collar").stamp(Pattern.scatter(count=30), tip=CHALK, brush=DAB, colors=[(250, 0, 0)])
        self.assertGreater(sum(painted_by_group(element, "collar").values()), 0)

    def test_width_profile_points_the_ends_and_swells_smoothly(self):
        brush = Brush(taper=0.9, taper_length=1.0, swell=0.2, swell_length=2.0)
        arc = np.linspace(0.0, 10.0, 201)
        flat = width_profile(brush.with_(swell=0.0), arc, 10.0, False)
        self.assertAlmostEqual(flat[0], 0.1)                              # a point at each end
        self.assertAlmostEqual(flat[-1], 0.1)
        np.testing.assert_allclose(flat[(arc >= 1.0) & (arc <= 9.0)], 1.0)  # full width between the tapers
        swollen = width_profile(brush.with_(taper=0.0), arc, 10.0, False, phase=(0.3, 1.1))
        self.assertGreater(swollen.max() - swollen.min(), 0.2)
        self.assertLessEqual(np.abs(swollen - 1).max(), 0.2 + 1e-9)
        self.assertLess(np.abs(np.diff(swollen)).max(), 0.05)                # smooth, not per-stamp jitter
        np.testing.assert_allclose(width_profile(brush.with_(swell=0.0), arc, 10.0, True), 1.0)   # no ends
        with self.assertRaises(ValueError):
            Brush(taper_length=0)

    def test_pieces_of_one_line_share_its_profile(self):
        view = TexturePainter.from_bbmodel(sheets_model(self.dir / 's.bbmodel'), render='pixel').surface()
        brush = Brush(radius=(1, 1), length=(1, 1), spacing=0.25, taper=0.9, taper_length=1.0,
                      size_jitter=(1, 1), jitter=(0, 0, 0))
        line = np.array([[0.5, 2.0, 0.3], [5.5, 2.0, 0.3]])
        whole, _ = path_strokes(view, [line], brush, [np.zeros(3)], np.random.default_rng(0), 64, 0.2)
        half = np.array([[3.0, 2.0, 0.3], [5.5, 2.0, 0.3]])
        piece = PathPiece(half, np.array([2.5, 5.0]), 5.0, False, 0)
        part, _ = path_strokes(view, [piece], brush, [np.zeros(3)], np.random.default_rng(0), 64, 0.2)
        self.assertAlmostEqual(part['r'][0], 0.2)                        # the cut is mid-line: no point there
        self.assertAlmostEqual(part['r'][-1], 0.2 * 0.1)                 # the line's real end
        self.assertAlmostEqual(whole['r'][0], 0.2 * 0.1)

    def test_texel_layer_matches_direct_painting(self):
        layer = TexelLayer(3)
        layer.lay(np.array([0, 1]), np.array([[255.0, 0, 0], [0, 255.0, 0]]), 0.5)
        layer.lay(np.array([1]), np.array([[0, 0, 255.0]]), 0.5)
        image = np.full((3, 3), 100.0)
        direct = image.copy()
        direct[[0, 1]] = direct[[0, 1]] * 0.5 + np.array([[255.0, 0, 0], [0, 255.0, 0]]) * 0.5
        direct[1] = direct[1] * 0.5 + np.array([0, 0, 255.0]) * 0.5
        np.testing.assert_allclose(layer.over(image), direct)
        idx, rgba = layer.rgba()
        self.assertEqual(idx.tolist(), [0, 1])
        np.testing.assert_allclose(rgba[0], [255, 0, 0, 127.5])


class AdditiveHitsTests(unittest.TestCase):
    def test_overlapping_strokes_add_up(self):
        from Tools.TexturePainter.stamps import Hits
        import numpy as np
        hits = Hits(np.arange(3), np.zeros((3, 3)), np.ones(3), 3, 3, np.array([1.0, 2.0, 3.0]))
        np.testing.assert_allclose(hits.additive(0.5), [0.5, 0.75, 0.875])
        np.testing.assert_allclose(Hits(np.arange(2), np.zeros((2, 3)), np.ones(2), 1, 1).additive(0.4), [0.4, 0.4])


if __name__ == "__main__":
    unittest.main()
