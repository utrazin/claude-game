import tempfile
import unittest
from pathlib import Path
from unittest import mock

from Tools import doctor


class DoctorTests(unittest.TestCase):
    def test_requirements_are_parsed_with_minimums(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "requirements.txt"
            path.write_text("# c\nPillow>=10\nnumpy>=1.26\nplaywright\n", encoding="utf-8")
            self.assertEqual(doctor.read_requirements(path), [("Pillow", "10"), ("numpy", "1.26"), ("playwright", "0")])

    def test_version_comparison(self):
        self.assertLess(doctor._version_tuple("1.9"), doctor._version_tuple("1.26"))
        self.assertEqual(doctor._version_tuple("10"), (10, 0, 0))

    def test_missing_package_is_a_fail_with_pip_fix(self):
        with mock.patch.object(doctor.importlib.metadata, "version", side_effect=doctor.importlib.metadata.PackageNotFoundError):
            results = doctor.check_pip_packages()
        self.assertTrue(results and all(r["status"] == doctor.FAIL and isinstance(r["fix"], list) for r in results))
        self.assertFalse(doctor.verdict(results))

    def test_optional_warning_does_not_block_verdict(self):
        checks = [doctor._check("node", doctor.WARN, "missing", required=False), doctor._check("python", doctor.PASS, "ok")]
        self.assertTrue(doctor.verdict(checks))

    def test_fixes_run_only_after_confirmation(self):
        calls = []
        checks = [doctor._check("pip:x", doctor.FAIL, "missing", ["tool", "install"]),
                  doctor._check("pip:y", doctor.FAIL, "missing", ["tool", "install"]),
                  doctor._check("note", doctor.FAIL, "manual", "do it by hand")]
        runner = lambda cmd, cwd: calls.append(cmd) or mock.Mock(returncode=0)
        self.assertEqual(doctor.apply_fixes(checks, confirm=lambda question: False, runner=runner), [])
        self.assertEqual(calls, [])
        ran = doctor.apply_fixes(checks, confirm=lambda question: True, runner=runner)
        self.assertEqual(calls, [["tool", "install"]])  # duplicate command asked and run once; text hints never run
        self.assertEqual(ran, [("tool install", 0)])

    def test_install_without_a_terminal_installs_nothing(self):
        self.assertFalse(doctor._confirm("anything?")) if not doctor.sys.stdin or not doctor.sys.stdin.isatty() else None


if __name__ == "__main__":
    unittest.main()
