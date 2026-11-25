import unittest

from lib import ModelBuilder


class StackOnRotationTests(unittest.TestCase):
    def test_a_rotated_cube_rests_on_its_lowest_corner(self):
        b = ModelBuilder("t", require_integer_dimensions=False)
        b.add_group("root")
        b.add_cube("floor", "root", from_=(-5, 0, -5), to_=(5, 2, 5))
        b.add_cube("tilted", "root", from_=(-1, 0, -1), to_=(1, 2, 1), origin=(0, 1, 0), rotation=(0, 0, 45))
        b.stack_on("tilted", "floor", axis="+Y")
        element = next(e for e in b._elements if e.name == "tilted")
        corners = [(x, y, z) for x in (element.from_[0], element.to_[0]) for y in (element.from_[1], element.to_[1])
                   for z in (element.from_[2], element.to_[2])]
        lowest = min(b._rotate_about(c, element.origin, element.rotation)[1] for c in corners)
        self.assertAlmostEqual(lowest, 2.0, places=6)

    def test_unrotated_stacking_is_unchanged(self):
        b = ModelBuilder("t", require_integer_dimensions=False)
        b.add_group("root")
        b.add_cube("floor", "root", from_=(-5, 0, -5), to_=(5, 2, 5))
        b.add_cube("box", "root", from_=(-1, 0, -1), to_=(1, 2, 1))
        b.stack_on("box", "floor", axis="+Y")
        element = next(e for e in b._elements if e.name == "box")
        self.assertAlmostEqual(element.from_[1], 2.0, places=6)


if __name__ == "__main__":
    unittest.main()
