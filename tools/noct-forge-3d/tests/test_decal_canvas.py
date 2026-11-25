"""Unit tests for DecalCanvas, seamless texturing, and tile grids."""

import tempfile
import unittest
from pathlib import Path
from PIL import Image

from Tools.TexturePainter import TexturePainter, DecalCanvas


class TestDecalCanvas(unittest.TestCase):
    def test_standalone_basic_drawing(self):
        painter = DecalCanvas(16, 16)
        painter.fill("#ff0000")
        img = painter.compose()
        self.assertEqual(img.size, (16, 16))
        self.assertEqual(img.getpixel((0, 0)), (255, 0, 0, 255))
        self.assertEqual(img.getpixel((15, 15)), (255, 0, 0, 255))

        # Pixel with wrap
        painter.set_pixel(16, 16, "#00ff00", wrap=True)  # (16 % 16, 16 % 16) -> (0, 0)
        img2 = painter.compose()
        self.assertEqual(img2.getpixel((0, 0)), (0, 255, 0, 255))

    def test_factory_method(self):
        painter = TexturePainter.create_canvas(32, 32, background="#112233")
        self.assertEqual(painter.width, 32)
        self.assertEqual(painter.height, 32)
        img = painter.compose()
        self.assertEqual(img.getpixel((5, 5)), (17, 34, 51, 255))

    def test_regions_and_local_coordinates(self):
        painter = DecalCanvas(32, 32)
        painter.define_region("grass_dry", 0, 0, 16, 16)
        painter.define_region("grass_lush", 16, 0, 16, 16)

        # Draw locally on grass_dry
        painter.grass_dry.fill("#7a8a3b")
        painter.grass_dry.set_pixel(0, 0, "#ffffff")

        # Draw locally on grass_lush
        painter.grass_lush.fill("#4a9a2b")
        painter.grass_lush.set_pixel(0, 0, "#000000")

        composed = painter.compose()
        # grass_dry at (0, 0)
        self.assertEqual(composed.getpixel((0, 0)), (255, 255, 255, 255))
        self.assertEqual(composed.getpixel((5, 5)), (122, 138, 59, 255))

        # grass_lush at (16, 0)
        self.assertEqual(composed.getpixel((16, 0)), (0, 0, 0, 255))
        self.assertEqual(composed.getpixel((20, 5)), (74, 154, 43, 255))

    def test_tile_grid(self):
        painter = DecalCanvas(32, 32)
        names = ["tile_a", "tile_b", "tile_c", "tile_d"]
        painter.tile_grid(tile_w=16, tile_h=16, names=names)

        self.assertIn("tile_a", painter.regions)
        self.assertIn("tile_b", painter.regions)
        self.assertIn("tile_c", painter.regions)
        self.assertIn("tile_d", painter.regions)

        self.assertEqual((painter.tile_a.x, painter.tile_a.y), (0, 0))
        self.assertEqual((painter.tile_b.x, painter.tile_b.y), (16, 0))
        self.assertEqual((painter.tile_c.x, painter.tile_c.y), (0, 16))
        self.assertEqual((painter.tile_d.x, painter.tile_d.y), (16, 16))

    def test_make_seamless(self):
        painter = DecalCanvas(16, 16)
        painter.fill("#204060")
        painter.set_pixel(0, 5, "#ff0000")
        painter.set_pixel(15, 5, "#00ff00")

        painter.make_seamless(border_width=1)
        img = painter.compose()

        # Both left and right border at y=5 should now have blended equal colors
        left_c = img.getpixel((0, 5))
        right_c = img.getpixel((15, 5))
        self.assertEqual(left_c, right_c)

    def test_save_png(self):
        painter = DecalCanvas(16, 16)
        painter.fill("#abcdef")

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "sub" / "sprite.png"
            saved_path = painter.save(out_file)
            self.assertTrue(Path(saved_path).exists())

            with Image.open(saved_path) as loaded:
                self.assertEqual(loaded.size, (16, 16))
                self.assertEqual(loaded.format, "PNG")


if __name__ == "__main__":
    unittest.main()
