import hashlib
import json
import unittest
import subprocess
from pathlib import Path


class RuntimeDistributionTests(unittest.TestCase):
    def test_playback_adapters_have_consistent_transport(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', 'tests/playback_session_check.js'], cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_embedded_runtime_matches_release_manifest(self):
        root = Path(__file__).resolve().parents[1] / 'Tools/viewer'
        manifest = json.loads((root / 'runtime-version.json').read_text())
        self.assertEqual(manifest['version'], '2.0.0')
        paths = {'forge-session.js': 'js/forge_session.js', 'forge-theme.css': 'forge-theme.css'}
        for source, target in paths.items():
            self.assertEqual(hashlib.sha256((root / target).read_bytes()).hexdigest(), manifest['hashes'][source])
