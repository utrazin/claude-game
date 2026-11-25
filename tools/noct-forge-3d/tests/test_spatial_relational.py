import json
import math
import tempfile
import unittest
from pathlib import Path

from lib import (Curve, MeshDraft, ModelBuilder, Placement, Profile, RelativePath,
                 SegmentSection, SpatialFrame)
from lib.primitives import cylinder,frustum,plane,quad_face,quad_sphere,uv_sphere
from Tools.uv_builder import UVBuilder


class SpatialRelationalTests(unittest.TestCase):
    def test_universal_references_and_ambiguity(self):
        builder=ModelBuilder("refs").add_group("root").add_transform_group("joint","root",pivot=(1,2,3))
        builder.add_socket("mount","joint",at="group:joint",forward=(1,0,0),up=(0,0,1))
        self.assertEqual(builder.resolve_point("group:joint"),(1.,2.,3.))
        self.assertEqual(builder.resolve_point("socket:mount"),(1.,2.,3.))
        builder.add_socket("joint","joint",at=(4,5,6))
        with self.assertRaisesRegex(KeyError,"Ambiguous"):
            builder.resolve_point("joint")

    def test_frames_follow_ancestor_rotation_and_roundtrip(self):
        builder=ModelBuilder("frames",require_integer_dimensions=False)
        builder.add_transform_group("root",pivot=(0,0,0),rotation=(0,0,90)).add_transform_group("arm","root",pivot=(2,0,0))
        builder.add_socket("tip","arm",at="group:arm",forward=(0,1,0),up=(0,0,1))
        builder.add_cylinder("limb","arm",radius=1,height=2,segments=8,
                             placement=Placement.at("group:arm").pivot("base"))
        world=builder.get_socket("tip")
        self.assertAlmostEqual(world.origin[0],0,places=6)
        self.assertAlmostEqual(world.origin[1],2,places=6)
        self.assertAlmostEqual(world.forward[0],-1,places=6)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"model.bbmodel"; builder.export_bbmodel(path)
            loaded=ModelBuilder.from_bbmodel(path)
            self.assertEqual(loaded.get_socket("tip"),world)
            self.assertEqual(loaded.get_frame("limb","base"),builder.get_frame("limb","base"))

    def test_box_loft_chain_and_relative_sweep(self):
        builder=ModelBuilder("declarative",require_integer_dimensions=False).add_group("root")
        box=builder.add_box("body","root",size=(4,6,2),at=(0,3,0),anchor="center").last
        self.assertEqual(box.anchor("base"),(0.,0.,0.))
        builder.add_socket("neck","root",at="body:top")
        sections=(SegmentSection("base",0,Profile.rectangle(3,2)),
                  SegmentSection("top",1,Profile.rectangle(2,1),offset=(.25,0)))
        builder.add_segment("head","root",start="socket:neck",end=(0,11,0),sections=sections)
        self.assertEqual(builder.get_anchor("head","base"),builder.resolve_point("socket:neck"))
        bones=builder.add_transform_chain("tail","root",start="body:back",direction=(0,0,-1),segments=(
            {"name":"base","length":2,"profile":Profile.rectangle(.5,.5)},
            {"name":"tip","length":1.5,"profile":Profile.rectangle(.3,.3)},))
        self.assertEqual(bones,("tail_base","tail_tip"))
        self.assertTrue(all(builder._groups[name].role == "transform" for name in bones))
        path=RelativePath.from_frame("socket:neck",points=((0,0,0),(0,1,0),(1,2,0)))
        builder.add_sweep("crest","root",profile=Profile.rectangle(.25,.25),path=path)
        self.assertEqual(builder.get_anchor("crest","base"),builder.resolve_point("socket:neck"))
        curve=Curve.between("body:base","body:top",bend=(1,2,0),samples=5).resolve(builder)
        self.assertEqual(len(curve.points),5)

    def test_mirror_group_preserves_transform_roles(self):
        builder = ModelBuilder("mirror_roles")
        builder.add_group("root")
        builder.add_transform_group("link_left", "root", pivot=(2, 0, 0))
        builder.add_transform_group("end_left", "link_left", pivot=(0, 2, 0))
        builder.mirror("link_left", "link_right")
        self.assertEqual(builder._groups["link_right"].role, "transform")
        self.assertEqual(builder._groups["end_right"].role, "transform")

    def test_place_aligns_two_oriented_frames(self):
        builder=ModelBuilder("place",require_integer_dimensions=False).add_group("root")
        builder.add_socket("target","root",at=(4,5,6),forward=(1,0,0),up=(0,0,1))
        builder.add_cylinder("part","root",radius=1,height=2,segments=8)
        builder.place("part",source="base",target="socket:target")
        actual=builder.get_frame("part","base")
        expected=builder.get_socket("target")
        self.assertLess(math.dist(actual.origin,expected.origin),1e-7)
        self.assertLess(math.dist(actual.forward,expected.forward),1e-7)

    def test_merge_preserves_namespaced_frames(self):
        builder=ModelBuilder("merge",require_integer_dimensions=False).add_group("root")
        builder.add_cylinder("a","root",radius=1,height=2,segments=8,
                             placement=Placement.at((0,0,0)))
        builder.add_cylinder("b","root",radius=1,height=2,segments=8,
                             placement=Placement.at((4,0,0)))
        builder.combine_meshes(("a","b"),"both")
        self.assertIn("a__base",builder._elements[0].frames)
        self.assertEqual(builder.get_frame("both","b__center").origin,(4.,0.,0.))

    def test_live_socket_follows_source_and_blocks_invalidating_merge(self):
        builder=ModelBuilder("live",require_integer_dimensions=False).add_group("root")
        builder.add_cylinder("source","root",radius=1,height=2,segments=8)
        builder.add_socket("live_mount","root",at="source:top")
        before=builder.get_socket("live_mount").origin
        builder.translate_element("source",(3,0,0))
        after=builder.get_socket("live_mount").origin
        self.assertAlmostEqual(after[0]-before[0],3)
        builder.add_cylinder("other","root",radius=1,height=2,segments=8,
                             placement=Placement.at((5,0,0)))
        with self.assertRaisesRegex(ValueError,"live sockets"):
            builder.combine_meshes(("source","other"),"merged")

    def test_primitives_expose_predictable_oriented_frames(self):
        geometries=(cylinder(radius=1,height=2,segments=8),
                    frustum(bottom_radius=1,top_radius=.5,height=2,segments=8),
                    uv_sphere(radius=1,segments=8,rings=4),quad_sphere(radius=1),
                    plane(width=2,height=2),
                    quad_face(points=((-1,0,0),(1,0,0),(1,1,0),(-1,1,0))))
        for geometry in geometries:
            with self.subTest(primitive=geometry.primitive):
                self.assertIn("center",geometry.frames)
                self.assertEqual(geometry.frames["center"].origin,geometry.anchors["center"])
        self.assertIn("side_000",geometries[0].frames)
        self.assertIn("ring_001",geometries[2].frames)
        self.assertEqual(geometries[3].frames["right"].forward,(1.,0.,0.))

    def test_declarative_box_stays_native_cube(self):
        builder=ModelBuilder("box").add_group("root")
        builder.add_box("base","root",size=(4,2,6),at=(0,0,0),anchor="base")
        builder.add_box("top","root",size=(2,2,2),at="base:top",anchor="base")
        self.assertTrue(all(element.kind=="cube" for element in builder._elements))
        self.assertEqual(builder.get_anchor("top","base"),builder.get_anchor("base","top"))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"box.bbmodel"
            builder.export_bbmodel(path)
            UVBuilder(path,require_integer_uvs=True).save()
            data=json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(all(element["type"]=="cube" for element in data["elements"]))
            self.assertTrue(data["unhandled_root_fields"]["model_as_code"]["uv_ready"])

    def test_ring_frames_refresh_after_partial_deformation(self):
        draft=MeshDraft.from_geometry(cylinder(radius=1,height=2,segments=8))
        before=draft.frames["top"].origin
        top=draft.select_vertices(ring="top")
        draft.translate_vertices(top,(0,1,0))
        self.assertAlmostEqual(draft.frames["top"].origin[1]-before[1],1)

    def test_segment_selects_stable_frame_for_each_axis(self):
        sections=(SegmentSection("start",0,Profile.rectangle(1,1)),
                  SegmentSection("end",1,Profile.rectangle(1,1)))
        builder=ModelBuilder("axes",require_integer_dimensions=False).add_group("root")
        for name,end in (("x",(3,0,0)),("y",(0,3,0)),("z",(0,0,3))):
            builder.add_segment(name,"root",start=(0,0,0),end=end,sections=sections)
            self.assertEqual(builder.get_anchor(name,"end"),tuple(float(v) for v in end))


if __name__ == "__main__": unittest.main()
