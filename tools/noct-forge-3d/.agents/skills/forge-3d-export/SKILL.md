---
name: forge-3d-export
description: Deliver existing Forge3D BBModels as GLB, PNG or BBModel products, with selected parts, clips, texture variants and chosen paths inside project assets.
---

# Forge 3D Export

Export existing data. Do not run model, UV, painting or animation to fill a missing prerequisite. Read [delivery contracts and examples](../../../docs/exports.md) for target configuration, format support and backend setup. Complete export options: [generated CLI reference](../../../docs/api/cli.md).

`--output` is always relative to `PROJECT/assets/` and cannot leave it (`--output out/crate.glb` writes `PROJECT/assets/out/crate.glb`). To deliver elsewhere, such as an engine folder, export under `assets/` and copy the product yourself. Stage commands also leave `model.bbmodel.bak` (previous BBModel) and `texture.png.bak` next to the asset; they are local recovery copies, not deliverables, and git-ignored.

Select `PROJECT --asset ID`. A source asset, a texture variant and an export product are different identities. Five expressions can share one BBModel and UV layout, producing separate heads, full models or PNG atlases for engine logic.

```bash
py -3.12 -m Tools.forge export PROJECT --asset hero --output engine/hero/idle.glb
py -3.12 -m Tools.forge export PROJECT --asset hero --include head --variant angry --output engine/heads/angry.glb
py -3.12 -m Tools.forge export PROJECT --asset hero --variant angry --output logic/expressions/angry.png
```

Paths are relative to `PROJECT/assets` and may use arbitrary nested folders. Sources and recipes are protected; replacing an existing product requires `--overwrite`. Selecting a part preserves its original UV and required transforms/skeleton; PNG export copies the whole atlas, without implicit cropping or repacking.

Put repeated products in the selected asset's `exports.json`, then export all or repeat `--target ID`. Only one target per source may have `runtime_role: "default"`; the engine chooses alternatives. A nondefault paint variant must not become active on the source BBModel by accident.

Use UUID/full hierarchy paths for ambiguous part names. Use `--animations idle,walk` or `--animations ""` for no clips. Unsupported format features must fail explicitly. `--capabilities` reports supported delivery formats. Completion means the requested products exist and the source BBModel is unchanged; verify GLB reimport when requested.
