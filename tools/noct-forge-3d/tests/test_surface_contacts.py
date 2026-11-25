import math
import unittest

from lib import Frame, SpatialFrame, SurfaceContact
from lib.spatial import box_surface_contacts, cross, turn


class SurfaceContactTests(unittest.TestCase):
    def assert_vector_close(self, actual, expected):
        self.assertLess(math.dist(actual, expected), 1e-7)

    def test_deterministic_normal_and_tangent_basis(self):
        contact = SurfaceContact((1, 2, 3), (0, 1, 0))
        self.assertEqual(contact.origin, (1.0, 2.0, 3.0))
        self.assertEqual(contact.normal, (0.0, 1.0, 0.0))
        self.assert_vector_close(cross(contact.tangent_u, contact.tangent_v), contact.normal)
        self.assert_vector_close(contact.tangent_u, (1, 0, 0))
        self.assert_vector_close(contact.tangent_v, (0, 0, -1))

    def test_contact_maps_points_and_roundtrips_all_frame_forms(self):
        contact = SurfaceContact((1, 2, 3), (0, 0, 1), tangent_u=(1, 0, 0))
        point = contact.point((2, -3, 4))
        self.assert_vector_close(point, (3, -1, 7))
        self.assert_vector_close(contact.local(point), (2, -3, 4))
        self.assertEqual(SurfaceContact.from_frame(contact.frame), contact)
        self.assertEqual(SurfaceContact.from_spatial_frame(contact.as_spatial_frame()), contact)
        self.assertEqual(contact.as_spatial_frame().right, contact.tangent_u)

    def test_transform_preserves_outward_normal_and_basis_after_reflection(self):
        contact = SurfaceContact((1, 2, 3), (0, 1, 0))
        reflected = contact.transformed(
            point_transform=lambda p: (-p[0], p[1], p[2]),
            vector_transform=lambda v: (-v[0], v[1], v[2]),
        )
        self.assertEqual(reflected.origin, (-1.0, 2.0, 3.0))
        self.assertEqual(reflected.normal, (0.0, 1.0, 0.0))
        self.assert_vector_close(cross(reflected.tangent_u, reflected.tangent_v), reflected.normal)

        rotated = contact.transformed(
            point_transform=lambda p: turn(p, (0, 0, 1), 90),
            vector_transform=lambda v: turn(v, (0, 0, 1), 90),
        )
        self.assert_vector_close(rotated.origin, (-2, 1, 3))
        self.assert_vector_close(rotated.normal, (-1, 0, 0))
        self.assert_vector_close(cross(rotated.tangent_u, rotated.tangent_v), rotated.normal)

    def test_opposite_contact_is_a_valid_mating_surface(self):
        contact = SurfaceContact((0, 0, 0), (0, 0, 1))
        opposite = contact.opposite()
        self.assert_vector_close(opposite.normal, (0, 0, -1))
        self.assert_vector_close(cross(opposite.tangent_u, opposite.tangent_v), opposite.normal)

    def test_box_contacts_are_semantic_and_outward(self):
        contacts = box_surface_contacts((-2, 1, -4), (6, 9, 8))
        self.assertEqual(set(contacts), {"left", "right", "bottom", "top", "back", "front"})
        self.assertEqual(contacts["top"].origin, (2.0, 9.0, 2.0))
        self.assertEqual(contacts["bottom"].normal, (0.0, -1.0, 0.0))
        self.assertEqual(contacts["front"].normal, (0.0, 0.0, 1.0))
        self.assertEqual(contacts["back"].normal, (0.0, 0.0, -1.0))

    def test_invalid_tangents_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Undefined direction"):
            SurfaceContact((0, 0, 0), (0, 1, 0), tangent_u=(0, 2, 0))
        with self.assertRaisesRegex(ValueError, "right-handed"):
            SurfaceContact((0, 0, 0), (0, 1, 0), tangent_u=(1, 0, 0), tangent_v=(0, 0, 1))
        with self.assertRaisesRegex(ValueError, "bounds"):
            box_surface_contacts((0, 0, 0), (0, 1, 1))


if __name__ == "__main__":
    unittest.main()
