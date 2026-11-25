import unittest
from lib.model_builder import ModelBuilder
from lib.spatial import Frame
from lib.procedural import Profile, Section, loft
from lib.primitives import capsule, wedge, prism, cylinder

class TestApiErgonomics(unittest.TestCase):
    def test_triangle_profile_and_loft(self):
        # 3 points forbidden by default
        with self.assertRaises(ValueError):
            Profile(((0, 0), (2, 0), (1, 2)))

        # 3 points allowed with allow_triangles=True
        tri_prof = Profile.triangle((0, 0), (2, 0), (1, 2))
        self.assertEqual(len(tri_prof.points), 3)
        self.assertTrue(tri_prof.allow_triangles)

        # Scale and resample preserve allow_triangles
        scaled = tri_prof.scale(2.0)
        self.assertTrue(scaled.allow_triangles)
        self.assertEqual(len(scaled.points), 3)

        # Loft with triangular profile
        builder = ModelBuilder("test_loft_tri")
        builder.add_group("root")
        builder.add_loft(
            "tri_prism", "root",
            sections=[
                Section("base", tri_prof, frame=Frame((0, 0, 0))),
                Section("top", tri_prof, frame=Frame((0, 0, 5))),
            ],
            allow_cap_triangles=True
        )
        self.assertEqual(len(builder._elements), 1)
        elem = builder.last_element
        self.assertEqual(len(elem.vertices), 6)
        # 3 side quad faces + 2 triangular caps
        self.assertEqual(len(elem.faces), 5)

    def test_odd_radial_primitive(self):
        # Odd segments forbidden without allow_triangles
        with self.assertRaises(ValueError):
            prism(radius=2, height=4, sides=3)
        with self.assertRaises(ValueError):
            prism(radius=2, height=4, sides=5)

        # Allowed with allow_triangles=True
        p3 = prism(radius=2, height=4, sides=3, allow_cap_triangles=True)
        self.assertTrue(p3.closed)
        self.assertEqual(len(p3.faces), 5)  # 3 sides + 2 triangular caps

        p5 = prism(radius=2, height=4, sides=5, allow_cap_triangles=True)
        self.assertTrue(p5.closed)

    def test_capsule_primitive(self):
        builder = ModelBuilder("test_capsule")
        builder.add_group("root")
        # Fluent chaining
        builder.add_capsule("cap", "root", radius=2.0, height=8.0, axis="Y", segments=8, rings=2)
        self.assertEqual(builder.last.name, "cap")
        elem = builder.last_element
        self.assertTrue(elem.mesh_closed)
        self.assertIn("base", elem.anchors)
        self.assertIn("top", elem.anchors)
        self.assertEqual(elem.anchors["base"], (0, -4.0, 0))
        self.assertEqual(elem.anchors["top"], (0, 4.0, 0))

        # Height must be at least 2 * radius
        with self.assertRaises(ValueError):
            capsule(radius=5.0, height=8.0)

    def test_wedge_primitive(self):
        builder = ModelBuilder("test_wedge")
        builder.add_group("root")
        builder.add_wedge("ramp", "root", width=4.0, depth=6.0, height=3.0, axis="Y")
        elem = builder.last_element
        self.assertTrue(elem.mesh_closed)
        self.assertEqual(len(elem.faces), 5)  # 3 quads + 2 triangles
        self.assertIn("ramp", elem.faces)
        self.assertIn("side_left", elem.faces)
        self.assertIn("side_right", elem.faces)

    def test_stack_on_cubes_and_meshes(self):
        builder = ModelBuilder("test_stack")
        builder.add_group("root")
        # Add table top as box
        builder.add_box("table", "root", size=(10, 4, 10), at=(0, 0, 0))
        # Add book as box initially at (0, 0, 0)
        builder.add_box("book", "root", size=(4, 1, 4), at=(0, 0, 0))
        # Stack book on table along +Y
        builder.stack_on("book", "table", axis="+Y", offset=0.5)

        table_elem = next(e for e in builder._elements if e.name == "table")
        book_elem = next(e for e in builder._elements if e.name == "book")
        table_top_y = max(table_elem.from_[1], table_elem.to_[1])
        book_bottom_y = min(book_elem.from_[1], book_elem.to_[1])
        self.assertAlmostEqual(book_bottom_y, table_top_y + 0.5)

        # Add wedge on book
        builder.add_wedge("ramp", "root", width=2, depth=2, height=1)
        builder.stack_on("ramp", "book", axis="+Y")
        ramp_elem = next(e for e in builder._elements if e.name == "ramp")
        ramp_low, ramp_high = builder._element_bounds(ramp_elem)
        book_low, book_high = builder._element_bounds(book_elem)
        self.assertAlmostEqual(ramp_low[1], book_high[1])

    def test_mirror_element(self):
        builder = ModelBuilder("test_mirror")
        builder.add_group("root")
        builder.add_transform_group("arm_left", "root", pivot=(5, 10, 0))
        builder.add_transform_group("arm_right", "root", pivot=(-5, 10, 0))

        builder.add_capsule("shoulder_left", "arm_left", radius=1.5, height=5.0, axis="Y")
        builder.mirror("shoulder_left", "shoulder_right", axis="X")

        right_elem = next(e for e in builder._elements if e.name == "shoulder_right")
        self.assertEqual(right_elem.parent, "arm_right")  # auto-detected bilateral group!
        self.assertEqual(right_elem.name, "shoulder_right")
        self.assertTrue(right_elem.mesh_closed)

        # Mirror a cube
        builder.add_box("hand_left", "arm_left", size=(2, 2, 2), at=(1, -2, 0))
        builder.mirror("hand_left", "hand_right", axis="X")
        hand_r = next(e for e in builder._elements if e.name == "hand_right")
        self.assertEqual(hand_r.parent, "arm_right")
        self.assertAlmostEqual(hand_r.from_[0], -2)
        self.assertAlmostEqual(hand_r.to_[0], 0)

if __name__ == "__main__":
    unittest.main()
