# Operating the local kit

## Environment Setup and Dependencies

Before executing any commands, confirm **Node.js (v22+)** is installed (`node -v`). If Node.js is missing, guide the user to install it:
* **Windows**: `winget install OpenJS.NodeJS.LTS` (in PowerShell) or download from [nodejs.org](https://nodejs.org). Note: Restart the terminal if `node -v` is not recognized immediately after install.
* **macOS**: `brew install node` or download from [nodejs.org](https://nodejs.org).
* **Linux**: `nvm install --lts` or NodeSource (`curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs`).

`tools/asset-kit/package.json` and its lockfile pin Three.js, manifold-3d, gltf-validator and Playwright. Canvas, Blob and PNG encoding come from the browser. Node/npm runs the CLI and its local HTTP server.

If `tools/asset-kit/node_modules` is absent (for instance, purged to optimize project disk size):
* Restore packages with `npm install` (or `npm ci`) inside `tools/asset-kit`.

The CLI uses installed Chrome, falling back to Playwright Chromium. If neither exists, install Chromium with `npx playwright install chromium` in the kit directory, respecting environment permissions. Do not depend on a network CDN during asset generation.

Tools use their actual APIs: [Three geometries](https://threejs.org/docs/), [GLTFExporter](https://threejs.org/docs/pages/GLTFExporter.html), [Manifold](https://manifoldcad.org/docs/jsapi/classes/manifold.Manifold.html), [Canvas PNG](https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/toBlob), [validator](https://github.com/KhronosGroup/glTF-Validator), [Playwright downloads](https://playwright.dev/docs/downloads). Check installed definitions before using APIs beyond the supplied examples.

## Suggested project layout

```text
<project>/
  asset-workbench/
    brief.md                 # omit if design.md already holds the same briefing
    assets.json              # only needed by the supplied CLI
    sources/*.js             # reproducible generation code
    checks/                  # reloaded-file screenshots and technical reports
  assets/models/*.glb
  assets/images/*.png
  <engine-specific sources>  # runtime visuals and behavior
```

Use a stable id and edit its source for revisions; do not create a new project or suffix for every generation. Preserve unrelated files. For parallel work assign disjoint sources/outputs; one owner edits the workbench file list. The consuming game does not depend on this kit at runtime.

## File list and generator interface

`asset-workbench/assets.json`:

```json
{"assets":[
  {"id":"fence","kind":"glb","source":"asset-workbench/sources/fence.js","output":"assets/models/fence.glb","size":[2,1,0.12],"tolerance":0.01,"maxTriangles":500},
  {"id":"icon","kind":"png","source":"asset-workbench/sources/icon.js","output":"assets/images/icon.png","size":[128,128],"transparent":true}
]}
```

Paths are relative to the project. IDs and outputs are unique. GLB `size` is optional measured X/Y/Z extent in project units; `tolerance` defaults to 0.01. Optional `clips` lists required animation names. PNG `size` is required. Triangle budgets are project decisions. This list configures the tool, not the visual brief or runtime systems.

Sources export `build(context)` (sync or async). For GLB, context provides `{THREE, loadManifold, manifoldGeometry}`; return an Object3D or `{object, clips}`. For PNG, context provides `{canvas,ctx}` at final dimensions; draw and return. Keep imports within the project, or use the injected APIs. Preview lighting/camera are outside the exported object. See working sources in `examples/estudo-kit-assets/asset-workbench/sources`.

`loadManifold()` loads and sets up WASM lazily. `manifoldGeometry(solid)` copies **positions and triangle indices only** and recomputes smooth normals, yielding one-material geometry. It does not transfer UVs, vertex colors, original material boundaries or authored sharp normals. Use separate solid parts or write explicit attribute mapping when required; use flat shading when suitable. Delete Manifold objects in `finally`, after copying their mesh. Manifold cylinders use Z as height; convert axes deliberately. `levelSet` expects **positive inside**, opposite many published SDF formulas. Bounds must enclose the surface with margin; select edgeLength in project units, starting coarse. Inspect the resulting triangle count and silhouette before increasing detail.

## Commands

On Windows, the default user entry point is **Abrir Visualizador.bat** in the project folder. Create it once with `node tools/asset-kit/cli.mjs launcher "<project>"` from the repository root; regenerate it if the project/kit moves. The preview command also creates a missing launcher. Paths are relative to the batch file, so double-click works independently of the terminal's working directory. Keep the first server window open. Reopening the batch reuses that project's server and opens the same address; the second process exits. Ports occupied by other services are skipped without terminating them.

The viewer receives local change notifications for the file list and its listed sources/outputs. Existing exports are shown by default; the mode selector can show source or exported file explicitly. Reexports reload only the current asset, retaining camera position; changes to assets.json update the menu while preserving selection. Register new assets there with source/output metadata. Writes to inspection reports do not trigger reload loops. Missing exports use source preview in automatic mode; a failed reload keeps the last good image/model and shows the error. Source preview reloads the entry module; edits to imported helper modules may require reopening the page because browser ESM dependencies are cached. A source change does not automatically reexport its output: use the CLI. The viewer's download button only downloads a copy to the browser's download location.

From repository root, replace `<project>` with an actual project path:

```text
node tools/asset-kit/cli.mjs preview "<project>"
node tools/asset-kit/cli.mjs export "<project>" [asset_id]
node tools/asset-kit/cli.mjs verify "<project>" [asset_id]
node tools/asset-kit/cli.mjs check "<project>" [asset_id]
```

`preview` prints a localhost URL; select an asset, orbit and export manually. Append `&file=1` to `?id=<id>` to inspect its exported file. Stop the server with Ctrl+C. `export` and `check` both generate files and run technical checks. `verify` only checks existing exports. All three save reloaded-file screenshots and reports under that project's `checks`; the report covers the selected assets from that invocation. Exit code is nonzero on any failure. Generation overwrites only selected outputs. Run trusted project source only: the browser execution is not an isolation boundary for untrusted code.

Exports use GLTFExporter with binary output and explicit animation clips, or Canvas.toBlob with image/png. Browser downloads are persisted by Playwright to the project's requested paths. PNG bitmap dimensions are independent of CSS/device scaling. Await font/image loading when needed and keep resources local to avoid canvas CORS tainting. Prefer glTF-compatible PBR materials; arbitrary preview shaders and procedural material code do not become portable GLB materials. Bake their appearance into textures or specify engine runtime delivery.

## Acceptance

The CLI validates GLB bytes with the Khronos validator, reopens GLB with GLTFLoader, checks nonempty finite geometry, optional extents/budget/clips; PNG is decoded and checked for dimensions, visible pixels and requested transparency. It produces screenshots, not aesthetic approval. Inspect those images and interact with animated/complex models in preview. Check pivots, forward axis, seams, surface shading and readability in context. Review warnings in `*.gltf.json`; zero validator errors alone does not establish compliance. Runtime visuals must be run and inspected in the actual engine. Destination-engine import is a separate integration check, especially for animation, materials and extensions.
