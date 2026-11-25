import math
import unittest

from lib import periodic, periodic_curve, quintic, smooth_periodic, spring_follow


class MotionTests(unittest.TestCase):
    def test_quintic_meets_its_ends_and_slopes(self):
        self.assertAlmostEqual(quintic(2.0, 5.0, -1.0, 3.0, 0.0), 2.0)
        self.assertAlmostEqual(quintic(2.0, 5.0, -1.0, 3.0, 1.0), 5.0)
        h = 1e-6
        self.assertAlmostEqual((quintic(2.0, 5.0, -1.0, 3.0, h) - 2.0) / h, -1.0, places=4)
        self.assertAlmostEqual((5.0 - quintic(2.0, 5.0, -1.0, 3.0, 1 - h)) / h, 3.0, places=4)

    def test_periodic_interpolates_numbers_and_vectors_and_repeats(self):
        numbers = periodic([0.0, 10.0, 20.0, 10.0], 2.0)
        self.assertAlmostEqual(numbers(0.25), 5.0)
        self.assertAlmostEqual(numbers(2.25), 5.0)
        self.assertAlmostEqual(numbers(1.75), 5.0)                 # wraps back toward the first sample
        vectors = periodic([(0.0, 0.0, 0.0), (2.0, 4.0, 6.0)], 1.0)
        self.assertEqual(vectors(0.25), (1.0, 2.0, 3.0))
        with self.assertRaises(ValueError):
            periodic([1.0], 1.0)

    def test_periodic_curve_is_continuous_and_holds_plateaus(self):
        keys = ((0.0, -8.0), (0.12, 0.0), (0.3, 0.0), (0.6, 20.0), (0.7, 24.0), (0.93, -7.0))
        for x in (0.0, 0.12, 0.6, 0.7):
            self.assertAlmostEqual(periodic_curve(keys, x), dict(keys)[x])
        for x in (0.15, 0.2, 0.25, 0.29):                          # never overshoots a flat stretch
            self.assertAlmostEqual(periodic_curve(keys, x), 0.0)
        self.assertAlmostEqual(periodic_curve(keys, 0.999999), periodic_curve(keys, 0.0), places=3)
        h = 1e-5
        for x in (0.05, 0.45, 0.65, 0.8, 0.97):                   # value and slope continuous
            left = (periodic_curve(keys, x) - periodic_curve(keys, x - h)) / h
            right = (periodic_curve(keys, x + h) - periodic_curve(keys, x)) / h
            self.assertAlmostEqual(left, right, delta=0.05 * max(1.0, abs(left)))
        with self.assertRaises(ValueError):
            periodic_curve(((0.0, 1.0),), 0.5)

    def test_spring_follow_trails_and_settles_into_a_loop(self):
        target = lambda t: (math.sin(2 * math.pi * t), 0.0, 0.0)
        follower = spring_follow(target, 3.0, 0.7, 1.0)
        self.assertAlmostEqual(follower(0.0)[0], follower(1.0)[0], places=2)
        peak_target = max(range(100), key=lambda i: target(i / 100)[0])
        peak_follow = max(range(100), key=lambda i: follower(i / 100)[0])
        self.assertGreater(peak_follow, peak_target)               # it lags behind
        self.assertLess(max(follower(i / 100)[0] for i in range(100)), 1.1)
        stiff = spring_follow(target, 40.0, 1.0, 1.0)
        self.assertAlmostEqual(stiff(0.3)[0], target(0.3)[0], delta=0.05)
        with self.assertRaises(ValueError):
            spring_follow(target, 0.0, 0.5, 1.0)

    def test_smooth_periodic_softens_corners_and_keeps_the_mean(self):
        samples = [0.0] * 50 + [1.0] * 50
        blurred = smooth_periodic(samples, 1.0, 0.05)
        self.assertAlmostEqual(sum(blurred) / 100, 0.5)
        self.assertGreater(blurred[49], 0.0)
        self.assertLess(blurred[50], 1.0)
        self.assertGreater(blurred[99], 0.0)                       # wraps around the loop
        self.assertEqual(smooth_periodic(samples, 1.0, 0.0), samples)

    def test_smooth_periodic_blurs_vectors_per_axis(self):
        xs = [0.0] * 50 + [1.0] * 50
        zs = [math.sin(2 * math.pi * i / 100) for i in range(100)]
        vectors = [(x, 2.0, z) for x, z in zip(xs, zs)]
        blurred = smooth_periodic(vectors, 1.0, 0.05)
        self.assertEqual(len(blurred), 100)
        self.assertTrue(all(isinstance(item, tuple) and len(item) == 3 for item in blurred))
        for got, x, z in zip(blurred, smooth_periodic(xs, 1.0, 0.05), smooth_periodic(zs, 1.0, 0.05)):
            self.assertAlmostEqual(got[0], x)
            self.assertAlmostEqual(got[1], 2.0)
            self.assertAlmostEqual(got[2], z)
        self.assertEqual(periodic(blurred, 1.0)(0.0), blurred[0])  # feeds periodic() directly


if __name__ == "__main__":
    unittest.main()
