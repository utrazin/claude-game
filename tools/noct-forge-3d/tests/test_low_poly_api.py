import unittest
import tempfile
import math
from pathlib import Path

from lib import (Frame, MeshGeometry, ModelBuilder, Path3D, Placement, Profile, Section,
                 SegmentSection)
from lib.procedural import loft, segment_sections, sweep_sections
from Tools.low_poly_audit import audit_low_poly


class LowPolyApiTests(unittest.TestCase):
    def test_public_loft_accepts_independent_sections_and_preserves_rings(self):
        builder=ModelBuilder("true-loft",require_integer_dimensions=False).add_group("root")
        axis=(0,1,0)
        base=Frame((0,0,0),(1,0,0),(0,0,-1),axis)
        turned=base.rotate(15)
        middle=Frame((1,4,0),turned.x,turned.y,turned.z)
        top=Frame((0,8,0),(1,0,0),(0,0,-1),axis)
        builder.add_loft("form","root",sections=(
            Section("base",Profile.rectangle(4,3),base),
            Section("middle",Profile.rectangle(5,2),middle),
            Section("top",Profile.rectangle(3,2),top),
        ))
        element=builder._elements[-1]
        self.assertEqual(set(element.mesh_rings),{"base","middle","top"})
        self.assertEqual(len(element.faces),10)  # eight side quads plus two quad caps
        self.assertEqual(builder.get_anchor("form","middle"),(1.,4.,0.))
        self.assertFalse(builder.validate()["errors"])

    def test_true_loft_resolves_spatial_frame_references(self):
        builder=ModelBuilder("loft-reference",require_integer_dimensions=False).add_group("root")
        builder.add_socket("base","root",at=(2,3,4),forward=(0,1,0),up=(0,0,1))
        up=Frame((2,3,8),(1,0,0),(0,1,0),(0,0,1))
        builder.add_loft("form","root",sections=(
            Section("base",Profile.rectangle(2,2),"socket:base"),
            Section("top",Profile.rectangle(1,1),up),
        ))
        self.assertEqual(builder.get_anchor("form","base"),(2.,3.,4.))

    def test_named_ring_edit_changes_only_requested_ring_and_is_transactional(self):
        builder=ModelBuilder("ring-edit",require_integer_dimensions=False).add_group("root")
        sections=(SegmentSection("base",0,Profile.rectangle(2,2)),
                  SegmentSection("waist",.5,Profile.rectangle(2,2)),
                  SegmentSection("top",1,Profile.rectangle(2,2)))
        builder.add_segment("body","root",start=(0,0,0),end=(0,6,0),sections=sections)
        element=builder._elements[-1]
        before={key:element.vertices[key] for key in element.mesh_rings["base"]}
        with builder.edit_mesh("body") as mesh:
            mesh.edit_ring("waist").scale((.5,.75)).translate((.25,0))
        element=builder._elements[-1]
        self.assertEqual(before,{key:element.vertices[key] for key in element.mesh_rings["base"]})
        with self.assertRaises(ValueError):
            with builder.edit_mesh("body") as mesh:
                mesh.edit_ring("waist").scale(0)
        self.assertFalse(builder.validate()["errors"])

    def test_raw_mesh_and_semantic_forms_share_one_builder(self):
        builder=ModelBuilder("layered",require_integer_dimensions=False).add_group("root")
        geometry=MeshGeometry.create(
            {"a":(0,0,0),"b":(1,0,0),"c":(1,1,0),"d":(0,1,0)},
            {"face":("a","b","c","d")})
        builder.add_mesh("raw","root",geometry)
        builder.add_cylinder("allowed","root",radius=1,height=2,segments=8)
        builder.add_segment("also_allowed","root",start=(3,0,0),end=(3,2,0),sections=(
            SegmentSection("base",0,Profile.rectangle(1,1)),
            SegmentSection("top",1,Profile.rectangle(1,1)),
        ))
        with builder.edit_mesh("also_allowed") as mesh:
            mesh.edit_ring("top").scale(.75)
        self.assertFalse(builder.validate()["errors"])

    def test_group_roles_remain_available_without_construction_policy(self):
        builder=ModelBuilder("groups",require_integer_dimensions=False).add_group("root")
        builder.add_group("folder","root")
        builder.add_transform_group("implicit_joint","root",pivot=(0,0,0))
        builder.add_transform_group("joint","root",pivot=(0,4,0))
        builder.add_cylinder("in_folder","folder",radius=1,height=2,segments=8)
        builder.add_cylinder("valid","joint",radius=1,height=2,segments=8)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"model.bbmodel"
            builder.export_bbmodel(path)
            self.assertEqual(ModelBuilder.from_bbmodel(path)._groups["joint"].role,"transform")

    def test_loft_placement_rebases_element_pivot_to_spatial_target(self):
        builder=ModelBuilder("loft-placement",require_integer_dimensions=False).add_group("root")
        builder.add_transform_group("joint","root",pivot=(0,10,0))
        sections=(Section("base",Profile.rectangle(2,2),Frame((0,0,0))),
                  Section("top",Profile.rectangle(2,2),Frame((0,0,3))))
        builder.add_loft("form","joint",sections=sections,
                         placement=Placement.at("group:joint").pivot("base"))
        element=builder._elements[-1]
        self.assertEqual(element.origin,(0.,10.,0.))
        self.assertFalse(builder.validate()["warnings"])

    def test_segment_and_sweep_use_shared_loft_geometry(self):
        builder=ModelBuilder("shared-core",require_integer_dimensions=False).add_group("root")
        segment_spec=(SegmentSection("base",0,Profile.rectangle(2,2)),
                      SegmentSection("top",1,Profile.rectangle(1,1)))
        builder.add_segment("segment","root",start=(4,0,0),end=(4,3,0),sections=segment_spec)
        expected_segment=loft(segment_sections((0,0,0),(0,3,0),segment_spec)).build()
        actual=builder._elements[-1]
        self.assertEqual(actual.vertices,expected_segment.vertices)
        path=Path3D.line((0,0,0),(0,0,3))
        builder.add_sweep("sweep","root",profile=Profile.rectangle(2,2),path=path)
        expected_sweep=loft(sweep_sections(Profile.rectangle(2,2),path,x_hint=(1,0,0))).build()
        actual=builder._elements[-1]
        self.assertEqual(actual.vertices,expected_sweep.vertices)
        self.assertEqual(actual.mesh_rings,expected_sweep.rings)

    def test_low_poly_audit_warns_without_invalidating_uniform_form(self):
        builder=ModelBuilder("audit",require_integer_dimensions=False).add_group("root")
        profile=Profile.ellipse(2,2,segments=8)
        builder.add_segment("tube","root",start=(0,0,0),end=(0,6,0),sections=(
            SegmentSection("base",0,profile), SegmentSection("middle",.5,profile),
            SegmentSection("top",1,profile)))
        report=audit_low_poly(builder,face_budget=10)
        self.assertTrue(any("near-uniform collinear" in warning for warning in report["warnings"]))
        self.assertTrue(any("exceeding" in warning for warning in report["warnings"]))
        self.assertFalse(builder.validate()["errors"])

    def test_audit_treats_relation_tag_as_intent_for_close_shells(self):
        builder=ModelBuilder("related",require_integer_dimensions=False).add_group("root")
        builder.add_cylinder("one","root",radius=1,height=2,segments=8,tags=("relation:joined",))
        builder.add_cylinder("two","root",radius=1,height=2,segments=8,tags=("relation:joined",))
        self.assertFalse(any("overlapping" in warning for warning in audit_low_poly(builder)["warnings"]))
