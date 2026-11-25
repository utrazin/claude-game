import unittest

from lib import MeshDraft, ModelBuilder


def tetrahedron():
    draft = MeshDraft(closed=True)
    for name, point in {"a": (0, 0, 0), "b": (2, 0, 0), "c": (0, 0, 2), "d": (0, 2, 0)}.items():
        draft.vertex(name, point)
    for name, order in {"bottom": "acb", "front": "abd", "left": "cad", "right": "bcd"}.items():
        draft.face(name, tuple(order))
    return draft


class TrianglePolicyTests(unittest.TestCase):
    def builder(self):
        b = ModelBuilder("t", require_integer_dimensions=False)
        b.add_group("root")
        return b

    def test_triangles_in_a_hand_made_mesh_must_be_declared(self):
        with self.assertRaisesRegex(ValueError, "allow_triangles=True"):
            self.builder().add_mesh("tetra", "root", tetrahedron())

    def test_declared_triangles_are_accepted(self):
        b = self.builder()
        b.add_mesh("tetra", "root", tetrahedron(), allow_triangles=True)
        self.assertEqual(b.validate()["errors"], [])

    def test_primitives_with_apexes_need_no_flag(self):
        b = self.builder()
        b.add_cone("cone", "root", radius=1, height=2, segments=8)
        self.assertEqual(b.validate()["errors"], [])


if __name__ == "__main__":
    unittest.main()
