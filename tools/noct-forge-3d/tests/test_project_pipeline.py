import json
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path

from Tools.asset_init import init_project
from Tools._resolve import resolve_asset, resolve_recipe
from Tools.project_manifest import inside, load_project, project_lock
from Tools.texture_variant import register_variant
from Tools.model_export import model_export
from Tools.animation_export import animation_export
from Tools.asset_build import asset_build
from Tools.forge import main as forge
from Tools.recipe_context import recipe_paths


class ProjectPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "collection"

    def test_repeatable_initialization_and_multiple_asset_stage_isolation(self):
        init_project(self.root, asset_id="hero", animation=True)
        init_project(self.root, asset_id="sword", mode="box")
        data = load_project(self.root)
        self.assertEqual(set(data["assets"]), {"hero", "sword"})
        hero = resolve_asset(f"{self.root}#hero")
        sword = resolve_asset(f"{self.root}#sword")
        self.assertFalse(hero.model.exists())
        script = hero.scripts / "generate_model.py"
        source = script.read_bytes()
        again = init_project(self.root, asset_id="hero", mode="box", animation=True)
        self.assertEqual(again["generate_model"], "EXISTS")
        self.assertEqual(script.read_bytes(), source)
        with self.assertRaisesRegex(ValueError, "Select an asset"):
            resolve_asset(self.root)
        report = model_export(f"{self.root}#hero")
        self.assertEqual(report["status"], "pass", report)
        self.assertFalse(sword.model.exists())
        self.assertEqual(resolve_asset(hero.model).asset_id, "hero")
        self.assertEqual(resolve_recipe(hero.model, "model"), script)
        # Animation runs immediately on the BBModel without UV or modeling.
        original = json.loads(hero.model.read_text())
        report = animation_export(f"{self.root}#hero")
        self.assertEqual(report["status"], "pass", report)
        after = json.loads(hero.model.read_text())
        self.assertEqual(original["elements"], after["elements"])
        self.assertFalse(after["unhandled_root_fields"]["model_as_code"]["uv_ready"])
        report = asset_build(f"{self.root}#hero", stages="uv,texture")
        self.assertEqual(report["status"], "pass", report)
        self.assertTrue(hero.texture.exists())
        self.assertFalse(sword.model.exists())

    def test_facade_selects_correct_asset(self):
        self.assertEqual(forge(["project", "init", str(self.root), "--asset", "hero"]), 0)
        self.assertEqual(forge(["asset", "init", str(self.root), "--asset", "sword"]), 0)
        self.assertEqual(forge(["model", str(self.root), "--asset", "sword", "--json"]), 0)
        self.assertFalse(resolve_asset(f"{self.root}#hero").model.exists())
        self.assertTrue(resolve_asset(f"{self.root}#sword").model.exists())
        self.assertEqual(forge(["inspect", str(self.root), "--asset=sword", "--summary"]), 0)

    def test_reinitialize_project_does_not_invent_asset_or_replace_recipes(self):
        forge(["project", "init", str(self.root), "--asset", "hero"])
        source = resolve_asset(f"{self.root}#hero").scripts / "generate_model.py"
        before = source.read_bytes()
        forge(["project", "init", str(self.root)])
        init_project(self.root)
        self.assertEqual(set(load_project(self.root)["assets"]), {"hero"})
        self.assertEqual(source.read_bytes(), before)
        self.assertFalse(resolve_asset(f"{self.root}#hero").model.exists())
        init_project(self.root, asset_id="sword")
        forge(["project", "init", str(self.root)])
        self.assertEqual(set(load_project(self.root)["assets"]), {"hero", "sword"})
        with self.assertRaisesRegex(ValueError, "asset"):
            init_project(self.root)

    def test_init_open_launches_shared_viewer_without_build_or_boilerplate(self):
        with patch("subprocess.Popen") as launch:
            self.assertEqual(forge(["project", "init", str(self.root), "--asset", "hero", "--open"]), 0)
        args = launch.call_args.args[0]
        self.assertEqual(args[1:3], ["-m", "Tools.model_viewer"])
        self.assertIn(str(self.root), args)
        self.assertIn("--serve", args)
        self.assertIn("--open", args)
        self.assertFalse(resolve_asset(f"{self.root}#hero").model.exists())
        self.assertFalse(list(self.root.rglob("*.html")))
        self.assertFalse(list(self.root.rglob("*.js")))

    def test_unregistered_directories_are_rejected_and_init_refuses_to_hide_models(self):
        self.root.mkdir()
        (self.root / "scripts").mkdir()
        model = self.root / "model.bbmodel"
        model.write_bytes(b'{"name":"manual","elements":[]}')
        recipe = self.root / "scripts/generate_model.py"
        recipe.write_text('raise RuntimeError("must never run without registration")')
        model_before, recipe_before = model.read_bytes(), recipe.read_bytes()
        with self.assertRaisesRegex(ValueError, "registered project"):
            resolve_asset(self.root)
        with self.assertRaisesRegex(ValueError, "no project.json"):
            init_project(self.root, asset_id="legacy")
        with self.assertRaisesRegex(ValueError, "registered project"):
            recipe_paths(recipe)
        self.assertEqual(model.read_bytes(), model_before)
        self.assertEqual(recipe.read_bytes(), recipe_before)

    def test_manifest_and_paths_cannot_escape_project(self):
        init_project(self.root, asset_id="hero")
        with self.assertRaises(ValueError):
            inside(self.root, "../outside")
        data = load_project(self.root)
        data["assets"]["hero"]["model"] = "../model.bbmodel"
        (self.root / "project.json").write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            resolve_asset(f"{self.root}#hero")

    def test_concurrent_registration_is_rejected_without_lost_assets(self):
        init_project(self.root, asset_id="hero")
        original = (self.root / "project.json").read_bytes()
        with project_lock(self.root):
            run = subprocess.run([sys.executable, "-m", "Tools.forge", "asset", "init", str(self.root), "--asset", "sword"],
                                 cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2, run.stdout+run.stderr)
            self.assertIn("registration is running", run.stderr)
            self.assertEqual((self.root / "project.json").read_bytes(), original)
            self.assertFalse((self.root / "scripts/sword").exists())
            with self.assertRaisesRegex(ValueError, "registration is running"):
                register_variant(f"{self.root}#hero", "angry")
        init_project(self.root, asset_id="sword")
        register_variant(f"{self.root}#hero", "angry")
        manifest = load_project(self.root)
        self.assertEqual(set(manifest["assets"]), {"hero", "sword"})
        self.assertIn("angry", manifest["assets"]["hero"]["variants"])

    def test_variant_cannot_share_another_assets_writable_source(self):
        init_project(self.root, asset_id="hero")
        init_project(self.root, asset_id="sword")
        original = (self.root / "project.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "distinct file paths"):
            register_variant(f"{self.root}#hero", "angry", output="sword/texture.png")
        self.assertEqual((self.root / "project.json").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
