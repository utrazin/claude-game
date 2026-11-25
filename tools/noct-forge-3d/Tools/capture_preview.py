"""
Headless Capture & Visual Inspection CLI for NoctAssetForge3D.

Uses Playwright to capture deterministic, high-resolution orthographic and perspective
screenshots of .bbmodel assets in Three.js, supporting reference image overlays,
side-by-side comparisons, composite turnaround sheets, and project sandbox compositions.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.model_viewer import ModelViewerServer, to_server_url
from Tools.project_manifest import identifier

GOTO_TIMEOUT_MS = 30000


def _load_playwright():
    """Playwright and its Chromium are optional installs; say how to fix a missing one instead of a bare ImportError."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run `py -3.12 -m Tools.forge doctor` to check the setup, "
            "or `py -3.12 -m pip install playwright` then `py -3.12 -m playwright install chromium`."
        ) from exc
    return sync_playwright


def _launch_chromium(playwright):
    try:
        return playwright.chromium.launch(
            headless=True,
            args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-webgl", "--disable-gpu-watchdog"],
        )
    except Exception as exc:
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            raise RuntimeError(
                "Chromium for Playwright is missing. Run `py -3.12 -m Tools.forge doctor` to check the setup, "
                "or `py -3.12 -m playwright install chromium`."
            ) from exc
        raise


def run_server_in_background(host: str = "127.0.0.1", *, project=None, model=None, allowed_files=()) -> tuple[ModelViewerServer, threading.Thread]:
    """Starts a ModelViewerServer in a background daemon thread."""
    server = ModelViewerServer(host=host, port=8900, project=project, model=model, allowed_files=allowed_files)
    thread = threading.Thread(target=server.server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def create_side_by_side_comparison(
    ref_image_path: Path,
    render_image_path: Path,
    output_path: Path,
    label_left: str = "REFERENCE",
    label_right: str = "3D MODEL",
) -> Path:
    """Stitches reference image and 3D render side-by-side with labels."""
    ref_img = Image.open(ref_image_path).convert("RGBA")
    render_img = Image.open(render_image_path).convert("RGBA")

    # Match height
    target_h = render_img.height
    ref_aspect = ref_img.width / ref_img.height
    new_ref_w = max(10, int(target_h * ref_aspect))
    ref_resized = ref_img.resize((new_ref_w, target_h), Image.Resampling.LANCZOS)

    header_h = 36
    total_w = new_ref_w + render_img.width
    total_h = target_h + header_h

    canvas = Image.new("RGBA", (total_w, total_h), (24, 24, 27, 255))
    canvas.paste(ref_resized, (0, header_h))
    canvas.paste(render_img, (new_ref_w, header_h))

    # Divider line
    draw = ImageDraw.Draw(canvas)
    draw.line([(new_ref_w, 0), (new_ref_w, total_h)], fill=(63, 63, 70, 255), width=2)

    # Draw header text labels
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    draw.text((12, 10), label_left, fill=(228, 228, 231, 255), font=font)
    draw.text((new_ref_w + 12, 10), label_right, fill=(228, 228, 231, 255), font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, format="PNG")
    return output_path


def create_turnaround_sheet(
    views_dict: dict[str, Path],
    output_path: Path,
    asset_name: str = "Model",
) -> Path:
    """Creates a 2x2 turnaround sheet collage: Front, Side, Back, Perspective."""
    order = ["front", "right", "back", "iso"]
    loaded = {}
    for v in order:
        p = views_dict.get(v)
        if p and p.exists():
            loaded[v] = Image.open(p).convert("RGBA")
        else:
            # Fallback blank
            loaded[v] = Image.new("RGBA", (800, 800), (24, 24, 27, 255))

    sample = next(iter(loaded.values()))
    w, h = sample.width, sample.height
    header_h = 44
    footer_h = 24

    sheet_w = w * 2
    sheet_h = header_h + (h * 2) + footer_h

    sheet = Image.new("RGBA", (sheet_w, sheet_h), (18, 18, 20, 255))
    draw = ImageDraw.Draw(sheet)

    # Paste 2x2
    sheet.paste(loaded["front"], (0, header_h))
    sheet.paste(loaded["right"], (w, header_h))
    sheet.paste(loaded["back"], (0, header_h + h))
    sheet.paste(loaded["iso"], (w, header_h + h))

    # Grid divider lines
    draw.line([(w, header_h), (w, header_h + h * 2)], fill=(63, 63, 70, 255), width=2)
    draw.line([(0, header_h + h), (sheet_w, header_h + h)], fill=(63, 63, 70, 255), width=2)

    # Labels
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None

    draw.text((16, 14), f"NOCTASSETFORGE3D TURNAROUND SHEET - {asset_name.upper()}", fill=(244, 244, 245, 255), font=font)
    draw.text((12, header_h + 10), "FRONT", fill=(161, 161, 170, 255), font=font)
    draw.text((w + 12, header_h + 10), "SIDE (RIGHT)", fill=(161, 161, 170, 255), font=font)
    draw.text((12, header_h + h + 10), "BACK", fill=(161, 161, 170, 255), font=font)
    draw.text((w + 12, header_h + h + 10), "PERSPECTIVE (ISOMETRIC)", fill=(161, 161, 170, 255), font=font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG")
    return output_path


def capture_views(
    bbmodel_path: Path,
    output_dir: Path,
    views: Sequence[str] = ("iso",),
    texture_path: Path | None = None,
    reference_path: Path | None = None,
    ref_mode: str = "backdrop",
    ref_opacity: float = 0.5,
    ref_scale: float = 1.0,
    ref_offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
    wireframe: bool = False,
    shading: bool = True,
    transparent: bool = False,
    cam_type: str | None = None,
    texture_filter: str | None = None,
    resolution: tuple[int, int] = (800, 800),
    turnaround: bool = False,
    side_by_side: bool = False,
    clip: str | None = None,
    times: Sequence[float] = (0.0,),
) -> dict[str, str]:
    """
    Executes headless Playwright session to capture requested views.
    Returns dictionary of view_name -> absolute file path. With ``clip`` the model is posed at each of ``times``
    (seconds into that animation clip) before every capture; files are then named render_<view>_<clip>_t<time>.png.
    """
    sync_playwright = _load_playwright()

    if not bbmodel_path.exists():
        raise FileNotFoundError(f"Model file not found: {bbmodel_path}")

    known = {"front", "back", "right", "side", "left", "top", "bottom", "iso"}
    unknown = [v for v in views if v not in known and not str(v).startswith("orbit:")]
    if unknown:
        raise ValueError(f"Unknown view {', '.join(map(repr, unknown))}; use front, back, right (side), left, top, bottom, iso, or --orbit YAW PITCH")

    output_dir.mkdir(parents=True, exist_ok=True)
    from Tools._resolve import resolve_asset, resolve_read_model
    _, direct = resolve_read_model(bbmodel_path)
    server, _ = run_server_in_background(project=direct.parent, model=bbmodel_path,
                                         allowed_files=(texture_path, reference_path))

    try:
        query = ["capture=1", f"model={urllib.parse.quote(to_server_url(bbmodel_path))}"]

        if texture_path and texture_path.exists():
            query.append(f"texture={urllib.parse.quote(to_server_url(texture_path))}")

        # Side-by-side uses the reference only during post-processing. Loading
        # it into the scene would contaminate the model-only comparison panel.
        if reference_path and reference_path.exists() and not side_by_side:
            query.append(f"reference={urllib.parse.quote(to_server_url(reference_path))}")
            query.append(f"ref_mode={ref_mode}")
            query.append(f"ref_opacity={ref_opacity}")
            if ref_scale != 1.0:
                query.append(f"ref_scale={ref_scale}")
            if ref_offset != (0.0, 0.0, 0.0):
                query.append(f"ref_offset={ref_offset[0]},{ref_offset[1]},{ref_offset[2]}")

        if wireframe:
            query.append("wireframe=1")
        if not shading:
            query.append("shading=0")
        if transparent:
            query.append("transparent=1")
        if cam_type:
            query.append(f"cam_type={cam_type}")
        if texture_filter is None:
            try:
                texture_filter = resolve_asset(bbmodel_path).texture_filter
            except ValueError:
                texture_filter = "nearest"
        query.append(f"filter={texture_filter}")

        url = f"http://{server.host}:{server.port}/?{'&'.join(query)}"

        # Determine views list
        requested_views = list(views)
        if turnaround:
            for v in ("front", "right", "back", "iso"):
                if v not in requested_views:
                    requested_views.append(v)

        captured_files: dict[str, str] = {}
        views_path_map: dict[str, Path] = {}

        with sync_playwright() as p:
            browser = _launch_chromium(p)
            page = browser.new_page(viewport={"width": resolution[0], "height": resolution[1]})

            # Fail-fast error reporting
            page.on("pageerror", lambda err: print(f"[Browser Error] {err}", file=sys.stderr))

            page.goto(url, timeout=GOTO_TIMEOUT_MS)

            # Wait until model and scene are ready
            page.wait_for_function("window.__FORGE_STATUS__?.state === 'ready' || window.__FORGE_STATUS__?.state === 'error'", timeout=15000)
            status = page.evaluate("window.__FORGE_STATUS__")
            if status["state"] == "error":
                raise RuntimeError(f"Viewer failed to load: {status['error']}")

            # Hide toolbar and UI badges for clean screenshots
            page.evaluate(
                """() => {
                    const tb = document.getElementById('toolbar');
                    if (tb) tb.style.display = 'none';
                    const badge = document.getElementById('model-badge');
                    if (badge) badge.style.display = 'none';
                }"""
            )

            if clip is not None:
                info = page.evaluate(
                    """(name) => {
                        if (typeof animationPlayer === 'undefined' || !animationPlayer) return {error: 'the model has no animation clips'};
                        const clips = animationPlayer.animations.map(item => item.name);
                        const found = animationPlayer.animations.find(item => item.name === name);
                        return found ? {length: found.length, clips} : {error: 'unknown clip', clips};
                    }""",
                    clip,
                )
                if "error" in info:
                    browser.close()
                    raise ValueError(f"{info['error']} {clip!r}; clips in the model: {info.get('clips', [])}")
                late = [t for t in times if t < 0 or t > info["length"] + 1e-9]
                if late:
                    browser.close()
                    raise ValueError(f"time {late[0]:g}s is outside clip {clip!r} (0 to {info['length']:g}s)")
            poses = [None] if clip is None else list(times)

            for view in requested_views:
                page.evaluate(f"window.setView('{view}')")
                for pose in poses:
                    if pose is not None:
                        page.evaluate("([name, t]) => { selectAnimation(name); seekAnimation(t); }", [clip, pose])
                    page.wait_for_timeout(200)

                    safe_view_name = view.replace(":", "_").replace(",", "_")
                    key = safe_view_name if pose is None else f"{safe_view_name}_{clip}_t{pose:g}"
                    out_file = output_dir / f"render_{key}.png"
                    # Screenshot the canvas directly
                    canvas = page.locator("#canvas-container")
                    canvas.screenshot(path=str(out_file), omit_background=transparent)

                    captured_files[key] = str(out_file)
                    views_path_map.setdefault(safe_view_name, out_file)

            browser.close()

        # Post-processing: Side-by-side if reference provided and requested
        if side_by_side and reference_path and reference_path.exists():
            for view in requested_views:
                safe_name = view.replace(":", "_").replace(",", "_")
                base_render = views_path_map[safe_name]
                comp_path = output_dir / f"comparison_{safe_name}.png"
                create_side_by_side_comparison(
                    reference_path,
                    base_render,
                    comp_path,
                    label_left=f"REFERENCE ({reference_path.name})",
                    label_right=f"3D MODEL ({view.upper()})",
                )
                captured_files[f"comparison_{safe_name}"] = str(comp_path)

        # Post-processing: Turnaround sheet if requested
        if turnaround:
            turnaround_file = output_dir / "turnaround_sheet.png"
            create_turnaround_sheet(
                views_path_map,
                turnaround_file,
                asset_name=bbmodel_path.stem,
            )
            captured_files["turnaround_sheet"] = str(turnaround_file)

        return captured_files
    finally:
        server.server.shutdown()
        server.server.server_close()


def capture_sandbox(
    project_target: str | Path,
    sandbox_name: str,
    output_dir_or_file: Path | None = None,
    views: Sequence[str] = ("iso",),
    transparent: bool = False,
    at_ms: int = 0,
    resolution: tuple[int, int] = (800, 800),
) -> dict[str, str]:
    """
    Executes headless Playwright session to capture requested views of a project sandbox.
    Returns dictionary of view_name -> absolute file path.
    """
    sync_playwright = _load_playwright()
    from Tools.sandbox import resolve_project_root

    if at_ms < 0:
        raise ValueError(f"--at must be non-negative, got {at_ms}")

    proj_arg = str(project_target).split("#")[0]
    project_root = resolve_project_root(proj_arg)
    sandbox_name = identifier(sandbox_name)
    sandbox_dir = project_root / "sandboxes" / sandbox_name
    index_html = sandbox_dir / "index.html"
    if not index_html.is_file():
        raise FileNotFoundError(f"Sandbox index.html not found: {index_html}")

    known = {"front", "back", "right", "side", "left", "top", "bottom", "iso"}
    unknown = [v for v in views if v not in known and not str(v).startswith("orbit:")]
    if unknown:
        raise ValueError(f"Unknown view {', '.join(map(repr, unknown))}; use front, back, right (side), left, top, bottom, iso, or --orbit YAW PITCH")

    requested_views = list(views)
    server, _ = run_server_in_background(project=project_root)

    try:
        captured_files: dict[str, str] = {}
        with sync_playwright() as p:
            browser = _launch_chromium(p)
            page = browser.new_page(viewport={"width": resolution[0], "height": resolution[1]})

            page_errors: list[str] = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))
            page.on("console", lambda msg: print(f"[Browser Console] {msg.type}: {msg.text}", file=sys.stderr))

            for view in requested_views:
                safe_view_name = view.replace(":", "_").replace(",", "_")

                if output_dir_or_file is not None:
                    target_p = Path(output_dir_or_file).resolve()
                    if target_p.suffix.lower() == ".png":
                        if len(requested_views) == 1:
                            out_file = target_p
                        else:
                            out_file = target_p.parent / f"{safe_view_name}.png"
                    else:
                        out_file = target_p / f"{safe_view_name}.png"
                else:
                    out_file = sandbox_dir / "renders" / f"{safe_view_name}.png"

                out_file.parent.mkdir(parents=True, exist_ok=True)

                page_errors.clear()
                url = (
                    f"http://{server.host}:{server.port}/sandbox/"
                    f"{urllib.parse.quote(project_root.name)}/{urllib.parse.quote(sandbox_name)}/"
                    f"?capture=1&view={urllib.parse.quote(view)}&transparent={1 if transparent else 0}"
                )

                page.goto(url, timeout=GOTO_TIMEOUT_MS)

                # Wait for scene readiness while watching for page errors
                start_time = time.monotonic()
                while time.monotonic() - start_time < 60.0:
                    if page_errors:
                        browser.close()
                        raise RuntimeError(f"Sandbox JavaScript error: {page_errors[0]}")
                    try:
                        state = page.evaluate("() => window.__FORGE_STATUS__ || {state: 'loading'}")
                        if state["state"] == "error":
                            raise RuntimeError(state["error"])
                        ready = state["state"] == "ready"
                        if ready:
                            break
                    except RuntimeError:
                        raise
                    except Exception:
                        pass
                    page.wait_for_timeout(100)
                else:
                    if page_errors:
                        browser.close()
                        raise RuntimeError(f"Sandbox JavaScript error: {page_errors[0]}")
                    browser.close()
                    raise TimeoutError(
                        "Timed out waiting for sandbox scene to be ready (window.__VIEWER_READY__ === true)"
                    )

                if at_ms > 0:
                    page.wait_for_timeout(at_ms)

                if page_errors:
                    browser.close()
                    raise RuntimeError(f"Sandbox JavaScript error: {page_errors[0]}")

                # Hide UI badges for clean screenshots
                page.evaluate(
                    """() => {
                        const badge = document.getElementById('sandbox-badge');
                        if (badge) badge.style.display = 'none';
                        const tb = document.getElementById('toolbar');
                        if (tb) tb.style.display = 'none';
                    }"""
                )

                page.screenshot(path=str(out_file), omit_background=transparent)
                captured_files[safe_view_name] = str(out_file)

            browser.close()

        return captured_files
    finally:
        server.server.shutdown()
        server.server.server_close()


def parse_views(text: str) -> list[str]:
    """The views of a comma-separated --view list; an orbit view keeps the numbers (and camera) that follow it, so
    ``front,orbit:30,15,iso`` is front, orbit:30,15 and iso."""
    views: list[str] = []
    for token in (t.strip().lower() for t in text.split(",") if t.strip()):
        last = views[-1] if views else ""
        if last.startswith("orbit:") and len(last.split(",")) < 3:
            try:
                float(token)
                is_part = True
            except ValueError:
                is_part = token in ("persp", "ortho", "perspective", "orthographic") and len(last.split(",")) == 2
            if is_part:
                views[-1] = f"{last},{token}"
                continue
        views.append("right" if token == "side" else token)
    return views


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description="Capture headless screenshots & reference comparisons for .bbmodel assets."
    )
    parser.add_argument("bbmodel", type=str, help="Path to .bbmodel file (or project directory/name when using --sandbox)")
    parser.add_argument(
        "--view",
        type=str,
        default="iso",
        help="Comma-separated list of views: front, back, right (side), left, top, bottom, iso, or orbit:yaw,pitch",
    )
    parser.add_argument(
        "--orbit",
        nargs=2,
        type=float,
        metavar=("YAW", "PITCH"),
        help="Custom camera orbit angles in degrees (e.g. --orbit 30 15)",
    )
    parser.add_argument("--out", type=str, default=None, help="Output directory, or a .png path to name the file when exactly one image is produced")
    parser.add_argument("--turnaround", action="store_true", help="Generate 2x2 turnaround sheet")
    parser.add_argument("--sandbox", type=str, default=None, help="Name of project sandbox to capture")
    parser.add_argument(
        "--at",
        type=int,
        default=0,
        help="Additional wait in milliseconds before capture (useful for animation clips and transitions)",
    )
    parser.add_argument("--reference", type=str, default=None, help="Reference image path")
    parser.add_argument(
        "--ref-mode",
        "--reference-display",
        dest="ref_mode",
        type=str,
        default="backdrop",
        choices=["backdrop", "overlay"],
        help="Reference mode in 3D scene",
    )
    parser.add_argument(
        "--ref-opacity",
        "--reference-opacity",
        dest="ref_opacity",
        type=float,
        default=0.5,
        help="Opacity for reference overlay (0.0 to 1.0)",
    )
    parser.add_argument(
        "--ref-scale",
        "--reference-scale",
        dest="ref_scale",
        type=float,
        default=1.0,
        help="Scale multiplier for reference image (default: 1.0)",
    )
    parser.add_argument(
        "--ref-offset",
        "--reference-offset",
        dest="ref_offset",
        type=str,
        default="0,0,0",
        help="Comma-separated offset X,Y,Z for reference image (default: '0,0,0')",
    )
    parser.add_argument(
        "--side-by-side",
        action="store_true",
        help="Generate side-by-side comparison with reference",
    )
    parser.add_argument("--wireframe", action="store_true", help="Render with wireframe overlay")
    parser.add_argument("--unlit", action="store_true",
                        help="Render without scene shading: the texture as it is (default: lit by the viewer's lights)")
    parser.add_argument("--filter", choices=("nearest", "linear"), default=None,
                        help="Texture filtering: nearest (crisp texels) or linear (smooth); "
                             "default is the asset's registered texture_filter, else nearest")
    parser.add_argument(
        "--transparent",
        action="store_true",
        help="Render with transparent background",
    )
    parser.add_argument(
        "--cam-type",
        type=str,
        default=None,
        choices=["persp", "ortho"],
        help="Force camera projection: persp or ortho",
    )
    parser.add_argument("--texture", type=str, default=None, help="Explicit texture path")
    parser.add_argument(
        "--resolution",
        type=str,
        default="800x800",
        help="Capture resolution WIDTHxHEIGHT (default: 800x800)",
    )
    parser.add_argument("--clip", type=str, default=None,
                        help="Pose the model at a moment of this animation clip before capturing")
    parser.add_argument("--time", type=str, default="0",
                        help="With --clip: seconds into the clip, or a comma list such as 0,0.25,0.5 (default: 0)")
    parser.add_argument("--json", action="store_true", help="Output captured paths as JSON")

    args = parser.parse_args(argv)

    if args.sandbox:
        views = parse_views(args.view)
        if args.orbit:
            orbit_view = f"orbit:{args.orbit[0]},{args.orbit[1]}"
            if args.cam_type:
                orbit_view += f",{args.cam_type}"
            if args.view == "iso":
                views = [orbit_view]
            else:
                views.append(orbit_view)

        out_target = Path(args.out).resolve() if args.out else None

        try:
            w_str, h_str = args.resolution.lower().split("x")
            res = (int(w_str), int(h_str))
        except Exception:
            res = (800, 800)

        try:
            results = capture_sandbox(
                args.bbmodel,
                args.sandbox,
                output_dir_or_file=out_target,
                views=views,
                transparent=args.transparent,
                at_ms=args.at,
                resolution=res,
            )
        except Exception as e:
            print(f"Error during sandbox capture: {e}", file=sys.stderr)
            sys.exit(1)

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print("Sandbox capture completed successfully:")
            for k, v in results.items():
                print(f"  [{k}]: {v}")
        return

    from Tools._resolve import resolve_read_model
    _, model_path = resolve_read_model(args.bbmodel)
    if not model_path.exists():
        print(f"Error: Model file '{args.bbmodel}' not found.", file=sys.stderr)
        sys.exit(1)

    views = parse_views(args.view)

    if args.orbit:
        orbit_view = f"orbit:{args.orbit[0]},{args.orbit[1]}"
        if args.cam_type:
            orbit_view += f",{args.cam_type}"
        if args.view == "iso":
            views = [orbit_view]
        else:
            views.append(orbit_view)

    # Parse ref-offset
    try:
        ref_offset_parts = [float(x.strip()) for x in args.ref_offset.split(",")]
        while len(ref_offset_parts) < 3:
            ref_offset_parts.append(0.0)
        ref_offset = (ref_offset_parts[0], ref_offset_parts[1], ref_offset_parts[2])
    except Exception:
        ref_offset = (0.0, 0.0, 0.0)

    # Resolve output directory / file
    if args.out:
        out_target = Path(args.out).resolve()
        if out_target.suffix.lower() == ".png":
            out_dir = out_target.parent
        else:
            out_dir = out_target
    else:
        out_dir = model_path.parent / "renders"

    try:
        clip_times = [float(t) for t in args.time.split(",") if t.strip()] or [0.0]
    except ValueError:
        print(f"Error: --time must be numbers in seconds, got {args.time!r}", file=sys.stderr)
        sys.exit(1)

    ref_path = Path(args.reference).resolve() if args.reference else None
    tex_path = Path(args.texture).resolve() if args.texture else None

    try:
        w_str, h_str = args.resolution.lower().split("x")
        res = (int(w_str), int(h_str))
    except Exception:
        res = (800, 800)

    try:
        results = capture_views(
            model_path,
            out_dir,
            views=views,
            texture_path=tex_path,
            reference_path=ref_path,
            ref_mode=args.ref_mode,
            ref_opacity=args.ref_opacity,
            ref_scale=args.ref_scale,
            ref_offset=ref_offset,
            wireframe=args.wireframe,
            shading=not args.unlit,
            transparent=args.transparent,
            cam_type=args.cam_type,
            texture_filter=args.filter,
            resolution=res,
            turnaround=args.turnaround,
            side_by_side=args.side_by_side,
            clip=args.clip, times=clip_times,
        )
    except Exception as e:
        print(f"Error during capture: {e}", file=sys.stderr)
        sys.exit(1)

    if args.out and Path(args.out).suffix.lower() == ".png":
        # A .png --out names the file only when exactly one image was produced.
        files = [Path(v) for v in results.values() if isinstance(v, str) and v.lower().endswith(".png")]
        wanted = Path(args.out).resolve()
        if len(files) == 1 and len(results) == 1:
            if files[0].resolve() != wanted:
                wanted.parent.mkdir(parents=True, exist_ok=True)
                files[0].replace(wanted)
            results = {key: str(wanted) for key in results}
        else:
            print(f"Warning: --out {args.out} names a single file, but {len(results)} outputs were produced; "
                  f"they were written to {wanted.parent} with generated names.", file=sys.stderr)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("Capture completed successfully:")
        for k, v in results.items():
            print(f"  [{k}]: {v}")


if __name__ == "__main__":
    main()
