"""Canonical quiet-by-default test runner for the Blockbench toolkit."""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path


AREA_TERMS = {
    "all": (),
    "model": ("model", "builder", "polygon", "procedural", "assembly", "spatial",
              "rigged", "character", "armature", "animation"),
    "uv": ("uv", "fractional"),
    "texture": ("texture", "painter"),
    "repository": ("repository",),
}


def _iter_cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from _iter_cases(test)
        else:
            yield test


def build_suite(root: Path, area: str = "all") -> unittest.TestSuite:
    discovered = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
    terms = AREA_TERMS[area]
    if not terms:
        return discovered
    return unittest.TestSuite(
        test for test in _iter_cases(discovered)
        if any(term in test.id().lower() for term in terms)
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the repository unittest suite")
    parser.add_argument("--area", choices=tuple(AREA_TERMS), default="all",
                        help="Run one broad subsystem (default: all)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print every test name")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    suite = build_suite(root, args.area)
    result = unittest.TextTestRunner(
        stream=sys.stderr,
        verbosity=2 if args.verbose else 0,
    ).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
