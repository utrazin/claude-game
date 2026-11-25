from Tools.uv_builder import UVBuilder
import copy
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from lib.model_builder import ModelBuilder
from Tools.uv_packer import BoxUVPacker, MaxRectsPacker
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.export import TextureExporter
from uv_assertions import uv_state


class TexturePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.bbmodel"
        self.png = Path(self.temp.name) / "texture.png"
        (ModelBuilder("contract")
         .add_group("root")
         .add_cube("body", "root", from_=(0, 0, 0), to_=(8, 6, 4), inflate=0.15)
         .add_axis_quad("badge", "root", from_=(0, 0, -0.2), size=(2, 2), normal="-Z")
         .export_bbmodel(self.model))
        UVBuilder(self.model, start_size=(64, 32), uv_scale=1).save()

    def read(self):
        return json.loads(self.model.read_text(encoding="utf-8"))

    def write(self, data):
        self.model.write_text(json.dumps(data), encoding="utf-8")

    def test_registration_preserves_uv_geometry_and_portable_reference(self):
        before = self.read()
        p = TexturePainter.from_bbmodel(self.model)
        p.body.fill_all("#445566")
        p.body.up.set_pixel(0, 0, "#ff0000")
        p.badge.quad.fill("#123456")
        p.save(self.png)
        after = self.read()
        self.assertFalse(after["meta"]["box_uv"])
        for old, new in zip(before["elements"], after["elements"]):
            for key in ("from", "to", "inflate", "origin", "rotation", "vertices", "uv_offset"):
                self.assertEqual(old.get(key), new.get(key))
            if new["type"] == "cube":
                self.assertFalse(new["box_uv"])
                self.assertEqual(new["autouv"], 0)
            for key, face in old["faces"].items():
                self.assertEqual(face["uv"], new["faces"][key]["uv"])
                self.assertEqual(new["faces"][key]["texture"], 0)
        self.assertEqual(before["outliner"], after["outliner"])
        tex = after["textures"][0]
        self.assertEqual(tex["relative_path"], "texture.png")
        self.assertEqual((tex["width"], tex["height"]), (64, 32))
        self.assertEqual((tex["uv_width"], tex["uv_height"]), (64, 32))
        self.assertNotIn("source", tex)
        self.assertNotIn("path", tex)
        with Image.open(self.png) as image:
            self.assertNotIn("model_as_code_uv_sha256", image.info)
            up = p.body.up.uv_info
            self.assertEqual(image.getpixel((up["x"]+up["w"]-1, up["y"]+up["h"]-1)), (255, 0, 0, 255))
        self.assertTrue(Path(str(self.model)+".bak").exists())
        # A second save remains valid after registration changes metadata.
        p.save(self.png)

    def test_explicit_render_sides_preserved_without_geometry_changes(self):
        p = TexturePainter.from_bbmodel(self.model)
        before = uv_state(self.read())
        p.save(self.png, render_sides="double")
        self.assertEqual(self.read()["textures"][0]["render_sides"], "double")
        self.assertEqual(uv_state(self.read()), before)
        p.save(self.png)
        self.assertEqual(self.read()["textures"][0]["render_sides"], "double")
        p.save(self.png, render_sides="front")
        self.assertEqual(self.read()["textures"][0]["render_sides"], "front")
        old_png = self.png.read_bytes()
        old_model = self.model.read_bytes()
        with self.assertRaisesRegex(ValueError, "render_sides"):
            p.save(self.png, render_sides="invalid")
        self.assertEqual(self.png.read_bytes(), old_png)
        self.assertEqual(self.model.read_bytes(), old_model)

    def test_changed_model_stops_before_png_overwrite(self):
        p = TexturePainter.from_bbmodel(self.model)
        self.png.write_bytes(b"previous texture")
        data = self.read()
        data["elements"][0]["name"] = "changed"
        self.write(data)
        with self.assertRaisesRegex(ValueError, "Model changed"):
            p.save(self.png)
        self.assertEqual(self.png.read_bytes(), b"previous texture")
        self.assertEqual(self.read(), data)

    def test_unsigned_png_registration_does_not_compare_layout_versions(self):
        p = TexturePainter.from_bbmodel(self.model)
        p.save(self.png, register=False)
        data = self.read()
        data["elements"][0]["faces"]["north"]["rotation"] = 180
        self.write(data)
        before = self.model.read_bytes()
        TextureExporter.register_texture(self.png, self.model)
        Image.new("RGBA", (64, 32)).save(self.png)
        TextureExporter.register_texture(self.png, self.model)
        before = self.model.read_bytes()
        Image.new("RGBA", (32, 32)).save(self.png)
        with self.assertRaisesRegex(ValueError, "resolution"):
            TextureExporter.register_texture(self.png, self.model)
        self.assertEqual(self.model.read_bytes(), before)

    def test_unfinalized_uv_mode_requires_separate_uv_stage(self):
        data = self.read()
        data["meta"]["box_uv"] = True
        cube = data["elements"][0]
        cube["box_uv"], cube["autouv"] = True, 1
        cube["faces"]["up"]["uv"] = [2, 0, 6, 2]
        self.write(data)
        with self.assertRaisesRegex(ValueError, "UV mode is not finalized"):
            TexturePainter.from_bbmodel(self.model)
        self.assertEqual(self.read(), data)
        BoxUVPacker.apply_to_bbmodel(self.model)
        before = self.read()
        p = TexturePainter.from_bbmodel(self.model)
        p.save(self.png)
        self.assertEqual(uv_state(before), uv_state(self.read()))
        self.assertFalse(self.read()["elements"][0]["box_uv"])

    def test_invalid_uvs_fail_instead_of_guessing(self):
        original = self.read()
        for case in ("missing", "fractional", "outside", "overlap", "duplicate", "degenerate_mesh"):
            with self.subTest(case=case):
                data = copy.deepcopy(original)
                cube = data["elements"][0]
                if case == "missing":
                    del cube["faces"]["north"]["uv"]
                elif case == "fractional":
                    cube["faces"]["north"]["uv"][0] += 0.25
                elif case == "outside":
                    cube["faces"]["north"]["uv"][2] = 1000
                elif case == "overlap":
                    cube["faces"]["north"]["uv"] = cube["faces"]["south"]["uv"][:]
                elif case == "duplicate":
                    data["elements"][1]["name"] = cube["name"]
                else:
                    face = data["elements"][1]["faces"]["quad"]
                    first = face["vertices"][0]
                    second = face["vertices"][1]
                    face["uv"][second] = face["uv"][first][:]
                self.write(data)
                with self.assertRaises(ValueError):
                    TexturePainter.from_bbmodel(self.model)

    def test_no_alpha_squaring_or_old_embedded_pixels(self):
        data = self.read()
        data["textures"] = [{"source": "data:image/png;base64,not-an-image"}]
        self.write(data)
        p = TexturePainter.from_bbmodel(self.model)
        p.body.north.fill((255, 0, 0, 128))
        p.save(self.png)
        q = p.body.north.uv_info
        with Image.open(self.png) as image:
            self.assertEqual(image.getpixel((q["x"], q["y"])), (255, 0, 0, 128))
            self.assertEqual(image.getpixel((63, 31)), (0, 0, 0, 0))
        self.assertNotIn("source", self.read()["textures"][0])

    def test_shared_engine_and_duplicate_free_rectangles(self):
        self.assertEqual(MaxRectsPacker._prune_contained([(0, 0, 8, 8)]*2), [(0, 0, 8, 8)])

    def test_regenerating_geometry_does_not_attach_previous_png(self):
        p = TexturePainter.from_bbmodel(self.model)
        p.save(self.png)
        png_before = self.png.read_bytes()
        (ModelBuilder("new").add_group("root")
         .add_cube("changed", "root", from_=(0, 0, 0), to_=(4, 4, 4))
         .export_bbmodel(self.model))
        UVBuilder(self.model, start_size=(64, 32)).save()
        self.assertEqual(self.read()["textures"], [])
        self.assertEqual(self.png.read_bytes(), png_before)
        TextureExporter.register_texture(self.png, self.model)
        self.assertEqual(self.read()["textures"][0]["relative_path"], "texture.png")

    def test_repacking_nonrectangular_planar_mesh_uses_polygon_uv(self):
        data = self.read()
        mesh = data["elements"][1]
        mesh["vertices"][mesh["faces"]["quad"]["vertices"][2]][0] += 0.5
        self.write(data)
        before = self.model.read_bytes()
        BoxUVPacker.apply_to_bbmodel(self.model)
        mapped = json.loads(self.model.read_text(encoding="utf-8"))
        face = mapped["elements"][1]["faces"]["quad"]
        self.assertIsInstance(face["uv"], dict)
        self.assertEqual(set(face["uv"]), set(face["vertices"]))

    def test_rotated_and_flipped_non_square_faces(self):
        # Expected location of the local top-left marker in atlas coordinates.
        for rotation, corner in [(0, (0, 0)), (90, (2, 0)), (180, (2, 1)), (270, (0, 1))]:
            for flip_x in (False, True):
                for flip_y in (False, True):
                    with self.subTest(rotation=rotation, flip_x=flip_x, flip_y=flip_y):
                        uv = [5 if flip_x else 2, 4 if flip_y else 2,
                              2 if flip_x else 5, 2 if flip_y else 4]
                        self.write({"meta": {"model_format": "free", "box_uv": False},
                                    "resolution": {"width": 16, "height": 16},
                                    "elements": [{"name": "box", "type": "cube", "faces": {
                                        "north": {"uv": uv, "rotation": rotation, "texture": False}}}]})
                        p = TexturePainter.from_bbmodel(self.model)
                        p.box.north.set_pixel(0, 0, "#00ff00")
                        x, y = corner
                        if flip_x:
                            x = 2-x
                        if flip_y:
                            y = 1-y
                        self.assertEqual(p.compose_atlas().getpixel((2+x, 2+y)), (0, 255, 0, 255))


if __name__ == "__main__":
    unittest.main()
