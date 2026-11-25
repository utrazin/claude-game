# `lib/` architecture

Agents author assets through the `forge-3d-*` skill references; this file maps
the modules for maintainers. Code-derived signatures are in the
[generated API reference](../docs/api/index.md).

| Module | Owns |
|---|---|
| `model_builder` | `ModelBuilder`: groups, transform groups, sockets, all `add_*` constructors, pivots/placement, `mirror`, `edit_mesh`, armature storage, binding (rigid/hard/smooth/explicit), validation and `.bbmodel` export/import. |
| `armature` | `ArmatureHandle` façade (`add_bone`, `add_chain`, `bind`, `mirror`), `JointBlend`, `BindingReport`. |
| `procedural` | `Profile`, `Section`, `SegmentSection`, `PathSection`, `Path3D` (+ `RelativePath`, `Curve`); `loft` is the single mesh core that `segment`, `sweep`/`path_sections` and the builder methods feed. `revolve` for lathe forms. |
| `primitives` | Closed quad-first generators (cylinder, frustum, prism, cone, pyramid, capsule, spheres, wedge, box, plane/quad/triangle). |
| `geometry_types` | `MeshGeometry` (validated immutable mesh), `MeshDraft` (editable mesh: rings, bridging, extrusion, caps, outward orientation, ring edits), `Placement`, `CapSpec`, `PrimitiveHandle`. |
| `spatial` | `Frame` (profile XY + normal Z), `SpatialFrame` (forward/up attachment frame), `SurfaceContact`, `ModelOrientation` (front/up contract) and vector helpers. |
| `mesh_validation`, `geometry_validation` | Per-mesh topology (convexity, manifoldness, winding, self-intersection) and cross-element conflicts (coplanar faces, submerged parts). |
| `animation` | `AnimationEditor` for native Blockbench clips. |

Invariants: every mesh face is a convex triangle or quad; closed meshes are
manifold and outward; section names are rings and anchors; frames are
right-handed; mirroring keeps faces outward and "up" unchanged.

## Runtime boundaries

`Tools.project_manifest`, `_resolve` and `recipe_context` map project/asset identities
to source and recipe paths. Individual stage CLIs consume existing BBModel data; no
freshness signatures or automatic dependency execution exists. `asset_build` is an
explicit shortcut with a manual geometry policy. See [pipeline](../docs/pipeline.md).

`asset_export` selects immutable delivery copies and target paths; `gltf_export`
converts BBModel geometry, materials and clips into GLB. `viewer_server` scopes the shared Three.js
application to one project. No Blockbench scene export is involved. See
[projects](../docs/projects.md), [exports](../docs/exports.md) and [viewer](../docs/viewer.md).
