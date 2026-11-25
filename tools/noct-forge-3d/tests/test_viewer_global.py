import http.client
import json
import socket
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from Tools.asset_init import init_project
from Tools.asset_build import asset_build
from Tools.texture_variant import register_variant
from Tools.viewer_server import (
    ModelViewerServer,
    probe_health,
    is_server_running,
)


class ViewerGlobalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.projects_root = Path(self.tmp.name) / "projects"
        self.projects_root.mkdir()

        # Project 1: proj_a with asset "hero"
        self.proj_a = self.projects_root / "proj_a"
        init_project(self.proj_a, asset_id="hero", animation=False)

        # Project 2: proj_b with asset "tree"
        self.proj_b = self.projects_root / "proj_b"
        init_project(self.proj_b, asset_id="tree", animation=False)

        # Global server
        self.global_server = ModelViewerServer(port=0, projects_root=self.projects_root)
        self.global_thread = threading.Thread(target=self.global_server.server.serve_forever, daemon=True)
        self.global_thread.start()
        self.addCleanup(self._close_server, self.global_server, self.global_thread)
        self.global_url = f"http://127.0.0.1:{self.global_server.port}"

        # Scoped server on proj_a
        self.scoped_server = ModelViewerServer(port=0, project=self.proj_a)
        self.scoped_thread = threading.Thread(target=self.scoped_server.server.serve_forever, daemon=True)
        self.scoped_thread.start()
        self.addCleanup(self._close_server, self.scoped_server, self.scoped_thread)
        self.scoped_url = f"http://127.0.0.1:{self.scoped_server.port}"

    def _close_server(self, server, thread):
        server.server.shutdown()
        server.server.server_close()
        thread.join(timeout=3)

    def test_health_and_probe_helper(self):
        # Global server health
        with urllib.request.urlopen(self.global_url + "/api/health") as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual((data["app"], data["mode"], data["protocolVersion"]), ("noct3d-viewer", "global", 2))
            self.assertTrue(data["workspaceId"])

        # Scoped server health
        with urllib.request.urlopen(self.scoped_url + "/api/health") as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual((data["app"], data["mode"], data["protocolVersion"]), ("noct3d-viewer", "project", 2))

        # Helper probe_health
        health_info = probe_health("127.0.0.1", self.global_server.port)
        self.assertIsNotNone(health_info)
        self.assertEqual(health_info["mode"], "global")
        self.assertTrue(is_server_running("127.0.0.1", self.global_server.port))

        # Inactive port probe
        self.assertIsNone(probe_health("127.0.0.1", 59999))
        self.assertFalse(is_server_running("127.0.0.1", 59999))

    def test_global_projects_discovery_dynamic(self):
        with urllib.request.urlopen(self.global_url + "/api/catalog") as resp:
            projects = json.loads(resp.read().decode("utf-8"))["projects"]
        ids = [p["id"] for p in projects]
        self.assertEqual(sorted(ids), ["proj_a", "proj_b"])

        # Dynamically create proj_c without restarting the server
        proj_c = self.projects_root / "proj_c"
        init_project(proj_c, asset_id="crystal", animation=False)

        with urllib.request.urlopen(self.global_url + "/api/catalog") as resp:
            projects = json.loads(resp.read().decode("utf-8"))["projects"]
        ids = [p["id"] for p in projects]
        self.assertEqual(sorted(ids), ["proj_a", "proj_b", "proj_c"])

    def test_scoped_projects_list(self):
        with urllib.request.urlopen(self.scoped_url + "/api/catalog") as resp:
            projects = json.loads(resp.read().decode("utf-8"))["projects"]
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0]["id"], "proj_a")

    def test_catalog_glbs_and_sandboxes(self):
        # Create a sandbox with index.html and a folder without index.html
        sb_dir = self.proj_a / "sandboxes" / "street"
        sb_dir.mkdir(parents=True)
        (sb_dir / "index.html").write_text("<h1>Street</h1>", encoding="utf-8")
        (self.proj_a / "sandboxes" / "empty_dir").mkdir(parents=True)

        # Create GLB files
        export_dir = self.proj_a / "assets" / "hero" / "export"
        export_dir.mkdir(parents=True)
        fake_glb = export_dir / "hero.glb"
        fake_glb.write_bytes(b"glTF\x02\x00\x00\x00fakebytes")

        standalone_glb = self.proj_a / "assets" / "standalone.glb"
        standalone_glb.write_bytes(b"glTF\x02\x00\x00\x00standalone")

        # Query global server for proj_a catalog
        with urllib.request.urlopen(self.global_url + "/api/catalog?project=proj_a") as resp:
            catalog = json.loads(resp.read().decode("utf-8"))

        self.assertEqual(catalog["id"], "proj_a")
        self.assertEqual(catalog["sandboxes"], ["street"])
        glb_paths = {g["path"]: g for g in catalog["glbs"]}
        self.assertIn("hero/export/hero.glb", glb_paths)
        self.assertEqual(glb_paths["hero/export/hero.glb"]["asset"], "hero")
        self.assertIsInstance(glb_paths["hero/export/hero.glb"]["stamp"], list)

        self.assertIn("standalone.glb", glb_paths)
        self.assertIsNone(glb_paths["standalone.glb"]["asset"])

        # Check URL scoping in catalog
        asset_info = catalog["assets"][0]
        self.assertEqual(asset_info["model_url"], "/api/p/proj_a/assets/hero/model")

        # Query scoped server for legacy /api/catalog
        with urllib.request.urlopen(self.scoped_url + "/api/catalog") as resp:
            scoped_cat = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(scoped_cat["sandboxes"], ["street"])
        self.assertEqual(len(scoped_cat["glbs"]), 2)
        self.assertEqual(scoped_cat["assets"][0]["model_url"], "/api/assets/hero/model")

    def test_project_assets_model_texture_variant(self):
        asset_build(f"{self.proj_a}#hero", stages="model,uv,texture")
        register_variant(f"{self.proj_a}#hero", "happy")
        variant_file = self.proj_a / "assets" / "hero" / "textures" / "happy.png"
        variant_file.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (16, 16), "green").save(variant_file)

        # GET model
        with urllib.request.urlopen(self.global_url + "/api/p/proj_a/assets/hero/model") as resp:
            model_data = json.loads(resp.read().decode("utf-8"))
        self.assertEqual(model_data["name"], "hero")
        self.assertEqual(model_data["textures"][0]["relative_path"], "/api/p/proj_a/assets/hero/texture/0")

        # GET texture
        with urllib.request.urlopen(self.global_url + "/api/p/proj_a/assets/hero/texture/0") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "image/png")
            self.assertGreater(len(resp.read()), 0)

        # GET variant
        with urllib.request.urlopen(self.global_url + "/api/p/proj_a/assets/hero/variant/happy") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "image/png")
            self.assertGreater(len(resp.read()), 0)

    def test_glb_serving(self):
        export_dir = self.proj_a / "assets" / "hero" / "export"
        export_dir.mkdir(parents=True)
        fake_glb = export_dir / "hero.glb"
        fake_glb.write_bytes(b"glTF\x02\x00\x00\x00binarypayload")

        with urllib.request.urlopen(self.global_url + "/api/p/proj_a/glb?path=hero/export/hero.glb") as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "model/gltf-binary")
            self.assertEqual(resp.read(), b"glTF\x02\x00\x00\x00binarypayload")

        # Not found GLB
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.global_url + "/api/p/proj_a/glb?path=nonexistent.glb")
        self.assertEqual(ctx.exception.code, 404)

    def test_sandbox_serving(self):
        sb_dir = self.proj_a / "sandboxes" / "garden"
        sb_dir.mkdir(parents=True)
        (sb_dir / "index.html").write_text("<!DOCTYPE html><html><body>Garden</body></html>", encoding="utf-8")
        (sb_dir / "app.js").write_text("console.log('garden');", encoding="utf-8")
        (sb_dir / "style.css").write_text("body { background: green; }", encoding="utf-8")

        # Index with trailing slash
        with urllib.request.urlopen(self.global_url + "/sandbox/proj_a/garden/") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type"))
            self.assertIn(b"Garden", resp.read())

        # Index without trailing slash
        with urllib.request.urlopen(self.global_url + "/sandbox/proj_a/garden") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type"))

        # Explicit JS
        with urllib.request.urlopen(self.global_url + "/sandbox/proj_a/garden/app.js") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type"))
            self.assertIn(b"console.log", resp.read())

        # Explicit CSS
        with urllib.request.urlopen(self.global_url + "/sandbox/proj_a/garden/style.css") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/css", resp.headers.get("Content-Type"))

    def test_lib_serving(self):
        # Serves from vendor
        with urllib.request.urlopen(self.global_url + "/lib/three.min.js") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type"))
            self.assertGreater(len(resp.read()), 1000)

        with urllib.request.urlopen(self.global_url + "/lib/GLTFLoader.js") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type"))
            self.assertIn(b"GLTFLoader", resp.read())

        # Serves from js
        with urllib.request.urlopen(self.global_url + "/lib/bbmodel_parser.js") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type"))

        with urllib.request.urlopen(self.global_url + "/lib/asset_loader.js") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type"))
            self.assertIn(b"loadAssetObject", resp.read())

        with urllib.request.urlopen(self.global_url + "/lib/inspector.js") as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("application/javascript", resp.headers.get("Content-Type"))
            self.assertIn(b"ModelInspector", resp.read())

        # Missing lib
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.global_url + "/lib/unknown_lib.js")
        self.assertEqual(ctx.exception.code, 404)

    def test_security_confinement(self):
        # 1. Scoped server accessing another project must return 403
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.scoped_url + "/api/catalog?project=proj_b")
        self.assertEqual(ctx.exception.code, 403)

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.scoped_url + "/sandbox/proj_b/street/index.html")
        self.assertEqual(ctx.exception.code, 403)

        # 2. Path traversal in GLB (?path=..) must return 403
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.global_url + "/api/p/proj_a/glb?path=../../outside.glb")
        self.assertEqual(ctx.exception.code, 403)

        # 3. Path traversal in sandbox must return 403
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.global_url + "/sandbox/proj_a/street/../../outside.txt")
        self.assertEqual(ctx.exception.code, 403)

        # 4. Path traversal in lib must return 403
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.global_url + "/lib/../../AGENTS.md")
        self.assertEqual(ctx.exception.code, 403)

        # 5. Non-existent project in global server returns 404
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.global_url + "/api/catalog?project=nonexistent_project")
        self.assertEqual(ctx.exception.code, 404)

    def test_global_port_fixed_fails_when_busy(self):
        # Global server does not scan when explicit port is provided and busy
        busy_port = self.global_server.port
        with self.assertRaises(ValueError):
            ModelViewerServer(port=busy_port, projects_root=self.projects_root)

    def test_global_default_port_falls_back_when_preferred_busy(self):
        # Use a free port as the "preferred" one so the test never depends on (or disturbs) a real viewer on 8765.
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        preferred = probe.getsockname()[1]
        probe.close()
        blocker = socket.socket()
        try:
            blocker.bind(("127.0.0.1", preferred))
        except OSError:
            blocker.close()
            self.skipTest(f"port {preferred} was taken meanwhile")
        try:
            with mock.patch("Tools.viewer_server.GLOBAL_PREFERRED_PORT", preferred):
                server = ModelViewerServer(projects_root=self.projects_root)
            self.addCleanup(server.server.server_close)
            self.assertTrue(preferred < server.port <= preferred + 20, server.port)
        finally:
            blocker.close()

    def test_stale_viewer_raises_value_error(self):
        from Tools.model_viewer import main
        self.global_server.server_revision = "stale-revision"
        with self.assertRaises(ValueError):
            main(["--all", "--projects-root", str(self.projects_root), "--port", str(self.global_server.port)])

    def _raw(self, base, method, path, host=None):
        port = int(base.rsplit(":", 1)[1])
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.putrequest(method, path, skip_host=host is not None)
            if host is not None:
                conn.putheader("Host", host)
            conn.endheaders()
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()

    def test_host_header_rejected_unless_loopback_on_server_port(self):
        port = self.global_server.port
        for host in ("evil.example.com", f"evil.example.com:{port}", f"127.0.0.1:{port + 1}", f"localhost:{port + 1}"):
            status, _, _ = self._raw(self.global_url, "GET", "/api/health", host=host)
            self.assertEqual(status, 403, host)
        for host in (f"127.0.0.1:{port}", f"localhost:{port}"):
            status, _, _ = self._raw(self.global_url, "GET", "/api/health", host=host)
            self.assertEqual(status, 200, host)

    def test_head_sends_length_without_body(self):
        status, headers, body = self._raw(self.global_url, "HEAD", "/api/health")
        get_status, _, get_body = self._raw(self.global_url, "GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assertEqual(int(headers["Content-Length"]), len(get_body))

    def test_corrupt_model_json_is_500_not_403(self):
        model = self.proj_a / json.loads((self.proj_a / "project.json").read_text(encoding="utf-8"))["assets"]["hero"]["model"]
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_text("{not json", encoding="utf-8")
        status, _, _ = self._raw(self.global_url, "GET", "/api/p/proj_a/assets/hero/model")
        self.assertEqual(status, 500)

    def test_bad_texture_index_is_404(self):
        asset_build(f"{self.proj_a}#hero", stages="model,uv,texture")
        for index in ("abc", "-1", "999"):
            status, _, _ = self._raw(self.global_url, "GET", f"/api/p/proj_a/assets/hero/texture/{index}")
            self.assertEqual(status, 404, index)

    def test_sandbox_redirect_keeps_query_and_charset(self):
        sb_dir = self.proj_a / "sandboxes" / "garden"
        sb_dir.mkdir(parents=True)
        (sb_dir / "index.html").write_text("<html></html>", encoding="utf-8")
        (sb_dir / "style.css").write_text("a{}", encoding="utf-8")
        status, headers, _ = self._raw(self.global_url, "GET", "/sandbox/proj_a/garden?capture=1&view=iso")
        self.assertEqual(status, 302)
        self.assertEqual(headers["Location"], "/sandbox/proj_a/garden/?capture=1&view=iso")
        _, headers, _ = self._raw(self.global_url, "GET", "/sandbox/proj_a/garden/")
        self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
        _, headers, _ = self._raw(self.global_url, "GET", "/sandbox/proj_a/garden/style.css")
        self.assertEqual(headers["Content-Type"], "text/css; charset=utf-8")

    def test_backend_revision_covers_four_modules(self):
        from Tools import viewer_server
        before = viewer_server.backend_revision()
        self.assertEqual(before, viewer_server.backend_revision())
        self.assertEqual(len(viewer_server._REVISION_FILES), 4)

    def test_global_and_scoped_ui_inspector_playwright(self):
        from playwright.sync_api import sync_playwright
        from Tools.asset_export import asset_export
        asset_build(f"{self.proj_a}#hero", stages="model,uv,texture")
        asset_export(f"{self.proj_a}#hero", output="hero/exports/hero.glb", format="glb")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True,
                args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"]
            )
            try:
                # 1. Global Mode UI verification
                page = browser.new_page()
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))
                page.goto(self.global_url + "/?project=proj_a&asset=hero")
                page.wait_for_function("window.__VIEWER_READY__ === true && window.inspector !== null")

                # Check sidebar is visible and toolbar has global-mode class
                self.assertTrue(page.is_visible("#explorer-sidebar"))
                toolbar_class = page.get_attribute("#toolbar", "class")
                self.assertIn("global-mode", toolbar_class)

                # Check projects listed in sidebar
                projects_text = page.text_content("#project-select")
                self.assertIn("proj_a", projects_text)
                self.assertIn("proj_b", projects_text)

                # Check outliner rendered
                outliner_text = page.text_content("#outliner-tree")
                self.assertIn("hero", outliner_text.lower())

                # Check selection in outliner
                node = page.locator(".outliner-node").first
                node.click()
                self.assertIn("selected", node.get_attribute("class"))

                # Check camera view buttons
                page.click('[data-inspector-tab="view"]')
                page.click("#btn-view-left")
                self.assertIn("active", page.locator("#btn-view-left").get_attribute("class"))
                page.click("#btn-view-bottom")
                self.assertIn("active", page.locator("#btn-view-bottom").get_attribute("class"))

                # Check perspective / orthographic toggle button
                proj_btn = page.locator("#btn-cam-proj")
                init_text = proj_btn.text_content()
                proj_btn.click()
                self.assertNotEqual(proj_btn.text_content(), init_text)

                # Check bones and pivots overlays toggling
                page.click('[data-inspector-tab="hierarchy"]')
                page.check("#chk-bones")
                bones_enabled = page.evaluate("() => window.inspector.showBones")
                self.assertTrue(bones_enabled)

                page.check("#chk-pivots")
                pivots_enabled = page.evaluate("() => window.inspector.showPivots")
                self.assertTrue(pivots_enabled)

                # Check format selector toggle (BBModel vs GLB)
                format_panel = page.locator("#format-panel")
                self.assertTrue(format_panel.is_visible())

                # Switch format to GLB
                page.select_option("#format-select", "glb:hero/exports/hero.glb")
                page.wait_for_function("() => window.currentLoadedAsset && window.currentLoadedAsset.kind === 'glb'")
                self.assertIn("glb=hero%2Fexports%2Fhero.glb", page.url)

                # Switch format back to BBModel
                page.select_option("#format-select", "bbmodel")
                page.wait_for_function("() => window.currentLoadedAsset && window.currentLoadedAsset.kind === 'bbmodel'")
                self.assertIn("asset=hero", page.url)

                self.assertFalse(errors, errors)
                page.close()

                # 2. Scoped Mode UI verification
                page_scoped = browser.new_page()
                scoped_errors = []
                page_scoped.on("pageerror", lambda err: scoped_errors.append(str(err)))
                page_scoped.goto(self.scoped_url)
                page_scoped.wait_for_function("window.__VIEWER_READY__ === true && window.inspector !== null")

                # In scoped mode, sidebar is hidden and toolbar does NOT have global-mode
                self.assertTrue(page_scoped.is_visible("#explorer-sidebar"))
                scoped_toolbar_class = page_scoped.get_attribute("#toolbar", "class") or ""
                self.assertNotIn("global-mode", scoped_toolbar_class)

                # Outliner works in scoped mode too
                scoped_outliner = page_scoped.text_content("#outliner-tree")
                self.assertIn("hero", scoped_outliner.lower())

                self.assertFalse(scoped_errors, scoped_errors)
                page_scoped.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
