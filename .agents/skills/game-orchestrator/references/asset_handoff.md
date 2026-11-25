# Project-local asset delivery contract

The consuming project owns its sources, checks and final files. Prefer **GLB for 3D and PNG for 2D**. No external asset repository, allocation pipeline or runtime manifest is required.

## Briefing

Use the existing design.md table, or asset-workbench/brief.md for standalone work. Ask what kind of art the user wants if unspecified. Reuse answers. For each item record ID, appearance/reference, dimensions/origin, delivery, technique/rationale and destination. Declare unit/up axis/forward direction for 3D. Add clips, transparency, seams, attachment points or geometry budgets only when relevant.

- delivery=file: project-relative GLB/PNG output; prefer this when export preserves the requirement.
- delivery=runtime: engine source/resource path and concrete live-state reason. Convenience alone is insufficient. List exported components separately from their live controllers.
- technique: primitives/direct mesh, solid operations, SDF converted to mesh, Canvas, or engine implementation. Match the requested style and necessary topology/control.

## Organization and reproduction

Suggested folders: asset-workbench/sources, asset-workbench/checks, assets/models and assets/images. Respect existing project conventions. Keep IDs/output paths stable on revisions, preserve unrelated files and document regeneration. The kit's optional assets.json is a tool file list, not a mandatory game-runtime registry.

GLB includes required geometry, materials, embedded textures and requested clips, with agreed scale/pivot/orientation. PNG has exact dimensions and requested alpha. Provide sprite metadata only when needed, in the consumer's agreed format. Deliverables use project-relative paths.

## Acceptance and handoff

- Reopen final files; source previews alone are insufficient.
- GLB: Khronos validator with zero errors, examine warnings; verify dimensions/pivot/orientation, appearance and clips. Test destination-engine import at integration.
- PNG: decode, check size, nonempty content and requested transparency; inspect edges, readability and seams.
- Runtime: run the specified behavior in the destination engine. Browser previews do not prove compatibility. Approved runtime work is not a placeholder.
- Report paths, regeneration commands, evidence and failures. Technical passes do not imply visual approval.

Use [game-asset-kit](../../game-asset-kit/SKILL.md) for tools and examples. Projects may use equivalent tools satisfying this contract.
