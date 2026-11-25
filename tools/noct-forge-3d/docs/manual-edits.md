# Manual BBModel state and recipe reconciliation

The current BBModel supplies all downstream data. Geometry can remain manually finalized with `ASSET_BUILD_GEOMETRY = "manual"`; this marker suppresses geometry only in the explicit build shortcut. No signature or recipe correspondence is required. See [pipeline](pipeline.md).

## Reconcile when requested

`py -3.12 -m Tools.forge edits PROJECT --asset ID` compares the BBModel with captured recipe results and backs up the edited file under history/. The comparison evaluates recipes in isolation; never run it as automatic prerequisite for UV, painting or animation.

The report lists meshes/cubes/groups, vertex changes and clips. `--full` shows values and generated code; `--emit NAME` limits emitted code; `--only model|animation` scopes comparison. Exit 0 means no differences, 1 differences, 2 failure. `?` indicates unresolved relationships; `!` unsupported/rejected state. No fixes apply automatically.

For replacing captured recipe spans, read [emitted block conventions](../.agents/skills/forge-3d-manual-edits/references/blocks.md).

Find constructor/placement calls by semantic name, adjust parameters or use MeshDraft for edits not expressed by a constructor. Geometry reconciliation does not cover native bone, weight, UV or texture edits; preserve those in the BBModel or report the unsupported reconciliation. Make approximations explicit before any requested regeneration.

## External import

`py -3.12 -m Tools.forge asset import source.bbmodel PROJECT --asset ID` captures a free-format BBModel into a registered project and creates recipes with explicit imported geometry, bones and weights. The importer preserves a source.bbmodel; `--force` backs up replaced files. Recipe verification captures data rather than regenerating the destination BBModel.

The destination must be a registered project: initialize it first with `Tools.forge project init PROJECT --asset ID` (or import into a fresh directory, which is registered in the modern layout automatically). Initialization creates recipes, so replacing those recipes during import requires `--force` even if geometry has not been built.

The recipe reconstruction importer currently requires free format. This limit does not apply to animation on an existing external BBModel. Rebuilding imported geometry subsequently loses imported texture registration: it remains in the preserved source file. Do not rebuild merely because the user supplied a model; choose direct downstream operations or explicit import according to the task.
