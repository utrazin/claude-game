import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from lib import ModelBuilder
from lib.geometry_types import MeshFace, MeshGeometry
from Tools.TexturePainter import TexturePainter
from Tools.uv_builder import UVBuilder


class DeclarativeTexturePainterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.bbmodel"

    def cube_painter(self):
        (ModelBuilder("declarative")
         .add_group("root", tags=["collection:character"])
         .add_cube("body", "root", from_=(0, 0, 0), to_=(4, 4, 4),
                   tags=["material:cloth"])
         .export_bbmodel(self.model))
        UVBuilder(self.model, start_size=(64, 32)).save()
        return TexturePainter.from_bbmodel(self.model)

    def test_stamp_is_exact_anchored_and_strict_by_default(self):
        painter = self.cube_painter()
        face = painter.body.front.fill("#101010")
        face.stamp(["AB", "BA"], {"A": "#ff0000", "B": "#00ff00"},
                   anchor="center")
        self.assertEqual(face.get_pixel(1, 1), (255, 0, 0, 255))
        self.assertEqual(face.get_pixel(2, 1), (0, 255, 0, 255))
        self.assertEqual(face.get_pixel(1, 2), (0, 255, 0, 255))
        with self.assertRaisesRegex(ValueError, "does not fit"):
            face.stamp(["XXXXX"], {"X": "#ffffff"}, anchor="top_left")
        face.stamp(["XXXXX"], {"X": "#ffffff"}, anchor="top_left", clip=True)

    def test_box_band_and_patch_keep_face_fast_path_available(self):
        painter = self.cube_painter()
        painter.body.fill_box(sides="#202020", top="#303030", bottom="#101010")
        painter.body.band("y", 0, 0.5).fill("#ff0000")
        self.assertEqual(painter.body.north.get_pixel(0, 0), (32, 32, 32, 255))
        self.assertEqual(painter.body.north.get_pixel(0, 3), (255, 0, 0, 255))
        painter.body.patch("front", center=(0.5, 0.5), size=(0.5, 0.5)).fill("#00ff00")
        self.assertEqual(painter.body.south.get_pixel(1, 1), (0, 255, 0, 255))
        self.assertNotEqual(painter.body.north.get_pixel(1, 1), (0, 255, 0, 255))

    def test_tags_are_explicit_and_ancestor_inheritance_is_opt_in(self):
        painter = self.cube_painter()
        cloth = painter.select(tag="material:cloth")
        inherited = painter.select(tag="collection:character", include_ancestors=True)
        not_inherited = painter.select(tag="collection:character")
        self.assertEqual(len(cloth), 1)
        self.assertEqual(len(inherited), 1)
        self.assertEqual(len(not_inherited), 0)
        self.assertIsInstance(cloth.elements, tuple)
        cloth.fill("#445566")
        self.assertEqual(painter.body.up.get_pixel(0, 0), (68, 85, 102, 255))

    def test_surface_callback_receives_frozen_transformed_samples(self):
        (ModelBuilder("transformed")
         .add_transform_group("root", pivot=(0, 0, 0), rotation=(0, 0, 90))
         .add_cube("body", "root", from_=(0, 0, 0), to_=(2, 4, 2),
                   origin=(0, 0, 0), rotation=(0, 90, 0), tags=["material:test"])
         .export_bbmodel(self.model))
        UVBuilder(self.model, start_size=(64, 32)).save()
        painter = TexturePainter.from_bbmodel(self.model)
        seen = []

        def paint(sample):
            if sample.face_name == "north":
                seen.append(sample)
            return "#123456" if sample.normalized_position[1] < 0.5 else None

        painter.body.paint_surface(paint)
        self.assertTrue(seen)
        sample = seen[0]
        self.assertNotEqual(sample.element_position, sample.model_position)
        self.assertAlmostEqual(sum(value * value for value in sample.model_normal), 1.0)
        self.assertEqual(sample.tags, ("material:test",))
        with self.assertRaises(FrozenInstanceError):
            sample.face_name = "changed"

    def test_polygon_sampling_uses_all_vertices_and_callback_can_preserve_pixels(self):
        builder = ModelBuilder("surface", require_integer_dimensions=False).add_group("root")
        vertices = {"a": (0, 0, 0), "b": (4, 0, 0), "c": (3, 3, 1), "d": (0, 3, 0)}
        builder.add_mesh("panel", "root", MeshGeometry.create(vertices,
                         {"surface": MeshFace(("a", "b", "c", "d"), group="front")}),
                         tags=["material:panel"])
        builder.export_bbmodel(self.model)
        UVBuilder(self.model, start_size=(32, 16), uv_scale=2,
                  require_integer_uvs=False).save()
        data = json.loads(self.model.read_text(encoding="utf-8"))
        face = next(face for face in data["elements"][0]["faces"].values()
                    if face.get("model_as_code_group") == "front")
        face["rotation"] = 90
        self.model.write_text(json.dumps(data), encoding="utf-8")
        painter = TexturePainter.from_bbmodel(self.model)
        samples = []

        def paint(sample):
            samples.append(sample)
            return "#abcdef" if sample.element_position[0] < 2 else None

        painter.panel.group("front").paint_surface(paint)
        self.assertGreater(len(samples), 4)
        self.assertTrue(any(sample.element_position[2] > 0 for sample in samples))
        canvas = painter.panel.group("front").faces[0].canvas
        self.assertTrue(any(pixel[3] for pixel in canvas.image.get_flattened_data()))

    def test_spatial_painting_rejects_shared_follower_context(self):
        builder = ModelBuilder("shared").add_group("root")
        builder.add_cube("owner", "root", from_=(0, 0, 0), to_=(2, 2, 2))
        builder.add_cube("follower", "root", from_=(4, 0, 0), to_=(6, 2, 2))
        builder.export_bbmodel(self.model)
        uv = UVBuilder(self.model, start_size=(64, 32)).clear_sharing()
        for face in ("north", "south", "east", "west", "up", "down"):
            uv.share_uv(("follower", face), source=("owner", face))
        uv.save()
        painter = TexturePainter.from_bbmodel(self.model)
        with self.assertRaisesRegex(ValueError, "shared UV followers"):
            painter.follower.band("y", 0, 1)

    def test_texture_cli_filters_element_face_and_tag(self):
        self.cube_painter()
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-m", "Tools.TexturePainter.cli", str(self.model),
             "--element", "body", "--face", "north", "--tag", "material:cloth"],
            cwd=root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[body] cube; 6 faces", result.stdout)
        self.assertIn("north:", result.stdout)
        self.assertNotIn("south:", result.stdout)

    def test_texture_cli_json_is_machine_readable_and_quiet_suppresses_header(self):
        self.cube_painter()
        root = Path(__file__).resolve().parents[1]
        json_result = subprocess.run(
            [sys.executable, "-m", "Tools.TexturePainter.cli", str(self.model),
             "--element", "body", "--face", "north", "--json"],
            cwd=root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(json_result.returncode, 0, json_result.stderr)
        payload = json.loads(json_result.stdout)
        self.assertEqual(payload["resolution"], [64, 32])
        self.assertEqual(list(payload["elements"][0]["faces"]), ["north"])

        quiet_result = subprocess.run(
            [sys.executable, "-m", "Tools.TexturePainter.cli", str(self.model), "--quiet"],
            cwd=root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(quiet_result.returncode, 0, quiet_result.stderr)
        self.assertEqual(quiet_result.stdout, "")


if __name__ == "__main__":
    unittest.main()
