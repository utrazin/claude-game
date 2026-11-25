import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from Tools.asset_init import init_project
from Tools._resolve import resolve_asset
from Tools.asset_build import asset_build
from Tools.texture_variant import register_variant
from Tools.viewer_server import ModelViewerServer
from Tools.model_viewer import export_standalone_html
from lib import AnimationEditor


class ProjectViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "collection"
        init_project(self.root, asset_id="hero", animation=True)
        self.context = resolve_asset(f"{self.root}#hero")
        self.server = ModelViewerServer(port=0, project=self.root)
        self.thread = threading.Thread(target=self.server.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = f"http://127.0.0.1:{self.server.port}"

    def close_server(self):
        self.server.server.shutdown()
        self.server.server.server_close()
        self.thread.join(timeout=3)

    def test_scope_catalog_and_exact_registered_model(self):
        catalog = json.load(urllib.request.urlopen(self.url+"/api/catalog"))
        self.assertEqual([asset["id"] for asset in catalog["assets"]], ["hero"])
        self.assertIsNone(catalog["assets"][0]["stamp"])
        self.assertEqual(asset_build(f"{self.root}#hero", stages="model,uv,texture")["status"], "pass")
        response = json.load(urllib.request.urlopen(self.url+"/api/assets/hero/model"))
        self.assertEqual(response["name"], "hero")
        self.assertEqual(response["textures"][0]["relative_path"], "/api/assets/hero/texture/0")
        outside = Path(self.tmp.name) / "outside.png"
        Image.new("RGBA", (16,16)).save(outside)
        from Tools.model_viewer import to_server_url
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.url+to_server_url(outside))
        self.assertEqual(error.exception.code, 403)
        for path in ("/Tools/model_export.py", "/js/../../AGENTS.md", "/api/assets/unknown/model"):
            with self.assertRaises(urllib.error.HTTPError):
                urllib.request.urlopen(self.url+path)

    def test_browser_empty_state_selection_variants_and_file_refresh(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"])
            try:
                page = browser.new_page(viewport={"width":1000,"height":750})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(self.url)
                page.wait_for_function("window.__VIEWER_READY__ === true")
                self.assertIn("não gerado", page.locator("#asset-message").inner_text())
                self.assertFalse(self.context.model.exists())
                self.assertEqual(asset_build(f"{self.root}#hero", stages="model,uv,texture,animation")["status"], "pass")
                page.wait_for_function("currentModelData && currentModelData.name === 'hero'", timeout=10000)
                before = self.context.model.read_bytes()
                recipe = self.context.scripts / "generate_model.py"
                recipe_before = recipe.read_bytes()
                register_variant(f"{self.root}#hero", "angry")
                path = self.context.directory / "textures/angry.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                resolution = json.loads(before)["resolution"]
                Image.new("RGBA", (resolution["width"],resolution["height"]), "red").save(path)
                page.wait_for_function("[...document.querySelector('#texture-select').options].some(option => option.value === 'angry')")
                page.select_option("#texture-select", "angry")
                page.wait_for_function("window.__VIEWER_VARIANT__ === 'angry' && parser.texture && parser.texture.image.src.includes('/variant/angry')")
                self.assertEqual(self.context.model.read_bytes(), before)
                init_project(self.root, asset_id="sword", mode="box")
                self.assertEqual(asset_build(f"{self.root}#sword", stages="model")["status"], "pass")
                page.wait_for_function("document.querySelectorAll('[data-asset]').length === 2")
                page.locator('[data-asset="sword"]').click()
                page.wait_for_function("currentModelData && currentModelData.name === 'sword'")
                page.locator('[data-asset="hero"]').click()
                page.wait_for_function("currentModelData && currentModelData.name === 'hero'")
                data = json.loads(self.context.model.read_text())
                data["name"] = "edited manually"
                self.context.model.write_text(json.dumps(data))
                page.wait_for_function("currentModelData && currentModelData.name === 'edited manually'", timeout=10000)
                self.assertEqual(recipe.read_bytes(), recipe_before)
                self.assertEqual(json.loads(self.context.model.read_text())["name"], "edited manually")
                self.assertFalse(errors, errors)
                review = Path(__file__).resolve().parents[1] / ".runtime/checks"
                review.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(review / "project-viewer.png"))
            finally:
                browser.close()

    def test_native_multiple_textures_and_external_controls_in_viewer_and_standalone(self):
        self.context.directory.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (16,32), "red").save(self.context.directory / "red.png")
        Image.new("RGBA", (32,16), "blue").save(self.context.directory / "blue.png")
        faces = {name: {"texture": None} for name in ("north", "south", "east", "west", "up", "down")}
        faces.update(north={"texture": 0, "uv": [0,0,8,16]}, south={"texture": 1, "uv": [0,0,16,8]})
        data = {"name": "external two atlas model", "meta": {"model_format": "free"},
                "resolution": {"width": 8, "height": 16}, "elements": [
                    {"type": "cube", "uuid": "cube-id", "name": "head", "from": [0,0,0], "to": [4,4,4], "faces": faces}],
                "outliner": [{"uuid": "jaw-id", "name": "jaw", "origin": [0,2,0], "children": ["cube-id"]}],
                "textures": [{"id": "0", "relative_path": "red.png", "uv_width": 8, "uv_height": 16},
                             {"id": "1", "relative_path": "blue.png", "uv_width": 16, "uv_height": 8}]}
        self.context.model.write_text(json.dumps(data))
        editor = AnimationEditor.from_bbmodel(self.context.model)
        editor.animation("turn", duration=1).group("jaw").key(0, rotation=(0,0,0)).key(1, rotation=(0,90,0))
        editor.save()
        original = self.context.model.read_bytes()
        recipe = self.context.scripts / "generate_model.py"
        recipe.write_text('raise RuntimeError("viewer must not execute geometry")')
        standalone = export_standalone_html(self.context.model, self.root / "renders/native.html")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"])
            try:
                for url in (self.url, standalone.as_uri()):
                    page = browser.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(url)
                    page.wait_for_function("window.__VIEWER_READY__ === true && parser && parser.textureList.length === 2")
                    summary = page.evaluate("""() => {
                        const meshes=[]; parser.rootObject.traverse(node=> {if(node.isMesh) meshes.push(node);});
                        return {images: parser.textureList.map(texture=>[texture.image.width,texture.image.height]),
                            controls: [...parser.controls.keys()], errors: parser.textureErrors,
                            faces: meshes[0].geometry.groups.map(group=>group.materialIndex),
                            uv: Array.from(meshes[0].geometry.attributes.uv.array)};
                    }""")
                    self.assertEqual(summary["images"], [[16,32],[32,16]])
                    self.assertEqual(summary["faces"], [0,1])
                    self.assertIn("jaw-id", summary["controls"])
                    self.assertFalse(summary["errors"])
                    self.assertTrue(all(0 <= value <= 1 for value in summary["uv"]))
                    page.evaluate("animationPlayer.select('turn'); animationPlayer.seek(1)")
                    rotation = page.evaluate("parser.controls.get('jaw-id').object.rotation.y")
                    import math
                    self.assertAlmostEqual(rotation, math.pi / 2)
                    self.assertFalse(errors, errors)
                    page.close()
            finally:
                browser.close()
        self.assertEqual(self.context.model.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
