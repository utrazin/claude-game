"""
Model Viewer CLI for NoctAssetForge3D.

Provides local Three.js web serving and standalone single-file HTML exporting
for Blockbench .bbmodel assets without modifying or creating per-project HTML files.
"""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import os
import socketserver
import sys
import threading
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWER_DIR = Path(__file__).resolve().parent / "viewer"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from Tools.viewer_server import (ModelViewerServer, is_server_running, probe_health, workspace_id, backend_revision,
                                 GLOBAL_PREFERRED_PORT, GLOBAL_FALLBACK_PORTS)


def export_standalone_html(
    bbmodel_path: Path,
    output_path: Path,
    texture_path: Path | None = None,
    reference_path: Path | None = None,
    default_view: str = "iso",
    wireframe: bool = False,
    texture_filter: str = "nearest",
    shading: bool = True,
) -> Path:
    """
    Bundles the Three.js viewer, .bbmodel JSON and textures into a single,
    100% self-contained HTML file with embedded base64 assets.
    """
    if not bbmodel_path.exists():
        raise FileNotFoundError(f"File not found: {bbmodel_path}")
    if output_path.suffix.lower() != ".html" or output_path.resolve() == bbmodel_path.resolve():
        raise ValueError("Standalone viewer output must be a separate .html file")

    model_data = json.loads(bbmodel_path.read_text(encoding="utf-8"))

    # Resolve texture
    tex_base64 = ""
    if texture_path and texture_path.exists():
        tex_bytes = texture_path.read_bytes()
        tex_base64 = f"data:image/png;base64,{base64.b64encode(tex_bytes).decode('ascii')}"
    else:
        for texture in model_data.get("textures", []):
            if texture.get("source", "").startswith("data:image/"):
                continue
            rel = texture.get("relative_path") or texture.get("path")
            if rel:
                from Tools.project_manifest import find_project
                base_dir = find_project(bbmodel_path) or bbmodel_path.parent.resolve()
                candidate = (bbmodel_path.parent / rel).resolve()
                if not candidate.is_relative_to(base_dir):
                    raise ValueError(f"Linked texture leaves the project directory: {rel}")
                if not candidate.is_file():
                    raise FileNotFoundError(f"Linked texture not found: {candidate}")
                import mimetypes
                mime = mimetypes.guess_type(candidate.name)[0] or "image/png"
                texture["source"] = f"data:{mime};base64,{base64.b64encode(candidate.read_bytes()).decode('ascii')}"
                texture.pop("relative_path", None)
                texture.pop("path", None)

    # Resolve reference image
    ref_base64 = ""
    if reference_path and reference_path.exists():
        ref_bytes = reference_path.read_bytes()
        mime = "image/png" if reference_path.suffix.lower() == ".png" else "image/jpeg"
        ref_base64 = f"data:{mime};base64,{base64.b64encode(ref_bytes).decode('ascii')}"

    # Read JS scripts
    three_js = (VIEWER_DIR / "vendor" / "three.min.js").read_text(encoding="utf-8")
    orbit_controls = (VIEWER_DIR / "vendor" / "OrbitControls.js").read_text(encoding="utf-8")
    gltf_loader_js = (VIEWER_DIR / "vendor" / "GLTFLoader.js").read_text(encoding="utf-8")
    bbmodel_parser_js = (VIEWER_DIR / "js" / "bbmodel_parser.js").read_text(encoding="utf-8")
    animation_player_js = (VIEWER_DIR / "js" / "animation_player.js").read_text(encoding="utf-8")
    asset_loader_js = (VIEWER_DIR / "js" / "asset_loader.js").read_text(encoding="utf-8")
    viewer_app_js = (VIEWER_DIR / "js" / "viewer_app.js").read_text(encoding="utf-8")
    scene_setup_js = (VIEWER_DIR / "js" / "scene_setup.js").read_text(encoding="utf-8")
    reference_plane_js = (VIEWER_DIR / "js" / "reference_plane.js").read_text(encoding="utf-8")
    inspector_js = (VIEWER_DIR / "js" / "inspector.js").read_text(encoding="utf-8")
    template_html = (VIEWER_DIR / "index.html").read_text(encoding="utf-8")

    # Injections
    embedded_script = f"""
    <script>
        window.__EMBEDDED_BBMODEL__ = {json.dumps(model_data).replace('</', '<\\/')};
        window.__EMBEDDED_TEXTURE__ = {json.dumps(tex_base64)};
        window.__EMBEDDED_REFERENCE__ = {json.dumps(ref_base64)};
        window.__VIEWER_OPTIONS__ = {json.dumps({'view': default_view, 'wireframe': wireframe, 'filter': texture_filter, 'shading': shading})};
    </script>
    """

    def inline(js):
        # A literal </script inside inlined code would end the element early.
        return js.replace("</script", "<\\/script")

    bundled = template_html

    def swap(marker, replacement):
        nonlocal bundled
        updated = bundled.replace(marker, replacement)
        if updated == bundled:
            raise ValueError(f"Standalone viewer template is missing marker: {marker}")
        bundled = updated

    session_js = (VIEWER_DIR / "js/forge_session.js").read_text(encoding="utf-8")
    swap('<script src="js/forge_session.js"></script>', f"<script>{inline(session_js)}</script>")
    for href, path in (("/lib/forge-theme.css", "forge-theme.css"), ("/css/workspace.css", "css/workspace.css")):
        swap(f'<link rel="stylesheet" href="{href}">', '<style>' + (VIEWER_DIR / path).read_text(encoding="utf-8").replace("</style", "<\\/style") + '</style>')
    for name, code in (("vendor/three.min.js", three_js), ("vendor/OrbitControls.js", orbit_controls),
                       ("vendor/GLTFLoader.js", gltf_loader_js), ("js/bbmodel_parser.js", bbmodel_parser_js),
                       ("js/animation_player.js", animation_player_js), ("js/asset_loader.js", asset_loader_js),
                       ("js/viewer_app.js", viewer_app_js), ("js/scene_setup.js", scene_setup_js),
                       ("js/reference_plane.js", reference_plane_js), ("js/inspector.js", inspector_js)):
        swap(f'<script src="{name}"></script>', f"<script>{inline(code)}</script>")

    # Insert embedded data before closing body
    swap("<!-- Scripts -->", embedded_script)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(bundled, encoding="utf-8")
    return output_path


def to_server_url(path: Path) -> str:
    """The server validates this path against its active project/explicit files."""
    return "/api/file?"+urllib.parse.urlencode({"path": str(path.resolve())})


def resolve_sandbox_target(sandbox_arg: str, projects_root: Path | None = None, project_hint: str | None = None) -> dict:
    if not sandbox_arg:
        return {"project": "", "name": ""}
    # Strip whitespace, quotes, and accidental escaped trailing slashes/quotes from Windows batch "%~dp0"
    clean_arg = sandbox_arg.strip().strip('"\'').rstrip('\\/')
    raw_path = Path(clean_arg).resolve()
    parts = [p.strip('"\'') for p in raw_path.parts]
    if "sandboxes" in parts:
        idx = len(parts) - 1 - parts[::-1].index("sandboxes")  # the last one: a parent folder may also be called sandboxes
        if idx > 0 and idx + 1 < len(parts):
            project_name = parts[idx - 1].strip('"\'')
            sandbox_name = parts[idx + 1].strip('"\'')
            return {"project": project_name, "name": sandbox_name}

    if (raw_path / "index.html").is_file() and raw_path.parent.name == "sandboxes":
        return {"project": raw_path.parent.parent.name.strip('"\''), "name": raw_path.name.strip('"\'')}

    if project_hint:
        proj_name = Path(project_hint.split("#", 1)[0]).name.strip('"\'')
        return {"project": proj_name, "name": Path(clean_arg).name.strip('"\'')}

    p = Path(clean_arg)
    if len(p.parts) == 2:
        return {"project": p.parts[0].strip('"\''), "name": p.parts[1].strip('"\'')}

    raise ValueError("Sandbox target must specify project/name or an exact sandbox directory")


def global_target_url(host, port, sandbox, projects_root, project_hint) -> str:
    url = f"http://{host}:{port}/"
    if sandbox:
        info = resolve_sandbox_target(sandbox, projects_root=projects_root, project_hint=project_hint)
        if info.get("project") and info.get("name"):
            url += f"sandbox/{urllib.parse.quote(info['project'], safe='')}/{urllib.parse.quote(info['name'], safe='')}/"
    return url


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="NoctAssetForge3D Model Viewer: view .bbmodel in browser or export to standalone HTML"
    )
    parser.add_argument("bbmodel", type=str, nargs="?", default=None, help="Project directory, project#asset or exact .bbmodel")
    parser.add_argument("--all", action="store_true", help="Launch global viewer across all projects in projects/")
    parser.add_argument("--projects-root", type=str, default=None, help="Root directory containing projects (default: projects/)")
    parser.add_argument("--sandbox", type=str, default=None, help="Path or name of sandbox to open directly")
    parser.add_argument("--serve", action="store_true", help="Launch local HTTP web viewer")
    parser.add_argument("--port", type=int, default=None, help="Server port (default: 8080 for a project viewer, 8765 for the global viewer)")
    parser.add_argument("--open", action="store_true", help="Automatically open browser on serve")
    parser.add_argument("--export-html", type=str, metavar="OUT_FILE", help="Export to single standalone HTML file")
    parser.add_argument("--texture", type=str, default=None, help="Explicit texture PNG path")
    parser.add_argument("--reference", type=str, default=None, help="Reference image path")
    parser.add_argument("--view", type=str, default="iso", choices=["iso", "front", "right", "side", "left", "back", "top", "bottom"])
    parser.add_argument("--wireframe", action="store_true", help="Start with wireframe enabled")
    parser.add_argument("--unlit", action="store_true", help="Start without scene shading (toggle: Shading)")
    parser.add_argument("--variant", help="Initial named texture variant in a project viewer")
    parser.add_argument("--filter", choices=("nearest", "linear"), default=None,
                        help="Texture filtering: nearest (crisp texels) or linear (smooth); "
                             "default is the asset's registered texture_filter (toggle: Smooth Texture)")

    args = parser.parse_args(argv)
    if args.view == "side":   # older name of the right view, which the viewer does not know
        args.view = "right"

    # Global mode: --all or missing bbmodel positional argument (unless exporting standalone html)
    if args.all or (args.bbmodel is None and not args.export_html):
        projects_root = Path(args.projects_root).resolve() if args.projects_root else (REPO_ROOT / "projects")
        host = "127.0.0.1"
        explicit_port = args.port is not None
        preferred = args.port if explicit_port else GLOBAL_PREFERRED_PORT
        expected_workspace = workspace_id(projects_root)

        # A viewer of this workspace may already be running on the preferred port or, after a fallback, on a later one.
        scan = [preferred] if explicit_port else range(preferred, preferred + GLOBAL_FALLBACK_PORTS + 1)
        for candidate in scan:
            health = probe_health(host, candidate)
            if health and health.get("protocolVersion") == 2 and health.get("mode") == "global" and health.get("workspaceId") == expected_workspace:
                if health.get("serverRevision") != backend_revision():
                    raise ValueError(f"O servidor na porta {candidate} está desatualizado. Encerre o viewer antigo e abra viewer.bat novamente.")
                target_url = global_target_url(host, candidate, args.sandbox, projects_root, args.bbmodel)
                print(f"Active global viewer already running at http://{host}:{candidate}/")
                print(f"Direct link: {target_url}", flush=True)
                if args.open:
                    webbrowser.open(target_url)
                return 0

        server = ModelViewerServer(host=host, port=args.port, projects_root=projects_root)
        target_url = global_target_url(host, server.port, args.sandbox, projects_root, args.bbmodel)
        print(f"Global Viewer running for projects under: {projects_root}")
        print(f"Direct link: {target_url}", flush=True)
        if args.open:
            webbrowser.open(target_url)
        server.start()
        return 0

    if args.bbmodel is None:
        raise ValueError("Target project, project#asset or .bbmodel file is required")

    from Tools._resolve import resolve_asset, resolve_direct_model
    raw_target = args.bbmodel.split("#", 1)[0]
    target = Path(raw_target).resolve()
    if not (target / "project.json").is_file() and (REPO_ROOT / "projects" / raw_target / "project.json").is_file():
        target = (REPO_ROOT / "projects" / raw_target).resolve()
    is_project = "#" not in args.bbmodel and (target / "project.json").is_file()
    context, model_path, project_root = None, None, target
    if is_project:
        if args.texture:
            context = resolve_asset(args.bbmodel)
            model_path = context.model
    else:
        if args.variant:
            raise ValueError("Texture variants require a registered project; direct .bbmodel files carry no variants")
        try:
            context = resolve_asset(args.bbmodel)
            model_path = context.model
            project_root = context.project
        except ValueError:
            model_path = resolve_direct_model(args.bbmodel)
            project_root = model_path.parent

    texture_path = Path(args.texture).resolve() if args.texture else None
    reference_path = Path(args.reference).resolve() if args.reference else None

    if args.export_html:
        if model_path is None:
            model_path = resolve_asset(args.bbmodel).model
        out_path = Path(args.export_html).resolve()
        result = export_standalone_html(
            model_path,
            out_path,
            texture_path=texture_path,
            reference_path=reference_path,
            default_view=args.view,
            wireframe=args.wireframe,
            shading=not args.unlit,
            texture_filter=args.filter or (context.texture_filter if context else "nearest"),
        )
        print(f"Standalone HTML viewer successfully exported to: {result}")
        if args.open:
            webbrowser.open(result.as_uri())
        return 0

    # Default action or explicit --serve in scoped mode:
    server = ModelViewerServer(port=args.port if args.port is not None else 8080, project=project_root, model=model_path,
                               allowed_files=(texture_path, reference_path))
    query_params = [f"view={args.view}"]
    if context and context.record:
        query_params.append("asset="+urllib.parse.quote(context.asset_id))
    elif context:
        query_params.append("model="+urllib.parse.quote(to_server_url(context.model)))
    if args.variant:
        query_params.append("variant="+urllib.parse.quote(args.variant))
    if texture_path and texture_path.exists():
        query_params.append(f"texture={urllib.parse.quote(to_server_url(texture_path))}")
    if reference_path and reference_path.exists():
        query_params.append(f"reference={urllib.parse.quote(to_server_url(reference_path))}")
    if args.wireframe:
        query_params.append("wireframe=1")
    if args.unlit:
        query_params.append("shading=0")
    if args.filter:
        query_params.append(f"filter={args.filter}")

    if args.sandbox:
        sb_info = resolve_sandbox_target(args.sandbox, projects_root=project_root.parent, project_hint=project_root.name)
        sb_name = sb_info.get("name") or args.sandbox
        url = f"http://{server.host}:{server.port}/sandbox/{urllib.parse.quote(project_root.name, safe='')}/{urllib.parse.quote(sb_name, safe='')}/"
    else:
        url = f"http://{server.host}:{server.port}/?{'&'.join(query_params)}"

    print(f"Project: {project_root.name}")
    print(f"Direct link: {url}", flush=True)

    if args.open:
        webbrowser.open(url)

    server.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
