"""Canonical texture recipe runner and integrity verifier.

Mirrors model_export for the texture stage:
  - Executes scripts/generate_texture.py
  - Requires existing explicit UVs, then verifies the output PNG dimensions
  - Reports [texture] PASS or FAIL with a clear reason

Usage:
  py -3.12 -m Tools.texture_export projects/<name>
  py -3.12 -m Tools.texture_export projects/<name>/model.bbmodel
  py -3.12 -m Tools.texture_export projects/<name> --json
  py -3.12 -m Tools.texture_export projects/<name> --verbose
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from Tools._resolve import resolve_model_target, resolve_recipe, resolve_asset
from Tools.recipe_context import recipe_environment
from Tools.project_manifest import inside
from Tools.TexturePainter.core.bbmodel_parser import BlockbenchModelParser
from Tools.TexturePainter.export import TextureExporter

_TRACEBACK_LINES = 20


def _issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _run_recipe(recipe_path: Path, env: dict, progress: bool) -> tuple[int, list[str]]:
    """Run the recipe and return (exit code, non-empty output lines, stdout and stderr merged).

    With ``progress`` each line is echoed to stderr as it arrives, prefixed ``[recipe]``, followed by
    the elapsed time, so a long paint shows what it is doing (stdout stays free for --json)."""
    started = time.monotonic()
    process = subprocess.Popen(
        [sys.executable, "-u", str(recipe_path)], cwd=REPO_ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        text=True, encoding="utf-8", errors="replace",
    )
    lines: list[str] = []
    assert process.stdout is not None
    with process.stdout:
        for raw in process.stdout:
            line = raw.rstrip()
            if line.strip():
                lines.append(line.strip())
                if progress:
                    print(f"[recipe] {line}", file=sys.stderr, flush=True)
    returncode = process.wait()
    if progress:
        print(f"[recipe] {'finished' if returncode == 0 else 'failed'} in {time.monotonic() - started:.1f}s",
              file=sys.stderr, flush=True)
    return returncode, lines


def texture_export(project: str | Path, *, recipe: str | Path | None = None,
                   variant: str | None = None, output=None, set_active=False,
                   progress: bool = False) -> dict[str, Any]:
    """Paint against existing BBModel UVs without running upstream stages."""
    project_dir, model_path = resolve_model_target(project)
    context = resolve_asset(project)
    variant = variant or context.record.get("default_variant", "default")
    variants = context.record.get("variants", {})
    if variant not in variants and (output or context.record):
        from Tools.texture_variant import register_variant
        register_variant(project, variant, output=output)
        context = resolve_asset(project)
        variants = context.record.get("variants", {})
    record = variants.get(variant, {})
    if output and record and inside(context.project / "assets", output) != inside(context.project, record["path"]):
        raise ValueError("Output conflicts with the registered variant; register a new variant")
    texture_path = inside(context.project, record["path"]) if record else context.texture
    recipe_path = resolve_recipe(project, "texture", recipe or record.get("recipe"))

    if not recipe_path.exists():
        return {
            "status": "fail",
            "issues": [_issue("RECIPE_NOT_FOUND", str(recipe_path))],
        }
    if not model_path.exists():
        return {
            "status": "fail",
            "issues": [_issue("MODEL_MISSING", f"model.bbmodel not found at {model_path}")],
        }

    try:
        BlockbenchModelParser(model_path)
    except Exception as exc:
        return {"status": "fail", "issues": [_issue("UV_REQUIRED", f"{exc}; run Tools.uv_packer explicitly")]}

    register = set_active or variant == context.record.get("default_variant", "default")
    env = recipe_environment(project, texture=texture_path, variant=variant, register_texture=register)
    returncode, lines = _run_recipe(recipe_path, env, progress)
    if returncode:
        tail = "\n".join(lines[-_TRACEBACK_LINES:]) if lines else f"recipe exited with code {returncode}"
        return {
            "status": "fail",
            "issues": [_issue("RECIPE_FAILED", tail)],
            "exit_code": returncode,
        }

    model_data = json.loads(model_path.read_text(encoding="utf-8"))
    slot_paths = TextureExporter.model_slot_png_paths(model_data, texture_path)
    is_single_default = len(slot_paths) == 1 and slot_paths[0][0]["name"] == "default"
    is_default_variant = variant == context.record.get("default_variant", "default")
    if is_single_default:
        missing = [texture_path] if not texture_path.exists() else []
    elif is_default_variant:
        missing = [spath for _, spath in slot_paths if not spath.exists()]
    else:
        missing = [slot_paths[0][1]] if not any(spath.exists() for _, spath in slot_paths) else []

    if missing:
        return {
            "status": "fail",
            "issues": [_issue("TEXTURE_MISSING", f"texture.png not found after recipe at {missing[0]}")],
        }

    # Validate the artifact itself, never compare recipe or layout versions.
    try:
        from PIL import Image
        to_check = [(slot_paths[0][0], texture_path)] if is_single_default else [
            (slot, spath) for slot, spath in slot_paths if spath.exists()
        ]
        for slot, spath in to_check:
            with Image.open(spath) as img:
                if img.format != "PNG" or img.size != (slot["width"], slot["height"]):
                    raise ValueError("PNG dimensions do not match BBModel resolution")
                img.verify()
        resolution = model_data.get("resolution", {})
        from Tools.uv_contract import filter_padding_warning
        warning = filter_padding_warning(context.texture_filter, model_data)
        out_report = {
            "status": "pass",
            "texture": str(to_check[0][1]),
            "resolution": f"{resolution.get('width', '?')}x{resolution.get('height', '?')}",
            "warnings": [warning] if warning else [],
        }
        if not is_single_default:
            out_report["textures"] = {slot["name"]: str(spath) for slot, spath in to_check}
        return out_report
    except Exception as exc:
        return {
            "status": "fail",
            "issues": [_issue("VERIFY_FAILED", str(exc))],
        }


def print_report(report: dict[str, Any], *, verbose: bool = False) -> None:
    if report["status"] == "pass":
        res = report.get("resolution", "")
        tex = Path(report.get("texture", "texture.png")).name
        print(f"[texture] PASS {tex}" + (f" {res}" if res else ""))
        for warning in report.get("warnings", []):
            print(f"  WARN {warning}")
    else:
        print("[texture] FAIL")
        for item in report.get("issues", []):
            msg = item["message"]
            if not verbose and "\n" in msg:
                last = msg.strip().splitlines()[-1]
                print(f"  {item['code']} {last}")
                print("  (run with --verbose for full traceback)")
            else:
                print(f"  {item['code']} {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run texture recipe against existing UVs and validate the PNG."
    )
    parser.add_argument("project", help="Registered project directory: projects/<name>")
    parser.add_argument("--recipe", help="Explicit path to texture recipe script (default: the asset's registered generate_texture.py)")
    parser.add_argument("--variant", help="Named texture alternative; non-default variants do not change the BBModel")
    parser.add_argument("--output", help="New variant PNG path relative to assets/")
    parser.add_argument("--set-active", action="store_true", help="Register this variant as the BBModel preview texture")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON report")
    parser.add_argument("--verbose", action="store_true", help="Print full traceback on recipe failure")
    parser.add_argument("--quiet", action="store_true",
                        help="Do not stream the recipe's output and elapsed time to stderr while it runs")
    args = parser.parse_args(argv)
    try:
        report = texture_export(args.project, recipe=args.recipe, variant=args.variant,
                                output=args.output, set_active=args.set_active, progress=not args.quiet)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print_report(report, verbose=args.verbose)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
