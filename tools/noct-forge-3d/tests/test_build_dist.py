import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_dist.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build_dist_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(SCRIPT.is_file(), "build script is not part of the distribution")
class CleanTargetGuardTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_refuses_repository_parents_and_drive_root(self):
        for target in (self.module.ROOT, self.module.ROOT.parent, Path(self.module.ROOT.anchor)):
            with self.subTest(target=target), self.assertRaises(SystemExit):
                self.module.check_clean_target(target)

    def test_refuses_unrelated_non_empty_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "precious.txt").write_text("x", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.module.check_clean_target(Path(tmp))

    def test_accepts_empty_folder_and_previous_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.module.check_clean_target(Path(tmp))
            (Path(tmp) / "BUILD_INFO.json").write_text("{}", encoding="utf-8")
            (Path(tmp) / "other.txt").write_text("x", encoding="utf-8")
            self.module.check_clean_target(Path(tmp))

    def test_generated_files_use_lf(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            self.module.write_text(target, "a\nb\n")
            self.assertEqual(target.read_bytes(), b"a\nb\n")


if __name__ == "__main__":
    unittest.main()
