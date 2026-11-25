---
name: forge-3d-visualize
description: Show existing Forge3D BBModels in the official project viewer, headless multi-angle captures, turnarounds, reference comparisons or standalone HTML previews.
---

# Forge 3D Visualize

Read existing BBModel and GLB data without building or changing it. The official implementation is shared; viewers support both single-project scoped viewing and repository-wide global exploration with double-click `viewer.bat`.

```bash
# Global viewer across all repository projects
viewer.bat
py -3.12 -m Tools.forge view --all --open

# Scoped project viewer & single asset captures
py -3.12 -m Tools.forge view PROJECT --open
py -3.12 -m Tools.forge preview PROJECT --asset ID
py -3.12 -m Tools.forge capture PROJECT --asset ID --turnaround
py -3.12 -m Tools.forge capture PROJECT --asset ID --view front --clip idle --time 0,0.25,0.5
py -3.12 -m Tools.forge view PROJECT --asset ID --export-html PROJECT/renders/preview.html
```

Choose viewer for interaction, preview for one inspection image, capture for multiple angles/poses, standalone HTML for a portable preview. Empty assets show an empty state; missing geometry never authorizes regeneration. The project viewer converts the current BBModel directly, including manual edits, native textures and clips.

## Multi-Asset Sandboxes

When inspecting multiple assets together (e.g. dioramas, environments, scale comparisons, character interactions), create a dedicated sandbox instead of modifying individual assets:

```bash
# 1. Create sandbox
py -3.12 -m Tools.forge sandbox PROJECT NAME

# 2. Compose scene in PROJECT/sandboxes/NAME/index.html
# Use forge.add(assetId, { position, rotationY, scale, clip, glb, variant })
# Call forge.frame() and forge.ready()

# 3. View or capture
py -3.12 -m Tools.forge view PROJECT --sandbox NAME --open
py -3.12 -m Tools.forge capture PROJECT --sandbox NAME --view iso --out renders/
```

Inside `sandboxes/NAME/index.html`:
```javascript
const forge = await ForgeSandbox.create(document.getElementById('app'));
await forge.add('hero', { position: [0, 0, 0], clip: 'idle' });
await forge.add('sword', { position: [1.5, 0, 0], rotationY: 45 });
forge.frame();
forge.ready();
```

Sandboxes auto-hot-reload on asset changes while preserving OrbitControls camera position in `sessionStorage`.

Read [project viewer](../../../docs/viewer.md) for discovery, file refresh and project boundaries. Read [CLI options](references/viewer-api.md) for reference overlays, orbit cameras and capture settings (complete options: [generated CLI reference](../../../docs/api/cli.md)). `Tools.forge inspect PROJECT --asset ID` provides numeric bounds/hierarchy when needed. Artistic critique uses `forge-3d-visual-conformance`.

Preserve source files. Rendering outputs are distinct from final products; GLB/PNG delivery uses `forge-3d-export`. Starting a project viewer requires no per-project HTML, JS or server boilerplate.
