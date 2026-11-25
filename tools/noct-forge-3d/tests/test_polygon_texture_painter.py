import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from lib import ModelBuilder, Placement
from lib.geometry_types import MeshFace, MeshGeometry
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.core.polygon_face_canvas import PolygonFaceCanvas
from uv_assertions import uv_state
from Tools.uv_builder import UVBuilder


class PolygonTexturePainterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = Path(self.temp.name) / "model.bbmodel"
        self.png = Path(self.temp.name) / "texture.png"
        builder = ModelBuilder("polygon-paint", require_integer_dimensions=False).add_group("root")
        points = ((0, 0, 0), (4, 0, 0), (3, 2, 0), (1, 3, 0))
        geometry=MeshGeometry.create({f"v{i}":point for i,point in enumerate(points)},
                                     {"surface":MeshFace(tuple(f"v{i}" for i in range(4)),"foliage")})
        builder.add_mesh("leaf", "root", geometry)
        builder.add_mesh("leaf_copy", "root", geometry,
                         origin=(6,0,0))
        builder.export_bbmodel(self.model)
        UVBuilder(self.model, start_size=(32, 16), uv_scale=2, island_padding=2).share_uv(
            ("leaf_copy", "surface"), source=("leaf", "surface")).save()

    def test_polygon_canvas_clips_all_operations(self):
        canvas = PolygonFaceCanvas(4, 4, ((0, 0), (4, 0), (2, 2), (0, 4)))
        canvas.fill("#224466").draw_rect(0, 0, 4, 4, "#ffffff").apply_gradient("#000000", "#ffffff")
        self.assertEqual(canvas.get_pixel(3, 3), (0, 0, 0, 0))
        self.assertGreater(canvas.get_pixel(0, 0)[3], 0)

    def test_polygon_groups_sharing_and_seeded_noise(self):
        first = TexturePainter.from_bbmodel(self.model)
        self.assertEqual(first.leaf.surface.uv_info["layout"], "polygon")
        first.leaf.group("foliage").fill("#285c2e").apply_noise(12, seed=73)
        image_a = first.compose_atlas()
        second = TexturePainter.from_bbmodel(self.model)
        second.leaf.group("foliage").fill("#285c2e").apply_noise(12, seed=73)
        self.assertEqual(image_a.tobytes(), second.compose_atlas().tobytes())
        with self.assertRaisesRegex(ValueError, "Shared face is not paintable"):
            second.leaf_copy.surface.fill("#ffffff")

    def test_polygon_save_registers_without_uv_mutation(self):
        before = json.loads(self.model.read_text(encoding="utf-8"))
        original_uvs = uv_state(before)
        painter = TexturePainter.from_bbmodel(self.model)
        painter.leaf.group("foliage").fill("#34783d").apply_noise(8, seed=5)
        painter.save(self.png)
        after = json.loads(self.model.read_text(encoding="utf-8"))
        self.assertEqual(original_uvs, uv_state(after))
        with Image.open(self.png) as image:
            self.assertEqual(image.size, (32, 16))

    def test_padding_and_edge_dilation_cover_polygon_gutter(self):
        painter = TexturePainter.from_bbmodel(self.model)
        painter.leaf.surface.fill("#34783d")
        plain = painter.compose_atlas(edge_dilation=0)
        dilated = painter.compose_atlas(edge_dilation=2)
        plain_coverage = plain.width * plain.height - plain.getchannel("A").histogram()[0]
        dilated_coverage = dilated.width * dilated.height - dilated.getchannel("A").histogram()[0]
        self.assertGreater(dilated_coverage, plain_coverage)
        self.assertEqual(painter.parser.island_padding, 2)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            painter.compose_atlas(edge_dilation=3)


if __name__ == "__main__":
    unittest.main()
