import copy
import json
import tempfile
import unittest
from pathlib import Path

from lib import (CapSpec, Frame, MeshDraft, MeshGeometry, ModelBuilder, Path3D,
                 Placement, Profile, Section)
from lib.geometry_types import MeshFace
from lib.procedural import loft, revolve, sweep
from lib.geometry_validation import world_point
from lib.mesh_validation import validate_geometry
from lib.primitives import cone, cylinder, frustum, prism, pyramid, triangle, uv_sphere
from Tools.TexturePainter import TexturePainter
from Tools.uv_packer import BoxUVPacker


def assert_tri_quad_only(test, faces):
    test.assertTrue(faces)
    test.assertTrue(all(len(face.vertices if hasattr(face, "vertices") else face["vertices"]) in (3, 4)
                        for face in faces))


def assert_quad_only(test, faces):
    test.assertTrue(faces)
    test.assertTrue(all(len(face.vertices if hasattr(face, "vertices") else face["vertices"]) == 4
                        for face in faces))


class PolygonApiTests(unittest.TestCase):
    def test_triangles_are_explicit_supported_topology_but_ngons_are_rejected(self):
        self.assertEqual(MeshFace(("a", "b", "c")).vertices, ("a", "b", "c"))
        geometry=MeshGeometry.create({"a":(0,0,0),"b":(1,0,0),"c":(0,1,0)},
                                     {"face":("a","b","c")})
        self.assertEqual(geometry.faces["face"].vertices, ("a", "b", "c"))
        draft=MeshDraft()
        for key,point in {"a":(0,0,0),"b":(1,0,0),"c":(0,1,0)}.items(): draft.vertex(key,point)
        draft.face("face",("a","b","c"))
        import lib.primitives as primitives
        self.assertTrue(hasattr(primitives,"triangle"))
        builder=ModelBuilder("strict",require_integer_dimensions=False).add_group("root")
        # ModelBuilder exposes the semantic wrapper; direct mesh factories
        # retain tri/quad topology for internal and imported geometry.
        self.assertTrue(hasattr(builder,"add_triangle"))
        self.assertFalse(hasattr(draft,"triangulate"))
        with self.assertRaisesRegex(ValueError, "three or four"):
            MeshFace(("a", "b", "c", "d", "e"))

    def test_direct_mesh_geometry_constructor_enforces_tri_quad_contract(self):
        with self.assertRaisesRegex(ValueError, "three or four"):
            MeshGeometry({"a":(0,0,0),"b":(1,0,0),"c":(0,1,0),"d":(1,1,0),"e":(2,0,0)},
                         {"face":("a","b","c","d","e")})
        with self.assertRaisesRegex(ValueError, "missing vertices"):
            MeshGeometry({"a":(0,0,0),"b":(1,0,0),"c":(1,1,0),"d":(0,1,0)},
                         {"face":("a","b","c","missing")})

    def test_import_accepts_triangle_but_rejects_ngons(self):
        data={"meta":{"model_format":"free"},"elements":[{
            "type":"mesh","name":"bad","uuid":"bad","origin":[0,0,0],
            "vertices":{"a":[0,0,0],"b":[1,0,0],"c":[0,1,0]},
            "faces":{"face":{"vertices":["a","b","c"]}},
            "model_as_code_mesh":{"closed":False}}]}
        loaded=ModelBuilder.from_bbmodel_data(data)
        self.assertEqual(loaded._elements[0].faces["face"]["vertices"], ["a", "b", "c"])
        data["elements"][0]["vertices"]["d"] = [1, 1, 0]
        data["elements"][0]["vertices"]["e"] = [2, 0, 0]
        data["elements"][0]["faces"]["face"]["vertices"] = ["a", "b", "c", "d", "e"]
        with self.assertRaisesRegex(ValueError,"triangles or quads"):
            ModelBuilder.from_bbmodel_data(data)

    def test_ngons_and_invalid_contours_are_rejected(self):
        for count in (5,6):
            vertices={f"v{i}":(i%3,i//3,0) for i in range(count)}
            with self.subTest(count=count), self.assertRaisesRegex(ValueError,"three or four"):
                MeshGeometry.create(vertices,{"surface":tuple(vertices)})
        with self.assertRaisesRegex(ValueError,"collinear corner"):
            MeshGeometry.create({"a":(0,0,0),"b":(1,0,0),"c":(2,0,0),"d":(0,2,0)},
                                {"surface":("a","b","c","d")})
        with self.assertRaisesRegex(ValueError,"convex triangle or quad"):
            MeshGeometry.create({"a":(0,0,0),"b":(2,0,0),"c":(1,.5,0),"d":(0,2,0)},
                                {"surface":("a","b","c","d")})

    def test_radial_primitive_matrix_is_quad_only(self):
        factories = (
            lambda axis,segments,style: cylinder(radius=2,height=4,segments=segments,axis=axis,start_cap=style,end_cap=style),
            lambda axis,segments,style: prism(radius=2,height=4,sides=segments,axis=axis,start_cap=style,end_cap=style),
            lambda axis,segments,style: frustum(bottom_radius=2,top_radius=1,height=4,segments=segments,axis=axis,start_cap=style,end_cap=style),
        )
        for axis in "XYZ":
            for segments in (4,6,8,10,12,14):
                for style in ("flat","inset","open"):
                    for factory in factories:
                        with self.subTest(axis=axis,segments=segments,style=style,factory=factory):
                            geometry=factory(axis,segments,style)
                            assert_quad_only(self,geometry.faces.values())
                            self.assertEqual(len(geometry.faces),len(set(geometry.faces)))
                            errors,warnings=validate_geometry(geometry)
                            self.assertEqual(errors,[])
                            if style != "open":
                                self.assertEqual(warnings,[])

    def test_uv_validates_even_disabled_mesh_faces(self):
        data={"meta":{"model_format":"free"},"elements":[{
            "type":"mesh","name":"bad","vertices":{"a":[0,0,0],"b":[1,0,0],"c":[0,1,0]},
            "faces":{"hidden":{"vertices":["a","b","c","d","e"],"texture":None}}}]}
        with self.assertRaisesRegex(ValueError,"three or four"):
            BoxUVPacker.pack_document(data)

    def test_uv_layout_accepts_and_preserves_triangle_vertex_order(self):
        data={"meta":{"model_format":"free"},"elements":[{
            "type":"mesh", "name":"tip", "origin":[0,0,0],
            "vertices":{"a":[0,0,0],"b":[3,0,0],"c":[0,2,0]},
            "faces":{"surface":{"vertices":["a","b","c"]}},
            "model_as_code_mesh":{"closed":False}}]}
        packed, _, _ = BoxUVPacker.pack_document(data, uv_scale=2)
        face=packed["elements"][0]["faces"]["surface"]
        self.assertEqual(list(face["uv"]), face["vertices"])
        self.assertEqual(len(face["uv"]), 3)

    def test_uv_sphere_extreme_anchors_match_actual_geometry(self):
        for axis,index in (("X",0),("Y",1),("Z",2)):
            geometry=uv_sphere(radius=3,segments=8,rings=4,axis=axis)
            coordinates=[point[index] for point in geometry.vertices.values()]
            self.assertAlmostEqual(geometry.anchors["base"][index],min(coordinates))
            self.assertAlmostEqual(geometry.anchors["top"][index],max(coordinates))

    def test_radial_caps_are_quad_patches(self):
        for segments in (6,8,10,12,14):
            with self.subTest(segments=segments):
                geometry=cylinder(radius=2,height=4,segments=segments)
                self.assertEqual(sum(f.group=="cap_bottom" for f in geometry.faces.values()),segments//2)
                self.assertEqual(sum(f.group=="cap_top" for f in geometry.faces.values()),segments//2)
                assert_quad_only(self,geometry.faces.values())
        compound=cylinder(radius=2,height=4,segments=10,
                          start_cap=CapSpec.inset_ring(.4),end_cap=CapSpec.inset_ring(.4))
        self.assertEqual(sum(face.group=="cap_bottom" for face in compound.faces.values()),15)
        assert_quad_only(self,compound.faces.values())
        distinct=cylinder(radius=2,height=4,segments=8,start_cap="open",end_cap="inset")
        self.assertFalse(any(face.group=="cap_bottom" for face in distinct.faces.values()))
        self.assertTrue(any(face.group=="cap_top" for face in distinct.faces.values()))

    def test_point_primitives_use_intentional_triangles_and_spheres_remain_quad(self):
        builder=ModelBuilder("forms",require_integer_dimensions=False).add_group("root")
        builder.add_cone("cone","root",radius=2,height=4,segments=6)
        builder.add_pyramid("pyramid", "root", base_width=4, base_depth=3, height=4,
                            placement=Placement.at((6,0,0)))
        builder.add_uv_sphere("uv","root",radius=2,segments=8,rings=4,placement=Placement.at((12,0,0)))
        builder.add_quad_sphere("quad","root",radius=2,subdivisions=2,placement=Placement.at((18,0,0)))
        self.assertTrue(all(len(face["vertices"]) == 3 for face in builder._elements[0].faces.values()
                            if face.get("model_as_code_group") == "side"))
        self.assertTrue(all(len(face["vertices"]) == 3 for face in builder._elements[1].faces.values()
                            if face.get("model_as_code_group") == "side"))
        for element in builder._elements[2:]: assert_quad_only(self,element.faces.values())
        self.assertEqual(builder.validate()["errors"],[])

    def test_triangle_and_pyramid_factories_are_semantic_and_valid(self):
        explicit=triangle(points=((0,0,0),(2,0,0),(0,2,0)))
        self.assertEqual(explicit.primitive,"triangle")
        self.assertEqual(len(explicit.faces["surface"].vertices),3)
        form=pyramid(base_width=4,base_depth=2,height=5)
        self.assertEqual(form.primitive,"pyramid")
        self.assertTrue(all(len(face.vertices) in (3,4) for face in form.faces.values()))
        self.assertTrue(all(len(face.vertices) == 3 for face in form.faces.values() if face.group=="side"))
        self.assertEqual(validate_geometry(form)[0],[])

    def test_procedural_algorithms_never_create_triangles(self):
        profile=Profile.polygon(((2,0),(1,1),(-1,1),(-2,0),(-1,-1),(1,-1)))
        shapes=(loft((Section("a",profile),Section("b",profile.scale(.7),Frame(origin=(0,0,3))))),
                sweep(profile,Path3D.line((0,0,0),(0,0,4),samples=3),x_hint=(1,0,0)),
                revolve(((1,0),(2,1),(1,3)),segments=8))
        for shape in shapes:
            assert_quad_only(self,shape.build().faces.values())
            self.assertEqual(shape.validate()["errors"],[])
        with self.assertRaisesRegex(ValueError,"singular poles"): revolve(((0,0),(2,1),(1,3)),segments=8)
        with self.assertRaisesRegex(ValueError,"four"): Profile.polygon(((0,0),(1,0),(0,1)))


    def test_final_validation_detects_intramesh_intersection(self):
        builder=ModelBuilder("cross",require_integer_dimensions=False).add_group("root")
        builder.add_mesh("crossed","root",MeshGeometry.create({
            "a":(-2,0,0),"b":(2,0,0),"c":(2,2,0),"d":(-2,2,0),
            "e":(0,-1,-1),"f":(0,3,-1),"g":(0,3,1),"h":(0,-1,1)},
            {"horizontal":("a","b","c","d"),"vertical":("e","f","g","h")}))
        self.assertTrue(any("Self-intersection" in error for error in builder.validate()["errors"]))

    def test_export_import_uv_and_painter_preserve_quad(self):
        builder=ModelBuilder("pipeline",require_integer_dimensions=False).add_group("root")
        builder.add_quad_face("leaf","root",((0,0,0),(3,0,0),(4,3,0),(0,2,0)))
        builder.rotate_element("leaf",(15,30,45))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"model.bbmodel"; builder.export_bbmodel(path)
            loaded=ModelBuilder.from_bbmodel(path)
            self.assertEqual(loaded._elements[0].rotation,(15.,30.,45.))
            self.assertEqual(len(loaded._elements[0].faces["surface"]["vertices"]),4)
            BoxUVPacker.apply_to_bbmodel(path,uv_scale=2,require_integer_uvs=False)
            painter=TexturePainter.from_bbmodel(path); painter.leaf.surface.fill("#336633")
            painter.save(Path(folder)/"texture.png")
            face=json.loads(path.read_text(encoding="utf-8"))["elements"][0]["faces"]["surface"]
            self.assertEqual(len(face["vertices"]),4)
            self.assertEqual(set(face["uv"]),set(face["vertices"]))

    def test_align_anchor_after_element_and_bone_rotation(self):
        builder=ModelBuilder("align",require_integer_dimensions=False)
        builder.add_transform_group("root",pivot=(0,0,0),rotation=(0,0,30)).add_transform_group("child","root",pivot=(2,1,0),rotation=(0,0,45))
        builder.add_cylinder("part","child",radius=1,height=2); builder.rotate_element("part",(0,0,90))
        target=(7.,5.,2.); builder.align_element("part","base",target); element=builder._elements[0]
        local=tuple(element.origin[i]+element.anchors["base"][i] for i in range(3))
        actual=world_point(builder,element,local)
        for got,want in zip(actual,target): self.assertAlmostEqual(got,want,places=6)


if __name__ == "__main__": unittest.main()


class DraftAsSavedTests(unittest.TestCase):
    def draft(self, closed):
        draft = MeshDraft(closed=closed)
        for name, point in {"a": (0, 0, 0), "b": (1, 0, 0), "c": (1, 1, 0), "d": (0, 1, 0),
                            "e": (0, 0, 1), "f": (1, 0, 1), "g": (1, 1, 1), "h": (0, 1, 1)}.items():
            draft.vertex(name, point)
        for name, order in {"bottom": "bcda", "top": "hgfe", "front": "efba", "back": "cghd",
                            "left": "dhea", "right": "fgcb"}.items():
            draft.face(name, tuple(order))   # every face wound inward
        return draft

    def faces(self, closed, **kwargs):
        builder = ModelBuilder("t", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_mesh("m", "root", self.draft(closed), **kwargs)
        element = next(e for e in builder.to_bbmodel_data()["elements"] if e["name"] == "m")
        return {k: tuple(f["vertices"]) for k, f in element["faces"].items()}


    def test_a_closed_draft_is_oriented_outward_by_default(self):
        self.assertNotEqual(self.faces(True)["bottom"], tuple("bcda"))

    def test_ring_of_registers_existing_vertices_and_rejects_unknown_ones(self):
        draft = self.draft(True)
        self.assertEqual(draft.ring_of("base", "abcd"), tuple("abcd"))
        self.assertEqual(draft.rings["base"], tuple("abcd"))
        with self.assertRaises(ValueError):
            draft.ring_of("bad", ("a", "b", "zzz"))
