"""Create and scaffold project sandboxes for multi-asset composition: py -3.12 -m Tools.forge sandbox PROJECT NAME."""
from __future__ import annotations

import argparse
import html
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEWER_DIR = Path(__file__).resolve().parent / "viewer"
TEMPLATE_DIR = VIEWER_DIR / "sandbox_template"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools.project_manifest import identifier, find_project


def resolve_project_root(project_arg: str | Path) -> Path:
    target = Path(project_arg).resolve()
    if (target / "project.json").is_file():
        return target
    candidate_in_projects = (REPO_ROOT / "projects" / project_arg).resolve()
    if (candidate_in_projects / "project.json").is_file():
        return candidate_in_projects
    found = find_project(target)
    if found is not None:
        return found
    raise ValueError(f"Project not found: {project_arg}")


def create_sandbox(project: str | Path, name: str) -> Path:
    proj_root = resolve_project_root(project)
    clean_name = identifier(name)

    sandboxes_dir = proj_root / "sandboxes"
    sandbox_dir = sandboxes_dir / clean_name

    if sandbox_dir.exists():
        raise FileExistsError(f"Sandbox already exists: {sandbox_dir}")

    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"Sandbox template directory missing: {TEMPLATE_DIR}")

    sandbox_dir.mkdir(parents=True, exist_ok=False)

    project_label = html.escape(proj_root.name)
    # Copy template files, including subdirectories
    for item in sorted(TEMPLATE_DIR.rglob("*")):
        dest = sandbox_dir / item.relative_to(TEMPLATE_DIR)
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        elif item.name == "index.html" and item.parent == TEMPLATE_DIR:
            content = item.read_text(encoding="utf-8")
            # Customize with project and sandbox name
            content = content.replace("<title>Forge Sandbox</title>", f"<title>{clean_name} — {project_label}</title>")
            content = content.replace('<strong id="badge-title">Forge Sandbox</strong>', f'<strong id="badge-title">{clean_name}</strong>')
            content = content.replace('<div id="badge-subtitle">Multi-asset Scene</div>', f'<div id="badge-subtitle">Project: {project_label}</div>')
            dest.write_text(content, encoding="utf-8")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)

    try:
        rel_path = sandbox_dir.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        rel_path = str(sandbox_dir)

    print(f"[sandbox] Created: {rel_path}")
    print(f"Viewer: py -3.12 -m Tools.forge view --all --open --sandbox {rel_path}")
    print(f"Capture: py -3.12 -m Tools.forge capture {proj_root.name} --sandbox {clean_name}")

    return sandbox_dir


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="Project directory or project ID under projects/")
    parser.add_argument("name", help="Sandbox identifier name")
    args = parser.parse_args(argv)

    create_sandbox(args.project, args.name)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[sandbox] FAIL {exc}", file=sys.stderr)
        sys.exit(1)
