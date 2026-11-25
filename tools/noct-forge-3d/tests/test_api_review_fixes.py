import json
import tempfile
import unittest
from pathlib import Path

from lib import ModelBuilder
from Tools.TexturePainter import TexturePainter


class ExplicitPointsTests(unittest.TestCase):
    def test_quad_face_and_triangle_stay_where_their_points_are(self):
        b = ModelBuilder("t", require_integer_dimensions=False, check_coplanar=False)
        b.add_group("root")
        b.add_quad_face("qf", "root", [(10, 5, 5), (12, 5, 5), (12, 7, 5), (10, 7, 5)])
        b.add_triangle("tr", "root", [(20, 0, 0), (22, 0, 0), (20, 2, 0)])
        world = {}
        for e in b.to_bbmodel_data()["elements"]:
            world[e["name"]] = sorted(tuple(round(v[i] + e["origin"][i], 3) for i in range(3))
                                      for v in e["vertices"].values())
        self.assertEqual(world["qf"], [(10, 5, 5), (10, 7, 5), (12, 5, 5), (12, 7, 5)])
        self.assertEqual(world["tr"], [(20, 0, 0), (20, 2, 0), (22, 0, 0)])


class PatchSideTests(unittest.TestCase):
    def test_patch_north_paints_the_north_face(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = ModelBuilder("c").add_group("root").add_cube(
                "crate", "root", from_=(0, 0, 0), to_=(4, 4, 4)).export_bbmodel(Path(tmp) / "model.bbmodel", auto_uv=True)
            painter = TexturePainter.from_bbmodel(str(model))
            crate = painter.element("crate")
            crate.patch("north", (0.5, 0.5), (1.0, 1.0)).fill((255, 0, 0, 255))
            def red(name):
                face = crate.faces[name]
                return sum(1 for x in range(face.width) for y in range(face.height)
                           if tuple(face.get_pixel(x, y))[:3] == (255, 0, 0))
            self.assertGreater(red("north"), 0)
            self.assertEqual(red("south"), 0)


class NoiseDeterminismTests(unittest.TestCase):
    def test_noise_without_a_seed_is_reproducible(self):
        from Tools.TexturePainter import DecalCanvas

        def render():
            painter = DecalCanvas(16, 16)
            painter.fill((100, 100, 100, 255)).apply_noise(10)
            return painter.compose().tobytes()
        self.assertEqual(render(), render())

    def test_a_different_seed_gives_a_different_pattern(self):
        from Tools.TexturePainter import DecalCanvas
        first, second = DecalCanvas(16, 16), DecalCanvas(16, 16)
        first.fill((100, 100, 100, 255)).apply_noise(10, seed=1)
        second.fill((100, 100, 100, 255)).apply_noise(10, seed=2)
        self.assertNotEqual(first.compose().tobytes(), second.compose().tobytes())


class BoneSocketMirrorTests(unittest.TestCase):
    def test_a_socket_on_a_mirrored_bone_is_mirrored_with_it(self):
        from lib import Path3D, PathSection, Profile, SegmentSection
        b = ModelBuilder("arm", require_integer_dimensions=False)
        rig = b.add_armature("rig")
        b.add_segment("torso", "rig", start=(0, 10, 0), end=(0, 20, 0), y_hint=(0, 0, 1),
                      sections=[SegmentSection("t0", 0, Profile.oval(3, 2, 2, segments=8)),
                                SegmentSection("t1", 1, Profile.oval(3, 2, 2, segments=8))])
        b.add_sweep("arm_L", "rig", path=Path3D.polyline([(3, 19, 0), (8, 19, 0), (13, 19, 0)]), y_hint=(0, 0, 1),
                    sections=[PathSection("sh", Profile.circle(1.2), point=0),
                              PathSection("wr", Profile.circle(0.8), point=2)])
        rig.add_bone("spine", between=("torso:t0", "torso:t1"))
        rig.add_bone("upper_L", between=("arm_L:sh", "arm_L:wr"), parent="spine", connected=False)
        b.add_socket("hand_L", "bone:upper_L", at="arm_L:wr")
        rig.mirror("upper_L")
        left, right = b.get_socket("hand_L"), b.get_socket("hand_R")
        for got, want in zip(right.origin, (-left.origin[0], left.origin[1], left.origin[2])):
            self.assertAlmostEqual(got, want, places=6)
        self.assertAlmostEqual(right.forward[0], -left.forward[0], places=6)


class TypoGuardTests(unittest.TestCase):
    def test_an_unknown_tag_and_an_unknown_view_are_errors(self):
        from Tools.capture_preview import capture_views
        with tempfile.TemporaryDirectory() as tmp:
            model = ModelBuilder("c").add_group("root").add_cube(
                "crate", "root", from_=(0, 0, 0), to_=(4, 4, 4), tags=["material:wood"]).export_bbmodel(
                    Path(tmp) / "model.bbmodel", auto_uv=True)
            painter = TexturePainter.from_bbmodel(str(model))
            self.assertEqual(len(painter.select(tag="material:wood")), 1)
            with self.assertRaisesRegex(ValueError, "No element or group carries the tag 'material:wod'"):
                painter.select(tag="material:wod")
            with self.assertRaisesRegex(ValueError, "Unknown view 'zzz'"):
                capture_views(model, Path(tmp) / "renders", views=["zzz"])


if __name__ == "__main__":
    unittest.main()
