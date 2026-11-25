---
name: forge-3d-model
description: Create or revise NoctAssetForge3D geometry, hierarchy, and rigs with reproducible Python recipes while honoring explicit box-only, free-only, or mixed requests.
---

# Forge 3D Modeler

Geometry lives in the asset's registered recipe, by default `projects/<name>/scripts/<id>/generate_model.py`, a factory
`build_<asset>_model() -> ModelBuilder` whose `main()` calls `export_bbmodel()`.
Its main uses `recipe_paths(__file__).model` as destination. Author with the builder's constructors below. Hand-writing vertex math is the
exception, reserved for shapes no constructor covers (see `custom-mesh.md`) and
for hand edits made in Blockbench (`forge-3d-manual-edits`).

## Conventions (all constructors)
| Topic | Rule |
|---|---|
| Axes & units | Y up, ground at Y=0, model units. The model **front is +Z** (`ModelOrientation` default); the viewer's `front` camera sits on +Z looking at it. |
| Sides | Anatomical suffixes `_L`/`_R` (also `_left`/`_right`, `.L`/`.R`). A character facing +Z has its **left on +X**. Semantic contacts `left`/`right` are *screen* sides of the front view (`right` = +X = the character's left). Suffixes must be at the very end of the name (e.g. `arm_L`, not `left_arm`). |
| Coordinates | Numbers inside shape descriptions (`start`/`end`, `Frame`, `Path3D`, `add_box(at=...)`) are bind-space: rest-pose world coordinates. `Placement.at(number)` and primitives without `placement` are relative to the parent group's pivot; `Placement.at(number, space="world")` is bind-space. Under an armature both are the same. |
| References | `"mesh:anchor"`, `"bone:name"`, `"group:name"`, `"socket:name"` resolve in world space anywhere a point is accepted (bone ends, placements, paths). |
| Profiles | 2D, counter-clockwise, same point count in every section of one shape. For vertical segments in +Y, always pass `y_hint=(0, 0, 1)` so profile +y points toward +Z (model front). Profile axes per constructor: `shapes.md` → *Profile axes*. |
| Topology | Quads by default. Triangles only for apexes, wedges, `add_triangle`, or explicit `allow_triangles=True`/`allow_cap_triangles=True`. |
| Winding | Primitives, lofts and closed `MeshDraft`s are oriented outward automatically. |

> [!WARNING]
> **CRITICAL LATERAL ORIENTATION TRAP ("left" vs "right")**
> - When a character faces `+Z`, anatomical left (`_L`) is in **`+X`**; anatomical right (`_R`) is in **`-X`**.
> - Primitive anchors `"left"` and `"right"` use **screen-space coordinates** (looking at the model from the front):
>   - Anchor `"left"` = `-X` (the character's anatomical **RIGHT** side `_R`!)
>   - Anchor `"right"` = `+X` (the character's anatomical **LEFT** side `_L`!)
> - To avoid attaching limbs to the inverted side, prefer:
>   - Cardinal aliases: `"+x"` (anatomical left), `"-x"` (anatomical right)
>   - Explicit anatomical aliases: `"anatomical_left"` (+X), `"anatomical_right"` (-X)
>   - Or remember: `arm_L` attaches to `torso:right` (or `torso:+x`), NOT `torso:left`!

## Choose a constructor
| Shape | Use | Reference |
|---|---|---|
| Standard solid (cylinder, capsule, cone, sphere, wedge, box…) | `add_<primitive>` | `shapes.md` |
| Straight span with changing cross-sections (torso, neck, head) | `add_segment` + `SegmentSection` (use `y_hint=(0, 0, 1)`) | `shapes.md` |
| Bent span through joints (arm, leg, tail) | `add_sweep(path=Path3D.polyline(...), sections=[PathSection...])` | `shapes.md` |
| Branching or hand-authored topology (thumb off a palm, horn, tail fork) | `MeshDraft` → `add_mesh` | `custom-mesh.md` |
| Cross-sections at free positions/orientations (foot, beak) | `add_loft` + `Section` + `Frame.from_normal` | `shapes.md` |
| Axial lathe form (vase, bottle) | `add_revolve` | `shapes.md` |
| Join separate meshes into one cohesive shell | `builder.combine_meshes(["a", "b"], into="target")` | `shapes.md` |
| Bones, skinning, bilateral rigs | `add_armature`, `rig.add_chain`, `rig.bind`, `builder.mirror` | `rigging.md` |
| Pivots, placing, stacking, mirroring | `pivot=`, `Placement`, `place`, `stack_on`, `mirror` | `placement-and-mirror.md` |
| Box-only / voxel requests | `add_box`, `add_cube`, `add_axis_quad` | `box-modeling.md` |
| An error or warning you do not understand | message → fix table | `errors.md` |

Read only the reference you need. Full constructor signatures are in the
[generated lib reference](../../../docs/api/lib.md); CLI options in the
[generated CLI reference](../../../docs/api/cli.md).

## Commands
```bash
py -3.12 -m Tools.forge project init projects/<name> --asset <id> --mode free
py -3.12 -m Tools.forge model projects/<name> --asset <id> [--checks geometry|standard|strict]
# Step 1: Instant technical pre-flight (bounds, pivots, hierarchy in ~20ms)
py -3.12 -m Tools.forge inspect projects/<name> --asset <id> --validate --summary
# Step 2: Visual clay review (Three.js render side-by-side with reference image)
py -3.12 -m Tools.forge preview projects/<name> --asset <id> [--no-reference --view right|iso|back]
```
- Save a user-supplied reference image as `projects/<name>/reference.<ext>`; the preview shows it side by side.
- `model_export` runs the recipe, overwrites the registered BBModel and audits it (edits made in Blockbench are lost: see `forge-3d-manual-edits`): `PASS` means 0 errors. `standard` blocks on geometry errors; `strict` also blocks on structure warnings, disconnected shells and budget; `--lint` (which needs `--checks strict`) adds style heuristics. Rigged assets: `py -3.12 -m Tools.forge inspect PROJECT --asset ID --skinning-audit`.
- Init creates recipes but never geometry. `model` executes only on explicit request, even when the BBModel is missing. Do not regenerate manually finalized geometry to perform another stage. Read [stage contracts](../../../docs/pipeline.md). Fixes for common messages are in `errors.md`. Clay review is `forge-3d-visual-conformance`, texturing is `forge-3d-texture`.
