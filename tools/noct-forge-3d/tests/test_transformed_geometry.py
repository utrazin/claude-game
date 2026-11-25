import unittest

from lib import ModelBuilder
from lib.geometry_validation import world_point


class TransformedGeometryTests(unittest.TestCase):
    def test_original_fangs_fail_even_with_rotated_jaw(self):
        b = ModelBuilder('fangs').add_transform_group('head', pivot=(0,0,0), rotation=(2, 0, 0))
        b.add_transform_group('jaw', 'head', pivot=(0, 32, -7), rotation=(6, 0, 0))
        b.add_cube('fang', 'head', from_=(.5, 32, -11), to_=(1.5, 33, -10))
        b.add_cube('jaw_cube', 'jaw', from_=(-1.5, 31, -12), to_=(1.5, 33, -7))
        errors = b.validate()['errors']
        self.assertTrue(any('(East)' in e for e in errors))
        self.assertTrue(any('completely submerged' in e for e in errors))
        self.assertFalse(any('(Up)' in e or '(North)' in e for e in errors))

    def test_equal_rotations_different_pivots_do_not_imply_coincidence(self):
        b = ModelBuilder('pivots').add_group('root')
        b.add_cube('a', 'root', from_=(0, 0, 0), to_=(2, 2, 2), origin=(0, 0, 0), rotation=(0, 0, 90))
        b.add_cube('b', 'root', from_=(0, 0, 0), to_=(2, 2, 2), origin=(10, 0, 0), rotation=(0, 0, 90))
        self.assertEqual(b.validate()['errors'], [])

    def test_rotation_composition_and_pivots(self):
        b = ModelBuilder('transforms').add_transform_group('root', pivot=(1, 0, 0), rotation=(0, 0, 90))
        b.add_transform_group('child', 'root', pivot=(1, 1, 0), rotation=(90, 0, 0))
        b.add_cube('cube', 'child', from_=(0, 0, 0), to_=(1, 1, 1))
        # Child maps (1,2,0) to (1,1,1); parent maps that to (0,0,1).
        for actual, expected in zip(world_point(b, b._elements[0], (1, 2, 0)), (0, 0, 1)):
            self.assertAlmostEqual(actual, expected)

    def test_quad_against_rotated_cube(self):
        b = ModelBuilder('quad').add_group('root')
        b.add_transform_group('child', 'root', pivot=(0,0,0), rotation=(20, 0, 0))
        b.add_cube('cube', 'child', from_=(0, 0, 0), to_=(1, 4, 4))
        b.add_axis_quad('detail', 'root', from_=(1, 1, 1), size=(1, 1), normal='+X')
        self.assertTrue(any('detail' in e and 'cube' in e for e in b.validate()['errors']))

if __name__ == '__main__':
    unittest.main()
