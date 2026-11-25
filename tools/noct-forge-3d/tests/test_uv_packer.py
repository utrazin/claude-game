import json
import tempfile
import unittest
from pathlib import Path

from Tools.uv_packer import BoxUVItem, BoxUVPacker, MaxRectsPacker


class UVPackerTests(unittest.TestCase):
    def test_item_padding_reserves_gutter_without_changing_content_size(self):
        item = BoxUVItem(name="leaf", dx=4, dy=3, dz=0, is_quad=True, padding=2)
        self.assertEqual((item.width, item.height), (8, 7))
        self.assertEqual(item.get_face_uvs()["quad"], [2, 2, 6, 5])

    def test_box_uv_footprint(self):
        # Cube of 4x12x2
        # Width: 2 * (dx + dz) = 2 * (4 + 2) = 12
        # Height: dz + dy = 2 + 12 = 14
        item = BoxUVItem(name="limb", dx=4, dy=12, dz=2)
        self.assertEqual(item.width, 12)
        self.assertEqual(item.height, 14)
        self.assertEqual(item.area, 168)

        # Faces calculation when placed at (10, 20)
        item.u = 10
        item.v = 20
        faces = item.get_face_uvs()
        # up: [u + dz, v, u + dz + dx, v + dz] -> [12, 20, 16, 22]
        self.assertEqual(faces["up"], [16, 22, 12, 20])
        self.assertEqual(faces["down"], [20, 20, 16, 22])
        # north: [u + dz, v + dz, u + dz + dx, v + dz + dy] -> [12, 22, 16, 34]
        self.assertEqual(faces["north"], [12, 22, 16, 34])

    def test_pack_small_model_fits_32x32(self):
        # Two small cubes: 4x4x4 (footprint: 16x8, area: 128)
        items = [
            BoxUVItem(name="head", dx=4, dy=4, dz=4),
            BoxUVItem(name="body", dx=4, dy=4, dz=4),
        ]
        size, packed, stats = BoxUVPacker.pack(items, start_size=32)
        self.assertEqual(size, 32)
        self.assertEqual(len(packed), 2)
        self.assertGreater(stats["efficiency_percent"], 0)

    def test_pack_automatic_pot_scaling(self):
        # Create cubes that cannot fit in 32x32 (e.g. total area > 32*32=1024)
        # 8 cubes of 8x8x8: each footprint is 2*(8+8)=32 wide, 8+8=16 high (area 512 each).
        # Total area = 4096 px. Fits in 64x64 (4096 px) or 128x128.
        items = [
            BoxUVItem(name=f"cube_{i}", dx=8, dy=8, dz=8)
            for i in range(5)
        ]
        # 5 cubes * 512 = 2560 px -> Exceeds 32x32 (1024 px), must scale to 64x64 (4096 px)
        size, packed, stats = BoxUVPacker.pack(items, start_size=32)
        self.assertEqual(size, 64)
        self.assertEqual(len(packed), 5)
        self.assertTrue(stats["efficiency_percent"] > 50.0)

    def test_zero_overlap_guarantee(self):
        # 20 diverse cubes
        items = [
            BoxUVItem(name=f"cube_{i}", dx=(i % 5) + 2, dy=(i % 7) + 2, dz=(i % 3) + 2)
            for i in range(20)
        ]
        size, packed, stats = BoxUVPacker.pack(items, start_size=32)

        # Verify no two items have overlapping bounding boxes
        for i in range(len(packed)):
            for j in range(i + 1, len(packed)):
                a, b = packed[i], packed[j]
                overlap = not (
                    a.u + a.width <= b.u
                    or b.u + b.width <= a.u
                    or a.v + a.height <= b.v
                    or b.v + b.height <= a.v
                )
                self.assertFalse(
                    overlap,
                    f"Collision between {a.name} ({a.u},{a.v},{a.width}x{a.height}) and {b.name} ({b.u},{b.v},{b.width}x{b.height})"
                )

    def test_load_and_apply_bbmodel(self):
        with tempfile.TemporaryDirectory() as folder:
            model_file = Path(folder) / "test_model.bbmodel"
            raw_model = {
                "meta": {"box_uv": True},
                "resolution": {"width": 16, "height": 16},
                "elements": [
                    {"name": "head", "from": [-4, 0, -4], "to": [4, 8, 4]},
                    {"name": "body", "from": [-4, 8, -2], "to": [4, 20, 2]},
                    {"name": "arm_left", "from": [4, 8, -2], "to": [8, 20, 2]},
                ],
            }
            model_file.write_text(json.dumps(raw_model), encoding="utf-8")

            # Apply packer
            canvas_size, stats = BoxUVPacker.apply_to_bbmodel(model_file, start_size=32)
            
            # Read back updated model
            updated = json.loads(model_file.read_text(encoding="utf-8"))
            self.assertIn(int(canvas_size), [32, 64, 128])
            self.assertEqual(updated["resolution"], {"width": canvas_size.width, "height": canvas_size.height})
            for elem in updated["elements"]:
                self.assertFalse(elem["box_uv"])
                self.assertEqual(elem["autouv"], 0)
                self.assertIn("uv_offset", elem)
                self.assertEqual(len(elem["uv_offset"]), 2)
                self.assertIn("faces", elem)
                self.assertEqual(len(elem["faces"]), 6)


if __name__ == "__main__":
    unittest.main()
