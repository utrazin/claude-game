"""Tests for multi-texture UV rules, packing, painting, status, and exports."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from lib import ModelBuilder
from lib.primitives import quad_sphere
from Tools._resolve import resolve_asset
from Tools.asset_export import asset_export
from Tools.asset_init import init_project
from Tools.asset_status import asset_status
from Tools.TexturePainter import TexturePainter
from Tools.texture_export import texture_export
from Tools.texture_variant import register_variant
from Tools.uv_builder import UVBuilder


def _glb_doc(path: Path) -> dict:
    payload = path.read_bytes()
    magic, version, size = struct.unpack_from("<4sII", payload)
    assert (magic, version, size) == (b"glTF", 2, len(payload))
    length, kind = struct.unpack_from("<II", payload, 12)
    assert kind == 0x4E4F534A
    return json.loads(payload[20 : 20 + length])


class MultiTextureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "project"
        init_project(self.root, asset_id="hero")
        self.target = f"{self.root}#hero"
        self.context = resolve_asset(self.target)

        builder = ModelBuilder("hero").add_group("root")
        builder.add_box("head", "root", size=(4, 4, 4), at=(0, 8, 0), tags=["skin", "head_part"])
        builder.add_box("body", "root", size=(6, 8, 4), at=(0, 0, 0), tags=["armor"])
        builder.add_cylinder("gem", "root", radius=2, height=2, segments=6, tags=["magic"], no_overlap_check=True)
        builder.export_bbmodel(self.context.model)

    def test_same_cube_different_faces_and_multi_object_packing(self):
        uv = UVBuilder(self.context.model, uv_scale=2, island_padding=1, require_integer_uvs=False)
        uv.clear()
        uv.rule(layout="box", texture="body")
        uv.rule(element="head", face="north", density=4, texture="face")
        uv.rule(element="gem", layout="charts", density=2, texture="magic")
        uv.save()

        data = json.loads(self.context.model.read_text(encoding="utf-8"))
        packing = data["unhandled_root_fields"]["model_as_code"]["uv_packing"]
        textures = packing.get("textures")
        self.assertIsNotNone(textures)
        self.assertEqual([t["name"] for t in textures], ["body", "face", "magic"])

        elems = {e["name"]: e for e in data["elements"]}
        self.assertEqual(elems["head"]["faces"]["north"]["texture"], 1)
        for side in ("south", "east", "west", "up", "down"):
            self.assertEqual(elems["head"]["faces"][side]["texture"], 0)
        for face in elems["body"]["faces"].values():
            self.assertEqual(face["texture"], 0)
        for face in elems["gem"]["faces"].values():
            self.assertEqual(face["texture"], 2)

        # Face slot only holds head.north (4*4 = 16x16 px + padding -> 32x32 or 16x16 POT)
        face_slot = textures[1]
        body_slot = textures[0]
        self.assertNotEqual((face_slot["width"], face_slot["height"]), (body_slot["width"], body_slot["height"]))

    def test_pins_and_sharing_isolated_per_texture_slot(self):
        # Two faces pinned at (0, 0) on different texture slots do NOT collide
        uv = UVBuilder(self.context.model, uv_scale=1, island_padding=0)
        uv.clear()
        uv.rule(element="head", face="north", layout="fixed", size=(4, 4), pin=(0, 0), texture="face")
        uv.rule(element="body", face="north", layout="fixed", size=(4, 4), pin=(0, 0), texture="body")
        uv.save()

        # Cross-slot UV sharing is rejected
        uv2 = UVBuilder(self.context.model, uv_scale=1, island_padding=0)
        uv2.clear()
        uv2.rule(element="head", face="north", texture="face")
        uv2.rule(element="head", face="south", texture="body")
        uv2.share_uv(("head", "south"), source=("head", "north"))
        with self.assertRaisesRegex(ValueError, "share_uv faces need the same UV rules"):
            uv2.save()

    def test_painter_multi_slot_select_compose_and_save(self):
        uv = UVBuilder(self.context.model, uv_scale=1, island_padding=1, require_integer_uvs=False)
        uv.clear()
        uv.rule(element="head", face="north", density=2, texture="face")
        uv.rule(element="gem", layout="charts", texture="magic")
        uv.save()

        painter = TexturePainter(str(self.context.model))
        self.assertEqual([s["name"] for s in painter.parser.texture_slots], ["default", "face", "magic"])

        # Paint default slot via select(texture="default"), face slot directly, magic slot via tag+texture
        painter.select(texture="default").fill("#224466")
        painter.head.north.fill("#ffccaa")
        painter.select(tag="magic", texture="magic").fill("#ff00ff")

        # Verify head.south got #224466 while head.north kept #ffccaa
        self.assertEqual(painter.head.north.get_pixel(0, 0), (255, 204, 170, 255))
        self.assertEqual(painter.head.south.get_pixel(0, 0), (34, 68, 102, 255))

        saved_main = painter.save(str(self.context.texture))
        self.assertEqual(Path(saved_main), self.context.texture.resolve())
        face_png = self.context.texture.with_name("texture_face.png")
        magic_png = self.context.texture.with_name("texture_magic.png")
        self.assertTrue(self.context.texture.is_file())
        self.assertTrue(face_png.is_file())
        self.assertTrue(magic_png.is_file())

        # Single-slot save also works without clobbering other slots
        painter.head.north.fill("#ee8866")
        saved_face = painter.save(str(self.context.texture), texture="face")
        self.assertEqual(Path(saved_face), face_png.resolve())

        data = json.loads(self.context.model.read_text(encoding="utf-8"))
        self.assertEqual(len(data["textures"]), 3)
        self.assertEqual(
            [t["name"] for t in data["textures"]],
            ["texture.png", "texture_face.png", "texture_magic.png"],
        )

    def test_end_to_end_pipeline_status_variants_and_exports(self):
        uv = UVBuilder(self.context.model, uv_scale=1, island_padding=1, require_integer_uvs=False)
        uv.clear()
        uv.rule(texture="body")
        uv.rule(element="head", face="north", density=2, texture="face")
        uv.save()

        (self.context.scripts / "generate_texture.py").write_text(
            "from Tools.recipe_context import recipe_paths\n"
            "from Tools.TexturePainter import TexturePainter\n"
            "paths = recipe_paths(__file__)\n"
            "painter = TexturePainter(str(paths.model))\n"
            "if paths.variant == 'angry':\n"
            "    painter.head.north.fill('#ff2222')\n"
            "    painter.save(str(paths.texture_for('face')), texture='face')\n"
            "else:\n"
            "    painter.select(texture='body').fill('#335577')\n"
            "    painter.select(texture='face').fill('#ffddbb')\n"
            "    painter.save(str(paths.texture))\n",
            encoding="utf-8",
        )

        res_default = texture_export(self.target)
        self.assertEqual(res_default["status"], "pass", res_default)
        self.assertIn("textures", res_default)
        self.assertEqual(set(res_default["textures"]), {"body", "face"})

        status = asset_status(self.target)
        self.assertTrue(status["all_pass"], status)
        self.assertEqual(set(status["texture"]["textures"]), {"body", "face"})

        # Register and run partial variant 'angry' (only overrides face slot)
        register_variant(self.target, "angry")
        res_angry = texture_export(self.target, variant="angry")
        self.assertEqual(res_angry["status"], "pass", res_angry)
        angry_face = self.root / "assets" / "hero" / "textures" / "angry_face.png"
        self.assertTrue(angry_face.is_file())

        # Export GLB and BBModel for both default and 'angry' variant
        glb_default = self.root / "assets" / "hero" / "export" / "hero.glb"
        glb_angry = self.root / "assets" / "hero" / "export" / "hero_angry.glb"
        bb_angry = self.root / "assets" / "hero" / "export" / "hero_angry.bbmodel"

        self.assertEqual(asset_export(self.target, output="hero/export/hero.glb")["status"], "pass")
        self.assertEqual(asset_export(self.target, output="hero/export/hero_angry.glb", variant="angry")["status"], "pass")
        self.assertEqual(asset_export(self.target, output="hero/export/hero_angry.bbmodel", variant="angry")["status"], "pass")

        doc_def = _glb_doc(glb_default)
        self.assertEqual(len(doc_def["materials"]), 2)
        self.assertEqual(len(doc_def["images"]), 2)

        doc_angry = _glb_doc(glb_angry)
        self.assertEqual(len(doc_angry["materials"]), 2)
        self.assertEqual([m["name"] for m in doc_angry["materials"]], ["texture_body.png", "angry_face.png"])

        bb_doc = json.loads(bb_angry.read_text(encoding="utf-8"))
        self.assertEqual([t["name"] for t in bb_doc["textures"]], ["texture_body.png", "angry_face.png"])


if __name__ == "__main__":
    unittest.main()
