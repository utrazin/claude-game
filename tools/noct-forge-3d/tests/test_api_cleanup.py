import inspect
import unittest

from lib import ModelBuilder, MeshDraft, Profile, SegmentSection
from Tools.model_export import main as export_main


class ApiCleanupTests(unittest.TestCase):
    def test_duplicates_are_gone_and_the_survivors_do_the_work(self):
        self.assertFalse(hasattr(ModelBuilder, "add_free_box"))
        self.assertFalse(hasattr(ModelBuilder, "add_rigid_chain"))
        self.assertFalse(hasattr(ModelBuilder, "mirror_element"))
        self.assertFalse(hasattr(ModelBuilder, "mirror_group"))
        self.assertNotIn("quads", inspect.signature(MeshDraft.connect_rings).parameters)
        b = ModelBuilder("t", require_integer_dimensions=False)
        b.add_group("root")
        b.add_box("mesh_box", "root", size=(2, 2, 2), at=(0, 1, 0), anchor="base", native=False)
        self.assertEqual(b.validate()["errors"], [])
        chain = b.add_transform_chain("tail", "root", start=(0, 0, 0),
                                      segments=[{"name": "s1", "length": 2, "direction": (0, 0, -1)}])
        self.assertTrue(chain)

    def test_rig_mirror_accepts_new_name(self):
        b = ModelBuilder("t", require_integer_dimensions=False)
        rig = b.add_armature("rig")
        b.add_segment("torso", "rig", start=(0, 0, 0), end=(0, 4, 0), y_hint=(0, 0, 1),
                      sections=[SegmentSection("a", 0, Profile.circle(1, segments=4)),
                                SegmentSection("b", 1, Profile.circle(1, segments=4))])
        rig.add_bone("root", between=((0, 0, 0), (0, 4, 0)))
        rig.add_bone("arm_L", between=((1, 3, 0), (3, 3, 0)), parent="root", connected=False)
        rig.mirror("arm_L", new_name="arm_R")
        self.assertIn("arm_R", b._armature_bones)

    def test_lint_without_strict_is_an_error_instead_of_a_silent_no_op(self):
        with self.assertRaises(SystemExit) as caught:
            export_main(["projects/none", "--lint"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
