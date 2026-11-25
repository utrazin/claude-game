import copy
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.model_builder import ModelBuilder
from Tools.uv_packer import BoxUVPacker
from Tools.uv_builder import UVBuilder
from Tools.TexturePainter import TexturePainter


class IndependentUVStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        init_project(Path(self.temp.name) / "proj", asset_id="uv")
        self.model = resolve_asset(f"{Path(self.temp.name) / 'proj'}#uv").model
        self.root = Path(__file__).resolve().parents[1]
        self.builder = (ModelBuilder("test")
                        .add_group("root")
                        .add_cube("body", "root", from_=(0, 0, 0), to_=(2, 3, 4))
                        .add_axis_quad("patch", "root", from_=(0, 0, -0.1), size=(2, 3), normal="-Z"))
        self.builder.export_bbmodel(self.model)
        UVBuilder(self.model, start_size=(32, 16), uv_scale=2, allow_rectangular=True).save()

    def read(self):
        return json.loads(self.model.read_text(encoding="utf-8"))

    def write(self, data):
        self.model.write_text(json.dumps(data), encoding="utf-8")

    def cli(self, *args):
        return subprocess.run([sys.executable, "-B", "-m", "Tools.uv_packer", str(self.model), *args],
                              cwd=self.root, capture_output=True, text=True)

    def test_geometry_export_does_not_pack_and_uv_recipe_uses_shared_stage(self):
        with patch.object(BoxUVPacker, "pack_document", wraps=BoxUVPacker.pack_document) as stage:
            self.builder.export_bbmodel(self.model)
            self.assertEqual(stage.call_count, 0)
            with self.assertRaisesRegex(ValueError, 'not finalized'):
                TexturePainter.from_bbmodel(self.model)
            UVBuilder(self.model, start_size=(32, 16), uv_scale=2).save()
        self.assertEqual(stage.call_count, 1)
        generated = self.read()
        mapped, _, _ = BoxUVPacker.pack_document(generated)
        self.assertEqual(mapped, generated)
        # Pure function does not modify its argument.
        snapshot = copy.deepcopy(generated)
        BoxUVPacker.pack_document(generated, uv_scale=1)
        self.assertEqual(generated, snapshot)

    def test_uv_builder_is_silent_unless_verbose(self):
        silent = io.StringIO()
        with contextlib.redirect_stdout(silent):
            builder = UVBuilder(self.model)
            builder.save()
        self.assertEqual(silent.getvalue(), "")
        self.assertEqual(builder.last_stats["width"], 32)
        verbose = io.StringIO()
        with contextlib.redirect_stdout(verbose):
            UVBuilder(self.model).save(verbose=True)
        self.assertIn("px/unit", verbose.getvalue())

    def test_manual_geometry_then_repeatable_remap_preserves_non_uv_data(self):
        data = self.read()
        data["elements"][0]["to"][0] = 9
        data["elements"][0]["inflate"] = 0.45
        data["elements"][0]["custom_field"] = {"keep": [1, 2]}
        mesh = data["elements"][1]
        for v in mesh["vertices"].values():
            v[0] *= 2
        # Another face on a separate plane, without any old UVs.
        ids = mesh["faces"]["quad"]["vertices"]
        second = [k + "_second" for k in ids]
        for original, new in zip(ids, second):
            mesh["vertices"][new] = [*mesh["vertices"][original][:2], -2]
        mesh["faces"]["second"] = {"vertices": second, "texture": False, "custom": 7}
        data["animations"] = [{"name": "keep", "length": 2}]
        data["custom_root"] = "preserved"
        self.write(data)
        png = self.model.with_name("texture.png")
        png.write_bytes(b"old image must not be touched")
        with patch.object(ModelBuilder, "export_bbmodel", side_effect=AssertionError("recipe not allowed")):
            BoxUVPacker.apply_to_bbmodel(self.model)
        mapped = self.read()
        for key in ("outliner", "groups", "animations", "custom_root"):
            self.assertEqual(data[key], mapped[key])
        for old, new in zip(data["elements"], mapped["elements"]):
            for key in old:
                if key not in ("faces", "uv_offset", "box_uv", "autouv"):
                    self.assertEqual(old[key], new[key], key)
        self.assertEqual(mapped["elements"][1]["faces"]["second"]["custom"], 7)
        self.assertEqual(mapped["textures"], [])
        p = TexturePainter.from_bbmodel(self.model)
        self.assertEqual(p.body.north.width, 18)  # edited width 9 * saved scale 2
        self.assertEqual(p.patch.quad.width, 8)   # edited width 4 * saved scale 2
        once = self.model.read_bytes()
        BoxUVPacker.apply_to_bbmodel(self.model)
        self.assertEqual(self.model.read_bytes(), once)
        self.assertEqual(png.read_bytes(), b"old image must not be touched")

    def test_cli_dry_run_copy_and_in_place(self):
        before = self.model.read_bytes()
        result = self.cli("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Dry run", result.stdout)
        self.assertEqual(self.model.read_bytes(), before)
        output = self.model.with_name("remapped.bbmodel")
        result = self.cli("--out", str(output), "--uv-scale", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(output.exists())
        self.assertEqual(self.model.read_bytes(), before)
        result = self.cli("--uv-scale", "1", "--start-size", "16")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(str(self.model)+".bak").read_bytes(), before)
        self.assertEqual(self.read()["unhandled_root_fields"]["model_as_code"]["uv_packing"]["uv_scale"], 1)

    def test_manual_ngon_polygon_is_rejected_without_geometry_changes(self):
        backup_before = Path(str(self.model)+'.bak').read_bytes()
        data = self.read()
        face = data["elements"][1]["faces"]["quad"]
        vertices = data["elements"][1]["vertices"]
        vertices["ngon_extra"] = [2, 1, 0]
        face["vertices"] = face["vertices"] + ["ngon_extra"]
        self.write(data)
        before = self.model.read_bytes()
        result = self.cli()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("three or four",result.stderr)
        self.assertEqual(self.model.read_bytes(),before)
        self.assertEqual(Path(str(self.model)+'.bak').read_bytes(),backup_before)

    def test_painter_consumes_resolution_without_any_uv_call_or_mode_write(self):
        # A larger declared canvas is authoritative even when geometry fits a smaller one.
        data = self.read()
        data["resolution"] = {"width": 256, "height": 128}
        self.write(data)
        with patch.object(BoxUVPacker, "pack_document", side_effect=AssertionError("UV stage not allowed")):
            p = TexturePainter.from_bbmodel(self.model)
            self.assertEqual((p.width, p.height), (256, 128))
            p.body.fill_all("#123456")
            p.save(self.model.with_name("texture.png"))
        after = self.read()
        self.assertEqual(after["resolution"], data["resolution"])
        self.assertEqual(after["meta"], data["meta"])
        for old, new in zip(data["elements"], after["elements"]):
            self.assertEqual(old.get("box_uv"), new.get("box_uv"))
            self.assertEqual(old.get("autouv"), new.get("autouv"))
            for name in old["faces"]:
                self.assertEqual(old["faces"][name]["uv"], new["faces"][name]["uv"])

    def test_fixed_atlas_and_invalid_options_fail_without_writes(self):
        before = self.model.read_bytes()
        for options in ({"start_size": 16, "fixed_texture_size": True},
                        {"uv_scale": 0}, {"max_size": 0}, {"start_size": [-1, 32]}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    BoxUVPacker.apply_to_bbmodel(self.model, **options)
                self.assertEqual(self.model.read_bytes(), before)

    def test_global_integer_density_and_geometry_preservation(self):
        source = self.read()
        for density in (1, 2, 3, 4):
            with self.subTest(density=density):
                mapped, _, stats = BoxUVPacker.pack_document(source, uv_scale=density)
                self.assertEqual(stats['uv_scale'], density)
                for old, new in zip(source['elements'], mapped['elements']):
                    for key in old.keys() - {'faces', 'uv_offset', 'box_uv', 'autouv'}:
                        self.assertEqual(old[key], new[key])
                uv = mapped['elements'][0]['faces']['north']['uv']
                self.assertEqual((abs(uv[2]-uv[0]), abs(uv[3]-uv[1])), (2*density, 3*density))
                vertices = list(mapped['elements'][1]['faces']['quad']['uv'].values())
                self.assertEqual(max(p[0] for p in vertices)-min(p[0] for p in vertices), 2*density)
                self.assertEqual(max(p[1] for p in vertices)-min(p[1] for p in vertices), 3*density)
                self.assertEqual(BoxUVPacker.pack_document(mapped)[0], mapped)
        source['unhandled_root_fields']['model_as_code']['uv_packing'].pop('uv_scale')
        self.assertEqual(BoxUVPacker.pack_document(source)[2]['uv_scale'], 1)
        self.assertFalse(hasattr(ModelBuilder('default'), 'uv_scale'))

    def test_fractional_geometry_rejected_before_density_without_writes(self):
        for kind in ('cube', 'mesh'):
            for size in (0.5, 1.5):
                with self.subTest(kind=kind, size=size):
                    data = self.read()
                    if kind == 'cube':
                        data['elements'][0]['to'][0] = size
                    else:
                        for vertex in data['elements'][1]['vertices'].values():
                            vertex[0] *= size / 2
                    self.write(data)
                    before = self.model.read_bytes()
                    backup_before = Path(str(self.model)+'.bak').read_bytes()
                    with self.assertRaisesRegex(ValueError, 'geometry size'):
                        BoxUVPacker.apply_to_bbmodel(self.model, uv_scale=2)
                    self.assertEqual(self.model.read_bytes(), before)
                    self.assertEqual(Path(str(self.model)+'.bak').read_bytes(), backup_before)
                    self.builder.export_bbmodel(self.model)
                    UVBuilder(self.model, start_size=(32,16), uv_scale=2).save()

    def test_fractional_positions_preserve_integer_sizes(self):
        data = self.read()
        cube = data['elements'][0]
        cube['from'] = [v + 0.35 for v in cube['from']]
        cube['to'] = [v + 0.35 for v in cube['to']]
        cube['rotation'] = [12.5, 0, 0]
        mapped, _, _ = BoxUVPacker.pack_document(data, uv_scale=2)
        for key in ('from', 'to', 'rotation'):
            self.assertEqual(mapped['elements'][0][key], cube[key])

    def test_fractional_density_and_pixel_dimensions_are_rejected(self):
        for value in (0.5, 1.5, 0, -1, True, float('nan'), float('inf')):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'positive integer'):
                    BoxUVPacker.pack_document(self.read(), uv_scale=value)
        data = self.read()
        data['unhandled_root_fields']['model_as_code']['uv_packing']['uv_scale'] = 0.5
        self.write(data)
        before = self.model.read_bytes()
        self.assertNotEqual(self.cli().returncode, 0)
        self.assertNotEqual(self.cli('--uv-scale', '0.5').returncode, 0)
        self.assertEqual(self.model.read_bytes(), before)
        result = self.cli('--uv-scale', '3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('3 px/unit', result.stdout)
        self.assertEqual(self.read()['unhandled_root_fields']['model_as_code']['uv_packing']['uv_scale'], 3)
        data['elements'][0]['to'][0] = 2.25
        with self.assertRaisesRegex(ValueError, 'body/X'):
            BoxUVPacker.pack_document(data, uv_scale=1)
        data['elements'][0]['to'][0] = 2.0000000001
        BoxUVPacker.pack_document(data, uv_scale=1)
        with self.assertRaisesRegex(ValueError, 'patch/width'):
            BoxUVPacker.create_item_from_quad('patch', (1.2, 2))


if __name__ == "__main__":
    unittest.main()
