import tempfile
import unittest
from pathlib import Path

import numpy as np

from Tools.TexturePainter import TexturePainter
from tests.fixtures_projection import sheets_model


class LayerBlendTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.model = sheets_model(Path(temp.name) / "s.bbmodel")


    def painted(self, painter, **compose):
        view = painter.surface()
        atlas = np.asarray(painter.compose_atlas(**compose)).astype(int)
        return atlas[view.y[0], view.x[0]]

    def test_multiply_and_screen_layers(self):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        painter.fill_all((200, 100, 50, 255))
        with painter.layer("shade", blend="multiply"):
            painter.fill_all((128, 128, 128, 255))
        np.testing.assert_allclose(self.painted(painter)[:3], [100, 50, 25], atol=1)
        np.testing.assert_array_equal(self.painted(painter, hide=("shade",)), [200, 100, 50, 255])
        with painter.layer("light", blend="screen", opacity=0.5):
            painter.fill_all((255, 255, 255, 255))
        lit = self.painted(painter)
        self.assertTrue(np.all(lit[:3] > [100, 50, 25]))
        self.assertTrue(np.all(lit[:3] < 255))

    def test_overlay_layer_multiplies_darks_and_screens_lights(self):
        from Tools.TexturePainter.core.color import blend_colors, blend_rows
        dark = blend_colors((60, 60, 60, 255), (128, 128, 128, 255), "overlay")
        light = blend_colors((200, 200, 200, 255), (128, 128, 128, 255), "overlay")
        self.assertEqual(dark[:3], (60, 60, 60))                  # a mid grey leaves the base as it is
        self.assertAlmostEqual(light[0], 200, delta=1)
        self.assertLess(blend_colors((60, 60, 60, 255), (60, 60, 60, 255), "overlay")[0], 60)     # dark over dark
        self.assertGreater(blend_colors((200, 200, 200, 255), (200, 200, 200, 255), "overlay")[0], 200)
        rows = blend_rows(np.array([[60, 60, 60, 255], [200, 200, 200, 255]]),
                          np.array([[60, 60, 60, 255], [200, 200, 200, 255]]), mode="overlay")
        np.testing.assert_array_equal(rows[:, 0], [blend_colors((60, 60, 60, 255), (60, 60, 60, 255), "overlay")[0],
                                                    blend_colors((200, 200, 200, 255), (200, 200, 200, 255), "overlay")[0]])
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        painter.fill_all((60, 60, 60, 255))
        with painter.layer("shade", blend="overlay"):
            painter.fill_all((60, 60, 60, 255))
        self.assertLess(self.painted(painter)[0], 60)

    def test_layer_options_are_checked(self):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        with self.assertRaises(ValueError):
            painter.add_layer("x", blend="dodge")
        with self.assertRaises(ValueError):
            painter.add_layer("x", opacity=2)
        with self.assertRaises(ValueError):
            painter.compose_atlas(hide=("missing",))


if __name__ == "__main__":
    unittest.main()
