import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from lib import ModelBuilder
from lib.geometry_types import MeshFace, MeshGeometry
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.core.contact_fields import _blend
from Tools.TexturePainter.core.contact_fields import _triangle_intersection_segment
from Tools.TexturePainter.core.contact_fields import _merge_collinear_segments
from Tools.uv_builder import UVBuilder


class ContactFieldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.bbmodel"

    def build_corner(self, *, concave=True):
        if not concave:
            (ModelBuilder("convex").add_group("root")
             .add_cube("corner", "root", from_=(-2, 0, 0), to_=(2, 4, 4), tags=["body"])
             .export_bbmodel(self.model))
            UVBuilder(self.model, start_size=(64, 32)).save()
            return TexturePainter.from_bbmodel(self.model)
        vertices = {
            "a": (-2, 0, 0), "b": (2, 0, 0), "c": (2, 0, 4), "d": (-2, 0, 4),
            "e": (2, 4, 0), "f": (-2, 4, 0),
        }
        wall = ("a", "b", "e", "f")
        builder = ModelBuilder("corner", require_integer_dimensions=False).add_group("root")
        builder.add_mesh("corner", "root", MeshGeometry.create(vertices, {
             "floor": MeshFace(("a", "d", "c", "b")),
             "wall": MeshFace(wall),
         }), tags=["body"])
        builder.export_bbmodel(self.model)
        UVBuilder(self.model, start_size=(64, 32), require_integer_uvs=False).save()
        return TexturePainter.from_bbmodel(self.model)

    def build_boxes(self, gap=-0.5):
        (ModelBuilder("contacts")
         .add_group("root")
         .add_cube("source", "root", from_=(0, 0, 0), to_=(4, 4, 4), tags=["source"])
         .add_cube("receiver", "root", from_=(4 + gap, .25, .5),
                   to_=(8 + gap, 4.25, 4.5), tags=["receiver"])
         .export_bbmodel(self.model))
        UVBuilder(self.model, start_size=(128, 64)).save()
        return TexturePainter.from_bbmodel(self.model)

    def test_concave_crease_detects_but_convex_corner_does_not(self):
        painter = self.build_corner(concave=True)
        field = painter.creases(receivers=painter.select(tag="body"),
                                max_internal_angle=100, spread=1.5).require_nonempty()
        self.assertTrue(all(hit.kind == "crease" for hit in field))
        self.assertEqual(field.stats["events"], 2)
        first = next(iter(field))
        with self.assertRaises(FrozenInstanceError):
            first.kind = "changed"

        painter = self.build_corner(concave=False)
        self.assertEqual(len(painter.creases(max_internal_angle=100, spread=1.5)), 0)

    def test_intersection_proximity_and_selection_filters(self):
        painter = self.build_boxes(gap=-0.5)
        field = painter.contacts(
            sources=painter.select(tag="source"), receivers=painter.select(tag="receiver"),
            tolerance=0, spread=1).require_nonempty()
        self.assertIn("intersection", field.stats["kinds"])
        self.assertEqual(field.stats["elements"], ("receiver",))
        self.assertTrue(any(hit.inside_contact for hit in field))
        self.assertTrue(any(not hit.inside_contact for hit in field))
        self.assertTrue(all(0 <= hit.occluded_fraction <= 1 for hit in field))
        self.assertTrue(all(hit.inside_contact == (hit.occluded_fraction >= 1-1e-6)
                            for hit in field))
        self.assertTrue(any(0 < hit.occluded_fraction < 1 for hit in field))

        painter = self.build_boxes(gap=0.2)
        near = painter.contacts(
            sources=painter.select(tag="source"), receivers=painter.select(tag="receiver"),
            tolerance=0.25, spread=1).require_nonempty()
        self.assertIn("proximity", near.stats["kinds"])
        far = painter.contacts(
            sources=painter.select(tag="source"), receivers=painter.select(tag="receiver"),
            tolerance=0.1, spread=1)
        self.assertEqual(len(far), 0)

    def test_triangle_intersection_preserves_the_full_segment(self):
        horizontal = ((-2, 0, -2), (2, 0, -2), (0, 0, 2))
        vertical = ((-1, -2, 0), (1, -2, 0), (0, 2, 0))
        segment = _triangle_intersection_segment(horizontal, vertical)
        self.assertIsNotNone(segment)
        self.assertGreater(sum((segment[0][i]-segment[1][i])**2 for i in range(3)), 0.5)
        merged = _merge_collinear_segments((((0,0,0),(1,0,0)),
                                             ((1,0,0),(2,0,0)),
                                             ((0,0,0),(1,0,0))))
        self.assertEqual(merged, (((0,0,0),(2,0,0)),))

    def test_union_mask_reports_and_paints_declaratively(self):
        painter = self.build_boxes(gap=-0.5)
        painter.receiver.fill_all("#808080")
        contacts = painter.contacts(
            sources=painter.select(tag="source"), receivers=painter.select(tag="receiver"),
            tolerance=0, spread=1)
        combined = contacts | contacts
        self.assertEqual(len(combined), len(contacts))
        intersections = combined.mask(lambda hit: hit.kind == "intersection")
        self.assertEqual(len(intersections), len(combined))
        self.assertEqual(json.loads(intersections.report(json=True))["texels"], len(intersections))
        self.assertIn("GeometryField:", intersections.report())
        hit = next(iter(intersections))
        face = painter.element(hit.surface.element_name).face(hit.surface.face_name)
        before = face.get_pixel(*hit.surface.pixel)
        intersections.paint(lambda item: "#804020" if item.intensity > 0 else None,
                            blend="multiply", opacity=0.5)
        self.assertNotEqual(face.get_pixel(*hit.surface.pixel), before)

    def test_blend_modes_are_deterministic_and_validate_inputs(self):
        expected = {
            "replace": (63, 87, 100, 160),
            "normal": (63, 87, 100, 160),
            "multiply": (42, 80, 97, 160),
            "screen": (70, 108, 128, 160),
            "add": (75, 113, 131, 160),
        }
        for mode, value in expected.items():
            with self.subTest(mode=mode):
                self.assertEqual(_blend((50, 100, 125, 128), (100, 50, 25, 128), mode, 0.5), value)
        with self.assertRaisesRegex(ValueError, "blend"):
            _blend((0,0,0,255), (0,0,0,255), "bad", 1)

    def test_broad_phase_skips_separated_geometry(self):
        builder = ModelBuilder("broad-phase").add_group("root")
        for index in range(8):
            start = index * 20
            builder.add_cube(f"box_{index}", "root", from_=(start, 0, 0),
                             to_=(start + 4, 4, 4), tags=["box"])
        builder.export_bbmodel(self.model)
        UVBuilder(self.model, start_size=(256, 128)).save()
        painter = TexturePainter.from_bbmodel(self.model)
        field = painter.contacts(tolerance=0.25, spread=1)
        self.assertEqual(len(field), 0)
        self.assertEqual(painter._geometry_fields.narrow_phase_pairs, 0)

    def test_field_crosses_uv_islands_only_through_surface_adjacency(self):
        vertices = {
            "a": (0,0,0), "b": (4,0,0), "c": (4,4,0), "d": (0,4,0),
            "e": (8,0,0), "f": (8,4,0),
            "g": (4,0,.2), "h": (8,0,.2), "i": (8,4,.2), "j": (4,4,.2),
        }
        builder = ModelBuilder("surface-distance", require_integer_dimensions=False).add_group("root")
        builder.add_cube("source", "root", from_=(1,1,-1), to_=(3,3,1), tags=["source"])
        builder.add_mesh("receiver", "root", MeshGeometry.create(vertices, {
            "contact": MeshFace(("a","b","c","d")),
            "connected": MeshFace(("b","e","f","c")),
            "detached": MeshFace(("g","h","i","j")),
        }), tags=["receiver"])
        builder.export_bbmodel(self.model)
        UVBuilder(self.model, start_size=(128,64), uv_scale=2,
                  require_integer_uvs=False, island_padding=1).save()
        painter=TexturePainter.from_bbmodel(self.model)
        field=painter.contacts(sources=painter.select(tag="source"),
                               receivers=painter.select(tag="receiver"),
                               tolerance=0,spread=3).require_nonempty()
        reached={hit.surface.face_name for hit in field}
        self.assertIn("contact",reached)
        self.assertIn("connected",reached)
        self.assertNotIn("detached",reached)

    def test_shared_receiver_uv_is_rejected_before_painting(self):
        (ModelBuilder("shared-contact").add_group("root")
         .add_cube("source", "root", from_=(0, 0, 0), to_=(4, 4, 4), tags=["source"])
         .add_cube("receiver", "root", from_=(4, 0, 0), to_=(8, 4, 4), tags=["receiver"])
         .export_bbmodel(self.model))
        uv = UVBuilder(self.model, start_size=(128, 64)).clear_sharing()
        uv.share_uv(("receiver", "west"), source=("source", "east"))
        uv.save()
        painter = TexturePainter.from_bbmodel(self.model)
        with self.assertRaisesRegex(ValueError, "shared UV followers"):
            painter.contacts(
                sources=painter.select(tag="source"),
                receivers=painter.select(tag="receiver"),
                tolerance=0, spread=1)


if __name__ == "__main__":
    unittest.main()
