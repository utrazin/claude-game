"""Unit tests for Tools.asset_build unified pipeline runner."""

import json
import tempfile
import unittest
from pathlib import Path

from Tools.asset_init import generate_model_template, init_project
from Tools._resolve import resolve_asset
from Tools.asset_build import asset_build


class AssetBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.tmp.name) / "test_hero"
        init_project(self.project_dir, asset_id="hero")
        self.context = resolve_asset(f"{self.project_dir}#hero")
        self.model = self.context.model
        self.texture = self.project_dir / "assets" / "hero" / "texture.png"

        # Write model recipe
        template = generate_model_template("hero", mode="free")
        (self.context.scripts / "generate_model.py").write_text(template, encoding="utf-8")

        # Write texture recipe
        tex_code = '''"""Texture authoring recipe."""
from Tools.TexturePainter import TexturePainter
from Tools.recipe_context import recipe_paths

def main():
    paths = recipe_paths(__file__)
    painter = TexturePainter.from_bbmodel(paths.model)
    painter.fill_all((120, 140, 160, 255))
    painter.save(paths.texture, edge_dilation=1)

if __name__ == "__main__":
    main()
'''
        (self.context.scripts / "generate_texture.py").write_text(tex_code, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_asset_build_runs_all_stages(self):
        # Initial run: builds model and paints texture
        rep1 = asset_build(self.project_dir, stages="model,uv,texture")
        self.assertEqual(rep1["status"], "pass")
        self.assertIn("model", rep1["steps"])
        self.assertIn("texture", rep1["steps"])

        self.assertTrue(self.model.exists())
        self.assertTrue(self.texture.exists())

        # A no-op request cannot silently select or rebuild any stages.
        with self.assertRaisesRegex(ValueError, "explicitly"):
            asset_build(self.project_dir)
        original = self.model.read_bytes()
        rep2 = asset_build(self.project_dir, stages="texture")
        self.assertEqual(rep2["status"], "pass")
        self.assertEqual(rep2["steps"], ["texture"])

        rep3 = asset_build(self.project_dir, stages="model,uv,texture")
        self.assertEqual(rep3["status"], "pass")
        self.assertIn("model", rep3["steps"])
        self.assertIn("texture", rep3["steps"])

    def test_missing_model_never_triggers_model_recipe(self):
        rep = asset_build(self.project_dir, stages="texture")
        self.assertEqual(rep["status"], "fail")
        self.assertEqual(rep["steps"], ["texture"])
        self.assertFalse(self.model.exists())

    def test_manual_geometry_policy_does_not_execute_recipe(self):
        recipe = self.context.scripts / "generate_model.py"
        recipe.write_text('ASSET_BUILD_GEOMETRY = "manual"\nraise RuntimeError("must not execute")\n')
        rep = asset_build(self.project_dir, stages="model")
        self.assertEqual(rep["status"], "fail")
        self.assertEqual(rep["steps"], [])
        self.assertEqual(rep["skipped"][0]["stage"], "model")
        self.assertFalse(self.model.exists())

    def test_manual_existing_model_is_preserved(self):
        from Tools.model_export import model_export
        self.assertEqual(model_export(self.project_dir)["status"], "pass")
        model = self.model
        original = model.read_bytes()
        recipe = self.context.scripts / "generate_model.py"
        recipe.write_text('ASSET_BUILD_GEOMETRY = "manual"\nraise RuntimeError("must not execute")\n')
        report = asset_build(self.project_dir, stages="model")
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["steps"], [])
        self.assertEqual(model.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
