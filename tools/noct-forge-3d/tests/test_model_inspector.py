"""Unit tests for Tools.model_inspector CLI and inspection functions."""

import copy
import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

from lib.model_builder import ModelBuilder
from Tools.model_inspector import (
    calculate_bounding_box,
    inspect_summary,
    build_tree_ascii,
    inspect_element,
    inspect_group,
    inspect_tag,
)


class TestModelInspector(unittest.TestCase):
    def setUp(self):
        self.builder = ModelBuilder("test_dummy")
        self.builder.add_group("root")
        self.builder.add_transform_group("body", "root", pivot=(0, 10, 0))
        self.builder.add_cube("chest", "body", from_=(-2, 10, -2), to_=(2, 14, 2))
        self.builder.add_cube("head", "body", from_=(-1, 14, -1), to_=(1, 16, 1))

    def test_from_bbmodel_roundtrip(self):
        doc = {
            "meta": {"model_format": "free"},
            "name": "roundtrip_test",
            "resolution": {"width": 64, "height": 64},
            "unhandled_root_fields": {"model_as_code": {"uv_ready": True, "uv_packing": {"uv_scale": 2}}},
            "groups": [
                {"name": "root", "origin": [0, 0, 0], "rotation": [0, 0, 0], "uuid": "u1"},
                {"name": "child", "origin": [0, 5, 0], "rotation": [0, 0, 0], "uuid": "u2"},
            ],
            "outliner": [
                {
                    "uuid": "u1",
                    "children": [
                        {
                            "uuid": "u2",
                            "children": ["e1"],
                        }
                    ],
                }
            ],
            "elements": [
                {
                    "name": "box1",
                    "type": "cube",
                    "uuid": "e1",
                    "from": [0, 5, 0],
                    "to": [2, 7, 2],
                    "origin": [0, 5, 0],
                    "faces": {"north": {"uv": [0, 0, 2, 2], "texture": 0}},
                }
            ],
            "textures": [{"name": "skin.png", "uv_width": 64, "uv_height": 64, "render_sides": "front"}],
        }

        reconstructed = ModelBuilder.from_bbmodel_data(doc)
        self.assertEqual(reconstructed.name, "roundtrip_test")
        self.assertIn("root", reconstructed._groups)
        self.assertIn("child", reconstructed._groups)
        self.assertEqual(reconstructed._groups["child"].parent, "root")
        self.assertEqual(len(reconstructed._elements), 1)
        self.assertEqual(reconstructed._elements[0].parent, "child")

        summary = inspect_summary(doc, reconstructed)
        self.assertEqual(summary["uv_status"], "READY")
        self.assertEqual(summary["uv_scale"], 2)
        self.assertEqual(summary["groups_count"], 2)
        self.assertEqual(summary["elements_count"], 1)
        self.assertEqual(len(summary["textures"]), 1)
        self.assertEqual(summary["textures"][0]["name"], "skin.png")

    def test_bounding_box(self):
        bmin, bmax = calculate_bounding_box(self.builder)
        self.assertEqual(bmin, (-2.0, 10.0, -2.0))
        self.assertEqual(bmax, (2.0, 16.0, 2.0))

    def test_tree_ascii(self):
        tree = build_tree_ascii(self.builder)
        self.assertIn("root", tree)
        self.assertIn("body", tree)
        self.assertIn("2 cubes", tree)

    def test_element_inspection(self):
        elem = inspect_element(self.builder, "chest")
        self.assertIsNotNone(elem)
        self.assertEqual(elem["name"], "chest")
        self.assertEqual(elem["size"], [4.0, 4.0, 4.0])
        self.assertEqual(elem["parent_group"], "body")
        self.assertIsNone(elem["parent_armature"])
        self.assertEqual(elem["face_count"], 0)

        none_elem = inspect_element(self.builder, "nonexistent")
        self.assertIsNone(none_elem)

    def test_group_inspection(self):
        group = inspect_group(self.builder, "body")
        self.assertIsNotNone(group)
        self.assertEqual(group["name"], "body")
        self.assertEqual(group["parent"], "root")
        self.assertEqual(group["elements"], ["chest", "head"])

    def test_tag_summary_and_filter(self):
        self.builder._groups["body"].tags.append("role:body")
        self.builder._elements[0].tags.append("material:cloth")
        summary = inspect_summary({}, self.builder)
        self.assertEqual(summary["tags"], {"material:cloth": 1, "role:body": 1})
        self.assertEqual(inspect_tag(self.builder, "material:cloth")["elements"], ["chest"])

    def test_check_returns_nonzero_for_geometry_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "invalid.bbmodel"
            builder = ModelBuilder("invalid").add_group("root")
            builder.add_cube("one", "root", from_=(0, 0, 0), to_=(2, 2, 2))
            builder.export_bbmodel(model)
            data = json.loads(model.read_text(encoding="utf-8"))
            duplicate = copy.deepcopy(data["elements"][0])
            duplicate["name"] = "two"
            duplicate["uuid"] = str(uuid.uuid4())
            data["elements"].append(duplicate)
            data["outliner"][0]["children"].append(duplicate["uuid"])
            model.write_text(json.dumps(data), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, "-m", "Tools.model_inspector", str(model), "--check"],
                capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 2)
            self.assertIn("ERRORS", proc.stdout)

    def test_cli_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            model_file = Path(temp) / "model.bbmodel"
            ModelBuilder("inspected").add_group("root").add_cube(
                "body", "root", from_=(0, 0, 0), to_=(2, 2, 2)).export_bbmodel(model_file)

            cmd = [sys.executable, "-m", "Tools.model_inspector", str(model_file), "--json"]
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0)
            data = json.loads(proc.stdout)
            self.assertIn("summary", data)
            self.assertEqual(data["summary"]["name"], "inspected")


if __name__ == "__main__":
    unittest.main()
