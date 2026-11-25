"""A UV chart may hold more faces than texels (a fan of thin triangles meeting at a crest's tip): the faces left
without a texel own nothing, and the model still packs, parses and paints (the pigeon's crest failed with "UV bounds
center must align to half pixels")."""
import math
import tempfile
import unittest
from pathlib import Path

import numpy as np

from lib import ModelBuilder
from lib.geometry_types import MeshFace, MeshGeometry
from Tools.TexturePainter import TexturePainter
from Tools.uv_builder import UVBuilder


def fan_model(path, segments=16, radius=0.1):
    """A flat fan of ``segments`` thin triangles round a centre, all inside a texel or two at density 8."""
    verts = {"c": (0.0, 0.0, 0.0)}
    for k in range(segments):
        a = 2 * math.pi * k / segments
        verts[f"r{k}"] = (radius * math.cos(a), radius * math.sin(a), 0.0)
    faces = {f"t{k}": MeshFace(("c", f"r{k}", f"r{(k + 1) % segments}"), "fan") for k in range(segments)}
    builder = ModelBuilder("fan", require_integer_dimensions=False).add_group("root")
    builder.add_mesh("fan", "root", MeshGeometry.create(verts, faces), allow_triangles=True)
    builder.export_bbmodel(path)


class ChartSliverTests(unittest.TestCase):
    def test_a_fan_with_more_faces_than_texels_packs_and_paints(self):
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "model.bbmodel"
            fan_model(model)
            UVBuilder(model, start_size=(32, 32), uv_scale=8, island_padding=1, layout="charts",
                      require_integer_uvs=False).save()
            painter = TexturePainter.from_bbmodel(model)
            faces = painter.parser.elements["fan"]["faces"]
            owned = {name: int(np.asarray(info["owned_mask"]).sum()) for name, info in faces.items()}
            self.assertEqual(len(owned), 16)                     # every face is still a chart face
            self.assertTrue(any(count == 0 for count in owned.values()))
            self.assertGreater(sum(owned.values()), 0)
            painter.fill_all((200, 10, 10, 255))
            atlas = np.asarray(painter.compose_atlas())
            self.assertEqual(int((atlas[..., 0] == 200).sum()), sum(owned.values()))


if __name__ == "__main__":
    unittest.main()
