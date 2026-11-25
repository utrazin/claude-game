# Custom meshes: `MeshDraft`

Full signatures (`MeshDraft`, `MeshGeometry`): [generated lib reference](../../../../docs/api/lib.md).

Use a `MeshDraft` for branching or hand-authored topology — typically a branch
growing out of a body (thumb from a palm, horn from a skull), or a form that
would otherwise need several constructors joined. Primitives stay the default
for standard solids and single-path spans. Build rings from profiles, bridge them, extrude branches, cap the
ends, then `builder.add_mesh(name, parent, draft)` (`origin=`, `rotation=`, `tags=`, `shading_mode=`, `visibility=`, `allow_triangles=` also accepted; triangles are refused unless `allow_triangles=True`).

```python
# runnable: mitten hand with a separate thumb
from lib import MeshDraft, ModelBuilder, Profile, Frame

builder = ModelBuilder("hand", require_integer_dimensions=False)
builder.add_group("root")
draft = MeshDraft(closed=True)
down = (0.0, -1.0, 0.0)
# phase=22.5 on 8 points puts a face (vertices 1-2) on profile +y = front (+Z here)
rows = [(0.0, 0.5, 0.6), (0.6, 0.64, 0.9), (1.4, 0.64, 1.0), (2.2, 0.52, 1.0), (3.2, 0.32, 0.7)]
rings = [draft.ring_from_profile(f"r{i}", Profile.oval(th, w, w, segments=8, phase=22.5),
                                 Frame.from_normal((0, -t, 0), normal=down, y_hint=(0, 0, 1)))
         for i, (t, th, w) in enumerate(rows)]
for i, (a, b) in enumerate(zip(rings, rings[1:])):
    draft.connect_rings(a, b, prefix=f"palm{i}", skip=(1,) if i == 1 else ())
draft.cap(rings[0], name="wrist_cap").cap(rings[-1], name="tip_cap")
root = (rings[1][1], rings[1][2], rings[2][2], rings[2][1])      # the open quad
tip = draft.extrude(root, "thumb0", offset=(0, -0.3, 0.55), scale=0.8)
tip = draft.extrude(tip, "thumb1", offset=(0, -0.3, 0.5), scale=0.75)
draft.cap(tip, name="thumb_cap")
draft.anchor("base", (0, 0, 0))
builder.add_mesh("hand_L", "root", draft, pivot="base")
```

## Methods
| Method | Purpose |
|---|---|
| `ring_from_profile(name, profile, frame)` | Place a `Profile` in a `Frame` (profile XY, normal = frame Z). Registers the ring, an anchor and a frame named `name`, like a loft section. |
| `connect_rings(a, b, prefix=, skip=())` | Quads between two equal rings; `skip` leaves listed quads open (branch roots). |
| `extrude(ring, name, offset=, scale=, frame=None)` | New ring = `ring` moved by `offset` and scaled about its centre (number, or three factors in `frame` axes); bridged with quads; returns the new ring. |
| `cap(ring, name=, inset=None)` | Close a ring: 4 points → one quad, larger even rings → quad fan around a centre vertex. Odd rings need `allow_triangles=True`. |
| `vertex(name, pos)`, `face(name, vertices, group=None)`, `anchor(name, pos)` | Raw building blocks for anything else: a mesh given as explicit coordinates and face lists. |
| `ring_of(name, vertices)` | Register existing vertices (in order) as a ring, so bones can reference `mesh:name`. |
| `ring(name, radius, segments, axis=)` | Axis-aligned circle ring (no frame). |
| `mirror(axis)` | Reflect in place; faces stay outward. |
| `orient_outward()` | Make winding consistent and outward now. |
| `validate()` / `build(orient=None)` | Check / freeze. |

Winding: a closed draft (`MeshDraft(closed=True)`) is oriented outward on
`build()` (which `add_mesh` calls), so bridging order does not matter. Pass
`build(orient=False)` only to inspect raw authored winding. An open draft
(`closed=False`) is a single-sided sheet; its boundary edges are reported as
information.

Anchors are not inferred: name every anchor you will reference (`base`,
`top`, sockets, bone ends). `ring_from_profile` and `extrude` add one per ring. `add_mesh(..., pivot=)` and `placement=` need the named anchor to exist, so call `draft.anchor("base", ...)` first. Every `cap()` after the first on one draft needs its own `name=` (e.g. `name="wrist_cap"`, `name="tip_cap"`), or the centre vertex `cap_center` is a duplicate.
`MeshGeometry.create(vertices={...}, faces={...}, closed=, anchors=)` is the
read-only form (dicts keyed by vertex/face name; treat it as frozen and change geometry through `MeshDraft`); prefer `MeshDraft`.
