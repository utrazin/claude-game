import contextlib
import copy
import io
import json
import runpy
import tempfile
import unittest
import uuid
from pathlib import Path

from Tools.animation_export import export_animations
from Tools.edit_diff import main as edit_diff
from Tools.model_export import export_project
from Tools.model_import import import_bbmodel
from lib.animation import AnimationEditor

from tests.test_model_edit_diff import RIG_RECIPE


def strip_metadata(node):
    if isinstance(node, dict):
        return {k: strip_metadata(v) for k, v in node.items()
                if not k.startswith("model_as_code") and k != "unhandled_root_fields"}
    if isinstance(node, list):
        return [strip_metadata(v) for v in node]
    return node


def cube(name, frm, to):
    return {"name": name, "box_uv": False, "rescale": False, "locked": False, "visibility": True,
            "from": frm, "to": to, "autouv": 0, "color": 0, "origin": frm, "rotation": [0, 0, 0],
            "inflate": 0, "faces": {f: {"uv": [0, 0, 1, 1], "texture": 0}
                                    for f in ("north", "east", "south", "west", "up", "down")},
            "type": "cube", "uuid": str(uuid.uuid4())}


def group(name, origin, rotation=(0, 0, 0)):
    return {"name": name, "origin": list(origin), "rotation": list(rotation), "color": 0,
            "uuid": str(uuid.uuid4()), "export": True, "isOpen": True, "locked": False,
            "visibility": True, "autouv": 0}


def native_document(*, nested=True):
    body, arm = cube("body", [-4, 12, -2], [4, 24, 2]), cube("arm", [4, 12, -4], [8, 24, 4])
    if not nested:
        return {"meta": {"format_version": "5.0", "model_format": "free", "box_uv": False}, "name": "flat",
                "elements": [body, arm], "groups": [], "outliner": [body["uuid"], arm["uuid"]],
                "textures": [], "animations": [], "resolution": {"width": 16, "height": 16}}
    root, pivot = group("root", (0, 0, 0)), group("arm_pivot", (4, 24, 0), (10, 0, 0))
    return {"meta": {"format_version": "5.0", "model_format": "free", "box_uv": False}, "name": "native",
            "elements": [body, arm], "groups": [root, pivot],
            "outliner": [{"uuid": root["uuid"], "isOpen": True, "children": [
                body["uuid"], {"uuid": pivot["uuid"], "isOpen": True, "children": [arm["uuid"]]}]}],
            "textures": [], "animations": [], "resolution": {"width": 16, "height": 16}}


class ImportTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def write_source(self, document, name="foreign.bbmodel"):
        path = self.root / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def project(self, name="imported"):
        return self.root / "projects" / name

    def foreign_rig(self):
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        rigdir = self.root / "rig_recipe"
        init_project(rigdir, asset_id="rig")
        context = resolve_asset(f"{rigdir}#rig")
        script = context.scripts / "generate_model.py"
        script.write_text(RIG_RECIPE, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(script), run_name="__main__")
        model = context.model
        model.write_text(json.dumps(strip_metadata(json.loads(model.read_text(encoding="utf-8")))), encoding="utf-8")
        editor = AnimationEditor.from_bbmodel(model)
        clip = editor.animation("bend", duration=1, loop=True)
        clip.bone("distal_L", armature="character").key(0, rotation=(0, 0, 0)).key(0.5, rotation=(0, 0, 25))
        editor.save()
        return model

    def diff_code(self, project):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return edit_diff([str(project)])

    def test_rig_without_recipe_metadata_is_imported_verified_and_exported(self):
        source = self.foreign_rig()
        report = import_bbmodel(source, self.project())
        self.assertEqual((report["status"], report["differences"], report["skipped"]), ("pass", [], []), report)
        self.assertEqual(len(report["written"]), 2)
        self.assertEqual(self.diff_code(self.project()), 0)

        exported = export_project(self.project())
        self.assertEqual(exported["status"], "pass", exported)
        self.assertEqual(export_animations(self.project())["status"], "pass")
        self.assertEqual(self.diff_code(self.project()), 0)
        names = {e["name"] for e in json.loads((self.project() / "assets/imported/model.bbmodel").read_text(encoding="utf-8"))["elements"]}
        self.assertTrue({"limb_L", "limb_R", "distal_L", "proximal_R"} <= names)

    def test_cubes_in_rotated_nested_groups_are_imported(self):
        source = self.write_source(native_document())
        report = import_bbmodel(source, self.project())
        self.assertEqual((report["status"], report["differences"]), ("pass", []), report)
        text = (self.project() / "scripts/imported/generate_model.py").read_text(encoding="utf-8")
        self.assertIn("add_transform_group('arm_pivot', 'root'", text)
        self.assertEqual(export_project(self.project())["status"], "pass")
        self.assertEqual(self.diff_code(self.project()), 0)

    def test_elements_without_any_group_get_a_root_group(self):
        report = import_bbmodel(self.write_source(native_document(nested=False)), self.project())
        self.assertEqual((report["status"], report["differences"]), ("pass", []), report)
        self.assertIn("add_group('root'", (self.project() / "scripts/imported/generate_model.py").read_text(encoding="utf-8"))
        self.assertEqual(export_project(self.project())["status"], "pass")

    def test_other_model_formats_are_refused_with_instructions(self):
        document = native_document()
        document["meta"]["model_format"] = "bedrock"
        report = import_bbmodel(self.write_source(document), self.project())
        self.assertEqual(report["status"], "fail")
        self.assertIn("Convert Project", report["issues"][0])
        self.assertFalse((self.project() / "scripts").exists())

    def test_unsupported_element_types_are_named(self):
        document = native_document()
        document["elements"].append({"type": "null_object", "name": "marker", "uuid": str(uuid.uuid4())})
        report = import_bbmodel(self.write_source(document), self.project())
        self.assertEqual(report["status"], "fail")
        self.assertIn("null_object", report["issues"][0])

    def test_a_locator_is_only_mentioned(self):
        document = native_document()
        locator = {"type": "locator", "name": "hand_socket", "position": [6, 24, 0], "rotation": [0, 0, 0],
                   "uuid": str(uuid.uuid4())}
        document["elements"].append(locator)
        document["outliner"][0]["children"][1]["children"].append(locator["uuid"])
        report = import_bbmodel(self.write_source(document), self.project())
        self.assertEqual((report["status"], report["differences"]), ("pass", []), report)
        self.assertIn("locator hand_socket: the builder has no locators", report["notes"][0])
        self.assertEqual(export_project(self.project())["status"], "pass")

    def test_existing_recipe_is_not_overwritten_without_force(self):
        source = self.write_source(native_document())
        self.assertEqual(import_bbmodel(source, self.project())["status"], "pass")
        self.assertEqual(import_bbmodel(source, self.project())["status"], "fail")
        self.assertEqual(import_bbmodel(source, self.project(), force=True)["status"], "pass")

    def test_existing_model_and_animation_recipe_are_never_overwritten_without_force(self):
        from Tools.asset_init import init_project
        project = self.project()
        init_project(project, asset_id="imported", animation=True)
        (project / "assets/imported/model.bbmodel").write_text("PRECIOUS MODEL", encoding="utf-8")
        (project / "scripts/imported/generate_animation.py").write_text("PRECIOUS SCRIPT", encoding="utf-8")
        report = import_bbmodel(self.write_source(native_document()), project)
        self.assertEqual(report["status"], "fail")
        self.assertIn("model.bbmodel", report["issues"][0])
        self.assertIn("generate_animation.py", report["issues"][0])
        self.assertEqual((project / "assets/imported/model.bbmodel").read_text(encoding="utf-8"), "PRECIOUS MODEL")
        self.assertEqual((project / "scripts/imported/generate_animation.py").read_text(encoding="utf-8"), "PRECIOUS SCRIPT")

    def test_force_copies_what_it_overwrites_into_history(self):
        source = self.write_source(native_document())
        self.assertIsNone(import_bbmodel(source, self.project())["backup"])
        old_recipe = (self.project() / "scripts/imported/generate_model.py").read_text(encoding="utf-8")
        report = import_bbmodel(source, self.project(), force=True)
        backup = Path(report["backup"])
        self.assertEqual((backup / "generate_model.py").read_text(encoding="utf-8"), old_recipe)
        self.assertTrue((backup / "model.bbmodel").exists())
        self.assertEqual(backup.parent, self.project() / "history")

    def test_meshes_the_builder_rejects_are_skipped_and_reported(self):
        document = copy.deepcopy(native_document())
        arm = document["elements"][1]
        document["elements"][1] = {
            "name": "bad", "origin": [0, 0, 0], "rotation": [0, 0, 0], "visibility": True, "uuid": arm["uuid"],
            "vertices": {"a": [0, 0, 0], "b": [2, 0, 0], "c": [2, 2, 0], "d": [1, 0.5, 0]},
            "faces": {"f": {"vertices": ["a", "b", "c", "d"], "texture": False}}, "type": "mesh"}
        report = import_bbmodel(self.write_source(document), self.project())
        self.assertTrue(any("bad" in line and "the builder rejects" in line for line in report["skipped"]), report)


if __name__ == "__main__":
    unittest.main()
