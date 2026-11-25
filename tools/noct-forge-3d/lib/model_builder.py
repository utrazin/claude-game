"""Small, dependency-free builder for Blockbench generic ``.bbmodel`` files."""

from __future__ import annotations

import copy
import json
import math
import tempfile
import uuid
from contextlib import contextmanager

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .geometry_types import MeshDraft, MeshFace, MeshGeometry, Placement, PrimitiveHandle
from .spatial import (Frame, SpatialFrame, SurfaceContact, ModelOrientation, add, box_surface_contacts,
                      cross, dot, mul, sub, turn, unit)
from .armature import ArmatureHandle, BindingReport


Vector3 = tuple[float, float, float]


def _vector3(value: Sequence[float], label: str) -> Vector3:
    if len(value) != 3:
        raise ValueError(f"{label} must contain exactly three numbers")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label} must contain finite numbers")
    return result  # type: ignore[return-value]


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _canonical_quad(order, vertices, planar=False):
    """A quad renders (Blockbench) and samples as triangles split on its first-third vertex diagonal A-C, so a
    non-planar quad's diagonal is part of its shape, and on any quad it decides how the texture maps (a UV that
    is not an exact affine image of the quad, such as an unfolded chart, bends along it). Rotate the vertex order
    (winding kept) so A-C is the shorter diagonal; ties go to the diagonal whose midpoint is higher, then further
    forward, then to the one holding the highest, most forward, outermost (|x|) vertex. Mirror images measure the
    same, so mirrored quads split on mirrored diagonals and stay mirror-identical. Planar quads are unchanged
    unless ``planar`` (the UV stage canonicalizes them too)."""
    order = list(order)
    p = [tuple(float(c) for c in vertices[k]) for k in order]
    sub = lambda a, b: tuple(x - y for x, y in zip(a, b))
    cross = lambda a, b: (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    normal = cross(sub(p[2], p[0]), sub(p[3], p[1]))
    size = max(abs(c) for point in p for c in sub(point, p[0])) or 1.0
    length = dot(normal, normal) ** 0.5
    if not planar and (length <= 1e-12 or abs(dot(sub(p[1], p[0]), normal)) / length <= 1e-6 * size):
        return order                                   # planar: the diagonal does not change the shape
    eps = 1e-9 * size

    def key(i):                                        # diagonal i - (i + 2)
        a, b = p[i], p[i + 2]
        mid = tuple((x + y) / 2 for x, y in zip(a, b))
        top = max((a, b), key=lambda v: (round(v[1] / eps), round(v[2] / eps), round(abs(v[0]) / eps)))
        return (round(dot(sub(a, b), sub(a, b)) ** 0.5 / eps), -round(mid[1] / eps), -round(mid[2] / eps),
                -round(top[1] / eps), -round(top[2] / eps), -round(abs(top[0]) / eps))

    return order if key(0) <= key(1) else order[1:] + order[:1]


def _clean_vector(value: Vector3) -> list[int | float]:
    return [_clean_number(item) for item in value]


def _tags(value, label="tags") -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raise TypeError(f"{label} must be an iterable of strings, not one string")
    result = list(value)
    if any(not isinstance(tag, str) or not tag for tag in result):
        raise ValueError(f"{label} must contain non-empty strings")
    return list(dict.fromkeys(result))


# Bilateral name suffixes understood by every mirror operation.
_SIDE_PAIRS = (("_left", "_right"), ("_L", "_R"), (".L", ".R"), (".l", ".r"), ("_l", "_r"))


def _swap_side(name: str) -> str | None:
    """``arm_L`` -> ``arm_R`` (and the other known suffix pairs); None if no suffix."""
    for left, right in _SIDE_PAIRS:
        if name.endswith(left):
            return name[:-len(left)] + right
        if name.endswith(right):
            return name[:-len(right)] + left
    return None


@contextmanager
def _about_mesh(name: str):
    """Prefix construction errors with the mesh being built."""
    try:
        yield
    except (ValueError, KeyError, TypeError) as exc:
        message = exc.args[0] if exc.args else str(exc)
        if isinstance(message, str) and not message.startswith(f"Mesh {name!r}"):
            raise type(exc)(f"Mesh {name!r}: {message}") from exc
        raise


@dataclass(frozen=True)
class ChainSegment:
    """One link of ``add_transform_chain`` (a rigid, group-based chain).

    ``direction`` is optional and replaces the running direction; ``profile``
    or ``sections`` (``SegmentSection``) add a mesh along the link.
    """
    name: str
    length: float
    direction: Sequence[float] | None = None
    up: Sequence[float] | None = None
    profile: object = None
    sections: object = None
    element: str | None = None
    tags: Iterable[str] | None = None
    element_tags: Iterable[str] | None = None
    start_cap: object = "flat"
    end_cap: object = "flat"

    def as_dict(self):
        data = {"name": self.name, "length": self.length, "start_cap": self.start_cap,
                "end_cap": self.end_cap}
        for key in ("direction", "up", "profile", "sections", "element", "tags", "element_tags"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


def _stable_uuid(*parts) -> str:
    """Ids derived from kind and name, so the same recipe exports the same file every time."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "noctforge:" + ":".join(str(p) for p in parts)))


@dataclass
class _Group:
    name: str
    parent: str | None
    pivot: Vector3
    rotation: Vector3
    tags: list[str]
    role: str = "folder"
    uuid: str = ""

    def __post_init__(self):
        self.uuid = self.uuid or _stable_uuid("group", self.name)


@dataclass
class _Armature:
    name: str
    origin: Vector3
    tags: list[str]
    parent: str | None = None
    uuid: str = ""

    def __post_init__(self):
        self.uuid = self.uuid or _stable_uuid("armature", self.name)


@dataclass
class _ArmatureBone:
    name: str
    armature: str
    parent: str | None
    origin: Vector3
    rotation: Vector3
    length: float
    width: float
    connected: bool
    tags: list[str]
    start: Vector3
    end: Vector3
    vertex_weights: dict[str, float] = field(default_factory=dict)
    uuid: str = ""

    def __post_init__(self):
        self.uuid = self.uuid or _stable_uuid("bone", self.name)


@dataclass
class _Element:
    kind: str
    name: str
    parent: str
    from_: Vector3
    to_: Vector3 | None
    size: tuple[float, float] | None
    normal: str | None
    tags: list[str]
    origin: Vector3
    rotation: Vector3
    inflate: float = 0
    visibility: bool = True
    shading_mode: str | None = None
    stretch: Vector3 | None = None
    uuid: str = ""
    uv_offset: list[int] = field(default_factory=lambda: [0, 0])
    faces: dict = field(default_factory=dict)
    vertices: dict[str, Vector3] = field(default_factory=dict)
    mesh_closed: bool = False
    anchors: dict[str, Vector3] = field(default_factory=dict)
    primitive: str | None = None
    mesh_rings: dict[str, tuple[str, ...]] = field(default_factory=dict)
    frames: dict[str, SpatialFrame] = field(default_factory=dict)
    parent_kind: str = "group"
    no_overlap_check: bool = False

    def __post_init__(self):
        self.uuid = self.uuid or _stable_uuid("element", self.name)


@dataclass(frozen=True)
class _Socket:
    name: str
    parent: str
    position: Vector3
    forward: Vector3
    up: Vector3
    source: str | None = None
    offset: Vector3 = (0.,0.,0.)
    inherit_forward: bool = False
    inherit_up: bool = False
    parent_kind: str = "group"

    @property
    def frame(self) -> SpatialFrame:
        return SpatialFrame(self.position, self.forward, self.up)





class ModelBuilder:
    """Build named rigid groups and armatures for a Blockbench generic model."""

    def __init__(
        self,
        name: str,
        *,

        format_id: str = "free",
        grid_step: float | None = None,
        max_nodes: int | None = None,
        allow_quads: bool = True,
        check_coplanar: bool = True,
        require_integer_dimensions: bool = True,
        modeling_mode: str = "free",
        orientation: ModelOrientation | None = None,
    ) -> None:
        if not name.strip():
            raise ValueError("Model name cannot be empty")
        self.name = name.strip()
        self.format_id = format_id.strip() or "free"
        self.check_coplanar = bool(check_coplanar)
        self.require_integer_dimensions = bool(require_integer_dimensions)
        self.modeling_mode = str(modeling_mode).strip().lower()
        if self.modeling_mode not in {"box", "free"}:
            raise ValueError("modeling_mode must be 'box' or 'free'")
        if orientation is not None and not isinstance(orientation, ModelOrientation):
            raise TypeError("orientation must be a ModelOrientation")
        self.orientation = orientation or ModelOrientation()
        if grid_step is not None and (not math.isfinite(grid_step) or grid_step <= 0):
            raise ValueError("grid_step must be a positive finite number")
        if max_nodes is not None and max_nodes <= 0:
            raise ValueError("max_nodes must be positive")
        self.grid_step = float(grid_step) if grid_step is not None else None
        self.max_nodes = max_nodes
        self.allow_quads = allow_quads
        self._groups: dict[str, _Group] = {}
        self._armatures: dict[str, _Armature] = {}
        self._armature_bones: dict[str, _ArmatureBone] = {}
        self._bindings: dict[str, dict[str, dict[str, float]]] = {}
        self._binding_topology: dict[str, tuple] = {}
        self._binding_policies: dict[str, dict[str, object]] = {}
        self._armature_chains: dict[str, tuple[str, ...]] = {}
        self._elements: list[_Element] = []
        self._element_names: set[str] = set()
        self._sockets: dict[str, _Socket] = {}
        self._chains: dict[str, tuple[str,...]] = {}

    def resolve_point(self, value) -> Vector3:
        """Resolve the shared spatial-reference syntax to a rest-pose world point."""
        if isinstance(value, SpatialFrame): return value.origin
        if isinstance(value, Frame): return value.origin
        if not isinstance(value, str): return _vector3(value, "point reference")
        value = value.strip()
        if value.startswith("group:"):
            name = value[6:]
            if name not in self._groups: raise KeyError(f"Unknown group reference {value!r}")
            return self._group_world_frame(name).origin
        if value.startswith("armature:"):
            name = value[9:]
            if name not in self._armatures: raise KeyError(f"Unknown armature reference {value!r}")
            return self._armatures[name].origin
        if value.startswith("bone:"):
            name = value[5:]
            if name not in self._armature_bones: raise KeyError(f"Unknown armature bone reference {value!r}")
            return self._armature_bone_world_frame(name).origin
        if value.startswith("socket:"):
            return self.get_socket(value[7:]).origin
        if ":" in value:
            element, anchor = value.split(":", 1)
            return self.get_anchor(element, anchor)
        candidates = [("group", value in self._groups), ("bone", value in self._armature_bones),
                      ("armature", value in self._armatures), ("socket", value in self._sockets)]
        matches=[kind for kind,present in candidates if present]
        if len(matches)>1: raise KeyError(f"Ambiguous spatial reference {value!r}; use an explicit prefix")
        if matches == ["group"]: return self._group_world_frame(value).origin
        if matches == ["bone"]: return self._armature_bone_world_frame(value).origin
        if matches == ["armature"]: return self._armatures[value].origin
        if matches == ["socket"]: return self.get_socket(value).origin
        raise KeyError(f"Unknown spatial reference {value!r}")

    _resolve_point = resolve_point

    def offset(self,ref,local=(0,0,0)) -> Vector3:
        """Return a point offset in the referenced frame's local axes."""
        return self.resolve_frame(ref).point(local)

    def between(self,start,end,t=.5) -> Vector3:
        t=float(t)
        if not math.isfinite(t): raise ValueError("between t must be finite")
        a,b=self.resolve_point(start),self.resolve_point(end)
        return tuple(a[i]+(b[i]-a[i])*t for i in range(3))

    def resolve_frame(self, value) -> SpatialFrame:
        """Resolve a bone, socket, or oriented element anchor."""
        if isinstance(value, SpatialFrame): return value
        if isinstance(value, Frame): return SpatialFrame.from_frame(value)
        if not isinstance(value, str):
            return SpatialFrame(self.resolve_point(value))
        value = value.strip()
        if value.startswith("group:"):
            name = value[6:]
            if name not in self._groups: raise KeyError(f"Unknown group reference {value!r}")
            return self._group_world_frame(name)
        if value.startswith("armature:"):
            name=value[9:]
            if name not in self._armatures: raise KeyError(f"Unknown armature reference {value!r}")
            return SpatialFrame(self._armatures[name].origin)
        if value.startswith("bone:"):
            name = value[5:]
            if name not in self._armature_bones: raise KeyError(f"Unknown armature bone reference {value!r}")
            return self._armature_bone_world_frame(name)
        if value.startswith("socket:"): return self.get_socket(value[7:])
        if ":" in value:
            element, anchor = value.split(":", 1)
            return self.get_frame(element, anchor)
        candidates=[("group",value in self._groups),("bone",value in self._armature_bones),
                    ("armature",value in self._armatures),("socket",value in self._sockets)]
        matches=[kind for kind,present in candidates if present]
        if len(matches)>1: raise KeyError(f"Ambiguous spatial reference {value!r}; use an explicit prefix")
        if matches == ["group"]: return self._group_world_frame(value)
        if matches == ["bone"]: return self._armature_bone_world_frame(value)
        if matches == ["armature"]: return SpatialFrame(self._armatures[value].origin)
        if matches == ["socket"]: return self.get_socket(value)
        raise KeyError(f"Unknown spatial reference {value!r}")

    def _group_world_frame(self, name: str) -> SpatialFrame:
        group = self._groups[name]
        point = group.pivot
        forward, up = (0., 1., 0.), (0., 0., 1.)
        chain = []
        current = name
        while current is not None:
            item = self._groups[current]
            chain.append(item)
            current = item.parent
        # The group's own rotation changes its axes, while only ancestors move its pivot.
        forward = self._rotate_vector(forward, group.rotation)
        up = self._rotate_vector(up, group.rotation)
        for ancestor in chain[1:]:
            point = self._rotate_about(point, ancestor.pivot, ancestor.rotation)
            forward = self._rotate_vector(forward, ancestor.rotation)
            up = self._rotate_vector(up, ancestor.rotation)
        return SpatialFrame(point, forward, up)

    def _armature_bone_world_frame(self,name: str) -> SpatialFrame:
        bone=self._armature_bones[name]
        if bone.parent is None:
            parent_frame=SpatialFrame(self._armatures[bone.armature].origin)
        else:
            parent_frame=self._armature_bone_world_frame(bone.parent)
        origin=parent_frame.point(bone.origin)
        forward=parent_frame.vector(self._rotate_vector((0,1,0),bone.rotation))
        up=parent_frame.vector(self._rotate_vector((0,0,1),bone.rotation))
        return SpatialFrame(origin,forward,up)

    @staticmethod
    def _direction_euler(direction) -> Vector3:
        x,y,z=unit(direction)
        rx=math.degrees(math.asin(max(-1.,min(1.,z))))
        rz=math.degrees(math.atan2(-x,y))
        return (rx,0.,rz)

    def get_socket(self, name: str) -> SpatialFrame:
        if name not in self._sockets: raise KeyError(f"Unknown socket {name!r}")
        socket = self._sockets[name]
        point, forward, up = socket.position, socket.forward, socket.up
        if socket.parent_kind == "bone":
            owner = self._armature_bone_world_frame(socket.parent)
            frame = SpatialFrame(owner.point(point), owner.vector(forward), owner.vector(up))
            if socket.source is not None:
                source = self.resolve_frame(socket.source)
                frame = SpatialFrame(
                    source.origin,
                    source.forward if socket.inherit_forward else frame.forward,
                    source.up if socket.inherit_up else frame.up,
                ).offset(socket.offset)
            return frame
        current = socket.parent
        while current is not None:
            bone = self._groups[current]
            point = self._rotate_about(point, bone.pivot, bone.rotation)
            forward = self._rotate_vector(forward, bone.rotation)
            up = self._rotate_vector(up, bone.rotation)
            current = bone.parent
        frame=SpatialFrame(point,forward,up)
        if socket.source is not None:
            point=self.resolve_point(socket.source)
            if socket.inherit_forward or socket.inherit_up:
                source=self.resolve_frame(socket.source)
                frame=SpatialFrame(point,source.forward if socket.inherit_forward else frame.forward,
                                   source.up if socket.inherit_up else frame.up)
            else:
                frame=SpatialFrame(point,frame.forward,frame.up)
            frame=frame.offset(socket.offset)
        return frame

    def add_socket(self, name: str, parent: str, *, at=None,
                   forward=None, up=None, offset=(0, 0, 0)) -> "ModelBuilder":
        """Declare a named attachment frame owned by one bone."""
        parent_kind = "group"
        if isinstance(parent, str) and parent.startswith("bone:"):
            parent = parent[5:]
            parent_kind = "bone"
        elif parent in self._armature_bones:
            parent_kind = "bone"
        if parent_kind == "bone":
            if parent not in self._armature_bones:
                raise KeyError(f"Unknown parent armature bone: {parent}")
        else:
            kind, parent = self._normalize_parent(parent)
            if kind != "group":
                raise ValueError("Sockets must be owned by a group or armature bone")
        if not name or not name.strip() or name in self._sockets:
            raise ValueError(f"Invalid or duplicate socket name {name!r}")
        owner_frame = (self._armature_bone_world_frame(parent) if parent_kind == "bone"
                       else self._group_world_frame(parent))
        source_frame = owner_frame if at is None else None
        source_oriented=False
        if at is not None:
            try:
                source_frame = self.resolve_frame(at); source_oriented=True
            except KeyError:
                source_frame = SpatialFrame(self.resolve_point(at))
        assert source_frame is not None
        position = source_frame.origin
        if parent_kind == "group" and at is not None and not isinstance(at, str):
            # numbers are bind-space (rest pose): follow the owner chain like the boxes in the same group do
            current = parent
            while current is not None:
                group = self._groups[current]
                position = self._rotate_about(position, group.pivot, group.rotation)
                current = group.parent
        inherit_forward=forward is None; inherit_up=up is None
        y = unit(source_frame.forward if inherit_forward else forward)
        up_value = unit(source_frame.up if inherit_up else up)
        if parent_kind == "bone" and not inherit_forward:
            y = owner_frame.vector(y)
        elif not inherit_forward:
            for group_name in self._group_chain(parent):
                y=self._rotate_vector(y,self._groups[group_name].rotation)
        if parent_kind == "bone" and not inherit_up:
            up_value = owner_frame.vector(up_value)
        elif not inherit_up:
            for group_name in self._group_chain(parent):
                up_value=self._rotate_vector(up_value,self._groups[group_name].rotation)
        if abs(dot(y, up_value)) > 1 - 1e-8:
            raise ValueError("Socket forward and up cannot be collinear")
        x = unit(cross(y, up_value))
        z = unit(cross(x, y))
        local_offset = _vector3(offset, "socket offset")
        position = tuple(position[i] + x[i] * local_offset[0] + y[i] * local_offset[1] +
                         z[i] * local_offset[2] for i in range(3))
        if parent_kind == "bone":
            position = owner_frame.local(position)
            y = (dot(y, owner_frame.right), dot(y, owner_frame.forward), dot(y, owner_frame.up))
            z = (dot(z, owner_frame.right), dot(z, owner_frame.forward), dot(z, owner_frame.up))
        else:
            # Store in unrotated bind space; get_socket applies the owner chain live.
            for group_name in reversed(self._group_chain(parent)):
                group = self._groups[group_name]
                position = self._inverse_rotate(position, group.pivot, group.rotation)
                y = self._inverse_rotate_vector(y, group.rotation)
                z = self._inverse_rotate_vector(z, group.rotation)
        source_ref=at.strip() if isinstance(at,str) else None
        self._sockets[name] = _Socket(name.strip(), parent, position, y, z,source_ref,
            local_offset,source_oriented and inherit_forward,source_oriented and inherit_up,
            parent_kind)
        return self

    def get_surface_contact(self, name: str, contact: str, *, world: bool = True) -> SurfaceContact:
        """Return a stable semantic surface contact for a native element.

        Contacts deliberately derive from the element's local bounds instead
        of treating generic anchors as normals.  A named anchor remains a
        point; a contact additionally guarantees an outward normal and a
        tangent basis suitable for relational placement.
        """
        element = next((e for e in self._elements if e.name == name), None)
        if element is None:
            raise KeyError(f"Unknown element {name!r}")
        raw_contact = str(contact).strip().lower()
        bounds_contact = raw_contact.startswith(("bounds.", "bounds:"))
        key = raw_contact.removeprefix("bounds.").removeprefix("bounds:")
        key = {"base": "bottom"}.get(key, key)
        if key == "center" and key in element.frames:
            frame = self.get_frame(name, key, world=world)
            return SurfaceContact.from_spatial_frame(frame)
        if key not in {"left", "right", "bottom", "top", "back", "front"}:
            raise KeyError(f"Unknown surface contact {name}:{contact}")
        direction = self._semantic_contact_direction(key)
        physical_key = self._cardinal_contact_key(direction)
        if element.kind == "cube":
            local = box_surface_contacts(element.from_, element.to_ or element.from_)[physical_key]
            local_origin = local.origin
        elif element.vertices and not bounds_contact:
            return self._mesh_surface_contact(element, key, direction, world=world)
        elif element.vertices:
            low = tuple(min(point[i] for point in element.vertices.values()) for i in range(3))
            high = tuple(max(point[i] for point in element.vertices.values()) for i in range(3))
            local = self._bounds_surface_contact(low, high, physical_key)
            local_origin = add(element.origin, local.origin)
        else:
            vertices, order = self._quad_vertices(element)
            points = [tuple(vertices[v]) for v in order]
            low = tuple(min(point[i] for point in points) for i in range(3))
            high = tuple(max(point[i] for point in points) for i in range(3))
            local = self._bounds_surface_contact(low, high, physical_key)
            local_origin = add(element.origin, local.origin)
        if not world:
            return SurfaceContact(local_origin, local.normal, local.tangent_u, local.tangent_v)
        return SurfaceContact(
            self._element_point_world(element, local_origin),
            self._element_vector_world(element, local.normal),
            self._element_vector_world(element, local.tangent_u),
            self._element_vector_world(element, local.tangent_v),
        )

    def _semantic_contact_direction(self, key: str) -> Vector3:
        """Resolve semantic sides through the persisted orientation contract."""
        up = self.orientation.up_vector
        front = self.orientation.front_vector
        right = unit(cross(up, front))
        return {
            "top": up, "bottom": mul(up, -1.),
            "front": front, "back": mul(front, -1.),
            "right": right, "left": mul(right, -1.),
        }[key]

    @staticmethod
    def _cardinal_contact_key(direction: Vector3) -> str:
        cardinal = {
            (1., 0., 0.): "right", (-1., 0., 0.): "left",
            (0., 1., 0.): "top", (0., -1., 0.): "bottom",
            (0., 0., 1.): "front", (0., 0., -1.): "back",
        }
        try:
            return cardinal[tuple(float(value) for value in direction)]
        except KeyError as exc:  # ModelOrientation is cardinal; this protects future extensions.
            raise ValueError(f"Surface contact direction must be cardinal, got {direction!r}") from exc

    def _mesh_surface_contact(self, element: _Element, key: str, desired: Vector3, *, world: bool) -> SurfaceContact:
        candidates = []
        for face_name, face in element.faces.items():
            points = [element.vertices[name] for name in face.get("vertices", ())]
            if len(points) not in {3, 4}:
                continue
            normal = (0., 0., 0.)
            for first, second in zip(points, points[1:] + points[:1]):
                normal = (normal[0] + (first[1] - second[1]) * (first[2] + second[2]),
                          normal[1] + (first[2] - second[2]) * (first[0] + second[0]),
                          normal[2] + (first[0] - second[0]) * (first[1] + second[1]))
            try:
                normal = unit(normal)
            except ValueError:
                continue
            candidates.append((dot(normal, desired), face_name, points, normal))
        if not candidates:
            raise ValueError(f"Mesh {element.name!r} has no usable faces for contact {key!r}")
        score, _, points, normal = max(candidates, key=lambda item: (item[0], item[1]))
        if score <= 1e-7:
            raise ValueError(
                f"Mesh {element.name!r} has no physical {key!r} surface; use an explicit contact frame or bounds:{key}")
        origin = tuple(sum(point[index] for point in points) / len(points) for index in range(3))
        if not world:
            return SurfaceContact(origin, normal)
        return SurfaceContact(self._element_point_world(element, add(element.origin, origin)),
                              self._element_vector_world(element, normal))

    @staticmethod
    def _bounds_surface_contact(low: Vector3, high: Vector3, key: str) -> SurfaceContact:
        """Build a cardinal contact for mesh bounds, including flat meshes."""
        center = tuple((low[i] + high[i]) / 2 for i in range(3))
        contacts = {
            "left": ((low[0], center[1], center[2]), (-1., 0., 0.)),
            "right": ((high[0], center[1], center[2]), (1., 0., 0.)),
            "bottom": ((center[0], low[1], center[2]), (0., -1., 0.)),
            "top": ((center[0], high[1], center[2]), (0., 1., 0.)),
            "back": ((center[0], center[1], low[2]), (0., 0., -1.)),
            "front": ((center[0], center[1], high[2]), (0., 0., 1.)),
        }
        origin, normal = contacts[key]
        return SurfaceContact(origin, normal)

    def _element_vector_world(self, element: _Element, vector: Vector3) -> Vector3:
        result = self._rotate_vector(vector, element.rotation)
        if element.parent_kind == "armature":
            return result
        current = element.parent
        while current is not None:
            bone = self._groups[current]
            result = self._rotate_vector(result, bone.rotation)
            current = bone.parent
        return result

    def _element_world_points(self, element: _Element) -> tuple[Vector3, ...]:
        if element.kind == "cube":
            low, high = element.from_, element.to_ or element.from_
            return tuple(self._element_point_world(element, (x, y, z))
                         for x in (low[0], high[0]) for y in (low[1], high[1])
                         for z in (low[2], high[2]))
        if element.vertices:
            return tuple(self._element_vertex_world(element, key) for key in element.vertices)
        vertices, order = self._quad_vertices(element)
        return tuple(self._element_point_world(element, add(element.origin, vertices[key])) for key in order)

    def _resolve_surface_contact(self, value) -> SurfaceContact:
        if isinstance(value, SurfaceContact):
            return value
        if not isinstance(value, str):
            raise TypeError("surface contact must be a SurfaceContact or named contact reference")
        text = value.strip()
        if ":" in text and not text.startswith(("group:", "bone:", "armature:", "socket:")):
            element, contact = text.split(":", 1)
            return self.get_surface_contact(element, contact)
        return SurfaceContact.from_spatial_frame(self.resolve_frame(text))

    def _world_to_parent_point(self, point: Vector3, parent: str) -> Vector3:
        return self._world_to_parent_frame(
            SpatialFrame(point, (0., 1., 0.), (0., 0., 1.)), parent).origin

    def _authoring_point(self, value, parent: str) -> Vector3:
        """Literal points are parent-local; spatial references are world-space."""
        if isinstance(value, (str, SpatialFrame)):
            return self._world_to_parent_point(self.resolve_point(value), parent)
        if isinstance(value, Frame):
            return value.origin
        return _vector3(value, "local point")

    def _world_to_parent_vector(self, origin: Vector3, vector: Vector3, parent: str) -> Vector3:
        hint = (1., 0., 0.) if abs(dot(unit(vector), (1., 0., 0.))) < .9 else (0., 1., 0.)
        return self._world_to_parent_frame(SpatialFrame(origin, vector, hint), parent).forward


    def _loft_sections_in_parent(self, sections, parent: str):
        """Resolve public loft frames into the local frame of ``parent``."""
        from .procedural import Section
        result=[]
        for section in tuple(sections):
            if not isinstance(section, Section):
                raise TypeError("add_loft sections must be Section instances")
            source=section.frame
            if isinstance(source, str):
                source=self.resolve_frame(source)
            if isinstance(source, SpatialFrame):
                source=self._world_to_parent_frame(source, parent).as_frame()
            if not isinstance(source, Frame):
                raise TypeError("Section.frame must be Frame, SpatialFrame, or a spatial reference")
            result.append(Section(section.name, section.profile, source))
        return tuple(result)

    def _append_loft(self, name, parent, sections, *, start_cap="flat", end_cap="flat",
                     tags=None, visibility=True, shading_mode="flat", anchors=None, frames=None,
                     origin=(0,0,0), placement: Placement | None = None,
                     pivot: str | None = None, allow_cap_triangles: bool = False,
                     no_overlap_check: bool = False):
        from .procedural import loft
        with _about_mesh(name):
            geometry=loft(sections, start_cap=start_cap, end_cap=end_cap,
                          allow_cap_triangles=allow_cap_triangles).build()
            if anchors or frames:
                geometry=MeshGeometry.create(geometry.vertices, geometry.faces, closed=geometry.closed,
                    anchors={**geometry.anchors, **(anchors or {})}, primitive=geometry.primitive,
                    rings=geometry.rings, frames={**geometry.frames, **(frames or {})})
            return self._append_mesh(name, parent, geometry, tags=tags, origin=origin,
                                     visibility=visibility, shading_mode=shading_mode,
                                     placement=placement, pivot=pivot,
                                     no_overlap_check=no_overlap_check)

    def add_segment(self, name: str, parent: str, *, start, end, sections,
                    x_hint=None, y_hint=None, start_cap="flat", end_cap="flat", tags=None,
                    visibility=True, shading_mode="flat", placement: Placement | None = None,
                    pivot: str | None = None, allow_cap_triangles: bool = False,
                    no_overlap_check: bool = False) -> "ModelBuilder":
        """Create a straight segment from ``SegmentSection`` cross-sections.

        Profile axes: pass ``y_hint`` to say where profile +y points (e.g.
        ``(0, 0, 1)`` = model front); see ``procedural.segment_frame`` for
        the default.  The pivot is the ``start`` anchor unless ``pivot`` names
        another anchor (``end``, ``center``, or any section name).
        """
        from .procedural import check_reserved, segment_frame, segment_sections
        with _about_mesh(name):
            start_point=self._authoring_point(start,parent)
            end_point=self._authoring_point(end,parent)
            delta=sub(end_point,start_point)
            built=segment_sections((0,0,0), delta, sections, x_hint=x_hint, y_hint=y_hint)
            check_reserved({s.name: s.frame.origin for s in built}, (("start", (0,0,0)), ("end", delta)))
            direction=unit(delta)
            frame=segment_frame(direction, x_hint=x_hint, y_hint=y_hint)
            return self._append_loft(name,parent,built,start_cap=start_cap,end_cap=end_cap,
                tags=tags,visibility=visibility,shading_mode=shading_mode,
                anchors={"start":(0,0,0),"end":delta},
                frames={"start":SpatialFrame((0,0,0),direction,mul(frame.y,-1)),
                        "end":SpatialFrame(delta,direction,mul(frame.y,-1))}, origin=start_point,
                placement=placement, pivot=pivot, allow_cap_triangles=allow_cap_triangles,
                no_overlap_check=no_overlap_check)

    def add_loft(self, name: str, parent: str, *, sections,
                 start_cap="flat", end_cap="flat", tags=None,
                 visibility=True, shading_mode="flat", placement: Placement | None = None,
                 pivot: str | None = None, allow_cap_triangles: bool = False,
                 no_overlap_check: bool = False) -> "ModelBuilder":
        """Create a true loft from independently positioned, oriented Sections.

        ``Frame`` values are local to ``parent``.  ``SpatialFrame`` values and
        string references are resolved in world space and normalized to parent.
        Anchors: ``base`` (first section), ``top`` (last), ``center`` (bounds)
        and one per section name.  The pivot is ``base`` unless ``pivot``
        names another anchor or a ``placement`` moves the mesh.
        """
        if pivot is None and placement is None:
            pivot="base"
        with _about_mesh(name):
            return self._append_loft(name,parent,self._loft_sections_in_parent(sections,parent),
                start_cap=start_cap,end_cap=end_cap,tags=tags,
                visibility=visibility,shading_mode=shading_mode,placement=placement,
                pivot=pivot,allow_cap_triangles=allow_cap_triangles,
                no_overlap_check=no_overlap_check)

    def add_sweep(self, name: str, parent: str, *, path, profile=None, sections=None,
                  x_hint=None, y_hint=None, scale=((0,1),(1,1)), twist=((0,0),(1,0)),
                  start_cap="flat", end_cap="flat", tags=None,
                  visibility=True, shading_mode="flat", placement: Placement | None = None,
                  pivot: str | None = None, allow_cap_triangles: bool = False,
                  no_overlap_check: bool = False) -> "ModelBuilder":
        """Sweep along a path: one ``profile`` (with ``scale``/``twist`` tables)
        or named ``sections`` (``PathSection``) with their own profiles.

        ``Path3D.polyline([hip, knee, ankle])`` plus ``PathSection("knee",
        profile, point=1)`` builds a bent limb whose knee ring sits exactly on
        the joint (bisecting frame) and becomes the anchor ``<name>:knee``.
        """
        from .procedural import Curve, Path3D, RelativePath, path_sections, sweep_sections
        if (profile is None) == (sections is None):
            raise ValueError(f"add_sweep {name!r} needs exactly one of profile= or sections=")
        if sections is not None and (tuple(scale)!=((0,1),(1,1)) or tuple(twist)!=((0,0),(1,0))):
            raise ValueError(f"add_sweep {name!r}: scale/twist apply only to a single profile; "
                             "give each PathSection its own profile/rotation instead")
        if pivot is None and placement is None:
            pivot="base"
        with _about_mesh(name):
            resolved=isinstance(path,(RelativePath,Curve))
            if resolved: path=path.resolve(self)
            if not isinstance(path,Path3D):
                raise TypeError("add_sweep path must be Path3D, RelativePath, or Curve")
            path=Path3D(tuple(self._world_to_parent_point(point,parent) for point in path.points)) if resolved else path
            if x_hint is None and y_hint is None:
                first=unit(sub(path.points[1],path.points[0]))
                x_hint=(1,0,0) if abs(first[0])<.9 else (0,0,1)
            if sections is not None:
                built=path_sections(path,sections,x_hint=x_hint,y_hint=y_hint)
            else:
                built=sweep_sections(profile,path,x_hint=x_hint,y_hint=y_hint,scale=scale,twist=twist)
            return self._append_loft(name,parent,built,start_cap=start_cap,
                                     end_cap=end_cap,tags=tags,visibility=visibility,
                                     shading_mode=shading_mode,placement=placement,pivot=pivot,
                                     allow_cap_triangles=allow_cap_triangles,
                                     no_overlap_check=no_overlap_check)

    def add_revolve(self, name: str, parent: str, *, meridian, segments=8, angle: float = 360,
                    start_cap="flat", end_cap="flat", placement=None, tags=None,
                    visibility=True, shading_mode="flat", pivot: str | None = None,
                    allow_cap_triangles: bool = False,
                    no_overlap_check: bool = False) -> "ModelBuilder":
        """Create a full axial volume from local (radius, height) pairs."""
        from .procedural import revolve
        with _about_mesh(name):
            geometry=revolve(meridian,segments=segments,angle=angle,start_cap=start_cap,
                             end_cap=end_cap,allow_cap_triangles=allow_cap_triangles).build(
                                 primitive="revolve")
            return self._append_mesh(name,parent,geometry,placement=placement,pivot=pivot,tags=tags,
                                     visibility=visibility,shading_mode=shading_mode,
                                     no_overlap_check=no_overlap_check)

    def place(self, element: str, *, source="center", target, orient=True, offset=(0,0,0)):
        item=next((value for value in self._elements if value.name==element),None)
        if item is None or not item.vertices: raise KeyError(f"{element!r} is not a polygon mesh (native cubes have no mesh operations; build it with native=False, or check the name)")
        if not orient:
            destination=self.resolve_frame(target).offset(offset).origin
            return self.align_element(element,source,destination)
        geometry=MeshGeometry.create(item.vertices,
            {key:MeshFace(tuple(value["vertices"]),value.get("model_as_code_group"),
                          value.get("model_as_code_source_face")) for key,value in item.faces.items()},closed=item.mesh_closed,
            anchors=item.anchors,primitive=item.primitive,rings=item.mesh_rings,frames=item.frames)
        source_frame=geometry.frames.get(source)
        if source_frame is None: raise KeyError(f"Anchor {element}:{source} has no orientation")
        target_frame=self._world_to_parent_frame(self.resolve_frame(target).offset(offset),item.parent)
        def point(value): return target_frame.point(source_frame.local(value))
        def vector(value):
            local=(dot(value,source_frame.right),dot(value,source_frame.forward),dot(value,source_frame.up))
            return target_frame.vector(local)
        origin=target_frame.origin
        item.vertices={key:sub(point(value),origin) for key,value in geometry.vertices.items()}
        item.anchors={key:sub(point(value),origin) for key,value in geometry.anchors.items()}
        item.frames={key:SpatialFrame(sub(point(value.origin),origin),vector(value.forward),vector(value.up))
                     for key,value in geometry.frames.items()}
        item.origin=origin; item.from_=origin; item.rotation=(0.,0.,0.)
        return self


    def add_group(self, name: str, parent: str | None = None,
                  tags: Iterable[str] | None = None) -> "ModelBuilder":
        """Add an organizational folder with an identity transform."""
        return self._add_group(name, parent, (0, 0, 0), (0, 0, 0), tags, "folder")

    def add_transform_group(self, name: str, parent: str | None = None, *,
                            pivot, rotation: Sequence[float] = (0, 0, 0),
                            tags: Iterable[str] | None = None) -> "ModelBuilder":
        """Add a rigid animation control with an explicit pivot."""
        return self._add_group(name, parent, pivot, rotation, tags, "transform")

    def _add_group(self, name, parent, pivot, rotation, tags, role):
        self._validate_new_name(name, self._groups)
        if name in self._armatures: raise ValueError(f"Duplicate spatial owner name: {name}")
        if parent is not None and parent not in self._groups:
            raise KeyError(f"Unknown parent group: {parent}")
        point=self.resolve_point(pivot)
        if isinstance(pivot,(str,SpatialFrame,Frame)) and parent is not None:
            point=self._world_to_parent_frame(SpatialFrame(point),parent).origin
        self._groups[name] = _Group(name,parent,point,_vector3(rotation,"rotation"),_tags(tags),role)
        return self

    def add_armature(self, name: str, *, tags=None,
                     parent: str | None = None) -> ArmatureHandle:
        if self.format_id != "free":
            raise ValueError("Native armatures currently require format_id='free'")
        self._validate_new_name(name,self._armatures)
        if name in self._groups: raise ValueError(f"Duplicate spatial owner name: {name}")
        if parent is not None:
            if parent not in self._groups:
                raise KeyError(f"Unknown armature parent group {parent!r}")
            cursor = parent
            while cursor is not None:
                group = self._groups[cursor]
                if group.role != "folder":
                    raise ValueError("An armature may be organized only by folder groups, never transform groups")
                cursor = group.parent
        # Blockbench armatures have no serialized position property: the mesh
        # vertices and bone origins are already in armature bind space.
        self._armatures[name]=_Armature(name,(0.,0.,0.),_tags(tags),parent)
        return ArmatureHandle(self,name)

    def armature(self, name: str) -> ArmatureHandle:
        """Return the handle of an existing armature."""
        if name not in self._armatures:
            raise KeyError(f"Unknown armature {name!r}; available: {', '.join(sorted(self._armatures)) or '(none)'}")
        return ArmatureHandle(self, name)

    def _add_armature_bone(self,name: str,*,armature,between,parent=None,connected=True,
                 width=None,tags=None) -> "ModelBuilder":
        armature_name=armature.name if isinstance(armature,ArmatureHandle) else str(armature)
        if armature_name not in self._armatures: raise KeyError(f"Unknown armature {armature_name!r}")
        self._validate_new_name(name,self._armature_bones)
        if len(between)!=2: raise ValueError("between must contain bone start and end references")
        start,end=self.resolve_point(between[0]),self.resolve_point(between[1])
        length=math.dist(start,end)
        if length<1e-8: raise ValueError("Armature bone endpoints must differ")
        if parent is not None:
            if parent not in self._armature_bones: raise KeyError(f"Unknown parent armature bone {parent!r}")
            if self._armature_bones[parent].armature!=armature_name:
                raise ValueError("Armature bone parent belongs to another armature")
            gap=math.dist(start,self._armature_bones[parent].end)
            if connected and gap>1e-6:
                raise ValueError(
                    f"Bone {name!r} is connected=True but starts {gap:.4g} away from the end of "
                    f"parent {parent!r} (start {tuple(round(v,4) for v in start)}, parent end "
                    f"{tuple(round(v,4) for v in self._armature_bones[parent].end)}); pass "
                    "connected=False for a joint beside the parent's tip (shoulder, hip, "
                    "offset foot)")
            parent_frame=self._armature_bone_world_frame(parent)
        else:
            parent_frame=SpatialFrame(self._armatures[armature_name].origin)
        origin=parent_frame.local(start)
        local_direction=parent_frame.local(end)
        local_direction=sub(local_direction,origin)
        rotation=self._direction_euler(local_direction)
        value=max(.01,float(width)) if width is not None else max(.25,length*.2)
        if not math.isfinite(value): raise ValueError("Armature bone width must be finite")
        self._armature_bones[name]=_ArmatureBone(name,armature_name,parent,origin,rotation,
            length,value,bool(connected),_tags(tags),start,end)
        return self

    def add_transform_chain(self, name: str, parent: str | None, *, start, segments,
                  direction=(0, -1, 0), tags=None):
        """Create a compact articulated chain and endpoint sockets.

        Segment entries are mappings with ``name`` and ``length``; optional
        ``direction`` is relative to the preceding direction.
        """
        origin = self.resolve_point(start)
        current_parent = parent
        current_direction = unit(direction)
        segments=tuple(spec.as_dict() if isinstance(spec, ChainSegment) else spec
                       for spec in segments)
        if not segments: raise ValueError("Chain needs at least one segment")
        chain_key=name or str(segments[0]["name"])
        if chain_key in self._chains: raise ValueError(f"Duplicate chain name {chain_key!r}")
        created = []
        for spec in segments:
            seg_name = str(spec["name"])
            length = float(spec["length"])
            if not math.isfinite(length) or length <= 0: raise ValueError("Chain lengths must be positive")
            if spec.get("direction") is not None: current_direction = unit(spec["direction"])
            bone_name = f"{name}_{seg_name}" if name else seg_name
            self.add_transform_group(
                bone_name,
                current_parent,
                pivot=SpatialFrame(origin),
                tags=spec.get("tags", tags),
            )
            end = add(origin, mul(current_direction, length))
            default_up=(0,1,0) if abs(current_direction[2])>.9 else (0,0,1)
            chain_up=spec.get("up",default_up)
            self.add_socket(f"{bone_name}_start", bone_name,
                            at=SpatialFrame(origin,current_direction,chain_up))
            self.add_socket(f"{bone_name}_end", bone_name,
                            at=SpatialFrame(end,current_direction,chain_up))
            section_specs=spec.get("sections")
            if section_specs is None and spec.get("profile") is not None:
                from .procedural import SegmentSection
                section_specs=(SegmentSection("start",0,spec["profile"]),
                               SegmentSection("end",1,spec["profile"]))
            if section_specs is not None:
                self.add_segment(spec.get("element",f"{bone_name}_mesh"),bone_name,
                    start=f"socket:{bone_name}_start",end=f"socket:{bone_name}_end",
                    sections=section_specs,tags=spec.get("element_tags",tags),
                    start_cap=spec.get("start_cap","flat"),
                    end_cap=spec.get("end_cap","flat"))
            created.append(bone_name)
            origin, current_parent = end, bone_name
        self._chains[chain_key]=tuple(created)
        return tuple(created)

    # Clearer name: this chain is made of transform groups, not armature bones
    # (armature chains are ``rig.add_chain``).  Segments may be ChainSegment.

    def add_cube(
        self,
        name: str,
        parent: str,
        *,
        from_: Sequence[float],
        to_: Sequence[float],
        tags: Iterable[str] | None = None,
        origin: Sequence[float] | None = None,
        rotation: Sequence[float] = (0, 0, 0),
        inflate: float = 0,
        visibility: bool = True,
        shading_mode: str | None = None,
        stretch: Sequence[float] | None = None,
    ) -> "ModelBuilder":
        parent_kind,parent=self._normalize_parent(parent)
        if parent_kind != "group": raise ValueError("Cubes require a group parent; armatures deform polygon meshes")
        self._validate_element_name(name)
        start, end = _vector3(from_, "from_"), _vector3(to_, "to_")
        if any(end[i] <= start[i] for i in range(3)):
            raise ValueError("Each to_ coordinate must be greater than from_")
        if not math.isfinite(float(inflate)):
            raise ValueError("inflate must be finite")
        element_origin = _vector3(origin, "origin") if origin is not None else start
        element_stretch = _vector3(stretch, "stretch") if stretch is not None else None
        element = _Element(
            "cube", name, parent, start, end, None, None, _tags(tags), element_origin,
            _vector3(rotation, "rotation"), float(inflate), bool(visibility), shading_mode,
            element_stretch,
        )
        size = tuple(end[i] - start[i] for i in range(3))
        center = tuple((start[i] + end[i]) / 2 for i in range(3))
        anchors = {
            "center": (0., 0., 0.), "base": (0., -size[1]/2, 0.), "top": (0., size[1]/2, 0.),
            "left": (-size[0]/2, 0., 0.), "right": (size[0]/2, 0., 0.),
            "front": (0., 0., size[2]/2), "back": (0., 0., -size[2]/2),
            "-x": (-size[0]/2, 0., 0.), "+x": (size[0]/2, 0., 0.),
            "-y": (0., -size[1]/2, 0.), "+y": (0., size[1]/2, 0.),
            "-z": (0., 0., -size[2]/2), "+z": (0., 0., size[2]/2),
            "screen_left": (-size[0]/2, 0., 0.), "screen_right": (size[0]/2, 0., 0.),
            "anatomical_left": (size[0]/2, 0., 0.), "anatomical_right": (-size[0]/2, 0., 0.),
        }
        directions = {
            "center": ((0, 1, 0), (0, 0, 1)), "base": ((0, 1, 0), (0, 0, 1)),
            "top": ((0, 1, 0), (0, 0, 1)), "left": ((-1, 0, 0), (0, 1, 0)),
            "right": ((1, 0, 0), (0, 1, 0)), "front": ((0, 0, 1), (0, 1, 0)),
            "back": ((0, 0, -1), (0, 1, 0)),
            "-x": ((-1, 0, 0), (0, 1, 0)), "+x": ((1, 0, 0), (0, 1, 0)),
            "-y": ((0, 1, 0), (0, 0, 1)), "+y": ((0, 1, 0), (0, 0, 1)),
            "-z": ((0, 0, -1), (0, 1, 0)), "+z": ((0, 0, 1), (0, 1, 0)),
            "screen_left": ((-1, 0, 0), (0, 1, 0)), "screen_right": ((1, 0, 0), (0, 1, 0)),
            "anatomical_left": ((1, 0, 0), (0, 1, 0)), "anatomical_right": ((-1, 0, 0), (0, 1, 0)),
        }
        frames = {key: SpatialFrame(tuple(center[i] + point[i] for i in range(3)), *directions[key])
                  for key, point in anchors.items()}
        element.anchors = {key: tuple(frame.origin[i] - element.origin[i] for i in range(3))
                           for key, frame in frames.items()}
        element.frames = {key: SpatialFrame(element.anchors[key], frame.forward, frame.up)
                          for key, frame in frames.items()}
        self._elements.append(element)
        self._element_names.add(name)
        return self

    def add_box(self, name: str, parent: str, *, size, at=(0, 0, 0),
                anchor: str = "center", tags=None, rotation=(0, 0, 0),
                inflate=0, visibility=True, shading_mode=None,
                native: bool = True) -> "ModelBuilder":
        """Box of ``size`` whose ``anchor`` lands on ``at``.

        ``native=True`` (default) makes a Blockbench ``cube`` element
        (rotation/inflate, box UV) that can never be armature-bound.
        ``native=False`` makes the same box as a polygon mesh (bindable,
        same anchors; no rotation/inflate).  Anchors: center, base/top (Y),
        left/right (X), front/back (Z), plus -x/+x/-y/+y/-z/+z, screen_left/right,
        anatomical_left/right.
        """
        size = _vector3(size, "size")
        if any(value <= 0 for value in size): raise ValueError("Box size must be positive")
        anchors = {
            "center": (0., 0., 0.), "base": (0., -size[1]/2, 0.), "top": (0., size[1]/2, 0.),
            "left": (-size[0]/2, 0., 0.), "right": (size[0]/2, 0., 0.),
            "front": (0., 0., size[2]/2), "back": (0., 0., -size[2]/2),
            "-x": (-size[0]/2, 0., 0.), "+x": (size[0]/2, 0., 0.),
            "-y": (0., -size[1]/2, 0.), "+y": (0., size[1]/2, 0.),
            "-z": (0., 0., -size[2]/2), "+z": (0., 0., size[2]/2),
            "screen_left": (-size[0]/2, 0., 0.), "screen_right": (size[0]/2, 0., 0.),
            "anatomical_left": (size[0]/2, 0., 0.), "anatomical_right": (-size[0]/2, 0., 0.),
        }
        if anchor not in anchors:
            raise KeyError(f"Unknown box anchor {anchor!r}; available: {', '.join(anchors)}")
        target = self.resolve_point(at)
        if isinstance(at,(str,SpatialFrame,Frame)):
            target=self._world_to_parent_frame(SpatialFrame(target),parent).origin
        if not native:
            if tuple(_vector3(rotation, "rotation")) != (0., 0., 0.) or float(inflate) != 0:
                raise ValueError(f"Box {name!r}: rotation/inflate need native=True; rotate a "
                                 "parent transform group for a mesh box")
            from .primitives import box
            with _about_mesh(name):
                geometry = box(size=size)
                point = geometry.anchors.get(anchor, anchors[anchor])
                return self._append_mesh(name, parent, geometry, tags=tags,
                                         origin=tuple(target[i] - point[i] for i in range(3)),
                                         pivot=anchor, visibility=visibility,
                                         shading_mode=shading_mode or "flat")
        center = tuple(target[i] - anchors[anchor][i] for i in range(3))
        start = tuple(center[i] - size[i]/2 for i in range(3))
        end = tuple(center[i] + size[i]/2 for i in range(3))
        return self.add_cube(name, parent, from_=start, to_=end, tags=tags, origin=target, rotation=rotation,
                             inflate=inflate, visibility=visibility, shading_mode=shading_mode)

    def add_axis_quad(
        self,
        name: str,
        parent: str,
        *,
        from_: Sequence[float],
        size: Sequence[float],
        normal: str = "+Z",
        tags: Iterable[str] | None = None,
        visibility: bool = True,
    ) -> "ModelBuilder":
        parent_kind,parent=self._normalize_parent(parent)
        self._validate_element_name(name)
        if len(size) != 2 or any(float(v) <= 0 for v in size):
            raise ValueError("size must contain two positive numbers")
        normalized = normal.upper()
        if normalized not in {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}:
            raise ValueError("normal must be one of +X, -X, +Y, -Y, +Z, -Z")
        quad_size = (float(size[0]), float(size[1]))
        start = _vector3(from_, "from_")
        width, height = quad_size
        if normalized[-1] == "X":
            center_offset = (0.0, height / 2, width / 2)
        elif normalized[-1] == "Y":
            center_offset = (width / 2, 0.0, height / 2)
        else:
            center_offset = (width / 2, height / 2, 0.0)
        sign = -1.0 if normalized[0] == "-" else 1.0
        norm_dir = {"X": (sign, 0.0, 0.0), "Y": (0.0, sign, 0.0), "Z": (0.0, 0.0, sign)}[normalized[-1]]
        up_dir = (0.0, 1.0, 0.0) if normalized[-1] != "Y" else (0.0, 0.0, 1.0)
        element = _Element(
            "mesh", name, parent, start, None, quad_size, normalized, _tags(tags), start,
            (0.0, 0.0, 0.0), 0, bool(visibility), None, None, parent_kind=parent_kind,
        )
        element.primitive = "rectangular_quad"
        element.anchors = {"center": center_offset}
        element.frames = {"center": SpatialFrame(center_offset, norm_dir, up_dir)}
        self._elements.append(element)
        self._element_names.add(name)
        return self

    def add_mesh(
        self,
        name: str,
        parent: str,
        geometry: MeshDraft | MeshGeometry,
        *,
        tags: Iterable[str] | None = None,
        origin: Sequence[float] | None = None,
        placement: Placement | None = None,
        pivot: str | None = None,
        rotation: Sequence[float] = (0, 0, 0),
        visibility: bool = True,
        shading_mode: str = "flat",
        no_overlap_check: bool = False,
        allow_triangles: bool = False,
    ) -> "ModelBuilder":
        """Add a ``MeshDraft``/``MeshGeometry`` authored in parent coordinates.

        ``pivot`` names an anchor to use as the element pivot without moving
        the mesh; ``placement`` instead moves the mesh so an anchor lands on a
        target.  Closed drafts are oriented outward automatically.  Triangles are refused unless
        ``allow_triangles=True`` (quads are the default; a hand-made mesh with triangles says so).
        """
        if origin is not None and placement is not None:
            raise ValueError('Choose origin or placement, not both')
        with _about_mesh(name):
            if isinstance(geometry, MeshDraft):
                geometry = geometry.build()
            if not isinstance(geometry, MeshGeometry):
                raise TypeError("add_mesh expects MeshDraft or MeshGeometry")
            triangles = [key for key, face in geometry.faces.items() if len(face.vertices) == 3]
            if triangles and not allow_triangles and geometry.primitive is None:
                raise ValueError(f"{len(triangles)} triangle face(s) ({', '.join(triangles[:3])}): quads are the default; "
                                 "pass allow_triangles=True to add_mesh if they are intentional")
            geometry = MeshGeometry.create(geometry.vertices, geometry.faces,
                                           closed=geometry.closed, anchors=geometry.anchors,
                                           primitive=geometry.primitive, rings=geometry.rings,
                                           frames=geometry.frames)
            return self._append_mesh(name, parent, geometry, tags=tags, origin=origin or (0,0,0),
                                     placement=placement, pivot=pivot,
                                     rotation=rotation, visibility=visibility,
                                     shading_mode=shading_mode,
                                     no_overlap_check=no_overlap_check)


    @staticmethod
    def _rebased(geometry: MeshGeometry, anchor: Vector3) -> MeshGeometry:
        """Express geometry relative to ``anchor`` (which becomes local zero)."""
        return MeshGeometry.create(
            {key: tuple(value[i] - anchor[i] for i in range(3))
             for key, value in geometry.vertices.items()},
            geometry.faces,
            closed=geometry.closed,
            anchors={key: tuple(value[i] - anchor[i] for i in range(3))
                     for key, value in geometry.anchors.items()},
            primitive=geometry.primitive,
            rings=geometry.rings,
            frames={key: SpatialFrame(tuple(value.origin[i] - anchor[i] for i in range(3)),
                                      value.forward, value.up)
                    for key, value in geometry.frames.items()},
        )

    @staticmethod
    def _require_anchor(name, geometry, anchor):
        if anchor not in geometry.anchors:
            raise KeyError(f"Mesh {name!r} has no anchor {anchor!r}; available: "
                           f"{', '.join(sorted(geometry.anchors)) or '(none)'}")
        return geometry.anchors[anchor]

    def _append_mesh(self, name, parent, geometry: MeshGeometry, *, tags=None,
                     origin=(0, 0, 0), rotation=(0, 0, 0), visibility=True,
                     shading_mode="flat", placement: Placement | None = None,
                     pivot: str | None = None, no_overlap_check: bool = False):
        parent_kind,parent=self._normalize_parent(parent)
        self._validate_element_name(name)
        if self.modeling_mode == "box":
            raise ValueError(
                "modeling_mode='box' permits only native cubes and rectangular quads; "
                "free polygon meshes are not allowed")
        invalid=[face_name for face_name,face in geometry.faces.items()
                 if len(face.vertices) not in {3, 4}]
        if invalid:
            raise ValueError(f"Mesh {name!r} contains faces outside the tri/quad contract: {invalid[:3]}")
        if pivot is not None and placement is not None:
            raise ValueError(f"Mesh {name!r}: pass pivot= (keep the mesh in place) or "
                             "placement= (move it), not both")
        if pivot is not None:
            # Pivot-only: geometry stays where it is, the pivot moves to the anchor.
            anchor = self._require_anchor(name, geometry, str(pivot))
            geometry = self._rebased(geometry, anchor)
            origin = tuple(_vector3(origin, "origin")[i] + anchor[i] for i in range(3))
        if placement is not None:
            anchor = self._require_anchor(name, geometry, placement.pivot_anchor)
            target_pos = self.resolve_point(placement.position)
            if isinstance(placement.position, (str, SpatialFrame, Frame)):
                target_pos = self._world_to_parent_frame(SpatialFrame(target_pos), parent).origin
            elif getattr(placement, "space", "local") == "local" and parent in self._groups:
                parent_pivot = self._groups[parent].pivot
                target_pos = tuple(target_pos[i] + parent_pivot[i] for i in range(3))
            # Placement moves the mesh so the anchor lands on the target, and
            # that anchor becomes the serialized (editable) pivot.
            geometry = self._rebased(geometry, anchor)
            origin = target_pos
        element_origin = _vector3(origin, "origin")
        face_data = {key: {"vertices": list(face.vertices), "texture": False,
                           "model_as_code_group": face.group,
                           "model_as_code_source_face": face.source_face}
                     for key, face in geometry.faces.items()}
        self._elements.append(_Element(
            "mesh", name, parent, element_origin, None, None, None, _tags(tags),
            element_origin, _vector3(rotation, "rotation"), 0, bool(visibility),
            shading_mode, None, faces=face_data, vertices=dict(geometry.vertices),
            mesh_closed=geometry.closed, anchors=dict(geometry.anchors),
            primitive=geometry.primitive, mesh_rings=copy.deepcopy(geometry.rings),
            frames=copy.deepcopy(geometry.frames), parent_kind=parent_kind,
            no_overlap_check=bool(no_overlap_check),
        ))
        self._element_names.add(name)
        return self

    def _make_handle(self, element: _Element) -> PrimitiveHandle:
        groups = {}
        for face_name, face in element.faces.items():
            grp = face.get("model_as_code_group") if isinstance(face, dict) else getattr(face, "group", None)
            if grp:
                groups.setdefault(grp, []).append(face_name)
        world_anchors = {
            key: self.get_anchor(element.name, key) for key in element.anchors
        }
        world_frames = {
            key: self.get_frame(element.name, key) for key in element.frames
        }
        return PrimitiveHandle(
            element.name,
            element.parent,
            element.primitive or element.kind,
            world_anchors,
            {k: tuple(v) for k, v in groups.items()},
            world_frames,
        )

    @property
    def last_element(self) -> _Element:
        if not self._elements:
            raise IndexError("No elements in ModelBuilder")
        return self._elements[-1]

    @property
    def last(self) -> PrimitiveHandle:
        return self._make_handle(self.last_element)

    def add_cylinder(self, name, parent, *, radius, height, segments=8, axis="Y",
                     start_cap="flat", end_cap="flat", placement=None, tags=None,
                     allow_cap_triangles: bool = False,
                     no_overlap_check: bool = False) -> "ModelBuilder":
        from .primitives import cylinder
        return self._append_mesh(name, parent, cylinder(radius=radius, height=height,
                                 segments=segments, axis=axis,start_cap=start_cap,
                                 end_cap=end_cap,
                                 allow_cap_triangles=allow_cap_triangles), tags=tags,
                                 placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_plane(self, name, parent, *, width, height, axis="Z", placement=None,
                  tags=None, no_overlap_check: bool = False) -> "ModelBuilder":
        from .primitives import plane
        return self._append_mesh(name, parent, plane(width=width, height=height, axis=axis),
                                 tags=tags, placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_quad_face(self, name, parent, points, *, placement=None, tags=None,
                      no_overlap_check: bool = False) -> "ModelBuilder":
        from .primitives import quad_face
        return self._append_mesh(name, parent, quad_face(points=points), tags=tags,
                                 placement=placement,
                                 no_overlap_check=no_overlap_check)

    def add_triangle(self, name, parent, points, *, placement=None, tags=None,
                     no_overlap_check: bool = False) -> "ModelBuilder":
        """Add an explicitly triangular free-mesh primitive.

        Triangles are deliberately opt-in: use this only for a genuine pointed
        feature rather than as a fallback for an arbitrary polygon.
        """
        from .primitives import triangle
        return self._append_mesh(name, parent, triangle(points=points), tags=tags,
                                 placement=placement,
                                 no_overlap_check=no_overlap_check)

    def add_pyramid(self, name, parent, *, base_width, height, base_depth=None,
                    axis="Y", start_cap="flat", placement=None, tags=None,
                    no_overlap_check: bool = False) -> "ModelBuilder":
        """Add a semantic pyramid with intentional triangular apex faces."""
        from .primitives import pyramid
        return self._append_mesh(name, parent,
                                 pyramid(base_width=base_width, base_depth=base_depth,
                                         height=height, axis=axis, start_cap=start_cap),
                                 tags=tags, placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_prism(self, name, parent, *, radius, height, sides=6, axis="Y",
                  start_cap="flat", end_cap="flat", placement=None, tags=None,
                  allow_cap_triangles: bool = False,
                  no_overlap_check: bool = False) -> "ModelBuilder":
        from .primitives import prism
        return self._append_mesh(name, parent, prism(radius=radius, height=height,
                                 sides=sides, axis=axis,start_cap=start_cap,
                                 end_cap=end_cap,
                                 allow_cap_triangles=allow_cap_triangles), tags=tags,
                                 placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_cone(self, name, parent, *, radius, height, segments=8, axis="Y",
                 start_cap="flat", placement=None, tags=None,
                 allow_cap_triangles: bool = False,
                 no_overlap_check: bool = False) -> "ModelBuilder":
        from .primitives import cone
        return self._append_mesh(name, parent, cone(radius=radius, height=height,
                                 segments=segments, axis=axis, start_cap=start_cap,
                                 allow_cap_triangles=allow_cap_triangles), tags=tags,
                                 placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_frustum(self, name, parent, *, bottom_radius, top_radius, height,
                    segments=8, axis="Y", start_cap="flat", end_cap="flat",
                    placement=None, tags=None, allow_cap_triangles: bool = False,
                    no_overlap_check: bool = False) -> "ModelBuilder":
        from .primitives import frustum
        return self._append_mesh(name, parent, frustum(bottom_radius=bottom_radius,
                                 top_radius=top_radius, height=height, segments=segments,
                                 axis=axis,start_cap=start_cap,end_cap=end_cap,
                                 allow_cap_triangles=allow_cap_triangles),
                                 tags=tags, placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_uv_sphere(self, name, parent, *, radius, segments=8, rings=4, axis="Y",
                      placement=None, tags=None,
                      no_overlap_check: bool = False) -> "ModelBuilder":
        from .primitives import uv_sphere
        return self._append_mesh(name, parent, uv_sphere(radius=radius, segments=segments,
                                 rings=rings, axis=axis), tags=tags,
                                 placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_quad_sphere(self, name, parent, *, radius, subdivisions=2,
                        placement=None, tags=None,
                        no_overlap_check: bool = False) -> "ModelBuilder":
        from .primitives import quad_sphere
        return self._append_mesh(name,parent,quad_sphere(radius=radius,subdivisions=subdivisions),
                                 tags=tags,placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_capsule(self, name: str, parent: str, *, radius: float, height: float,
                    axis: str = "Y", segments: int = 8, rings: int = 1,
                    placement=None, tags=None,
                    no_overlap_check: bool = False) -> "ModelBuilder":
        """Add a native low-poly capsule primitive."""
        from .primitives import capsule
        return self._append_mesh(name, parent, capsule(radius=radius, height=height,
                                 axis=axis, segments=segments, rings=rings), tags=tags,
                                 placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def add_wedge(self, name: str, parent: str, *, width: float, depth: float,
                  height: float, axis: str = "Y",
                  placement=None, tags=None,
                  no_overlap_check: bool = False) -> "ModelBuilder":
        """Add a native low-poly wedge/ramp primitive."""
        from .primitives import wedge
        return self._append_mesh(name, parent, wedge(width=width, depth=depth,
                                 height=height, axis=axis), tags=tags,
                                 placement=placement or Placement(),
                                 no_overlap_check=no_overlap_check)

    def _element_bounds(self, element: _Element) -> tuple[Vector3, Vector3]:
        """Return (min_vector, max_vector) of element in its parent coordinate space."""
        if element.vertices:
            points = [add(element.origin, v) for v in element.vertices.values()]
            low = tuple(min(p[i] for p in points) for i in range(3))
            high = tuple(max(p[i] for p in points) for i in range(3))
            return low, high
        xmin, xmax, ymin, ymax, zmin, zmax = self._cube_bounds(element)
        return (xmin, ymin, zmin), (xmax, ymax, zmax)

    def stack_on(self, child: str, target: str, axis: str = "+Y", offset: float = 0.0) -> "ModelBuilder":
        """Position child adjacent to target along the specified axis (e.g. '+Y', '-Y', '+X', '+Z')."""
        child_elem = next((e for e in self._elements if e.name == child), None)
        if child_elem is None:
            raise KeyError(f"Unknown child element: {child!r}")
        target_elem = next((e for e in self._elements if e.name == target), None)
        if target_elem is None:
            raise KeyError(f"Unknown target element: {target!r}")

        axis_clean = axis.strip().upper()
        sign = -1 if axis_clean.startswith("-") else 1
        axis_char = axis_clean.lstrip("+-")
        if axis_char not in {"X", "Y", "Z"}:
            raise ValueError(f"Invalid axis {axis!r}; expected X, Y, or Z with optional +/-")
        axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis_char]

        child_low, child_high = self._element_bounds(child_elem)
        target_low, target_high = self._element_bounds(target_elem)

        def extent(elem, low, high, world):
            """Min and max along the axis of the eight bound corners, after the element's own rotation."""
            corners = [(x, y, z) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]
            corners = [self._element_point_world(elem, c) if world else
                       self._rotate_about(c, elem.origin, elem.rotation) for c in corners]
            values = [c[axis_idx] for c in corners]
            return min(values), max(values)

        world = child_elem.parent != target_elem.parent
        target_min, target_max = extent(target_elem, target_low, target_high, world)
        child_min, child_max = extent(child_elem, child_low, child_high, world)

        if sign > 0:
            delta = (target_max + float(offset)) - child_min
        else:
            delta = (target_min - float(offset)) - child_max

        offset_vec = [0.0, 0.0, 0.0]
        offset_vec[axis_idx] = delta
        return self.translate_element(child, offset_vec)

    def mirror(self, source: str, new_name: str | None = None, *, axis: str = "X",
               parent: str | None = None, kind: str | None = None) -> "ModelBuilder":
        """Mirror one element, a group subtree, or an armature-bone subtree.

        One entry point for bilateral symmetry.  ``new_name`` defaults to the
        side-swapped name (``arm_L``->``arm_R``, ``_left``/``_right``,
        ``.L``/``.R``).  Descendants, sockets and armature chains are renamed
        with the same rule, and a parent group with a side suffix is swapped
        too.  Faces stay outward; frames keep "up" and flip their lateral
        axis.  Mirror bones before binding and bind the mirrored meshes after.
        ``kind`` ("element", "group" or "bone") disambiguates a shared name.
        """
        target = new_name or _swap_side(source)
        if target is None:
            raise ValueError(f"Cannot infer the mirrored name of {source!r} (no side suffix "
                             f"like {', '.join(a for a, _ in _SIDE_PAIRS)}); pass new_name")
        found = [label for label, present in (("element", source in self._element_names),
                                              ("group", source in self._groups),
                                              ("bone", source in self._armature_bones)) if present]
        if kind is not None:
            if kind not in {"element", "group", "bone"}:
                raise ValueError("kind must be 'element', 'group', or 'bone'")
            if kind not in found:
                raise KeyError(f"No {kind} named {source!r}")
            found = [kind]
        if not found:
            raise KeyError(f"Unknown element, group, or armature bone {source!r}")
        if len(found) > 1:
            raise ValueError(f"{source!r} names a {' and a '.join(found)}; pass kind= to choose")
        if found[0] == "element":
            return self._mirror_element(source, target, axis=axis, parent=parent)
        if parent is not None:
            raise ValueError("parent= applies to elements; groups and bones keep their mirrored parent")
        if found[0] == "bone":
            return self._mirror_armature_subtree(self._armature_bones[source].armature,
                                                 source, target, axis)
        return self._mirror_group(source, target, axis, _semantic=True)

    def _mirror_element(self, source: str, new_name: str, axis: str = "X",
                       parent: str | None = None) -> "ModelBuilder":
        """Duplicate and mirror an element across the given axis, preserving outward normals."""
        element = next((e for e in self._elements if e.name == source), None)
        if element is None:
            raise KeyError(f"Unknown source element: {source!r}")
        if new_name in self._element_names:
            raise ValueError(f"Element {new_name!r} already exists")

        axis_clean = axis.strip().upper()
        if axis_clean not in {"X", "Y", "Z"}:
            raise ValueError(f"axis must be X, Y, or Z; got {axis!r}")
        axis_idx = {"X": 0, "Y": 1, "Z": 2}[axis_clean]

        target_parent = parent if parent is not None else element.parent
        if parent is None and target_parent:
            swapped = _swap_side(target_parent)
            if swapped is not None and (swapped in self._groups or swapped in self._armatures):
                target_parent = swapped

        def _mirror_vec(v: Vector3) -> Vector3:
            return tuple(-val if i == axis_idx else val for i, val in enumerate(v))

        mirrored = copy.deepcopy(element)
        mirrored.name = new_name
        mirrored.parent = target_parent
        mirrored.uuid = _stable_uuid("element", new_name)
        mirrored.origin = _mirror_vec(element.origin)
        mirrored.rotation = tuple(rot if i == axis_idx else -rot for i, rot in enumerate(element.rotation))

        if element.kind == "cube":
            f1 = _mirror_vec(element.from_)
            t1 = _mirror_vec(element.to_ or element.from_)
            mirrored.from_ = tuple(min(f1[i], t1[i]) for i in range(3))
            mirrored.to_ = tuple(max(f1[i], t1[i]) for i in range(3))
        else:
            mirrored.vertices = {k: _mirror_vec(p) for k, p in element.vertices.items()}
            mirrored.faces = {}
            for fname, face in element.faces.items():
                mface = copy.deepcopy(face)
                if "vertices" in mface:
                    mface["vertices"] = tuple(reversed(mface["vertices"]))
                mirrored.faces[fname] = mface
            mirrored.anchors = {k: _mirror_vec(p) for k, p in element.anchors.items()}
            # Reflect forward and up; SpatialFrame recomputes a right-handed
            # ``right``, so "up stays up" and the lateral axis flips sides.
            mirrored.frames = {
                fname: SpatialFrame(_mirror_vec(sf.origin), _mirror_vec(sf.forward), _mirror_vec(sf.up))
                for fname, sf in element.frames.items()
            }
            if element.from_ is not None:
                f1 = _mirror_vec(element.from_)
                t1 = _mirror_vec(element.to_ or element.from_)
                mirrored.from_ = tuple(min(f1[i], t1[i]) for i in range(3))
                mirrored.to_ = tuple(max(f1[i], t1[i]) for i in range(3))

        if target_parent in self._groups:
            mirrored.parent_kind = "group"
        elif target_parent in self._armatures:
            mirrored.parent_kind = "armature"

        self._elements.append(mirrored)
        self._element_names.add(new_name)
        return self

    def translate_element(self, name: str, offset: Sequence[float]) -> "ModelBuilder":
        delta = _vector3(offset, "offset")
        element = next((e for e in self._elements if e.name == name), None)
        if element is None: raise KeyError(f"Unknown element: {name}")
        element.from_ = tuple(element.from_[i] + delta[i] for i in range(3))
        element.origin = tuple(element.origin[i] + delta[i] for i in range(3))
        if element.to_ is not None:
            element.to_ = tuple(element.to_[i] + delta[i] for i in range(3))
        return self

    def get_anchor(self, name: str, anchor: str, *, world=True):
        element=next((e for e in self._elements if e.name==name),None)
        if element is None: raise KeyError(f'Unknown element {name!r}')
        anchor=anchor.removeprefix("bounds.")
        anchors=dict(self._derived_anchors(element)); anchors.update(element.anchors)
        if anchor not in anchors: raise KeyError(f'Unknown mesh anchor {name}.{anchor}')
        if not world: return tuple(anchors[anchor])
        point=tuple(element.origin[i]+anchors[anchor][i] for i in range(3))
        return self._element_point_world(element,point)

    def get_frame(self, name: str, frame: str, *, world=True) -> SpatialFrame:
        element = next((e for e in self._elements if e.name == name), None)
        if element is None: raise KeyError(f"Unknown element {name!r}")
        frame=frame.removeprefix("bounds.")
        frames=dict(element.frames)
        if frame not in frames and frame in self._derived_anchors(element):
            derived_directions = {
                "center": ((0, 1, 0), (0, 0, 1)),
                "base": ((0, 1, 0), (0, 0, 1)),
                "top": ((0, 1, 0), (0, 0, 1)),
                "left": ((-1, 0, 0), (0, 1, 0)),
                "right": ((1, 0, 0), (0, 1, 0)),
                "front": ((0, 0, 1), (0, 1, 0)),
                "back": ((0, 0, -1), (0, 1, 0)),
                "-x": ((-1, 0, 0), (0, 1, 0)),
                "+x": ((1, 0, 0), (0, 1, 0)),
                "-y": ((0, 1, 0), (0, 0, 1)),
                "+y": ((0, 1, 0), (0, 0, 1)),
                "-z": ((0, 0, -1), (0, 1, 0)),
                "+z": ((0, 0, 1), (0, 1, 0)),
                "screen_left": ((-1, 0, 0), (0, 1, 0)),
                "screen_right": ((1, 0, 0), (0, 1, 0)),
                "anatomical_left": ((1, 0, 0), (0, 1, 0)),
                "anatomical_right": ((-1, 0, 0), (0, 1, 0)),
            }
            if frame in derived_directions:
                direction, up = derived_directions[frame]
                frames[frame] = SpatialFrame(self._derived_anchors(element)[frame], direction, up)
        if frame not in frames:
            if frame in element.anchors:
                raise KeyError(f"Anchor {name}:{frame} has no orientation")
            raise KeyError(f"Unknown frame {name}:{frame}")
        value = frames[frame]
        if not world: return value
        point = add(element.origin, value.origin)
        forward = self._rotate_vector(value.forward, element.rotation)
        up = self._rotate_vector(value.up, element.rotation)
        point = self._rotate_about(point, element.origin, element.rotation)
        if element.parent_kind=="armature":
            origin=self._armatures[element.parent].origin
            point=add(point,origin)
        else:
            current = element.parent
            while current is not None:
                bone = self._groups[current]
                point = self._rotate_about(point, bone.pivot, bone.rotation)
                forward = self._rotate_vector(forward, bone.rotation)
                up = self._rotate_vector(up, bone.rotation)
                current = bone.parent
        return SpatialFrame(point, forward, up)

    def _element_point_world(self,element,point):
        point=self._rotate_about(point,element.origin,element.rotation)
        if element.parent_kind=="armature": return add(point,self._armatures[element.parent].origin)
        current=element.parent
        while current is not None:
            group=self._groups[current]
            point=self._rotate_about(point,group.pivot,group.rotation)
            current=group.parent
        return point

    def _element_vertex_world(self,element,key):
        return self._element_point_world(element,add(element.origin,element.vertices[key]))

    @staticmethod
    def _topology_signature(element):
        return (tuple(sorted(element.vertices)),
                tuple(sorted((name,tuple(face.get("vertices",()))) for name,face in element.faces.items())))

    @staticmethod
    def _distance_to_segment(point,start,end):
        delta=sub(end,start); denom=dot(delta,delta)
        t=0. if denom<=1e-16 else max(0.,min(1.,dot(sub(point,start),delta)/denom))
        return math.dist(point,add(start,mul(delta,t)))

    @staticmethod
    def _normalize_weights(values):
        items=sorted(((name,max(0.,float(weight))) for name,weight in values.items() if weight>1e-12),
                     key=lambda item:(-item[1],item[0]))[:4]
        total=sum(weight for _,weight in items)
        if total<=1e-12: return {}
        return {name:weight/total for name,weight in items}

    def _armature_binding_target(self, armature_name, mesh):
        if isinstance(mesh, ModelBuilder):
            mesh = mesh.last
        mesh_name = mesh.name if isinstance(mesh, PrimitiveHandle) else str(mesh)
        element=next((item for item in self._elements if item.name==mesh_name),None)
        if element is None or element.kind!="mesh" or not element.vertices:
            raise KeyError(f"{mesh_name!r} is not a polygon mesh (native cubes have no mesh operations; build it with native=False, or check the name)")
        if element.parent_kind!="armature" or element.parent!=armature_name:
            raise ValueError("A skinned mesh must be a direct child of its armature")
        bones=sorted((bone for bone in self._armature_bones.values()
                      if bone.armature==armature_name),key=lambda bone:bone.name)
        if not bones: raise ValueError("Cannot bind an armature without bones")
        return mesh_name, element, bones

    def _commit_armature_binding(self, mesh_name, element, bones, result, *, applied=0,
                                 ambiguities=0):
        for key, influences in result.items():
            if set(influences) - {bone.name for bone in bones}:
                raise KeyError(f"Armature binding for {mesh_name!r} references a bone outside its armature")
            if not influences or len(influences) > 4:
                raise ValueError(f"Armature binding for {mesh_name!r} has invalid influences at {key!r}")
            if any(not math.isfinite(weight) or weight < 0 for weight in influences.values()):
                raise ValueError(f"Armature binding for {mesh_name!r} has invalid weight at {key!r}")
            if not math.isclose(sum(influences.values()), 1.0, abs_tol=1e-8):
                raise ValueError(f"Armature binding for {mesh_name!r} must total 1.0 at {key!r}")
        self._bindings[mesh_name]=result
        self._binding_topology[mesh_name]=self._topology_signature(element)
        prefix=element.uuid[:6]+":"
        for bone in bones:
            bone.vertex_weights={key:value for key,value in bone.vertex_weights.items()
                                 if not key.startswith(prefix)}
        for key,influences in result.items():
            for bone_name,weight in influences.items():
                self._armature_bones[bone_name].vertex_weights[prefix+key]=weight
        counts=[len(value) for value in result.values()]
        used=tuple(sorted({name for value in result.values() for name in value}))
        return BindingReport(mesh_name,len(result),used,sum(counts)/len(counts),max(counts),applied,
                             ambiguities)

    def _bind_armature_explicit(self, armature_name, mesh, weights):
        mesh_name,element,bones=self._armature_binding_target(armature_name,mesh)
        if not isinstance(weights,Mapping):
            raise TypeError("Explicit armature weights must map every vertex to bone weights")
        unknown=set(weights)-set(element.vertices)
        missing=set(element.vertices)-set(weights)
        if unknown: raise KeyError("Unknown mesh vertices in weights: "+", ".join(sorted(unknown)))
        if missing: raise ValueError("Explicit armature weights omit vertices: "+", ".join(sorted(missing)))
        result={}
        for key, influences in weights.items():
            if not isinstance(influences, Mapping):
                raise TypeError("Each explicit vertex weight value must be a mapping of bone to weight")
            result[str(key)]={str(name):float(weight) for name,weight in influences.items()}
        report=self._commit_armature_binding(mesh_name,element,bones,result)
        self._binding_policies[mesh_name]={"mode":"explicit","bones":None}
        return report

    def _bind_armature_rigid(self, armature_name, mesh, bone_name):
        mesh_name,element,bones=self._armature_binding_target(armature_name,mesh)
        bone_name=str(bone_name)
        if bone_name not in self._armature_bones or self._armature_bones[bone_name].armature!=armature_name:
            raise KeyError(f"Unknown armature bone {bone_name!r}")
        result={key:{bone_name:1.} for key in element.vertices}
        report=self._commit_armature_binding(mesh_name,element,bones,result)
        self._binding_policies[mesh_name]={"mode":"rigid","bones":[bone_name]}
        return report

    def _resolve_armature_chain(self,armature_name,chain):
        if chain is None:
            raise ValueError("Multi-bone binding requires chain=")
        if isinstance(chain,str):
            if chain not in self._armature_chains:
                raise KeyError(f"Unknown armature chain {chain!r}")
            names=tuple(self._armature_chains[chain])
        else:
            names=tuple(str(name) for name in chain)
        if len(names)<2:
            raise ValueError("A multi-bone chain needs at least two bones")
        for index,name in enumerate(names):
            bone=self._armature_bones.get(name)
            if bone is None or bone.armature!=armature_name:
                raise KeyError(f"Unknown bone {name!r} in armature chain")
            if index and bone.parent!=names[index-1]:
                raise ValueError("Binding chain must be a linear parent-child sequence")
        return names

    def _ring_center_world(self, element, ring_name):
        """Where a named ring sits: its authored anchor (the section origin) when
        the mesh has one, otherwise the vertex centroid."""
        if ring_name in element.anchors:
            return self._element_point_world(element, add(element.origin, element.anchors[ring_name]))
        keys=element.mesh_rings[ring_name]
        points=[self._element_vertex_world(element,key) for key in keys]
        return tuple(sum(point[index] for point in points)/len(points) for index in range(3))

    def _infer_armature_joint_blends(self,armature_name,mesh,bones,*,blend="tight",
                                     curve="smooth",tolerance=1e-5,support=True):
        """Find the ring each child bone starts on.

        ``support=False`` (hard binding) needs only that joint ring; smooth
        binding also needs named rings before/after it to span the blend.
        """
        from .armature import JointBlend
        mesh_name,element,_=self._armature_binding_target(armature_name,mesh)
        if blend not in {"tight","soft"}:
            raise ValueError("blend must be 'tight' or 'soft'")
        span=1 if blend=="tight" else 2
        ring_names=tuple(element.mesh_rings)
        if not ring_names:
            raise ValueError(f"Bone {bones[1]!r} must start on exactly one named ring of mesh "
                             f"{mesh_name!r}, but the mesh has no named rings; build it with "
                             "add_segment/add_loft/add_sweep sections or MeshDraft rings")
        centers={name:self._ring_center_world(element,name) for name in ring_names}
        inferred=[]
        for child_name in bones[1:]:
            child=self._armature_bones[child_name]
            matches=[name for name,center in centers.items()
                     if math.dist(center,child.start)<=tolerance]
            if len(matches)!=1:
                nearest=min(ring_names,key=lambda name:math.dist(centers[name],child.start))
                detail=(f"several rings match: {matches}" if matches else
                        f"nearest ring {nearest!r} is {math.dist(centers[nearest],child.start):.4g} away")
                raise ValueError(
                    f"Bone {child_name!r} must start on exactly one named ring of mesh "
                    f"{mesh_name!r} (tolerance {tolerance:g}); {detail}. Start the bone on the "
                    f"ring anchor, e.g. between=(\"{mesh_name}:{nearest}\", ...)")
            index=ring_names.index(matches[0])
            if not support:
                inferred.append(JointBlend(child_name,ring=matches[0],before=matches[0],
                                           after=matches[0],curve="linear"))
                continue
            if index-span<0 or index+span>=len(ring_names):
                side="before" if index-span<0 else "after"
                raise ValueError(
                    f"Smooth binding of {mesh_name!r} needs {span} named ring(s) {side} joint ring "
                    f"{matches[0]!r} (rings in order: {', '.join(ring_names)}); add sections "
                    "there, use blend='tight', or use mode='hard'")
            inferred.append(JointBlend(child_name,ring=matches[0],
                                       before=ring_names[index-span],after=ring_names[index+span],
                                       curve=curve))
        return tuple(inferred)

    def _bind_armature_hard(self, armature_name, mesh, *, bones, joints=(), joint_owner="child"):
        if joint_owner not in {"child","parent"}:
            raise ValueError("joint_owner must be 'child' or 'parent'")
        mesh_name,element,all_bones=self._armature_binding_target(armature_name,mesh)
        self._auto_weight_armature(armature_name,mesh,bones=bones)
        automatic=self._bindings[mesh_name]
        result={key:{max(influences,key=lambda name:(influences[name],name)):1.}
                for key,influences in automatic.items()}
        for joint in joints:
            owner=joint.bone if joint_owner=="child" else self._armature_bones[joint.bone].parent
            for key in element.mesh_rings[joint.ring]: result[key]={owner:1.}
        report=self._commit_armature_binding(mesh_name,element,all_bones,result)
        self._binding_policies[mesh_name]={"mode":"hard","bones":list(bones),
                                           "joints":[joint.as_dict() for joint in joints],
                                           "joint_owner":joint_owner}
        return report

    def _auto_weight_armature(self, armature_name, mesh, *, bones=None, joints=()):
        """Generate bounded weights: hard ownership except inside declared joint bands."""
        from .armature import JointBlend
        mesh_name,element,all_bones=self._armature_binding_target(armature_name,mesh)
        candidate_bones=all_bones
        if bones is not None:
            requested=tuple(dict.fromkeys(str(name) for name in bones))
            unknown=[name for name in requested if name not in self._armature_bones or
                     self._armature_bones[name].armature!=armature_name]
            if unknown: raise KeyError("Unknown scoped armature bones: "+", ".join(unknown))
            if not requested: raise ValueError("Automatic bone scope cannot be empty")
            candidate_bones=[self._armature_bones[name] for name in requested]
        by_name={bone.name:bone for bone in candidate_bones}
        result={}
        ambiguities=0
        for key in sorted(element.vertices):
            point=self._element_vertex_world(element,key)
            distances={bone.name:self._distance_to_segment(point,bone.start,bone.end)
                       for bone in candidate_bones}
            ordered=sorted(distances,key=lambda name:(distances[name],name))
            nearest=ordered[0]
            if len(ordered)>1 and math.isclose(distances[nearest],distances[ordered[1]],
                                               rel_tol=.05,abs_tol=1e-6):
                ambiguities+=1
            result[key]={nearest:1.}

        def ring_center(ring_name):
            if ring_name not in element.mesh_rings:
                raise KeyError(f"Mesh {mesh_name!r} has no ring {ring_name!r}; "
                               f"available: {', '.join(element.mesh_rings)}")
            if not element.mesh_rings[ring_name]:
                raise ValueError(f"Mesh ring {ring_name!r} cannot be empty")
            return self._ring_center_world(element,ring_name)

        serialized_joints=[]
        for blend in tuple(joints):
            if not isinstance(blend,JointBlend):
                raise TypeError("joints must contain JointBlend values")
            child=by_name.get(blend.bone)
            if child is None:
                raise KeyError(f"Joint blend references bone {blend.bone!r} outside the binding scope")
            parent_name=blend.parent or child.parent
            if parent_name not in by_name:
                raise KeyError(f"Joint blend for {blend.bone!r} requires parent bone {parent_name!r} in scope")
            before=ring_center(blend.before); center=ring_center(blend.ring); after=ring_center(blend.after)
            axis=sub(after,before); denominator=dot(axis,axis)
            if denominator<=1e-12:
                raise ValueError(f"Joint blend rings for {blend.bone!r} do not span a usable band: the before and after rings coincide; "
                                 "name rings on either side of the joint ring, or use blend=\"tight\"")
            joint_t=dot(sub(center,before),axis)/denominator
            if not 1e-6 < joint_t < 1-1e-6:
                raise ValueError(f"Joint ring {blend.ring!r} must lie between before and after rings")

            def curve(value):
                value=max(0.,min(1.,value))
                return value if blend.curve=="linear" else value*value*(3-2*value)

            for key in sorted(element.vertices):
                point=self._element_vertex_world(element,key)
                position=dot(sub(point,before),axis)/denominator
                if position < -1e-8 or position > 1+1e-8: continue
                if position<=joint_t:
                    child_weight=.5*curve(position/joint_t)
                else:
                    child_weight=.5+.5*curve((position-joint_t)/(1-joint_t))
                if child_weight<=1e-10: result[key]={parent_name:1.}
                elif child_weight>=1-1e-10: result[key]={child.name:1.}
                else: result[key]={parent_name:1-child_weight,child.name:child_weight}
            serialized_joints.append(blend.as_dict())

        report=self._commit_armature_binding(mesh_name,element,all_bones,result,
                                             ambiguities=ambiguities)
        self._binding_policies[mesh_name]={"mode":"smooth","bones":list(requested) if bones is not None else None,
                                           "joints":serialized_joints}
        return report

    def _derived_anchors(self,element):
        if element.kind=="cube":
            low=element.from_; high=element.to_ or low
            # Cube coordinates are already in parent bind space; express them relative to origin.
            low=tuple(low[i]-element.origin[i] for i in range(3)); high=tuple(high[i]-element.origin[i] for i in range(3))
        elif element.vertices:
            low=tuple(min(p[i] for p in element.vertices.values()) for i in range(3))
            high=tuple(max(p[i] for p in element.vertices.values()) for i in range(3))
        else:
            return {}
        center = tuple((low[i] + high[i]) / 2 for i in range(3))
        base = (center[0], low[1], center[2])
        top = (center[0], high[1], center[2])
        left = (low[0], center[1], center[2])
        right = (high[0], center[1], center[2])
        front = (center[0], center[1], high[2])
        back = (center[0], center[1], low[2])
        return {
            "center": center, "base": base, "top": top,
            "left": left, "right": right, "front": front, "back": back,
            "-x": left, "+x": right, "-y": base, "+y": top, "-z": back, "+z": front,
            "screen_left": left, "screen_right": right,
            "anatomical_left": right, "anatomical_right": left,
        }

    @contextmanager
    def edit_mesh(self, name: str):
        """Edit a private copy and commit validated geometry on normal context exit."""
        from .geometry_types import MeshDraft, MeshFace
        element=next((e for e in self._elements if e.name==name),None)
        if element is None or not element.vertices: raise KeyError(f"{name!r} is not a polygon mesh (native cubes have no mesh operations; build it with native=False, or check the name)")
        snapshot=copy.deepcopy(element)
        errors_before=set(self.validate(require_armature_bindings=False)["errors"])
        geometry=MeshGeometry.create(element.vertices,
            {k:MeshFace(tuple(f['vertices']),f.get('model_as_code_group'),f.get('model_as_code_source_face')) for k,f in element.faces.items()},
            closed=element.mesh_closed,anchors=element.anchors,primitive=element.primitive,
            rings=element.mesh_rings,frames=element.frames)
        draft=MeshDraft.from_geometry(geometry)
        yield draft
        draft.validate()
        result=draft.build(primitive=element.primitive)
        invalid=[key for key,face in result.faces.items() if len(face.vertices) not in {3,4}]
        if invalid:
            raise ValueError(f"Mesh edit would create faces outside the tri/quad contract: {', '.join(invalid[:3])}")
        if element!=snapshot: raise ValueError('Element changed while mesh edit was open')
        candidate=copy.deepcopy(element)
        candidate.vertices=dict(result.vertices); candidate.anchors=dict(result.anchors)
        candidate.frames=copy.deepcopy(result.frames)
        candidate.mesh_closed=result.closed
        candidate.mesh_rings=copy.deepcopy(result.rings)
        candidate.faces={k:{'vertices':list(f.vertices),'texture':False,
                           'model_as_code_group':f.group,'model_as_code_source_face':f.source_face} for k,f in result.faces.items()}
        candidate.uv_offset=[0,0]
        index=self._elements.index(element)
        self._elements[index]=candidate
        try:
            report=self.validate(require_armature_bindings=False)
            new_errors=[error for error in report['errors'] if error not in errors_before]   # only what this edit caused
            if new_errors: raise ValueError('; '.join(new_errors))
        except Exception:
            self._elements[index]=element
            raise

    def rotate_element(self, name: str, rotation: Sequence[float]) -> "ModelBuilder":
        element = next((e for e in self._elements if e.name == name), None)
        if element is None: raise KeyError(f"Unknown element: {name}")
        element.rotation = _vector3(rotation, "rotation")
        return self

    def scale_mesh(self, name: str, scale: float | Sequence[float]) -> "ModelBuilder":
        element = next((e for e in self._elements if e.name == name), None)
        if element is None or not element.vertices:
            raise KeyError(f"{name!r} is not a polygon mesh (native cubes have no mesh operations; build it with native=False, or check the name)")
        factors = (float(scale),)*3 if isinstance(scale, (int,float)) else _vector3(scale,"scale")
        if any(not math.isfinite(v) or v == 0 for v in factors):
            raise ValueError("scale components must be finite and non-zero")
        element.vertices = {k: tuple(p[i]*factors[i] for i in range(3))
                            for k,p in element.vertices.items()}
        element.anchors = {k: tuple(p[i]*factors[i] for i in range(3))
                           for k,p in element.anchors.items()}
        element.frames = {k: SpatialFrame(tuple(p.origin[i]*factors[i] for i in range(3)),
                                          tuple(p.forward[i]*factors[i] for i in range(3)),
                                          tuple(p.up[i]*factors[i] for i in range(3)))
                          for k,p in element.frames.items()}
        if factors[0]*factors[1]*factors[2] < 0:
            for face in element.faces.values(): face["vertices"].reverse()
        return self

    def align_element(self, name: str, anchor: str, target) -> "ModelBuilder":
        element = next((e for e in self._elements if e.name == name), None)
        if element is None or anchor not in element.anchors:
            raise KeyError(f"Unknown element/anchor: {name}.{anchor}")
        destination = self.resolve_point(target)

        # Convert the world target back through the complete ancestor chain.
        chain = []
        parent = element.parent
        while parent is not None:
            bone = self._groups[parent]
            chain.append(bone)
            parent = bone.parent
        local_target = destination
        for bone in reversed(chain):
            local_target = self._inverse_rotate(local_target, bone.pivot, bone.rotation)

        rotated_anchor = self._rotate_vector(element.anchors[anchor], element.rotation)
        new_origin = tuple(local_target[i] - rotated_anchor[i] for i in range(3))
        delta = tuple(new_origin[i] - element.origin[i] for i in range(3))
        return self.translate_element(name, delta)

    def combine_meshes(
        self,
        names: Sequence[str],
        into: str,
        parent: str | None = None,
        tags: Iterable[str] | None = None,
        shading_mode: str | None = None,
    ) -> "ModelBuilder":
        """Aggregate meshes under one element while preserving disconnected shells."""
        names = list(names)
        if len(names) < 2:
            raise ValueError("combine_meshes requires at least two elements to combine")
        if len(set(names)) != len(names):
            raise ValueError("combine_meshes element names must be unique")
        self._validate_element_name(into)

        elements_to_merge: list[_Element] = []
        for name in names:
            elem = next((e for e in self._elements if e.name == name), None)
            if elem is None:
                raise KeyError(f"Unknown element to merge: {name!r}")
            if elem.kind != "mesh" or not elem.vertices:
                raise ValueError(f"Element {name!r} must be a canonical polygon mesh")
            elements_to_merge.append(elem)
        bound = sorted(name for name in names if name in self._bindings)
        if bound:
            raise ValueError(
                "Cannot merge bound meshes; merge first and call bind() again: "
                + ", ".join(bound)
            )
        dependent=[socket.name for socket in self._sockets.values()
                   if socket.source and any(socket.source.startswith(f"{name}:") for name in names)]
        if dependent:
            raise ValueError("Cannot merge meshes referenced by live sockets: "+", ".join(sorted(dependent)))

        target_parent = parent or elements_to_merge[0].parent
        parent_kind, target_parent = self._normalize_parent(target_parent)
        if parent_kind != "group":
            raise ValueError("Merge bound-space meshes before parenting them to an armature")
        if any(e.parent_kind != "group" or e.parent != target_parent for e in elements_to_merge):
            raise ValueError(
                "All merged elements must already share the target parent bone; "
                "cross-bone merging would change their transform space"
            )

        merged_vertices = {}
        merged_faces = {}
        merged_anchors = {}
        merged_rings = {}
        merged_frames = {}
        all_closed = all(e.mesh_closed for e in elements_to_merge)
        combined_tags = list(_tags(tags))
        merged_origin = self._groups[target_parent].pivot

        for elem in elements_to_merge:
            prefix = elem.name
            for tag in elem.tags:
                if tag not in combined_tags:
                    combined_tags.append(tag)

            for v_name, v_pos in elem.vertices.items():
                rotated = self._rotate_vector(v_pos, elem.rotation)
                world_local = tuple(elem.origin[i] + rotated[i] for i in range(3))
                key = f"{prefix}__{v_name}"
                merged_vertices[key] = tuple(world_local[i] - merged_origin[i] for i in range(3))

            for f_name, f_data in elem.faces.items():
                key = f"{prefix}__{f_name}"
                face_dict = copy.deepcopy(f_data)
                face_dict["vertices"] = [f"{prefix}__{v}" for v in f_data.get("vertices", [])]
                if not face_dict.get("model_as_code_group"):
                    face_dict["model_as_code_group"] = prefix
                merged_faces[key] = face_dict

            for a_name, a_pos in elem.anchors.items():
                rotated = self._rotate_vector(a_pos, elem.rotation)
                world_local = tuple(elem.origin[i] + rotated[i] for i in range(3))
                key = f"{prefix}__{a_name}"
                merged_anchors[key] = tuple(world_local[i] - merged_origin[i] for i in range(3))

            for r_name, r_verts in elem.mesh_rings.items():
                key = f"{prefix}__{r_name}"
                merged_rings[key] = tuple(f"{prefix}__{v}" for v in r_verts)
            for frame_name, frame in elem.frames.items():
                point=self._rotate_vector(frame.origin,elem.rotation)
                merged_frames[f"{prefix}__{frame_name}"]=SpatialFrame(
                    tuple(elem.origin[i]+point[i]-merged_origin[i] for i in range(3)),
                    self._rotate_vector(frame.forward,elem.rotation),
                    self._rotate_vector(frame.up,elem.rotation))

        for elem in elements_to_merge:
            self._elements.remove(elem)
            self._element_names.remove(elem.name)

        shading = shading_mode or elements_to_merge[0].shading_mode or "flat"
        merged_element = _Element(
            "mesh", into, target_parent, merged_origin, None, None, None,
            combined_tags, merged_origin, (0.0, 0.0, 0.0), 0, True,
            shading, None, faces=merged_faces, vertices=merged_vertices,
            mesh_closed=all_closed, anchors=merged_anchors, primitive="merged_mesh",
            mesh_rings=merged_rings,
            frames=merged_frames,
        )
        self._elements.append(merged_element)
        self._element_names.add(into)

        groups = {}
        for face_name, face_data in merged_faces.items():
            grp = face_data.get("model_as_code_group")
            if grp:
                groups.setdefault(grp, []).append(face_name)
        return self


    @staticmethod
    def _rotate_vector(vector: Vector3, angles: Vector3) -> Vector3:
        x, y, z = vector
        rx, ry, rz = map(math.radians, angles)
        y, z = math.cos(rx)*y-math.sin(rx)*z, math.sin(rx)*y+math.cos(rx)*z
        x, z = math.cos(ry)*x+math.sin(ry)*z, -math.sin(ry)*x+math.cos(ry)*z
        x, y = math.cos(rz)*x-math.sin(rz)*y, math.sin(rz)*x+math.cos(rz)*y
        return (x, y, z)

    @classmethod
    def _rotate_about(cls, point: Vector3, pivot: Vector3, angles: Vector3) -> Vector3:
        return add(pivot,cls._rotate_vector(sub(point,pivot),angles))

    @classmethod
    def _inverse_rotate_vector(cls, vector: Vector3, angles: Vector3) -> Vector3:
        return sub(cls._inverse_rotate(vector,(0,0,0),angles),(0,0,0))

    def _group_chain(self,name):
        chain=[]
        while name is not None:
            chain.append(name); name=self._groups[name].parent
        return chain

    def _world_to_parent_frame(self,frame: SpatialFrame,parent: str) -> SpatialFrame:
        if isinstance(parent,ArmatureHandle): parent=parent.name
        if isinstance(parent,str) and parent.startswith("armature:"): parent=parent[9:]
        if parent in self._armatures:
            origin=self._armatures[parent].origin
            return SpatialFrame(sub(frame.origin,origin),frame.forward,frame.up)
        point,forward,up=frame.origin,frame.forward,frame.up
        for bone_name in reversed(self._group_chain(parent)):
            bone=self._groups[bone_name]
            point=self._inverse_rotate(point,bone.pivot,bone.rotation)
            forward=self._inverse_rotate_vector(forward,bone.rotation)
            up=self._inverse_rotate_vector(up,bone.rotation)
        return SpatialFrame(point,forward,up)

    @classmethod
    def _inverse_rotate(cls, point: Vector3, pivot: Vector3, angles: Vector3) -> Vector3:
        x, y, z = (point[i] - pivot[i] for i in range(3))
        rx, ry, rz = map(math.radians, angles)
        x, y = math.cos(rz)*x+math.sin(rz)*y, -math.sin(rz)*x+math.cos(rz)*y
        x, z = math.cos(ry)*x-math.sin(ry)*z, math.sin(ry)*x+math.cos(ry)*z
        y, z = math.cos(rx)*y+math.sin(rx)*z, -math.sin(rx)*y+math.cos(rx)*z
        return (x+pivot[0], y+pivot[1], z+pivot[2])

    def _mirror_group(self, group_name: str, new_name: str, axis: str = "x", *, _semantic=False) -> "ModelBuilder":
        """Mirror a rigid group subtree; native armature bones use ``rig.mirror``."""
        bone_name = group_name
        if bone_name not in self._groups:
            raise KeyError(f"Unknown group: {bone_name}")
        self._validate_new_name(new_name, self._groups)
        axis = axis.lower()
        if axis not in {"x", "y", "z"}:
            raise ValueError("axis must be x, y, or z")
        axis_index = {"x": 0, "y": 1, "z": 2}[axis]
        subtree = self._subtree_names(bone_name)
        name_map = {bone_name: new_name}
        semantic=_semantic and _swap_side(bone_name)==new_name

        def side_rename(value):
            """Side-swapped descendant name, or None to fall back to a prefix."""
            if not semantic: return None
            swapped=_swap_side(value)
            if swapped is not None: return swapped
            for left,right in _SIDE_PAIRS[:1]:
                if left in value: return value.replace(left,right)
                if right in value: return value.replace(right,left)
            return None

        for source in subtree[1:]:
            candidate = side_rename(source) or f"{new_name}_{source}"
            suffix = 2
            while candidate in self._groups or candidate in name_map.values():
                candidate = f"{new_name}_{source}_{suffix}"
                suffix += 1
            name_map[source] = candidate

        for source_name in subtree:
            source = self._groups[source_name]
            parent = source.parent if source_name == bone_name else name_map[source.parent]  # type: ignore[index]
            pivot = list(source.pivot)
            pivot[axis_index] *= -1
            rotation = self._mirror_rotation(source.rotation, axis_index)
            self._add_group(name_map[source_name], parent, pivot, rotation,
                            source.tags, source.role)

        originals = [element for element in self._elements if element.parent in subtree]
        for source in originals:
            base_name=side_rename(source.name) or f"{new_name}_{source.name}"
            mirrored_name = self._unique_element_name(base_name)
            start = list(source.from_)
            if source.kind == "cube":
                end = list(source.to_ or ())
                start[axis_index], end[axis_index] = -end[axis_index], -start[axis_index]
                origin = list(source.origin)
                origin[axis_index] *= -1
                stretch = list(source.stretch) if source.stretch else None
                self.add_cube(
                    mirrored_name, name_map[source.parent], from_=start, to_=end, tags=source.tags,
                    origin=origin, rotation=self._mirror_rotation(source.rotation, axis_index),
                    inflate=source.inflate, visibility=source.visibility,
                    shading_mode=source.shading_mode, stretch=stretch,
                )

            else:
                if source.vertices:
                    vertices = {k: tuple((-v if i == axis_index else v) for i, v in enumerate(p))
                                for k, p in source.vertices.items()}
                    faces = copy.deepcopy(source.faces)
                    for face in faces.values(): face["vertices"] = list(reversed(face.get("vertices", [])))
                    mirrored_origin=tuple(-v if i == axis_index else v for i,v in enumerate(source.origin))
                    anchors={k:tuple(-v if i == axis_index else v for i,v in enumerate(p))
                             for k,p in source.anchors.items()}
                    self._elements.append(_Element("mesh",mirrored_name,name_map[source.parent],
                        mirrored_origin,None,None,None,list(source.tags),mirrored_origin,
                        self._mirror_rotation(source.rotation,axis_index),0,source.visibility,
                        source.shading_mode,None,faces=faces,vertices=vertices,
                        mesh_closed=source.mesh_closed,anchors=anchors,primitive=source.primitive,
                        mesh_rings={k:tuple(reversed(v)) for k,v in source.mesh_rings.items()},
                        frames={k:v.mirrored(axis) for k,v in source.frames.items()}))
                    self._element_names.add(mirrored_name)
                else:
                    start[axis_index] *= -1
                    normal = source.normal or "+Z"
                    if normal[-1].lower() == axis:
                        normal = ("-" if normal[0] == "+" else "+") + normal[1]
                    self.add_axis_quad(mirrored_name, name_map[source.parent], from_=start,
                                  size=source.size or (1, 1), normal=normal, tags=source.tags,
                                  visibility=source.visibility)
        original_sockets=[socket for socket in self._sockets.values() if socket.parent in subtree]
        for socket in original_sockets:
            mirrored_socket=socket.frame.mirrored(axis)
            socket_base=side_rename(socket.name) or f"{new_name}_{socket.name}"
            new_socket_name=self._unique_socket_name(socket_base)
            source=socket.source
            if source and semantic: source=side_rename(source) or source
            self._sockets[new_socket_name]=_Socket(new_socket_name,name_map[socket.parent],
                mirrored_socket.origin,mirrored_socket.forward,mirrored_socket.up,source,
                socket.offset,socket.inherit_forward,socket.inherit_up)
        return self

    def _mirror_armature_subtree(self, armature_name, source_name, target_name, axis="X"):
        if armature_name not in self._armatures:
            raise KeyError(f"Unknown armature {armature_name!r}")
        if source_name not in self._armature_bones:
            raise KeyError(f"Unknown armature bone {source_name!r}")
        if self._armature_bones[source_name].armature != armature_name:
            raise ValueError("Source bone belongs to another armature")
        if self._bindings:
            raise ValueError("Mirror armature bones before bind()")
        axis = axis.lower()
        if axis not in {"x", "y", "z"}:
            raise ValueError("axis must be x, y, or z")
        index = {"x": 0, "y": 1, "z": 2}[axis]

        def subtree(name):
            result = [name]
            for child in sorted(
                bone.name for bone in self._armature_bones.values() if bone.parent == name
            ):
                result.extend(subtree(child))
            return result

        names = subtree(source_name)
        mapping = {source_name: target_name}
        semantic = _swap_side(source_name) == target_name
        if target_name in self._armature_bones:
            raise ValueError(f"Mirrored bone name already exists: {target_name}")
        for name in names[1:]:
            candidate = (_swap_side(name) if semantic else None) or f"{target_name}_{name}"
            if candidate in self._armature_bones or candidate in mapping.values():
                raise ValueError(f"Mirrored bone name already exists: {candidate}")
            mapping[name] = candidate

        armature_origin = self._armatures[armature_name].origin
        def reflected(point):
            value = list(point)
            value[index] = 2 * armature_origin[index] - value[index]
            return tuple(value)

        for name in names:
            source = self._armature_bones[name]
            parent = source.parent if name == source_name else mapping[source.parent]
            self._add_armature_bone(
                mapping[name],
                armature=armature_name,
                between=(reflected(source.start), reflected(source.end)),
                parent=parent,
                connected=source.connected,
                width=source.width,
                tags=source.tags,
            )
        # Mirror every armature chain that lies inside the subtree, so the new
        # side can be bound with rig.bind(..., chain="<mirrored chain name>").
        for key, chain in list(self._armature_chains.items()):
            if not all(bone in mapping for bone in chain):
                continue
            mirrored_key = (_swap_side(key) if semantic else None) or f"{target_name}_{key}"
            if mirrored_key not in self._armature_chains:
                self._armature_chains[mirrored_key] = tuple(mapping[bone] for bone in chain)
        # Sockets owned by a mirrored bone follow it (a hand socket on upper_L gives one on upper_R).
        for socket in [s for s in self._sockets.values() if s.parent_kind == "bone" and s.parent in mapping]:
            world = self.get_socket(socket.name).mirrored(axis)
            owner = self._armature_bone_world_frame(mapping[socket.parent])
            forward, up = unit(world.forward), unit(world.up)
            z = unit(cross(unit(cross(forward, up)), forward))
            local = lambda v: (dot(v, owner.right), dot(v, owner.forward), dot(v, owner.up))
            new_name = self._unique_socket_name((_swap_side(socket.name) if semantic else None)
                                                 or f"{target_name}_{socket.name}")
            self._sockets[new_name] = _Socket(new_name, mapping[socket.parent], owner.local(world.origin),
                                              local(forward), local(z), None, (0., 0., 0.), False, False, "bone")
        return self

    def _unique_socket_name(self,base):
        candidate,suffix=base,2
        while candidate in self._sockets:
            candidate,suffix=f"{base}_{suffix}",suffix+1
        return candidate

    def validate_groups(self, required_groups: Iterable[str] | None = None) -> dict[str, object]:
        """Check the authored rigid group hierarchy before geometry is added."""
        errors: list[str] = []
        warnings: list[str] = []
        names = set(self._groups)
        for name in required_groups or ():
            if name not in names:
                errors.append(f"Missing required group: {name}")
        for name, bone in self._groups.items():
            if bone.parent is not None and bone.parent not in names:
                errors.append(f"Group {name!r} references missing parent {bone.parent!r}")
        roots = sorted(name for name, bone in self._groups.items() if bone.parent is None)
        for start in names:
            seen: set[str] = set()
            current: str | None = start
            while current is not None:
                if current in seen:
                    errors.append(f"Group hierarchy cycle includes {current!r}")
                    break
                seen.add(current)
                current = self._groups[current].parent
        if len(roots) > 1:
            warnings.append(f"Group hierarchy has {len(roots)} roots")
        return {"errors": sorted(set(errors)), "warnings": sorted(set(warnings)), "groups": sorted(names), "roots": roots}

    def import_builder(
        self,
        source: "ModelBuilder",
        *,
        mount_parent: str | None = None,
        offset: Sequence[float] = (0, 0, 0),
        prefix: str = "",
        texture_slot_remap: dict[int, int] | None = None,
    ) -> "ModelBuilder":
        """Imports another ModelBuilder hierarchy into this model with translation, prefixing and texture slot remapping."""
        off = _vector3(offset, "offset")
        if mount_parent is not None and mount_parent not in self._groups:
            raise KeyError(f"Unknown mount parent group: {mount_parent}")

        # Map bones
        for bone in source._groups.values():
            new_bone_name = f"{prefix}{bone.name}"
            new_parent = f"{prefix}{bone.parent}" if bone.parent is not None else mount_parent
            new_pivot = ((0., 0., 0.) if bone.role == "folder" else
                         (bone.pivot[0] + off[0], bone.pivot[1] + off[1], bone.pivot[2] + off[2]))
            new_bone = _Group(
                name=new_bone_name,
                parent=new_parent,
                pivot=new_pivot,
                rotation=bone.rotation,
                tags=list(bone.tags),
                role=bone.role,
                uuid=_stable_uuid("group", new_bone_name),
            )
            self._groups[new_bone_name] = new_bone

        for armature in source._armatures.values():
            name = f"{prefix}{armature.name}"
            self._armatures[name] = _Armature(
                name, armature.origin, list(armature.tags),
                parent=f"{prefix}{armature.parent}" if armature.parent else mount_parent,
                uuid=_stable_uuid("armature", name),
            )
        for bone in source._armature_bones.values():
            name = f"{prefix}{bone.name}"
            self._armature_bones[name] = _ArmatureBone(
                name=name,
                armature=f"{prefix}{bone.armature}",
                parent=f"{prefix}{bone.parent}" if bone.parent else None,
                origin=add(bone.origin, off),
                rotation=bone.rotation,
                length=bone.length,
                width=bone.width,
                connected=bone.connected,
                tags=list(bone.tags),
                start=add(bone.start, off),
                end=add(bone.end, off),
                uuid=_stable_uuid("bone", name),
            )

        # Map elements
        for elem in source._elements:
            new_elem_name = f"{prefix}{elem.name}"
            new_elem_parent = f"{prefix}{elem.parent}"
            new_origin = (elem.origin[0] + off[0], elem.origin[1] + off[1], elem.origin[2] + off[2])
            new_uuid = _stable_uuid("element", new_elem_name)

            new_faces = copy.deepcopy(elem.faces)
            if texture_slot_remap:
                for face_data in new_faces.values():
                    if isinstance(face_data, dict):
                        tex = face_data.get("texture")
                        if isinstance(tex, int) and tex in texture_slot_remap:
                            face_data["texture"] = texture_slot_remap[tex]

            if elem.kind == "cube":
                new_from = (elem.from_[0] + off[0], elem.from_[1] + off[1], elem.from_[2] + off[2])
                new_to = (elem.to_[0] + off[0], elem.to_[1] + off[1], elem.to_[2] + off[2]) if elem.to_ else None
                new_elem = _Element(
                    kind="cube",
                    name=new_elem_name,
                    parent=new_elem_parent,
                    from_=new_from,
                    to_=new_to,
                    size=None,
                    normal=None,
                    tags=list(elem.tags),
                    origin=new_origin,
                    rotation=elem.rotation,
                    inflate=elem.inflate,
                    visibility=elem.visibility,
                    shading_mode=elem.shading_mode,
                    stretch=elem.stretch,
                    uuid=new_uuid,
                    uv_offset=list(elem.uv_offset),
                    faces=new_faces,
                )
            else:
                new_from = (elem.from_[0] + off[0], elem.from_[1] + off[1], elem.from_[2] + off[2])
                new_elem = _Element(
                    kind="mesh",
                    name=new_elem_name,
                    parent=new_elem_parent,
                    from_=new_from,
                    to_=None,
                    size=elem.size,
                    normal=elem.normal,
                    tags=list(elem.tags),
                    origin=new_origin,
                    rotation=elem.rotation,
                    inflate=elem.inflate,
                    visibility=elem.visibility,
                    shading_mode=None,
                    stretch=None,
                    uuid=new_uuid,
                    uv_offset=[0, 0],
                    faces=new_faces,
                    vertices=copy.deepcopy(elem.vertices),
                    mesh_closed=elem.mesh_closed,
                    anchors=copy.deepcopy(elem.anchors),
                    primitive=elem.primitive,
                    mesh_rings=copy.deepcopy(elem.mesh_rings),
                    frames=copy.deepcopy(elem.frames),
                    parent_kind=elem.parent_kind,
                )
            self._elements.append(new_elem)
            self._element_names.add(new_elem_name)

        for old_mesh, weights in source._bindings.items():
            new_mesh = f"{prefix}{old_mesh}"
            mapped = {
                key: {f"{prefix}{bone}": weight for bone, weight in influences.items()}
                for key, influences in weights.items()
            }
            self._bindings[new_mesh] = mapped
            element = next(item for item in self._elements if item.name == new_mesh)
            self._binding_topology[new_mesh] = self._topology_signature(element)
            native_prefix = element.uuid[:6] + ":"
            for key, influences in mapped.items():
                for bone, weight in influences.items():
                    self._armature_bones[bone].vertex_weights[native_prefix + key] = weight

        for socket in source._sockets.values():
            new_name=f"{prefix}{socket.name}"
            if new_name in self._sockets: raise ValueError(f"Duplicate imported socket: {new_name}")
            source_ref=socket.source
            if source_ref:
                if source_ref.startswith("group:"): source_ref=f"group:{prefix}{source_ref[6:]}"
                elif source_ref.startswith("bone:"): source_ref=f"bone:{prefix}{source_ref[5:]}"
                elif source_ref.startswith("socket:"): source_ref=f"socket:{prefix}{source_ref[7:]}"
                elif ":" in source_ref: source_ref=f"{prefix}{source_ref}"
            self._sockets[new_name]=_Socket(new_name,f"{prefix}{socket.parent}",
                socket.position if socket.parent_kind == "bone" else add(socket.position,off),
                socket.forward,socket.up,source_ref,socket.offset,
                socket.inherit_forward,socket.inherit_up,socket.parent_kind)
        for name,chain in source._chains.items():
            imported_name=f"{prefix}{name}"
            self._chains[imported_name]=tuple(f"{prefix}{bone}" for bone in chain)
        for name,chain in source._armature_chains.items():
            self._armature_chains[f"{prefix}{name}"] = tuple(f"{prefix}{bone}" for bone in chain)

        return self


    @staticmethod
    def _cube_bounds(element: _Element) -> tuple[float, float, float, float, float, float]:
        """Return (xmin, xmax, ymin, ymax, zmin, zmax) taking inflate into account."""
        x1, y1, z1 = element.from_
        x2, y2, z2 = element.to_ or element.from_
        inf = element.inflate
        xmin = min(x1, x2) - inf
        xmax = max(x1, x2) + inf
        ymin = min(y1, y2) - inf
        ymax = max(y1, y2) + inf
        zmin = min(z1, z2) - inf
        zmax = max(z1, z2) + inf
        return (xmin, xmax, ymin, ymax, zmin, zmax)

    def _check_geometry_conflicts(self) -> tuple[list[str], list[str]]:
        from .geometry_validation import check_geometry_conflicts
        return check_geometry_conflicts(self)

    @staticmethod
    def _quad_face_info(element: _Element) -> tuple[str, float, float, float, float, float]:
        """Return (normal, plane_coord, u_min, u_max, v_min, v_max) for a planar quad element."""
        x, y, z = element.from_
        w, h = element.size or (1.0, 1.0)
        norm = (element.normal or "+Z").upper()
        if norm[-1] == "X":
            return (norm, x, y, y + h, z, z + w)
        elif norm[-1] == "Y":
            return (norm, y, x, x + w, z, z + h)
        else:
            return (norm, z, x, x + w, y, y + h)

    def validate(self, *, require_armature_bindings: bool = True) -> dict[str, object]:
        """Return deterministic errors and warnings without changing the model."""
        errors: list[str] = []
        warnings: list[str] = []
        node_count = len(self._groups)+len(self._armatures)+len(self._armature_bones)+len(self._elements)
        if self.max_nodes is not None and node_count > self.max_nodes:
            errors.append(f"Node count {node_count} exceeds limit {self.max_nodes}")
        for group in self._groups.values():
            if group.role == "folder" and (group.pivot != (0., 0., 0.) or
                                            group.rotation != (0., 0., 0.)):
                errors.append(f"Folder {group.name!r} has a transform; use a transform group")
        if not self.allow_quads and any(element.kind == "mesh" for element in self._elements):
            errors.append("Quads are not allowed by this recipe")
        if self.modeling_mode == "box":
            illegal = [element.name for element in self._elements
                       if element.kind == "mesh" and element.primitive != "rectangular_quad"]
            if illegal:
                errors.append("modeling_mode='box' contains free polygon meshes: " + ", ".join(illegal))
        if self.require_integer_dimensions:
            for element in self._elements:
                if element.kind == "cube":
                    end = element.to_ or element.from_
                    dx = abs(end[0] - element.from_[0])
                    dy = abs(end[1] - element.from_[1])
                    dz = abs(end[2] - element.from_[2])
                    if not (math.isclose(dx, round(dx), abs_tol=1e-5) and
                            math.isclose(dy, round(dy), abs_tol=1e-5) and
                            math.isclose(dz, round(dz), abs_tol=1e-5)):
                        errors.append(
                            f"Element {element.name!r} has non-integer cube dimensions ({dx:g}, {dy:g}, {dz:g}). "
                            "Cube dimensions must be strictly integer to prevent sub-pixel UV distortion."
                        )
                elif element.kind == "mesh":
                    if element.vertices:
                        continue
                    w, h = element.size or (1, 1)
                    if not (math.isclose(w, round(w), abs_tol=1e-5) and
                            math.isclose(h, round(h), abs_tol=1e-5)):
                        errors.append(
                            f"Quad {element.name!r} has non-integer dimensions ({w:g}, {h:g}). "
                            "Quad dimensions must be strictly integer."
                        )
        if self.grid_step is not None:
            for element in self._elements:
                values = list(element.from_)
                if element.to_ is not None:
                    values.extend(element.to_)
                if any(not self._on_grid(value, self.grid_step) for value in values):
                    errors.append(f"Element {element.name!r} is not aligned to grid step {self.grid_step:g}")
        if self.check_coplanar:
            geo_errors, geo_warnings = self._check_geometry_conflicts()
            errors.extend(geo_errors)
            warnings.extend(geo_warnings)
        from .mesh_validation import validate_mesh_elements
        mesh_errors, mesh_warnings = validate_mesh_elements(self._elements)
        errors.extend(mesh_errors)
        warnings.extend(mesh_warnings)
        spatial_errors,spatial_warnings=self._validate_spatial()
        errors.extend(spatial_errors); warnings.extend(spatial_warnings)
        for armature in self._armatures.values():
            cursor = armature.parent
            while cursor is not None:
                group = self._groups.get(cursor)
                if group is None:
                    errors.append(f"Armature {armature.name!r} has an invalid parent group")
                    break
                if group.role != "folder":
                    errors.append(f"Armature {armature.name!r} is nested below transform group {group.name!r}")
                    break
                cursor = group.parent
        for name, bone in self._armature_bones.items():
            if bone.armature not in self._armatures:
                errors.append(f"Armature bone {name!r} references unknown armature")
            if bone.parent is not None:
                parent = self._armature_bones.get(bone.parent)
                if parent is None or parent.armature != bone.armature:
                    errors.append(f"Armature bone {name!r} has invalid parent")
                elif bone.connected and math.dist(bone.start, parent.end) > 1e-6:
                    errors.append(f"Connected armature bone {name!r} is detached from its parent")
        for element in self._elements:
            if element.parent_kind!="armature": continue
            if element.kind!="mesh" or not element.vertices:
                errors.append(f"Armature child {element.name!r} must be a canonical polygon mesh")
            elif element.name not in self._bindings and require_armature_bindings:
                errors.append(f"Armature mesh {element.name!r} is not bound")
            elif element.name in self._bindings and self._binding_topology.get(element.name)!=self._topology_signature(element):
                errors.append(f"Armature mesh {element.name!r} topology changed; bind it again")
            elif element.name in self._bindings:
                weights = self._bindings[element.name]
                if set(weights) != set(element.vertices):
                    errors.append(f"Armature mesh {element.name!r} has unweighted vertices")
                for key, influences in weights.items():
                    if (not influences or len(influences) > 4
                            or any(name not in self._armature_bones or
                                   self._armature_bones[name].armature != element.parent
                                   for name in influences)
                            or any(not math.isfinite(weight) or weight < 0 for weight in influences.values())
                            or not math.isclose(sum(influences.values()), 1, abs_tol=1e-8)):
                        errors.append(f"Armature mesh {element.name!r} has invalid weights at {key!r}")
        if not self._elements:
            warnings.append("Model has no geometry")
        return {"errors": sorted(set(errors)), "warnings": sorted(set(warnings)), "node_count": node_count}

    def spatial_summary(self):
        anchors=sum(len(element.anchors) for element in self._elements)
        frames=sum(len(element.frames) for element in self._elements)
        chain_sockets=sum(2*len(chain) for chain in self._chains.values())
        return {"anchors":anchors,"frames":frames,"sockets":len(self._sockets),
                "chains":len(self._chains),"armature_chains":len(self._armature_chains),
                "chain_endpoints":chain_sockets,
                "warnings":self._validate_spatial()[1]}

    def skinning_audit(self):
        """Return non-blocking diagnostics for suspicious armature weights."""
        meshes=[]; warnings=[]
        for element in self._elements:
            weights=self._bindings.get(element.name)
            if not weights or element.parent_kind!="armature": continue
            policy=self._binding_policies.get(element.name,{})
            scope=policy.get("bones")
            bones={bone.name:bone for bone in self._armature_bones.values()
                   if bone.armature==element.parent and (not scope or bone.name in scope)}
            children={name:set() for name in bones}
            for bone in bones.values():
                if bone.parent in children: children[bone.parent].add(bone.name)
            leaked=[]; dominant={}
            for key,influences in weights.items():
                point=self._element_vertex_world(element,key)
                nearest=min(bones,key=lambda name:(self._distance_to_segment(
                    point,bones[name].start,bones[name].end),name))
                allowed={nearest,*children[nearest]}
                if bones[nearest].parent in bones: allowed.add(bones[nearest].parent)
                unexpected=sorted(name for name,weight in influences.items()
                                  if weight>=.05 and name not in allowed)
                if unexpected: leaked.append((key,tuple(unexpected)))
                winner=max(influences,key=lambda name:(influences[name],name))
                dominant[winner]=dominant.get(winner,0)+1
            rigid_bones={next(iter(value)) for value in weights.values() if len(value)==1}
            rigid=(len(rigid_bones)==1 and all(len(value)==1 and next(iter(value.values()))==1
                                               for value in weights.values()))
            mode=str(policy.get("mode") or ("rigid" if rigid else "unknown"))
            meshes.append({"mesh":element.name,"vertices":len(weights),"rigid":rigid,
                           "mode":mode,
                           "dominant_bones":dict(sorted(dominant.items())),
                           "leaked_vertices":len(leaked)})
            if leaked:
                examples=", ".join(f"{key}->{'/'.join(names)}" for key,names in leaked[:3])
                warnings.append(f"Mesh {element.name!r} has {len(leaked)} vertices with non-local "
                                f"bone influence ({examples})")
        return {"meshes":meshes,"warnings":warnings}

    def _validate_spatial(self):
        errors=[]; warnings=[]
        for element in self._elements:
            for name,frame in element.frames.items():
                if name in element.anchors and math.dist(frame.origin,element.anchors[name])>1e-6:
                    errors.append(f"Element {element.name!r} frame {name!r} is detached from its anchor")
            # A skinned mesh is deformed by its bones, never by its pivot, and a
            # pivot sitting on one of the mesh's own anchors (e.g. a capsule's
            # idealized pole, a loft's base section) is a deliberate choice.
            deliberate=(element.parent_kind=="armature" or
                        any(math.dist(point,(0.,0.,0.))<=1e-6 for point in element.anchors.values()))
            if element.vertices and not deliberate:
                lows=[min(point[i] for point in element.vertices.values()) for i in range(3)]
                highs=[max(point[i] for point in element.vertices.values()) for i in range(3)]
                extent=max(highs[i]-lows[i] for i in range(3))
                gap=math.sqrt(sum((0 if lows[i]<=0<=highs[i] else min(abs(lows[i]),abs(highs[i])))**2 for i in range(3)))
                pivot=tuple(round(v,4) for v in element.origin)
                bounds=(tuple(round(v+o,4) for v,o in zip(lows,element.origin)),
                        tuple(round(v+o,4) for v,o in zip(highs,element.origin)))
                if extent>0 and gap>max(10,extent*4):
                    warnings.append(f"Element {element.name!r} geometry is far from its pivot "
                                    f"{pivot} (bounds {bounds[0]}..{bounds[1]}); pass pivot='center' "
                                    "or another anchor name when adding it")
                elif any(lows[i] > 1e-6 or highs[i] < -1e-6 for i in range(3)) and gap>1e-6:
                    warnings.append(f"Element {element.name!r} pivot {pivot} is outside its geometry "
                                    f"bounds {bounds[0]}..{bounds[1]}; pass pivot='center' or another "
                                    "anchor name when adding it")
        for chain in self._chains.values():
            for owner,child in zip(chain,chain[1:]):
                socket_name=f"{owner}_end"
                if math.dist(self.get_socket(socket_name).origin,self._group_world_frame(child).origin)>1e-4:
                    warnings.append(f"Chain endpoint {socket_name!r} is distant from child joint {child!r}")
        for name,bone in self._groups.items():
            if not name.endswith("_left") or "mirror:override" in bone.tags: continue
            partner_name=name[:-5]+"_right"; partner=self._groups.get(partner_name)
            if partner is None or "mirror:override" in partner.tags: continue
            expected=(-bone.pivot[0],bone.pivot[1],bone.pivot[2])
            if math.dist(expected,partner.pivot)>1e-5:
                warnings.append(f"Bilateral bones {name!r} and {partner_name!r} diverge without mirror:override")
        return errors,warnings

    def to_bbmodel_data(self) -> dict:
        """Validate the model and build the complete bbmodel document in memory."""
        if not self._groups and not self._armatures:
            raise ValueError("Add at least one group or armature before exporting")
        validation = self.validate()
        if validation["errors"]:
            errors = validation["errors"]
            shown = errors[:20]
            more = f"\n  ... and {len(errors) - len(shown)} more" if len(errors) > len(shown) else ""
            raise ValueError("Model validation failed:\n  - " + "\n  - ".join(shown) + more)

        groups = {name: self._group_json(bone) for name, bone in self._groups.items()}
        outliner_nodes = {
            name: {"uuid": bone.uuid, "isOpen": True, "children": []}
            for name, bone in self._groups.items()
        }
        for element in self._elements:
            if element.parent_kind=="group": outliner_nodes[element.parent]["children"].append(element.uuid)
        roots: list[dict] = []
        for name, bone in self._groups.items():
            node = outliner_nodes[name]
            if bone.parent is None:
                roots.append(node)
            else:
                outliner_nodes[bone.parent]["children"].append(node)
        armature_elements=[]

        def armature_bone_outliner_node(bone):
            """Serialize parent nodes exactly as Blockbench's Outliner.toJSON()."""
            return {
                "uuid": bone.uuid,
                "isOpen": True,
                "children": [
                    armature_bone_outliner_node(child)
                    for child in self._armature_bones.values()
                    if child.parent == bone.name
                ],
            }

        for armature in self._armatures.values():
            root_bones=[bone for bone in self._armature_bones.values()
                        if bone.armature==armature.name and bone.parent is None]
            meshes=[element.uuid for element in self._elements
                    if element.parent_kind=="armature" and element.parent==armature.name]
            armature_elements.append(self._armature_json(
                armature, [bone.uuid for bone in root_bones] + meshes
            ))
            armature_node = {
                "uuid": armature.uuid,
                "isOpen": True,
                "children": [armature_bone_outliner_node(bone) for bone in root_bones] + meshes,
            }
            if armature.parent is None:
                roots.append(armature_node)
            else:
                outliner_nodes[armature.parent]["children"].append(armature_node)
        armature_elements.extend(self._armature_bone_json(bone,
            [child.uuid for child in self._armature_bones.values() if child.parent==bone.name])
            for bone in self._armature_bones.values())

        document = {
            "meta": {"format_version": "5.0", "model_format": self.format_id, "box_uv": False},
            "name": self.name,
            "model_identifier": "",
            "visible_box": [1, 1, 0],
            "variable_placeholders": "",
            "variable_placeholder_buttons": [],
            "timeline_setups": [],
            "unhandled_root_fields": {"model_as_code": {
                "version": 3,
                "uv_ready": False,
                "modeling_mode": self.modeling_mode,
                "orientation": self.orientation.as_metadata(),
                "validation_policy": {"check_coplanar": self.check_coplanar},
                "sockets": {
                    name: {
                        "parent": socket.parent,
                        "parent_kind": socket.parent_kind,
                        "position": _clean_vector(socket.position),
                        "forward": _clean_vector(socket.forward),
                        "up": _clean_vector(socket.up),
                        "space": "owner_bind",
                        "source": socket.source,
                        "offset": _clean_vector(socket.offset),
                        "inherit_forward": socket.inherit_forward,
                        "inherit_up": socket.inherit_up,
                    }
                    for name, socket in self._sockets.items()
                },
                "chains": {name:list(chain) for name,chain in self._chains.items()},
                "armature_chains": {name:list(chain) for name,chain in self._armature_chains.items()},
                "binding_policies": copy.deepcopy(self._binding_policies),
            }},
            "elements": [*armature_elements,*[self._element_json(element) for element in self._elements]],
            "groups": list(groups.values()),
            "outliner": roots,
            "textures": [],
            "animations": [],
        }
        return document

    def export_bbmodel(self, filepath: str | Path, *, auto_uv: bool = False,
                       island_padding: int = 1) -> Path:
        document = self.to_bbmodel_data()
        if not isinstance(auto_uv, bool):
            raise TypeError("auto_uv must be a boolean")
        if not isinstance(island_padding, int) or island_padding < 0:
            raise ValueError("island_padding must be a non-negative integer")

        # Geometry first; the independent UV stage consumes the resulting document.
        output = Path(filepath)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not auto_uv:
            output.write_text(json.dumps(document, indent=2), encoding="utf-8")
            return output
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".bbmodel",
                                             prefix=f".{output.stem}.", dir=output.parent,
                                             delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(document, handle, indent=2)
            from Tools.uv_builder import UVBuilder
            UVBuilder(temporary, island_padding=island_padding,
                      require_integer_uvs=(self.modeling_mode == "box")).save()
            temporary.replace(output)
        except Exception:
            if temporary is not None and temporary.exists():
                temporary.unlink()
            raise
        return output

    @staticmethod
    def _armature_json(armature,children):
        result={"type":"armature","uuid":armature.uuid,"name":armature.name,
                "visibility":True,"export":True,
                "locked":False,"isOpen":True,"children":children}
        if armature.tags:result["model_as_code_tags"]=armature.tags
        return result

    @staticmethod
    def _armature_bone_json(bone,children):
        result={"type":"armature_bone","uuid":bone.uuid,"name":bone.name,
                "origin":_clean_vector(bone.origin),"rotation":_clean_vector(bone.rotation),
                "length":_clean_number(bone.length),"width":_clean_number(bone.width),
                "connected":bone.connected,"color":0,"visibility":True,"export":True,
                "locked":False,"isOpen":True,"children":children,
                "vertex_weights":{key:weight for key,weight in sorted(bone.vertex_weights.items())}}
        if bone.tags:result["model_as_code_tags"]=bone.tags
        return result


    @staticmethod
    def _validate_new_name(name: str, existing: dict) -> None:
        if not name or not name.strip():
            raise ValueError("Names cannot be empty")
        if name in existing:
            raise ValueError(f"Duplicate name: {name}")

    def _validate_element_name(self, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("Names cannot be empty")
        if name in self._element_names:
            raise ValueError(f"Duplicate element name: {name}")

    def _unique_element_name(self, base: str) -> str:
        candidate, suffix = base, 2
        while candidate in self._element_names:
            candidate, suffix = f"{base}_{suffix}", suffix + 1
        return candidate

    def _require_parent(self, parent: str) -> None:
        self._normalize_parent(parent)

    def _normalize_parent(self,parent):
        if isinstance(parent,ArmatureHandle): return "armature",parent.name
        if not isinstance(parent,str): raise TypeError("Parent must be a group name or ArmatureHandle")
        if parent.startswith("group:"):
            name=parent[6:]
            if name not in self._groups: raise KeyError(f"Unknown parent group: {name}")
            return "group",name
        if parent.startswith("armature:"):
            name=parent[9:]
            if name not in self._armatures: raise KeyError(f"Unknown parent armature: {name}")
            return "armature",name
        matches=(parent in self._groups,parent in self._armatures)
        if matches==(True,True): raise KeyError(f"Ambiguous parent {parent!r}; use an explicit prefix")
        if matches[0]: return "group",parent
        if matches[1]: return "armature",parent
        raise KeyError(f"Unknown parent: {parent}")

    def _subtree_names(self, root: str) -> list[str]:
        result = [root]
        for name, bone in self._groups.items():
            if bone.parent == root:
                result.extend(self._subtree_names(name))
        return result

    @staticmethod
    def _on_grid(value: float, step: float) -> bool:
        return math.isclose(value / step, round(value / step), abs_tol=1e-9)

    @staticmethod
    def _mirror_rotation(rotation: Vector3, axis_index: int) -> Vector3:
        mirrored = list(rotation)
        for index in range(3):
            if index != axis_index:
                mirrored[index] *= -1
        return tuple(mirrored)  # type: ignore[return-value]


    @staticmethod
    def _group_json(group: _Group) -> dict:
        result = {
            "name": group.name,
            "origin": _clean_vector(group.pivot),
            "rotation": _clean_vector(group.rotation),
            "color": 0,
            "uuid": group.uuid,
            "export": True,
            "locked": False,
            "visibility": True,
            "autouv": 0,
        }
        if group.tags:
            result["model_as_code_tags"] = group.tags
        result["model_as_code_role"] = group.role
        return result

    def _element_json(self, element: _Element) -> dict:
        if element.kind == "cube":
            faces = {}
            for face_name, face_data in element.faces.items():
                if isinstance(face_data, dict):
                    face_dict = copy.deepcopy(face_data)
                    face_dict.setdefault("texture", False)
                    faces[face_name] = face_dict
                else:
                    faces[face_name] = {"uv": face_data, "texture": False}
            result = {
                "name": element.name,
                "box_uv": False,
                "rescale": False,
                "locked": False,
                "visibility": element.visibility,
                "light_emission": 0,
                "render_order": "default",
                "allow_mirror_modeling": True,
                "from": _clean_vector(element.from_),
                "to": _clean_vector(element.to_ or element.from_),
                "autouv": 0,
                "color": 0,
                "origin": _clean_vector(element.origin),
                "rotation": _clean_vector(element.rotation),
                "inflate": _clean_number(element.inflate),
                "uv_offset": element.uv_offset,
                "faces": faces,
                "type": "cube",
                "uuid": element.uuid,
            }
            if element.shading_mode is not None:
                result["shading_mode"] = element.shading_mode
            if element.stretch is not None:
                result["stretch"] = _clean_vector(element.stretch)
        else:
            if element.vertices:
                invalid=[name for name,face in element.faces.items()
                         if len(face.get("vertices",())) not in {3,4}]
                if invalid:
                    raise ValueError(
                        f"Internal tri/quad invariant violated by {element.name!r}: {invalid[:3]}")
                vertices = {key: _clean_vector(value) for key, value in element.vertices.items()}
                mesh_faces=copy.deepcopy(element.faces)
                for face in mesh_faces.values():
                    if len(face.get("vertices", ())) == 4:
                        face["vertices"] = _canonical_quad(face["vertices"], vertices)
            else:
                vertices, order = self._quad_vertices(element)
                quad_face = {"vertices": order, "texture": False}
                if "quad" in element.faces and isinstance(element.faces["quad"], dict):
                    quad_face.update(element.faces["quad"])
                    quad_face.setdefault("vertices", order)
                mesh_faces = {"quad": quad_face}
            result = {
                "name": element.name,
                "color": 0,
                "origin": _clean_vector(element.from_),
                "rotation": _clean_vector(element.rotation),
                "visibility": element.visibility,
                "vertices": vertices,
                "faces": mesh_faces,
                "type": "mesh",
                "uuid": element.uuid,
            }
            if element.shading_mode is not None:
                result["shading"] = element.shading_mode
            if element.vertices:
                result["model_as_code_mesh"] = {
                    "closed": element.mesh_closed,
                    "anchors": {k: _clean_vector(v) for k, v in element.anchors.items()},
                    "primitive": element.primitive,
                }
                if element.mesh_rings:
                    result['model_as_code_mesh']['rings']={k:list(v) for k,v in element.mesh_rings.items()}
            if element.primitive == "rectangular_quad":
                # Keep the native rectangular-quad UV backend.  A mesh metadata
                # object would make the UV/painter layer treat this as a
                # canonical polygon instead of a native rectangular quad.
                result.pop("model_as_code_mesh", None)
                result["model_as_code_geometry_kind"] = "rectangular_quad"

        if element.tags:
            result["model_as_code_tags"] = element.tags
        if element.anchors or element.frames:
            result["model_as_code_spatial"] = {
                "anchors": {k:_clean_vector(v) for k,v in element.anchors.items()},
                "frames": {k:{"origin":_clean_vector(v.origin),
                              "forward":_clean_vector(v.forward),"up":_clean_vector(v.up)}
                           for k,v in element.frames.items()},
            }
        return result

    @staticmethod
    def _quad_vertices(element: _Element) -> tuple[dict[str, list[int | float]], list[str]]:
        x, y, z = element.from_
        width, height = element.size or (1, 1)
        normal = element.normal or "+Z"
        if normal[-1] == "X":
            points = [(x, y, z), (x, y + height, z), (x, y + height, z + width), (x, y, z + width)]
        elif normal[-1] == "Y":
            points = [(x, y, z), (x + width, y, z), (x + width, y, z + height), (x, y, z + height)]
        else:
            points = [(x, y, z), (x + width, y, z), (x + width, y + height, z), (x, y + height, z)]
        if normal[0] == "-":
            points.reverse()
        ids = [_stable_uuid("vertex", element.name, i)[:8] for i, _ in enumerate(points)]
        # Mesh vertices are relative to mesh.origin, unlike cube from/to.
        # Exporting world coordinates here applies the translation twice.
        return {key: _clean_vector(tuple(point[i] - element.from_[i] for i in range(3)))
                for key, point in zip(ids, points)}, ids

    @staticmethod
    def _is_rectangular_quad_mesh(vertices, faces, *, tolerance: float = 1e-7) -> bool:
        """Verify the only mesh representation accepted by ``modeling_mode='box'``.

        Metadata is not authoritative here: a document may claim a
        rectangular quad only if it has exactly one non-degenerate planar
        rectangle face.  This keeps the box-mode boundary enforceable on
        import as well as construction.
        """
        if len(faces) != 1:
            return False
        face = next(iter(faces.values()))
        order = tuple(face.get("vertices", ()))
        if len(order) != 4 or len(set(order)) != 4 or set(order) != set(vertices):
            return False
        try:
            points = [tuple(float(value) for value in vertices[key]) for key in order]
        except (KeyError, TypeError, ValueError):
            return False
        edges = [sub(points[(index + 1) % 4], points[index]) for index in range(4)]
        lengths = [math.sqrt(dot(edge, edge)) for edge in edges]
        if any(length <= tolerance for length in lengths):
            return False
        scale = max(lengths)
        # Opposite sides must oppose exactly, adjacent sides must be orthogonal.
        return (all(math.dist(add(edges[index], edges[(index + 2) % 4]), (0., 0., 0.)) <= tolerance * scale
                    for index in range(2))
                and all(abs(dot(edges[index], edges[(index + 1) % 4])) <= tolerance * scale * scale
                        for index in range(4)))

    @classmethod
    def from_bbmodel_data(cls, data: dict) -> "ModelBuilder":
        root_meta = data.get("unhandled_root_fields", {}).get("model_as_code", {})
        validation_policy = root_meta.get("validation_policy", {})
        orientation_data = root_meta.get("orientation", {})
        builder = cls(
            name=data.get("name", "model"),
            format_id=data.get("meta", {}).get("model_format", "free"),
            modeling_mode=root_meta.get("modeling_mode", "free"),
            check_coplanar=validation_policy.get("check_coplanar", True),
            orientation=ModelOrientation(orientation_data.get("up", "+Y"),
                                         orientation_data.get("front", "+Z")),
        )
        groups = data.get("groups", [])
        groups_by_uuid = {g["uuid"]: g for g in groups if isinstance(g, dict) and "uuid" in g}
        raw_elements = [item for item in data.get("elements", []) if isinstance(item, dict)]
        supported_types = {"cube", "mesh", "armature", "armature_bone"}
        unsupported = sorted({item.get("type", "cube") for item in raw_elements}
                             - supported_types)
        if unsupported:
            raise ValueError("Unsupported Blockbench element types for ModelBuilder: "
                             + ", ".join(str(kind) for kind in unsupported))
        nodes_by_uuid = {item.get("uuid"): item for item in raw_elements if item.get("uuid")}
        raw_armatures = [item for item in raw_elements if item.get("type") == "armature"]
        raw_armature_bones = [item for item in raw_elements if item.get("type") == "armature_bone"]
        armature_uuids = {item["uuid"] for item in raw_armatures}
        armature_bone_uuids = {item["uuid"] for item in raw_armature_bones}

        bone_parent: dict[str, str | None] = {}
        element_parent: dict[str, str] = {}
        armature_parent_uuid: dict[str, str | None] = {}

        def walk_outliner(node, current_group=None):
            if isinstance(node, dict):
                uuid_val = node.get("uuid")
                if uuid_val in armature_uuids:
                    armature_parent_uuid[uuid_val] = current_group
                    return
                if uuid_val in armature_bone_uuids:
                    return
                if uuid_val in nodes_by_uuid:
                    element_parent[uuid_val] = current_group
                    return
                grp = groups_by_uuid.get(uuid_val)
                if grp is None:
                    return
                group_name = grp["name"]
                bone_parent[group_name] = current_group
                for child in node.get("children", []):
                    walk_outliner(child, group_name)
            elif isinstance(node, str):
                if node in armature_uuids:
                    armature_parent_uuid[node] = current_group
                elif node not in armature_bone_uuids:
                    element_parent[node] = current_group

        for root in data.get("outliner", []):
            walk_outliner(root, None)

        for g in groups:
            if isinstance(g, dict) and "name" in g and g["name"] not in bone_parent:
                bone_parent[g["name"]] = None

        def get_depth(b_name: str) -> int:
            depth = 0
            curr = bone_parent.get(b_name)
            seen = set()
            while curr and curr not in seen:
                seen.add(curr)
                depth += 1
                curr = bone_parent.get(curr)
            return depth

        sorted_groups = sorted(
            [g for g in groups if isinstance(g, dict) and "name" in g],
            key=lambda g: get_depth(g["name"]),
        )
        for g in sorted_groups:
            name = g["name"]
            parent = bone_parent.get(name)
            pivot = _vector3(g.get("origin", [0, 0, 0]), "pivot")
            rotation = _vector3(g.get("rotation", [0, 0, 0]), "rotation")
            tags = _tags(g.get("model_as_code_tags", []), f"bone {name!r} tags")
            builder._groups[name] = _Group(
                name, parent, pivot, rotation, tags,
                str(g.get("model_as_code_role", "folder")), g.get("uuid") or _stable_uuid("group", name)
            )

        bone_parent_uuid = {}
        bone_armature_uuid = {}
        armature_mesh_parent = {}
        for armature in raw_armatures:
            for child_uuid in armature.get("children", []):
                if child_uuid in armature_bone_uuids:
                    bone_parent_uuid[child_uuid] = None
                    bone_armature_uuid[child_uuid] = armature["uuid"]
                elif child_uuid in nodes_by_uuid:
                    armature_mesh_parent[child_uuid] = armature["uuid"]
        changed = True
        while changed:
            changed = False
            for parent_bone in raw_armature_bones:
                parent_uuid = parent_bone["uuid"]
                owner_uuid = bone_armature_uuid.get(parent_uuid)
                if owner_uuid is None:
                    continue
                for child_uuid in parent_bone.get("children", []):
                    if child_uuid in armature_bone_uuids and child_uuid not in bone_armature_uuid:
                        bone_parent_uuid[child_uuid] = parent_uuid
                        bone_armature_uuid[child_uuid] = owner_uuid
                        changed = True

        armature_names_by_uuid = {}
        for raw in raw_armatures:
            name = str(raw.get("name") or raw["uuid"])
            builder._validate_new_name(name, builder._armatures)
            native_origin = _vector3(raw.get("origin", (0, 0, 0)), "armature origin")
            if math.dist(native_origin, (0., 0., 0.)) > 1e-8:
                raise ValueError("Blockbench armatures do not support an offset origin")
            parent = armature_parent_uuid.get(raw["uuid"])
            if parent is not None:
                cursor = parent
                while cursor is not None:
                    group = builder._groups.get(cursor)
                    if group is None or group.role != "folder":
                        raise ValueError("Armature is nested below a transform group")
                    cursor = group.parent
            builder._armatures[name] = _Armature(
                name=name,
                origin=(0., 0., 0.),
                tags=_tags(raw.get("model_as_code_tags", []), f"armature {name!r} tags"),
                parent=parent,
                uuid=raw["uuid"],
            )
            armature_names_by_uuid[raw["uuid"]] = name

        raw_bones_by_uuid = {item["uuid"]: item for item in raw_armature_bones}
        bone_names_by_uuid = {item["uuid"]: str(item.get("name") or item["uuid"])
                              for item in raw_armature_bones}
        pending = set(raw_bones_by_uuid)
        while pending:
            progressed = False
            for bone_uuid in sorted(pending):
                owner_uuid = bone_armature_uuid.get(bone_uuid)
                if owner_uuid not in armature_names_by_uuid:
                    raise ValueError(f"Armature bone {bone_names_by_uuid[bone_uuid]!r} has no armature")
                parent_uuid = bone_parent_uuid.get(bone_uuid)
                if parent_uuid is not None and bone_names_by_uuid[parent_uuid] not in builder._armature_bones:
                    continue
                raw = raw_bones_by_uuid[bone_uuid]
                name = bone_names_by_uuid[bone_uuid]
                parent = bone_names_by_uuid[parent_uuid] if parent_uuid else None
                armature_name = armature_names_by_uuid[owner_uuid]
                origin = _vector3(raw.get("origin", (0, 0, 0)), f"bone {name!r} origin")
                rotation = _vector3(raw.get("rotation", (0, 0, 0)), f"bone {name!r} rotation")
                length = float(raw.get("length", 1))
                width = float(raw.get("width", max(.25, length * .2)))
                parent_frame = (builder._armature_bone_world_frame(parent) if parent
                                else SpatialFrame(builder._armatures[armature_name].origin))
                start = parent_frame.point(origin)
                direction = parent_frame.vector(builder._rotate_vector((0, 1, 0), rotation))
                end = add(start, mul(unit(direction), length))
                builder._armature_bones[name] = _ArmatureBone(
                    name, armature_name, parent, origin, rotation, length, width,
                    bool(raw.get("connected", False)),
                    _tags(raw.get("model_as_code_tags", []), f"bone {name!r} tags"),
                    start, end,
                    {str(key): float(value) for key, value in raw.get("vertex_weights", {}).items()},
                    bone_uuid,
                )
                pending.remove(bone_uuid)
                progressed = True
                break
            if not progressed:
                raise ValueError("Armature bone hierarchy is cyclic or incomplete")

        builder._chains={str(name):tuple(chain) for name,chain in root_meta.get("chains",{}).items()}
        builder._armature_chains={str(name):tuple(chain) for name,chain in root_meta.get("armature_chains",{}).items()}
        for name, payload in root_meta.get("sockets", {}).items():
            parent = payload.get("parent")
            parent_kind = payload.get("parent_kind", "group")
            owners = builder._armature_bones if parent_kind == "bone" else builder._groups
            if parent not in owners:
                raise ValueError(f"Socket {name!r} references unknown {parent_kind} {parent!r}")
            if payload.get("space") == "owner_bind":
                builder._sockets[name]=_Socket(name,parent,
                    _vector3(payload.get("position",owners[parent].origin if parent_kind == "bone" else owners[parent].pivot),"socket position"),
                    _vector3(payload.get("forward",(0,1,0)),"socket forward"),
                    _vector3(payload.get("up",(0,0,1)),"socket up"),payload.get("source"),
                    _vector3(payload.get("offset",(0,0,0)),"socket offset"),
                    bool(payload.get("inherit_forward",payload.get("inherit_orientation",False))),
                    bool(payload.get("inherit_up",payload.get("inherit_orientation",False))),
                    parent_kind)
            else:
                default_position = owners[parent].origin if parent_kind == "bone" else owners[parent].pivot
                owner_ref = f"bone:{parent}" if parent_kind == "bone" else parent
                builder.add_socket(name,owner_ref,at=payload.get("position",default_position),
                                   forward=payload.get("forward",(0,1,0)),up=payload.get("up",(0,0,1)))

        armature_name_for_uuid = {uuid_value: name for uuid_value, name in armature_names_by_uuid.items()}
        for elem in raw_elements:
            elem_uuid = elem.get("uuid") or _stable_uuid("element", elem.get("name", "element"))
            elem_name = elem.get("name", "element")
            parent = element_parent.get(elem_uuid)
            if parent is None and builder._groups:
                parent = next(iter(builder._groups.keys()))
            kind = elem.get("type", "cube")
            if kind in {"armature", "armature_bone"}:
                continue
            parent_kind = "group"
            if elem_uuid in armature_mesh_parent:
                parent = armature_name_for_uuid[armature_mesh_parent[elem_uuid]]
                parent_kind = "armature"
            tags = _tags(elem.get("model_as_code_tags", []), f"element {elem_name!r} tags")
            vis = elem.get("visibility", True)
            spatial = elem.get("model_as_code_spatial", {})
            spatial_anchors={str(k):_vector3(v,f"anchor {k!r}") for k,v in spatial.get("anchors",{}).items()}
            spatial_frames={str(k):SpatialFrame(v["origin"],v["forward"],v["up"])
                            for k,v in spatial.get("frames",{}).items()}

            if kind == "cube":
                f_ = _vector3(elem.get("from", [0, 0, 0]), "from_")
                t_ = _vector3(elem.get("to", [1, 1, 1]), "to_")
                orig = _vector3(elem.get("origin", f_), "origin")
                rot = _vector3(elem.get("rotation", [0, 0, 0]), "rotation")
                inf = float(elem.get("inflate", 0))
                shading = elem.get("shading_mode")
                stretch = _vector3(elem["stretch"], "stretch") if "stretch" in elem and elem["stretch"] is not None else None
                faces = elem.get("faces", {})
                uv_offset = elem.get("uv_offset", [0, 0])
                builder._elements.append(_Element(
                    "cube", elem_name, parent or "", f_, t_, None, None, tags, orig, rot, inf, vis, shading, stretch, elem_uuid, uv_offset, faces,
                    anchors=spatial_anchors,frames=spatial_frames,parent_kind=parent_kind
                ))
            else:
                orig = _vector3(elem.get("origin", [0, 0, 0]), "origin")
                vertices = elem.get("vertices", {})
                faces = elem.get("faces", {})
                metadata = elem.get("model_as_code_mesh", {})
                geometry_kind = elem.get("model_as_code_geometry_kind", metadata.get("primitive"))
                if not vertices or not faces:
                    raise ValueError(
                        f"Imported mesh {elem_name!r} requires explicit vertices and quad faces")
                invalid=[str(key) for key,face in faces.items()
                         if len(face.get("vertices",())) not in {3,4}]
                if invalid:
                    raise ValueError(
                        f"Imported mesh {elem_name!r} must use only triangles or quads; invalid faces: {invalid[:3]}")
                MeshGeometry.create(
                    vertices,
                    {str(key):MeshFace(tuple(face.get("vertices",())),
                                       face.get("model_as_code_group"),
                                       face.get("model_as_code_source_face"))
                     for key,face in faces.items()},
                    closed=bool(metadata.get("closed",False)),
                )
                if geometry_kind == "rectangular_quad" and not cls._is_rectangular_quad_mesh(vertices, faces):
                    if builder.modeling_mode == "box":
                        raise ValueError(
                            f"Imported rectangular_quad {elem_name!r} must contain exactly one planar rectangular quad")
                    # A human may have edited a formerly rectangular patch in
                    # Blockbench.  In free mode retain the valid geometry, but
                    # revoke the rectangular-quad optimization rather than
                    # trusting stale metadata.
                    geometry_kind = "mesh"
                builder._elements.append(_Element(
                    "mesh", elem_name, parent or "", orig, None, None, None, tags, orig,
                    _vector3(elem.get("rotation", [0, 0, 0]), "rotation"), 0, vis,
                    elem.get("shading", "flat"), None, elem_uuid, [0, 0], copy.deepcopy(faces),
                    {str(k): _vector3(v, f"vertex {k!r}") for k, v in vertices.items()},
                    bool(metadata.get("closed", False)),
                    spatial_anchors or {str(k): _vector3(v, f"anchor {k!r}") for k, v in metadata.get("anchors", {}).items()},
                    geometry_kind,
                    {str(k):tuple(v) for k,v in metadata.get('rings',{}).items()},
                    spatial_frames,parent_kind))
            builder._element_names.add(elem_name)

        if builder.modeling_mode == "box":
            illegal = [element.name for element in builder._elements
                       if element.kind == "mesh" and (
                           element.primitive != "rectangular_quad"
                           or not cls._is_rectangular_quad_mesh(element.vertices, element.faces))]
            if illegal:
                raise ValueError("Imported box model contains free polygon meshes: " + ", ".join(illegal))

        for element in builder._elements:
            if element.parent_kind != "armature" or not element.vertices:
                continue
            prefix = element.uuid[:6] + ":"
            weights = {}
            for vertex_key in element.vertices:
                native_key = prefix + vertex_key
                influences = {
                    bone.name: bone.vertex_weights[native_key]
                    for bone in builder._armature_bones.values()
                    if bone.armature == element.parent and native_key in bone.vertex_weights
                }
                if influences:
                    weights[vertex_key] = builder._normalize_weights(influences)
            if weights:
                builder._bindings[element.name] = weights
                builder._binding_topology[element.name] = builder._topology_signature(element)

        for mesh_name, policy in root_meta.get("binding_policies", {}).items():
            if mesh_name in builder._bindings and isinstance(policy, dict):
                builder._binding_policies[mesh_name] = copy.deepcopy(policy)

        return builder

    @classmethod
    def from_bbmodel(cls, filepath: str | Path) -> "ModelBuilder":
        content = Path(filepath).read_text(encoding="utf-8")
        return cls.from_bbmodel_data(json.loads(content))
