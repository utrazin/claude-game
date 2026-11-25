# NoctAssetForge3DBB

Procedural 3D assets with saved Python recipes, editable BBModel intermediates,
independent UV/painting/animation commands, project viewers and engine delivery.

## Setup

Windows with Python 3.12 (the `py` launcher) is the supported setup. The Blockbench desktop app is not required: the entire pipeline (modeling, UV, texturing, animation, 3D viewing and glTF export) runs standalone in Python; Blockbench is purely an optional GUI editor if you wish to inspect or tweak `.bbmodel` files by hand. Node.js LTS is
needed only for glTF validation and the viewer JavaScript checks.

Check this machine, and install what is missing (each command asks `y/N` first):

```powershell
py -3.12 -m Tools.forge doctor            # report only, changes nothing
py -3.12 -m Tools.forge doctor --install  # offers each fix, runs it only on "y"
py -3.12 -m Tools.forge doctor --smoke    # also launches headless Chromium and checks WebGL
```

Manual equivalent:

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -m playwright install chromium
npm ci
```

Double-click `viewer.bat` to open the global viewer over every project in `projects/`.

## Start a collection

```powershell
py -3.12 -m Tools.forge project init projects/characters --asset hero --open
py -3.12 -m Tools.forge asset init projects/characters --asset sword --mode box
```

Init writes deterministic scripts, directories and `project.json`; it does not
build. The shared viewer is ready to select registered assets as soon as they exist.
Edit the registered recipes, then run only requested operations:

```powershell
py -3.12 -m Tools.forge model projects/characters --asset hero
py -3.12 -m Tools.forge uv projects/characters --asset hero
py -3.12 -m Tools.forge texture projects/characters --asset hero
py -3.12 -m Tools.forge animation projects/characters --asset hero
py -3.12 -m Tools.forge view projects/characters --open
py -3.12 -m Tools.forge export projects/characters --asset hero --output engine/hero/idle.glb
```

These are separate commands, not an automatic pipeline. Animation requires only
BBModel controls and its own recipe; painting requires existing UV. Missing inputs
produce an error. UV and downstream operations use the current BBModel, including
manual edits, without consulting the geometry recipe.

The optional `build --stages uv,texture` shortcut executes only selected stages.
Geometry finalized manually uses `ASSET_BUILD_GEOMETRY = "manual"` in the model
recipe. Explicit model regeneration replaces geometry and resets later state;
do it only when requested.

## Agent entrypoints

The `.agents/skills/` folder contains specialized instructions for AI coding agents:
- `forge-3d-orchestrator`: project lifecycle, CLI operations and routing
- `forge-3d-model`: procedural geometry and BBModel generation
- `forge-3d-texture`: procedural UV unwrap and texture painting
- `forge-3d-animation`: procedural animation clips and tracks
- `forge-3d-export`: glTF/GLB packaging and validations
- `forge-3d-manual-edits`: reconciling manual Blockbench GUI edits
- `forge-3d-setup`: dependency check (`Tools.forge doctor`) and permissioned installs

## License

This software is distributed under the terms in [LICENSE](LICENSE). Third-party components and their licenses are listed in [THIRD_PARTY.md](THIRD_PARTY.md). Build information is in [BUILD_INFO.json](BUILD_INFO.json), and file hashes are in [checksums.sha256](checksums.sha256).
