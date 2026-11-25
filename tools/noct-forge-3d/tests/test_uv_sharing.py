import copy
import json
import tempfile
import unittest
from pathlib import Path

from lib import ModelBuilder
from Tools.uv_builder import UVBuilder
from Tools.uv_packer import BoxUVPacker
from Tools.TexturePainter import TexturePainter


class SharingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'model.bbmodel'
        b = ModelBuilder('leaves').add_group('root')
        b.add_axis_quad('owner', 'root', from_=(0,0,0), size=(2,3), normal='+Z')
        b.add_axis_quad('follower', 'root', from_=(5,0,0), size=(2,3), normal='+Z')
        b.add_cube('cube', 'root', from_=(10,0,0), to_=(12,3,2))
        b.export_bbmodel(self.path)

    def read(self):
        return json.loads(self.path.read_text())

    def plan(self):
        return UVBuilder(self.path).clear_sharing().share_uv(('follower','quad'), source=('owner','quad'))

    def test_shared_paint_and_rerun(self):
        before = self.read()
        self.plan().save()
        data = self.read()
        for a,b in zip(before['elements'], data['elements']):
            for key in ('from','to','vertices','origin','rotation'):
                self.assertEqual(a.get(key),b.get(key))
        self.assertEqual(data, BoxUVPacker.pack_document(data)[0])
        p = TexturePainter(self.path)
        self.assertEqual(p.follower.quad.owner, ('owner','quad'))
        with self.assertRaisesRegex(ValueError, 'paint owner'):
            p.follower.quad.fill('#00ff00')
        p.owner.quad.fill('#ff0000')
        p.cube.fill_all('#0000ff')
        p.save(self.path.with_suffix('.png'))
        region = p.owner.quad.uv_info
        self.assertEqual(p.compose_atlas().getpixel((region['x'],region['y'])), (255,0,0,255))
        self.plan().save()
        self.assertEqual(len(self.read()['unhandled_root_fields']['model_as_code']['uv_sharing']),1)

    def test_cube_face_can_share_with_quad(self):
        self.plan().share_uv(('cube','north'), source=('owner','quad')).save()
        p = TexturePainter(self.path)
        self.assertEqual(p.cube.north.owner, ('owner','quad'))
        self.assertFalse(p.cube.south.uv_info['owner'])

    def test_invalid_plans_do_not_write(self):
        cases = [
            [(('owner','quad'),('owner','quad'))],
            [(('missing','quad'),('owner','quad'))],
            [(('cube','up'),('owner','quad'))],
            [(('follower','quad'),('owner','quad')), (('owner','quad'),('cube','north'))],
            [(('follower','quad'),('owner','quad')), (('follower','quad'),('owner','quad'))],
        ]
        before = self.path.read_bytes()
        for links in cases:
            uv = UVBuilder(self.path).clear_sharing()
            for target, source in links:
                uv.share_uv(target, source=source)
            with self.assertRaises(ValueError):
                uv.save()
            self.assertEqual(self.path.read_bytes(),before)

    def test_tampered_overlap_or_dimensions_rejected(self):
        self.plan().save()
        valid = self.read()
        for change in ('unlink','offset','resize'):
            data=copy.deepcopy(valid)
            if change == 'unlink':
                data['unhandled_root_fields']['model_as_code']['uv_sharing']=[]
            elif change == 'offset':
                for p in data['elements'][1]['faces']['quad']['uv'].values():
                    p[0]+=1
            else:
                for p in data['elements'][1]['vertices'].values():
                    p[0]*=2
            self.path.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                TexturePainter(self.path)

    def test_uv_recipe_rejects_concurrent_changes(self):
        uv=self.plan()
        data=self.read()
        data['name']='edited'
        self.path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'Model changed'):
            uv.save()

    def test_whole_cube_explicit_links_and_no_inference(self):
        b=ModelBuilder('boxes').add_group('root')
        b.add_cube('a','root',from_=(0,0,0),to_=(2,3,4))
        b.add_cube('b','root',from_=(10,0,0),to_=(12,3,4))
        b.export_bbmodel(self.path)
        UVBuilder(self.path, uv_scale=3).save()
        exclusive=self.read()
        self.assertNotEqual(exclusive['elements'][0]['faces']['north']['uv'],exclusive['elements'][1]['faces']['north']['uv'])
        uv=UVBuilder(self.path).clear_sharing()
        for face in ('north','south','east','west','up','down'):
            uv.share_uv(('b',face),source=('a',face))
        uv.save()
        shared=self.read()
        for face in shared['elements'][0]['faces']:
            self.assertEqual(shared['elements'][0]['faces'][face]['uv'],shared['elements'][1]['faces'][face]['uv'])
        p=TexturePainter(self.path)
        self.assertEqual((p.a.north.width,p.a.north.height),(6,9))
        p.a.fill_all('#123456')
        p.save(self.path.with_suffix('.png'))

    def test_recipe_sources_compile_and_geometry_calls_have_no_uv_options(self):
        import ast
        root=Path(__file__).resolve().parents[1]
        for recipe in (root/'projects').glob('*/scripts/*/generate_model.py'):
            source=recipe.read_text(encoding='utf-8-sig')
            tree=ast.parse(source)
            compile(tree,str(recipe),'exec')
            for call in ast.walk(tree):
                if isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='ModelBuilder':
                    self.assertEqual(len(call.args) <= 1, True, str(recipe))
                    self.assertFalse({'uv_scale','texture_size','fixed_texture_size','allow_rectangular'} & {k.arg for k in call.keywords}, str(recipe))
            uv=recipe.with_name('generate_uv.py')
            if uv.exists():
                compile(uv.read_text(encoding='utf-8-sig'),str(uv),'exec')


class MirrorSharingTests(unittest.TestCase):
    """share_uv(mirror=True): a left/right pair reuses one island reflected."""
    POINTS = {"a": (0, 0, 0), "b": (4, 0, 0), "c": (3, 2, 0), "d": (0.5, 3, 0)}

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'model.bbmodel'

    def read(self):
        return json.loads(self.path.read_text())

    def build(self, mirrored=True, integer=True):
        from lib.geometry_types import MeshFace, MeshGeometry
        b = ModelBuilder('pair', require_integer_dimensions=False).add_group('root')
        b.add_mesh('left', 'root', MeshGeometry.create(self.POINTS, {'surface': MeshFace(('a', 'b', 'c', 'd'))}),
                   origin=(2, 0, 0))
        if mirrored:   # reflect x and reverse winding so the face still points outward
            points = {k: (-x, y, z) for k, (x, y, z) in self.POINTS.items()}
            faces = {'surface': MeshFace(('d', 'c', 'b', 'a'))}
        else:
            points, faces = self.POINTS, {'surface': MeshFace(('a', 'b', 'c', 'd'))}
        b.add_mesh('right', 'root', MeshGeometry.create(points, faces), origin=(-2, 0, 0))
        b.add_cube('cube_l', 'root', from_=(0, 4, 0), to_=(2, 7, 1))
        b.add_cube('cube_r', 'root', from_=(-2, 4, 0), to_=(0, 7, 1))
        b.export_bbmodel(self.path)
        options = dict(uv_scale=4, island_padding=1, require_integer_uvs=integer)
        return UVBuilder(self.path, **options).clear_sharing().share_uv(
            ('right', 'surface'), source=('left', 'surface'), mirror=True)

    def test_mesh_follower_reuses_reflected_owner_points(self):
        for integer in (True, False):
            with self.subTest(integer=integer):
                self.build(integer=integer).save()
                data = self.read()
                elements = {e['name']: e for e in data['elements']}
                left, right = elements['left'], elements['right']
                link = data['unhandled_root_fields']['model_as_code']['uv_sharing'][0]
                self.assertIs(link['mirror'], True)
                for key, point in right['faces']['surface']['uv'].items():
                    owner_key = next(k for k, p in left['faces']['surface']['uv'].items() if p == point)
                    # The follower vertex sits where the reflected owner vertex is.
                    x, y, z = right['vertices'][key]
                    self.assertEqual([-x, y, z], left['vertices'][owner_key])
                p = TexturePainter(self.path)
                self.assertEqual(p.right.surface.owner, ('left', 'surface'))
                p.left.surface.fill('#ff0000')
                p.save(self.path.with_suffix('.png'))
                self.assertEqual(data, BoxUVPacker.pack_document(data)[0])

    def test_cube_follower_is_flipped_rectangle(self):
        uv = self.build().share_uv(('cube_r', 'north'), source=('cube_l', 'north'), mirror=True)
        uv.save()
        elements = {e['name']: e for e in self.read()['elements']}
        u1, v1, u2, v2 = elements['cube_l']['faces']['north']['uv']
        self.assertEqual(elements['cube_r']['faces']['north']['uv'], [u2, v1, u1, v2])
        self.assertTrue(TexturePainter(self.path).cube_r.north.uv_info['flip_x'])

    def test_non_reflected_shape_is_rejected(self):
        uv = self.build(mirrored=False)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'mirror shape differs'):
            uv.save()
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'boolean'):
            uv.share_uv(('cube_r', 'up'), source=('cube_l', 'up'), mirror='yes')

    def test_tampered_mirror_is_rejected(self):
        self.build().save()
        data = self.read()
        face = next(e for e in data['elements'] if e['name'] == 'right')['faces']['surface']
        keys = list(face['uv'])
        face['uv'][keys[0]], face['uv'][keys[1]] = face['uv'][keys[1]], face['uv'][keys[0]]
        self.path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Mirrored UV layout differs'):
            TexturePainter(self.path)


class FilterPaddingWarningTests(unittest.TestCase):
    def test_warns_only_for_linear_below_minimum(self):
        from Tools.uv_contract import LINEAR_MIN_PADDING, filter_padding_warning

        def data(padding):
            return {'unhandled_root_fields': {'model_as_code': {'uv_packing': {'island_padding': padding}}}}
        self.assertRegex(filter_padding_warning('linear', data(2)), f'island_padding >= {LINEAR_MIN_PADDING}')
        self.assertIsNone(filter_padding_warning('linear', data(LINEAR_MIN_PADDING)))
        self.assertIsNone(filter_padding_warning('nearest', data(0)))
