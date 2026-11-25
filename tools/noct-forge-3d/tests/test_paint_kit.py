"""The cloaked_cat paint kit: every fabric of the library makes a valid material with the standard light and shade,
and the rules classify every texel (first match wins, fixed colours for holes, occlusion shapes)."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "cloaked_cat"
SCRIPTS = PROJECT / "scripts"


@unittest.skipUnless((SCRIPTS / "paint_kit" / "__init__.py").is_file(), "the cloaked_cat paint kit is not here")
class PaintKitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(SCRIPTS))
        import paint_kit
        cls.kit = paint_kit

    @classmethod
    def tearDownClass(cls):
        if str(SCRIPTS) in sys.path:
            sys.path.remove(str(SCRIPTS))

    def layers(self):
        return [layer.name for layer in self.kit.THEME.layers]

    def test_every_fabric_makes_a_valid_material_with_the_standard_tone(self):
        base, light, dark = (90, 80, 100), [(110, 100, 120)], [(60, 50, 70)]
        for name in self.kit.FABRICS:
            with self.subTest(fabric=name):
                look = self.kit.material(name, base, light, dark)
                self.assertEqual(look.problems(name, self.layers()), [])
                tone = [p for p in look.stack if p.layer != "texture"]
                self.assertEqual(tone, [self.kit.TONE_SHADE, self.kit.TONE_LIGHT])
                self.assertEqual(look.colors["neutral_dark"], (self.kit.shade_color(base),))
                if name != "smooth":
                    self.assertTrue(any(p.layer == "texture" for p in look.stack))

    def test_rules_classify_every_texel_first_match_wins(self):
        from lib import ModelBuilder
        from Tools.TexturePainter import TexturePainter
        from Tools.uv_builder import UVBuilder
        kit = self.kit
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "model.bbmodel"
            builder = ModelBuilder("parts", require_integer_dimensions=False).add_group("root")
            builder.add_cylinder("body", "root", radius=2, height=4, segments=8)
            builder.add_cylinder("hat", "root", radius=1, height=1, segments=8)
            builder.export_bbmodel(model)
            UVBuilder(model, start_size=(64, 64), uv_scale=4, island_padding=1).save()
            view = TexturePainter.from_bbmodel(model).surface()
            materials = {"fur": kit.material("fur", (90, 80, 100)), "cloth": kit.material("chalk", (40, 80, 60))}
            rules = [kit.Rule(color=(10, 8, 18), on=("hat",)),
                     kit.Rule("cloth", on=("body",), where=lambda p, n: p[:, 1] < 2.0,
                              occlusion=kit.below(0.0, 2.0, 0.5)),
                     kit.Rule("fur", on=("body",))]
            names, material, value, fixed, occlusion = kit.classify.classifier(
                materials, rules, light=kit.X["light"])(view)
            self.assertEqual(names, ("fur", "cloth"))
            hat = view.select("hat")
            self.assertTrue((material[hat] == -1).all() and (fixed[hat] == (10, 8, 18)).all())
            low = ~hat & (view.position[:, 1] < 2.0)
            self.assertTrue((material[low] == 1).all() and (material[~hat & ~low] == 0).all())
            self.assertTrue((occlusion[~low] == 0).all() and occlusion[low].max() > 0.2)
            self.assertTrue((value >= 0).all() and (value <= 1.0 + 1e-9).all())
            with self.assertRaises(ValueError):          # a texel no rule paints is an error
                kit.classify.classifier(materials, rules[1:2], light=kit.X["light"])(view)


    def test_item_lines_follow_the_construction(self):
        """``paint_kit.items`` reads an item_kit model's rings: a lathe's surface points lie on its rings, a level
        ring closes, and a plate's ridge line runs through one point of every ring."""
        sys.path.insert(0, str(SCRIPTS / "item_kit"))
        try:
            import item_kit as ik
        finally:
            sys.path.remove(str(SCRIPTS / "item_kit"))
        from paint_kit import items
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "model.bbmodel"
            it = ik.Item("probe")
            ik.lathe(it, "grip", [(0.0, 0.8), (2.0, 0.8), (4.0, 0.8)], n=8, max_span=None)
            ik.plate(it, "blade", [ik.Row(5.0, -1.0, 1.0, 0.2, ridge=0.0, ridge_th=0.4),
                                   ik.Row(9.0, -0.8, 0.8, 0.2, ridge=0.0, ridge_th=0.4)], apex=(None, (11.0, 0.0)))
            it.export(model)
            mesh = items.Mesh(model)
            self.assertEqual(len(mesh.rings("grip", "r")), 3)
            p = np.array(items.surface_point(mesh, "grip", 0.3, 2.0))
            self.assertAlmostEqual(p[1], 2.0, places=6)
            self.assertTrue(0.7 < np.hypot(p[0], p[2]) <= 0.8 + 1e-6)     # on the octagon, not off it
            self.assertTrue(items.level_ring(mesh, "grip", 1.0).closed)
            ridge = items.ring_line(mesh, "blade", items.PLATE_RIDGED["ridge_front"])
            names = ridge.data[1]
            self.assertEqual(len(names), len(mesh.rings("blade", "u")))
            self.assertTrue(all(n.endswith("_03") for n in names))
            self.assertTrue(all(mesh.point("blade", n)[2] > 0.3 for n in names[:2]))   # the front ridge: +Z


if __name__ == "__main__":
    unittest.main()
