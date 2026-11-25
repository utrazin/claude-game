---
name: noct-review
description: Verify NoctProceduralAssetForge outputs before delivery. Covers the verification ladder, the numeric inspect command, the global viewer, per-project sandboxes for layouts and states, and mockups. Use after an export, when a UI layout or state must be checked, or when the user asks to see or review assets.
---

# Reviewing assets in NoctProceduralAssetForge

This skill covers how to check what was produced. It does not cover writing asset code (see `noct-asset-forge`) or installing the environment (see `noct-setup`).

## Verification ladder

Go up the ladder only as far as the change needs. Each step is cheaper than the next.

1. **Compiles.** `npm run check -- <project>` reports no type errors in the project.
2. **Exported.** `npm run --silent export -- <project> <subpath> --json` exits with code 0, and each output has a path that exists.
3. **Measured.** `npm run inspect -- <output.png> --json` returns numbers that match what the asset should be (see below).
4. **Looked at.** Open the output with the image viewer (the `Read` tool, using the absolute path from the export). Judge form, color and style against `STYLE.md`.
5. **In context.** Open the viewer or a sandbox in a browser, only when the asset is part of a layout or a state. See the sections below.

Do not skip step 3 for sprites. A sprite can look right and still be clipped, have soft edges where hard ones were required, or use more colors than the palette allows.

## Reading `inspect`

| Field | What it means | What to check |
| :--- | :--- | :--- |
| `opaqueBounds` | Smallest rectangle that contains every pixel with alpha > 0 | For a sprite, leave a margin: the content should not fill the whole canvas unless it is a full-bleed background. |
| `reachesEdges` | Which sides of the canvas the content touches | A sprite that reaches an edge is probably clipped. A background is expected to reach all four. |
| `transparentShare` | Fraction of fully transparent pixels | A full-canvas opaque sprite is almost always wrong. |
| `hardEdges` | `true` when every alpha value is 0 or 255 | Pixel art must be `true`. Vector art is usually `false`. |
| `distinctAlphaValues` | Count of alpha levels used | Pixel art should use 2. |
| `distinctOpaqueColors` | Count of distinct colors among opaque pixels | Compare with the palette: a pixel asset that uses far more colors than `_theme.ts` defines has an error. |

`inspect` reads PNG files only, with 8-bit RGB or RGBA. For a JPEG output, use the image viewer and skip this step.

## The viewer

`npm run view` starts the dev server and serves the viewer at `http://localhost:5173`. It lists every project, the sources in `source/`, and the outputs in `assets/`. It does not list mockups in `preview-assets/`. A project with a sandbox gets a `Preview: <project>` link.

Leave the server running while you work. Stop it with Ctrl+C when you are done.

## Sandboxes

A sandbox is an HTML page in `projects/<project>/sandboxes/main/`. It is for composing assets into layouts and for checking states (normal, hover, pressed). It is never an asset and never ships with the game.

- Create one with `npm run new-sandbox -- <project>`. It creates `sandboxes/main/index.html`, a managed HTML page with the session SDK. Everything else is up to you.
- The sandbox is free-form. Use any approach: HTML, CSS, JavaScript, canvas, frame-by-frame animation, transforms on separate sprite parts, rigs, or a flow of screens with buttons and hover states. `PROJECT.md`, if the project has one, gives direction for that sandbox only.
- While `npm run view` runs, outputs are served at `/projects/<project>/assets/`, so a sandbox can read them directly. The atlas JSON written by an animated export lists the rectangle of each frame.
- Creating a sandbox also creates a launcher for it: `sandboxes/main/open.bat` on Windows and `sandboxes/main/open.sh` on macOS and Linux. Open the sandbox with the launcher, or with `npm run view` and the `http://localhost:5173/projects/<project>/sandboxes/main/` URL.
- The launcher and the viewer share one server. The launcher never starts a second server for a sandbox. If `npm run view` is not running, the launcher starts it. Do not start a separate server for a sandbox, and do not change the port.

Use a sandbox when the question is about placement, spacing, or how states look together. Use `inspect` and the image viewer when the question is about one asset.

## Browser access

To see the viewer or a sandbox, use a browser tool that your harness provides. Navigate to the URL above, take a screenshot, and judge it.

Browser panes may not advance animation frames, and some panes refuse a localhost server that the agent started. If the pane does not open the page, do not work around it: use the capture command below. For animation, or when no browser tool is available, use the capture command, which waits for the given time and saves a PNG:

```bash
npm run --silent capture -- projects/<project>/sandboxes/main/ --at 400 --json
```

Capture several times with different `--at` values to see successive frames. Pass a path that starts with `projects/`, not `/projects/`, because Git Bash on Windows rewrites paths that begin with `/`. The command exits with code 1 and lists the page errors when the page logs any.

If neither a browser tool nor the capture command works, say so, and rely on steps 1 to 4 of the ladder.

Do not change files in `assets/` or `preview-assets/` by hand. They are regenerated by the export.

## Mockups

A mockup is an export with `--mockup`. It renders with `context.preview = true` into `projects/<project>/preview-assets/`, so it can show sample labels or placeholder content. The official `assets/` folder and any external `outDir` are never touched by mockups.

Review a mockup with the image viewer, using the path the export prints. Mockups are not listed in the viewer. Delete a mockup folder when it is no longer needed. It is regenerated on the next run.

## Reporting

When you finish a review, report the ladder steps you ran and their results, in that order. A step you did not run must be reported as not run, with the reason.
