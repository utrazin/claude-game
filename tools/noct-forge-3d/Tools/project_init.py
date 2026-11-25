"""Initialize a multi-asset project."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from Tools.asset_init import init_project, REPO_ROOT
from Tools.project_manifest import load_project


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project")
    parser.add_argument("--asset", help="Initial asset id (default: project name)")
    parser.add_argument("--mode", choices=("free", "box", "mixed"), default="free")
    parser.add_argument("--open", action="store_true", help="Open this project's automatic viewer")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        root = Path(args.project)
        if not root.is_absolute():
            root = REPO_ROOT / root if str(root).startswith("projects") else REPO_ROOT / "projects" / root
        if (root / "project.json").exists() and not args.asset:
            report = load_project(root)
        else:
            report = init_project(root, asset_id=args.asset, mode=args.mode, animation=True)
        if args.json:
            print(json.dumps(report, ensure_ascii=False))
        else:
            print(f"[project] Ready: {args.project}")
            print("[project] .forge-project.lock is a local write lock (git-ignored, safe to delete when no command is running).")
            print(f'Viewer: py -3.12 -m Tools.forge view "{args.project}" --open')
        if args.open:
            import subprocess
            import sys
            subprocess.Popen([sys.executable, "-m", "Tools.model_viewer", str(root), "--serve", "--open"],
                             cwd=REPO_ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (ValueError, OSError, KeyError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
