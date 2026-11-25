import copy
import json
import math
from pathlib import Path
import tempfile
import unittest

from Tools.uv_packer import BoxUVPacker
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.core.bbmodel_parser import BlockbenchModelParser
from Tools.TexturePainter.core.polygon_face_canvas import polygon_mask
from uv_assertions import uv_state


def document():
    return {'meta': {'model_format': 'free'}, 'elements': [{
        'name': 'thin', 'uuid': 'thin', 'type': 'mesh', 'model_as_code_mesh': {'version': 1},
        'vertices': {'a': [0,0,0], 'b': [10,0,0], 'c': [1,.1,0], 'd': [0,.1,0]},
        'faces': {'surface': {'vertices': ['a','b','c','d']}}}]}


class FractionalUVTests(unittest.TestCase):
    def mapped(self):
        return BoxUVPacker.pack_document(document(), require_integer_uvs=False, island_padding=2)[0]

    def test_fractional_preserves_shape_and_aligns_center(self):
        source = document()
        with self.assertRaisesRegex(ValueError, r'collapses.*--uv-scale.*--no-require-integer-uvs'):
            BoxUVPacker.pack_document(source)
        result = self.mapped()
        self.assertEqual(source['elements'][0]['vertices'], result['elements'][0]['vertices'])
        uv = result['elements'][0]['faces']['surface']['uv']
        for axis in (0,1):
            values = [p[axis] for p in uv.values()]
            self.assertAlmostEqual(min(values)+max(values), round(min(values)+max(values)))
        for a,b in (('a','b'),('b','c'),('c','d'),('d','a')):
            self.assertAlmostEqual(math.dist(uv[a],uv[b]), math.dist(source['elements'][0]['vertices'][a],source['elements'][0]['vertices'][b]))
        again = BoxUVPacker.pack_document(result)[0]
        self.assertEqual(result, again)

    def test_positive_area_coverage_without_boundary_only_pixels(self):
        points = ((0,.45),(10,.45),(1,.55),(0,.55))
        self.assertIsNotNone(polygon_mask(10,1,points,True).getbbox())
        rectangle = polygon_mask(2,1,((0,0),(1,0),(1,1),(0,1)),True)
        self.assertEqual([rectangle.getpixel((x,0)) for x in range(2)], [255,0])

    def test_save_and_register_preserve_fractional_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'model.bbmodel'
            data = self.mapped()
            path.write_text(json.dumps(data),encoding='utf-8')
            painter = TexturePainter.from_bbmodel(path)
            painter.thin.fill_all('#236b39')
            painter.save(Path(directory)/'texture.png', edge_dilation=2)
            after = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['elements'][0]['faces']['surface']['uv'], after['elements'][0]['faces']['surface']['uv'])
            self.assertEqual(uv_state(data), uv_state(after))

    def test_fractional_shared_layout_and_incompatible_shape(self):
        data = document()
        other = copy.deepcopy(data['elements'][0])
        other['name'] = other['uuid'] = 'copy'
        data['elements'].append(other)
        data['unhandled_root_fields'] = {'model_as_code': {'uv_sharing': [
            {'target': ['copy','surface'], 'source': ['thin','surface']}]}}
        result = BoxUVPacker.pack_document(data, require_integer_uvs=False)[0]
        BlockbenchModelParser.from_document(result)
        self.assertEqual(result['elements'][0]['faces']['surface']['uv'],result['elements'][1]['faces']['surface']['uv'])
        data['elements'][1]['vertices']['c'][0] += .01
        with self.assertRaisesRegex(ValueError, 'shape'):
            BoxUVPacker.pack_document(data, require_integer_uvs=False)

    def test_invalid_policy_center_and_overlapping_coverage_rejected(self):
        with self.assertRaisesRegex(ValueError,'boolean'):
            BoxUVPacker.pack_document(document(),require_integer_uvs='false')
        data = self.mapped()
        for p in data['elements'][0]['faces']['surface']['uv'].values():
            p[0] += .1
        with self.assertRaisesRegex(ValueError,'center'):
            BlockbenchModelParser.from_document(data)
        data = self.mapped()
        other = copy.deepcopy(data['elements'][0])
        other['name'] = other['uuid'] = 'copy'
        data['elements'].append(other)
        with self.assertRaisesRegex(ValueError,'overlap'):
            BlockbenchModelParser.from_document(data)

    def test_box_dimensions_still_restricted_in_fractional_mode(self):
        data = {'meta': {'model_format':'free'},'elements': [
            {'type':'cube','name':'box','from':[0,0,0],'to':[1.2,2,3]}]}
        with self.assertRaisesRegex(ValueError,'integer'):
            BoxUVPacker.pack_document(data,require_integer_uvs=False)
        data['elements'][0]['to'][0] = 1
        integer = BoxUVPacker.pack_document(data)[0]
        fractional = BoxUVPacker.pack_document(data,require_integer_uvs=False)[0]
        self.assertEqual(integer['elements'], fractional['elements'])


if __name__ == '__main__':
    unittest.main()
