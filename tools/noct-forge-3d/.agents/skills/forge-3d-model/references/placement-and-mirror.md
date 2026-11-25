# Pivots, placement, and mirroring

Full signatures (`Placement`, `SpatialFrame`, `mirror`, `place`, `stack_on`):
[generated lib reference](../../../../docs/api/lib.md).

## Pivot vs placement
Every element has a pivot (its Blockbench origin). Two keywords control it:
`pivot=` works on segments, sweeps, lofts, revolves and `add_mesh`; primitives (`add_cylinder`, `add_box`...) take only `placement=`.

| Keyword | Moves the mesh? | Use |
|---|---|---|
| `pivot="anchor"` | no | Mesh authored where it belongs; put its pivot on one of its anchors (`"center"`, `"knee"`, `"start"`). |
| `placement=Placement.at(target).pivot("anchor")` | yes | Mesh authored at the origin (primitives); move it so `anchor` lands on `target`, which becomes the pivot. |

Default pivots: segments `start`, sweeps and lofts `base` (first section),
primitives `center` placed on the parent pivot, `add_mesh` the parent origin.
Meshes bound to an armature deform through bones, so their pivot is only
cosmetic and never produces warnings.

`Placement.at(target)` accepts a number triple (relative to the parent group's
pivot; `space="world"` for bind space) or a reference (`"torso:top"`,
`"socket:hand_grip"`, `"bone:head"`), which is always world space. A reference is a point on the shape's axis: for a side part (an ear, a hand) use numbers, or `builder.place(element, source=, target=, offset=(dx, dy, dz))`.

## Moving and fitting existing elements
| Call | Effect |
|---|---|
| `builder.stack_on(child, target, axis="+Y", offset=0)` | Butt `child`'s bounds against `target`'s face along `axis`; the other axes are unchanged (to centre it too, use `Placement.at("target:top").pivot("base")`).  |
| `builder.place(element, source="base", target="socket:x", orient=True)` | Align an oriented anchor frame onto a target frame (position and rotation). |
| `builder.add_socket(name, parent, at=..., forward=..., up=...)` | Named attachment frame on a group or bone, referenced as `"socket:name"`. Numbers in `at`, `forward`, `up` are bind-space like box positions, so the socket turns with its group; a reference (`"torso:top"`) is taken where it is after rotation. |
| `builder.translate_element(name, offset)` | Moves an element by `offset` (relative). |
| `builder.rotate_element(name, rotation)` | Sets the element rotation in degrees (absolute: calling it twice with the same value is a no-op). |
| `builder.scale_mesh`, `align_element` | `scale_mesh` scales a polygon mesh only (not native cubes); `align_element` aligns one element to another. |

Prefer building in place (`pivot=`) or `placement=` at creation; use `place`
or `stack_on` for fitting one finished part to another.

## Mirroring
`builder.mirror(source, new_name=None, axis="X", parent=None, kind=None)`
handles every case:
- **Element** – mirrored copy; if its parent group has a side suffix, the
  copy goes under the opposite group.
- **Group** – the whole subtree with meshes and sockets.
- **Armature bone** – the bone subtree, plus every chain inside it.

`new_name` defaults to the side-swapped name (`arm_L`→`arm_R`,
`_left`/`_right`, `.L`/`.R`, `.l`/`.r`); a descendant whose name has no side suffix gets the
new group name as a prefix (`arm_L_box` becomes `arm_R_arm_L_box`), so name limb parts with a side suffix (`box_L`). Faces stay outward and anchor frames keep "up" while their lateral axis
flips. Mirror bones before binding. `kind=` resolves a name shared by a mesh
and a bone. `rig.mirror(bone)` is the same operation limited to bones.

## Posed and bind-space coordinates
`builder.get_anchor(name, anchor)` returns where the anchor is after group rotation (posed). Numbers given to `at=`, `Placement.at(...)` and box positions are bind-space (before rotation). Under a rotated group the two differ, so pass references (`"mesh:anchor"`, `"socket:name"`, which are resolved in the posed frame) instead of feeding `get_anchor` numbers back in as numbers.
