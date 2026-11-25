"""Pixel art must not change when painting is refactored: repaint the cat's main texture from its recipe and compare
it, texel by texel, with the PNG the repository stores for that asset (the pixel-art version, archived in the
project's legacy/ folder; it is not a registered asset, so it paints in pixel mode)."""
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from Tools.TexturePainter import TexturePainter

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "cloaked_cat"
ASSET = PROJECT / "legacy" / "assets" / "cloaked_cat_v2"
RECIPES = PROJECT / "legacy" / "scripts" / "cloaked_cat_v2"


@unittest.skipUnless((ASSET / "model.bbmodel").exists() and (ASSET / "texture.png").exists(),
                     "the cloaked_cat project is not in this checkout")
class PixelGoldenTests(unittest.TestCase):
    def test_the_cat_main_texture_is_bit_identical(self):
        sys.path.insert(0, str(RECIPES))
        try:
            import generate_texture as recipe
            import lines
            painter = TexturePainter.from_bbmodel(ASSET / "model.bbmodel")
            self.assertFalse(painter.render.smooth)
            painter.fill_all(recipe.FUR[1] + (255,))
            for element in painter.all_elements():
                element.paint_surface_arrays(recipe.array_painter(element.name))
            painter.paint_strokes(lines.build_strokes(), offset=lines.recipe_offset).require_nonempty()
        finally:
            sys.path.remove(str(RECIPES))
        painted = np.asarray(painter.compose_atlas(edge_dilation=1)).astype(int)
        stored = np.asarray(Image.open(ASSET / "texture.png").convert("RGBA")).astype(int)
        self.assertEqual(painted.shape, stored.shape)
        differing = np.argwhere(np.abs(painted - stored).max(axis=2) > 0)
        self.assertEqual(len(differing), 0, f"{len(differing)} texels differ, first at (y, x) = {differing[:3].tolist()}")


if __name__ == "__main__":
    unittest.main()
