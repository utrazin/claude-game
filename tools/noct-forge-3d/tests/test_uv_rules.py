"""UV rules (Tools.uv_rules): per-region density and layout, flat / fixed islands, pins, packers, UV recipes."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lib import ModelBuilder
from Tools.TexturePainter import TexturePainter
from Tools.uv_builder import UVBuilder
from Tools.uv_packer import BoxUVPacker


def boxes(data):
    """(element, face) -> UV bounds (u0, v0, u1, v1)."""
    out = {}
    for elem in data["elements"]:
        for name, face in elem["faces"].items():
            uv = face["uv"]
            points = list(uv.values()) if isinstance(uv, dict) else [uv[:2], uv[2:]]
            us, vs = [p[0] for p in points], [p[1] for p in points]
            out[elem["name"], name] = (min(us), min(vs), max(us), max(vs))
    return out


class UVRuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "model.bbmodel"
        b = ModelBuilder("doll").add_group("root").add_group("body", "root").add_group("top", "root")
        b.add_cube("torso", "body", from_=(-2, 0, -1), to_=(2, 6, 1), tags=["flat"])
        b.add_cube("leg", "body", from_=(0, -4, -1), to_=(2, 0, 1), tags=["flat"])
        b.add_cube("head", "top", from_=(-2, 6, -2), to_=(2, 10, 2))
        b.add_cylinder("hat", "top", radius=2, height=2, segments=8, no_overlap_check=True)
        b.export_bbmodel(self.path)

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def builder(self, **options):
        options = dict(dict(uv_scale=2, island_padding=1, require_integer_uvs=False), **options)
        return UVBuilder(self.path, **options).clear()

    def test_without_rules_packing_is_the_automatic_one(self):
        source = self.read()
        source["unhandled_root_fields"]["model_as_code"]["uv_sharing"] = []       # what UVBuilder declares
        UVBuilder(self.path, uv_scale=2, island_padding=1, require_integer_uvs=False).save()
        expected = BoxUVPacker.pack_document(source, uv_scale=2, island_padding=1, require_integer_uvs=False)[0]
        self.assertEqual(self.read(), expected)
        self.assertNotIn("rules", self.read()["unhandled_root_fields"]["model_as_code"]["uv_packing"])

    def test_flat_element_shares_one_texel_and_paints_one_colour(self):
        self.builder().rule(tag="flat", layout="flat").save()
        data = self.read()
        found = boxes(data)
        torso = {found["torso", face] for face in ("north", "south", "east", "west", "up", "down")}
        self.assertEqual(len(torso), 1)
        u0, v0, u1, v1 = torso.pop()
        self.assertEqual((u1 - u0, v1 - v0), (1, 1))
        self.assertNotEqual(found["torso", "north"], found["leg", "north"])      # per element by default
        links = data["unhandled_root_fields"]["model_as_code"]["uv_sharing"]
        self.assertEqual(len(links), 10)
        self.assertTrue(all(link["region"] for link in links))
        painter = TexturePainter(self.path)
        painter.element("torso").fill_all("#ff0000")
        painter.select(tag="flat").fill("#ff0000")
        self.assertEqual(painter.compose_atlas().getpixel((int(u0), int(v0))), (255, 0, 0, 255))
        # spatial painting skips the faces of a flat region (their owner shows for them)
        self.assertGreater(len(painter.surface().position), 0)

    def test_flat_per_rule_joins_elements(self):
        self.builder().rule(tag="flat", layout="flat", per="rule").save()
        found = boxes(self.read())
        self.assertEqual(found["torso", "north"], found["leg", "up"])

    def test_density_fixed_and_pin(self):
        self.builder().rule(element="head", density=4).rule(
            element="head", face="north", layout="fixed", size=(32, 32), pin=(1, 1)).save()
        found = boxes(self.read())
        self.assertEqual(found["head", "north"], (1, 1, 33, 33))
        u0, v0, u1, v1 = found["head", "south"]
        self.assertEqual((u1 - u0, v1 - v0), (16, 16))                       # 4 units at 4 px/unit
        u0, v0, u1, v1 = found["torso", "north"]
        self.assertEqual((u1 - u0, v1 - v0), (8, 12))                        # default 2 px/unit
        painter = TexturePainter(self.path)
        self.assertEqual(painter.texel_density([("head", "south", 1)]), 4.0)
        self.assertEqual(painter.texel_density([("torso", "north", 1)]), 2.0)

    def test_charts_take_their_rule_density(self):
        self.builder(layout="charts").rule(element="hat", density=6).save()
        data = self.read()
        hat = next(e for e in data["elements"] if e["name"] == "hat")
        self.assertTrue(all(face.get("model_as_code_chart") for face in hat["faces"].values()))
        default = BoxUVPacker.pack_document(self.read(), uv_scale=2)[0]
        self.assertEqual(default["unhandled_root_fields"]["model_as_code"]["uv_packing"]["rules"],
                         [{"select": {"element": "hat"}, "density": 6}])

    def test_rules_are_remembered_by_the_model(self):
        self.builder(packer="shelf").rule(tag="flat", layout="flat").rule(element="head", density=3).save()
        before = self.read()
        BoxUVPacker.apply_to_bbmodel(self.path, backup=False)
        self.assertEqual(self.read(), before)
        self.assertEqual(before["unhandled_root_fields"]["model_as_code"]["uv_packing"]["packer"], "shelf")
        # a new recipe starting with clear() replaces the plan
        UVBuilder(self.path).clear().save()
        self.assertNotIn("rules", self.read()["unhandled_root_fields"]["model_as_code"]["uv_packing"])
        self.assertEqual(self.read()["unhandled_root_fields"]["model_as_code"]["uv_sharing"], [])

    def test_packers_place_without_overlap(self):
        for packer in ("maxrects", "shelf", "grouped"):
            self.builder(packer=packer).rule(tag="flat", layout="flat").rule(element="head", density=4).save()
            TexturePainter(self.path)                                       # validates ownership and overlaps

    def test_grouped_keeps_each_block_together(self):
        self.builder(packer="grouped").rule(element="head", block="face").rule(element="hat", block="face").save()
        found = boxes(self.read())
        face = [box for (name, _), box in found.items() if name in ("head", "hat")]
        rest = [box for (name, _), box in found.items() if name not in ("head", "hat")]
        area = (min(b[0] for b in face), min(b[1] for b in face), max(b[2] for b in face), max(b[3] for b in face))
        for u0, v0, u1, v1 in rest:
            self.assertFalse(u0 < area[2] and area[0] < u1 and v0 < area[3] and area[1] < v1)

    def test_invalid_rules_write_nothing(self):
        before = self.path.read_bytes()
        cases = [dict(colour="red", density=2), dict(element="nobody", density=2),
                 dict(element="hat", layout="box"), dict(element="torso", layout="charts"),
                 dict(element="head", layout="fixed"), dict(element="head", density=0)]
        for case in cases:
            with self.assertRaises(ValueError, msg=str(case)):
                self.builder().rule(**case).save()
        with self.assertRaisesRegex(ValueError, "pinned islands overlap"):
            self.builder().rule(element="head", face="north", layout="fixed", size=(8, 8), pin=(2, 2)).rule(
                element="head", face="south", layout="fixed", size=(8, 8), pin=(4, 4)).save()
        with self.assertRaisesRegex(ValueError, "share_uv needs"):
            self.builder().rule(tag="flat", layout="flat").share_uv(("torso", "north"), source=("torso", "south")).save()
        self.assertEqual(self.path.read_bytes(), before)


class UVRecipeStageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        self.project = Path(self.temp.name) / "proj"
        init_project(self.project, asset_id="uv")
        context = resolve_asset(f"{self.project}#uv")
        self.model, self.recipe = context.model, context.scripts / "generate_uv.py"
        (ModelBuilder("test").add_group("root").add_cube("body", "root", from_=(0, 0, 0), to_=(2, 3, 4))
         .add_cube("arm", "root", from_=(3, 0, 0), to_=(4, 3, 1)).export_bbmodel(self.model))
        self.recipe.parent.mkdir(parents=True, exist_ok=True)
        self.recipe.write_text(
            "from Tools.recipe_context import recipe_paths\n"
            "from Tools.uv_builder import UVBuilder\n"
            "UVBuilder(recipe_paths(__file__).model, uv_scale=2, island_padding=1).clear()"
            ".rule(element='arm', layout='flat').save(verbose=True)\n", encoding="utf-8")
        self.root = Path(__file__).resolve().parents[1]

    def forge(self, *args):
        return subprocess.run([sys.executable, "-B", "-m", "Tools.forge", "uv", str(self.project), "--asset", "uv",
                               *args], cwd=self.root, capture_output=True, text=True)

    def test_forge_uv_runs_the_recipe(self):
        before = self.model.read_bytes()
        dry = self.forge("--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("DRY-RUN", dry.stdout)
        self.assertEqual(self.model.read_bytes(), before)
        run = self.forge()
        self.assertEqual(run.returncode, 0, run.stderr)
        data = json.loads(self.model.read_text(encoding="utf-8"))
        self.assertEqual(data["unhandled_root_fields"]["model_as_code"]["uv_packing"]["rules"][0]["layout"], "flat")
        refused = self.forge("--uv-scale", "4")
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("--no-recipe", refused.stderr)
        plain = self.forge("--no-recipe", "--uv-scale", "4")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        data = json.loads(self.model.read_text(encoding="utf-8"))
        self.assertEqual(data["unhandled_root_fields"]["model_as_code"]["uv_packing"]["uv_scale"], 4)

    def test_asset_build_uv_stage_runs_the_recipe(self):
        from Tools.asset_build import asset_build
        report = asset_build(f"{self.project}#uv", stages="uv")
        self.assertEqual(report["status"], "pass", report)
        data = json.loads(self.model.read_text(encoding="utf-8"))
        self.assertIn("rules", data["unhandled_root_fields"]["model_as_code"]["uv_packing"])


if __name__ == "__main__":
    unittest.main()
