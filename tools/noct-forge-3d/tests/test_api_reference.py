"""Tests for the deterministic API reference generator (Tools.api_reference)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ApiReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from Tools import api_reference
        cls.api_reference = api_reference
        cls.pages = api_reference.build_pages()

    def test_expected_pages(self):
        self.assertEqual(sorted(self.pages),
                         ["cli.md", "index.md", "lib.md",
                          "recipe-context.md", "texture-painter.md"])

    def test_generate_is_deterministic_and_clean(self):
        again = self.api_reference.build_pages()
        self.assertEqual(self.pages, again)
        for name, text in self.pages.items():
            with self.subTest(page=name):
                self.assertNotIn("\r", text)
                self.assertTrue(text.endswith("\n"))
                self.assertIn("py -3.12 -m Tools.api_reference", text)
                self.assertIn("Do not edit by hand", text)
                self.assertNotIn(str(ROOT), text)

    def test_public_python_surfaces_are_covered(self):
        import importlib
        import lib
        painter_mod = importlib.import_module("Tools.TexturePainter")
        for name in lib.__all__:
            self.assertIn(f"## `{name}`", self.pages["lib.md"], name)
        for name in painter_mod.__all__:
            self.assertIn(f"## `{name}`", self.pages["texture-painter.md"], name)
        for name in ("Tools.recipe_context.RecipePaths",
                     "Tools.recipe_context.recipe_paths",
                     "Tools.recipe_context.recipe_environment",
                     "Tools.uv_builder.UVBuilder"):
            self.assertIn(f"## `{name}`", self.pages["recipe-context.md"], name)

    def test_cli_commands_are_covered(self):
        from Tools import forge
        for command in forge.COMMANDS:
            self.assertIn(f"`forge {command}`", self.pages["cli.md"], command)
        for label in ("forge project init",
                      "forge asset init", "forge asset import"):
            self.assertIn(f"`{label}`", self.pages["cli.md"], label)

    def test_internal_modules_are_not_documented_as_api(self):
        internal_markers = ["Tools._resolve", "Tools.project_manifest",
                            "Tools.recipe_emit", "Tools.gltf_export",
                            "Tools.low_poly_audit", "Tools.uv_contract",
                            "Tools.viewer_server", "lib.primitives",
                            "lib.mesh_validation", "lib.geometry_validation"]
        for page in ("lib.md", "texture-painter.md", "recipe-context.md"):
            for marker in internal_markers:
                self.assertNotIn(f"Defined in `{marker}`", self.pages[page],
                                  f"{page} documents internal {marker}")

    def test_internalized_symbols_are_absent(self):
        import importlib
        import lib
        painter_mod = importlib.import_module("Tools.TexturePainter")
        internal_lib = {"loft", "sweep", "segment", "revolve", "segment_sections",
                        "sweep_sections", "MeshFace", "box_surface_contacts"}
        internal_painter = {"TextureExporter", "parse_color", "color_add_noise",
                            "color_lerp", "color_adjust_brightness"}
        self.assertTrue(internal_lib.isdisjoint(lib.__all__))
        self.assertTrue(internal_painter.isdisjoint(painter_mod.__all__))
        for name in internal_lib:
            self.assertNotIn(f"## `{name}`", self.pages["lib.md"], name)
        for name in internal_painter:
            self.assertNotIn(f"## `{name}`", self.pages["texture-painter.md"], name)

    def test_missing_docstrings_are_reported(self):
        missing = self.api_reference._collect_missing(
            [("demo.present", str), ("demo.absent", type("NoDoc", (), {}))])
        self.assertEqual(missing, ["demo.absent"])
        rendered = self.api_reference._render_symbol(
            "NoDoc", type("NoDoc", (), {}))
        self.assertIn("lacuna documentada", rendered)

    def test_generation_does_not_touch_projects(self):
        before = {str(path): path.stat().st_mtime_ns
                  for path in (ROOT / "projects").rglob("*") if path.is_file()}
        self.assertGreater(len(before), 0)
        self.api_reference.build_pages()
        after = {str(path): path.stat().st_mtime_ns
                 for path in (ROOT / "projects").rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_check_mode_matches_disk(self):
        self.assertEqual(self.api_reference.main(["--check"]), 0)
        for name, text in self.pages.items():
            disk = (ROOT / "docs" / "api" / name).read_text(encoding="utf-8").replace("\r\n", "\n")
            self.assertEqual(disk, text, name)

    def test_check_mode_fails_when_outdated(self):
        target = ROOT / "docs" / "api" / "index.md"
        original = target.read_text(encoding="utf-8")
        try:
            with open(target, "a", encoding="utf-8", newline="\n") as handle:
                handle.write("\n<!-- stale marker -->\n")
            self.assertEqual(self.api_reference.main(["--check"]), 1)
        finally:
            with open(target, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(original)
        self.assertEqual(self.api_reference.main(["--check"]), 0)


if __name__ == "__main__":
    unittest.main()
