import json
import tempfile
import unittest
from pathlib import Path

from Tools.asset_build import asset_build
from Tools.asset_init import init_project
from Tools.asset_twin import create, sync
from Tools.model_export import model_export
from Tools.project_manifest import load_project
from Tools.texture_export import texture_export
from Tools.TexturePainter import TexturePainter
from Tools._resolve import resolve_asset, resolve_recipe


def packing(model):
    return json.loads(Path(model).read_text(encoding="utf-8"))["unhandled_root_fields"]["model_as_code"]["uv_packing"]


class AssetTwinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "collection"
        init_project(self.root, asset_id="hero")
        self.assertEqual(model_export(f"{self.root}#hero")["status"], "pass")
        self.assertEqual(asset_build(f"{self.root}#hero", stages="uv,texture")["status"], "pass")

    def test_a_smooth_twin_shares_the_model_and_recipes_with_its_own_uvs(self):
        create(self.root, "hero", "hero_smooth", "smooth")
        record = load_project(self.root)["assets"]["hero_smooth"]
        self.assertEqual(record["twin_of"], "hero")
        self.assertEqual(record["texture_filter"], "linear")
        hero, twin = resolve_asset(f"{self.root}#hero"), resolve_asset(f"{self.root}#hero_smooth")
        self.assertEqual(packing(twin.model)["uv_scale"], 16)
        self.assertEqual(packing(twin.model)["island_padding"], 4)
        source = json.loads(hero.model.read_text(encoding="utf-8"))
        copy = json.loads(twin.model.read_text(encoding="utf-8"))
        geometry = lambda doc: [(e["name"], e.get("from"), e.get("to"), e.get("vertices")) for e in doc["elements"]]
        self.assertEqual(geometry(source), geometry(copy))
        self.assertEqual(resolve_recipe(twin.model, "texture"), hero.scripts / "generate_texture.py")
        with self.assertRaisesRegex(ValueError, "twin"):
            resolve_recipe(twin.model, "model")
        self.assertTrue(TexturePainter.from_bbmodel(twin.model).render.smooth)
        self.assertFalse(TexturePainter.from_bbmodel(hero.model).render.smooth)
        self.assertEqual(texture_export(f"{self.root}#hero_smooth")["status"], "pass")

    def test_sync_copies_the_source_model_again_and_keeps_the_twin_uv_options(self):
        create(self.root, "hero", "hero_smooth", "smooth")
        hero, twin = resolve_asset(f"{self.root}#hero"), resolve_asset(f"{self.root}#hero_smooth")
        document = json.loads(hero.model.read_text(encoding="utf-8"))
        document["elements"][0]["name"] = document["elements"][0]["name"] + "_edited"     # a manual edit
        hero.model.write_text(json.dumps(document), encoding="utf-8")
        sync(self.root, "hero_smooth")
        copy = json.loads(twin.model.read_text(encoding="utf-8"))
        self.assertEqual(copy["elements"][0]["name"], document["elements"][0]["name"])
        self.assertEqual(packing(twin.model)["uv_scale"], 16)
        with self.assertRaises(ValueError):
            sync(self.root, "hero")                       # not a twin
        with self.assertRaises(ValueError):
            create(self.root, "hero_smooth", "again", "smooth")   # twins of twins are refused


if __name__ == "__main__":
    unittest.main()
