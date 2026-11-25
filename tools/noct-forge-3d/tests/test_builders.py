from Tools.uv_builder import UVBuilder
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from lib import ModelBuilder
from Tools.TexturePainter import TexturePainter


class BuilderTests(unittest.TestCase):
    def test_tags_are_validated_and_deduplicated(self):
        builder = (ModelBuilder("tags")
                   .add_group("root", tags=["role:root", "role:root"])
                   .add_cube("body", "root", from_=(0, 0, 0), to_=(2, 2, 2),
                             tags=["material:cloth", "material:cloth"]))
        self.assertEqual(builder._groups["root"].tags, ["role:root"])
        self.assertEqual(builder._elements[0].tags, ["material:cloth"])
        with self.assertRaises(TypeError):
            ModelBuilder("bad").add_group("root", tags="material:wood")
        with self.assertRaises(ValueError):
            ModelBuilder("bad").add_group("root", tags=[""])

    def test_model_export_mirror_and_uvs(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "model.bbmodel"
            (ModelBuilder("test")
             .add_group("root")
             .add_transform_group("arm_left", "root", pivot=(4, 10, 0))
             .add_cube("arm_left_cube", "arm_left", from_=(3, 2, -1), to_=(5, 10, 1))
             .add_axis_quad("badge", "arm_left", from_=(5, 5, -1.1), size=(2, 2), normal="-Z")
             .mirror("arm_left", "arm_right")
             .export_bbmodel(output))
            UVBuilder(output, start_size=(32, 32)).save()
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["meta"]["model_format"], "free")
            self.assertEqual(data["meta"]["format_version"], "5.0")
            self.assertEqual(len(data["groups"]), 3)
            self.assertEqual(len(data["elements"]), 4)
            self.assertEqual(data["textures"], [])
            mirrored = next(item for item in data["elements"] if item["name"] == "arm_right_cube")
            self.assertEqual(mirrored["from"], [-5, 2, -1])
            self.assertEqual(mirrored["to"], [-3, 10, 1])
            uuids = [item["uuid"] for item in data["elements"]]
            self.assertEqual(len(uuids), len(set(uuids)))
            face_rectangles = [
                tuple(face["uv"])
                for item in data["elements"] if item["type"] == "cube"
                for face in item["faces"].values()
            ]
            occupied = set()
            for x1, y1, x2, y2 in face_rectangles:
                pixels = {(x, y) for x in range(min(x1, x2), max(x1, x2)) for y in range(min(y1, y2), max(y1, y2))}
                self.assertTrue(occupied.isdisjoint(pixels))
                occupied.update(pixels)

    def test_model_constraints_fail_before_export(self):
        builder = (ModelBuilder("limited", grid_step=1, max_nodes=1)
                   .add_group("root")
                   .add_cube("off_grid", "root", from_=(0.5, 0, 0), to_=(2.5, 2, 2)))
        report = builder.validate()
        self.assertEqual(report["node_count"], 2)
        self.assertEqual(len(report["errors"]), 2)

    def test_uniform_uv_scale_preserves_fixed_atlas(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "scaled.bbmodel"
            (ModelBuilder("scaled")
             .add_group("root")
             .add_cube("body", "root", from_=(0, 0, 0), to_=(2, 2, 2))
             .export_bbmodel(output))
            UVBuilder(output, start_size=(16, 16), fixed_texture_size=True, uv_scale=2).save()
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["resolution"], {"width": 16, "height": 16})
            self.assertTrue(all(
                abs(face["uv"][2] - face["uv"][0]) == 4
                for face in data["elements"][0]["faces"].values()
            ))

    def test_hierarchy_can_be_validated_before_geometry(self):
        builder = ModelBuilder("skeleton").add_group("root").add_group("arm")
        report = builder.validate_groups(["root", "arm", "missing"])
        self.assertIn("Missing required group: missing", report["errors"])
        self.assertEqual(report["roots"], ["arm", "root"])

    def test_texture_painter_resolution_from_bbmodel(self):
        with tempfile.TemporaryDirectory() as folder:
            model_path = Path(folder) / "model.bbmodel"
            (ModelBuilder("res_test")
             .add_group("root")
             .add_cube("head", "root", from_=(0, 0, 0), to_=(8, 8, 8))
             .export_bbmodel(model_path))
            UVBuilder(model_path, start_size=(128, 128)).save()

            painter = TexturePainter.from_bbmodel(model_path)
            self.assertEqual(painter.width, 128)
            self.assertEqual(painter.height, 128)

    def test_texture_painter_drawing_and_saving(self):
        with tempfile.TemporaryDirectory() as folder:
            model_path = Path(folder) / "model.bbmodel"
            texture_path = Path(folder) / "texture.png"
            (ModelBuilder("draw_test")
             .add_group("root")
             .add_cube("box", "root", from_=(0, 0, 0), to_=(4, 4, 4))
             .export_bbmodel(model_path))
            UVBuilder(model_path, start_size=(32, 32), allow_rectangular=False).save()

            painter = TexturePainter.from_bbmodel(model_path)
            painter.box.fill_box(top="#ffffff", bottom="#000000", sides="#ff0000")
            painter.box.north.set_pixel(0, 0, "#00ff00")
            saved_path = painter.save(str(texture_path))

            self.assertTrue(Path(saved_path).exists())
            with Image.open(saved_path) as img:
                self.assertEqual(img.size, (32, 32))
                self.assertEqual(img.mode, "RGBA")

            # Check that model.bbmodel was NOT modified with Base64
            model_data = json.loads(model_path.read_text(encoding="utf-8"))
            if model_data.get("textures"):
                for tex in model_data["textures"]:
                    self.assertNotIn("source", tex)

    def test_texture_painter_face_aliases(self):
        with tempfile.TemporaryDirectory() as folder:
            model_path = Path(folder) / "model.bbmodel"
            (ModelBuilder("alias_test")
             .add_group("root")
             .add_cube("cube", "root", from_=(0, 0, 0), to_=(4, 4, 4))
             .export_bbmodel(model_path))
            UVBuilder(model_path, start_size=(16, 16)).save()

            painter = TexturePainter.from_bbmodel(model_path)
            # Canonical ModelOrientation uses +Z as front (+Z is Blockbench south).
            self.assertEqual(painter.cube.front, painter.cube.south)
            self.assertEqual(painter.cube.back, painter.cube.north)
            self.assertEqual(painter.cube.top, painter.cube.up)
            self.assertEqual(painter.cube.bottom, painter.cube.down)
            painter.cube.fill_box(front="#111111", back="#222222")
            self.assertEqual(painter.cube.front.get_pixel(0, 0), (17, 17, 17, 255))
            self.assertEqual(painter.cube.back.get_pixel(0, 0), (34, 34, 34, 255))

    def test_end_to_end_model_builder_to_texture_painter_pot_resolution(self):
        # Create a model with multiple cubes that naturally exceed 32x32 footprint
        with tempfile.TemporaryDirectory() as folder:
            model_path = Path(folder) / "character.bbmodel"
            texture_path = Path(folder) / "texture.png"

            # 4 cubes of 6x6x6:
            # Each footprint: width 2*(6+6)=24, height 6+6=12 (area 288).
            # 4 cubes = 1152 px area > 32x32 (1024 px).
            # ModelBuilder starting at default (32, 32) must scale up to 64x64.
            builder = (ModelBuilder("character")
                       .add_group("root")
                       .add_cube("head", "root", from_=(-3, 12, -3), to_=(3, 18, 3))
                       .add_cube("torso", "root", from_=(-3, 6, -3), to_=(3, 12, 3))
                       .add_cube("leg_left", "root", from_=(-3, 0, -3), to_=(0, 6, 3))
                       .add_cube("leg_right", "root", from_=(0, 0, -3), to_=(3, 6, 3)))
            builder.export_bbmodel(model_path)
            UVBuilder(model_path, start_size=(32, 32), allow_rectangular=False).save()

            # 1. Verify the exported model has box_uv and 64x64 resolution
            data = json.loads(model_path.read_text(encoding="utf-8"))
            self.assertEqual(data["resolution"], {"width": 64, "height": 64})
            self.assertFalse(data["meta"]["box_uv"])
            for elem in data["elements"]:
                self.assertFalse(elem["box_uv"])
                self.assertEqual(elem["autouv"], 0)
                self.assertIn("uv_offset", elem)

            # 2. Verify TexturePainter reads 64x64 and paints accurately
            painter = TexturePainter.from_bbmodel(model_path)
            self.assertEqual(painter.width, 64)
            self.assertEqual(painter.height, 64)

            # Paint head front face
            painter.head.north.fill("#ff0000")
            painter.head.north.set_pixel(0, 0, "#00ff00")
            saved = painter.save(str(texture_path))

            # 3. Verify texture file on disk
            with Image.open(saved) as img:
                self.assertEqual(img.size, (64, 64))
                # Look up where head.north was mapped
                head_item = next(e for e in data["elements"] if e["name"] == "head")
                north_uv = head_item["faces"]["north"]["uv"]
                # Verify pixel at (north_uv[0], north_uv[1]) is #00ff00 (green)
                pixel = img.getpixel((north_uv[0], north_uv[1]))
                self.assertEqual(pixel, (0, 255, 0, 255))

    def test_detects_same_normal_coplanar_faces_and_submerged_cube(self):
        # Cube 4x4 and a 2x2 cube aligned to the exact outer wall
        builder = (ModelBuilder("coplanar_test")
                   .add_group("root")
                   .add_cube("box_big", "root", from_=(-2, 0, -2), to_=(2, 4, 2))
                   .add_cube("box_small", "root", from_=(0, 0, 0), to_=(2, 2, 2)))
        report = builder.validate()
        self.assertTrue(len(report["errors"]) > 0)
        error_text = " ".join(report["errors"])
        self.assertIn("Z-fighting coplanar face conflict", error_text)
        self.assertIn("completely submerged", error_text)

    def test_allows_abutting_joint_caps_opposite_normals(self):
        # Thigh ending at y=5 (down face normal -Y), shin starting at y=5 (up face normal +Y)
        # Stepped cross-section (4x4 to 3x3) to test abutting opposite-normal caps
        builder = (ModelBuilder("leg_joint")
                   .add_group("root")
                   .add_transform_group("thigh_bone", "root", pivot=(0, 11, 0))
                   .add_cube("thigh", "thigh_bone", from_=(-2, 5, -2), to_=(2, 11, 2))
                   .add_transform_group("shin_bone", "thigh_bone", pivot=(0, 5, 0))
                   .add_cube("shin", "shin_bone", from_=(-1.5, 0, -1.5), to_=(1.5, 5, 1.5)))
        report = builder.validate()
        self.assertEqual(report["errors"], [])

    def test_allows_rotated_penetrating_elements(self):
        # Head cube and an ear cube rotated at an angle
        builder = (ModelBuilder("elf_head")
                   .add_group("root")
                   .add_cube("head", "root", from_=(-4, 10, -4), to_=(4, 18, 4))
                   .add_transform_group("ear_left", "root", pivot=(4, 14, 0), rotation=(0, 0, -15))
                   .add_cube("ear", "ear_left", from_=(3.5, 13, -1), to_=(8.5, 16, 1)))
        report = builder.validate()
        self.assertEqual(report["errors"], [])

    def test_allows_inflated_layers(self):
        # Body and jacket sharing base coordinates but separated by inflate
        builder = (ModelBuilder("layered_outfit")
                   .add_group("root")
                   .add_cube("body", "root", from_=(-4, 0, -2), to_=(4, 10, 2))
                   .add_cube("jacket", "root", from_=(-4, 0, -2), to_=(4, 10, 2), inflate=0.2))
        report = builder.validate()
        self.assertEqual(report["errors"], [])

    def test_can_disable_coplanar_check_if_requested(self):
        builder = (ModelBuilder("coplanar_disabled", check_coplanar=False)
                   .add_group("root")
                   .add_cube("box_big", "root", from_=(-2, 0, -2), to_=(2, 4, 2))
                   .add_cube("box_small", "root", from_=(0, 0, 0), to_=(2, 2, 2)))
        report = builder.validate()
        self.assertEqual(report["errors"], [])

    def test_integer_dimensions_validation(self):
        # Fractional cube dimensions trigger error
        builder = (ModelBuilder("fractional_cube")
                   .add_group("root")
                   .add_cube("bad_cube", "root", from_=(0, 0, 0), to_=(2.5, 3, 4)))
        report = builder.validate()
        self.assertTrue(any("non-integer cube dimensions" in e for e in report["errors"]))

        # Fractional quad dimensions trigger error
        builder_quad = (ModelBuilder("fractional_quad")
                        .add_group("root")
                        .add_axis_quad("bad_quad", "root", from_=(0, 0, 0), size=(2.5, 3), normal="+Z"))
        report_quad = builder_quad.validate()
        self.assertTrue(any("non-integer dimensions" in e for e in report_quad["errors"]))

        # Can disable integer dimensions check if needed
        builder_disabled = (ModelBuilder("disabled_check", require_integer_dimensions=False)
                            .add_group("root")
                            .add_cube("frac_cube", "root", from_=(0, 0, 0), to_=(2.5, 3, 4)))
        report_disabled = builder_disabled.validate()
        self.assertEqual(report_disabled["errors"], [])

    def test_quad_cube_coplanar_conflict(self):
        # Quad coplanar with cube face (Z=2)
        builder = (ModelBuilder("coplanar_quad")
                   .add_group("root")
                   .add_cube("body", "root", from_=(-2, 0, -2), to_=(2, 4, 2))
                   .add_axis_quad("patch", "root", from_=(-1, 1, 2), size=(2, 2), normal="+Z"))
        report = builder.validate()
        self.assertTrue(any("Z-fighting" in e and "'patch'" in e and "'body'" in e for e in report["errors"]))

        # Quad with an intentional 0.05 offset passes cleanly
        builder_offset = (ModelBuilder("offset_quad")
                          .add_group("root")
                          .add_cube("body", "root", from_=(-2, 0, -2), to_=(2, 4, 2))
                          .add_axis_quad("patch", "root", from_=(-1, 1, 2.05), size=(2, 2), normal="+Z"))
        report_offset = builder_offset.validate()
        self.assertEqual(report_offset["errors"], [])

    def test_texture_painter_with_quads(self):
        with tempfile.TemporaryDirectory() as folder:
            model_path = Path(folder) / "quad_model.bbmodel"
            tex_path = Path(folder) / "texture.png"
            (ModelBuilder("quad_test")
             .add_group("root")
             .add_cube("body", "root", from_=(-2, 0, -2), to_=(2, 4, 2))
             .add_axis_quad("pocket", "root", from_=(-1, 1, 2.05), size=(2, 2), normal="+Z")
             .export_bbmodel(model_path))
            UVBuilder(model_path, start_size=(32, 32)).save()

            painter = TexturePainter.from_bbmodel(model_path)
            self.assertIn("pocket", painter.elements)
            self.assertIn("quad", painter.pocket.faces)
            painter.pocket.quad.fill("#123456")
            painter.pocket.quad.set_pixel(0, 0, "#abcdef")
            saved = painter.save(str(tex_path))
            self.assertTrue(Path(saved).exists())
            with Image.open(saved) as img:
                self.assertEqual(img.size, (32, 32))


if __name__ == "__main__":
    unittest.main()
