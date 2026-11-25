# NoctAssetForge3D

Canonical runtime: Official Python (`py -3.12`) on Windows (elsewhere `python3.12` or `python3`). Terminal execution is restricted to saved scripts and CLIs; never run inline Python (`python -c`, stdin).

Read and modify ONLY the active project files and loaded skills. Sibling projects under `projects/` are strictly off-limits unless explicitly requested by the user.

Repository maintenance may inspect and change shared Tools/lib, documentation, skills and tests. Asset work remains scoped to the selected project. Use `project.json` to select the asset; multiple assets require an explicit ID. Recipes receive paths through `Tools.recipe_context`, not fixed folder depths.

The current BBModel is the serialized JSON input to independent UV, painting, animation and export stages, processed entirely by Python without requiring the Blockbench application (which is purely an optional GUI editor for manual tweaks). Never regenerate geometry or run a missing prerequisite unless the user requested it. See `docs/pipeline.md` and `docs/projects.md`.

Start from `.agents/skills/forge-3d-orchestrator`, which routes to the specialized skills in `.agents/skills/`:
- `forge-3d-model`: geometry, hierarchy, rigs
- `forge-3d-visual-conformance`: clay review
- `forge-3d-texture`: surface and UV
- `forge-3d-animation`: clips
- `forge-3d-manual-edits`: changes the user made in Blockbench, and importing a `.bbmodel`
- `forge-3d-visualize`: inspection renders
- `forge-3d-export`: final products, parts and texture variants in chosen assets/ paths
- `forge-3d-setup`: checks this machine's dependencies (`Tools.forge doctor`) and installs missing ones only with the user's permission
