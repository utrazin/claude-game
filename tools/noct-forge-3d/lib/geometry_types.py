"""Canonical mesh value objects used by the model-as-code pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Mapping, Sequence

Vector3 = tuple[float, float, float]


@dataclass(frozen=True)
class CapSpec:
    style: str = "flat"
    inset: float = 0.5

    def __post_init__(self):
        style=str(self.style).lower()
        if style not in {"open","flat","inset"}:
            raise ValueError("CapSpec style must be open, flat, or inset")
        inset=float(self.inset)
        if style=="inset" and (not math.isfinite(inset) or not 0<inset<1):
            raise ValueError("Inset cap ratio must be strictly between 0 and 1")
        object.__setattr__(self,"style",style); object.__setattr__(self,"inset",inset)

    @classmethod
    def open(cls): return cls("open")
    @classmethod
    def flat(cls): return cls("flat")
    @classmethod
    def inset_ring(cls, ratio=0.5): return cls("inset",ratio)


def parse_cap_spec(value) -> CapSpec:
    """Normalize the single public cap vocabulary used by every mesh factory."""
    if isinstance(value, CapSpec):
        return value
    if isinstance(value, str):
        return CapSpec(value)
    raise TypeError("Cap must be a CapSpec or style string")


def _project(points):
    # Newell's normal also works when an edge split makes the first three points collinear.
    normal=tuple(sum((a[(i+1)%3]-b[(i+1)%3])*(a[(i+2)%3]+b[(i+2)%3])
                     for a,b in zip(points,points[1:]+points[:1])) for i in range(3))
    drop = max(range(3), key=lambda i: abs(normal[i]))
    axes = [i for i in range(3) if i != drop]
    return [(p[axes[0]], p[axes[1]]) for p in points], normal


def _validate_face(order, vertices, label):
    points = [vertices[k] for k in order]
    projected, normal = _project(points)
    nlen = math.sqrt(sum(v*v for v in normal))
    if nlen <= 1e-8: raise ValueError(f"Face {label!r} is degenerate: it has zero area (collinear or repeated corners); move a corner off the line")
    unit = tuple(v/nlen for v in normal)
    from .polygon_math import validate_contour
    validate_contour(tuple(projected))
    def turn(a,b,c):
        return (b[0]-a[0])*(c[1]-b[1])-(b[1]-a[1])*(c[0]-b[0])
    turns = [turn(projected[index-1], projected[index],
                  projected[(index+1) % len(projected)])
             for index in range(len(projected))]
    if any(abs(value) <= 1e-9 for value in turns):
        raise ValueError(f"Face {label!r} has a collinear corner")
    if not (all(value > 0 for value in turns) or all(value < 0 for value in turns)):
        raise ValueError(f"Face {label!r} must be a convex triangle or quad")
    # A deliberately warped quad is valid Blockbench topology. The renderer
    # chooses its A-C diagonal internally, but that diagonal is never a face.


def vector3(value: Sequence[float], label: str = "position") -> Vector3:
    if len(value) != 3:
        raise ValueError(f"{label} must contain exactly three numbers")
    result = tuple(float(v) for v in value)
    if not all(math.isfinite(v) for v in result):
        raise ValueError(f"{label} must contain finite numbers")
    return result  # type: ignore[return-value]


@dataclass(frozen=True)
class MeshFace:
    vertices: tuple[str, ...]
    group: str | None = None
    source_face: str | None = None

    def __post_init__(self):
        order=tuple(str(value) for value in self.vertices)
        if len(order) not in (3, 4):
            raise ValueError("Every mesh face must contain exactly three or four vertices")
        if len(set(order)) != len(order):
            raise ValueError("Mesh faces need distinct vertices")
        object.__setattr__(self,"vertices",order)


@dataclass(frozen=True)
class MeshGeometry:
    vertices: dict[str, Vector3]
    faces: dict[str, MeshFace]
    closed: bool = False
    anchors: dict[str, Vector3] = field(default_factory=dict)
    primitive: str | None = None
    rings: dict[str, tuple[str, ...]] = field(default_factory=dict)
    frames: dict[str, object] = field(default_factory=dict)

    def __post_init__(self):
        verts = {str(key): vector3(value, f"vertex {key!r}")
                 for key, value in self.vertices.items()}
        if len(verts) != len(self.vertices):
            raise ValueError("Vertex names collide after string conversion")
        parsed: dict[str, MeshFace] = {}
        for key, value in self.faces.items():
            face = value if isinstance(value, MeshFace) else MeshFace(tuple(value))
            face_key = str(key)
            if face_key in parsed:
                raise ValueError(f"Face name collision: {key}")
            if any(vertex not in verts for vertex in face.vertices):
                raise ValueError(f"Face {key!r} references missing vertices")
            _validate_face(face.vertices, verts, face_key)
            parsed[face_key] = face
        anchor_data = {str(key): vector3(value, f"anchor {key!r}")
                       for key, value in self.anchors.items()}
        ring_data = {str(key): tuple(str(vertex) for vertex in value)
                     for key, value in self.rings.items()}
        if any(not ring or len(set(ring)) != len(ring)
               or any(vertex not in verts for vertex in ring)
               for ring in ring_data.values()):
            raise ValueError("Ring references missing or repeated vertices")
        from .spatial import SpatialFrame
        frame_data = {}
        for key, value in self.frames.items():
            if isinstance(value, SpatialFrame):
                frame_data[str(key)] = value
            elif hasattr(value, "origin") and hasattr(value, "y") and hasattr(value, "z"):
                frame_data[str(key)] = SpatialFrame(value.origin, value.y, value.z)
            elif isinstance(value, Mapping):
                frame_data[str(key)] = SpatialFrame(value["origin"], value["forward"], value["up"])
            else:
                raise TypeError(f"Frame {key!r} must be a SpatialFrame or frame-like value")
        object.__setattr__(self, "vertices", verts)
        object.__setattr__(self, "faces", parsed)
        object.__setattr__(self, "closed", bool(self.closed))
        object.__setattr__(self, "anchors", anchor_data)
        object.__setattr__(self, "rings", ring_data)
        object.__setattr__(self, "frames", frame_data)

    @classmethod
    def create(
        cls,
        vertices: Mapping[str, Sequence[float]],
        faces: Mapping[str, Sequence[str] | MeshFace],
        *,
        closed: bool = False,
        anchors: Mapping[str, Sequence[float]] | None = None,
        primitive: str | None = None,
        rings: Mapping[str, Sequence[str]] | None = None,
        frames: Mapping[str, object] | None = None,
    ) -> "MeshGeometry":
        verts = {str(k): vector3(v, f"vertex {k!r}") for k, v in vertices.items()}
        if len(verts) != len(vertices): raise ValueError('Vertex names collide after string conversion')
        parsed = {}
        for key, value in faces.items():
            original = value if isinstance(value, MeshFace) else MeshFace(tuple(str(x) for x in value))
            order = original.vertices
            if len(order) not in (3, 4) or len(set(order)) != len(order):
                raise ValueError(f"Face {key!r} needs exactly three or four distinct vertices")
            if any(k not in verts for k in order): raise ValueError(f'Face {key!r} references missing vertices')
            if str(key) in parsed: raise ValueError(f'Face name collision: {key}')
            # Shape/convexity is validated once, by __post_init__ below.
            parsed[str(key)] = original
        ring_data={str(k):tuple(v) for k,v in (rings or {}).items()}
        if any(not v or len(set(v))!=len(v) or any(x not in verts for x in v) for v in ring_data.values()):
            raise ValueError('Ring references missing or repeated vertices')
        from .spatial import SpatialFrame
        frame_data = {}
        for key, value in (frames or {}).items():
            if isinstance(value, SpatialFrame):
                frame_data[str(key)] = value
            elif hasattr(value, "origin") and hasattr(value, "y") and hasattr(value, "z"):
                frame_data[str(key)] = SpatialFrame(value.origin, value.y, value.z)
            elif isinstance(value, Mapping):
                frame_data[str(key)] = SpatialFrame(value["origin"], value["forward"], value["up"])
            else:
                raise TypeError(f"Frame {key!r} must be a SpatialFrame or frame-like value")
        return cls(verts, parsed, bool(closed),
                   {str(k): vector3(v, f"anchor {k!r}") for k, v in (anchors or {}).items()},
                   primitive, ring_data, frame_data)


@dataclass(frozen=True)
class Placement:
    position: object = (0.0, 0.0, 0.0)
    pivot_anchor: str = "center"
    bone: str | None = None
    space: str = "local"

    def __post_init__(self):
        if self.space not in {"local", "world"}:
            raise ValueError("space must be 'local' or 'world'")

    @classmethod
    def at(cls, position, *, space: str = "local") -> "Placement":
        pos = position.strip() if isinstance(position, str) else vector3(position, "placement")
        return cls(pos, space=space)

    @classmethod
    def at_bone(cls, bone: str, *, pivot_anchor: str = "center") -> "Placement":
        if not isinstance(bone, str) or not bone.strip():
            raise ValueError("bone must be a non-empty string")
        return cls(position=f"bone:{bone.strip()}", pivot_anchor=str(pivot_anchor), bone=bone.strip(), space="world")

    @classmethod
    def at_group(cls, group: str, *, pivot_anchor: str = "center") -> "Placement":
        if not isinstance(group, str) or not group.strip():
            raise ValueError("group must be a non-empty string")
        return cls(position=f"group:{group.strip()}", pivot_anchor=str(pivot_anchor), bone=group.strip(), space="world")

    def pivot(self, anchor: str) -> "Placement":
        return Placement(self.position, str(anchor), self.bone, space=self.space)

    def with_space(self, space: str) -> "Placement":
        return Placement(self.position, self.pivot_anchor, self.bone, space=space)


@dataclass(frozen=True)
class PrimitiveHandle:
    name: str
    parent: str
    primitive: str
    anchors: dict[str, Vector3]
    face_groups: dict[str, tuple[str, ...]]
    frames: dict[str, object] = field(default_factory=dict)

    @property
    def groups(self) -> dict[str, tuple[str, ...]]:
        return self.face_groups

    def anchor(self, name: str) -> Vector3:
        if name not in self.anchors:
            raise KeyError(f"Unknown anchor {name!r}; available: {sorted(self.anchors)}")
        return self.anchors[name]

    def frame(self, name: str):
        if name not in self.frames:
            raise KeyError(f"Unknown frame {name!r}; available: {sorted(self.frames)}")
        return self.frames[name]

    def __str__(self) -> str:
        return self.name


class MeshDraft:
    """Deterministic helper for procedural meshes; arbitrary coordinates remain explicit."""

    def __init__(self, *, closed: bool = False):
        self.vertices: dict[str, Vector3] = {}
        self.faces: dict[str, MeshFace] = {}
        self.closed = bool(closed)
        self.anchors: dict[str, Vector3] = {}
        self.rings: dict[str, tuple[str, ...]] = {}
        self.frames: dict[str, object] = {}

    def vertex(self, name: str, position: Sequence[float]) -> "MeshDraft":
        if name in self.vertices:
            raise ValueError(f"Duplicate vertex name: {name}")
        self.vertices[name] = vector3(position, f"vertex {name!r}")
        return self

    def face(self, name: str, vertices: Iterable[str], *, group: str | None = None) -> "MeshDraft":
        if name in self.faces:
            raise ValueError(f"Duplicate face name: {name}")
        self.faces[name] = MeshFace(tuple(vertices), group=group, source_face=name)
        return self

    def anchor(self, name: str, position: Sequence[float]) -> "MeshDraft":
        self.anchors[name] = vector3(position, f"anchor {name!r}")
        return self

    def frame(self, name: str, frame) -> "MeshDraft":
        from .spatial import SpatialFrame
        if not isinstance(frame, SpatialFrame):
            if hasattr(frame, "origin") and hasattr(frame, "y") and hasattr(frame, "z"):
                frame = SpatialFrame(frame.origin, frame.y, frame.z)
            else:
                raise TypeError("frame must be SpatialFrame or Frame")
        self.frames[name] = frame
        self.anchors.setdefault(name, frame.origin)
        return self

    def ring(self, name: str, radius: float, segments: int, *, axis: str = "Y",
             offset: float = 0) -> tuple[str, ...]:
        if radius <= 0 or not math.isfinite(radius): raise ValueError("radius must be positive and finite")
        if not isinstance(segments, int) or not 4 <= segments <= 128:
            raise ValueError("segments must be an integer from 4 to 128")
        axis=axis.upper()
        if axis not in {"X","Y","Z"}: raise ValueError("axis must be X, Y, or Z")
        keys=[]
        for i in range(segments):
            angle=2*math.pi*i/segments; a,b=radius*math.cos(angle),radius*math.sin(angle)
            position=(offset,a,b) if axis=="X" else ((a,offset,b) if axis=="Y" else (a,b,offset))
            key=f"{name}_{i:03d}"; self.vertex(key,position); keys.append(key)
        self.rings[name] = tuple(keys)
        return tuple(keys)

    def ring_of(self, name: str, vertices: Sequence[str]) -> tuple[str, ...]:
        """Register existing vertices (in order) as the ring ``name``; bones reference it as ``mesh:name``."""
        missing = [v for v in vertices if v not in self.vertices]
        if missing or len(vertices) < 3:
            raise ValueError(f"ring {name!r} needs at least 3 existing vertices; unknown: {missing}")
        self.rings[name] = tuple(vertices)
        return self.rings[name]

    def ring_from_profile(self, name: str, profile, frame) -> tuple[str, ...]:
        """Place a ``Profile`` in ``frame`` (profile XY plane, normal = frame Z).

        Registers the ring, an anchor at ``frame.origin`` and an oriented
        frame under ``name`` exactly like a loft section, so the ring can be
        edited with ``edit_ring`` and referenced by bones as ``mesh:name``.
        """
        keys=[]
        for index,(x,y) in enumerate(profile.points):
            key=f"{name}_v{index:03d}"; self.vertex(key,frame.point((x,y,0))); keys.append(key)
        from .spatial import SpatialFrame, mul
        self.rings[name]=tuple(keys)
        self.anchor(name,frame.origin)
        self.frames[name]=SpatialFrame(frame.origin,frame.z,mul(frame.y,-1))
        return tuple(keys)

    def connect_rings(self, a: Sequence[str], b: Sequence[str], *, group: str = "side",
                      prefix: str = "side", skip=()) -> "MeshDraft":
        """Bridge two equal rings with quads ``(a[i], b[i], b[i+1], a[i+1])``.

        ``skip`` leaves the listed quads open (e.g. a thumb root to extrude
        from).  Winding direction does not matter for closed drafts:
        ``build()`` orients every face outward.
        """
        if len(a) != len(b) or len(a) < 3: raise ValueError(
            f"connect_rings needs two rings of equal size (>=3); got {len(a)} and {len(b)}")
        skipped={int(value)%len(a) for value in skip}
        for i in range(len(a)):
            if i in skipped: continue
            j=(i+1)%len(a)
            self.face(f"{prefix}_{i:03d}",(a[i],b[i],b[j],a[j]),group=group)
        return self

    def extrude(self, ring: Sequence[str], name: str, *, offset=(0, 0, 0), scale=1.0,
                frame=None, group: str = "side") -> tuple[str, ...]:
        """Copy ``ring`` moved by ``offset`` and scaled about its centre, bridged with quads.

        ``scale`` is a number or three factors in ``frame``'s local axes
        (default: world axes).  Returns the new ring (registered under
        ``name``) so it can be extruded again or capped.  Typical branch:
        ``connect_rings(..., skip=(k,))`` leaves a quad open, its four
        vertices are the ring to extrude.
        """
        from .spatial import Frame, add
        ring=tuple(ring)
        if len(ring)<3: raise ValueError("extrude needs a ring of at least three vertices")
        values=(float(scale),)*3 if isinstance(scale,(int,float)) else tuple(float(v) for v in scale)
        if len(values)!=3 or any(not math.isfinite(v) or v<=0 for v in values):
            raise ValueError("extrude scale must be positive (a number or three factors)")
        delta=vector3(offset,"extrude offset")
        center=self.center(ring); basis=frame or Frame()
        pivot=Frame(add(center,delta),basis.x,basis.y,basis.z)
        keys=[]
        for index,key in enumerate(ring):
            local=pivot.local(add(self.vertices[key],delta))
            new=f"{name}_v{index:03d}"
            self.vertex(new,pivot.point(tuple(a*b for a,b in zip(local,values))))
            keys.append(new)
        self.rings[name]=tuple(keys)
        self.anchor(name,self.center(keys))
        self.connect_rings(ring,keys,group=group,prefix=name)
        return tuple(keys)

    def _oriented_faces(self) -> dict[str, "MeshFace"]:
        """Faces made consistent per connected component, then flipped outward by volume."""
        faces=dict(self.faces)
        edge_faces: dict[frozenset, list[str]] = {}
        for key,face in faces.items():
            order=face.vertices
            for a,b in zip(order,order[1:]+order[:1]):
                edge_faces.setdefault(frozenset((a,b)),[]).append(key)
        if any(len(refs)>2 for refs in edge_faces.values()):
            return faces  # non-manifold: leave it for validation to report
        def directed(key,a,b):
            order=faces[key].vertices
            return any(order[i]==a and order[(i+1)%len(order)]==b for i in range(len(order)))
        def flip(key):
            face=faces[key]; faces[key]=MeshFace(tuple(reversed(face.vertices)),face.group,face.source_face)
        seen=set()
        for seed in sorted(faces):
            if seed in seen: continue
            component=[]; pending=[seed]; seen.add(seed)
            while pending:
                key=pending.pop(); component.append(key)
                order=faces[key].vertices
                for a,b in zip(order,order[1:]+order[:1]):
                    for other in edge_faces[frozenset((a,b))]:
                        if other in seen: continue
                        if directed(other,a,b): flip(other)   # neighbour must run b->a
                        seen.add(other); pending.append(other)
            volume=0.
            for key in component:
                order=faces[key].vertices
                for i in range(1,len(order)-1):
                    a,b,c=(self.vertices[k] for k in (order[0],order[i],order[i+1]))
                    volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])
                             +a[2]*(b[0]*c[1]-b[1]*c[0]))/6
            if volume<0:
                for key in component: flip(key)
        return faces

    def orient_outward(self) -> "MeshDraft":
        """Make winding consistent and outward (closed drafts do this on ``build()``)."""
        self.faces=self._oriented_faces()
        return self

    def cap(self, ring: Sequence[str], *, name: str = "cap", center: Sequence[float] | None = None,
            reverse: bool = False, group: str | None = None,
            inset: float | None = None, allow_triangles: bool = False) -> "MeshDraft":
        if not allow_triangles:
            if len(ring) < 4 or len(ring) % 2:
                raise ValueError("quad caps need an even ring with at least four vertices")
        else:
            if len(ring) < 3:
                raise ValueError("caps need a ring with at least three vertices")
        if name in self.faces or f"{name}_center" in self.vertices or f"{name}_inner_000" in self.vertices:
            raise ValueError(f"cap name {name!r} is already used on this draft: pass a different name= to each cap")
        order=tuple(reversed(ring)) if reverse else tuple(ring)
        if len(order) == 3:
            self.face(name, order, group=group or name)
            return self
        if inset is not None:
            inset=float(inset)
            if not math.isfinite(inset) or not 0<inset<1:
                raise ValueError("cap inset must be strictly between 0 and 1")
            center=vector3(center if center is not None else tuple(
                sum(self.vertices[key][axis] for key in ring)/len(ring) for axis in range(3)),
                "cap center")
            inner=[]
            for index,key in enumerate(ring):
                inner_key=f"{name}_inner_{index:03d}"
                point=tuple(center[axis]+inset*(self.vertices[key][axis]-center[axis])
                            for axis in range(3))
                self.vertex(inner_key,point); inner.append(inner_key)
            for index in range(len(ring)):
                following=(index+1)%len(ring)
                quad=(ring[index],ring[following],inner[following],inner[index])
                if reverse: quad=tuple(reversed(quad))
                self.face(f"{name}_ring_{index:03d}",quad,group=group or name)
            self.cap(inner,name=f"{name}_center",center=center,reverse=reverse,
                     group=group or name, allow_triangles=allow_triangles)
            return self
        center=vector3(center if center is not None else tuple(
            sum(self.vertices[key][axis] for key in ring)/len(ring) for axis in range(3)),
            "cap center")
        if len(order)==4:
            self.face(name,order,group=group or name)
            return self
        if len(order) % 2 != 0:
            center_key = f"{name}_center"
            self.vertex(center_key, center)
            for index in range(len(order)):
                following = (index + 1) % len(order)
                tri = (center_key, order[index], order[following])
                self.face(f"{name}_{index:03d}", tri, group=group or name)
            return self
        center_key=f"{name}_center"
        self.vertex(center_key,center)
        for index in range(0,len(order),2):
            quad=(center_key,order[index],order[(index+1)%len(order)],
                  order[(index+2)%len(order)])
            self.face(f"{name}_{index//2:03d}",quad,group=group or name)
        return self

    def mirror(self, axis: str = "X") -> "MeshDraft":
        """Reflect across a world plane, keeping faces outward and frames right-handed."""
        axis=axis.upper()
        if axis not in {"X","Y","Z"}: raise ValueError("axis must be X, Y, or Z")
        index="XYZ".index(axis)
        self.vertices={k:tuple(-v if i==index else v for i,v in enumerate(p)) for k,p in self.vertices.items()}
        self.anchors={k:tuple(-v if i==index else v for i,v in enumerate(p)) for k,p in self.anchors.items()}
        self.faces={k:MeshFace(tuple(reversed(f.vertices)),f.group,f.source_face) for k,f in self.faces.items()}
        self.frames={k:f.mirrored(axis) for k,f in self.frames.items()}
        return self

    def _selection(self, keys, source):
        keys = (keys,) if isinstance(keys, str) else tuple(keys)
        if not keys:
            raise ValueError("Selection is empty")
        if any(k not in source for k in keys):
            raise KeyError(f"Unknown or removed selection: {keys}")
        return tuple(dict.fromkeys(keys))

    def select_vertices(self, *, names=None, faces=None, ring=None, axis=None, t=(0, 1)):
        if sum(v is not None for v in (names, faces, ring, axis)) != 1:
            raise ValueError("Choose one vertex selector")
        if faces is not None:
            names = sorted({v for f in self._selection(faces, self.faces) for v in self.faces[f].vertices})
        elif ring is not None:
            if ring not in self.rings:
                raise KeyError(f"Unknown ring: {ring}")
            names = self.rings[ring]
        elif axis is not None:
            index = "XYZ".index(axis.upper())
            low, high = t
            if not 0 <= low <= high <= 1:
                raise ValueError("Normalized interval must be within [0,1]")
            values = [p[index] for p in self.vertices.values()]
            a, b = min(values), max(values)
            names = sorted(k for k, p in self.vertices.items() if low - 1e-10 <= (p[index] - a) / (b - a) <= high + 1e-10) if b > a else sorted(self.vertices)
        return self._selection(names, self.vertices)

    def _deform(self, keys, transform, weights=None):
        from .spatial import SpatialFrame, add, sub
        keys = self._selection(keys, self.vertices)
        weights = {} if weights is None else weights
        if set(weights) - set(keys):
            raise ValueError("Weights reference vertices outside selection")
        new = {}
        for k in keys:
            w = float(weights.get(k, 1))
            if not math.isfinite(w) or not 0 <= w <= 1:
                raise ValueError("Weight must be in [0,1]")
            p = self.vertices[k]
            q = vector3(transform(p))
            new[k] = tuple(a + w * (b - a) for a, b in zip(p, q))
        self.vertices.update(new)
        if set(keys) == set(self.vertices) and not weights:
            self.anchors = {name: vector3(transform(point)) for name, point in self.anchors.items()}
            transformed = {}
            for name, frame in self.frames.items():
                origin = vector3(transform(frame.origin))
                forward = sub(vector3(transform(add(frame.origin, frame.forward))), origin)
                up = sub(vector3(transform(add(frame.origin, frame.up))), origin)
                transformed[name] = SpatialFrame(origin, forward, up)
            self.frames = transformed
        elif not weights:
            # A ring anchor/frame (e.g. a loft section origin that bones may
            # reference) follows its ring only when the whole ring moved
            # together; partial edits leave the authored anchor untouched.
            selected = set(keys)
            for name, ring in self.rings.items():
                if not ring or not set(ring) <= selected:
                    continue
                if name in self.anchors:
                    self.anchors[name] = vector3(transform(self.anchors[name]))
                if name in self.frames:
                    frame = self.frames[name]
                    origin = vector3(transform(frame.origin))
                    forward = sub(vector3(transform(add(frame.origin, frame.forward))), origin)
                    up = sub(vector3(transform(add(frame.origin, frame.up))), origin)
                    try:
                        self.frames[name] = SpatialFrame(origin, forward, up)
                    except ValueError:
                        pass
        return self

    def translate_vertices(self, vertices, offset, *, frame=None, weights=None):
        from .spatial import add
        offset = frame.vector(offset) if frame is not None else vector3(offset)
        return self._deform(vertices, lambda p: add(p, offset), weights)

    def rotate_vertices(self, vertices, degrees, *, axis=(0, 0, 1), pivot=None, frame=None, weights=None):
        from .spatial import add, sub, turn
        keys = self._selection(vertices, self.vertices)
        pivot = pivot if pivot is not None else (frame.origin if frame else self.center(keys))
        axis = frame.vector(axis) if frame else axis
        return self._deform(keys, lambda p: add(pivot, turn(sub(p, pivot), axis, degrees)), weights)

    def scale_vertices(self, vertices, factors, *, pivot=None, frame=None, weights=None):
        from .spatial import Frame
        keys = self._selection(vertices, self.vertices)
        values = (factors,) * 3 if isinstance(factors, (float, int)) else tuple(factors)
        if len(values) != 3 or any(not math.isfinite(v) or v <= 0 for v in values):
            raise ValueError("Scale must be positive; use mirror for reflection")
        basis = frame or Frame()
        frame = Frame(pivot if pivot is not None else (frame.origin if frame else self.center(keys)), basis.x, basis.y, basis.z)
        return self._deform(keys, lambda p: frame.point(tuple(a * b for a, b in zip(frame.local(p), values))), weights)

    def edit_ring(self, ring_name: str) -> "_RingEditor":
        return _RingEditor(self, ring_name)

    @classmethod
    def from_geometry(cls, geometry: MeshGeometry) -> "MeshDraft":
        import copy
        d = cls(closed=geometry.closed)
        d.vertices = copy.deepcopy(dict(geometry.vertices))
        d.faces = copy.deepcopy(dict(geometry.faces))
        d.anchors = copy.deepcopy(dict(geometry.anchors))
        d.rings = copy.deepcopy(dict(geometry.rings))
        d.frames = copy.deepcopy(dict(getattr(geometry, "frames", {})))
        return d

    def center(self, vertices=None) -> tuple[float, float, float]:
        keys = tuple(vertices) if vertices is not None else tuple(self.vertices)
        if not keys:
            raise ValueError("Selection is empty")
        return tuple(sum(self.vertices[k][i] for k in keys) / len(keys) for i in range(3))

    def bounds_point(self, t=(0.5, 0.5, 0.5)) -> tuple[float, float, float]:
        if len(t) != 3 or any(not math.isfinite(v) or not 0 <= v <= 1 for v in t):
            raise ValueError("Bounds parameters must be within [0,1]")
        if not self.vertices:
            raise ValueError("Mesh has no vertices")
        return tuple(
            min(p[i] for p in self.vertices.values()) + t[i] * (max(p[i] for p in self.vertices.values()) - min(p[i] for p in self.vertices.values()))
            for i in range(3)
        )

    def validate(self) -> dict[str, list[str]]:
        from .mesh_validation import validate_geometry
        geometry = self.build()
        errors, warnings = validate_geometry(geometry, check_intersections=True, name="draft")
        if errors:
            raise ValueError("; ".join(errors))
        return {"errors": errors, "warnings": warnings}

    def build(self, *, primitive: str | None = None, orient: bool | None = None) -> MeshGeometry:
        """Freeze into ``MeshGeometry``.

        Closed drafts are oriented outward first (``orient=False`` keeps the
        authored winding so validation reports it instead).
        """
        faces = self._oriented_faces() if (self.closed if orient is None else orient) else self.faces
        geometry = MeshGeometry.create(self.vertices, faces, closed=self.closed,
                                       anchors=self.anchors, primitive=primitive, rings=self.rings,
                                       frames=self.frames)
        return geometry


class _RingEditor:
    """Edit one named ring in its own profile plane.

    For rings that carry a frame (every loft/segment/sweep section and
    ``MeshDraft.ring_from_profile``), ``(x, y)`` values are profile axes and
    the third axis is the ring normal, and the pivot is the section origin.
    Rings without a frame fall back to world axes around the ring centroid.
    """

    def __init__(self, draft: MeshDraft, ring_name: str):
        if ring_name not in draft.rings:
            raise KeyError(f"Unknown ring {ring_name!r}; available: {sorted(draft.rings)}")
        self._draft = draft
        self._ring_name = ring_name
        self._keys = draft.rings[ring_name]

    def _frame(self, frame):
        if frame is not None:
            return frame
        spatial = self._draft.frames.get(self._ring_name)
        if spatial is None:
            return None
        from .spatial import Frame, mul
        # Section frames store forward=normal and up=-profile_y.
        return Frame(spatial.origin, spatial.right, mul(spatial.up, -1), spatial.forward)

    def _pivot(self, pivot, frame):
        if pivot is not None:
            return pivot
        if frame is not None and self._ring_name in self._draft.anchors:
            return self._draft.anchors[self._ring_name]
        return None

    def scale(self, factors, *, pivot=None, frame=None):
        if isinstance(factors, (float, int)):
            factors = (factors, factors, 1.0)
        elif len(factors) == 2:
            factors = (factors[0], factors[1], 1.0)
        frame = self._frame(frame)
        self._draft.scale_vertices(self._keys, factors, pivot=self._pivot(pivot, frame), frame=frame)
        return self

    def translate(self, offset, *, frame=None):
        if len(offset) == 2:
            offset = (offset[0], offset[1], 0.0)
        self._draft.translate_vertices(self._keys, offset, frame=self._frame(frame))
        return self

    def rotate(self, degrees, *, axis=(0, 0, 1), pivot=None, frame=None):
        frame = self._frame(frame)
        self._draft.rotate_vertices(self._keys, degrees, axis=axis,
                                    pivot=self._pivot(pivot, frame), frame=frame)
        return self
