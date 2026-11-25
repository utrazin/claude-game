import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from Tools.TexturePainter import TexturePainter
from tests.fixtures_projection import SCALE, ramp_model


def image(*columns):
    """A one-row image of solid columns, e.g. image((0, 0, 0), (255, 255, 255)) = black | white."""
    return Image.fromarray(np.array([[list(c) + [255] for c in columns]], dtype=np.uint8), "RGBA")


class SmoothProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.model = ramp_model(Path(self.temp.name) / "model.bbmodel")

    def wall_row(self, painter, y=2.0):
        """(model x * SCALE floor, rgba) of the wall texels in the row at model height ``y``, sorted by x."""
        out = []
        for face, rows in painter.element("ramp")._surface_region()._entries:
            if face.uv_info.get("group") != "wall":
                continue
            centre = np.asarray(rows.fields["_e0"])
            pixels = face.canvas.read_pixels(rows.x, rows.y)
            pick = np.floor(centre[:, 1] * SCALE).astype(int) == int(y * SCALE)
            out += list(zip(np.floor(centre[pick, 0] * SCALE).astype(int).tolist(), pixels[pick].tolist()))
        return sorted(out)

    def painter(self, mode):
        painter = TexturePainter.from_bbmodel(self.model, render=mode)
        painter.fill_all((200, 0, 0, 255))
        return painter

    def test_decal_edges_are_anti_aliased_only_in_smooth_mode(self):
        # decal covering normalized x 0.3..0.7: the left edge falls at model x 1.8 = texel 14.4
        for mode, smooth in (("pixel", False), ("smooth", True)):
            with self.subTest(mode=mode):
                painter = self.painter(mode)
                painter.element("ramp").project_decal(image((0, 0, 0)), center=(0.5, 0.5), size=(0.4, 1.0))
                row = dict(self.wall_row(painter))
                reds = [row[x][0] for x in range(10, 20)]
                self.assertEqual(reds[0], 200)                              # outside: untouched
                self.assertEqual(reds[-1], 0)                               # inside: the decal
                partial = [r for r in reds if 0 < r < 200]
                if smooth:
                    self.assertEqual(len(partial), 1)                        # one anti-aliased texel on the edge
                else:
                    self.assertEqual(partial, [])

    def test_planar_and_triplanar_average_the_image_over_the_texel(self):
        for method in ("project_planar", "project_triplanar"):
            for mode, smooth in (("pixel", False), ("smooth", True)):
                with self.subTest(method=method, mode=mode):
                    painter = self.painter(mode)
                    # tiles of 3.7 model units, black | white: the edge falls at model x 1.85 = texel 14.8
                    getattr(painter.element("ramp"), method)(image((0, 0, 0), (255, 255, 255)), scale=1 / 3.7)
                    row = dict(self.wall_row(painter))
                    reds = [row[x][0] for x in range(10, 20)]
                    grey = [r for r in reds if 0 < r < 255]
                    self.assertEqual(len(grey), 1 if smooth else 0, reds)

    def test_pixel_mode_is_unchanged_by_the_shared_projection_path(self):
        painter = self.painter("pixel")
        painter.element("ramp").project_decal(image((0, 0, 0)), center=(0.5, 0.5), size=(0.4, 1.0))
        reds = {pixel[0] for _, pixel in self.wall_row(painter)}
        self.assertEqual(reds, {0, 200})


if __name__ == "__main__":
    unittest.main()
