# Pipeline and project implementation handoff

## Objective and current state

Updated 2026-10-03. Implementation and acceptance audit are complete.

The approved objective was to implement independent BBModel stages, multiple assets
per project, deterministic initialization, an automatic project-scoped viewer,
expression variants and controlled arbitrary exports inside assets/. Recipes define
procedural regeneration; the current BBModel supplies downstream working data,
including manual edits. Geometry execution remains explicit.

## Checkpoints

- [x] 0. Initial snapshot of pending work, including scene removal: `774787d`.
- [x] 1. Independent stages, removed signatures, manual geometry policy: `0afa215`.
- [x] 2. Multi-asset manifest, context, init and explicit legacy adoption: `b0fd091`.
- [x] 3. Texture variants, chosen delivery paths, parts and GLB: `23e5b47`.
- [x] 4. Automatic project viewer, asset/texture selectors and refresh: `e022862`.
- [x] 5. Focused skills, separate documentation and end-to-end verification.
  Interim checkpoint: `2f7775a`; final commit records the acceptance audit and fixes.

## Final checkpoint changes

- Eight focused skills, including dedicated export; separate animation API,
  manual-edit procedures and root README. Corrected local documentation paths and
  YAML frontmatter. Historical module contracts are explicitly superseded.
- Repeated init preserves scripts and creates no geometry or extra asset. Init
  --open launches the shared viewer without per-project HTML/JS boilerplate.
- Context chooses the deepest registered recipe directory in mixed legacy/modern
  layouts. Stage selectors support --asset ID and --asset=ID.
- Registration holds an OS lock through read/modify/write, rejects contention
  before mutation and preserves assets after retry. Writable variant path collisions
  across assets and sources under recipe directories are rejected.
- UV refuses to overwrite a model edited during packing. Manual geometry policy
  skips model in the build shortcut but reports a missing BBModel as failure.
- Export protects registered and linked source images. Current BBModel texture
  determines default PNG delivery. Every batch payload/conversion is staged before
  publishing products; publication failures report partial results explicitly.
- Assets-root junctions outside the project are rejected, including legacy layouts.
- GLB uses per-material UV dimensions and correct inverse bind transforms. Viewer
  skinning includes mesh bind/current transforms. Source data remains unchanged.
- Import messaging no longer recommends automatic geometry regeneration.

## Final evidence

Command: `py -3.12 -m Tools.run_tests`

Result at the prior checkpoint: **412 tests passed**, exit code 0, 53.917 seconds.
That count predates removing two converter-specific integration checks. Tests
intentionally exercising invalid CLI flags may print argparse usage; the
authoritative result is the final unittest summary.

Official saved `skill-creator/scripts/quick_validate.py`: all eight skills valid.
Local documentation links resolve; runnable API reference examples execute.
`git diff --check` passed before the final commit.

Meaningful integration coverage includes:

- A manually edited BBModel with a poisoned geometry recipe: animation before UV,
  painting failure without UV, explicit UV/paint and final export all use model data.
- External Bedrock animation without UV, resolution or procedural metadata.
- Five distinct expressions as PNGs, five head-only GLBs and five full GLBs using
  one source model; source bytes and active texture remain unchanged.
- Runtime default uniqueness, duplicate output rejection, path/source protection,
  batch-validation staging and actual Windows junction escape rejection.
- Khronos GLB validation, embedded image bytes, native two-atlas materials/UVs,
  head clips and native skin weights.
- Browser empty state without building, live asset/variant discovery and selection,
  manual BBModel refresh, project isolation, external controls and native two-atlas
  rendering both live and in standalone HTML.
- Node checks of weighted animation under transformed parents and rest restoration.
- A subprocess registration contention test plus successful retry preserving assets.

Current viewer screenshot was visually inspected at
`.runtime/checks/project-viewer.png`. It is an ignored local verification artifact.

The requirement-by-requirement mapping (`docs/completion-audit.md`) and the Portuguese
implementation plan (`docs/plano-evolucao-forge3d.md`) live only in the development
repository; this handoff records the executed state.

## Runtime and documented boundaries

Official Python 3.12: `py -3.12`; never inline Python. Core dependencies are in
requirements.txt. Browser captures use Playwright/Chromium. Development GLB checks
use Node and `npm ci` for gltf-validator.

GLB delivery bakes transform clips, Bezier/Catmull-Rom curves, discontinuous
points and deterministic arithmetic expressions into numeric samples. Molang variables
needing Blockbench project/editor context, effects and custom channels fail explicitly.
See [animation export plan](animation-export-plan.md) for the supported expression
subset and acceptance work still to run. Native multiple textures are supported;
expression override requires one atlas. PNG delivery does not crop/repack. UV packing
supports free/hytale_character; BBModel animation is independent of that restriction.
Recipe reconstruction import is free-format. See [exports](exports.md),
[pipeline](pipeline.md) and [manual edits](manual-edits.md).

Legacy adoption registers the explicitly chosen files in place. Existing sibling
assets were not migrated or regenerated. Same-BBModel tasks must remain serial;
registration has OS locking, and export publication is atomic per file.

## Future agent entry

Start from AGENTS.md and forge-3d-orchestrator. A handoff for asset work supplies the
project path, asset ID/exact BBModel, requested stage, user constraints, manual
geometry policy and desired products. Run only requested stages. Do not treat a
missing file, recipe change or status result as authorization to rebuild geometry.
