# Shapes: primitives, segments, sweeps, lofts, revolves

Full constructor signatures live in the generated reference: [lib](../../../../docs/api/lib.md)
(`ModelBuilder.add_*`, `Profile`, `SegmentSection`, `PathSection`, `Section`,
`Frame`, `Path3D`, `Placement`, `CapSpec`). This page keeps only the
operational rules and examples.

Imports: `from lib import ModelBuilder, Profile, SegmentSection, PathSection, Section, Frame, Path3D, Placement, CapSpec`.

Every `add_*` returns the builder (chainable); `builder.last` is a handle with
world `anchors`/`frames`. Free-mesh methods accept `tags=`,
`no_overlap_check=True` (an element intentionally embedded in another; for a
multi-part assembly give every part the same `tags=("assembly:<name>",)`),
`placement=` (see `placement-and-mirror.md`). `pivot=` applies to segment, sweep, loft,
revolve and `add_mesh`; the primitives above take `placement=` only.

## Primitives
| Call | Key parameters | Anchors (besides indexed `side_*`/`ring_*`) | Rings |
|---|---|---|---|
| `add_cylinder` | `radius, height, segments=8, axis="Y"` | base, center, top | base, bottom, top |
| `add_frustum` | `bottom_radius, top_radius, height, segments=8` | base, center, top | base, bottom, top |
| `add_prism` | `radius, height, sides=6` | base, center, top | base, bottom, top |
| `add_cone` / `add_pyramid` | `radius`/`base_width`, `height` (apex = triangles) | base, center, top | base, bottom |
| `add_capsule` | `radius, height >= 2*radius, segments` even 4–128, `rings` 1–32 | base, center, top (poles of the full round shape) | bottom, top |
| `add_uv_sphere` / `add_quad_sphere` | `radius`, `segments,rings` / `subdivisions` | base, center, top (+ left/right/front/back for quad sphere) | – |
| `add_wedge` | `width, depth, height, axis` | base, center, top | – |
| `add_plane` / `add_quad_face` / `add_triangle` | sheet sizes or explicit points (free/mixed mode only) | center | – |
| `add_axis_quad` | `from_=(x,y,z), size=(w,h), normal="+Z"` (**the only 2D sheet allowed in box mode**) | center | – |
| `add_box(..., native=False)` | `size`, box anchors | center, base/top, left/right, front/back | – |

### 2D Quads & Sheets: When to Use Which
| Method | Modeling Mode | Geometry Type | Anchors | Use Case |
|---|---|---|---|---|
| `add_axis_quad(name, parent, from_, size, normal)` | **`box`**, `mixed`, `free` | Native Blockbench rectangular quad | `center` | **Only quad allowed in `box` mode** (leaves, paper, banners, billboards without violating box constraints). |
| `add_plane(name, parent, width, height, axis)` | `free`, `mixed` (rejected in `box`) | Centered `MeshGeometry` quad | `center` | Parametric flat polygonal sheet in free/mixed models with `placement=`. |
| `add_quad_face(name, parent, points)` | `free`, `mixed` (rejected in `box`) | Explicit 4-point `MeshGeometry` | `center` | Arbitrary non-axis-aligned polygonal faces from 4 3D points. |

### Box & Cube Anchors & Aliases
Native cubes (`add_cube`), native boxes (`add_box`), and mesh boxes (`add_box(..., native=False)`) all expose:
- Standard: `center`, `base` (-Y), `top` (+Y), `left` (-X), `right` (+X), `front` (+Z), `back` (-Z).
- Cardinal: `-x`, `+x`, `-y`, `+y`, `-z`, `+z`.
- Screen-space: `screen_left` (-X), `screen_right` (+X).
- Anatomical: `anatomical_left` (+X, character's left arm `arm_L`), `anatomical_right` (-X, character's right arm `arm_R`).

Primitives are built around their `center` anchor; without `placement` that
anchor sits on the parent pivot. Capped radial forms take `start_cap`/`end_cap`:
`"flat"` (default), `"open"`, or `CapSpec.inset_ring(ratio)`; a closed cap on an
odd ring needs `allow_cap_triangles=True`. A capsule or UV sphere is exactly as tall
and wide as its `height`/`radius`: the flat polar ring is placed on the pole, so
`base`/`top` sit flush on the end at any `rings`.

Signatures: `SegmentSection` supports both `(name, profile, t)` and `(name, t, profile)` positional orders, as well as keyword arguments (`profile=...`, `t=...`, `distance=...`); `PathSection(name, profile, at=None, point=None)` (`distance=` works as another name for `at=`) and `Section(name, profile, frame)` take the profile second.

## Profiles
| Call | Result | Dimensions Interpretation |
|---|---|---|
| `Profile.circle(r, segments=8, phase=0)` | Circular disk | `r` is the **radius** (total width and height are `2*r`) |
| `Profile.ellipse(w, d, segments=8, phase=0)` | Elliptical disk | `w` and `d` are **total dimensions** (full width and full depth) |
| `Profile.oval(half_w, pos_y, neg_y, segments=8, phase=0)` | Asymmetric egg/oval | `half_w` is the **X radius** (full width is `2*half_w`); `pos_y` is radius toward +y (front if y_hint is +Z), `neg_y` is radius toward -y |
| `Profile.rectangle(w, d)` | Sharp box profile | `w` and `d` are **total dimensions** (full width and full depth) |
| `Profile.rounded_rectangle(w, d, r)` | Box profile with rounded corners | `w`, `d` are total dimensions; `r` is corner radius |
| `Profile.polygon([(x, y), ...])` | Custom polygon outline | Any counter-clockwise outline (4+ points; `allow_triangles=True` for 3) |
| `.nudge({i: (dx, dy)})`, `.scale(f or (fx, fy))`, `.expand(margin)`, `.resample(n)` | Derived copies | Direct vertex sculpting and scaling |


Vertex `i` of circle/ellipse/oval sits at `phase + 360*i/segments` degrees
from +x, counter-clockwise. `phase=0` puts a vertex on +x and, for 8 or 12
segments, on ±y; `phase=180/segments` puts a face there instead (e.g. a face
on the front to extrude from). Use `nudge` for single-vertex sculpting
(nose ridge, chin point, cheekbones).

## Profile axes (where profile x/y land in the world)
A section's frame has profile x, profile y and a normal (the travel direction).
Say where profile +y points with `y_hint=` (it is projected onto the section
plane); otherwise the defaults below apply.

| Constructor | Default profile axes |
|---|---|
| `add_segment` | x = world axis least parallel to the segment (ties X, Y, Z); y = direction × x. Running +Y → x=+X, **y=-Z (back)**. Running -Y → y=+Z. Running +X → x=+Y, y=+Z. Pass `y_hint=(0, 0, 1)` to make profile +y the model front. |
| `add_sweep` | first frame from `x_hint` (default +X unless the path starts along X) or `y_hint`; later frames are parallel-transported without twist. A downward limb with default hints gets y=+Z (front). |
| `add_loft` / `Section(name, profile, Frame.from_normal(origin, normal=n, x_hint=... or y_hint=...))` | as given; `from_normal` with `x_hint` sets y = n × x. |
| `add_revolve` | meridian `(radius, height)` pairs around +Y. |

## Straight spans: `add_segment`
```python
# runnable: torso with three sections
from lib import ModelBuilder, Profile, SegmentSection

builder = ModelBuilder("torso_demo", require_integer_dimensions=False)
builder.add_group("rig")          # an armature here ("add_armature") also needs rig.bind, see rigging.md
builder.add_segment("torso", "rig", start=(0, 19, 0), end=(0, 26.8, 0), y_hint=(0, 0, 1),
    sections=(
        SegmentSection("waist", profile=Profile.oval(2.0, 1.4, 1.3, segments=12), distance=0),
        SegmentSection("chest", profile=Profile.oval(2.8, 2.1, 1.9, segments=12), distance=4.5),
        SegmentSection("collar", profile=Profile.oval(1.0, 0.8, 0.9, segments=12), t=1),
    ))
```
Place a section with `t` (0..1) or `distance` from `start`; the first must be
at the start and the last at the end: end with `t=1`, because `distance=<length>` can miss the end by float rounding (the error then reads `must start at t=0 and end at t=1`). `offset=(dx, dy)` shifts a section in its
profile plane, `rotation=` spins it. Anchors: `start`, `end`, `base`, `top`,
`center` and one per section name; the pivot is `start`.

## Bent spans through joints: `add_sweep(sections=...)`
```python
leg_path = Path3D.polyline([(1.6, 17.4, 0), (1.6, 16.4, 0), (2.35, 10.4, 0.05), (3.2, 2.0, -0.3), (3.2, 1.2, -0.3)])
builder.add_sweep("leg_L", "rig", path=leg_path, y_hint=(0, 0, 1), sections=(
    PathSection("hip_cap", Profile.circle(1.2), point=0),
    PathSection("hip", Profile.circle(1.5), point=1),
    PathSection("thigh", Profile.oval(1.45, 1.6, 1.45), at=3.0),
    PathSection("knee", Profile.oval(1.0, 1.1, 1.0), point=2),
    PathSection("calf", Profile.oval(1.15, 1.0, 1.5), at=9.0),
    PathSection("ankle", Profile.circle(0.6), point=3),
    PathSection("tuck", Profile.circle(0.55), point=4),
))
```
`point=i` puts a section exactly on path vertex `i` with the frame bisecting
the bend; `at=d` places it `d` units along the path (negative or past the end
extends straight). Section names become rings and anchors (`leg_L:knee`), which
is what bones and hard binding use. Sections must advance along the path. For
a single profile swept with `scale`/`twist` tables pass `profile=` instead of
`sections=`; a table is `((t, value), ...)` with `t` rising from 0 to 1 (`scale`
default `((0, 1), (1, 1))`, value a factor or `(fx, fy)`; `twist` default
`((0, 0), (1, 0))`, value in degrees), e.g. `scale=((0, 1), (1, 0.6))` tapers to 60%.
The pivot is `base` (the first section).

`base`, `top`, `center`, `start` and `end` are the shape's own anchors. A section
may reuse `base`/`start` (first section) or `top`/`end` (last section) where the
anchor lands anyway; anywhere else, and for `center`, the build raises
`Section 'x' is not where the shape's own 'x' anchor is`: rename the section.

## Free sections: `add_loft`
```python
sections = [Section(f"r{i}", profile, Frame.from_normal((x, 0, z), normal=(0, 0, 1), x_hint=(1, 0, 0)))
            for i, (x, z, profile) in enumerate(foot_rows)]
builder.add_loft("foot_L", "rig", sections=sections)
```
Each `Section` gets its own `Frame` (parent-local), `SpatialFrame`, or a
reference string. Anchors: `base` (first section), `top` (last), `center`, one
per section; the pivot is `base`.

## Revolve
`builder.add_revolve("vase", "root", meridian=((0.6, 0), (1.2, 1.5), (0.4, 3)), segments=8)`
— radii must stay positive (use a cone or sphere for a pole). `angle=` (default 360) makes a partial revolve, which needs `start_cap="open", end_cap="open"`. Rings are
`section_000…`, anchors `base`, `top`, `center`.

## Editing after construction
```python
with builder.edit_mesh("torso") as mesh:            # validated on exit, rolled back on error
    mesh.edit_ring("chest").scale((1.1, 1.2))        # profile x/y, around the section origin
    mesh.edit_ring("chest").translate((0, 0.2))      # profile axes; third value = along normal
    mesh.edit_ring("collar").rotate(10)              # about the ring normal
```
Section rings edit in their own profile plane. Rings without a frame (plain
`MeshDraft.ring`, primitive rings) use world axes around the ring centroid; pass
`frame=` to choose. A section anchor follows its ring when the whole ring moves
and stays put on partial edits, so bones targeting `mesh:section` stay valid.
Other vertex tools on the draft: `select_vertices(names=, faces=, ring=, axis=, t=)` returns vertex names, then `translate_vertices(vertices, offset)`, `rotate_vertices(vertices, degrees, axis=, pivot=)`, `scale_vertices(vertices, factors, pivot=)`; e.g. `mesh.translate_vertices(mesh.select_vertices(ring="chest"), (0, 0.2, 0))`. Optional `weights={vertex: 0..1}` scales the effect per vertex; `linear_falloff(t)` and `smooth_falloff(t)` turn a normalized distance into such a factor.

## Combining Meshes (Joining Disconnected Shells)
When parts are constructed separately but need to form a single cohesive mesh element (avoiding the `contains N disconnected shells` error):
```python
# Joins several mesh elements into one target element:
builder.combine_meshes(["collar", "torso_base"], into="torso", parent="body")
```

## Paths and Spatial Helpers
- `Path3D.polyline([(x, y, z), ...])`: piecewise linear path.
- `Path3D.bezier(p0, p1, p2, p3, samples=16)`: smooth cubic Bezier curve.
- `Path3D.line(start, end, samples=8)`: straight path sampled into segments.
- `builder.between(start, end, t=0.5)`: returns interpolated 3D coordinates between two points or anchors.
- `builder.offset(reference, local=(x, y, z))`: returns coordinates offset from a named anchor or frame.

