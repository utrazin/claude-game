# Box modeling

Full signatures (`add_box`, `add_cube`, `add_axis_quad`, transform groups):
[generated lib reference](../../../../docs/api/lib.md).

For explicit box-only, cube, or voxel requests (`ModelBuilder(..., modeling_mode="box")`
rejects polygon meshes). Mixed models may combine these with free meshes.

## Constructors
| Call | Notes |
|---|---|
| `add_box(name, parent, size=(w, h, d), at=point_or_ref, anchor="center", rotation=, inflate=)` | Native cube placed so `anchor` lands on `at`. Anchors: `center`, `base`/`top` (Y), `left`/`right` (X), `front`/`back` (Z), plus aliases `-x`/`+x`, `-y`/`+y`, `-z`/`+z`, `screen_left`/`right`, `anatomical_left`/`right`. |
| `add_cube(name, parent, from_=(x0, y0, z0), to_=(x1, y1, z1), origin=...)` | Native cube by corners. Automatically exposes the same 7 standard anchors and aliases. |
| `add_axis_quad(name, parent, from_=(x, y, z), size=(w, h), normal="+Z")` | Flat rectangular 2D sheet. **The ONLY quad permitted in `box` mode** (retains Blockbench rectangular quad UV backend). Exposes anchor `"center"`. |
| `add_box(..., native=False)` | Same box as a polygon mesh: armature-bindable, no rotation/inflate (free/mixed mode only). |

> [!NOTE]
> For 2D planes/quads in `free` and `mixed` modes, use `add_plane(width, height)` or `add_quad_face(points)`. In `box` mode, only `add_axis_quad` is accepted; free meshes are rejected.

Box and cube coordinates are bind-space (see the conventions table in
`SKILL.md`). Native cubes are never armature-bound; articulate them with
transform groups.

## Rules
| Parameter | Rule | Why |
|---|---|---|
| Dimensions | Positive integers (validated when `require_integer_dimensions=True`) | Pixel-exact box UVs |
| Coordinates | Integers or half-integers | Clean seams |
| `inflate` | 0 for structure, > 0 for outer layers (clothing, armor) | Avoid clipping |
| Coplanar details | Leave clearance from the host face | Z-fighting |

## Articulation
- Parent each moving part to `add_transform_group(name, parent, pivot=joint)`
  with the pivot exactly on the joint plane; the proximal box ends on that
  plane and the distal box starts on it.
- Keep distinct cross-sections at joints so walls do not coincide when rotated.
- `add_transform_chain(name, parent, start=, segments=[ChainSegment(name, length, direction=...)])` (group and socket names get the chain name as a prefix: `tail_s1`)
  builds a whole rigid chain with `<link>_start`/`<link>_end` sockets.
- Position with `at=` anchors, `stack_on`, and transform groups. Note: `builder.place` applies **only** to polygon meshes (`native=False`), not native cubes. Mirror with `builder.mirror`
  (`placement-and-mirror.md`).
