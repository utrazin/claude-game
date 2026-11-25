import tempfile
import unittest
from pathlib import Path

import numpy as np

from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.ink import style
from Tools.TexturePainter.looks import LayerStyle, Look, Overlay, PaintLayer, Pass, Region, Style, paint_looks
from Tools.TexturePainter.marks import Brush, Tip
from Tools.TexturePainter.theme import define_theme, load_theme
from Tools import theme_tokens
from tests.fixtures_projection import collar_model

CHALK = Tip.grain(scale=0.08)
LAYERS = (PaintLayer("texture"), PaintLayer("shading"), PaintLayer("lighting"))


def look(**changes):
    base = Look(base=(60, 60, 90), colors={"light": ((120, 120, 160),), "shadow": ((20, 20, 40),)},
                tips={"tip": CHALK}, brush=Brush(radius=(0.3, 0.5)), sizes={"big": (0.3, 0.5)},
                stack=(Pass("mottle", "light", None, 0.5, 0.3, 2.0),
                       Pass("shadow", "shadow", (0.7, 0.2), (0.7, 0.2), 0.5, 3.0, layer="shading", strength="shadow"),
                       Pass("light", "light", (0.6, 1.0), (0.6, 1.0), 0.5, 3.0, layer="lighting")),
                strengths={"shadow": 1.0},
                layers={"shading": LayerStyle(overlay=Overlay((0, 0, 0), 0.4, (0.75, 0.1), tip=CHALK))})
    return base.but(**changes)


class ThemeTests(unittest.TestCase):
    def test_define_theme_checks_and_looks_tokens_up(self):
        theme = define_theme("t", palette={"ink": "#0e1222"}, tips={"chalk": CHALK},
                             brushes={"chalk": Brush()}, lines={"thick": style(width=2)}, layers=LAYERS,
                             styles={"default": Style("default", {"cloth": look()})})
        self.assertEqual(theme.color("ink")[:3], (14, 18, 34))
        self.assertIs(theme.tip("chalk"), CHALK)
        with self.assertRaises(KeyError) as caught:
            theme.brush("felt")
        self.assertIn("chalk", str(caught.exception))
        self.assertIn("tips", theme.summary())
        for bad in (dict(palette={"x": (300, 0, 0)}), dict(tips={"x": "chalk"}),
                    dict(styles={"s": Style("s", {"cloth": look(stack=(Pass("p", "nope", None, 1, 1, 1),))})},
                         layers=LAYERS),
                    dict(styles={"s": Style("s", {"cloth": look()})}),               # styles without layers
                    dict(layers=(PaintLayer("a"), PaintLayer("a")))):
            with self.subTest(bad=list(bad)), self.assertRaises(ValueError):
                define_theme("t", **bad)
        with self.assertRaises(TypeError):
            define_theme("t", colours={})

    def test_load_theme_and_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "proj"
            project.mkdir()
            (project / "project.json").write_text("{}", encoding="utf-8")
            self.assertIsNone(load_theme(project, required=False))
            with self.assertRaises(FileNotFoundError):
                load_theme(project)
            self.assertEqual(theme_tokens.main([str(project), "--init"]), 0)
            self.assertTrue((project / "STYLE.md").is_file())
            theme = load_theme(project)
            self.assertEqual(theme.name, "proj")
            self.assertEqual([l.name for l in theme.layers], ["texture", "shading", "lighting"])
            sheet = Path(folder) / "sheet.png"
            self.assertEqual(theme_tokens.main([str(project), "--sheet", str(sheet)]), 0)
            self.assertTrue(sheet.is_file())

    def test_style_problems(self):
        good = Style("s", {"cloth": look()})
        self.assertEqual(good.problems(["cloth"], [l.name for l in LAYERS]), [])
        cases = {
            "missing material": Style("s", {"cloth": look()}).problems(["cloth", "fur"]),
            "unknown layer": Style("s", {"cloth": look(stack=(Pass("p", "light", None, 1, 1, 1, layer="glaze"),))})
            .problems((), ["texture"]),
            "bad overlay": Style("s", {"cloth": look(layers={"shading": LayerStyle(overlay=Overlay(amount=2))})})
            .problems(),
            "region without selector": Style("s", {"cloth": look()}, regions={"r": Region("cloth")}).problems(),
            "region of an unknown material": Style("s", {"cloth": look()},
                                                   regions={"r": Region("fur", on=("x",))}).problems(),
            "no default tip": Style("s", {"cloth": look(tips={"veil": CHALK})}).problems(),
        }
        for label, problems in cases.items():
            with self.subTest(case=label):
                self.assertTrue(problems)


class PaintLooksTests(unittest.TestCase):
    def test_layers_are_written_to_painter_layers(self):
        with tempfile.TemporaryDirectory() as folder:
            painter = TexturePainter.from_bbmodel(collar_model(Path(folder) / "c.bbmodel"), render="pixel")
            view = painter.surface()

            def classify(v):
                material = np.where(v.group == "lip", -1, 0)
                return ("cloth",), material, np.clip(v.normal[:, 2] * 0.5 + 0.5, 0, 1), np.full((v.count, 3), 200.0)
            materials = painter.material_map(classify)
            image = paint_looks(painter, Style("s", {"cloth": look()}), materials, LAYERS)
            self.assertEqual(image.shape, (view.count, 3))
            lip = view.group == "lip"
            np.testing.assert_allclose(image[lip], 200.0)                     # no material keeps its fixed colour
            full = np.asarray(painter.compose_atlas()).astype(float)
            plain = np.asarray(painter.compose_atlas(hide=("shading", "lighting"))).astype(float)
            texels = full[view.y, view.x, :3]
            np.testing.assert_allclose(texels, image, atol=2.0)               # the painter layers add up to it
            self.assertGreater(np.abs(texels - plain[view.y, view.x, :3]).max(), 10)   # shading and light show


if __name__ == "__main__":
    unittest.main()
