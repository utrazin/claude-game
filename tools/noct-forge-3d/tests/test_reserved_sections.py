import unittest

from lib import ModelBuilder, Path3D, PathSection, Profile, SegmentSection


def builder():
    b = ModelBuilder("t", require_integer_dimensions=False)
    b.add_group("root")
    return b


class ReservedSectionNameTests(unittest.TestCase):
    def test_a_section_may_reuse_base_and_top_where_the_shape_has_those_anchors(self):
        b = builder()
        b.add_segment("s", "root", start=(0, 0, 0), end=(0, 4, 0), y_hint=(0, 0, 1), sections=(
            SegmentSection("base", 0, Profile.circle(1, segments=4)),
            SegmentSection("top", 1, Profile.circle(1, segments=4))))
        self.assertEqual(b.validate()["errors"], [])

    def test_a_sweep_section_named_top_at_the_start_is_refused(self):
        b = builder()
        path = Path3D.polyline([(0, 0, 0), (0, 5, 0), (0, 10, 0)])
        with self.assertRaisesRegex(ValueError, "reserved"):
            b.add_sweep("s", "root", path=path, y_hint=(0, 0, 1), sections=(
                PathSection("top", Profile.circle(1), point=0),
                PathSection("end", Profile.circle(1), point=2)))

    def test_a_segment_section_named_end_in_the_middle_is_refused(self):
        b = builder()
        with self.assertRaisesRegex(ValueError, "reserved"):
            b.add_segment("s", "root", start=(0, 0, 0), end=(0, 4, 0), y_hint=(0, 0, 1), sections=(
                SegmentSection("a", 0, Profile.circle(1, segments=4)),
                SegmentSection("end", 0.5, Profile.circle(1, segments=4)),
                SegmentSection("b", 1, Profile.circle(1, segments=4))))

    def test_a_section_named_center_is_refused(self):
        b = builder()
        with self.assertRaisesRegex(ValueError, "reserved"):
            b.add_segment("s", "root", start=(0, 0, 0), end=(0, 4, 0), y_hint=(0, 0, 1), sections=(
                SegmentSection("a", 0, Profile.circle(1, segments=4)),
                SegmentSection("center", 0.25, Profile.circle(1, segments=4)),
                SegmentSection("b", 1, Profile.circle(1, segments=4))))


if __name__ == "__main__":
    unittest.main()
