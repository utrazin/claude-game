"""The cloaked_cat project's theme: it checks, every style of the cat is valid for every material, and the card's
passes paint texture, then shading, then lighting."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "cloaked_cat"
SCRIPTS = PROJECT / "scripts" / "cloaked_cat"


@unittest.skipUnless((PROJECT / "theme.py").is_file(), "the cloaked_cat project is not in this checkout")
class CatThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from Tools.TexturePainter.theme import load_theme
        cls.theme = load_theme(PROJECT)
        sys.path.insert(0, str(SCRIPTS))
        import regions
        import styles
        cls.styles, cls.materials = styles, list(regions.MATERIALS)

    @classmethod
    def tearDownClass(cls):
        if str(SCRIPTS) in sys.path:
            sys.path.remove(str(SCRIPTS))

    def layer_names(self):
        return [layer.name for layer in self.theme.layers]

    def test_the_theme_checks(self):
        self.assertEqual(self.theme.problems(), [])
        self.assertEqual(self.layer_names(), ["texture", "shading", "lighting"])

    def test_every_style_of_the_cat_is_valid_for_every_material(self):
        for name, style in {**self.styles.STYLES, **self.styles.ARCHIVED}.items():
            with self.subTest(style=name):
                style.validate(self.materials, self.layer_names())

    def test_every_palette_makes_a_valid_style(self):
        from Tools.TexturePainter.looks import Style
        extras = self.theme.extras
        for name, palette in extras["palettes"].items():
            with self.subTest(palette=name):
                Style(name, extras["looks"](palette)).validate(self.materials, self.layer_names())

    def test_card_passes_paint_texture_then_shading_then_lighting(self):
        order = self.layer_names()
        for stack in self.theme.extras["stacks"].values():
            layers = [p.layer for p in stack]
            self.assertEqual(layers, sorted(layers, key=order.index))


if __name__ == "__main__":
    unittest.main()
