import tempfile
import unittest
from pathlib import Path

import numpy as np

from Tools.TexturePainter import TexturePainter
from tests.fixtures_projection import collar_model, painted_by_group


class SurfaceViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = collar_model(Path(self.temp.name) / "collar.bbmodel")

    def test_surface_lists_every_texel_with_element_and_group(self):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        view = painter.surface()
        total = sum(len(rows) for element in painter.all_elements()
                    for _face, rows in element._surface_region()._entries)
        self.assertEqual(view.count, total)
        self.assertEqual(set(view.element.tolist()), {"collar"})
        self.assertEqual(set(view.group.tolist()), {"outer", "inner", "lip"})
        self.assertEqual(int(view.select(groups="lip").sum()), int((view.group == "lip").sum()))
        self.assertFalse(view.select(on="nothing").any())

    def test_write_paints_the_chosen_texels(self):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        view = painter.surface()
        inner = np.flatnonzero(view.select(groups="inner"))
        view.write(np.tile([255, 0, 0, 255], (len(inner), 1)), inner)
        painted = painted_by_group(painter, "collar")
        self.assertEqual(painted.get("inner"), len(inner))
        self.assertEqual(painted.get("outer", 0), 0)

    def test_write_with_coverage_and_blend(self):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        view = painter.surface()
        everything = np.arange(view.count)
        view.write(np.tile([200, 200, 200, 255], (view.count, 1)))
        view.write(np.tile([0, 0, 0, 255], (view.count, 1)), everything, coverage=np.full(view.count, 0.5))
        face, rows = view.entries[0]
        grey = face.canvas.read_pixels(rows.x, rows.y)[0]
        self.assertTrue(90 <= grey[0] <= 110)                                    # half way to black
        view.write(np.tile([128, 128, 128, 255], (view.count, 1)), blend="multiply")
        darker = face.canvas.read_pixels(rows.x, rows.y)[0]
        self.assertLess(darker[0], grey[0])

    def test_material_map_is_cached_per_project(self):
        project = Path(self.temp.name) / "project"
        project.mkdir()
        (project / "project.json").write_text("{}", encoding="utf-8")
        model = collar_model(project / "collar.bbmodel")
        calls = []

        def classify(view):
            calls.append(1)
            material = np.where(view.group == "outer", 0, np.where(view.group == "inner", 1, -1))
            return ("cloth", "lining"), material, np.clip(view.normal[:, 2], 0, 1), np.zeros((view.count, 3))

        first = TexturePainter.from_bbmodel(model, render="pixel").material_map(classify)
        second = TexturePainter.from_bbmodel(model, render="pixel").material_map(classify)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first.names, ("cloth", "lining"))
        np.testing.assert_array_equal(first.material, second.material)
        self.assertEqual(first.present(), ["cloth", "lining"])
        self.assertEqual(int(first.mask("lining").sum()), int((second.material == 1).sum()))
        with self.assertRaises(KeyError):
            first.mask("fur")

    def test_occlusion_darkens_after_normalisation_and_is_cached(self):
        from Tools.TexturePainter.looks import shading_fields
        project = Path(self.temp.name) / "project2"
        project.mkdir()
        (project / "project.json").write_text("{}", encoding="utf-8")
        model = collar_model(project / "collar.bbmodel")

        def classify(view):
            low = view.centre[:, 1] < 1.0
            return ("cloth",), np.zeros(view.count, dtype=int), np.clip(view.normal[:, 2], 0, 1), \
                np.zeros((view.count, 3)), np.where(low, 0.5, 0.0)

        painter = TexturePainter.from_bbmodel(model, render="pixel")
        first = painter.material_map(classify)
        second = TexturePainter.from_bbmodel(model, render="pixel").material_map(lambda view: 1 / 0)   # cached
        np.testing.assert_array_equal(first.occlusion, second.occlusion)
        view = painter.surface()
        v, _lit = shading_fields(view, first, np.ones(view.count, dtype=bool))
        plain, _ = shading_fields(view, type(first)(first.names, first.material, first.value, first.fixed),
                                  np.ones(view.count, dtype=bool))
        low = first.occlusion > 0
        self.assertTrue(low.any())
        np.testing.assert_allclose(v[low], plain[low] * 0.5)
        np.testing.assert_allclose(v[~low], plain[~low])

    def test_material_map_rejects_bad_shapes(self):
        painter = TexturePainter.from_bbmodel(self.model, render="pixel")
        with self.assertRaises(ValueError):
            painter.material_map(lambda view: (("a",), np.zeros(3), np.zeros(3), np.zeros((3, 3))))


if __name__ == "__main__":
    unittest.main()
