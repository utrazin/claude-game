# Rigging: armature, bones, skinning, bilateral rigs

Full signatures (`ArmatureHandle`, `ModelBuilder.add_armature`, `bind`, `mirror`):
[generated lib reference](../../../../docs/api/lib.md).

Two kinds of animation control exist:
- **Armature bones** (`builder.add_armature`) deform polygon meshes through
  weights. Use them for characters and anything that bends.
- **Transform groups** (`add_transform_group`, `add_transform_chain`) move
  their children rigidly. Use them for mechanisms and box-mode models.
A mesh is controlled by one or the other, never both.

> [!IMPORTANT]
> **Kinematics: Forward Kinematics (FK) vs. Inverse Kinematics (IK)**
> Model recipes build **FK** rigs: armatures, parent hierarchies and weight bindings (`rig.bind()`). There is no IK constraint to declare on the model; never call methods like `rig.add_ik()` or `armature.set_ik_controller()`.
> IK belongs to the animation stage: `clip.chain(start, end).reach(...)` / `.aim(...)` solves it in the animation recipe and bakes ordinary rotation keys (see `forge-3d-animation`). Name bones and place joints so chains read naturally: a leg is `thigh -> shin` (tip = shin tip), an arm `upper_arm -> forearm`, with a visible rest bend at knees and elbows.

## Minimal humanoid leg (both sides)
```python
# runnable: skinned, mirrored leg
from lib import ModelBuilder, Path3D, PathSection, Profile, SegmentSection

builder = ModelBuilder("biped", require_integer_dimensions=False)
rig = builder.add_armature("rig")                      # create before the meshes it owns
builder.add_segment("pelvis", "rig", start=(0, 15, 0), end=(0, 19, 0), y_hint=(0, 0, 1),
    sections=[SegmentSection(n, t, Profile.oval(2.4, 1.3, 1.7, segments=8))
              for n, t in (("crotch", 0), ("hips", 0.5), ("waist", 1))])
leg = Path3D.polyline([(1.6, 17.0, 0), (1.6, 16.4, 0), (2.3, 10.4, 0.05), (3.0, 2.0, -0.2), (3.0, 1.2, -0.2)])
builder.add_sweep("leg_L", "rig", path=leg, y_hint=(0, 0, 1), sections=(
    PathSection("cap", Profile.circle(1.1), point=0),
    PathSection("hip", Profile.circle(1.4), point=1),
    PathSection("knee", Profile.oval(1.0, 1.1, 0.95), point=2),      # asymmetric is fine
    PathSection("calf", Profile.oval(1.1, 0.9, 1.4), at=10.0),
    PathSection("ankle", Profile.circle(0.6), point=3),
    PathSection("tuck", Profile.circle(0.5), point=4),
))
rig.add_bone("hips", between=("pelvis:crotch", "pelvis:waist"))
rig.add_chain("leg_chain_L", joints=("leg_L:hip", "leg_L:knee", "leg_L:ankle"),
              names=("thigh_L", "shin_L"), parent="hips", connected=False)
builder.mirror("thigh_L")      # bones thigh_R/shin_R + chain leg_chain_R
builder.mirror("leg_L")        # mesh leg_R
rig.bind("pelvis", bone="hips")
for side in ("L", "R"):
    rig.bind(f"leg_{side}", mode="hard", chain=f"leg_chain_{side}")
```

## Bones
- `rig.add_bone(name, between=(start, end), parent=None, connected=True)` and
  `rig.add_chain(chain_name, joints=(j0, j1, ..., jN), names=(b1, ..., bN), parent=, connected=)`
  (N+1 joints make N bones; only the first bone takes `connected`).
- Joints accept literal points or references. Point bones at section anchors
  (`"leg_L:knee"`): the coordinates live in one place, and hard binding finds
  the ring automatically.
- `connected=True` requires the bone to start exactly on its parent's end.
  Joints beside the parent's tip (shoulder off the chest, hip off the pelvis,
  a foot nudged forward) need `connected=False`; the error names the gap.
- Meshes bound to an armature must be its direct children
  (`add_*(name, "rig", ...)`).
- `builder.armature("rig")` returns the handle of an existing armature, so code
  can address it without the variable that created it. `rig.register_chain(name,
  bones)` names existing bones (root first) so `bind(chain=name)` can use them;
  `Tools.model_import` prints it.

## Binding (`rig.bind`)
| Intent | Call | Result |
|---|---|---|
| Rigid part | `rig.bind(mesh, bone="head")` | every vertex weight 1.0 on one bone |
| One shell over a chain, PSX-style hard split | `rig.bind(mesh, mode="hard", chain="leg_chain_L")` | each vertex goes to its nearest bone of the chain; the ring each child bone starts on goes wholly to the child (`joint_owner="parent"` flips that) |
| Smooth joint | `rig.bind(mesh, mode="smooth", chain=..., blend="tight"/"soft", curve="smooth"/"linear")` | blends between the named rings 1 (tight) or 2 (soft) before/after each joint ring |
| Explicit | `rig.bind(mesh, mode="explicit", weights={vertex: {bone: w}})` | up to 4 influences summing to 1 |

Chain bindings match every child bone's start to a named ring of the mesh:
the section anchor when the ring has one (loft/segment/sweep sections,
`ring_from_profile`), otherwise the ring centroid, within 1e-5. `chain=` may be
a registered chain name or a tuple of bone names in parent→child order. Bind
after the final topology; any later topology edit requires binding again.

## Bilateral rigs
Build one side, then `builder.mirror(name)`: for a bone it mirrors the whole
subtree, renames `_L`↔`_R` (also `_left`/`_right`, `.L`/`.R`) and registers
the mirrored chains; for a mesh it mirrors the element.
**Note on naming:** Bilateral suffixes must be placed strictly at the **end** of the identifier (e.g. `arm_L`, `shin_left`, not `left_arm` or `arm_L_box`), otherwise `builder.mirror` cannot deduce the mirrored counterpart.
Mirror bones before the first `bind`, and bind each mirrored mesh afterwards. When a mesh and a
bone share a name, pass `kind="element"` or `kind="bone"`.

## Checking a rig
`py -3.12 -m Tools.forge inspect PROJECT --asset ID --skinning-audit`
lists each mesh's mode, dominant bones and non-local weight leaks.
Animation clips are authored afterwards with `forge-3d-animation`.
