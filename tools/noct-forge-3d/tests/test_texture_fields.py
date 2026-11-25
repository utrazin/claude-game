"""Procedural fields: stability, ranges, seamless tiles, dithering and painting on models."""
import hashlib
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from lib import ModelBuilder
from Tools.TexturePainter import Field, Shader, TexturePainter
from Tools.TexturePainter.fields import Frame, _threshold, blue_noise_ranks, hash_cells
from Tools.uv_builder import UVBuilder

POINTS = ([0.3, -2.7, 5.55, 11.1], [1.9, 0.4, -7.2, 3.3], [-0.5, 8.8, 2.2, -4.4])


def rounded(field):
    return [round(float(v), 6) for v in field(*POINTS)]


class StabilityTests(unittest.TestCase):
    """A change in any of these values repaints every recipe that uses the field: add a new
    generator instead of changing an existing one."""

    def test_hash_is_stable(self):
        values = hash_cells(np.array([0, 1, -1, 123456]), np.array([0, 2, -2, 7]), np.array([0, 3, -3, 9]), 5)
        self.assertEqual(values.tolist(), [1557653252, 1542615334, 2318150402, 3676354038])

    def test_generators_are_stable(self):
        expected = {
            "value": (Field.value(1.7, seed=3), [0.57793, 0.536328, 0.302638, 0.364575]),
            "gradient": (Field.gradient(1.7, seed=3), [0.517574, 0.395526, 0.490428, 0.426222]),
            "f1": (Field.cells(1.7, seed=3), [0.539512, 0.110472, 0.292111, 0.346309]),
            "edge": (Field.cells(1.7, seed=3, mode="edge"), [0.0566, 0.620679, 0.22625, 0.239378]),
            "id": (Field.cells(1.7, seed=3, mode="id"), [0.975792, 0.420903, 0.30919, 0.303971]),
            "white": (Field.white(2.0, seed=3), [0.255577, 0.250333, 0.339331, 0.668466]),
            "fbm": (Field.gradient(1.1, seed=3).fbm(4), [0.433675, 0.590662, 0.458756, 0.449966]),
            "warp": (Field.value(1.1, seed=3).warp(Field.gradient(0.6, seed=4), 0.7),
                     [0.331923, 0.220873, 0.603904, 0.726006]),
            "stripes": (Field.stripes(0.9, (1, 1, 0), shape="sine"), [0.90464, 0.987059, 0.024524, 0.24306]),
        }
        for name, (field, values) in expected.items():
            with self.subTest(name):
                self.assertEqual(rounded(field), values)

    def test_blue_noise_and_thresholds_are_stable(self):
        ranks = blue_noise_ranks()
        self.assertEqual(sorted(ranks.ravel().tolist()), list(range(ranks.size)))
        self.assertEqual(hashlib.sha256(ranks.astype("<i8").tobytes()).hexdigest(),
                         "746a090008196ac9505607102ddeed2e4829f3eb4a67a9cc2a22a265b4d7155b")
        px, py = np.meshgrid(np.arange(8), np.arange(8))
        digests = {"bayer4": "3b342c6af15b2367", "blue": "450cb202ed2575ec",
                   "ign": "2ec34eb94d894ac3", "cluster": "8c43341704e74af8"}
        for method, digest in digests.items():
            data = np.round(_threshold(method, px, py, 0) * 1e6).astype("<i8").tobytes()
            self.assertEqual(hashlib.sha256(data).hexdigest()[:16], digest, method)

    def test_blue_noise_is_more_even_than_white(self):
        def worst_cluster(threshold):
            dark = threshold < 0.25
            near = sum((np.roll(np.roll(dark, dy, 0), dx, 1) & dark).sum()
                       for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0))
            return near
        px, py = np.meshgrid(np.arange(64), np.arange(64))
        self.assertLess(worst_cluster(_threshold("blue", px, py, 0)), worst_cluster(_threshold("white", px, py, 1)) // 2)


class FieldValueTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.points = rng.uniform(-20, 20, (3, 3000))

    def fields(self):
        return {
            "value": Field.value(1.3), "gradient": Field.gradient(1.3), "f1": Field.cells(1.3),
            "f2": Field.cells(1.3, mode="f2"), "edge": Field.cells(1.3, mode="edge", metric="manhattan"),
            "id": Field.cells(1.3, mode="id", jitter=0.4), "white": Field.white(3),
            "stripes": Field.stripes(2, (0, 1, 0), shape="square"), "rings": Field.rings((1, 0, 0), 2, axis="y"),
            "height": Field.height("y", -5, 5), "constant": Field.constant(0.25),
            "fbm": Field.gradient(1).ridge(2).fbm(5), "billow": Field.value(1).billow(),
            "warp": Field.gradient(1).warp(Field.value(0.7), 2.0), "mix": Field.value(1).mix(Field.cells(1), Field.height()),
            "ops": (Field.value(1) + Field.cells(1)) * 0.5 - Field.constant(0.1) | ~Field.white(1) & Field.gradient(2),
            "shaped": Field.value(1).remap(0.2, 0.7).contrast(3).gamma(1.4).curve([(0, 0), (.5, .1), (1, 1)])
            .threshold(0.5, 0.2).steps(4).rotate(33).scale(2).stretch(1, 3).offset(1, 2),
        }

    def test_values_stay_in_unit_range_and_are_deterministic(self):
        for name, field in self.fields().items():
            with self.subTest(name):
                first, second = field(*self.points), field(*self.points)
                np.testing.assert_array_equal(first, second)
                self.assertTrue(np.isfinite(first).all())
                self.assertGreaterEqual(first.min(), 0.0)
                self.assertLessEqual(first.max(), 1.0)
                self.assertEqual(first.shape, self.points[0].shape)

    def test_seeds_and_parameters_change_the_pattern(self):
        for make in (Field.value, Field.gradient, Field.cells, Field.white):
            a, b = make(1.5, seed=1)(*self.points), make(1.5, seed=2)(*self.points)
            self.assertGreater(np.abs(a - b).mean(), 0.05, make.__name__)
        base = Field.value(1)(*self.points)
        self.assertGreater(np.abs(base - Field.value(1, stretch=(1, 5, 1))(*self.points)).mean(), 0.05)
        self.assertGreater(np.abs(base - Field.value(1).warp(Field.value(0.5), 1.5)(*self.points)).mean(), 0.05)

    def test_gradient_uses_the_full_range_and_is_centered(self):
        rng = np.random.default_rng(4)
        values = Field.gradient(1)(*rng.uniform(-100, 100, (3, 100000)))
        self.assertAlmostEqual(values.mean(), 0.5, delta=0.01)
        self.assertGreater(values.max(), 0.95)
        self.assertLess(values.min(), 0.05)

    def test_cells_modes_have_their_meaning(self):
        grid = np.array([0.0, 1.0, 2.0])
        regular = Field.cells(1.0, jitter=0.0)(grid + 0.5, grid + 0.5, grid + 0.5)
        np.testing.assert_allclose(regular, 0.0, atol=1e-12)
        ids = Field.cells(1.0, mode="id")(np.array([0.1, 0.2]), np.array([0.1, 0.2]), np.array([0.1, 0.2]))
        self.assertEqual(ids[0], ids[1])
        edge = Field.cells(1.0, mode="edge")(*self.points)
        near_edge = Field.cells(1.0, mode="edge").invert().threshold(0.95)(*self.points)
        self.assertLess(near_edge.mean(), 0.2)
        self.assertGreater(edge.mean(), 0.05)

    def test_operators_and_validation(self):
        v = Field.constant(0.5)
        one = (np.zeros(2),) * 3
        self.assertEqual((v + 0.25)(*one).tolist(), [0.75, 0.75])
        self.assertEqual((1.0 - v)(*one).tolist(), [0.5, 0.5])
        self.assertEqual(v.invert().steps(2)(*one).tolist(), [1.0, 1.0])
        self.assertEqual((v | 0.9)(*one).tolist(), [0.9, 0.9])
        self.assertEqual(v.mix(1.0, 0.5)(*one).tolist(), [0.75, 0.75])
        self.assertEqual(Field.height("y", 0, 10)(np.zeros(2), np.array([5.0, 20.0]), np.zeros(2)).tolist(), [0.5, 1.0])
        for bad in (lambda: Field.value(0), lambda: Field.cells(mode="x"), lambda: Field.constant(2),
                    lambda: v.fbm(0), lambda: v.steps(1), lambda: v.curve([(0, 0)]), lambda: v.remap(1, 1),
                    lambda: Field.stripes(1, (0, 0, 0)), lambda: v.ramp(["#000"], stops=[0, 1])):
            with self.assertRaises(ValueError):
                bad()
        with self.assertRaises(TypeError):
            v + "x"

    def test_custom_fields_compose_with_everything(self):
        stripes = Field.from_function(lambda x, y, z: (np.sin(x * 3) * 0.5 + 0.5))
        combined = stripes.warp(Field.value(1), 0.5).fbm(2).mix(Field.cells(1), 0.3)
        self.assertEqual(combined(*self.points).shape, self.points[0].shape)
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            Field.from_function(lambda x, y, z: x * 100)(*self.points)
        with self.assertRaisesRegex(ValueError, "tiled"):
            stripes.image((8, 8), (1, 1), tileable=True)
        frame_field = Field.from_frame_function(lambda frame: np.full(frame.shape, 0.5 if frame.wrap is None else 1.0))
        self.assertEqual(frame_field.image((2, 2)).getpixel((0, 0)), 128)
        self.assertEqual(frame_field.image((2, 2), tileable=True).getpixel((0, 0)), 255)

    def test_facing_needs_normals(self):
        with self.assertRaisesRegex(ValueError, "normals"):
            Field.facing()(*self.points)
        up = Field.facing((0, 1, 0), 2)(np.zeros(2), np.zeros(2), np.zeros(2), normal=[[0, 1, 0], [1, 0, 0]])
        self.assertEqual(up.tolist(), [1.0, 0.0])


class SeamlessTests(unittest.TestCase):
    """A tile of length L must repeat exactly: f(x + L) == f(x)."""

    def assert_periodic(self, field, length=4.0, z=0.7):
        rng = np.random.default_rng(8)
        x, y = rng.uniform(0, length, (2, 500))
        wrap = (length, length, None)
        a = field._eval(Frame(x, y, z, wrap=wrap))
        np.testing.assert_allclose(field._eval(Frame(x + length, y, z, wrap=wrap)), a, atol=1e-12)
        np.testing.assert_allclose(field._eval(Frame(x, y - 2 * length, z, wrap=wrap)), a, atol=1e-12)

    def test_generators_and_operators_tile(self):
        for name, field in {
            "value": Field.value(1), "gradient": Field.gradient(0.5), "cells": Field.cells(1.5 / 1.5),
            "edge": Field.cells(0.5, mode="edge"), "id": Field.cells(1, mode="id", stretch=(1, 2, 1)),
            "white": Field.white(2), "stripes": Field.stripes(0.5, (1, 0, 0)), "fbm": Field.gradient(0.5).ridge().fbm(4),
            "warp": Field.gradient(1).warp(Field.value(0.5), 0.9), "mix": Field.value(1).mix(Field.cells(0.5), Field.white(1)),
            "scale": Field.value(1).scale(2).stretch(2, 1, 1),
        }.items():
            with self.subTest(name):
                self.assert_periodic(field)

    def test_bad_tiles_are_rejected_with_advice(self):
        with self.assertRaisesRegex(ValueError, "whole number of cells"):
            Field.value(0.3).image((8, 8), (4, 4), tileable=True)
        with self.assertRaisesRegex(ValueError, "cannot be tiled"):
            Field.rings().image((8, 8), (4, 4), tileable=True)
        with self.assertRaisesRegex(ValueError, "cannot be tiled"):
            Field.value(1).rotate(10).image((8, 8), (4, 4), tileable=True)

    def test_tiled_image_wraps_in_pixels(self):
        image = np.asarray(Field.gradient(0.5).fbm(3).image((64, 64), (4, 4), tileable=True)).astype(int)
        shifted = np.asarray(Field.gradient(0.5).fbm(3).image((64, 64), (4, 4), tileable=True)).astype(int)
        np.testing.assert_array_equal(image, shifted)
        step = np.abs(np.diff(image, axis=1)).mean()
        seam = np.abs(image[:, 0] - image[:, -1]).mean()
        self.assertLess(seam, step * 2.5)


class OutputTests(unittest.TestCase):
    def frame(self, width=64, height=64, **kwargs):
        columns, rows = np.meshgrid(np.arange(width), np.arange(height))
        return Frame(columns / width, rows / height, 0.0, pixel=(columns, rows), grid=(height, width), **kwargs)

    def test_ramp_smooth_and_hard(self):
        ramp = Field.height("x", 0, 1)
        frame = Frame(np.array([0.0, 0.25, 0.5, 1.0]), 0.0, 0.0)
        smooth = ramp.ramp(["#000000", "#ff0000", "#ffffff00"]).render(frame)
        self.assertEqual(smooth[:, 0].tolist(), [0.0, 127.5, 255.0, 255.0])
        self.assertEqual(smooth[:, 3].tolist(), [255.0, 255.0, 255.0, 0.0])
        hard = ramp.ramp(["#000000", "#ff0000", "#ffffff"], smooth=False).render(frame)
        self.assertEqual(hard[:, 0].tolist(), [0.0, 0.0, 255.0, 255.0])

    def test_dither_only_uses_palette_colors_and_preserves_mean(self):
        colors = ["#101820", "#506070", "#a0b0c0", "#f0f8ff"]
        palette = {tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,) for c in colors}
        field = Field.gradient(2, seed=5).fbm(3)
        for method in ("bayer2", "bayer4", "bayer8", "blue", "white", "ign", "cluster", "lines", "diagonal",
                       "floyd", "atkinson"):
            with self.subTest(method):
                shader = field.dither(colors, method, scale=1)
                image = np.asarray(shader.image((48, 48), (6, 6))).reshape(-1, 4)
                self.assertTrue({tuple(p) for p in image.tolist()} <= palette)
                target = np.asarray(Field.gradient(2, seed=5).fbm(3).ramp(colors).image((48, 48), (6, 6)))
                self.assertLess(abs(float(image[:, 0].mean()) - float(target[..., 0].mean())), 14.0)

    def test_dither_methods_look_different_and_strength_zero_is_hard(self):
        field = Field.height("x", 0, 1)
        frame = self.frame()
        out = {m: field.dither(["#000", "#fff"], m).render(frame)[..., 0] for m in ("bayer4", "blue", "white", "cluster", "lines")}
        names = list(out)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                self.assertFalse(np.array_equal(out[a], out[b]), (a, b))
        hard = field.dither(["#000", "#fff"], "blue", strength=0).render(frame)[..., 0]
        np.testing.assert_array_equal(hard, (field._eval(frame) > 0.5) * 255.0)
        wide = field.dither(["#000", "#fff"], "bayer4", scale=3).render(frame)[..., 0]
        np.testing.assert_array_equal(wide[:, 0:3], np.repeat(wide[:, :1], 3, axis=1))

    def test_dither_requirements(self):
        field = Field.constant(0.5)
        with self.assertRaisesRegex(ValueError, "canvas pixels"):
            field.dither(["#000", "#fff"]).render(Frame(np.zeros(2)))
        with self.assertRaisesRegex(ValueError, "needs an image"):
            field.dither(["#000", "#fff"], "floyd").render(Frame(np.zeros(2), pixel=(np.zeros(2, int),) * 2))
        for bad in (lambda: field.dither(["#000"]), lambda: field.dither(["#000", "#fff"], "x"),
                    lambda: field.dither(["#000", "#fff"], scale=0)):
            with self.assertRaises(ValueError):
                bad()

    def test_shader_masked_and_over_and_image(self):
        frame = Frame(np.array([0.0, 1.0]), 0.0, 0.0)
        red = Field.constant(0.5).ramp(["#ff0000", "#ff0000"])
        blue = Field.constant(0.5).ramp(["#0000ff", "#0000ff"])
        half = red.masked(Field.height("x", 0, 1)).render(frame)
        self.assertEqual(half[:, 3].tolist(), [0.0, 255.0])
        both = half_over = red.masked(Field.height("x", 0, 1)).over(blue).render(frame)
        self.assertEqual(both[0].tolist(), [0.0, 0.0, 255.0, 255.0])
        self.assertEqual(half_over[1].tolist(), [255.0, 0.0, 0.0, 255.0])
        image = red.image((4, 2), (2, 1))
        self.assertEqual((image.size, image.mode), ((4, 2), "RGBA"))
        gray = Field.height("x", 0, 4).image((4, 1))
        self.assertEqual([gray.getpixel((i, 0)) for i in range(4)], [32, 96, 159, 223])


class PaintFieldTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.model = self.root / "model.bbmodel"
        (ModelBuilder("blocks").add_group("root")
         .add_cube("left", "root", from_=(0, 0, 0), to_=(4, 4, 4))
         .add_cube("right", "root", from_=(4, 0, 0), to_=(8, 4, 4))
         .export_bbmodel(self.model))
        UVBuilder(self.model, start_size=(64, 64), uv_scale=4, island_padding=1).save()
        self.painter = TexturePainter.from_bbmodel(self.model)

    def atlas(self):
        return np.asarray(self.painter.compose_atlas()).astype(int)

    def test_paint_field_matches_manual_array_painting_and_is_continuous(self):
        field = Field.gradient(0.7, seed=2).fbm(3)
        shader = field.ramp(["#202020", "#e0e0e0"])
        self.painter.left.paint_field(shader)
        self.painter.right.paint_field(shader)
        painted = self.atlas()
        self.painter.fill_all((0, 0, 0, 0))

        def manual(rows):
            frame = Frame(*rows.model_position.T)
            return shader.render(frame)
        self.painter.left.paint_surface_arrays(manual)
        self.painter.right.paint_surface_arrays(manual)
        np.testing.assert_array_equal(painted, self.atlas())
        # Same model position, same color on both elements (continuity across parts).
        samples = {}
        for name in ("left", "right"):
            for face_name, face in self.painter.element(name).faces.items():
                for sample in self.painter.surface_sampler.samples(name, face_name, face):
                    key = tuple(round(v, 4) for v in sample.model_position)
                    samples.setdefault(key, []).append(tuple(face.get_pixel(*sample.pixel)))
        shared = [colors for colors in samples.values() if len(colors) > 1]
        self.assertTrue(shared)
        self.assertTrue(all(len(set(colors)) == 1 for colors in shared))

    def test_where_blend_opacity_and_spaces(self):
        self.painter.fill_all((100, 100, 100, 255))
        red = Field.constant(0.5).ramp(["#ff0000", "#ff0000"])
        self.painter.left.paint_field(red, where=lambda rows: rows.model_position[:, 1] > 2)
        left_up = self.painter.left.face("up").get_pixel(1, 1)
        self.assertEqual(left_up, (255, 0, 0, 255))
        self.assertEqual(self.painter.left.face("down").get_pixel(1, 1), (100, 100, 100, 255))
        self.painter.right.paint_field(red, where=Field.height("x", 4, 8), opacity=0.5)
        row = [self.painter.right.face("up").get_pixel(x, 1) for x in range(self.painter.right.face("up").width)]
        self.assertTrue(row[0][0] < row[-1][0] and row[-1][0] <= 178)
        self.painter.fill_all((200, 200, 200, 255))
        self.painter.left.paint_field(Field.constant(0.5).ramp(["#808080"] * 2), blend="multiply")
        self.assertEqual(self.painter.left.face("up").get_pixel(1, 1), (100, 100, 100, 255))
        for space in ("element", "normalized", "uv"):
            self.painter.left.paint_field(Field.value(1).ramp(["#000", "#fff"]), space=space)
        with self.assertRaisesRegex(ValueError, "space"):
            self.painter.left.paint_field(red, space="world")
        with self.assertRaisesRegex(TypeError, "Shader"):
            self.painter.left.paint_field(Field.value(1))

    def test_facing_uses_normals_and_dither_uses_canvas_pixels(self):
        self.painter.fill_all((0, 0, 0, 255))
        top = Field.facing((0, 1, 0), 4).ramp(["#000000", "#00ff00"], smooth=False, stops=[0, 0.5])
        self.painter.left.paint_field(top)
        self.assertEqual(self.painter.left.face("up").get_pixel(1, 1), (0, 255, 0, 255))
        self.assertEqual(self.painter.left.face("north").get_pixel(1, 1), (0, 0, 0, 255))
        self.painter.right.paint_field(Field.value(0.5).dither(["#000000", "#ffffff"], "bayer4"))
        face = self.painter.right.face("up")
        colors = {tuple(face.get_pixel(x, y)) for x in range(face.width) for y in range(face.height)}
        self.assertEqual(colors, {(0, 0, 0, 255), (255, 255, 255, 255)})

    def test_selection_and_layers(self):
        shader = Field.value(1).ramp(["#000", "#fff"])
        with self.painter.layer("grain"):
            self.painter.left.paint_field(shader)
        self.assertTrue(self.atlas()[..., 3].any())


if __name__ == "__main__":
    unittest.main()


class GalleryTests(unittest.TestCase):
    def test_every_recipe_tiles_and_both_styles_work(self):
        from Tools import field_gallery
        for name, (make, colors) in field_gallery.RECIPES.items():
            with self.subTest(name):
                field = make()
                rng = np.random.default_rng(2)
                x, y = rng.uniform(0, 4, (2, 200))
                wrap = (4.0, 4.0, None)
                np.testing.assert_allclose(field._eval(Frame(x + 4, y, 0.0, wrap=wrap)),
                                           field._eval(Frame(x, y, 0.0, wrap=wrap)), atol=1e-12)
                palette = {tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,) for c in colors}
                pixel = np.asarray(field_gallery.tile(name, "pixel", 32)).reshape(-1, 4)
                self.assertTrue({tuple(p) for p in pixel.tolist()} <= palette)
                self.assertGreater(len({tuple(p) for p in pixel.tolist()}), 1)
                painted = np.asarray(field_gallery.tile(name, "painted", 32)).reshape(-1, 4)
                self.assertGreater(len({tuple(p) for p in painted.tolist()}), len(palette))

    def test_recipes_are_distinct_and_cli_writes_a_sheet(self):
        from Tools import field_gallery
        tiles = {name: np.asarray(field_gallery.tile(name, "painted", 32)).astype(int) for name in field_gallery.RECIPES}
        names = list(tiles)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                self.assertFalse(np.array_equal(tiles[a], tiles[b]), (a, b))
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "sheet.png"
            self.assertEqual(field_gallery.main([str(out), "--only", "stone,wood", "--size", "32"]), 0)
            with Image.open(out) as sheet:
                self.assertEqual(sheet.size[0], 8 + 2 * (32 + 8))
        with self.assertRaises(ValueError):
            field_gallery.shader("lava")


class DocExampleTests(unittest.TestCase):
    """Code blocks starting with '# example:' in the procedural-fields reference must run."""

    def test_reference_examples_execute(self):
        import re
        root = Path(__file__).resolve().parents[1]
        text = (root / ".agents/skills/forge-3d-texture/references/procedural-fields.md").read_text(encoding="utf-8")
        blocks = [code for code in re.findall(r"```python\n(.*?)```", text, re.S) if code.lstrip().startswith("# example:")]
        self.assertGreaterEqual(len(blocks), 2)
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.bbmodel"
            (ModelBuilder("blocks").add_group("root")
             .add_cube("body", "root", from_=(0, 0, 0), to_=(4, 4, 4))
             .add_cube("cap", "root", from_=(0, 4, 0), to_=(4, 6, 4))
             .export_bbmodel(model))
            UVBuilder(model, start_size=(64, 64), uv_scale=4, island_padding=1).save()
            for code in blocks:
                painter = TexturePainter.from_bbmodel(model)
                exec(compile(code, "procedural-fields.md", "exec"), {"Field": Field, "painter": painter})
                self.assertTrue(np.asarray(painter.compose_atlas())[..., 3].any())
