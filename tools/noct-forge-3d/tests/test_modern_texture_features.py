"""Unit tests for modern TexturePainter features:
- Universal 3D Decal Projection (project_decal)
- Triplanar Texture Mapping (project_triplanar)
- Non-destructive Multi-Layer Architecture (layer, export_layers)
- 2D Drawing Primitives (draw_circle, blend modes)
- ElementPainter gradients
"""

import math
import tempfile
import unittest
from pathlib import Path
from PIL import Image

from lib.model_builder import ModelBuilder
from Tools.TexturePainter import TexturePainter
from Tools.TexturePainter.core.color import blend_colors


class ModernTextureFeaturesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_dir = Path(self.tmp.name)
        # Create a simple test model with two cubes
        self.model_path = self.tmp_dir / "test_model.bbmodel"
        (ModelBuilder("character")
         .add_group("body")
         .add_cube("head", "body", from_=(-2, 8, -2), to_=(2, 12, 2))
         .add_cube("torso", "body", from_=(-3, 0, -2), to_=(3, 8, 2))
         .export_bbmodel(self.model_path, auto_uv=True))

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_canvas_and_draw_circle(self):
        canvas = TexturePainter.create_canvas(16, 16)
        # Test outline circle
        canvas.draw_circle(8, 8, radius=4, color=(255, 0, 0, 255), fill=False)
        img = canvas.to_image()
        # Top-most point of radius 4 from (8,8) is (8, 4)
        self.assertEqual(img.getpixel((8, 4)), (255, 0, 0, 255))
        # Center should remain transparent in outline mode
        self.assertEqual(img.getpixel((8, 8))[3], 0)

        # Test filled circle
        canvas.clear()
        canvas.draw_circle(8, 8, radius=3, color=(0, 255, 0, 255), fill=True)
        img_filled = canvas.to_image()
        self.assertEqual(img_filled.getpixel((8, 8)), (0, 255, 0, 255))
        self.assertEqual(img_filled.getpixel((8, 5)), (0, 255, 0, 255))

    def test_blend_colors_modes(self):
        base = (100, 100, 100, 255)
        overlay = (200, 50, 0, 255)

        # Normal full opacity replaces
        res_normal = blend_colors(base, overlay, mode="normal", opacity=1.0)
        self.assertEqual(res_normal, (200, 50, 0, 255))

        # Multiply
        res_mul = blend_colors((200, 200, 200, 255), (128, 128, 128, 255), mode="multiply", opacity=1.0)
        # 200 * 128 / 255 ~ 100
        self.assertTrue(98 <= res_mul[0] <= 102)

        # Add
        res_add = blend_colors((100, 100, 100, 255), (50, 50, 50, 255), mode="add", opacity=1.0)
        self.assertEqual(res_add, (150, 150, 150, 255))

    def test_face_painter_draw_circle(self):
        painter = TexturePainter.from_bbmodel(str(self.model_path))
        head_north = painter.head.north
        head_north.fill((0, 0, 0, 255))
        head_north.draw_circle(head_north.width // 2, head_north.height // 2, radius=1, color=(255, 255, 255, 255), fill=True)
        pixel = head_north.get_pixel(head_north.width // 2, head_north.height // 2)
        self.assertEqual(pixel[:3], (255, 255, 255))

    def test_element_painter_apply_gradient(self):
        painter = TexturePainter.from_bbmodel(str(self.model_path))
        painter.torso.apply_gradient((0, 0, 0, 255), (255, 255, 255, 255), axis="y")
        # Check that bottom pixel is darker than top pixel on torso front/north
        face = painter.torso.front
        bottom_val = face.get_pixel(face.width // 2, 0)[0]
        top_val = face.get_pixel(face.width // 2, face.height - 1)[0]
        self.assertNotEqual(bottom_val, top_val)

    def test_project_decal_from_pattern_and_image(self):
        painter = TexturePainter.from_bbmodel(str(self.model_path))
        painter.fill_all((50, 50, 50, 255))

        # 1. Project decal with ASCII pattern on head front
        smile_pattern = [
            "XX..XX",
            "......",
            ".XXXX.",
        ]
        palette = {"X": (255, 255, 0, 255)}

        painter.head.project_decal(
            (smile_pattern, palette),
            side="front",
            center=(0.5, 0.5),
            size=(0.8, 0.8),
            filtering="nearest"
        )

        face = painter.head.front
        yellow_count = sum(1 for x in range(face.width) for y in range(face.height)
                           if face.get_pixel(x, y)[:3] == (255, 255, 0))
        self.assertGreater(yellow_count, 0)

        # 2. Project decal with DecalCanvas / PIL Image on torso front
        badge = TexturePainter.create_canvas(8, 8)
        badge.fill((0, 0, 255, 255))
        painter.torso.project_decal(
            badge,
            side="front",
            center=(0.5, 0.5),
            size=(0.5, 0.5),
            blend="normal"
        )
        torso_face = painter.torso.front
        blue_count = sum(1 for x in range(torso_face.width) for y in range(torso_face.height)
                         if torso_face.get_pixel(x, y)[:3] == (0, 0, 255))
        self.assertGreater(blue_count, 0)

    def test_project_triplanar(self):
        painter = TexturePainter.from_bbmodel(str(self.model_path))
        painter.fill_all((0, 0, 0, 0))

        # Create seamless texture for triplanar projection
        tex = TexturePainter.create_canvas(16, 16)
        tex.fill((180, 120, 60, 255))

        # Project triplanar on whole model
        painter.head.project_triplanar(tex, scale=0.5, blend_sharpness=4.0)

        # Ensure multiple faces received projection
        for face_name in ("north", "east", "up"):
            face = painter.head.faces[face_name]
            painted = sum(1 for x in range(face.width) for y in range(face.height)
                          if face.get_pixel(x, y)[3] > 0)
            self.assertGreater(painted, 0)

    def test_layers_architecture(self):
        painter = TexturePainter.from_bbmodel(str(self.model_path))

        # 1. Base layer solid color
        painter.fill_all((40, 40, 40, 255))

        # 2. Switch to 'overlay' layer using context manager
        with painter.layer("overlay") as p:
            self.assertEqual(p.active_layer_name, "overlay")
            # Paint red star on torso
            p.torso.front.draw_circle(2, 2, radius=1, color=(255, 0, 0, 255), fill=True)

        # Context manager automatically restores active layer
        self.assertEqual(painter.active_layer_name, "base")

        # In base layer, the pixel is still (40, 40, 40, 255)
        self.assertEqual(painter.torso.front.get_pixel(2, 2), (40, 40, 40, 255))

        # When composed into atlas, the overlay layer sits on top
        atlas = painter.compose_atlas()
        uv_info = painter.torso.front.uv_info
        pixel_in_atlas = atlas.getpixel((uv_info["x"] + 2, uv_info["y"] + 2))
        self.assertEqual(pixel_in_atlas, (255, 0, 0, 255))

        # 3. Export separate layers
        export_dir = self.tmp_dir / "layers"
        exported = painter.export_layers(export_dir)
        self.assertIn("base", exported)
        self.assertIn("overlay", exported)
        self.assertTrue(Path(exported["base"]).exists())
        self.assertTrue(Path(exported["overlay"]).exists())

        # Verify overlay PNG is transparent except for the painted mark
        with Image.open(exported["overlay"]) as overlay_img:
            self.assertEqual(overlay_img.size, (painter.width, painter.height))
            # Background should be transparent
            self.assertEqual(overlay_img.getpixel((0, 0))[3], 0)
            # The painted pixel should be opaque red
            self.assertEqual(overlay_img.getpixel((uv_info["x"] + 2, uv_info["y"] + 2)), (255, 0, 0, 255))

        # 4. Clear layer
        painter.clear_layer("overlay")
        with painter.layer("overlay") as p:
            self.assertEqual(p.torso.front.get_pixel(2, 2)[3], 0)


if __name__ == "__main__":
    unittest.main()
