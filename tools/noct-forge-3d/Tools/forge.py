"""One discoverable CLI for independent Forge operations: py -3.12 -m Tools.forge."""
from __future__ import annotations

import argparse
import importlib
import sys

COMMANDS = {
    "model": "model_export", "uv": "uv_packer", "texture": "texture_export",
    "animation": "animation_export", "status": "asset_status", "build": "asset_build",
    "inspect": "model_inspector", "preview": "model_preview", "edits": "edit_diff",
    "view": "model_viewer", "export": "asset_export",
    "variant": "texture_variant",
    "capture": "capture_preview", "art": "art", "theme": "theme_tokens",
    "sandbox": "sandbox", "doctor": "doctor",
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        parser = argparse.ArgumentParser(description=__doc__, epilog="Stage commands accept PROJECT --asset ID and their own --help.")
        parser.add_argument("command", choices=("project", "asset", *COMMANDS))
        parser.print_help()
        return 0
    command = argv.pop(0)
    if command == "project":
        action = argv.pop(0) if argv else ""
        if action != "init":
            raise ValueError("Use forge project init PROJECT")
        module = "project_init"
    elif command == "asset":
        action = argv.pop(0) if argv else ""
        if action not in ("init", "import", "twin"):
            raise ValueError("Use forge asset init PROJECT --asset ID, asset import SOURCE PROJECT --asset ID, "
                             "or asset twin PROJECT --asset SOURCE --id TWIN [--mode smooth|pixel] [--sync]")
        module = {"init": "asset_init", "import": "model_import", "twin": "asset_twin"}[action]
    else:
        if command not in COMMANDS:
            raise ValueError(f"Unknown operation {command!r}")
        module = COMMANDS[command]
        # art takes its action before PROJECT: forge art guide PROJECT --asset ID
        action = [argv.pop(0)] if command == "art" and argv and not argv[0].startswith("-") else []
        selectors = [index for index, value in enumerate(argv) if value == "--asset" or value.startswith("--asset=")]
        if selectors:
            if len(selectors) != 1:
                raise ValueError("Select only one asset")
            index = selectors[0]
            if not argv or index == 0 or argv[0].startswith("-"):
                raise ValueError("Use PROJECT --asset ID")
            if argv[index] == "--asset":
                if index + 1 >= len(argv) or argv[index + 1].startswith("-"):
                    raise ValueError("Use PROJECT --asset ID")
                asset_id = argv[index + 1]
                del argv[index:index + 2]
            else:
                asset_id = argv.pop(index).split("=", 1)[1]
            if not asset_id:
                raise ValueError("Asset ID cannot be empty")
            argv[0] = f"{argv[0]}#{asset_id}"
        argv = action + argv
        if command == "view" and "--export-html" not in argv and "--serve" not in argv:
            argv.append("--serve")
    return importlib.import_module(f"Tools.{module}").main(argv) or 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        print(f"[forge] FAIL {exc}", file=sys.stderr)
        raise SystemExit(2)
