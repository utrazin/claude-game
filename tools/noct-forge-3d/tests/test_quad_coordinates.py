from Tools.uv_builder import UVBuilder
import json
import tempfile
import unittest
from pathlib import Path
from lib.model_builder import ModelBuilder


class QuadCoordinateTests(unittest.TestCase):
    def test_mesh_origin_is_applied_exactly_once_for_every_normal(self):
        for normal in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
            with self.subTest(normal=normal), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "model.bbmodel"
                b = ModelBuilder("quad").add_group("root")
                b.add_axis_quad("detail", "root", from_=(4, 20, -2.2), size=(3, 2), normal=normal)
                b.export_bbmodel(path)
                UVBuilder(path, start_size=(16, 16)).save()
                e = json.loads(path.read_text())["elements"][0]
                world = [[v[i] + e["origin"][i] for i in range(3)] for v in e["vertices"].values()]
                lo = [min(v[i] for v in world) for i in range(3)]
                hi = [max(v[i] for v in world) for i in range(3)]
                self.assertEqual(lo, [4, 20, -2.2])
                expected = { "X": [4, 22, 0.8], "Y": [7, 20, -0.2], "Z": [7, 22, -2.2]}[normal[-1]]
                for actual, wanted in zip(hi, expected):
                    self.assertAlmostEqual(actual, wanted)


if __name__ == "__main__":
    unittest.main()
