# Errors and warnings → fix

Messages below are raised by the code (signatures in the [generated lib reference](../../../../docs/api/lib.md));
this table only maps each message to its cause and fix.

Errors raised while a recipe runs start with `Mesh '<name>':` when they
concern one mesh. `model_export` prints the whole message; `--verbose` adds the
traceback. Only structure warnings block in `--checks strict`.

| Message (start) | Cause | Fix |
|---|---|---|
| `Mesh 'x' has no anchor 'y'; available: ...` | `pivot=`/`placement=` names an anchor the shape lacks | Use a listed name (section names are anchors). |
| `Loft section 'b' has N points but 'a' has M` | profiles differ in point count | `Profile.resample(M)` or equal `segments`. |
| `Loft section 'b' winds opposite to 'a'` | a profile is clockwise | List points counter-clockwise. |
| `Segment sections must start at t=0 and end at t=1` / `distance ... outside the segment length` | first/last section not on the ends | First `t=0`, last `t=1` (a `distance` equal to the length can miss the end by float rounding). |
| `Path sections must advance along the path` | `at`/`point` out of order | Sort sections along the path. |
| `Bone 'x' is connected=True but starts ... away from the end of parent` | socket-like joint | `connected=False`, or start the bone on the parent's end. |
| `Bone 'x' must start on exactly one named ring of mesh 'm' ...; nearest ring 'r' ...` | chain joint is not on a section | Start the bone at `"m:r"`, or add a section at the joint. |
| `Smooth binding ... needs N named ring(s) before/after joint ring` | joint ring at the end of the shape | Add sections around the joint, `blend="tight"`, or `mode="hard"`. |
| `A skinned mesh must be a direct child of its armature` | mesh parented to a group | Create it with parent = the armature name. |
| `Armature mesh 'x' is not bound` / `topology changed; bind it again` | missing/stale `rig.bind` | Bind after the last topology edit. |
| `has inconsistent winding across N edge(s)` / `inward or zero-volume winding` | hand-made faces | Build through `MeshDraft(closed=True)` (orients on build) or call `orient_outward()`. |
| `is marked closed but has N boundary edges` | hole in a closed mesh | Cap or bridge the open ring (`cap`, `connect_rings`). |
| `Face 'f' must be a convex triangle or quad` / `has a collinear corner` | folded or twisted quad | Keep bridged rings in matching order; extrude along the face normal. |
| `Self-intersection between faces ...` | surfaces cross inside one mesh | Move/scale the offending ring; for branches, extrude outward. |
| `Z-fighting coplanar face conflict between 'a' and 'b'` | coincident faces of two elements (often mirrored caps meeting at X=0) | Shrink or offset one of the faces. |
| `Element 'x' is completely submerged inside 'y'` | hidden element | Remove it or let it protrude. |
| WARN `pivot (...) is outside its geometry bounds` / `far from its pivot` | pivot left on the parent origin | Segments, sweeps, lofts and `add_mesh`: `pivot="center"` (or another anchor). Primitives: `placement=Placement.at(...).pivot("center")`. |
| `have overlapping/very close bounds without a shared relation tag` (`--lint`) | intentionally touching parts | `no_overlap_check=True`, or a shared `assembly:<name>` tag. |
| `contains N disconnected shells` (strict) | separate islands in one mesh | Join them, or split into separate elements. |
| `Model uses N faces, exceeding low-poly budget` (strict) | too dense | Fewer segments/sections. |
| `has N highly elongated faces` (`--lint`) | spans much longer than wide | Add intermediate sections. |
| `has near-uniform collinear rings` (`--lint`) | straight tube, no contour | Vary section sizes (taper, bulge). |
| `Model validation failed:` + a list | `model_export` wraps every validation error of the whole model in one message | Fix each listed line; the first names the mesh. |
| `Open mesh 'x' has N boundary edges` (strict) | single-sided sheet such as `add_axis_quad` or an open `MeshDraft` | Intentional for sheets; otherwise close it (`cap`) or pass a closed shape. |
| `Partial coplanar articulation` (WARN) | faces of two parts on the same plane at a joint that rotates | Give one part a slightly different cross-section, or offset it. |
| `non-integer cube dimensions` (box mode) | box or cube sizes/positions not whole numbers | Use integers, or `ModelBuilder(..., require_integer_dimensions=False)`. |
| `Cannot infer the mirrored name of 'x'` | name has no `_L/_R`, `_left/_right`, `.L/.R` suffix | Pass `new_name=`, or name the source `x_L`. |
| `[uv] FAIL <mesh>: polygon collapses at UV density 1` | mesh too small for one pixel per unit | `uv_packer projects/<name> --uv-scale 2 --island-padding 1` (raise if needed). |
| `edge_dilation cannot exceed the UV island_padding` | texture recipe dilates more than the packed padding | Pack with `--island-padding 1` and use `edge_dilation<=1`. |
| `Section 'x' is not where the shape's own 'x' anchor is` | a section is named `base/top/center/start/end` but sits elsewhere | Rename the section (`hip_top`, `mid`). |
| `MODEL_MISSING` (export) | the recipe finished without creating `model.bbmodel` | Make the recipe call `builder.export_bbmodel(...)` from `main()`. |
| `MODEL_NOT_UPDATED` (export) | the recipe ran but did not write `model.bbmodel` | Make the recipe call `builder.export_bbmodel(...)`. |
| `Joint blend rings for 'x' do not span a usable band` | the `before` and `after` rings of a smooth bind coincide | Name rings on either side of the joint ring, or use `blend="tight"`. |
| `cap name 'x' is already used on this draft` | two `MeshDraft.cap` calls with the default name | Pass a different `name=` to each cap. |
| `Face 'f' is degenerate: it has zero area` | collinear or repeated corners (a bowtie or flat quad) | Move a corner off the line or drop the face. |
| `Invalid color ...` / `looks like 0..1 floats` (texture) | color is not `#rrggbb` or a 0-255 tuple | Use `'#rrggbb'` or `(r, g, b[, a])` with integers 0-255. |
| `N triangle face(s) (...): quads are the default` (`add_mesh`) | a hand-made mesh contains triangles | Use quads, or pass `allow_triangles=True` when triangles are intended. |
| `add_cylinder() got an unexpected keyword argument 'pivot'` | primitives take `placement=`, not `pivot=` | `placement=Placement.at(...).pivot("center")`. |
| `Coplanar articulation conflict` | two parts of a joint (a lid on a box, an arm on a torso) have the same cross-section, so their faces coincide when rotated | Make one slightly larger or smaller, or `ModelBuilder(..., check_coplanar=False)` when intended. |
| `is not a polygon mesh (native cubes have no mesh operations ...)` | `scale_mesh`, `place`, `bind` or `edit_mesh` on a native cube | Build the part with `add_box(..., native=False)`, or use a transform group for cubes. |
| `Section 'a' has a concave profile` (extruded L-shape or star) | the flat caps fan around the centre, which needs a convex outline | `start_cap="open", end_cap="open"` plus your own cap, or build the shape from several convex parts. |
