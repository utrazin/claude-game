import tempfile
import unittest
from pathlib import Path

import numpy as np

from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.fields import Field
from Tools.TexturePainter.marks import Brush, Direction, Pattern, Tip, grain_field
from tests.fixtures_projection import collar_model


class TipTests(unittest.TestCase):
    def test_grain_is_a_deterministic_rank_field(self):
        tip = Tip.grain(speck=0.9, cluster=5.0, clump=0.55, size=64)
        a, b = tip.field(3), tip.field(3)
        self.assertIs(a, b)                                       # cached
        self.assertEqual(a.shape, (64, 64))
        self.assertAlmostEqual(float(a.min()), 0.0)
        self.assertAlmostEqual(float(a.max()), 1.0)
        self.assertFalse(np.array_equal(a, tip.field(4)))         # each pass seed its own grain
        fixed = tip.with_(seed=9)
        np.testing.assert_array_equal(fixed.field(1), fixed.field(2))
        np.testing.assert_array_equal(grain_field(64, 104, 0.9, 5.0, 0.55), tip.field(3))

    def test_with_changes_grain_options_and_checks(self):
        tip = Tip.grain(speck=(0.5, 3.0), cluster=(2.0, 9.0), clump=0.3)
        self.assertEqual(tip.with_(clump=0.8).texture["clump"], 0.8)
        self.assertEqual(tip.with_(scale=0.2).texture, tip.texture)
        with self.assertRaises(ValueError):
            tip.with_(scale=0)
        with self.assertRaises(ValueError):
            Tip(texture={"speck": 1, "cluster": 2, "clump": 0, "bogus": 1}).checked()

    def test_solid_and_image_tips(self):
        self.assertIsNone(Tip.solid().field(0))
        star = np.zeros((8, 8, 4), dtype=np.uint8)
        star[2:6, 2:6] = (255, 200, 0, 255)
        tip = Tip.image(star)
        self.assertTrue(tip.colored)
        self.assertEqual(tip.motif.shape, (8, 8, 4))
        with self.assertRaises(ValueError):
            Tip.image(np.zeros((8, 8, 3)))

    def test_on_surface_projects_the_grain(self):
        tip = Tip.grain(size=32, scale=0.5)
        pos = np.array([[0.1, 0.2, 0.3], [0.1, 0.2, 0.3], [5.0, 5.0, 5.0]])
        nrm = np.array([[0, 0, 1.0], [0, 0, 1.0], [1.0, 0, 0]])
        g = tip.on_surface(pos, nrm, seed=0)
        self.assertEqual(g[0], g[1])
        self.assertTrue(np.all(np.abs(g) <= 0.5))
        np.testing.assert_array_equal(Tip.solid().on_surface(pos, nrm, 0), np.zeros(3))


class BrushAndDirectionTests(unittest.TestCase):
    def test_brush_validation_and_derivation(self):
        brush = Brush(radius=(0.3, 0.5), length=(2, 4))
        self.assertEqual(brush.with_(turn=0).turn, 0)
        self.assertEqual(brush.scaled(2).stamp_radius(), (0.6, 1.0))
        for bad in (dict(radius=(0.5, 0.3)), dict(length=(0, 2)), dict(taper=1.0), dict(density=0),
                    dict(direction="fall")):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Brush(**bad)

    def test_directions(self):
        pos = np.array([[1.0, 2.0, 3.0]])
        nrm = np.array([[0.0, 0.0, 1.0]])
        np.testing.assert_allclose(Direction.around()(pos, nrm), [[1.0, 0.0, 0.0]])
        np.testing.assert_allclose(Direction.fall()(pos, nrm), [[0.0, 1.0, 0.0]])
        np.testing.assert_allclose(Direction.away((0, 0, 0))(pos, nrm), pos)
        np.testing.assert_allclose(Direction.toward((0, 0, 0))(pos, nrm), -pos)
        np.testing.assert_allclose(Direction.fixed((0, 0, 2))(pos, nrm), [[0, 0, 2.0]])
        self.assertEqual(Direction.diagonal()(pos, nrm).shape, (1, 3))
        with self.assertRaises(ValueError):
            Direction.away((0, 0))


class PatternTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.view = TexturePainter.from_bbmodel(collar_model(Path(temp.name) / "c.bbmodel"), render="pixel").surface()
        self.everywhere = np.ones(self.view.count, dtype=bool)

    def test_scatter_by_count_coverage_and_weight(self):
        rng = np.random.default_rng(0)
        starts = Pattern.scatter(count=40).starts(self.view, self.everywhere, rng, 1.0, 1.0)
        self.assertEqual(len(starts), 40)
        outer = self.view.select(groups="outer")
        starts = Pattern.scatter(count=40).starts(self.view, outer, rng, 1.0, 1.0)
        self.assertTrue(outer[starts].all())
        few = Pattern.scatter(coverage=1.0).starts(self.view, self.everywhere, rng, 100.0, 1 / 64)
        many = Pattern.scatter(coverage=1.0).starts(self.view, self.everywhere, rng, 1.0, 1 / 64)
        self.assertLess(len(few), len(many))
        up = Pattern.scatter(count=200, weight=Field.facing((0, -1, 0)))
        starts = up.starts(self.view, self.everywhere, rng, 1.0, 1.0)
        self.assertFalse((self.view.group[starts] == "inner").any())   # the inner wall faces up, never down
        with self.assertRaises(ValueError):
            Pattern.scatter()

    def test_lattice_is_regular(self):
        rng = np.random.default_rng(0)
        outer = self.view.select(groups="outer")
        starts = Pattern.lattice(1.0).starts(self.view, outer, rng, 1.0, 1.0)
        self.assertGreater(len(starts), 10)
        points = self.view.centre[starts]
        gaps = np.linalg.norm(points[:, None] - points[None], axis=2) + np.eye(len(points)) * 99
        self.assertGreater(gaps.min(axis=1).min(), 0.4)               # one start per cell, never two close
        again = Pattern.lattice(1.0).starts(self.view, outer, np.random.default_rng(0), 1.0, 1.0)
        np.testing.assert_array_equal(starts, again)

    def test_at_snaps_to_the_nearest_texel(self):
        target = self.view.centre[123]
        starts = Pattern.at(tuple(target)).starts(self.view, self.everywhere, np.random.default_rng(0), 1, 1)
        self.assertEqual(starts.tolist(), [123])


class LightFieldTests(unittest.TestCase):
    def test_light_matches_the_key_and_fill_model(self):
        light = Field.light((0, 1, 0), fill=(0, 0, 1), fill_strength=0.35)
        normals = np.array([[0, 1.0, 0], [1.0, 0, 0], [0, -1.0, 0], [0, -0.6, 0.8]])
        values = light(np.zeros(4), np.zeros(4), np.zeros(4), normal=normals)
        self.assertAlmostEqual(values[0], 1.0)
        self.assertAlmostEqual(values[1], 0.48)
        self.assertAlmostEqual(values[2], 0.0)
        self.assertAlmostEqual(values[3], 0.48 - 0.52 * 0.6 + 0.35 * 0.8)


if __name__ == "__main__":
    unittest.main()
