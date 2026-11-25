import json
import tempfile
import unittest
from pathlib import Path

from lib.model_builder import ModelBuilder
from Tools.model_export import audit_model_file
from Tools.asset_status import asset_status
from Tools.texture_export import texture_export


class ModelPipelineTests(unittest.TestCase):
    def test_standard_audit_reports_a_clean_model_compactly(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.bbmodel"
            ModelBuilder("clean").add_group("root").add_cube("body", "root", from_=(0, 0, 0), to_=(2, 2, 2)).export_bbmodel(model)
            report = audit_model_file(model)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["metrics"]["low_poly_issues"], 0)

    def test_asset_status_checks_uv_ready(self):
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            init_project(project_dir, asset_id="hero")
            model = resolve_asset(f"{project_dir}#hero").model
            ModelBuilder("test").add_group("root").add_cube("b", "root", from_=(0, 0, 0), to_=(2, 2, 2)).export_bbmodel(model)
            # Before UV packing: uv_ready is false
            status = asset_status(project_dir)
            self.assertEqual(status["uv"]["status"], "MISSING")

            # With dummy uv_packing but uv_ready False: must still be MISSING
            data = json.loads(model.read_text(encoding="utf-8"))
            data.setdefault("unhandled_root_fields", {}).setdefault("model_as_code", {})["uv_packing"] = {"island_padding": 1}
            data["unhandled_root_fields"]["model_as_code"]["uv_ready"] = False
            model.write_text(json.dumps(data), encoding="utf-8")
            status2 = asset_status(project_dir)
            self.assertEqual(status2["uv"]["status"], "MISSING")

    def test_texture_export_requires_separate_uv_command(self):
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        with tempfile.TemporaryDirectory() as directory:
            project_dir = Path(directory)
            init_project(project_dir, asset_id="hero")
            context = resolve_asset(f"{project_dir}#hero")
            scripts_dir = context.scripts
            model = context.model
            ModelBuilder("test").add_group("root").add_cube("b", "root", from_=(0, 0, 0), to_=(2, 2, 2)).export_bbmodel(model)

            # Write a simple generate_texture.py
            recipe = scripts_dir / "generate_texture.py"
            recipe.write_text(
                "from Tools.TexturePainter import TexturePainter\n"
                "from Tools.recipe_context import recipe_paths\n"
                "paths = recipe_paths(__file__)\n"
                "painter = TexturePainter.from_bbmodel(paths.model)\n"
                "painter.fill_all((100, 100, 100, 255))\n"
                "painter.save(paths.texture, edge_dilation=1)\n",
                encoding="utf-8"
            )

            # Model starts with no UV packing
            data = json.loads(model.read_text(encoding="utf-8"))
            self.assertFalse(data.get("unhandled_root_fields", {}).get("model_as_code", {}).get("uv_ready", False))

            before = model.read_bytes()
            report = texture_export(project_dir)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["issues"][0]["code"], "UV_REQUIRED")
            self.assertEqual(model.read_bytes(), before)
            self.assertFalse(context.texture.exists())
            from Tools.uv_packer import BoxUVPacker
            BoxUVPacker.apply_to_bbmodel(model, island_padding=1)
            report = texture_export(project_dir)
            self.assertEqual(report["status"], "pass")

            # Model now has uv_ready True and valid texture.png
            after = json.loads(model.read_text(encoding="utf-8"))
            self.assertTrue(after["unhandled_root_fields"]["model_as_code"]["uv_ready"])
            self.assertTrue(context.texture.exists())

    def test_asset_init_creates_valid_and_exportable_scaffold(self):
        from Tools.asset_init import init_project
        from Tools.model_export import export_project

        with tempfile.TemporaryDirectory() as directory:
            proj = Path(directory) / "test_scaffold"
            results = init_project(proj, mode="free")
            self.assertTrue((proj / "scripts/test_scaffold/generate_model.py").exists())
            self.assertTrue((proj / "scripts/test_scaffold/generate_texture.py").exists())

            # The scaffolded generate_model.py must immediately export cleanly without any import errors
            report = export_project(proj)
            self.assertEqual(report["status"], "pass")
            self.assertTrue((proj / "assets/test_scaffold/model.bbmodel").exists())

            # Running init again without force must report EXISTS and not overwrite
            results2 = init_project(proj, mode="box")
            self.assertEqual(results2["generate_model"], "EXISTS")

    def test_export_fails_when_the_recipe_did_not_write_the_model(self):
        from Tools.asset_init import init_project
        from Tools.model_export import export_project

        with tempfile.TemporaryDirectory() as directory:
            proj = Path(directory) / "stale"
            init_project(proj, mode="free")
            self.assertEqual(export_project(proj)["status"], "pass")
            (proj / "scripts/stale/generate_model.py").write_text("print('nothing written')\n", encoding="utf-8")
            report = export_project(proj)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["issues"][0]["code"], "MODEL_NOT_UPDATED")

    def test_asset_init_cli_works_outside_the_repository_and_prints_no_extra_steps(self):
        import contextlib
        import io
        from Tools.asset_init import main

        with tempfile.TemporaryDirectory() as directory:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main([str(Path(directory) / "elsewhere")])
        self.assertEqual(code, 0)
        self.assertIn("created", out.getvalue())
        self.assertNotIn("Next steps", out.getvalue())


if __name__ == "__main__":
    unittest.main()

