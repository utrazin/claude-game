import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from lib import ModelBuilder
from Tools.uv_packer import main


class UVPackerJsonTests(unittest.TestCase):
    def run_packer(self, *extra):
        with tempfile.TemporaryDirectory() as tmp:
            from Tools.asset_init import init_project
            from Tools._resolve import resolve_asset
            init_project(Path(tmp) / "proj", asset_id="uv")
            model = resolve_asset(f"{Path(tmp) / 'proj'}#uv").model
            ModelBuilder("t").add_group("root").add_cube("body", "root", from_=(0, 0, 0), to_=(4, 4, 4)).export_bbmodel(model)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main([str(model), *extra])
        return out.getvalue()

    def test_json_output_is_parseable_for_a_real_pack_and_a_dry_run(self):
        packed = json.loads(self.run_packer("--json"))
        self.assertEqual(packed["status"], "pass")
        self.assertIn("uv_scale", packed)
        dry = json.loads(self.run_packer("--dry-run", "--json"))
        self.assertEqual(dry["status"], "dry-run")

    def test_the_text_output_is_unchanged_without_the_flag(self):
        self.assertTrue(self.run_packer().startswith("[uv] PASS atlas="))


if __name__ == "__main__":
    unittest.main()
