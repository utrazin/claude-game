import unittest

from lib import ModelBuilder


class ArticulationValidationTests(unittest.TestCase):
    def test_identical_cross_section_fails(self):
        """Adjacent parent-child cubes with identical cross-section must be flagged."""
        b = ModelBuilder("test_limb")
        b.add_group("root")
        b.add_transform_group("arm_upper", parent="root", pivot=(0, 10, 0))
        b.add_transform_group("arm_lower", parent="arm_upper", pivot=(0, 5, 0))

        # Upper arm: 3x5x3 (x in [-1.5, 1.5], y in [5, 10], z in [-1.5, 1.5])
        b.add_cube("upper_cube", "arm_upper", from_=(-1.5, 5, -1.5), to_=(1.5, 10, 1.5))
        # Lower arm: identical 3x5x3 cross-section (x in [-1.5, 1.5], y in [0, 5], z in [-1.5, 1.5])
        b.add_cube("lower_cube", "arm_lower", from_=(-1.5, 0, -1.5), to_=(1.5, 5, 1.5))

        report = b.validate()
        self.assertTrue(
            any("Coplanar articulation conflict" in err and "identical cross-section" in err
                for err in report["errors"]),
            f"Expected coplanar articulation error, got: {report['errors']}"
        )

    def test_differentiated_cross_section_passes(self):
        """Adjacent parent-child cubes with stepped thickness must pass cleanly."""
        b = ModelBuilder("test_stepped")
        b.add_group("root")
        b.add_transform_group("arm_upper", parent="root", pivot=(0, 10, 0))
        b.add_transform_group("arm_lower", parent="arm_upper", pivot=(0, 5, 0))

        # Upper arm: 3x5x3
        b.add_cube("upper_cube", "arm_upper", from_=(-1.5, 5, -1.5), to_=(1.5, 10, 1.5))
        # Lower arm: stepped down to 2x5x2 (x in [-1, 1], z in [-1, 1])
        b.add_cube("lower_cube", "arm_lower", from_=(-1, 0, -1), to_=(1, 5, 1))

        report = b.validate()
        articulation_errors = [e for e in report["errors"] if "Coplanar articulation conflict" in e]
        self.assertEqual(articulation_errors, [])

    def test_multiple_objects_in_parent_ignores_non_contacting(self):
        """Non-contacting cubes in parent bone (e.g. shoulder pad) do not trigger false conflicts."""
        b = ModelBuilder("test_compound")
        b.add_group("root")
        b.add_transform_group("arm_upper", parent="root", pivot=(0, 10, 0))
        b.add_transform_group("arm_lower", parent="arm_upper", pivot=(0, 5, 0))

        # Shoulder pad high up on parent bone (y in [8, 11]), does NOT touch joint at y=5
        b.add_cube("shoulder_pad", "arm_upper", from_=(-2, 8, -2), to_=(2, 11, 2))
        # Upper arm base: 3x5x3, touches joint at y=5
        b.add_cube("upper_cube", "arm_upper", from_=(-1.5, 5, -1.5), to_=(1.5, 10, 1.5))
        # Lower arm: stepped down to 2x5x2
        b.add_cube("lower_cube", "arm_lower", from_=(-1, 0, -1), to_=(1, 5, 1))

        report = b.validate()
        articulation_errors = [e for e in report["errors"] if "Coplanar articulation conflict" in e]
        self.assertEqual(articulation_errors, [])

    def test_same_bone_siblings_do_not_trigger_articulation_check(self):
        """Two cubes in the same bone stacked together are not an articulated connection."""
        b = ModelBuilder("test_same_bone")
        b.add_group("root")
        # Stacked blocks inside the same bone (static composite geometry)
        b.add_cube("block_top", "root", from_=(-1, 2, -1), to_=(1, 4, 1))
        b.add_cube("block_bottom", "root", from_=(-1, 0, -1), to_=(1, 2, 1))

        report = b.validate()
        articulation_errors = [e for e in report["errors"] if "Coplanar articulation conflict" in e]
        self.assertEqual(articulation_errors, [])


if __name__ == "__main__":
    unittest.main()
