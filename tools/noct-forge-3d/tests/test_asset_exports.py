import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from lib import ModelBuilder, AnimationEditor
from lib.primitives import quad_sphere
from Tools.asset_init import init_project
from Tools._resolve import resolve_asset
from Tools.asset_export import asset_export, export_targets
from Tools.texture_export import texture_export
from Tools.texture_variant import register_variant
from Tools.uv_packer import BoxUVPacker


def glb_data(path):
    payload = path.read_bytes()
    magic, version, size = struct.unpack_from("<4sII", payload)
    assert (magic, version, size) == (b"glTF", 2, len(payload))
    length, kind = struct.unpack_from("<II", payload, 12)
    assert kind == 0x4e4f534a
    document = json.loads(payload[20:20+length])
    return document, payload[20+length+8:]


def accessor(doc, binary, index):
    record = doc["accessors"][index]
    view = doc["bufferViews"][record["bufferView"]]
    components = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[record["type"]]
    code = "f" if record["componentType"] == 5126 else "H"
    start = view.get("byteOffset", 0)+record.get("byteOffset", 0)
    values = struct.unpack_from("<"+code*record["count"]*components, binary, start)
    return [values[i:i+components] for i in range(0, len(values), components)]


class AssetExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "characters"
        init_project(self.root, asset_id="hero")
        self.target = f"{self.root}#hero"
        self.context = resolve_asset(self.target)
        builder = ModelBuilder("hero").add_group("root")
        builder.add_transform_group("head", "root", pivot=(0, 8, 0))
        builder.add_box("head_mesh", "head", size=(4,4,4), at=(0,8,0))
        builder.add_box("body", "root", size=(6,8,4), at=(0,0,0))
        builder.export_bbmodel(self.context.model)
        BoxUVPacker.apply_to_bbmodel(self.context.model, island_padding=1)
        self.assertEqual(texture_export(self.target)["status"], "pass")
        editor = AnimationEditor.from_bbmodel(self.context.model)
        editor.animation("idle", duration=1, loop=True).group("head").key(0, rotation=(0,0,0)).key(.5, rotation=(0,30,0)).key(1, rotation=(0,0,0))
        editor.save()

    def validate(self, path):
        script = Path(__file__).with_name("gltf_validator_check.js")
        if shutil.which("node") is None or not (script.parent.parent / "node_modules" / "gltf-validator").is_dir():
            self.skipTest("glTF validator unavailable: install Node and run `npm ci` (see `py -3.12 -m Tools.forge doctor`)")
        run = subprocess.run(["node", str(script), str(path)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout+run.stderr)

    def test_five_expressions_reuse_geometry_and_only_default_is_registered(self):
        # A saved paint recipe reads the variant, without consulting model recipes.
        (self.context.scripts / "generate_texture.py").write_text(
            'from Tools.recipe_context import recipe_paths\n'
            'from Tools.TexturePainter import TexturePainter\n'
            'paths = recipe_paths(__file__)\n'
            'colors = {"neutral": (20,30,40), "angry": (200,30,40), "happy": (20,200,40), "sad": (20,30,200), "surprised": (200,200,40)}\n'
            'p = TexturePainter.from_bbmodel(paths.model)\n'
            'p.fill_all(colors[paths.variant])\n'
            'p.save(paths.texture)\n')
        original = self.context.model.read_bytes()
        images = []
        for expression in ("neutral", "angry", "happy", "sad", "surprised"):
            register_variant(self.target, expression)
            report = texture_export(self.target, variant=expression)
            self.assertEqual(report["status"], "pass", report)
            self.assertEqual(self.context.model.read_bytes(), original)
            report = asset_export(self.target, output=f"engine/hero/expressions/{expression}.png", variant=expression)
            with Image.open(report["output"]) as image, Image.open(self.context.texture) as default:
                self.assertEqual(image.size, default.size)
                images.append(image.tobytes())
            head = asset_export(self.target, output=f"heads/{expression}.glb", include=["head"], variant=expression)
            doc, _ = glb_data(Path(head["output"]))
            self.assertEqual([mesh["name"] for mesh in doc["meshes"]], ["head_mesh"])
            full = asset_export(self.target, output=f"full/{expression}.glb", variant=expression)
            doc, _ = glb_data(Path(full["output"]))
            self.assertEqual(len(doc["meshes"]), 2)
            self.assertEqual(self.context.model.read_bytes(), original)
        self.assertEqual(len(set(images)), 5)
        report = asset_export(self.target, output="engine/hero/hero_idle.glb", variant="default")
        doc, binary = glb_data(Path(report["output"]))
        self.assertEqual(len(doc["meshes"]), 2)
        self.assertEqual(doc["animations"][0]["name"], "idle")
        self.assertEqual(doc["images"][0]["mimeType"], "image/png")
        view = doc["bufferViews"][doc["images"][0]["bufferView"]]
        self.assertEqual(binary[view["byteOffset"]:view["byteOffset"]+view["byteLength"]], self.context.texture.read_bytes())
        self.validate(Path(report["output"]))
        self.assertEqual(self.context.model.read_bytes(), original)

    def test_head_only_export_preserves_uvs_and_animation(self):
        report = asset_export(self.target, output="chosen/custom/head.glb", include=["head"], variant="default")
        doc, binary = glb_data(Path(report["output"]))
        self.assertEqual([mesh["name"] for mesh in doc["meshes"]], ["head_mesh"])
        uv = accessor(doc, binary, doc["meshes"][0]["primitives"][0]["attributes"]["TEXCOORD_0"])
        self.assertTrue(all(0 <= value <= 1 for pair in uv for value in pair))
        self.assertGreater(len(set(uv)), 4)
        self.assertEqual(doc["animations"][0]["name"], "idle")
        self.validate(Path(report["output"]))
        before = Path(report["output"]).read_bytes()
        with self.assertRaises(FileExistsError):
            asset_export(self.target, output="chosen/custom/head.glb")
        self.assertEqual(Path(report["output"]).read_bytes(), before)

    def test_destination_constraints_and_unknown_selectors(self):
        for path in ("../outside.glb", str(self.root / "outside.glb"), "hero/model.bbmodel", "hero/texture.png"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                asset_export(self.target, output=path)
        with self.assertRaisesRegex(ValueError, "selector"):
            asset_export(self.target, output="unknown.glb", include=["not_present"])
        self.assertFalse((self.root / "assets/unknown.glb").exists())

    def test_assets_root_junction_cannot_escape_project(self):
        victim = self.root.parent / "victim"
        init_project(victim, asset_id="hero")
        hero = resolve_asset(f"{victim}#hero")
        ModelBuilder("hero").add_group("root").add_cube("body", "root", from_=(0,0,0), to_=(2,2,2)).export_bbmodel(hero.model)
        shutil.rmtree(victim / "assets")
        outside = self.root.parent / "outside"
        outside.mkdir()
        if os.name == "nt":
            run = subprocess.run(["cmd", "/c", "mklink", "/J", str(victim / "assets"), str(outside)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
        else:
            (victim / "assets").symlink_to(outside, target_is_directory=True)
        try:
            with self.assertRaises(ValueError):
                asset_export(victim, output="escape.glb")
            self.assertFalse((outside / "escape.glb").exists())
        finally:
            if os.name == "nt":
                (victim / "assets").rmdir()
            else:
                (victim / "assets").unlink()

    def test_target_configuration_exports_model_and_texture_products(self):
        config = self.context.scripts / "exports.json"
        config.write_text(json.dumps({"targets": [
            {"id": "idle", "output": "runtime/idle.glb", "format": "glb", "runtime_role": "default"},
            {"id": "head", "output": "parts/head.glb", "include": ["head"], "animations": []},
            {"id": "texture", "output": "logic/neutral.png", "texture_variant": "default"}]}))
        report = export_targets(self.target)
        self.assertEqual(len(report["targets"]), 3)
        self.assertEqual(report["targets"][0]["runtime_role"], "default")
        doc, _ = glb_data(self.root / "assets/parts/head.glb")
        self.assertNotIn("animations", doc)

    def test_config_rejects_multiple_defaults_and_duplicate_output_paths(self):
        config = self.context.scripts / "exports.json"
        targets = [{"id": "first", "output": "runtime/one.glb", "runtime_role": "default"},
                   {"id": "second", "output": "runtime/two.glb", "runtime_role": "default"}]
        config.write_text(json.dumps({"targets": targets}))
        with self.assertRaisesRegex(ValueError, "Only one export target"):
            export_targets(self.target)
        targets[1].pop("runtime_role")
        targets[1]["output"] = targets[0]["output"]
        config.write_text(json.dumps({"targets": targets}))
        with self.assertRaisesRegex(ValueError, "distinct destinations"):
            export_targets(self.target)
        self.assertFalse((self.root / "assets/runtime/one.glb").exists())

    def test_export_batch_prepares_all_products_before_publication(self):
        config = self.context.scripts / "exports.json"
        config.write_text(json.dumps({"targets": [
            {"id": "first", "output": "batch/first.glb"},
            {"id": "bad", "output": "batch/second.png", "include": ["head"]}]}))
        with self.assertRaisesRegex(ValueError, "PNG export"):
            export_targets(self.target)
        self.assertFalse((self.root / "assets/batch/first.glb").exists())
        config.write_text(json.dumps({"targets": [
            {"id": "first", "output": "batch/first.glb"},
            {"id": "second", "output": "batch/second.glb", "include": ["not_present"]}]}))
        with self.assertRaisesRegex(ValueError, "selector"):
            export_targets(self.target)
        self.assertFalse((self.root / "assets/batch/first.glb").exists())
        self.assertFalse((self.root / "assets/batch/second.glb").exists())

    def test_default_png_uses_current_bbmodel_texture_and_protects_link(self):
        image = self.context.directory / "manual.png"
        resolution = json.loads(self.context.model.read_bytes())["resolution"]
        Image.new("RGBA", (resolution["width"], resolution["height"]), "purple").save(image)
        doc = json.loads(self.context.model.read_bytes())
        doc["textures"][0].pop("source", None)
        doc["textures"][0]["relative_path"] = "manual.png"
        self.context.model.write_text(json.dumps(doc))
        report = asset_export(self.target, output="engine/current.png")
        self.assertEqual(Path(report["output"]).read_bytes(), image.read_bytes())
        with self.assertRaisesRegex(ValueError, "linked source texture"):
            asset_export(self.target, output="hero/manual.png", overwrite=True)

    def test_glb_preserves_native_two_atlas_materials_and_uv_dimensions(self):
        first, second = self.context.directory / "red.png", self.context.directory / "blue.png"
        Image.new("RGBA", (16,32), "red").save(first)
        Image.new("RGBA", (32,16), "blue").save(second)
        faces = {name: {"texture": None} for name in ("north", "south", "east", "west", "up", "down")}
        faces.update(north={"texture": 0, "uv": [0,0,8,16]}, south={"texture": 1, "uv": [0,0,16,8]})
        document = {"name": "two atlas", "resolution": {"width": 8, "height": 16},
                    "elements": [{"type": "cube", "uuid": "head-id", "name": "head", "from": [0,0,0], "to": [4,4,4], "faces": faces}],
                    "outliner": ["head-id"], "textures": [
                        {"relative_path": "red.png", "uv_width": 8, "uv_height": 16},
                        {"relative_path": "blue.png", "uv_width": 16, "uv_height": 8}]}
        self.context.model.write_text(json.dumps(document))
        original = self.context.model.read_bytes()
        report = asset_export(self.target, output="engine/multi.glb")
        doc, binary = glb_data(Path(report["output"]))
        self.assertEqual(len(doc["images"]), 2)
        self.assertEqual(len(doc["materials"]), 2)
        self.assertEqual([item["material"] for item in doc["meshes"][0]["primitives"]], [0,1])
        for index, image in enumerate((first, second)):
            view = doc["bufferViews"][doc["images"][index]["bufferView"]]
            self.assertEqual(binary[view["byteOffset"]:view["byteOffset"]+view["byteLength"]], image.read_bytes())
            uv = accessor(doc, binary, doc["meshes"][0]["primitives"][index]["attributes"]["TEXCOORD_0"])
            self.assertEqual({tuple(pair) for pair in uv}, {(0,0),(1,0),(0,1),(1,1)})
        self.validate(Path(report["output"]))
        with self.assertRaisesRegex(ValueError, "single-atlas"):
            asset_export(self.target, output="engine/bad.glb", variant="default")
        self.assertEqual(self.context.model.read_bytes(), original)

    def write_skinned_model(self):
        builder = ModelBuilder("rigged", require_integer_dimensions=False)
        rig = builder.add_armature("rig")
        builder.add_mesh("body", rig, quad_sphere(radius=2, subdivisions=1))
        mesh = builder.last
        rig.add_bone("base", between=((0,-2,0),(0,0,0)))
        rig.add_bone("tip", between=((0,0,0),(0,2,0)), parent="base")
        element = next(e for e in builder._elements if e.name == "body")
        rig.bind(mesh, weights={key: {"base": .5, "tip": .5} for key in element.vertices})
        builder.export_bbmodel(self.context.model)
        editor = AnimationEditor.from_bbmodel(self.context.model)
        editor.animation("bend", duration=1).bone("tip", armature="rig").key(0, rotation=(0,0,0)).key(1, rotation=(0,0,60))
        editor.save()

    def test_skinned_mesh_glb_has_inverse_bind_matrices_and_weights(self):
        self.write_skinned_model()
        report = asset_export(self.target, output="rigged.glb")
        doc, binary = glb_data(Path(report["output"]))
        self.assertEqual(len(doc["skins"][0]["joints"]), 2)
        attributes = doc["meshes"][0]["primitives"][0]["attributes"]
        weights = accessor(doc, binary, attributes["WEIGHTS_0"])
        self.assertTrue(all(math.isclose(sum(value), 1) for value in weights))
        self.assertEqual(weights[0], (.5,.5,0,0))
        self.validate(Path(report["output"]))


if __name__ == "__main__":
    unittest.main()
