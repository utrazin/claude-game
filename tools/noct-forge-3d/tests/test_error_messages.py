import unittest

from lib import ModelBuilder, Path3D, PathSection, Profile, SegmentSection
from lib.geometry_types import MeshDraft
from Tools.TexturePainter.core.color import parse_color


def builder():
    b = ModelBuilder("t", require_integer_dimensions=False)
    b.add_group("root")
    return b


class ErrorMessageTests(unittest.TestCase):
    def test_sweep_tables_explain_what_a_table_is(self):
        b = builder()
        path = Path3D.polyline([(0, 0, 0), (0, 5, 0)])
        with self.assertRaisesRegex(ValueError, r"scale must be a table"):
            b.add_sweep("s", "root", path=path, profile=Profile.circle(1), scale=0.5)
        with self.assertRaisesRegex(ValueError, r"scale entry .* is invalid"):
            b.add_sweep("s", "root", path=path, profile=Profile.circle(1), scale=((0, 1), (2, 0.5)))
        with self.assertRaisesRegex(ValueError, r"twist must start at t=0"):
            b.add_sweep("s", "root", path=path, profile=Profile.circle(1), twist=((0.5, 0), (1, 0)))

    def test_a_second_cap_with_the_default_name_says_to_rename_it(self):
        draft = MeshDraft(closed=True)
        first = draft.ring("a", 1, 4)
        second = draft.ring("b", 1, 4, offset=2)
        draft.cap(first)
        with self.assertRaisesRegex(ValueError, "pass a different name="):
            draft.cap(second)

    def test_a_bad_meridian_and_a_zero_length_path_say_what_is_wrong(self):
        b = builder()
        with self.assertRaisesRegex(ValueError, "at least two"):
            b.add_revolve("v", "root", meridian=((1, 0),), segments=8)
        with self.assertRaisesRegex(ValueError, "zero-length"):
            Path3D.polyline([(0, 0, 0), (0, 0, 0), (0, 5, 0)])

    def test_colors_are_validated_with_english_messages(self):
        self.assertEqual(parse_color("#fa0"), (255, 170, 0, 255))
        self.assertEqual(parse_color((10, 20, 30)), (10, 20, 30, 255))
        with self.assertRaisesRegex(ValueError, "Invalid color 'red'"):
            parse_color("red")
        with self.assertRaisesRegex(ValueError, "outside 0-255"):
            parse_color((300, 0, 0))
        with self.assertRaisesRegex(ValueError, "0..1 floats"):
            parse_color((0.5, 1, 0.2))


if __name__ == "__main__":
    unittest.main()
