---
name: game-asset-kit
description: Produce project-local procedural 3D and 2D game assets using browser JavaScript, Three.js, Manifold SDF/solids and Canvas. Choose art technique, export GLB/PNG, and inspect delivered files; distinguish exportable art from runtime effects.
---

# Project Asset Kit

Produce assets inside the consuming project's folder. Prefer **GLB for 3D and PNG for 2D**. The kit is a set of direct library tools, not a required game architecture or a fixed end-to-end pipeline.

## Art intake and decisions

Read the user's request and existing visual direction first. If the art style is unspecified, **ask what kind of art the user wants**, with useful examples (low-poly, clay, realistic, pixel art, flat illustrated) and request visual references when helpful. Do not silently impose a style preset. Reuse answers already provided. Also establish perspective/camera and animation needs when they affect production. Explain which requested visual features the procedural tools can support; do not promise automatic rigging or realism.

For each asset, choose and briefly justify the technique against the user's style and requirements:

| Technique | Good fit | Costs / limits |
| --- | --- | --- |
| Three.js primitives, extrusions, lathe, explicit BufferGeometry | Modular construction, crisp low-poly silhouettes, controlled topology, hard edges and articulated pieces | Detailed organic surfaces can become verbose; author normals, UVs and topology intentionally |
| Manifold solid operations | Closed solids with holes, cuts, unions, extrusion and revolution | WASM lifecycle and conversion; material/UV mapping needs explicit handling |
| SDF -> Manifold levelSet -> mesh -> GLB | Organic blended volumes, erosion, rounded sculptural shapes and procedural surfaces | Sampling resolution and bounds control cost; no automatic UV unwrap, rig or animation-ready topology |
| Canvas 2D -> PNG | Icons, sprites, textures, UI artwork, tile sets, baked effects | Bitmap resolution and alpha must match delivery |
| Runtime engine code/shader | Gameplay-dependent deformation, particles, trails, dynamic terrain or effects whose appearance depends on live state | Must be implemented and tested in the destination engine; browser shader code is not a portable game asset |

Avoid choosing SDF just because it is available. Use the simplest technique that preserves the requested appearance and control. Exportable models can contain several separate meshes; a union is not necessary merely to deliver one GLB. Hybrid construction is fine.

## Exported versus runtime

Record `delivery: file` or `delivery: runtime` in the existing asset briefing, plus technique and a short reason. Prefer files whenever the required behavior survives baking/export. Runtime delivery needs a concrete reason, such as dependence on live gameplay state; convenience or avoidance of export work is insufficient.

Examples: a tree is a GLB, its wind response may be runtime; a smoke sprite is PNG while its emitter is runtime; a water surface can use a GLB plus a destination-engine shader. Do not classify legitimate runtime work as a placeholder or force dynamic behavior into a static image. HUD layout and live text are generally engine controls, with PNG art where useful. Rigid animations, skins and morph clips may be exportable; assess them individually.

## Setup and Prerequisites

Before executing any CLI commands, previews, or exports with the kit:
1. **Node.js Verification**: Run `node -v` to ensure Node.js (v22+) is installed.
   * **If Node.js is missing**: Instruct the user immediately to install it:
     * **Windows**: Run `winget install OpenJS.NodeJS.LTS` in PowerShell or download from [nodejs.org](https://nodejs.org). Note: Restart the terminal if `node -v` is not recognized immediately after install.
     * **macOS**: Run `brew install node` or download from [nodejs.org](https://nodejs.org).
     * **Linux**: Run `nvm install --lts` or install via NodeSource (`curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs`).
     * Halt tool operations until Node.js is confirmed installed.
2. **Kit Dependencies (`node_modules`)**: Check if `tools/asset-kit/node_modules` exists.
   * If missing (e.g., cleared to keep workspace size minimal), restore dependencies by running `npm install` (or `npm ci`) inside `tools/asset-kit`.
   * If headless verification requires Chromium and no local Chrome is present, run `npx playwright install chromium` in `tools/asset-kit`.

## Tools and operation

Read [operations.md](references/operations.md) when producing assets. The installed kit lives at `tools/asset-kit` relative to the repository root. Use Three.js and Canvas directly; load Manifold only when needed. Keep custom helpers local and small. Do not build another framework, schema ecosystem, scene editor or modeling DSL.

All sources, previews, checks and final assets belong to the project. Existing projects may use their own tooling and directory layout. The supplied HTML workbench and CLI are optional conveniences. Its `assets.json` selects local source modules and output paths; **it is not a mandatory game-runtime manifest**. Runtime items stay in the briefing and engine source, outside that file list.

When using the supplied workbench on Windows, provide **Abrir Visualizador.bat in the project folder as the default user entry point**. Generate it with `node tools/asset-kit/cli.mjs launcher "<project>"`. It opens the browser and reuses the existing preview server for that project, including simultaneous launches. The viewer updates listed exports and new file-list entries in place, preserving selection and the current asset's 3D camera; no full-page refresh is needed. New exported assets must be added to the workbench file list. Browser downloads are copies; production CLI exports save to the configured project paths.

Read [the delivery contract](../game-orchestrator/references/asset_handoff.md). Validate files technically, inspect the reloaded outputs visually, and test the destination import when integrating. An automated `passed` result is not visual approval. Report missing capability or failed delivery honestly, preserve sources, and document regeneration. Delegate by asset/family only when requested or required by the active orchestrator; no external repository is required.
