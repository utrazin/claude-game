import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from Tools.asset_status import asset_status
from lib.animation import AnimationEditor
from lib import ModelBuilder
from unittest.mock import patch
from Tools.asset_init import init_project
from Tools._resolve import resolve_asset
from Tools.animation_export import animation_export
from Tools.texture_export import texture_export
from Tools.uv_packer import BoxUVPacker
from Tools.asset_export import asset_export


class IndependentStagesTests(unittest.TestCase):
    def test_downstream_stages_ignore_poisoned_geometry_recipe_and_use_manual_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "collection"
            init_project(root, asset_id="hero", animation=True)
            target = f"{root}#hero"
            context = resolve_asset(target)
            builder = ModelBuilder("manually edited", modeling_mode="box").add_group("root")
            builder.add_transform_group("body", "root", pivot=(0, 2, 0))
            builder.add_box("manual_shape", "body", size=(8, 4, 2), at=(0, 2, 0))
            builder.export_bbmodel(context.model)
            original = json.loads(context.model.read_bytes())["elements"]
            (context.scripts / "generate_model.py").write_text('raise RuntimeError("geometry recipe must not run")')
            self.assertEqual(animation_export(target)["status"], "pass")
            self.assertEqual(texture_export(target)["status"], "fail")
            self.assertFalse(context.texture.exists())
            BoxUVPacker.apply_to_bbmodel(context.model, island_padding=1)
            self.assertEqual(texture_export(target)["status"], "pass")
            self.assertEqual(asset_export(target, output="runtime/manual.glb")["status"], "pass")
            after = json.loads(context.model.read_bytes())["elements"]
            for old, new in zip(original, after):
                self.assertEqual(old["name"], new["name"])
                for field in ("from", "to", "origin", "rotation"):
                    self.assertEqual(old.get(field), new.get(field))

    def test_texture_cli_streams_recipe_output_to_stderr_and_keeps_json_clean(self):
        import contextlib
        import io
        from Tools import texture_export as texture_cli
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "collection"
            init_project(root, asset_id="hero")
            context = resolve_asset(f"{root}#hero")
            builder = ModelBuilder("streamed", modeling_mode="box").add_group("root")
            builder.add_box("shape", "root", size=(4, 4, 4), at=(0, 2, 0))
            builder.export_bbmodel(context.model)
            BoxUVPacker.apply_to_bbmodel(context.model, island_padding=1)
            recipe = context.scripts / "generate_texture.py"
            recipe.write_text('print("painting phase one")\nraise SystemExit("boom")\n', encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = texture_cli.main([f"{root}#hero", "--json"])
            self.assertEqual(code, 2)
            report = json.loads(out.getvalue())                       # stdout is only the JSON report
            self.assertIn("boom", report["issues"][0]["message"])
            self.assertIn("painting phase one", report["issues"][0]["message"])
            self.assertIn("[recipe] painting phase one", err.getvalue())
            self.assertIn("[recipe] failed in", err.getvalue())
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                texture_cli.main([f"{root}#hero", "--json", "--quiet"])
            self.assertEqual(err.getvalue(), "")

    def test_uv_does_not_overwrite_an_edit_made_while_packing(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.bbmodel"
            builder = ModelBuilder("initial").add_group("root")
            builder.add_box("body", "root", size=(2,2,2))
            builder.export_bbmodel(model)
            pack = BoxUVPacker.pack_document
            def concurrent_edit(data, **options):
                result = pack(data, **options)
                changed = json.loads(model.read_bytes())
                changed["name"] = "user edit"
                model.write_text(json.dumps(changed))
                return result
            with patch.object(BoxUVPacker, "pack_document", side_effect=concurrent_edit):
                with self.assertRaisesRegex(ValueError, "changed during UV"):
                    BoxUVPacker.apply_to_bbmodel(model)
            self.assertEqual(json.loads(model.read_bytes())["name"], "user edit")
    def test_external_model_animation_does_not_require_uv_or_model_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.bbmodel"
            source = {"meta": {"model_format": "bedrock"}, "elements": [],
                      "outliner": [{"uuid": "body-id", "name": "body", "children": []}]}
            model.write_text(json.dumps(source))
            editor = AnimationEditor.from_bbmodel(model)
            editor.animation("idle", duration=1, loop=True).group("body").key(0, rotation=(0, 0, 0)).key(1, rotation=(0, 0, 0))
            editor.save()
            after = json.loads(model.read_text())
            self.assertEqual(after["elements"], source["elements"])
            self.assertNotIn("resolution", after)
            self.assertEqual(after["animations"][0]["name"], "idle")

    def test_unreadable_model_does_not_hide_independent_texture(self):
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            init_project(root, asset_id="stages")
            context = resolve_asset(f"{root}#stages")
            context.model.write_text("invalid json")
            Image.new("RGBA", (16, 16)).save(context.texture)
            status = asset_status(root)
            self.assertEqual(status["model"]["status"], "FAIL")
            self.assertEqual(status["texture"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
