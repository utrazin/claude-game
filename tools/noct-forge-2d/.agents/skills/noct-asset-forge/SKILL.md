---
name: noct-asset-forge
description: Create, modify, check and export programmatic 2D game and UI assets in NoctProceduralAssetForge with the repository's canonical brush or pixel engine. Use for asset code, projects, and the export pipeline.
---

# NoctProceduralAssetForge

This skill defines the production policy for raster assets built with the repository's engines. It does not teach the API. The API is documented per module (see Routing), and the guides explain when to use each module.

Before the first asset in a checkout, run the `noct-setup` skill. For visual checks and sandboxes, use the `noct-review` skill.

## Authority

1. **User prompt**: the requested asset, scope, or explicit request for ideation.
2. **`projects/<project>/source/_theme.ts`**: palette colors, ramps, stroke presets, shape styles.
3. **`projects/<project>/STYLE.md`** (optional): when it exists, it is the style that the theme implements, or the specifications the theme cannot express. See the two flows below.
4. **This document**: universal production rules and quality gates.
5. **Module guides and API reference**: consulted for the module you are using.

### Two flows

- **Style first.** The style is defined before the theme. Write `STYLE.md` (`new-project --style`), then build `source/_theme.ts` from it.
- **Theme first.** The theme exists before anything else. `STYLE.md` is optional here, and when it exists it holds only a summary of the theme plus what the theme cannot express: resolution rules, edge treatment, layering, motion.

Most projects use the theme-first flow. Do not write `STYLE.md` only to have one.

## Routing

Read the guide for a module before using it. Read its API file to get exact signatures. Do not rely on memory for signatures.

| Module | Guide | API reference |
| :--- | :--- | :--- |
| Geometry, primitives, booleans, modeling, placement | [01](../../../core/brush/docs/01-shapes-and-geometry.md) | [brush-geometry](../../../core/docs/api/brush-geometry.md) |
| Paths, lines, curves, `PathBuilder` | [02](../../../core/brush/docs/02-paths-and-lines.md) | [brush-paths](../../../core/docs/api/brush-paths.md) |
| Stroke and shape styles, brushes, themes | [03](../../../core/brush/docs/03-styles-and-themes.md) | [brush-styles](../../../core/docs/api/brush-styles.md) |
| Hatch, stipple, grit, stamps | [04](../../../core/brush/docs/04-procedural-textures.md) | [brush-textures](../../../core/docs/api/brush-textures.md) |
| Spritesheets and atlas packing | [05](../../../core/brush/docs/05-sheets-and-atlas-packing.md) | [core](../../../core/docs/api/core.md) (`packGrid`, `packCompact`) |
| Ideation (exploration before locking a style) | [06](../../../core/brush/docs/06-ideation-and-brainstorm.md) | — |
| Pixel art (`@core/pixel`, `PixelCanvas`) | [07](../../../core/brush/docs/07-pixel-art-engine.md) | [pixel](../../../core/docs/api/pixel.md) |
| Noise, PRNG, math, asset contract, color, theme (`@core`) | [08](../../../core/brush/docs/08-procedural-math-and-noise.md) | [core](../../../core/docs/api/core.md) |

## Engine selection

- `@core/brush`: vector 2D graphics (items, icons, buttons, panels, characters, nature, VFX). Export at `scale: 2`.
- `@core/pixel`: discrete pixel art on an integer grid. Export at `scale: 1` with `antialiasing: 'none'`.
- `@core`: deterministic PRNG, noise, math helpers.

Sizes are logical. The exported image is `width × scale` (per frame, for animations). `width: 96, scale: 2` exports 192 px. Assets are declared with `defineAsset` from `@core`.

For animation, set `frames` (and `fps`). The export writes a horizontal strip of the frames and an atlas JSON with `frame_0..frame_N`. Optional `animations` names ranges of frames, for example `{ idle: [0, 1, 2, 3] }`; the atlas JSON lists them under `meta.animations`. Use `new-asset ... --frames N --fps N` to start from a strip.

`defineAsset` takes `width`, `height`, `scale`, optional `frames`/`fps`/`animations`, `antialiasing` (`'native'`, `'none'`, `'dither'`), and a `render(context)` function that receives `ctx` and `frameIndex`/`frameCount`. The engine creates the canvas. Do not create canvases yourself. The types are in [`core/asset.ts`](../../../core/asset.ts).

---

## Rejection rules

Reject or rewrite code that violates these rules:

- **Project isolation.** Work only inside `projects/<project>/`. Do not read or borrow code from other `projects/*` directories unless the user asks.
- **No legacy patterns.** Do not copy raw Canvas2D coordinate cascades from older assets. Use declarative `@core/brush` builders or `@core/pixel`.
- **No other graphics stacks.** Raw Canvas2D cascades, raw SVG, Rough.js and HTML/CSS layouts are not allowed in asset files.
- **No hardcoded geometry arrays.** Build geometry with `Polygon`, `Path`, `PathBuilder`, transforms, anchors and booleans. Do not concatenate point arrays by hand.
- **No hardcoded styling.** Compose `_theme.ts` tokens, ramps and stroke presets. No stray `#hex` values or renderer settings in asset files.
- **Rotate parts with a pivot.** The `rotation` option of a shape built from free points turns it around the origin, not around the shape. Build the part, then `.rotate(degrees, pivot)`.
- **No fake organic shapes.** For organic forms (terrain, vines, clouds, creatures) build continuous contours, not clusters of circles.
- **No leaking details.** Interior marks, highlights and textures stay inside their host (`inside` callback or a texture on that shape).
- **No baked text.** Official game assets contain no rendered text, labels or numbers. Preview text is allowed only when the user asks for it, and must be removed or guarded with `if (context.preview)` before the official export.

## Quality gates

Every asset is checked against these four criteria before it is delivered:

1. **Theme adherence.** Uses the project's palette, ramps and stroke presets, and matches the art direction in `STYLE.md`.
2. **Form articulation.** Distinct parts (blade, guard, hilt; body, eyes; surface, bevel) are visually separated. No flat monochrome blobs.
3. **Production maturity.** Reads as finished game art, not a wireframe, debug graphic or placeholder.
4. **Technical integrity.** Compiles, exports cleanly at the engine's scale, produces no console errors, has no unintended clipping, and contains no baked typography. The `inspect` command reports the numbers for this gate (see `noct-review`).

## Ideation mode

Ideation runs only when the user asks for it (for example "let's brainstorm" or "explore variations before locking the style"). In that case follow [guide 06](../../../core/brush/docs/06-ideation-and-brainstorm.md): draft 2 to 3 variants in `projects/<project>/temp/`, export and present them, and formalize `STYLE.md` and `_theme.ts` only after the user chooses a direction. Otherwise go straight to production with the existing `STYLE.md` and `_theme.ts`.

---

## Commands

Run commands from the repository root. Use `npm run --silent` whenever you need to parse the output, because npm otherwise prints its own banner on stdout.

| Task | Command |
| :--- | :--- |
| Create a project | `npm run new-project -- <project> [--style] [--doc]` (`--style` adds `STYLE.md`, `--doc` adds `PROJECT.md` for the sandbox) |
| Create an asset | `npm run new-asset -- <project> <subpath> --engine brush\|pixel [--size 128x128] [--frames N] [--fps N]` |
| Check types of one project | `npm run check -- <project>` (add `--json` for parsing) |
| Export official assets | `npm run export -- <project> [subpath] [options]` |
| Export with a JSON summary | `npm run --silent export -- <project> [subpath] [options] --json` |
| Export a mockup (never overwrites official files) | `npm run export -- <project> <subpath> --mockup` |
| List projects and assets | `npm run list -- [project] [--json]` |
| Measure a PNG | `npm run inspect -- <file.png> [--json]` |
| Capture a page of a sandbox | `npm run capture -- projects/<project>/sandboxes/main/ [--at <ms>] [--viewport 800x600] [--out <png>] [--json]` |

Export options: `--grid` or `--compact` for a sheet, `--gap <px>`, `--cols <n>`, `--sheet-name <name>`, `--both`, `--no-json`, `--scale <n>`, `--format png|jpeg`, `--out-dir <path>`. Values can be written as `--gap 8` or `--gap=8`. The full list is `npm run export -- --help`.

Mirroring: `--out-dir` or `outDir` in `projects/<project>/forge.config.json` copies official outputs to another folder. Mockups are never mirrored. The config file accepts only `outDir`, `scale`, `format`, `cols` and `gap`. Any other key is an error.

---

## Production workflow

1. **Project.** If the project does not exist, create it with `new-project`. Read the active project's `_theme.ts`, and `STYLE.md` if it exists.
2. **Asset.** Create the file with `new-asset`, which refuses to overwrite. Files that start with `_` are helpers and are not exported. Build the form with the module guides as reference, then compose the layers and apply styles.
3. **Check.** Run `check -- <project>`. Fix every error in the project before exporting. Errors in other projects are not yours to fix.
4. **Export.** Run the export with `--json` and read the output paths from the summary.
5. **Measure.** Run `inspect` on each official output. Compare the numbers with what the asset should be: bounds, edges, hard or soft alpha, number of colors.
6. **Look.** Open the image with the image viewer (see Harness notes) and review it against the quality gates. For a folder or sheet, review the sheet or two or three representative assets instead of every file.
7. **Polish.** If an asset is crude, flat or off-direction, change geometry, colors or layers, then repeat steps 3 to 6 before finishing.

Mockups are for review only. Use `--mockup` to see sample labels or placeholder content, and remove them before the official export. Mockups are checked with the same steps, but they never go to the game.

---

## Harness notes

- To view a PNG or JPEG, use the `Read` tool with the absolute path printed by the export. Other harnesses may name the image viewer differently. Use whichever tool displays raster images.
- The export never requires a running dev server. The viewer and sandboxes do, and they are covered by the `noct-review` skill.
