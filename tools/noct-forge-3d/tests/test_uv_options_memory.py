import tempfile
import unittest
from pathlib import Path

from lib import ModelBuilder
from Tools.uv_packer import BoxUVPacker


def write_model(path):
    ModelBuilder("t").add_group("root").add_cube("body", "root", from_=(0, 0, 0), to_=(4, 4, 4)).export_bbmodel(path)


class UVOptionMemoryTests(unittest.TestCase):
    def test_regeneration_resets_uv_options_without_sidecar_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.bbmodel"
            write_model(model)
            _, first = BoxUVPacker.apply_to_bbmodel(str(model), uv_scale=3, island_padding=2)
            self.assertEqual((first["uv_scale"], first["island_padding"]), (3, 2))
            write_model(model)                    # what model_export does: the packing is gone
            _, second = BoxUVPacker.apply_to_bbmodel(str(model))
            self.assertEqual(second["uv_scale"], 1)

    def test_explicit_options_win_over_the_remembered_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.bbmodel"
            write_model(model)
            BoxUVPacker.apply_to_bbmodel(str(model), uv_scale=3)
            write_model(model)
            _, stats = BoxUVPacker.apply_to_bbmodel(str(model), uv_scale=2)
            self.assertEqual(stats["uv_scale"], 2)

    def test_a_model_that_is_already_packed_keeps_its_own_saved_options(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.bbmodel"
            write_model(model)
            BoxUVPacker.apply_to_bbmodel(str(model), uv_scale=3)
            _, stats = BoxUVPacker.apply_to_bbmodel(str(model))
            self.assertEqual(stats["uv_scale"], 3)


if __name__ == "__main__":
    unittest.main()
