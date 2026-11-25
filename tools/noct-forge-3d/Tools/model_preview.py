"""Render the current model for human visual inspection; never score it."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.capture_preview import capture_views
from Tools._resolve import resolve_read_model


REFERENCE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def find_reference(project: Path) -> Path | None:
    """Return the project-local reference when one was intentionally saved."""
    candidates = sorted(
        path for path in project.iterdir()
        if path.is_file() and path.stem == "reference" and path.suffix.lower() in REFERENCE_EXTENSIONS
    )
    return candidates[0] if candidates else None


def resolve_reference(project: Path, reference: str | None, no_reference: bool) -> Path | None:
    if no_reference:
        return None
    if reference is None:
        return find_reference(project)
    path = Path(reference)
    if not path.is_absolute():
        path = (project / path).resolve()
    if not path.is_file():
        raise ValueError(f"Reference image not found: {path}")
    return path


def preview_project(
    project: str | Path,
    *,
    view: str = "front",
    reference: str | None = None,
    no_reference: bool = False,
    reference_display: str = "side-by-side",
    reference_opacity: float = 0.5,
    reference_scale: float = 1.0,
    reference_offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    resolution: tuple[int, int] = (800, 800),
) -> Path:
    """Write one current inspection image, optionally composed with a reference."""
    root, model = resolve_read_model(project)
    if not model.exists():
        raise ValueError(f"Expected an existing .bbmodel: {model}")
    if not 0.0 <= reference_opacity <= 1.0:
        raise ValueError("reference opacity must be between 0.0 and 1.0")
    if reference_scale <= 0:
        raise ValueError("reference scale must be positive")
    reference_path = resolve_reference(root, reference, no_reference)
    effective_display = reference_display
    if reference_path is None and reference_display == "side-by-side":
        effective_display = "model"
    if effective_display != "model" and reference_path is None:
        raise ValueError("A reference image is required for the selected reference display")

    renders = root / "renders"
    temporary = renders / ".model_preview_tmp"
    try:
        shutil.rmtree(temporary, ignore_errors=True)
        captured = capture_views(
            model,
            temporary,
            views=(view,),
            reference_path=reference_path,
            ref_mode=effective_display if effective_display in {"backdrop", "overlay"} else "backdrop",
            ref_opacity=reference_opacity,
            ref_scale=reference_scale,
            ref_offset=reference_offset,
            side_by_side=reference_path is not None and effective_display == "side-by-side",
            cam_type="ortho",
            resolution=resolution,
        )
        key = f"comparison_{view}" if effective_display == "side-by-side" else view
        output = renders / f"inspection_{view}.png"
        shutil.copy2(captured[key], output)
        return output
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _offset(value: str) -> tuple[float, float, float]:
    parts = [float(part.strip()) for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("reference offset must be X,Y,Z")
    return tuple(parts)  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render one inspection image; visual judgement remains human-led.")
    parser.add_argument("project", help="Canonical project directory: projects/<name>")
    parser.add_argument("--view", default="front", choices=("front", "right", "back", "left", "top", "bottom", "iso"))
    parser.add_argument("--reference", help="Reference path, relative to the project or absolute; default uses reference.*")
    parser.add_argument("--no-reference", action="store_true", help="Render the model alone, even if reference.* exists")
    parser.add_argument("--reference-display", "--ref-mode", default="side-by-side", choices=("model", "side-by-side", "backdrop", "overlay"),
                        dest="reference_display",
                        help="How to show the reference; default is side-by-side when reference.* exists")
    parser.add_argument("--reference-opacity", "--ref-opacity", type=float, default=0.5,
                        dest="reference_opacity", help="Backdrop/overlay opacity from 0.0 to 1.0")
    parser.add_argument("--reference-scale", "--ref-scale", type=float, default=1.0,
                        dest="reference_scale", help="Backdrop/overlay scale")
    parser.add_argument("--reference-offset", "--ref-offset", type=_offset, default=(0.0, 0.0, 0.0),
                        dest="reference_offset", help="Backdrop/overlay offset X,Y,Z")
    parser.add_argument("--resolution", default="800x800", help="WIDTHxHEIGHT (default: 800x800)")
    args = parser.parse_args(argv)
    try:
        width, height = (int(part) for part in args.resolution.lower().split("x", 1))
        output = preview_project(
            args.project, view=args.view, reference=args.reference, no_reference=args.no_reference,
            reference_display=args.reference_display, reference_opacity=args.reference_opacity,
            reference_scale=args.reference_scale, reference_offset=args.reference_offset,
            resolution=(width, height),
        )
    except Exception as exc:
        print(f"[preview] FAIL {exc}")
        return 3
    print(f"[preview] {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
