import json
import tempfile
import unittest
import subprocess
from pathlib import Path

from lib.model_builder import ModelBuilder
from lib.animation import AnimationEditor
from lib.primitives import quad_sphere
from Tools.model_viewer import export_standalone_html, VIEWER_DIR


@unittest.skipUnless(__import__("shutil").which("node"), "node missing: see `py -3.12 -m Tools.forge doctor`")
class ModelViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)

        self.model_path = self.temp_path / "model.bbmodel"
        self.output_html = self.temp_path / "preview.html"

        # Create a simple test model
        (
            ModelBuilder("viewer_test")
            .add_group("root")
            .add_cube("box_part", "root", from_=(0, 0, 0), to_=(4, 4, 4))
            .export_bbmodel(self.model_path)
        )

    def test_viewer_assets_exist(self):
        self.assertTrue((VIEWER_DIR / "index.html").exists())
        self.assertTrue((VIEWER_DIR / "vendor" / "three.min.js").exists())
        self.assertTrue((VIEWER_DIR / "vendor" / "OrbitControls.js").exists())
        self.assertTrue((VIEWER_DIR / "vendor" / "GLTFLoader.js").exists())
        self.assertTrue((VIEWER_DIR / "js" / "bbmodel_parser.js").exists())
        self.assertTrue((VIEWER_DIR / "js" / "scene_setup.js").exists())
        self.assertTrue((VIEWER_DIR / "js" / "animation_player.js").exists())
        self.assertTrue((VIEWER_DIR / "js" / "asset_loader.js").exists())
        self.assertTrue((VIEWER_DIR / "js" / "reference_plane.js").exists())
        self.assertTrue((VIEWER_DIR / "js" / "inspector.js").exists())
        self.assertTrue((VIEWER_DIR / "js" / "forge_sandbox.js").exists())
        self.assertTrue((VIEWER_DIR / "sandbox_template" / "index.html").exists())
        self.assertTrue((VIEWER_DIR / "sandbox_template" / "open.bat").exists())

    def test_two_servers_never_share_a_port(self):
        from Tools.viewer_server import ModelViewerServer
        first = ModelViewerServer(port=8970, model=self.model_path)
        self.addCleanup(first.server.server_close)
        second = ModelViewerServer(port=8970, model=self.model_path)
        self.addCleanup(second.server.server_close)
        self.assertNotEqual(first.port, second.port)

    def test_export_standalone_html_generates_valid_bundle(self):
        result = export_standalone_html(
            self.model_path,
            self.output_html,
            default_view="front",
            wireframe=True,
        )
        self.assertTrue(result.exists())
        content = result.read_text(encoding="utf-8")

        # Verify key elements are inlined
        self.assertIn("window.__EMBEDDED_BBMODEL__", content)
        self.assertIn("viewer_test", content)
        self.assertIn("BBModelParser", content)
        self.assertIn("SceneSetup", content)
        self.assertIn("ReferencePlane", content)
        self.assertIn("AnimationPlayer", content)
        self.assertIn("GLTFLoader", content)
        self.assertIn("loadAssetObject", content)
        self.assertIn("ModelInspector", content)
        self.assertGreater(len(content), 500_000)

    def test_animation_pose_and_weighted_mesh(self):
        check = Path(__file__).with_name("asset_loader_check.js")
        result = subprocess.run(["node", str(check)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_inspector_outliner_and_overlays(self):
        check = Path(__file__).with_name("inspector_check.js")
        result = subprocess.run(["node", str(check)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_original_animation_pose_and_weighted_mesh(self):
        check = Path(__file__).with_name("animation_viewer_check.js")
        result = subprocess.run(["node", str(check)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exported_armature_animates_in_viewer(self):
        builder = ModelBuilder("native-viewer", require_integer_dimensions=False)
        rig = builder.add_armature("rig")
        builder.add_mesh("body", rig, quad_sphere(radius=2, subdivisions=1))
        mesh = builder.last
        rig.add_bone("base", between=((0, -2, 0), (0, 0, 0)))
        rig.add_bone("tip", between=((0, 0, 0), (0, 2, 0)), parent="base")
        element = next(item for item in builder._elements if item.name == "body")
        rig.bind(mesh, weights={key: {"base": 0.5, "tip": 0.5} for key in element.vertices})
        builder.export_bbmodel(self.model_path)
        editor = AnimationEditor.from_bbmodel(self.model_path)
        editor.animation("bend", duration=1).bone("tip", armature="rig").key(
            0, rotation=(0, 0, 0)).key(1, rotation=(0, 0, 60))
        editor.save()
        check = Path(__file__).with_name("animation_viewer_check.js")
        result = subprocess.run(["node", str(check), str(self.model_path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
