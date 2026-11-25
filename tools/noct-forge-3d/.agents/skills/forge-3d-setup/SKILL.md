---
name: forge-3d-setup
description: Check that a computer has what NoctAssetForge3D needs (Python 3.12, pip packages, Playwright Chromium, optional Node validator) and install what is missing only after the user agrees. Use on a new machine, after a fresh clone or distribution unzip, or when a command fails with a missing module, browser or node error.
---

# Forge 3D Setup

One command inspects everything and prints the exact fix for each gap:

```bash
py -3.12 -m Tools.forge doctor
```

It changes nothing by itself. Exit code 0 means ready; 1 means a required item failed.

## What it checks
| Item | Required | Fix |
|---|---|---|
| Python 3.12+ and the `py` launcher | yes | Install from python.org (manual) |
| `Pillow`, `numpy`, `playwright` at the versions in `requirements.txt` | yes | `py -3.12 -m pip install -r requirements.txt` |
| Playwright Chromium (captures, inspection renders) | yes | `py -3.12 -m playwright install chromium` |
| Node + `node_modules/gltf-validator` (GLB validation in export and tests) | no | `winget install --id OpenJS.NodeJS.LTS -e`, then `npm ci` |
| Viewer port 8765 | no | The viewer falls back to the next free port |
| Write access to `projects/` and `.runtime/checks` | yes | Move the repository out of protected folders |

The desktop Blockbench application is **not** a dependency and is not checked by `doctor`. All `.bbmodel` files are parsed, generated, and animated natively by Python code.

## Procedure
1. Run `py -3.12 -m Tools.forge doctor` and show the user the report.
2. If everything required passes, stop. Do not install anything "just in case".
3. For each missing item, tell the user the exact command and what it downloads, and ask permission. Run a fix only after a yes for that command.
4. Install with the user's terminal: `py -3.12 -m Tools.forge doctor --install` asks y/N for each command itself and needs an interactive terminal, so from an agent session suggest the user type `! py -3.12 -m Tools.forge doctor --install`, or run the individual approved command yourself.
5. Rerun `doctor` (add `--smoke` to launch headless Chromium and confirm WebGL) and report the final state. Python itself and Node cannot be silently installed; if Python 3.12 is missing, send the user to python.org.

Never run inline Python for any of this; use the commands above.
