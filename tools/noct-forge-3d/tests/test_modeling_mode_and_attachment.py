import json
import math
import tempfile
import unittest
from pathlib import Path

from lib import MeshGeometry, ModelBuilder, ModelOrientation, Placement


class ModelingModeAndAttachmentTests(unittest.TestCase):
    @staticmethod
    def _box_geometry(center, size=2.0):
        half = size / 2
        x, y, z = center
        vertices = {
            "000": (x - half, y - half, z - half), "001": (x - half, y - half, z + half),
            "010": (x - half, y + half, z - half), "011": (x - half, y + half, z + half),
            "100": (x + half, y - half, z - half), "101": (x + half, y - half, z + half),
            "110": (x + half, y + half, z - half), "111": (x + half, y + half, z + half),
        }
        faces = {
            "bottom": ("000", "100", "101", "001"), "top": ("010", "011", "111", "110"),
            "front": ("001", "101", "111", "011"), "back": ("000", "010", "110", "100"),
            "left": ("000", "001", "011", "010"), "right": ("100", "110", "111", "101"),
        }
        return MeshGeometry.create(vertices, faces, closed=True, primitive="box_mesh")

    def test_box_mode_rejects_free_geometry_at_creation(self):
        builder = ModelBuilder("boxes", modeling_mode="box").add_group("root")
        builder.add_box("body", "root", size=(4, 6, 2))
        with self.assertRaisesRegex(ValueError, "free polygon meshes"):
            builder.add_cylinder("neck", "root", radius=1, height=2)

    def test_free_mode_keeps_native_cube_rules_without_conversion(self):
        builder = (ModelBuilder("free", modeling_mode="free")
                   .add_group("root")
                   .add_cube("cube", "root", from_=(0, 0, 0), to_=(2, 2, 2)))
        builder.add_triangle("point", "root", ((0, 3, 0), (1, 3, 0), (0, 4, 0)))
        self.assertEqual(builder._elements[0].kind, "cube")
        self.assertEqual(len(builder._elements[1].faces["surface"]["vertices"]), 3)
        self.assertEqual(builder.validate()["errors"], [])

    def test_auto_uv_and_validation_metadata_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "box.bbmodel"
            builder = (ModelBuilder("export", modeling_mode="box", check_coplanar=False)
                       .add_group("root")
                       .add_cube("body", "root", from_=(0, 0, 0), to_=(2, 2, 2)))
            builder.export_bbmodel(path, auto_uv=True, island_padding=1)
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data["unhandled_root_fields"]["model_as_code"]
            self.assertEqual(meta["modeling_mode"], "box")
            self.assertFalse(meta["validation_policy"]["check_coplanar"])
            self.assertTrue(meta["uv_ready"])
            loaded = ModelBuilder.from_bbmodel(path)
            self.assertEqual(loaded.modeling_mode, "box")
            self.assertFalse(loaded.check_coplanar)

    def test_orientation_is_persisted_and_validated(self):
        orientation = ModelOrientation(up="+Y", front="+X")
        builder = (ModelBuilder("orientation", orientation=orientation)
                   .add_group("root")
                   .add_cube("body", "root", from_=(0, 0, 0), to_=(2, 2, 2)))
        self.assertEqual(builder.orientation.front, "+X")
        self.assertEqual(builder.get_surface_contact("body", "front").normal, (1., 0., 0.))
        self.assertEqual(builder.get_surface_contact("body", "right").normal, (0., 0., -1.))
        with self.assertRaisesRegex(ValueError, "perpendicular"):
            ModelOrientation(up="+Y", front="-Y")

    def test_box_rectangular_quad_round_trips_and_rejects_forged_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "quad.bbmodel"
            builder = ModelBuilder("quad", modeling_mode="box").add_group("root")
            builder.add_axis_quad("panel", "root", from_=(0, 0, 0), size=(2, 3), normal="+Z")
            builder.export_bbmodel(path)
            loaded = ModelBuilder.from_bbmodel(path)
            self.assertEqual(loaded.modeling_mode, "box")
            self.assertEqual(loaded._elements[0].primitive, "rectangular_quad")

            data = json.loads(path.read_text(encoding="utf-8"))
            element = data["elements"][0]
            element["vertices"][next(iter(element["vertices"]))][0] = 1.0
            with self.assertRaisesRegex(ValueError, "rectangular_quad"):
                ModelBuilder.from_bbmodel_data(data)

    def test_import_rejects_free_mesh_when_document_declares_box_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "free.bbmodel"
            builder = ModelBuilder("free", modeling_mode="free").add_group("root")
            builder.add_triangle("tip", "root", ((0, 0, 0), (1, 0, 0), (0, 1, 0)))
            builder.export_bbmodel(path)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["unhandled_root_fields"]["model_as_code"]["modeling_mode"] = "box"
            with self.assertRaisesRegex(ValueError, "box model contains free polygon meshes"):
                ModelBuilder.from_bbmodel_data(data)


if __name__ == "__main__":
    unittest.main()
