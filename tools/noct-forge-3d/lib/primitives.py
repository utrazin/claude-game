"""Pure, deterministic low-poly primitive factories."""

from __future__ import annotations

import math
from .geometry_types import MeshFace, MeshGeometry
from .geometry_types import parse_cap_spec
from .spatial import SpatialFrame


def _anchor_frames(anchors, axis="Y"):
    direction={"X":(1,0,0),"Y":(0,1,0),"Z":(0,0,1)}[axis]
    up=(0,1,0) if axis=="Z" else (0,0,1)
    return {name:SpatialFrame(point,direction,up) for name,point in anchors.items()}


def _axis_point(axis, axial, a, b):
    if axis == "X": return (axial, a, b)
    if axis == "Y": return (a, axial, b)
    return (a, b, axial)


def _outward(geometry: MeshGeometry) -> MeshGeometry:
    volume=0.0
    for face in geometry.faces.values():
        keys=face.vertices
        for i in range(1,len(keys)-1):
            a,b,c=(geometry.vertices[k] for k in (keys[0],keys[i],keys[i+1]))
            volume += (a[0]*(b[1]*c[2]-b[2]*c[1]) - a[1]*(b[0]*c[2]-b[2]*c[0]) + a[2]*(b[0]*c[1]-b[1]*c[0]))/6
    if volume >= 0: return geometry
    return MeshGeometry(geometry.vertices,
                        {k:MeshFace(tuple(reversed(v.vertices)),v.group,v.source_face) for k,v in geometry.faces.items()},
                        geometry.closed,geometry.anchors,geometry.primitive,geometry.rings,
                        geometry.frames)


def _cap_faces(faces, verts, *, ring, center, group, reverse=False,
               style="flat", inset=0.5, allow_triangles: bool = False):
    """Fill a radial boundary exclusively with deterministic quads, or triangles when allowed."""
    if not allow_triangles:
        if len(ring) < 4 or len(ring) % 2:
            raise ValueError("Radial quad caps need an even ring of at least four vertices")
    else:
        if len(ring) < 3:
            raise ValueError("Radial caps need a ring of at least three vertices")
    if style not in {"flat","inset"}:
        raise ValueError("cap_style must be 'flat' or 'inset'")
    if style == "flat":
        order=tuple(reversed(ring)) if reverse else tuple(ring)
        if len(order)==3:
            faces[group]=MeshFace(order,group,group)
            return
        if len(order)==4:
            faces[group]=MeshFace(order,group,group)
            return
        center_key=center
        verts[center_key]=tuple(sum(verts[key][axis] for key in ring)/len(ring)
                                for axis in range(3))
        if len(order) % 2 != 0:
            for index in range(len(order)):
                following = (index + 1) % len(order)
                tri = (center_key, order[index], order[following])
                faces[f"{group}_{index:03d}"] = MeshFace(tri, group, group)
            return
        for index in range(0,len(order),2):
            quad=(center_key,order[index],order[(index+1)%len(order)],
                  order[(index+2)%len(order)])
            faces[f"{group}_{index//2:03d}"]=MeshFace(quad,group,group)
        return
    inset=float(inset)
    if not math.isfinite(inset) or not 0<inset<1:
        raise ValueError("cap_inset must be strictly between 0 and 1")
    center_point=tuple(sum(verts[key][axis] for key in ring)/len(ring) for axis in range(3))
    inner=[]
    for index,key in enumerate(ring):
        inner_key=f"{group}_inner_{index:03d}"
        verts[inner_key]=tuple(center_point[axis]+inset*(verts[key][axis]-center_point[axis])
                               for axis in range(3))
        inner.append(inner_key)
    for index in range(len(ring)):
        following=(index+1)%len(ring)
        order=(ring[index],ring[following],inner[following],inner[index])
        if reverse: order=tuple(reversed(order))
        faces[f"{group}_ring_{index:03d}"]=MeshFace(order,group,group)
    _cap_faces(faces,verts,ring=tuple(inner),center=f"{group}_center",
               group=group,reverse=reverse,style="flat",allow_triangles=allow_triangles)


def plane(*, width: float, height: float, axis: str = "Z") -> MeshGeometry:
    if width <= 0 or height <= 0: raise ValueError("width and height must be positive")
    axis = axis.upper()
    if axis not in {"X","Y","Z"}: raise ValueError("axis must be X, Y, or Z")
    w,h=width/2,height/2
    if axis == "X": points=[(0,-h,-w),(0,h,-w),(0,h,w),(0,-h,w)]
    elif axis == "Y": points=[(-w,0,-h),(-w,0,h),(w,0,h),(w,0,-h)]
    else: points=[(-w,-h,0),(w,-h,0),(w,h,0),(-w,h,0)]
    verts={f"v{i:03d}":p for i,p in enumerate(points)}
    anchors={"center":(0.,0.,0.)}
    normal={"X":(1,0,0),"Y":(0,1,0),"Z":(0,0,1)}[axis]
    up=(0,1,0) if axis!="Y" else (0,0,1)
    return MeshGeometry(verts,{"surface":MeshFace(tuple(verts),"surface")},False,
                        anchors,"plane",frames={"center":SpatialFrame((0,0,0),normal,up)})


def quad_face(*, points) -> MeshGeometry:
    if len(points) != 4:
        raise ValueError("quad_face requires exactly four points; use triangle() for an intentional triangular primitive")
    vertices={f"v{i:03d}":p for i,p in enumerate(points)}
    center=tuple(sum(float(p[i]) for p in points)/len(points) for i in range(3))
    from .geometry_types import _project
    _,normal=_project([tuple(float(v) for v in point) for point in points])
    up=(0,1,0) if abs(normal[1])<.9 else (0,0,1)
    return MeshGeometry.create(vertices,{"surface":tuple(vertices)},closed=False,
                               anchors={"center":center}, primitive="quad_face",
                                frames={"center":SpatialFrame(center,normal,up)})


def triangle(*, points) -> MeshGeometry:
    """Create one explicit triangular face.

    This is intentionally a separate factory instead of a three-point variant
    of :func:`polygon`: callers make the exceptional triangle topology visible
    in the recipe.
    """
    if len(points) != 3:
        raise ValueError("triangle requires exactly three points")
    vertices = {f"v{i:03d}": point for i, point in enumerate(points)}
    center = tuple(sum(float(point[index]) for point in points) / 3
                   for index in range(3))
    from .geometry_types import _project
    _, normal = _project([tuple(float(value) for value in point) for point in points])
    up = (0, 1, 0) if abs(normal[1]) < .9 else (0, 0, 1)
    return MeshGeometry.create(vertices, {"surface": tuple(vertices)}, closed=False,
                               anchors={"center": center}, primitive="triangle",
                               frames={"center": SpatialFrame(center, normal, up)})


def prism(*, radius: float, height: float, sides: int = 6, axis: str = "Y",
          start_cap="flat", end_cap="flat", allow_cap_triangles: bool = False) -> MeshGeometry:
    return radial_primitive("prism", radius=radius, height=height, segments=sides, axis=axis,
                            start_cap=start_cap,end_cap=end_cap,
                            allow_cap_triangles=allow_cap_triangles)


def radial_primitive(kind: str, *, radius: float, height: float, segments: int = 8,
                     axis: str = "Y", top_radius: float | None = None,
                     start_cap="flat", end_cap="flat",
                     allow_cap_triangles: bool = False) -> MeshGeometry:
    axis = axis.upper()
    if axis not in {"X", "Y", "Z"}: raise ValueError("axis must be X, Y, or Z")
    if not math.isfinite(radius) or radius <= 0: raise ValueError("radius must be positive and finite")
    if not math.isfinite(height) or height <= 0: raise ValueError("height must be positive and finite")
    min_segments = 3
    if not isinstance(segments, int) or not min_segments <= segments <= 128:
        raise ValueError(f"segments must be an integer from {min_segments} to 128")
    upper = radius if top_radius is None else float(top_radius)
    if upper < 0 or not math.isfinite(upper):
        raise ValueError("top_radius must be non-negative and finite")
    pointed = upper == 0
    if pointed and kind != "cone":
        raise ValueError("Only the semantic cone primitive may use a zero top radius")
    verts, faces = {}, {}
    bottom_spec=parse_cap_spec(start_cap)
    top_spec=parse_cap_spec(end_cap)
    if segments % 2 and not allow_cap_triangles and (
            bottom_spec.style != "open" or (not pointed and top_spec.style != "open")):
        raise ValueError("Odd segment counts require open ends or allow_cap_triangles=True")
    if pointed and top_spec.style != "flat":
        raise ValueError("A pointed cone has no end cap")
    lo, hi = -height / 2, height / 2
    for ring, axial, rad in (("bottom", lo, radius),):
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            verts[f"{ring}_{i:03d}"] = _axis_point(axis, axial, rad*math.cos(angle), rad*math.sin(angle))
    if pointed:
        verts["top_tip"] = _axis_point(axis, hi, 0, 0)
    else:
        for i in range(segments):
            angle = 2 * math.pi * i / segments
            verts[f"top_{i:03d}"] = _axis_point(axis, hi, upper*math.cos(angle), upper*math.sin(angle))
    for i in range(segments):
        j = (i + 1) % segments
        b0, b1 = f"bottom_{i:03d}", f"bottom_{j:03d}"
        order = (b0, "top_tip", b1) if pointed else (b0, f"top_{i:03d}", f"top_{j:03d}", b1)
        faces[f"side_{i:03d}"] = MeshFace(order, "side", f"side_{i:03d}")
    bottom=tuple(f"bottom_{i:03d}" for i in range(segments))
    if bottom_spec.style!="open":
        _cap_faces(faces,verts,ring=bottom,center="bottom_cap_center",group="cap_bottom",
                   style=bottom_spec.style,inset=bottom_spec.inset,
                   allow_triangles=allow_cap_triangles)
    rings = {"base": bottom, "bottom": bottom}
    top=tuple(f"top_{i:03d}" for i in range(segments))
    if not pointed and top_spec.style!="open":
        _cap_faces(faces,verts,ring=top,center="top_cap_center",group="cap_top",reverse=True,
                   style=top_spec.style,inset=top_spec.inset,
                   allow_triangles=allow_cap_triangles)
    if not pointed:
        rings["top"] = top
    anchors = {"center": (0.,0.,0.), "base": _axis_point(axis, lo, 0, 0), "top": _axis_point(axis, hi, 0, 0)}
    frames=_anchor_frames(anchors,axis)
    for i in range(segments):
        angle=2*math.pi*(i+.5)/segments
        middle_radius=radius/2 if pointed else (radius+upper)/2
        point=_axis_point(axis,0,middle_radius*math.cos(angle),middle_radius*math.sin(angle))
        outward=_axis_point(axis,0,math.cos(angle),math.sin(angle))
        name=f"side_{i:03d}"; anchors[name]=point
        frames[name]=SpatialFrame(point,outward,{"X":(1,0,0),"Y":(0,1,0),"Z":(0,0,1)}[axis])
    return _outward(MeshGeometry(verts, faces,
                                  bottom_spec.style!="open" and (pointed or top_spec.style!="open"),
                                 anchors, kind, rings=rings,frames=frames))


def cylinder(*, radius: float, height: float, segments: int = 8, axis: str = "Y",
             start_cap="flat", end_cap="flat", allow_cap_triangles: bool = False) -> MeshGeometry:
    return radial_primitive("cylinder", radius=radius, height=height, segments=segments, axis=axis,
                            start_cap=start_cap,end_cap=end_cap,
                            allow_cap_triangles=allow_cap_triangles)


def cone(*, radius: float, height: float, segments: int = 8, axis: str = "Y",
         start_cap="flat", allow_cap_triangles: bool = False) -> MeshGeometry:
    """Cone with an intentional real apex."""
    return radial_primitive("cone", radius=radius, height=height, segments=segments,
                            axis=axis, top_radius=0, start_cap=start_cap,
                            allow_cap_triangles=allow_cap_triangles)


def pyramid(*, base_width: float, height: float, base_depth: float | None = None,
            axis: str = "Y", start_cap="flat") -> MeshGeometry:
    """Square/rectangular pyramid with an intentional triangular apex.

    The base is centered at the negative end of ``axis`` and the tip at the
    positive end, matching the axial placement conventions of radial forms.
    """
    axis = axis.upper()
    if axis not in {"X", "Y", "Z"}:
        raise ValueError("axis must be X, Y, or Z")
    width = float(base_width)
    depth = width if base_depth is None else float(base_depth)
    if not math.isfinite(width) or width <= 0:
        raise ValueError("base_width must be positive and finite")
    if not math.isfinite(depth) or depth <= 0:
        raise ValueError("base_depth must be positive and finite")
    if not math.isfinite(height) or height <= 0:
        raise ValueError("height must be positive and finite")
    base_spec = parse_cap_spec(start_cap)
    lo, hi = -height / 2, height / 2
    half_width, half_depth = width / 2, depth / 2
    corners = ((-half_width, -half_depth), (half_width, -half_depth),
               (half_width, half_depth), (-half_width, half_depth))
    vertices = {f"base_{index:03d}": _axis_point(axis, lo, *corner)
                for index, corner in enumerate(corners)}
    vertices["top_tip"] = _axis_point(axis, hi, 0, 0)
    faces = {}
    for index in range(4):
        following = (index + 1) % 4
        faces[f"side_{index:03d}"] = MeshFace(
            (f"base_{index:03d}", "top_tip", f"base_{following:03d}"),
            "side", f"side_{index:03d}")
    if base_spec.style != "open":
        faces["cap_bottom"] = MeshFace(tuple(f"base_{index:03d}" for index in range(4)),
                                        "cap_bottom", "cap_bottom")
    base = tuple(f"base_{index:03d}" for index in range(4))
    anchors = {"center": (0., 0., 0.), "base": _axis_point(axis, lo, 0, 0),
               "top": _axis_point(axis, hi, 0, 0)}
    return _outward(MeshGeometry(vertices, faces, base_spec.style != "open", anchors,
                                 "pyramid", rings={"base": base, "bottom": base},
                                 frames=_anchor_frames(anchors, axis)))


def frustum(*, bottom_radius: float, top_radius: float, height: float,
            segments: int = 8, axis: str = "Y", start_cap="flat", end_cap="flat",
            allow_cap_triangles: bool = False) -> MeshGeometry:
    return radial_primitive("frustum", radius=bottom_radius, top_radius=top_radius,
                            height=height, segments=segments, axis=axis,
                            start_cap=start_cap,end_cap=end_cap,
                            allow_cap_triangles=allow_cap_triangles)


def uv_sphere(*, radius: float, segments: int = 8, rings: int = 4, axis: str = "Y") -> MeshGeometry:
    if not isinstance(rings, int) or not 2 <= rings <= 64: raise ValueError("rings must be an integer from 2 to 64")
    axis = axis.upper()
    if axis not in {"X", "Y", "Z"}: raise ValueError("axis must be X, Y, or Z")
    if radius <= 0 or not math.isfinite(radius): raise ValueError("radius must be positive and finite")
    if not isinstance(segments, int) or not 4 <= segments <= 128: raise ValueError("segments must be an integer from 4 to 128")
    if segments % 2: raise ValueError("UV spheres require an even segment count")
    verts = {}
    faces = {}
    # stretch the latitudes so the flat polar rings reach +-radius and the widest ring reaches radius
    axial_scale = 1 / math.cos(math.pi * .5 / (rings + 1))
    radial_scale = 1 / max(math.cos(-math.pi/2 + math.pi*(r+.5)/(rings+1)) for r in range(rings+1))
    for r in range(rings+1):
        phi = -math.pi/2 + math.pi*(r+.5)/(rings+1)
        for i in range(segments):
            theta = 2*math.pi*i/segments
            verts[f"ring_{r:03d}_{i:03d}"] = _axis_point(axis, radius*math.sin(phi)*axial_scale, radius*radial_scale*math.cos(phi)*math.cos(theta), radius*radial_scale*math.cos(phi)*math.sin(theta))
    bottom=tuple(f"ring_000_{i:03d}" for i in range(segments))
    top=tuple(f"ring_{rings:03d}_{i:03d}" for i in range(segments))
    _cap_faces(faces,verts,ring=bottom,center="pole_bottom_center",
               group="pole_bottom",reverse=True,style="flat")
    _cap_faces(faces,verts,ring=top,center="pole_top_center",
               group="pole_top",style="flat")
    for r in range(rings):
        for i in range(segments):
            j=(i+1)%segments
            faces[f"band_{r:03d}_{i:03d}"] = MeshFace((f"ring_{r:03d}_{i:03d}",f"ring_{r:03d}_{j:03d}",f"ring_{r+1:03d}_{j:03d}",f"ring_{r+1:03d}_{i:03d}"),f"ring_{r:03d}")
    bottom_axial = radius*math.sin(-math.pi/2 + math.pi*.5/(rings+1))*axial_scale
    top_axial = radius*math.sin(-math.pi/2 + math.pi*(rings+.5)/(rings+1))*axial_scale
    anchors={"center":(0.,0.,0.),"base":_axis_point(axis,bottom_axial,0,0),
             "top":_axis_point(axis,top_axial,0,0)}
    for r in range(rings+1):
        phi=-math.pi/2+math.pi*(r+.5)/(rings+1)
        anchors[f"ring_{r:03d}"]=_axis_point(axis,radius*math.sin(phi)*axial_scale,0,0)
    return _outward(MeshGeometry(verts,faces,True,anchors,"uv_sphere",
                                 frames=_anchor_frames(anchors,axis)))


def quad_sphere(*, radius: float, subdivisions: int = 2) -> MeshGeometry:
    """Cube-sphere with shared vertices and exclusively non-degenerate quad faces."""
    if radius <= 0 or not math.isfinite(radius): raise ValueError("radius must be positive and finite")
    if not isinstance(subdivisions,int) or not 1 <= subdivisions <= 32:
        raise ValueError("subdivisions must be an integer from 1 to 32")
    n=subdivisions
    vertices={}
    faces={}

    def vertex(coord):
        key=f"v_{coord[0]+n:03d}_{coord[1]+n:03d}_{coord[2]+n:03d}"
        if key not in vertices:
            length=math.sqrt(sum(value*value for value in coord))
            vertices[key]=tuple(radius*value/length for value in coord)
        return key

    # constant axis, sign, horizontal axis, vertical axis
    specs=((0,-1,2,1),(0,1,2,1),(1,-1,0,2),(1,1,0,2),(2,-1,0,1),(2,1,0,1))
    for axis,sign,u_axis,v_axis in specs:
        for row in range(n):
            for column in range(n):
                keys=[]
                for u,v in ((column,row),(column+1,row),(column+1,row+1),(column,row+1)):
                    coord=[0,0,0]
                    coord[axis]=sign*n
                    coord[u_axis]=-n+2*u
                    coord[v_axis]=-n+2*v
                    keys.append(vertex(tuple(coord)))
                a,b,c=(vertices[key] for key in keys[:3])
                normal=((b[1]-a[1])*(c[2]-a[2])-(b[2]-a[2])*(c[1]-a[1]),
                        (b[2]-a[2])*(c[0]-a[0])-(b[0]-a[0])*(c[2]-a[2]),
                        (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))
                center=tuple(sum(vertices[key][i] for key in keys)/4 for i in range(3))
                if sum(normal[i]*center[i] for i in range(3)) < 0: keys.reverse()
                face_name=f"side_{axis}_{sign:+d}_{row:03d}_{column:03d}"
                faces[face_name]=MeshFace(tuple(keys),f"axis_{axis}_{sign:+d}",face_name)
    anchors = {
        "center": (0., 0., 0.), "base": (0., -radius, 0.), "top": (0., radius, 0.),
        "left": (-radius, 0., 0.), "right": (radius, 0., 0.),
        "front": (0., 0., radius), "back": (0., 0., -radius),
        "-x": (-radius, 0., 0.), "+x": (radius, 0., 0.),
        "-y": (0., -radius, 0.), "+y": (0., radius, 0.),
        "-z": (0., 0., -radius), "+z": (0., 0., radius),
        "screen_left": (-radius, 0., 0.), "screen_right": (radius, 0., 0.),
        "anatomical_left": (radius, 0., 0.), "anatomical_right": (-radius, 0., 0.),
    }
    frames = _anchor_frames(anchors, "Y")
    for name, direction, up in (
        ("left", (-1, 0, 0), (0, 1, 0)),
        ("right", (1, 0, 0), (0, 1, 0)),
        ("front", (0, 0, 1), (0, 1, 0)),
        ("back", (0, 0, -1), (0, 1, 0)),
        ("-x", (-1, 0, 0), (0, 1, 0)),
        ("+x", (1, 0, 0), (0, 1, 0)),
        ("screen_left", (-1, 0, 0), (0, 1, 0)),
        ("screen_right", (1, 0, 0), (0, 1, 0)),
        ("anatomical_left", (1, 0, 0), (0, 1, 0)),
        ("anatomical_right", (-1, 0, 0), (0, 1, 0)),
    ):
        frames[name] = SpatialFrame(anchors[name], direction, up)
    return MeshGeometry(vertices, faces, True, anchors, "quad_sphere", frames=frames)


def capsule(*, radius: float, height: float, axis: str = "Y",
            segments: int = 8, rings: int = 1) -> MeshGeometry:
    """Capsule primitive with hemispherical quad caps and cylindrical body."""
    axis = axis.upper()
    if axis not in {"X", "Y", "Z"}:
        raise ValueError("axis must be X, Y, or Z")
    if radius <= 0 or not math.isfinite(radius):
        raise ValueError("radius must be positive and finite")
    if height <= 0 or not math.isfinite(height):
        raise ValueError("height must be positive and finite")
    if height < 2 * radius:
        raise ValueError(f"Capsule height ({height}) must be at least 2 * radius ({2 * radius})")
    if not isinstance(segments, int) or not 4 <= segments <= 128 or segments % 2 != 0:
        raise ValueError("segments must be an even integer between 4 and 128")
    if not isinstance(rings, int) or not 1 <= rings <= 32:
        raise ValueError("rings must be an integer between 1 and 32")

    cyl_h = height - 2 * radius
    pole_scale = 1 / math.cos(math.pi / (2 * (rings + 1)))   # the flat polar ring reaches exactly +-height/2
    is_sphere = cyl_h <= 1e-9  # height == 2*radius: no cylindrical body, pure sphere
    lo, hi = -cyl_h / 2, cyl_h / 2
    verts, faces = {}, {}

    # Bottom hemisphere rings: k=0 (near south pole) to k=rings (bottom equator)
    for k in range(rings + 1):
        phi = -math.pi / 2 + (math.pi / 2) * (k + 1) / (rings + 1)
        z_axial = lo + radius * math.sin(phi) * pole_scale
        r_current = radius * math.cos(phi)
        for i in range(segments):
            theta = 2 * math.pi * i / segments
            verts[f"b_{k:03d}_{i:03d}"] = _axis_point(
                axis, z_axial,
                r_current * math.cos(theta),
                r_current * math.sin(theta)
            )

    # Top hemisphere rings: k=0 (top equator) to k=rings (near north pole).
    # When the shape degenerates to a sphere (cyl_h == 0) the top equator
    # (k=0) is geometrically identical to the bottom equator (b_{rings}); it
    # is aliased to those existing vertices instead of duplicated, so no
    # zero-height "cylinder body" band is ever built between coincident rings.
    def top_ring_vertex(i: int) -> str:
        return f"b_{rings:03d}_{i:03d}" if is_sphere else f"t_000_{i:03d}"

    for k in range(1 if is_sphere else 0, rings + 1):
        phi = (math.pi / 2) * k / (rings + 1)
        z_axial = hi + radius * math.sin(phi) * pole_scale
        r_current = radius * math.cos(phi)
        for i in range(segments):
            theta = 2 * math.pi * i / segments
            verts[f"t_{k:03d}_{i:03d}"] = _axis_point(
                axis, z_axial,
                r_current * math.cos(theta),
                r_current * math.sin(theta)
            )

    # Bottom hemisphere bands
    for k in range(rings):
        for i in range(segments):
            j = (i + 1) % segments
            faces[f"bband_{k:03d}_{i:03d}"] = MeshFace(
                (f"b_{k:03d}_{i:03d}", f"b_{k:03d}_{j:03d}", f"b_{k+1:03d}_{j:03d}", f"b_{k+1:03d}_{i:03d}"),
                f"bhemi_{k:03d}"
            )

    # Cylinder body connecting bottom equator (b_{rings}) and top equator (t_0).
    # Skipped for a degenerate sphere, where the two rings coincide.
    if not is_sphere:
        for i in range(segments):
            j = (i + 1) % segments
            faces[f"cyl_{i:03d}"] = MeshFace(
                (f"b_{rings:03d}_{i:03d}", f"b_{rings:03d}_{j:03d}", top_ring_vertex(j), top_ring_vertex(i)),
                "cylinder"
            )

    # Top hemisphere bands
    for k in range(rings):
        for i in range(segments):
            j = (i + 1) % segments
            lo_i = top_ring_vertex(i) if k == 0 else f"t_{k:03d}_{i:03d}"
            lo_j = top_ring_vertex(j) if k == 0 else f"t_{k:03d}_{j:03d}"
            faces[f"tband_{k:03d}_{i:03d}"] = MeshFace(
                (lo_i, lo_j, f"t_{k+1:03d}_{j:03d}", f"t_{k+1:03d}_{i:03d}"),
                f"themi_{k:03d}"
            )

    # Pole caps
    bottom_pole = tuple(f"b_000_{i:03d}" for i in range(segments))
    top_pole = tuple(f"t_{rings:03d}_{i:03d}" for i in range(segments))
    _cap_faces(faces, verts, ring=bottom_pole, center="pole_bottom_center",
               group="pole_bottom", reverse=True, style="flat")
    _cap_faces(faces, verts, ring=top_pole, center="pole_top_center",
               group="pole_top", style="flat")

    anchors = {
        "center": (0., 0., 0.),
        "base": _axis_point(axis, -height / 2, 0, 0),
        "top": _axis_point(axis, height / 2, 0, 0)
    }
    rings_dict = {
        "bottom": tuple(f"b_{rings:03d}_{i:03d}" for i in range(segments)),
        "top": tuple(top_ring_vertex(i) for i in range(segments))
    }
    return _outward(MeshGeometry(verts, faces, True, anchors, "capsule",
                                 rings=rings_dict, frames=_anchor_frames(anchors, axis)))


def wedge(*, width: float, depth: float, height: float, axis: str = "Y") -> MeshGeometry:
    """Low-poly wedge/ramp solid with 3 quad faces and 2 triangular sides."""
    axis = axis.upper()
    if axis not in {"X", "Y", "Z"}:
        raise ValueError("axis must be X, Y, or Z")
    w, d, h = float(width), float(depth), float(height)
    if w <= 0 or not math.isfinite(w):
        raise ValueError("width must be positive and finite")
    if d <= 0 or not math.isfinite(d):
        raise ValueError("depth must be positive and finite")
    if h <= 0 or not math.isfinite(h):
        raise ValueError("height must be positive and finite")

    lo, hi = -h / 2, h / 2
    verts = {
        "b_bl": _axis_point(axis, lo, -w / 2, -d / 2),
        "b_br": _axis_point(axis, lo, w / 2, -d / 2),
        "b_fr": _axis_point(axis, lo, w / 2, d / 2),
        "b_fl": _axis_point(axis, lo, -w / 2, d / 2),
        "t_l": _axis_point(axis, hi, -w / 2, -d / 2),
        "t_r": _axis_point(axis, hi, w / 2, -d / 2),
    }

    faces = {
        "bottom": MeshFace(("b_bl", "b_fl", "b_fr", "b_br"), "bottom"),
        "back": MeshFace(("b_bl", "b_br", "t_r", "t_l"), "back"),
        "ramp": MeshFace(("b_fl", "t_l", "t_r", "b_fr"), "ramp"),
        "side_left": MeshFace(("b_bl", "t_l", "b_fl"), "side"),
        "side_right": MeshFace(("b_br", "b_fr", "t_r"), "side"),
    }

    anchors = {
        "center": (0., 0., 0.),
        "base": _axis_point(axis, lo, 0, 0),
        "top": _axis_point(axis, hi, 0, 0),
    }
    return _outward(MeshGeometry(verts, faces, True, anchors, "wedge",
                                 frames=_anchor_frames(anchors, axis)))


def box(*, size) -> MeshGeometry:
    """Free-mesh rectangular cuboid: 6 quad faces, X=width/Y=height/Z=depth.

    Unlike the native ``cube`` element (``ModelBuilder.add_cube``/``add_box``
    in box-modeling mode), this is a real polygon mesh and can be bound to
    an armature like any other semantic primitive.
    """
    w, h, d = (float(value) for value in size)
    for value, label in ((w, "width"), (h, "height"), (d, "depth")):
        if value <= 0 or not math.isfinite(value):
            raise ValueError(f"box {label} must be positive and finite")
    hx, hy, hz = w / 2, h / 2, d / 2
    verts = {
        "v0": (-hx, -hy, -hz), "v1": (hx, -hy, -hz), "v2": (hx, hy, -hz), "v3": (-hx, hy, -hz),
        "v4": (-hx, -hy, hz), "v5": (hx, -hy, hz), "v6": (hx, hy, hz), "v7": (-hx, hy, hz),
    }
    faces = {
        "bottom": MeshFace(("v0", "v1", "v5", "v4"), "bottom"),
        "top": MeshFace(("v3", "v7", "v6", "v2"), "top"),
        "front": MeshFace(("v4", "v5", "v6", "v7"), "front"),
        "back": MeshFace(("v1", "v0", "v3", "v2"), "back"),
        "right": MeshFace(("v5", "v1", "v2", "v6"), "right"),
        "left": MeshFace(("v0", "v4", "v7", "v3"), "left"),
    }
    anchors = {
        "center": (0., 0., 0.), "base": (0., -hy, 0.), "top": (0., hy, 0.),
        "left": (-hx, 0., 0.), "right": (hx, 0., 0.),
        "front": (0., 0., hz), "back": (0., 0., -hz),
        "-x": (-hx, 0., 0.), "+x": (hx, 0., 0.),
        "-y": (0., -hy, 0.), "+y": (0., hy, 0.),
        "-z": (0., 0., -hz), "+z": (0., 0., hz),
        "screen_left": (-hx, 0., 0.), "screen_right": (hx, 0., 0.),
        "anatomical_left": (hx, 0., 0.), "anatomical_right": (-hx, 0., 0.),
    }
    frames = _anchor_frames(anchors, "Y")
    for name, direction in (("left", (-1, 0, 0)), ("right", (1, 0, 0)),
                            ("front", (0, 0, 1)), ("back", (0, 0, -1)),
                            ("-x", (-1, 0, 0)), ("+x", (1, 0, 0)),
                            ("screen_left", (-1, 0, 0)), ("screen_right", (1, 0, 0)),
                            ("anatomical_left", (1, 0, 0)), ("anatomical_right", (-1, 0, 0))):
        frames[name] = SpatialFrame(anchors[name], direction, (0, 1, 0))
    return _outward(MeshGeometry(verts, faces, True, anchors, "box", frames=frames))

