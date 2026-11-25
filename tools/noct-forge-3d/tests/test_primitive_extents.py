import unittest

from lib.primitives import capsule, uv_sphere


def bounds(geometry):
    points = list(geometry.vertices.values())
    return [(min(p[i] for p in points), max(p[i] for p in points)) for i in range(3)]


class PrimitiveExtentTests(unittest.TestCase):
    def test_a_capsule_is_as_tall_and_wide_as_requested(self):
        for rings in (1, 2, 3, 5):
            with self.subTest(rings=rings):
                x, y, z = bounds(capsule(radius=2, height=5, segments=8, rings=rings))
                self.assertAlmostEqual(y[1] - y[0], 5, places=6)
                self.assertAlmostEqual(x[1] - x[0], 4, places=6)
                self.assertAlmostEqual(z[1] - z[0], 4, places=6)

    def test_a_capsule_without_a_body_is_a_sphere_of_the_requested_size(self):
        x, y, z = bounds(capsule(radius=2, height=4, segments=8, rings=2))
        self.assertAlmostEqual(y[1] - y[0], 4, places=6)

    def test_a_uv_sphere_reaches_its_radius_in_every_direction(self):
        for rings in (2, 3, 4, 5):
            with self.subTest(rings=rings):
                x, y, z = bounds(uv_sphere(radius=2, segments=8, rings=rings))
                self.assertAlmostEqual(y[1] - y[0], 4, places=6)
                self.assertAlmostEqual(x[1] - x[0], 4, places=6)

    def test_the_named_pole_anchors_sit_on_the_extent(self):
        g = uv_sphere(radius=2, segments=8, rings=4)
        self.assertAlmostEqual(g.anchors["top"][1], 2, places=6)
        self.assertAlmostEqual(g.anchors["base"][1], -2, places=6)


if __name__ == "__main__":
    unittest.main()
