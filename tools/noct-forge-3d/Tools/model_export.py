"""Canonical one-command model export and objective technical audit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.model_builder import ModelBuilder
from Tools.low_poly_audit import audit_low_poly
from Tools._resolve import resolve_model_target, resolve_recipe
from Tools.recipe_context import recipe_environment


CHECK_PROFILES = ("geometry", "standard", "strict")

_TRACEBACK_LINES = 40  # room for a multi-line validation message


def resolve_project(project: str | Path) -> tuple[Path, Path, Path]:
    project_dir, model_path = resolve_model_target(project)
    return project_dir, resolve_recipe(project, "model"), model_path


def _issue(code: str, message: str, *, stage: str, severity: str = "error") -> dict[str, str]:
    return {"code": code, "message": message, "stage": stage, "severity": severity}


def audit_model_file(model_path: Path, *, checks: str = "standard",
                     lint: bool = False) -> dict[str, Any]:
    """Audit a model file. strict blocks on structural low-poly issues; lint also blocks on style heuristics."""
    if checks not in CHECK_PROFILES:
        raise ValueError(f"Unknown check profile {checks!r}")
    data = json.loads(model_path.read_text(encoding="utf-8"))
    builder = ModelBuilder.from_bbmodel_data(data)
    validation = builder.validate()
    issues = [
        _issue("VALIDATION_ERROR", message, stage="geometry")
        for message in validation["errors"]
    ]
    warnings = list(validation["warnings"])
    low_poly: dict[str, Any] | None = None
    skinning: dict[str, Any] | None = None

    if checks == "strict":
        # Structure warnings become blocking errors
        issues.extend(
            _issue("VALIDATION_WARNING", message, stage="structure")
            for message in warnings
        )
        # Run audit with style=True so we get both buckets; only promote based on lint flag
        low_poly = audit_low_poly(builder, style=True)
        # Structural low-poly checks (disconnected shells, face budget) always block in strict
        issues.extend(
            _issue("LOW_POLY_STRUCTURAL", message, stage="low_poly")
            for message in low_poly["structural_warnings"]
        )
        if lint:
            # Style heuristics block only when --lint is active
            issues.extend(
                _issue("LOW_POLY_STYLE", message, stage="low_poly")
                for message in low_poly["style_warnings"]
            )
    # In standard mode warnings are informational only — they never block the export

    if checks == "strict" and builder._armature_bones:
        skinning = builder.skinning_audit()
        issues.extend(
            _issue("SKINNING", message, stage="skinning")
            for message in skinning["warnings"]
        )

    all_low_poly_warnings = low_poly["warnings"] if low_poly else []
    return {
        "status": "pass" if not issues else "fail",
        "model": str(model_path),
        "checks": checks,
        "lint": lint,
        "issues": issues,
        "warnings": warnings,  # always present; informational only in standard mode
        "metrics": {
            "validation_errors": len(validation["errors"]),
            "validation_warnings": len(warnings),
            "low_poly_structural": len(low_poly["structural_warnings"]) if low_poly else 0,
            "low_poly_style": len(low_poly["style_warnings"]) if low_poly else 0,
            "low_poly_issues": len(all_low_poly_warnings),
            "skinning_issues": len(skinning["warnings"]) if skinning else 0,
        },
    }


def export_project(project: str | Path, *, recipe: str | Path | None = None,
                   checks: str = "standard", lint: bool = False) -> dict[str, Any]:
    """Execute one saved recipe, require the model file to exist, then audit it."""

    project_dir, default_recipe, model_path = resolve_project(project)
    recipe_path = resolve_recipe(project, "model", recipe)
    if not recipe_path.exists():
        return {
            "status": "fail", "stage": "recipe", "model": str(model_path), "checks": checks,
            "issues": [_issue("RECIPE_NOT_FOUND", f"{recipe_path} (no recipe there: create one with Tools.asset_init, or turn an existing .bbmodel into a project with Tools.model_import)", stage="recipe")],
            "warnings": [], "metrics": {},
        }

    env = recipe_environment(project)
    written_before = model_path.stat().st_mtime_ns if model_path.exists() else None
    run = subprocess.run(
        [sys.executable, str(recipe_path)], cwd=REPO_ROOT, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if run.returncode:
        raw = (run.stderr or run.stdout or "").strip()
        lines = [l.strip() for l in raw.splitlines() if l.strip()]
        tail = "\n".join(lines[-_TRACEBACK_LINES:]) if lines else f"recipe exited with code {run.returncode}"
        return {
            "status": "fail", "stage": "recipe", "model": str(model_path), "checks": checks,
            "issues": [_issue("RECIPE_FAILED", tail, stage="recipe")],
            "warnings": [], "metrics": {"exit_code": run.returncode},
        }
    if model_path.exists() and model_path.stat().st_mtime_ns == written_before:
        return {
            "status": "fail", "stage": "export", "model": str(model_path), "checks": checks,
            "issues": [_issue("MODEL_NOT_UPDATED", "The recipe ran but did not write model.bbmodel, so the file on disk is older than the recipe; make it call export_bbmodel", stage="export")],
            "warnings": [], "metrics": {},
        }
    if not model_path.exists():
        return {
            "status": "fail", "stage": "export", "model": str(model_path), "checks": checks,
            "issues": [_issue("MODEL_MISSING", "Recipe completed without model.bbmodel", stage="export")],
            "warnings": [], "metrics": {},
        }
    try:
        report = audit_model_file(model_path, checks=checks, lint=lint)
    except Exception as exc:
        return {
            "status": "fail", "stage": "audit", "model": str(model_path), "checks": checks,
            "issues": [_issue("MODEL_PARSE_FAILED", str(exc), stage="audit")],
            "warnings": [], "metrics": {},
        }
    report["stage"] = "audit"
    return report


model_export = export_project


def print_report(report: dict[str, Any], *, verbose: bool = False) -> None:
    model_name = Path(report["model"]).name
    if report.get("stage") == "recipe" and report["status"] == "fail":
        print("[export] FAIL stage=recipe")
        for item in report["issues"]:
            if verbose or "\n" not in item["message"]:
                print(item["message"])
            else:
                # Print the whole exception message (it may span several
                # lines), not only the traceback's last line.
                lines = item["message"].strip().splitlines()
                start = max((i for i, line in enumerate(lines)
                             if re.match(r"^[A-Za-z_][\w.]*(Error|Exception)\b", line)),
                            default=len(lines) - 1)
                print("\n".join(lines[start:]))
                print("  (run with --verbose for full traceback)")
    else:
        # Reaching the audit stage means the recipe ran and wrote the model.
        exported = report.get("stage") == "audit" or report["status"] == "pass"
        print(f"[export] {'PASS' if exported else 'FAIL'} {model_name}")
        metrics = report.get("metrics", {})
        lint_label = "+lint" if report.get("lint") else ""
        print(f"[audit] {'PASS' if report['status'] == 'pass' else 'FAIL'} profile={report['checks']}{lint_label} issues={len(report['issues'])}")
        blocking = {item["message"] for item in report["issues"]}
        if report["status"] == "fail":
            for item in report["issues"]:
                print(f"  {item['code']} {item['message']}")
        elif metrics.get("low_poly_issues") is not None:
            structural = metrics.get("low_poly_structural", 0)
            style = metrics.get("low_poly_style", 0)
            print(f"[audit] validation={metrics.get('validation_errors', 0)}/{metrics.get('validation_warnings', 0)} "
                  f"low_poly=structural:{structural} style:{style}")
        # Informational warnings (never blocking); skip those already listed as issues.
        for msg in report.get("warnings", []):
            if msg not in blocking:
                print(f"[audit] WARN {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a model recipe, export model.bbmodel, and run compact audits.")
    parser.add_argument("project", help="Canonical project directory: projects/<name>")
    parser.add_argument("--recipe", help="Recipe path relative to the project (default: the asset's registered generate_model.py)")
    parser.add_argument(
        "--checks", choices=CHECK_PROFILES, default="standard",
        help=(
            "geometry: topology integrity only; "
            "standard: integrity + informational structure warnings; "
            "strict: geometry + structure warnings as errors + structural low-poly checks (disconnected shells, budget)"
        ),
    )
    parser.add_argument(
        "--lint", action="store_true",
        help="When used with --checks strict, also treat style heuristics (collinear rings, elongated faces, overlapping bounds) as blocking errors",
    )
    parser.add_argument("--json", action="store_true", help="Emit the stable audit report as JSON")
    parser.add_argument("--verbose", action="store_true", help="Print full traceback on recipe failure")
    args = parser.parse_args(argv)
    if args.lint and args.checks != "strict":
        parser.error("--lint only applies together with --checks strict")
    try:
        report = export_project(args.project, recipe=args.recipe, checks=args.checks,
                                lint=getattr(args, "lint", False))
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print_report(report, verbose=args.verbose)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
