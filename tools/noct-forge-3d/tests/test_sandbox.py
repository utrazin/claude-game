import json
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

from PIL import Image

from Tools.asset_init import init_project
from Tools.asset_build import asset_build
from Tools.sandbox import create_sandbox
from Tools.model_viewer import resolve_sandbox_target
from Tools.viewer_server import ModelViewerServer
from Tools.capture_preview import capture_sandbox


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projects_root = Path(self.tmp.name) / "projects"
        self.projects_root.mkdir()

        # Initialize test project
        self.project_a = self.projects_root / "proj_alpha"
        init_project(self.project_a, asset_id="crystal", animation=False)

        # Global server
        self.server = ModelViewerServer(port=0, projects_root=self.projects_root)
        self.thread = threading.Thread(target=self.server.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._close_server)
        self.url = f"http://127.0.0.1:{self.server.port}"

    def _close_server(self):
        self.server.server.shutdown()
        self.server.server.server_close()
        self.thread.join(timeout=3)

    def test_create_sandbox_scaffolds_files(self):
        sb_dir = create_sandbox(self.project_a, "playground")
        self.assertTrue(sb_dir.is_dir())
        self.assertEqual(sb_dir.name, "playground")
        self.assertEqual(sb_dir.parent.name, "sandboxes")

        index_file = sb_dir / "index.html"
        open_bat = sb_dir / "open.bat"
        self.assertTrue(index_file.is_file())
        self.assertTrue(open_bat.is_file())

        index_content = index_file.read_text(encoding="utf-8")
        self.assertIn("playground", index_content)
        self.assertIn("proj_alpha", index_content)
        self.assertIn("/lib/forge_sandbox.js", index_content)

        bat_content = open_bat.read_text(encoding="utf-8")
        self.assertIn("Tools.forge view --all --open --sandbox", bat_content)

    def test_create_sandbox_refuses_overwrite(self):
        create_sandbox(self.project_a, "test_existing")
        with self.assertRaises(FileExistsError):
            create_sandbox(self.project_a, "test_existing")

    def test_create_sandbox_validates_identifier(self):
        with self.assertRaises(ValueError):
            create_sandbox(self.project_a, "invalid name!")
        with self.assertRaises(ValueError):
            create_sandbox(self.project_a, "../escape")
        with self.assertRaises(ValueError):
            create_sandbox(self.project_a, "CON")

    def test_create_sandbox_nonexistent_project_fails(self):
        with self.assertRaises(ValueError):
            create_sandbox(Path(self.tmp.name) / "nonexistent", "play")

    def test_cli_forge_sandbox(self):
        cmd = [
            sys.executable,
            "-m",
            "Tools.forge",
            "sandbox",
            str(self.project_a),
            "cli_box",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[sandbox] Created:", result.stdout)
        self.assertTrue((self.project_a / "sandboxes" / "cli_box" / "index.html").is_file())

    def test_resolve_sandbox_target_uses_last_sandboxes_component(self):
        nested = Path(self.tmp.name) / "sandboxes" / "proj_beta" / "sandboxes" / "plaza"
        nested.mkdir(parents=True)
        info = resolve_sandbox_target(str(nested))
        self.assertEqual((info["project"], info["name"]), ("proj_beta", "plaza"))

    def test_resolve_sandbox_target_helper(self):
        sb_dir = self.project_a / "sandboxes" / "arena"
        sb_dir.mkdir(parents=True)
        (sb_dir / "index.html").write_text("arena", encoding="utf-8")

        # 1. From exact path with "sandboxes"
        info = resolve_sandbox_target(str(sb_dir))
        self.assertEqual(info["project"], "proj_alpha")
        self.assertEqual(info["name"], "arena")

        # 2. From project hint and name
        info2 = resolve_sandbox_target("arena", project_hint="proj_alpha")
        self.assertEqual(info2["project"], "proj_alpha")
        self.assertEqual(info2["name"], "arena")

        # 3. From project/sandbox path
        info3 = resolve_sandbox_target("proj_alpha/arena")
        self.assertEqual(info3["project"], "proj_alpha")
        self.assertEqual(info3["name"], "arena")

    def test_http_serving_sandbox_and_lib(self):
        create_sandbox(self.project_a, "web_view")

        # Check /lib/forge_sandbox.js
        with urllib.request.urlopen(f"{self.url}/lib/forge_sandbox.js") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type"))
            content = resp.read().decode("utf-8")
            self.assertIn("ForgeSandbox", content)

        # Check /sandbox/proj_alpha/web_view/
        with urllib.request.urlopen(f"{self.url}/sandbox/proj_alpha/web_view/") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type"))
            html = resp.read().decode("utf-8")
            self.assertIn("web_view", html)

    def test_canonical_routes_and_rejected_aliases(self):
        create_sandbox(self.project_a, "flex_view")
        with urllib.request.urlopen(f"{self.url}/sandbox/proj_alpha/flex_view") as response:
            self.assertTrue(response.url.endswith("/flex_view/"))
        for path in ("/sandbox/", "/sandbox/proj_alpha/", "/sandbox/flex_view/", "/sandbox/proj_alpha/index.html"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(self.url + path)
            self.assertEqual(error.exception.code, 404)

    def test_sandbox_error_reporting(self):
        create_sandbox(self.project_a, "err_view")

        # Missing sandbox
        try:
            urllib.request.urlopen(f"{self.url}/sandbox/proj_alpha/missing_box/")
            self.fail("Expected 404")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 404)
            data = json.loads(err.read().decode("utf-8"))
            self.assertIn("Sandbox 'missing_box' not found", data.get("error", ""))

        # Missing file inside existing sandbox
        try:
            urllib.request.urlopen(f"{self.url}/sandbox/proj_alpha/err_view/missing_file.png")
            self.fail("Expected 404")
        except urllib.error.HTTPError as err:
            self.assertEqual(err.code, 404)
            data = json.loads(err.read().decode("utf-8"))
            self.assertIn("File 'missing_file.png' not found in sandbox 'err_view'", data.get("error", ""))

    def test_ambiguous_targets_are_rejected(self):
        for target in ("auto_disc", "proj_alpha"):
            with self.assertRaises(ValueError):
                resolve_sandbox_target(target, projects_root=self.projects_root)

    def test_sandbox_playwright_e2e(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.skipTest("playwright not installed")

        # Build asset so BBModel exists
        asset_build(f"{self.project_a}#crystal", stages="model,uv,texture")
        sb_dir = create_sandbox(self.project_a, "e2e_box")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"]
            )
            try:
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))

                page.goto(f"{self.url}/sandbox/proj_alpha/e2e_box/")
                page.wait_for_function("window.__VIEWER_READY__ === true")

                # Verify sandbox badge and title
                badge_title = page.text_content("#badge-title")
                self.assertEqual(badge_title, "e2e_box")

                # Verify Three.js scene instances
                summary = page.evaluate("""() => {
                    return {
                        appChildren: document.getElementById('app').children.length,
                        hasThree: typeof THREE !== 'undefined',
                        hasForgeSandbox: typeof ForgeSandbox !== 'undefined'
                    };
                }""")
                self.assertGreater(summary["appChildren"], 0)
                self.assertTrue(summary["hasThree"])
                self.assertTrue(summary["hasForgeSandbox"])

                self.assertFalse(errors, errors)
                page.close()
            finally:
                browser.close()

    def test_capture_sandbox_multiple_views(self):
        try:
            import playwright
        except ImportError:
            self.skipTest("playwright not installed")

        # Build asset so BBModel exists
        asset_build(f"{self.project_a}#crystal", stages="model,uv,texture")
        create_sandbox(self.project_a, "capture_box")

        results = capture_sandbox(
            self.project_a,
            "capture_box",
            views=["iso", "front"],
            at_ms=50,
            transparent=True,
            resolution=(400, 400),
        )

        self.assertIn("iso", results)
        self.assertIn("front", results)

        iso_file = Path(results["iso"])
        front_file = Path(results["front"])
        self.assertTrue(iso_file.is_file())
        self.assertTrue(front_file.is_file())
        self.assertGreater(iso_file.stat().st_size, 500)
        self.assertGreater(front_file.stat().st_size, 500)

        # Default path must be sandboxes/<name>/renders/<view>.png
        expected_dir = self.project_a / "sandboxes" / "capture_box" / "renders"
        self.assertEqual(iso_file.parent.resolve(), expected_dir.resolve())
        self.assertEqual(front_file.parent.resolve(), expected_dir.resolve())

        with Image.open(iso_file) as img:
            self.assertEqual(img.size, (400, 400))
            self.assertEqual(img.mode, "RGBA")

    def test_capture_sandbox_custom_output(self):
        try:
            import playwright
        except ImportError:
            self.skipTest("playwright not installed")

        asset_build(f"{self.project_a}#crystal", stages="model,uv,texture")
        create_sandbox(self.project_a, "custom_box")

        custom_png = Path(self.tmp.name) / "custom_out.png"
        results = capture_sandbox(
            self.project_a,
            "custom_box",
            output_dir_or_file=custom_png,
            views=["iso"],
            resolution=(300, 300),
        )

        self.assertIn("iso", results)
        self.assertEqual(Path(results["iso"]).resolve(), custom_png.resolve())
        self.assertTrue(custom_png.is_file())
        self.assertGreater(custom_png.stat().st_size, 500)

    def test_capture_sandbox_js_pageerror_fails_fast(self):
        try:
            import playwright
        except ImportError:
            self.skipTest("playwright not installed")

        create_sandbox(self.project_a, "broken_box")
        index_html = self.project_a / "sandboxes" / "broken_box" / "index.html"
        orig_content = index_html.read_text(encoding="utf-8")
        # Inject script error
        crashed_content = orig_content.replace(
            "</body>",
            "<script>throw new Error('Deliberate sandbox syntax crash');</script></body>"
        )
        index_html.write_text(crashed_content, encoding="utf-8")

        with self.assertRaises(RuntimeError) as cm:
            capture_sandbox(self.project_a, "broken_box")
        self.assertIn("Sandbox JavaScript error:", str(cm.exception))
        self.assertIn("Deliberate sandbox syntax crash", str(cm.exception))

    def test_capture_sandbox_missing_sandbox_fails(self):
        with self.assertRaises(FileNotFoundError):
            capture_sandbox(self.project_a, "nonexistent_box")

    def test_cli_forge_capture_sandbox(self):
        try:
            import playwright
        except ImportError:
            self.skipTest("playwright not installed")

        asset_build(f"{self.project_a}#crystal", stages="model,uv,texture")
        create_sandbox(self.project_a, "cli_capture_box")

        cmd = [
            sys.executable,
            "-m",
            "Tools.forge",
            "capture",
            str(self.project_a),
            "--sandbox",
            "cli_capture_box",
            "--view",
            "iso",
            "--json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}")
        data = json.loads(result.stdout)
        self.assertIn("iso", data)
        self.assertTrue(Path(data["iso"]).is_file())


if __name__ == "__main__":
    unittest.main()
