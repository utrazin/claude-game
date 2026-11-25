import unittest

from lib import ModelBuilder


def builder():
    b = ModelBuilder("t", require_integer_dimensions=False)
    b.add_group("root")
    return b


class SignatureDefaultTests(unittest.TestCase):
    def test_add_axis_quad_defaults_to_a_front_facing_quad(self):
        b = builder()
        b.add_axis_quad("badge", "root", from_=(0, 0, 0), size=(2, 2))
        self.assertEqual(next(e for e in b._elements if e.name == "badge").normal, "+Z")

    def test_add_revolve_takes_an_angle_like_revolve_does(self):
        full = builder()
        full.add_revolve("vase", "root", meridian=((0.6, 0), (1.2, 1.5), (0.4, 3)), segments=8)
        half = builder()
        half.add_revolve("vase", "root", meridian=((0.6, 0), (1.2, 1.5), (0.4, 3)), segments=8, angle=180,
                        start_cap="open", end_cap="open")
        spread = lambda b: [v[2] for v in next(e for e in b._elements if e.name == "vase").vertices.values()]
        self.assertLess(min(spread(full)), -1)              # a full turn surrounds the axis
        self.assertGreaterEqual(min(spread(half)), -1e-6)   # half a turn stays on one side
        with self.assertRaisesRegex(ValueError, "Angle"):
            builder().add_revolve("v", "root", meridian=((1, 0), (1, 1)), angle=400, start_cap="open", end_cap="open")


if __name__ == "__main__":
    unittest.main()
