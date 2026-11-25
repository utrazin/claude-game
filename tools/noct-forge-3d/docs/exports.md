# Texture variants and asset delivery

Register a variant: `Tools.forge variant PROJECT angry --asset hero`.
Paint it: `Tools.forge texture PROJECT --asset hero --variant angry`.
The saved recipe reads `recipe_paths(__file__).variant` and `.texture`. A non-default
variant does not register itself on the BBModel. `--set-active` explicitly changes its
preview texture. All expressions share the BBModel's existing UVs. Painting never runs
geometry or UV; optional variant-specific recipes are project-relative manifest paths.

Examples (prepend `py -3.12 -m`):

```
Tools.forge export PROJECT --asset hero --output engine/hero/idle.glb --variant default
Tools.forge export PROJECT --asset hero --output engine/heads/angry.glb --include head --variant angry
Tools.forge export PROJECT --asset hero --output engine/expressions/angry.png --variant angry
Tools.forge export PROJECT --asset hero --output any/chosen/path/body.glb --exclude head
```

Output paths are relative to PROJECT/assets and may use arbitrary nested folders.
Directories are created automatically. Paths must remain inside assets after resolving
symlinks/junctions. Source BBModels, registered texture variants and recipe directories
cannot be replaced by exports. Existing products require explicit `--overwrite`.
Export never executes any upstream recipe or changes source BBModel bytes.

Parts accept names, UUIDs or full hierarchy paths. Ambiguous names fail. Selecting a
group includes its descendant geometry, while retaining ancestor transforms and the
skeleton. `--animations idle,walk` selects clips; `--animations ""` omits clips. PNG
delivery copies the complete atlas without cropping or repacking its UVs.

## Reproducible products

Each asset can keep `exports.json` beside its recipes:

```json
{"targets": [
  {"id": "idle", "format": "glb", "output": "engine/hero/idle.glb", "texture_variant": "default", "runtime_role": "default"},
  {"id": "head_angry", "format": "glb", "output": "engine/heads/angry.glb", "include": ["head"], "texture_variant": "angry"},
  {"id": "expression_angry", "format": "png", "output": "engine/hero/angry.png", "texture_variant": "angry"}
]}
```

Run `Tools.forge export PROJECT --asset hero` for these targets, or select repeatable
`--target ID` flags. One target may have runtime_role=default; other products are for
engine logic to select. The exporter does not generate or attach that engine logic.
Export products never become authoring assets automatically.

All selected payloads are validated and staged before any products are published. A
failed selector, missing texture or unsupported format leaves no new products. Publication uses atomic replacement
or creation per file; an operating-system failure during publication reports the
number already published rather than claiming the batch completed.

## Formats and dependencies

GLB embeds PNG/JPEG images, explicit UVs, cubes/polygon meshes, hierarchy, native
armature weights (up to four influences per vertex), and numeric position/rotation/
scale clips. Animation export converts position, rotation and scale, including armature
bones. Catmull-Rom, Bezier and mixed curves are baked at 60 fps by default (`--fps`
changes it), and discontinuous multi-point keys are retained. Deterministic numeric
expressions can use arithmetic, common `math.*` functions, `query.anim_time`,
`query.life_time` and `this` (the previous sampled channel value). Expressions depending
on project variables, editor/camera state, random functions or statements are not
portable without their Blockbench evaluation context and fail with a diagnostic.
Blockbench effects/events and custom channels have no equivalent in glTF and fail
explicitly rather than disappearing. Quads are triangulated only in delivery. See
[the animation export correction plan](animation-export-plan.md) for scope and format
boundaries.
The default scale is 1/16 model units per meter; --scale changes delivery units.
GLB supports native multi-texture materials; variant overrides support single-atlas models and multi-slot UV recipes (`uv_packing.textures`, where a variant can override all slots or a subset such as `angry_face.png`).
Implementation follows the [Khronos glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html).

BBModel exports preserve a selected subset and rewrite texture links for their new
location. PNG exports preserve source pixels. GLB is generated directly from the
current BBModel. `--capabilities` reports supported delivery formats.

Core Python dependencies are in requirements.txt. Viewer capture uses Playwright.
Development checks use Node and `npm ci` for the Khronos GLB validator.
