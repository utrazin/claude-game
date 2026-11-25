---
name: forge-3d-manual-edits
description: Preserve or reconcile user changes to a BBModel, or import an external BBModel as a Forge3D asset. Use when the user reports editor changes or supplies a model file.
---

# Forge 3D Manual Edits

The edited BBModel is valid working data. Follow the user's choice:

- **Preserve geometry:** set the literal `ASSET_BUILD_GEOMETRY = "manual"` in the registered model recipe. UV, painting, animation and export consume the edited BBModel directly. Do not run edit_diff or regenerate geometry just to continue these stages.
- **Reconcile the recipe:** inspect `Tools.forge edits PROJECT --asset ID` and update the model or animation recipe to represent the requested changes. This comparison explicitly evaluates recipes; it is not a prerequisite for downstream work.

Read [manual edit and import procedures](../../../docs/manual-edits.md) for limitations, backups and reconciliation flags. Model regeneration replaces manual state and resets later data. Run it only when requested; do not automatically run UV, painting or animation afterward.

Animation export replaces only clips declared by its recipe. A user-edited clip must be reconciled or left untouched according to their request. Use `rg` to find recipe calls, then the relevant modeling/animation API reference; do not silently approximate a manual edit without reporting the difference.

For an external BBModel, existing stage commands can operate on the exact file. To reconstruct procedural recipes, use `Tools.forge asset import SOURCE PROJECT --asset ID` after reviewing import constraints. Import and source registration are distinct from executing the model recipe.
