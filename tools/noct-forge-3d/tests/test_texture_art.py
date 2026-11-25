import json
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PIL import Image

from lib.model_builder import ModelBuilder
from Tools import art, forge
from Tools._resolve import resolve_asset
from Tools.gltf_export import GLBWriter
from Tools.project_manifest import load_project
from Tools.TexturePainter import TexturePainter
from Tools.uv_builder import UVBuilder

RED = (255, 0, 0, 255)
BLUE = (0, 0, 255, 255)


class ArtRequestTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.delivered = base / "artist"
        self.delivered.mkdir()
        self.project = base / "hero_project"
        self.model = self.project / "assets" / "hero" / "model.bbmodel"
        self.model.parent.mkdir(parents=True)
        (ModelBuilder("hero").add_group("root")
         .add_cube("body", "root", from_=(-4, 0, -2), to_=(4, 8, 2))
         .add_cube("arm_L", "root", from_=(4, 4, -1), to_=(6, 6, 1))
         .add_cube("arm_R", "root", from_=(-6, 4, -1), to_=(-4, 6, 1))
         .export_bbmodel(self.model))
        UVBuilder(self.model, start_size=(64, 64), uv_scale=2).save()
        self.manifest_project = {
            "schema": 1, "id": "hero_project",
            "assets": {"hero": {"name": "hero", "model": "assets/hero/model.bbmodel", "scripts": "scripts/hero"}},
        }
        self.write_project()
        self.requests = {
            "schema": 2, "source": str(self.delivered),
            "requests": {
                "emblem": {"asset": "hero", "description": "Red emblem, pixel art, transparent background.",
                           "pixels": [8, 8],
                           "guide": {"element": "arm_L", "side": "front", "points": {"center": [5, 5]}}},
                "grain": {"asset": "hero", "description": "Soft blue painted grain, seamless tile.",
                          "pixels": [8, 8], "file": "tiles/grain.png", "notes": "kept as is"},
            },
        }
        self.write_requests()

    def write_project(self):
        (self.project / "project.json").write_text(json.dumps(self.manifest_project))

    def write_requests(self):
        (self.project / "art.json").write_text(json.dumps(self.requests))

    def context(self):
        return resolve_asset(f"{self.project}#hero")

    def deliver(self, size=(8, 8)):
        Image.new("RGBA", size, RED).save(self.delivered / "emblem.png")
        (self.delivered / "tiles").mkdir(exist_ok=True)
        Image.new("RGBA", (8, 8), BLUE).save(self.delivered / "tiles" / "grain.png")

    def run_cli(self, *args):
        output = StringIO()
        with redirect_stdout(output):
            code = forge.main(["art", *args])
        return code, output.getvalue()

    def test_guide_renders_requested_size_mapping_and_points(self):
        code, output = self.run_cli("guide", str(self.project), "--asset", "hero")
        self.assertEqual(code, 0, output)
        data = json.loads((self.project / "art.json").read_text())
        guide = data["requests"]["emblem"]["guide"]
        self.assertEqual(guide["points_px"]["center"], [4.0, 4.0])
        self.assertIn("canvas x 0..8 = x 4.000..6.000", guide["mapping"])
        with Image.open(self.project / guide["image"]) as image:
            self.assertEqual(image.size, (8, 8))
        self.assertNotIn("guide", data["requests"]["grain"])
        self.assertEqual(data["requests"]["grain"]["notes"], "kept as is")

    def test_prompt_is_self_contained(self):
        self.run_cli("guide", str(self.project))
        code, output = self.run_cli("prompt", str(self.project), "--request", "emblem")
        self.assertEqual(code, 0)
        for text in ("Red emblem, pixel art", "exactly 8x8 px", str(self.delivered / "emblem.png"),
                     "Guide", "Point center: x=4.0, y=4.0"):
            self.assertIn(text, output)
        self.assertIn(str(self.delivered / "tiles" / "grain.png"), self.run_cli("prompt", str(self.project))[1])

    def test_pull_copies_only_delivered_files_of_the_requested_size(self):
        code, output = self.run_cli("pull", str(self.project))
        self.assertEqual(code, 0)
        self.assertIn("emblem: missing", output)
        self.assertEqual(self.run_cli("pull", str(self.project), "--check")[0], 1)
        self.deliver(size=(8, 4))
        code, output = self.run_cli("pull", str(self.project))
        self.assertEqual(code, 1)
        self.assertIn("emblem: wrong_size", output)
        self.assertFalse(art.deliver_path(self.context(), "emblem").exists())
        self.deliver()
        self.assertIn("emblem: copied", self.run_cli("pull", str(self.project))[1])
        code, output = self.run_cli("pull", str(self.project), "--check")
        self.assertEqual(code, 0)
        self.assertIn("grain: unchanged", output)

    def test_recipe_reads_delivered_images(self):
        painter = TexturePainter.from_bbmodel(self.model)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertIsNone(painter.art("emblem"))
        self.assertIn("not delivered yet", str(caught[0].message))
        with self.assertRaises(KeyError):
            painter.art("missing")
        self.deliver()
        self.run_cli("pull", str(self.project))
        path = painter.art("grain")
        self.assertEqual(path, self.project / "assets" / "hero" / "art" / "grain.png")
        painter.body.project_triplanar(Image.open(path), scale=1 / 4)
        self.assertEqual(painter.body.face("up").get_pixel(2, 2), BLUE)

    def test_validation(self):
        good = {"asset": "hero", "description": "x", "pixels": [4, 4]}
        cases = [
            (dict(good, asset="other"), "asset must be"),
            (dict(good, description=" "), "description"),
            (dict(good, pixels=[4]), "pixels"),
            (dict(good, pixels=[4, 0]), "pixels"),
            (dict(good, file="../x.png"), "relative .png"),
            (dict(good, guide={"side": "front"}), "guide needs an element"),
            (dict(good, guide={"element": "body", "points": {"a": [1]}}), "guide points"),
        ]
        for request, message in cases:
            self.requests["requests"] = {"bad": request}
            self.write_requests()
            with self.assertRaisesRegex(ValueError, message):
                art.load(self.project)
        self.requests["schema"] = 1
        self.requests["requests"] = {"ok": good}
        self.write_requests()
        with self.assertRaisesRegex(ValueError, "schema=2"):
            art.load(self.project)


class PlanarAndFilterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.model = self.root / "assets" / "hero" / "model.bbmodel"
        self.model.parent.mkdir(parents=True)
        (ModelBuilder("hero").add_group("root")
         .add_cube("left", "root", from_=(0, 0, 0), to_=(4, 4, 4))
         .add_cube("right", "root", from_=(4, 0, 0), to_=(8, 4, 4))
         .export_bbmodel(self.model))
        UVBuilder(self.model, start_size=(64, 64), uv_scale=1).save()

    def test_planar_tiling_is_continuous_across_elements(self):
        stripes = Image.new("RGBA", (8, 1), BLUE)
        stripes.paste(Image.new("RGBA", (4, 1), RED), (0, 0))
        painter = TexturePainter.from_bbmodel(self.model)
        for name in ("left", "right"):
            painter.element(name).project_planar(stripes, side="front", scale=1 / 8)
        # One repeat spans 8 units: red on x 0..4 (left cube), blue on x 4..8 (right cube).
        for name, color in (("left", RED), ("right", BLUE)):
            face = painter.element(name).face("south")
            self.assertEqual({face.get_pixel(x, y) for x in range(face.width) for y in range(face.height)}, {color})

    def test_texture_filter_is_validated_and_drives_glb_sampler(self):
        (self.root / "project.json").write_text(json.dumps({
            "schema": 1, "id": "p",
            "assets": {"hero": {"model": "assets/hero/model.bbmodel", "scripts": "scripts/hero",
                                "texture_filter": "linear"}}}))
        self.assertEqual(resolve_asset(f"{self.root}#hero").texture_filter, "linear")
        data = load_project(self.root)
        data["assets"]["hero"]["texture_filter"] = "cubic"
        (self.root / "project.json").write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "texture_filter"):
            load_project(self.root)
        with self.assertRaisesRegex(ValueError, "texture_filter"):
            GLBWriter({}, texture_filter="cubic")


if __name__ == "__main__":
    unittest.main()
