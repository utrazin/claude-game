import tempfile
import unittest
from pathlib import Path
from PIL import Image

from lib.model_builder import ModelBuilder
from Tools.capture_preview import capture_views, create_side_by_side_comparison, create_turnaround_sheet


class CapturePreviewTests(unittest.TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parents[1]
        self.temp_dir = tempfile.TemporaryDirectory(dir=repo_root)
        self.addCleanup(self.temp_dir.cleanup)
        self.temp_path = Path(self.temp_dir.name)

        self.model_path = self.temp_path / "model.bbmodel"
        self.renders_dir = self.temp_path / "renders"

        # Build a small cube model
        (
            ModelBuilder("test_cube")
            .add_group("base")
            .add_cube("body", "base", from_=(0, 0, 0), to_=(6, 8, 4))
            .export_bbmodel(self.model_path)
        )

        # Create dummy reference image
        self.ref_path = self.temp_path / "ref.png"
        ref_img = Image.new("RGBA", (200, 300), (100, 150, 200, 255))
        ref_img.save(self.ref_path)

    def test_side_by_side_generator(self):
        render_img = self.temp_path / "render.png"
        Image.new("RGBA", (400, 400), (50, 50, 50, 255)).save(render_img)

        comp_out = self.temp_path / "comp.png"
        create_side_by_side_comparison(self.ref_path, render_img, comp_out)
        self.assertTrue(comp_out.exists())

        with Image.open(comp_out) as img:
            self.assertEqual(img.height, 400 + 36)
            self.assertGreater(img.width, 400)

    def test_turnaround_sheet_generator(self):
        views = {}
        for v in ("front", "right", "back", "iso"):
            p = self.temp_path / f"{v}.png"
            Image.new("RGBA", (200, 200), (30, 30, 30, 255)).save(p)
            views[v] = p

        sheet_out = self.temp_path / "turnaround.png"
        create_turnaround_sheet(views, sheet_out, asset_name="test_cube")
        self.assertTrue(sheet_out.exists())

        with Image.open(sheet_out) as img:
            self.assertEqual(img.width, 400)
            self.assertEqual(img.height, 44 + 400 + 24)

    def test_unlit_capture_differs_from_lit(self):
        import numpy as np
        lit = capture_views(self.model_path, self.renders_dir / "lit", views=["iso"], resolution=(200, 200))
        flat = capture_views(self.model_path, self.renders_dir / "flat", views=["iso"], resolution=(200, 200),
                             shading=False)
        with Image.open(lit["iso"]) as a, Image.open(flat["iso"]) as b:
            self.assertGreater(np.abs(np.asarray(a.convert("RGB"), float) - np.asarray(b.convert("RGB"), float)).max(), 0)

    def test_orbit_views_keep_their_numbers_in_a_view_list(self):
        from Tools.capture_preview import parse_views
        self.assertEqual(parse_views("front,orbit:30,15,side,orbit:-40,10,ortho,iso"),
                         ["front", "orbit:30,15", "right", "orbit:-40,10,ortho", "iso"])

    def test_an_ortho_orbit_differs_from_a_perspective_one(self):
        import numpy as np
        shots = {cam: capture_views(self.model_path, self.renders_dir / cam, views=[f"orbit:30,15,{cam}"],
                                    resolution=(200, 200))["orbit_30_15_" + cam] for cam in ("ortho", "persp")}
        with Image.open(shots["ortho"]) as a, Image.open(shots["persp"]) as b:
            self.assertGreater(np.abs(np.asarray(a.convert("RGB"), float) - np.asarray(b.convert("RGB"), float)).max(), 0)

    def test_png_out_names_the_file_when_one_image_is_produced(self):
        from Tools.capture_preview import main
        target = self.temp_path / "named" / "shot.png"
        main([str(self.model_path), "--view", "front", "--resolution", "200x200", "--out", str(target)])
        self.assertTrue(target.is_file())
        self.assertEqual([p.name for p in target.parent.glob("*.png")], ["shot.png"])

    def test_headless_capture_views(self):
        results = capture_views(
            self.model_path,
            self.renders_dir,
            views=["front", "iso", "orbit:30,15"],
            wireframe=True,
            transparent=True,
            ref_scale=0.9,
            ref_offset=(0.0, 1.0, 0.0),
            resolution=(400, 400),
            turnaround=True,
            reference_path=self.ref_path,
            side_by_side=True,
        )

        self.assertIn("front", results)
        self.assertIn("iso", results)
        self.assertIn("orbit_30_15", results)
        self.assertIn("turnaround_sheet", results)
        self.assertIn("comparison_front", results)

        for key, path_str in results.items():
            path = Path(path_str)
            self.assertTrue(path.exists(), f"Captured file {path} should exist")
            self.assertGreater(path.stat().st_size, 500)

    def test_cubes_with_pending_uvs_are_drawn(self):
        results = capture_views(self.model_path, self.renders_dir, views=["front"], transparent=True,
                                resolution=(200, 200))
        image = Image.open(results["front"]).convert("RGBA")
        opaque = sum(1 for alpha in image.getchannel("A").tobytes() if alpha > 200)
        self.assertGreater(opaque, 2000, "the cube should cover a good part of the frame")

    def test_a_clip_can_be_rendered_at_a_moment_and_an_unknown_clip_is_an_error(self):
        from lib import AnimationEditor
        model = (ModelBuilder("swinger", modeling_mode="box")
                 .add_group("root")
                 .add_transform_group("arm", "root", pivot=(0, 8, 0))
                 .add_box("arm_box", "arm", size=(2, 6, 2), at=(0, 8, 0), anchor="top")
                 .export_bbmodel(self.temp_path / "swing.bbmodel"))
        editor = AnimationEditor.from_bbmodel(model)
        editor.animation("swing", duration=1.0).group("arm").key(0, rotation=(0, 0, 0)).key(1, rotation=(0, 0, 80))
        editor.save()
        results = capture_views(model, self.renders_dir, views=["front"], clip="swing", times=[0.0, 1.0],
                                resolution=(200, 200))
        self.assertEqual(sorted(results), ["front_swing_t0", "front_swing_t1"])
        first, last = (Image.open(results[k]).convert("RGB").tobytes() for k in sorted(results))
        self.assertNotEqual(first, last, "the pose at 1s must differ from the pose at 0s")
        with self.assertRaisesRegex(ValueError, "unknown clip 'nope'.*swing"):
            capture_views(model, self.renders_dir, views=["front"], clip="nope", resolution=(200, 200))
        with self.assertRaisesRegex(ValueError, "outside clip 'swing'"):
            capture_views(model, self.renders_dir, views=["front"], clip="swing", times=[5.0], resolution=(200, 200))


if __name__ == "__main__":
    unittest.main()
