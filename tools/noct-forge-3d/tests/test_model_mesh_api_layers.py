import unittest

from lib import (Frame, MeshDraft, ModelBuilder, Path3D, Profile, RelativePath,
                 Section, SegmentSection)
from lib.primitives import cylinder


class MeshApiLayersTests(unittest.TestCase):
    def test_literal_geometry_is_parent_local_and_references_are_world_space(self):
        builder = ModelBuilder("spaces", require_integer_dimensions=False)
        builder.add_transform_group("root", pivot=(0, 0, 0), rotation=(0, 0, 90))
        builder.add_box("mark", "root", size=(1, 1, 1), at=(1, 0, 0))
        sections = (SegmentSection("start", 0, Profile.rectangle(1, 1)),
                    SegmentSection("end", 1, Profile.rectangle(1, 1)))

        builder.add_segment("literal", "root", start=(1, 0, 0), end=(1, 2, 0),
                            sections=sections)
        builder.add_segment("reference", "root", start="mark:center", end=(1, 2, 0),
                            sections=sections)
        self.assertEqual(builder.get_anchor("literal", "start"),
                         builder.get_anchor("mark", "center"))
        self.assertEqual(builder.get_anchor("reference", "start"),
                         builder.get_anchor("mark", "center"))
        self.assertAlmostEqual(builder.get_anchor("literal", "end")[0], -2)

        builder.add_loft("loft", "root", sections=(
            Section("a", Profile.rectangle(1, 1), Frame((1, 0, 0))),
            Section("b", Profile.rectangle(1, 1), Frame((1, 0, 2))),
        ))
        self.assertEqual(builder.get_anchor("loft", "a"),
                         builder.get_anchor("mark", "center"))

        builder.add_sweep("local_path", "root", profile=Profile.rectangle(1, 1),
                          path=Path3D.line((1, 0, 0), (1, 0, 2)))
        builder.add_sweep("world_path", "root", profile=Profile.rectangle(1, 1),
                          path=RelativePath.from_frame("mark:center",
                                                       points=((0, 0, 0), (0, 0, 2))))
        self.assertEqual(builder.get_anchor("local_path", "base"),
                         builder.get_anchor("mark", "center"))
        self.assertEqual(builder.get_anchor("world_path", "base"),
                         builder.get_anchor("mark", "center"))

    def test_odd_sections_can_stay_quad_only_when_open(self):
        open_cylinder = cylinder(radius=2, height=4, segments=5,
                                 start_cap="open", end_cap="open")
        self.assertFalse(open_cylinder.closed)
        self.assertTrue(all(len(face.vertices) == 4 for face in open_cylinder.faces.values()))
        with self.assertRaisesRegex(ValueError, "allow_cap_triangles"):
            cylinder(radius=2, height=4, segments=5)
        closed_cylinder = cylinder(radius=2, height=4, segments=5,
                                   allow_cap_triangles=True)
        self.assertTrue(closed_cylinder.closed)
        self.assertTrue(any(len(face.vertices) == 3 for face in closed_cylinder.faces.values()))

    def test_revolve_facade_and_raw_draft_coexist(self):
        builder = ModelBuilder("layers", require_integer_dimensions=False).add_group("root")
        builder.add_revolve("vase", "root", meridian=((1, 0), (2, 2), (1, 4)),
                            segments=8)
        self.assertEqual(builder.last.primitive, "revolve")
        self.assertEqual(set(builder.last.anchors) & {"base", "top"}, {"base", "top"})
        draft = MeshDraft().vertex("a", (5, 0, 0)).vertex("b", (6, 0, 0))
        draft.vertex("c", (6, 1, 0)).vertex("d", (5, 1, 0))
        draft.face("surface", ("a", "b", "c", "d"))
        builder.add_mesh("panel", "root", draft)
        self.assertEqual(builder.last.name, "panel")
        with self.assertRaisesRegex(TypeError, "MeshDraft or MeshGeometry"):
            builder.add_mesh("invalid", "root", {"a": (0, 0, 0)})
        self.assertFalse(builder.validate()["errors"])


if __name__ == "__main__":
    unittest.main()
