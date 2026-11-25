import unittest

from lib import Frame, Profile, Section
from lib.procedural import loft


class ConcaveCapTests(unittest.TestCase):
    def test_an_even_concave_outline_gets_a_message_that_names_the_cause(self):
        l_shape = Profile.polygon(((0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)))
        with self.assertRaisesRegex(ValueError, "concave profile.*start_cap='open'"):
            loft([Section("a", l_shape), Section("b", l_shape, Frame(origin=(0, 0, 3)))])

    def test_the_same_outline_with_open_caps_builds(self):
        l_shape = Profile.polygon(((0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)))
        draft = loft([Section("a", l_shape), Section("b", l_shape, Frame(origin=(0, 0, 3)))],
                     start_cap="open", end_cap="open")
        self.assertEqual(draft.validate()["errors"], [])

    def test_convex_outlines_are_untouched(self):
        loft([Section("a", Profile.circle(1)), Section("b", Profile.circle(1), Frame(origin=(0, 0, 3)))])

    def test_path_section_accepts_distance_as_at(self):
        from lib import PathSection
        self.assertEqual(PathSection("k", Profile.circle(1), distance=2.5).at, 2.5)
        with self.assertRaises(ValueError):
            PathSection("k", Profile.circle(1), at=1, distance=2)


if __name__ == "__main__":
    unittest.main()
