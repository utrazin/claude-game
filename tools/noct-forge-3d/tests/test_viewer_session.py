"""Behavioral regressions for transactional refresh and the animation transport."""
import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock
import urllib.request
from playwright.sync_api import sync_playwright
from tests import test_viewer_global as fixtures
from Tools.asset_build import asset_build
from Tools.asset_export import asset_export
from Tools._resolve import resolve_asset
from Tools.sandbox import create_sandbox


class ViewerSessionTests(unittest.TestCase):
    setUp = fixtures.ViewerGlobalTests.setUp
    _close_server = fixtures.ViewerGlobalTests._close_server

    def test_library_can_open_a_glb_only_project(self):
        asset_build(f'{self.proj_a}#hero', stages='model')
        asset_export(f'{self.proj_a}#hero', output='hero/exports/hero.glb', format='glb')
        manifest = self.proj_a / 'project.json'
        data = json.loads(manifest.read_text()); data['assets'] = {}
        manifest.write_text(json.dumps(data))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-webgl'])
            try:
                page = browser.new_page()
                page.goto(self.global_url)
                page.locator('[data-glb="hero/exports/hero.glb"]').wait_for(timeout=10000)
                page.locator('[data-glb="hero/exports/hero.glb"]').click()
                page.wait_for_function("currentLoadedAsset?.kind === 'glb' && !navigationPending")
                self.assertEqual(page.locator('#badge-name').inner_text(), 'hero.glb')
            finally:
                browser.close()

    def test_selected_catalog_does_not_scan_other_projects_and_caches_manifest(self):
        with mock.patch.object(self.global_server, 'list_projects', side_effect=AssertionError('Global scan during selection')):
            with urllib.request.urlopen(self.global_url + '/api/catalog?project=proj_a&asset=hero') as response:
                data = json.load(response)
            self.assertEqual(data['id'], 'proj_a')
        from Tools.project_manifest import load_project
        self.global_server._project_metadata.clear()
        with mock.patch('Tools.viewer_server.load_project', wraps=load_project) as loader:
            self.global_server.project_data(self.proj_a)
            self.global_server.project_data(self.proj_a)
            self.assertEqual(loader.call_count, 1)
            manifest = self.proj_a / 'project.json'
            data = json.loads(manifest.read_text()); data['name'] = 'Renamed'
            manifest.write_text(json.dumps(data))
            self.assertEqual(self.global_server.project_data(self.proj_a)['name'], 'Renamed')
            self.assertEqual(loader.call_count, 2)

    def test_background_index_cannot_cancel_a_model_clicked_in_the_library(self):
        asset_build(f'{self.proj_a}#hero', stages='model')
        asset_build(f'{self.proj_b}#tree', stages='model')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=['--use-gl=angle', '--use-angle=swiftshader', '--enable-webgl'])
            try:
                page = browser.new_page()
                page.goto(self.global_url + '/?project=proj_a&asset=hero')
                page.wait_for_function("currentModelData?.name === 'hero'")
                page.evaluate('''() => {
                    const original = window.fetch;
                    window.fetch = async (...args) => {
                        if (args[0] === '/api/catalog') await new Promise(resolve => setTimeout(resolve, 200));
                        if (String(args[0]).includes('project=proj_b')) await new Promise(resolve => setTimeout(resolve, 650));
                        return original(...args);
                    };
                    void refreshAll(true);
                }''')
                page.select_option('#project-select', 'proj_b')
                page.locator('[data-asset="tree"]').click()
                page.wait_for_function("currentModelData?.name === 'tree' && !navigationPending", timeout=10000)
                self.assertEqual(page.evaluate('[activeProject, activeAsset, currentModelData.name]'), ['proj_b', 'tree', 'tree'])
                page.locator('[data-inspector-tab="hierarchy"]').click()
                page.locator('.outliner-node').first.click()
                self.assertEqual(page.locator('#badge-name').inner_text(), 'tree')
            finally:
                browser.close()

    def test_refresh_playback_glb_and_latest_navigation(self):
        asset_build(f"{self.proj_a}#hero", stages="model,uv,texture")
        model = resolve_asset(f"{self.proj_a}#hero").model
        doc = json.loads(model.read_text())
        def groups(nodes):
            for node in nodes:
                if isinstance(node, dict):
                    yield node
                    yield from groups(node.get('children', []))
        definitions = list(groups(doc['outliner'])) + doc.get('groups', []) + doc.get('elements', [])
        animated_id = next(node['uuid'] for node in definitions if node.get('name') == 'body')
        doc["animations"] = [{"name": name, "length": 2, "loop": "loop", "animators": {
            animated_id: {'keyframes': [
                {'time': 0, 'channel': 'rotation', 'data_points': [{'x': 0, 'y': 0, 'z': 0}]},
                {'time': 2, 'channel': 'rotation', 'data_points': [{'x': 0, 'y': 90 if name == 'walk' else -30, 'z': 0}]}
            ]}
        }} for name in ("idle", "walk")]
        model.write_text(json.dumps(doc))
        asset_export(f"{self.proj_a}#hero", output="hero/exports/hero.glb", format="glb")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"])
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(self.global_url + '/?project=proj_a&asset=hero')
                page.wait_for_function("currentLoadedAsset && animationPlayer?.names.length === 2")
                self.assertTrue(page.locator('#animation-panel').is_visible())
                page.locator('[data-clip="walk"]').click()
                page.locator('#animation-play').click()
                self.assertEqual(page.locator('#animation-state').inner_text(), 'Reproduzindo')
                page.wait_for_function('animationPlayer.time > 0.05')
                self.assertNotEqual(page.evaluate('id => parser.controls.get(id).object.rotation.y', animated_id), 0)
                page.locator('#animation-play').click()
                self.assertEqual(page.locator('#animation-state').inner_text(), 'Pausado')
                page.select_option('#animation-speed', '0.5')
                page.locator('.playback-settings summary').click()
                page.select_option('#animation-repeat', 'once')
                page.locator('.playback-settings summary').click()
                page.evaluate("seekAnimation(0.8); sceneSetup.setCameraType('orthographic'); sceneSetup.camera.zoom=1.7; sceneSetup.camera.updateProjectionMatrix()")
                before = page.evaluate('ForgeSession.cameraSnapshot(sceneSetup)')
                doc['name'] = 'updated hero'
                model.write_text(json.dumps(doc))
                page.wait_for_function("currentModelData?.name === 'updated hero'", timeout=10000)
                self.assertEqual(page.evaluate('ForgeSession.cameraSnapshot(sceneSetup)'), before)
                playback = page.evaluate('ForgeSession.playbackSnapshot(animationPlayer)')
                self.assertEqual(playback, {'clip': 'walk', 'time': 0.8, 'playing': False, 'speed': 0.5, 'repeat': 'once'})
                self.assertEqual(page.evaluate('animationPlayer.length'), 2)
                screenshot = Path(__file__).resolve().parents[1] / '.runtime/checks/viewer-3d-new.png'
                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(screenshot))
                page.select_option('#format-select', 'glb:hero/exports/hero.glb')
                page.wait_for_function("currentLoadedAsset?.kind === 'glb'")
                page.evaluate('window.testLoaded = currentLoadedAsset')
                page.evaluate('refreshAll(false)')
                self.assertTrue(page.evaluate('window.testLoaded === currentLoadedAsset'))
                glb = self.proj_a / 'assets/hero/exports/hero.glb'
                os.utime(glb, (time.time() + 2, time.time() + 2))
                page.evaluate('refreshAll(false)')
                self.assertTrue(page.evaluate('window.testLoaded !== currentLoadedAsset'))
                page.evaluate('window.testLoaded = currentLoadedAsset; refreshAll(false)')
                self.assertTrue(page.evaluate('window.testLoaded === currentLoadedAsset'))
                page.evaluate("""() => {
                    const original = window.fetch;
                    window.fetch = async (...args) => {
                        if (String(args[0]).includes('/api/catalog?project=proj_b')) await new Promise(resolve => setTimeout(resolve, 350));
                        return original(...args);
                    };
                    void selectAsset('tree', 'proj_b');
                }""")
                page.evaluate("selectAsset('hero', 'proj_a')")
                page.wait_for_timeout(600)
                self.assertEqual(page.evaluate('[activeProject, activeAsset, catalog.id]'), ['proj_a', 'hero', 'proj_a'])
                self.assertFalse(errors, errors)
            finally:
                browser.close()

    def test_sandbox_replaces_content_without_reload_or_transform_loss(self):
        asset_build(f"{self.proj_a}#hero", stages="model,uv,texture")
        sandbox = create_sandbox(self.proj_a, 'test_scene')
        model = resolve_asset(f"{self.proj_a}#hero").model
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl"])
            try:
                page = browser.new_page()
                page.goto(self.global_url + '/sandbox/proj_a/test_scene/')
                page.wait_for_function('window.__VIEWER_READY__ === true')
                page.evaluate("window.token=1; window.handle=__CURRENT_SANDBOX__.instances[0]; handle.object.position.x=9; window.oldContent=handle.object.children[0]")
                doc = json.loads(model.read_text()); doc['name'] = 'changed sandbox model'
                model.write_text(json.dumps(doc))
                page.wait_for_function('handle.object.children[0] !== window.oldContent', timeout=10000)
                self.assertEqual(page.evaluate('[window.token, handle === __CURRENT_SANDBOX__.instances[0], handle.object.position.x]'), [1, True, 9])
                page.evaluate('window.oldContent=handle.object.children[0]; __CURRENT_SANDBOX__.refreshInstances()')
                self.assertTrue(page.evaluate('handle.object.children[0] === window.oldContent'))
            finally:
                browser.close()
