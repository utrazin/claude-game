import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from Tools.TexturePainter import TexturePainter
from tests.fixtures_projection import collar_model, painted_by_group, ramp_model


def solid(color=(255, 0, 0)):
    return Image.fromarray(np.array([[list(color) + [255]]], dtype=np.uint8), "RGBA")


class ProjectionLayersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = collar_model(Path(self.temp.name) / "collar.bbmodel")

    def painter(self, mode="pixel"):
        return TexturePainter.from_bbmodel(self.model, render=mode)

    def test_planar_projection_through_a_double_wall_collar(self):
        for mode in ("pixel", "smooth"):
            with self.subTest(mode=mode):
                everything = self.painter(mode)
                everything.element("collar").project_planar(solid(), scale=1 / 64)
                front = self.painter(mode)
                front.element("collar").project_planar(solid(), scale=1 / 64, layers="front")
                all_layers, front_only = painted_by_group(everything, "collar"), painted_by_group(front, "collar")
                self.assertGreater(all_layers["inner"], 0)                # the wall behind is painted through
                self.assertEqual(front_only["inner"], 0)                  # but not when only the front layer counts
                self.assertGreater(front_only["outer"], 0.9 * all_layers["outer"])   # the front wall is kept

    def test_decal_layers_front_keeps_the_front_wall(self):
        for mode in ("pixel", "smooth"):
            with self.subTest(mode=mode):
                painter = self.painter(mode)
                painter.element("collar").project_decal(solid(), center=(0.5, 0.5), size=(1.0, 1.0), layers="front")
                counts = painted_by_group(painter, "collar")
                self.assertGreater(counts["outer"], 0)
                self.assertEqual(counts["inner"], 0)

    def test_layers_rejects_unknown_modes(self):
        with self.assertRaises(ValueError):
            self.painter().element("collar").project_decal(solid(), layers="behind")
        with self.assertRaises(ValueError):
            self.painter().element("collar").project_planar(solid(), layers="behind")


class GrazingFadeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = ramp_model(Path(self.temp.name) / "ramp.bbmodel")

    def alphas(self, **options):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        painter.element("ramp").project_planar(solid(), scale=1 / 64, **options)
        out = {}
        for face, rows in painter.element("ramp")._surface_region()._entries:
            out[face.uv_info.get("group")] = face.canvas.read_pixels(rows.x, rows.y)[:, 3]
        return out

    def test_fade_loses_the_image_gradually_on_a_grazing_face(self):
        hard = self.alphas()                                   # default: everything is painted at full alpha
        self.assertTrue((hard["ramp"] == 255).all())
        faded = self.alphas(fade=(0.0, 0.5))                   # the wall faces the front (1.0), the ramp barely (0.12)
        self.assertTrue((faded["wall"] == 255).all())
        self.assertTrue(((faded["ramp"] > 0) & (faded["ramp"] < 255)).all())
        self.assertAlmostEqual(float(faded["ramp"].mean()) / 255, 0.124 / 0.5, delta=0.03)
        cut = self.alphas(fade=(0.2, 0.6))                     # beyond the start of the fade: nothing
        self.assertEqual(int(cut["ramp"].sum()), 0)

    def test_fade_must_be_an_increasing_pair(self):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        for bad in ((0.5, 0.5), (0.6, 0.2)):
            with self.assertRaises(ValueError):
                painter.element("ramp").project_planar(solid(), fade=bad)


class ProjectionMirrorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = collar_model(Path(self.temp.name) / "collar.bbmodel")

    def mirrored_pairs_differ(self, painter):
        """Texels whose mirror image (K - 1 - x, y - D, from the UV charts' mirror table) has another colour."""
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

    def paint(self, method, mode, mirror):
        painter = TexturePainter.from_bbmodel(self.model, render=mode)
        painter.fill_all((10, 10, 10, 255))
        stamp = Image.fromarray(np.array([[[255, 0, 0, 255], [0, 0, 255, 255]]], dtype=np.uint8), "RGBA")
        element = painter.element("collar")
        if method == "decal":     # on the +x half only, and not symmetric by itself
            element.project_decal(stamp, center=(0.75, 0.5), size=(0.4, 0.6), mirror=mirror)
        elif method == "planar":
            element.project_planar(stamp, scale=1 / 3.1, mirror=mirror)
        else:
            element.project_triplanar(stamp, scale=1 / 3.1, mirror=mirror)
        return painter

    def test_mirror_x_makes_both_halves_identical_by_construction(self):
        for method in ("decal", "planar", "triplanar"):
            for mode in ("pixel", "smooth"):
                with self.subTest(method=method, mode=mode):
                    probe = self.paint(method, mode, None)
                    self.assertTrue(probe.parser.chart_mirrors)             # the fixture has mirrored charts
                    mirrored = self.paint(method, mode, "x")
                    differ, total = self.mirrored_pairs_differ(mirrored)
                    self.assertGreater(total, 0)
                    self.assertEqual(differ, 0)
                    if method == "decal":     # the decal sits on +x, so without mirror the halves differ
                        self.assertGreater(self.mirrored_pairs_differ(probe)[0], 0)

    def test_mirror_accepts_only_x(self):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        with self.assertRaises(ValueError):
            painter.element("collar").project_decal(solid(), mirror="y")


if __name__ == "__main__":
    unittest.main()
