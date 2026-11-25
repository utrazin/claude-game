import unittest

from lib import ModelBuilder


def model_with_an_unrelated_problem():
    b = ModelBuilder("t", require_integer_dimensions=False)
    b.add_group("root")
    # two identical boxes: z-fighting between them is an existing problem, nothing to do with "far"
    b.add_box("twin_a", "root", size=(2, 2, 2), at=(0, 0, 0), anchor="base", native=False)
    b.add_box("twin_b", "root", size=(2, 2, 2), at=(0, 0, 0), anchor="base", native=False)
    b.add_cylinder("far", "root", radius=1, height=2, segments=8,
                   placement=__import__("lib").Placement.at((20, 0, 0)).pivot("base"))
    return b


class EditMeshScopeTests(unittest.TestCase):
    def test_an_edit_is_not_blocked_by_problems_it_did_not_cause(self):
        b = model_with_an_unrelated_problem()
        self.assertTrue(b.validate(require_armature_bindings=False)["errors"])
        with b.edit_mesh("far") as mesh:
            mesh.scale_vertices(list(mesh.vertices), (1.1, 1.1, 1.1))
        far = next(e for e in b._elements if e.name == "far")
        self.assertTrue(far.vertices)

    def test_an_edit_that_creates_a_problem_is_still_rolled_back(self):
        b = model_with_an_unrelated_problem()
        before = dict(next(e for e in b._elements if e.name == "far").vertices)
        with self.assertRaises(ValueError):
            with b.edit_mesh("far") as mesh:
                mesh.translate_vertices(list(mesh.vertices), (-20, 0, 0))   # lands on the twins
        self.assertEqual(dict(next(e for e in b._elements if e.name == "far").vertices), before)


if __name__ == "__main__":
    unittest.main()
