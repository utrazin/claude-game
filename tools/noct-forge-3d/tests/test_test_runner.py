import unittest
from pathlib import Path

from Tools.run_tests import AREA_TERMS, build_suite, _iter_cases


class CanonicalTestRunnerTests(unittest.TestCase):
    def test_every_area_selects_tests_from_the_discovered_suite(self):
        root = Path(__file__).resolve().parents[1]
        all_ids = {test.id() for test in _iter_cases(build_suite(root))}
        self.assertGreater(len(all_ids), 100)
        for area in AREA_TERMS:
            selected = {test.id() for test in _iter_cases(build_suite(root, area))}
            self.assertTrue(selected, area)
            self.assertLessEqual(selected, all_ids)


if __name__ == "__main__":
    unittest.main()
