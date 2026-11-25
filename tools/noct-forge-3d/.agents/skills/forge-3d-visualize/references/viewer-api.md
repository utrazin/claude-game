# Visualizer & Capture CLI Specification

Complete options for every command are captured from the code in the
[generated CLI reference](../../../../docs/api/cli.md). This page keeps the
command forms, the common options and the camera presets.

All commands accept registered `PROJECT#ID` or exact BBModel paths. The facade
`Tools.forge capture PROJECT --asset ID` forwards the same options. Interactive
`Tools.forge view PROJECT --open` discovers assets from that project's manifest.
Global `Tools.forge view --all --open` or `viewer.bat` explores all projects in `projects/`.
See [viewer contracts](../../../../docs/viewer.md) for automatic refresh and
project boundaries. None of these commands generate missing geometry.

## 1. Headless Capture (`Tools.capture_preview`)
```bash
py -3.12 -m Tools.capture_preview <bbmodel> [options]
# Or via forge CLI:
py -3.12 -m Tools.forge capture PROJECT --asset ID [options]
py -3.12 -m Tools.forge capture PROJECT --sandbox NAME [options]
```

### Common options
| Argument | Meaning |
|---|---|
| `--sandbox NAME` | Name of project sandbox to capture (first positional argument is the project) |
| `--at MS` | Additional wait in milliseconds before capture (useful for clips and transitions) |
| `--view front,back,right,left,top,bottom,iso` | Comma-separated views (default `iso`) or `orbit:yaw,pitch` |
| `--turnaround` | 2x2 collage (`turnaround_sheet.png`) |
| `--clip NAME --time 0,0.25,0.5` | Pose at clip moment(s) before capturing |
| `--reference PATH [--side-by-side]` | Stitch a reference image next to the render |
| `--out DIR_OR_FILE` | Output image file or directory (default `renders/`) |
| `--texture PATH`, `--wireframe`, `--unlit`, `--transparent`, `--resolution 800x800`, `--json` | Overrides and output settings (`--unlit`: no scene lights, the texture as painted; default is lit by the viewer's lights) |

### Camera Presets
- `front`: Orthographic (Z+ looking along Z-)
- `right` / `side`: Orthographic (X+ looking along X-)
- `back`: Orthographic (Z- looking along Z+)
- `left`: Orthographic (X- looking along X+)
- `top`: Orthographic (Y+ looking along Y-)
- `bottom`: Orthographic (Y- looking along Y+)
- `iso`: Perspective 45° yaw, 30° pitch isometric view

---

## 2. Interactive Viewer & HTML Bundler (`Tools.model_viewer`)
```bash
py -3.12 -m Tools.model_viewer <bbmodel> [options]
# Or via forge CLI:
py -3.12 -m Tools.forge view PROJECT [options]
py -3.12 -m Tools.forge view --all [options]
py -3.12 -m Tools.forge view PROJECT --sandbox NAME [options]
```

### Common options
| Argument | Meaning |
|---|---|
| `--all` | Launch global viewer discovering all projects in `projects/` (port 8765) |
| `--sandbox NAME_OR_PATH` | Open sandbox directly in browser |
| `--serve` / `--port PORT` / `--open` | Local viewer server (default action for `forge view`) |
| `--export-html PATH` | Single-file portable preview (HTML requires one asset) |
| `--view iso,front,right,left,back,top,bottom` | Initial camera (default `iso`) |
| `--texture PATH`, `--reference PATH`, `--variant NAME`, `--wireframe`, `--unlit` | Overrides (`--unlit` starts without scene shading; toggle: Shading) |
