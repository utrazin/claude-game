import copy
import json
from pathlib import Path
import tempfile
import unittest

from lib import (ModelBuilder, MeshDraft, MeshGeometry, Placement, Frame,
                 Profile, Section, Path3D, linear_falloff, smooth_falloff)
from lib.geometry_types import MeshFace
from lib.procedural import loft, revolve, sweep
from lib.mesh_validation import validate_geometry
from lib.primitives import cylinder
from Tools.uv_builder import UVBuilder


def block():
    p=Profile.rectangle(4,4)
    return loft([Section('lower',p),Section('upper',p,Frame(origin=(0,0,4)))])


class ProceduralTests(unittest.TestCase):
    def test_frames_and_section_values(self):
        f=Frame.from_normal((2,3,4),normal=(0,1,0),x_hint=(1,0,0))
        self.assertEqual(f.local(f.point((1,2,3))),(1,2,3))
        with self.assertRaises(ValueError): Frame(x=(2,0,0))
        with self.assertRaises(ValueError): Frame.from_normal(normal=(1,0,0),x_hint=(1,0,0))
        a=Section('a',Profile.rectangle(4,2),f)
        b=a.scale(2).offset((0,0,3)).rotate(30)
        self.assertEqual(a.profile,Profile.rectangle(4,2))
        self.assertNotEqual(a,b)

    def test_profile_offsets_and_resampling(self):
        p=Profile.rectangle(4,2)
        self.assertEqual(p.expand(1),Profile.rectangle(6,4))
        with self.assertRaises(ValueError): p.expand(-2)
        self.assertEqual(p.resample(12).points[0],p.points[0])
        self.assertEqual(len(Profile.rounded_rectangle(4,3,.4,corner_segments=2).points),12)
        for points in (((0,0),(2,2),(0,2),(2,0)),((0,0),(1,0),(1,0)),((0,0),(1,0),(2,0))):
            with self.assertRaises(ValueError): Profile.polygon(points)

    def test_loft_quads_and_stable_names(self):
        d=block(); g=d.build()
        self.assertEqual(len(g.faces),6)
        self.assertTrue(all(len(f.vertices)==4 for f in g.faces.values()))
        changed=loft([Section('lower',Profile.rectangle(6,3)),Section('upper',Profile.rectangle(5,2),Frame(origin=(0,0,8)))])
        self.assertEqual(set(d.vertices),set(changed.vertices))
        self.assertEqual(set(d.faces),set(changed.faces))
        self.assertEqual(d.validate()['errors'],[])

    def test_concave_caps_and_count_mismatch(self):
        p=Profile.polygon(((0,0),(3,0),(3,3),(1.5,1),(0,3)))
        with self.assertRaisesRegex(ValueError,'even ring'):
            loft([Section('a',p),Section('b',p,Frame(origin=(0,0,3)))])
        d=loft([Section('a',p),Section('b',p,Frame(origin=(0,0,3)))],
               start_cap="open",end_cap="open")
        self.assertEqual(d.validate()['errors'],[])
        with self.assertRaises(ValueError): loft([Section('a',p),Section('b',Profile.circle(),Frame(origin=(0,0,3)))])

    def test_even_convex_loft_caps_use_symmetric_quad_fans(self):
        p=Profile.polygon(((2,1),(1,2),(-1,2),(-2,1),(-2,-1),(-1,-2),(1,-2),(2,-1)))
        d=loft([Section('lower',p),Section('upper',p.scale(.7),Frame(origin=(0,0,3)))])
        g=d.build()
        for group in ('cap_start','cap_end'):
            faces=[f for f in g.faces.values() if f.group==group]
            self.assertEqual(len(faces),4)
            self.assertTrue(all(len(face.vertices)==4 for face in faces))
        self.assertEqual(d.validate()['errors'],[])

    def test_nonplanar_quad_preserves_authored_quad_topology(self):
        vertices={'a':(-2,0,0),'b':(2,0,0),'c':(1,2,1),'d':(-1,2,0)}
        geometry=MeshGeometry.create(vertices,{'side':('a','b','c','d')})
        self.assertEqual(tuple(geometry.faces),('side',))
        self.assertEqual(geometry.faces['side'].vertices,('a','b','c','d'))
        self.assertEqual(validate_geometry(geometry)[0],[])

    def test_sweep_parallel_transport_and_deformation(self):
        path=Path3D.bezier((0,0,0),(0,0,3),(1,0,5),(2,1,8),samples=6)
        frames=path.frames(x_hint=(1,0,0))
        self.assertEqual(len(frames),6)
        d=sweep(Profile.circle(.5),path,x_hint=(1,0,0),scale=((0,1),(1,.6)),twist=((0,0),(1,25)))
        self.assertEqual(d.validate()['errors'],[])
        self.assertTrue(all(len(face.vertices)==4 for face in d.faces.values()
                            if face.group=='side'))
        self.assertEqual(len(d.rings),6)
        for points in (((0,0,0),(0,0,0),(1,0,0)),((0,0,0),(1,0,0),(.5,0,0))):
            with self.assertRaises(ValueError): Path3D.polyline(points)

    def test_revolve_rejects_poles_and_supports_partial_seam(self):
        for angle in (360,180):
            with self.subTest(angle=angle):
                with self.assertRaisesRegex(ValueError,'singular poles'):
                    revolve(((0,0),(2,1),(1,3),(0,4)),segments=8,angle=angle)
        d=revolve(((1,0),(2,2),(1,3)),angle=180,
                  start_cap="open",end_cap="open")
        self.assertEqual(d.validate()['errors'],[])

    def test_self_intersection_and_valid_shared_edges(self):
        d=MeshDraft()
        for k,p in {'a':(-2,0,0),'b':(2,0,0),'c':(2,3,0),'d':(-2,3,0),
                    'e':(0,-1,-1),'f':(0,4,-1),'g':(0,4,1),'h':(0,-1,1)}.items(): d.vertex(k,p)
        d.face('one',('a','b','c','d')).face('two',('e','f','g','h'))
        with self.assertRaisesRegex(ValueError,'Self-intersection'): d.validate()
        self.assertEqual(block().validate()['errors'],[])

    def test_closed_components_validate_independently(self):
        a=block().build(); vertices=dict(a.vertices); faces=dict(a.faces)
        for k,p in a.vertices.items(): vertices['b'+k]=(p[0]+10,p[1],p[2])
        for k,f in a.faces.items(): faces['b'+k]=MeshFace(tuple('b'+v for v in reversed(f.vertices)))
        errors,_=validate_geometry(MeshGeometry(vertices,faces,True))
        self.assertTrue(errors)

    def test_live_anchor_placement_and_transaction_rollback(self):
        b=ModelBuilder('anchors',require_integer_dimensions=False).add_transform_group('root',pivot=(0,0,0),rotation=(0,0,90))
        b.add_mesh('shape','root',block().build(),placement=Placement.at((0,0,0)).pivot('base'))
        before=b.get_anchor('shape','top')
        b.translate_element('shape',(1,0,0))
        after=b.get_anchor('shape','top')
        self.assertAlmostEqual(after[1]-before[1],1)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'model.bbmodel'; b.export_bbmodel(p); original=p.read_bytes()
            with self.assertRaises(ValueError):
                with b.edit_mesh('shape') as d: d.closed=True; d.faces.clear()
            b.export_bbmodel(p)
            self.assertEqual(p.read_bytes(),original)
        with self.assertRaises(ValueError): b.add_mesh('ambiguous','root',block().build(),origin=(0,0,0),placement=Placement())

    def test_export_uv_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'model.bbmodel'
            b=ModelBuilder('loft',require_integer_dimensions=False).add_group('root')
            b.add_mesh('shape','root',block().build(),rotation=(10,20,30))
            b.export_bbmodel(p); UVBuilder(p,uv_scale=2,island_padding=2).save()
            before=json.loads(p.read_text())
            loaded=ModelBuilder.from_bbmodel(p)
            with loaded.edit_mesh('shape') as d:
                k = next(iter(d.vertices))
                d.vertices[k] = tuple(v + 0.1 for v in d.vertices[k])
            loaded.export_bbmodel(p); pending=json.loads(p.read_text())
            self.assertFalse(pending['unhandled_root_fields']['model_as_code']['uv_ready'])
            self.assertEqual(pending['textures'],[])
            self.assertEqual(before['elements'][0]['uuid'],pending['elements'][0]['uuid'])
            self.assertEqual(before['elements'][0]['rotation'],pending['elements'][0]['rotation'])
            UVBuilder(p,uv_scale=2,island_padding=2).save()

    def test_name_collisions_and_reference_errors(self):
        points={'a':(0,0,0),'b':(2,0,0),'c':(2,2,0),'d':(1,1,0),'e':(0,2,0)}
        with self.assertRaisesRegex(ValueError,'three or four'):
            MeshGeometry.create(points,{'invalid':('a','b','c','d','e')})
        with self.assertRaisesRegex(ValueError,'missing'):
            MeshGeometry.create(points,{'poly':('a','b','unknown','e')})

    def test_connected_vertex_contact_and_coplanar_overlap(self):
        d=MeshDraft()
        for k,p in {'a':(0,0,0),'b':(2,0,0),'c':(2,2,0),'d':(0,2,0),
                    'e':(1,0,0),'f':(3,0,0),'g':(3,2,0),'h':(1,2,0)}.items(): d.vertex(k,p)
        d.face('one',('a','b','c','d')).face('two',('e','f','g','h'))
        with self.assertRaisesRegex(ValueError,'Self-intersection'): d.validate()
        # A disconnected vertex fan is invalid even when the surfaces only touch at that vertex.
        d=MeshDraft()
        for k,p in {'a':(0,0,0),'b':(2,0,0),'c':(2,2,0),'d':(0,2,0),
                    'e':(0,0,2),'f':(-2,0,2),'g':(-2,0,0)}.items(): d.vertex(k,p)
        d.face('one',('a','b','c','d')).face('two',('a','e','f','g'))
        with self.assertRaisesRegex(ValueError,'Non-manifold vertex'): d.validate()

    def test_invalid_sweep_tables_and_self_intersecting_path_geometry(self):
        path=Path3D.line((0,0,0),(0,0,5),samples=3)
        for table in (((.2,1),(1,1)),((0,1),(.5,-1),(1,1)),((0,1),(0,1),(1,1))):
            with self.assertRaises(ValueError): sweep(Profile.circle(),path,x_hint=(1,0,0),scale=table)
        crossing=Path3D.polyline(((0,0,0),(4,0,0),(4,4,0),(0,4,0),(0,-2,0)))
        with self.assertRaisesRegex(ValueError,'Self-intersection'):
            sweep(Profile.circle(.5),crossing,x_hint=(0,0,1))


if __name__=='__main__': unittest.main()
