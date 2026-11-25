"""Forward kinematics of a BBModel outliner, matching the project viewer and GLB delivery.

A node's transform is ``T(origin + Δposition) · R_zyx(rest + Δrotation) · S(Δscale)``. Children of a
transform group are additionally offset by ``-origin`` (group origins are pivots in model space);
armature and armature-bone origins are local joint offsets. Rotations are Blockbench degrees applied
as three.js Euler order "ZYX" (R = Rz · Ry · Rx), exactly as ``Tools/viewer/js/bbmodel_parser.js``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .animation_sampling import sample

Vec = tuple[float, float, float]
Mat = tuple[Vec, Vec, Vec]
IDENTITY: Mat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


# ----------------------------------------------------------------------------- vectors and matrices
def add(a, b, k=1.0) -> Vec:
    return (a[0] + b[0] * k, a[1] + b[1] * k, a[2] + b[2] * k)


def sub(a, b) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a, k) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def norm(a) -> float:
    return math.sqrt(dot(a, a))


def unit(a) -> Vec:
    length = norm(a)
    if length < 1e-12:
        raise ValueError("Cannot normalize a zero-length vector")
    return scale(a, 1.0 / length)


def reject(a, axis) -> Vec:
    """Component of ``a`` perpendicular to the unit vector ``axis``."""
    return sub(a, scale(axis, dot(a, axis)))


def mm(a, b) -> Mat:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))


def mv(a, v) -> Vec:
    return tuple(a[i][0] * v[0] + a[i][1] * v[1] + a[i][2] * v[2] for i in range(3))


def transpose(a) -> Mat:
    return tuple(tuple(a[j][i] for j in range(3)) for i in range(3))


def inverse(a) -> Mat:
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if abs(det) < 1e-12:
        raise ValueError("Transform is singular (a scale of zero?)")
    cof = [[(a[(j + 1) % 3][(i + 1) % 3] * a[(j + 2) % 3][(i + 2) % 3]
             - a[(j + 1) % 3][(i + 2) % 3] * a[(j + 2) % 3][(i + 1) % 3]) for j in range(3)] for i in range(3)]
    return tuple(tuple(cof[i][j] / det for j in range(3)) for i in range(3))


def rot_x(deg) -> Mat:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((1.0, 0.0, 0.0), (0.0, c, -s), (0.0, s, c))


def rot_y(deg) -> Mat:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, 0.0, s), (0.0, 1.0, 0.0), (-s, 0.0, c))


def rot_z(deg) -> Mat:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return ((c, -s, 0.0), (s, c, 0.0), (0.0, 0.0, 1.0))


def rot_zyx(euler) -> Mat:
    """Rotation of Blockbench degrees (x, y, z) in three.js order "ZYX": R = Rz · Ry · Rx."""
    return mm(rot_z(euler[2]), mm(rot_y(euler[1]), rot_x(euler[0])))


def euler_zyx(m, gimbal_x: float = 0.0) -> Vec:
    """Inverse of ``rot_zyx``; degrees, y in [-90, 90].

    At gimbal lock (y = ±90°) only x and z combined are defined; x is then ``gimbal_x`` (pass the
    previous sample's x to stay continuous) and z absorbs the rest.
    """
    y = math.asin(-max(-1.0, min(1.0, m[2][0])))
    if abs(m[2][0]) < 0.9999999:
        x = math.atan2(m[2][1], m[2][2])
        z = math.atan2(m[1][0], m[0][0])
    else:
        x = math.radians(gimbal_x)
        rest = mm(m, transpose(rot_x(gimbal_x)))           # = Rz(z) · Ry(±90°)
        z = math.atan2(-rest[0][1], rest[1][1])
    return (math.degrees(x), math.degrees(y), math.degrees(z))


def nearest_euler(euler, previous) -> Vec:
    """The Euler triple equivalent to ``euler`` closest to ``previous`` (no 179° → -179° jumps)."""
    def shifted(candidate):
        return tuple(value + 360.0 * round((reference - value) / 360.0)
                     for value, reference in zip(candidate, previous))
    alternative = (euler[0] + 180.0, 180.0 - euler[1], euler[2] + 180.0)
    options = [shifted(euler), shifted(alternative)]
    return min(options, key=lambda option: sum((a - b) ** 2 for a, b in zip(option, previous)))


def continuous_euler(m, previous) -> Vec:
    """Euler degrees of rotation ``m`` closest to the ``previous`` triple, robust through gimbal lock."""
    return nearest_euler(euler_zyx(m, gimbal_x=previous[0]), previous)


def axis_rotation(axis, deg) -> Mat:
    ax = unit(axis)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    k = ((0.0, -ax[2], ax[1]), (ax[2], 0.0, -ax[0]), (-ax[1], ax[0], 0.0))
    kk = mm(k, k)
    return tuple(tuple((1.0 if i == j else 0.0) + s * k[i][j] + (1 - c) * kk[i][j] for j in range(3))
                 for i in range(3))


def shortest_rotation(u, v) -> Mat:
    """Smallest rotation taking unit vector ``u`` onto unit vector ``v``."""
    c = max(-1.0, min(1.0, dot(u, v)))
    if c > 1 - 1e-12:
        return IDENTITY
    if c < -1 + 1e-12:
        helper = (1.0, 0.0, 0.0) if abs(u[0]) < 0.9 else (0.0, 1.0, 0.0)
        return axis_rotation(cross(u, helper), 180.0)
    return axis_rotation(cross(u, v), math.degrees(math.acos(c)))


def signed_angle(a, b, axis) -> float:
    """Degrees rotating ``a`` onto ``b`` about ``axis`` (both projected onto its plane)."""
    return math.degrees(math.atan2(dot(axis, cross(a, b)), dot(a, b)))


# ----------------------------------------------------------------------------- rig
@dataclass(frozen=True)
class Frame:
    """World transform of a node: ``world_point = linear · local + origin``."""
    linear: Mat
    origin: Vec

    def point(self, local) -> Vec:
        return add(self.origin, mv(self.linear, local))

    def compose(self, linear, offset) -> "Frame":
        return Frame(mm(self.linear, linear), self.point(offset))


ROOT = Frame(IDENTITY, (0.0, 0.0, 0.0))


@dataclass(frozen=True)
class RigNode:
    uuid: str
    name: str
    kind: str                  # "group", "folder", "armature", "bone"
    parent: str | None
    origin: Vec
    rotation: Vec
    length: float | None       # armature bones only; the tip lies at (0, length, 0) in the bone frame

    @property
    def pivots_children(self) -> bool:
        return self.kind in {"group", "folder"}


def _vec(value, default=(0.0, 0.0, 0.0)) -> Vec:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return default
    return tuple(float(item or 0.0) for item in value)


class Rig:
    """Outliner transforms of a BBModel, evaluated the way the viewer and GLB delivery evaluate them."""

    def __init__(self, nodes: dict[str, RigNode]):
        self.nodes = nodes
        self.order = tuple(nodes)              # outliner depth-first order: parents precede children
        self._rest: dict[str, Frame] | None = None

    @classmethod
    def from_document(cls, data: dict) -> "Rig":
        groups = {item.get("uuid"): item for item in data.get("groups", []) if isinstance(item, dict)}
        elements = {item.get("uuid"): item for item in data.get("elements", []) if isinstance(item, dict)}
        nodes: dict[str, RigNode] = {}

        def visit(node, parent):
            if not isinstance(node, dict):
                return
            uid = node.get("uuid")
            item = groups.get(uid) or elements.get(uid) or node
            if uid in elements:
                kind = {"armature": "armature", "armature_bone": "bone"}.get(item.get("type"), "group")
            else:
                kind = "folder" if item.get("model_as_code_role") == "folder" else "group"
            length = float(item.get("length", 0.0)) if kind == "bone" else None
            nodes[uid] = RigNode(uid, item.get("name") or "", kind, parent, _vec(item.get("origin")),
                                 _vec(item.get("rotation")), length)
            for child in node.get("children", []):
                visit(child, uid)

        for root in data.get("outliner", []):
            visit(root, None)
        return cls(nodes)

    def fk(self, pose: dict | None = None) -> dict[str, Frame]:
        """World frame of every node. ``pose`` maps uuid -> {"position"|"rotation"|"scale": offset}."""
        pose = pose or {}
        frames: dict[str, Frame] = {}
        containers: dict[str, Frame] = {}
        for uid in self.order:
            node = self.nodes[uid]
            offsets = pose.get(uid, {})
            parent = containers[node.parent] if node.parent else ROOT
            position = add(node.origin, offsets.get("position", (0.0, 0.0, 0.0)))
            rotation = add(node.rotation, offsets.get("rotation", (0.0, 0.0, 0.0)))
            factor = offsets.get("scale", (1.0, 1.0, 1.0))
            linear = mm(rot_zyx(rotation), ((factor[0], 0.0, 0.0), (0.0, factor[1], 0.0), (0.0, 0.0, factor[2])))
            frame = parent.compose(linear, position)
            frames[uid] = frame
            containers[uid] = frame.compose(IDENTITY, scale(node.origin, -1.0)) if node.pivots_children else frame
        return frames

    @property
    def rest(self) -> dict[str, Frame]:
        if self._rest is None:
            self._rest = self.fk()
        return self._rest

    def parent_container(self, uid: str, frames: dict[str, Frame]) -> Frame:
        """Frame the node's own origin is expressed in (its parent's children container)."""
        parent = self.nodes[uid].parent
        if parent is None:
            return ROOT
        frame = frames[parent]
        return frame.compose(IDENTITY, scale(self.nodes[parent].origin, -1.0)) \
            if self.nodes[parent].pivots_children else frame

    def carried_point(self, uid: str, rest_point, frames: dict[str, Frame]) -> Vec:
        """Where the model-space ``rest_point``, carried rigidly by node ``uid``, lies in ``frames``."""
        rest = self.rest[uid]
        local = mv(inverse(rest.linear), sub(rest_point, rest.origin))
        return frames[uid].point(local)

    def tip(self, uid: str, frames: dict[str, Frame]) -> Vec | None:
        node = self.nodes[uid]
        return frames[uid].point((0.0, node.length, 0.0)) if node.kind == "bone" else None

    def ancestors(self, uid: str) -> list[str]:
        found, current = [], self.nodes[uid].parent
        while current is not None:
            found.append(current)
            current = self.nodes[current].parent
        return found

    def descendants(self, uid: str) -> list[str]:
        return [other for other in self.order if uid in self.ancestors(other)]


def pose_from_tracks(tracks: dict[str, list[dict]], time: float, *, skip=()) -> dict:
    """Offsets of every keyed channel at ``time``. ``skip`` holds (uuid, channel) pairs to leave at rest."""
    pose: dict[str, dict] = {}
    for uid, keyframes in tracks.items():
        for channel in ("position", "rotation", "scale"):
            if (uid, channel) in skip:
                continue
            keys = [kf for kf in keyframes if kf["channel"] == channel]
            if keys:
                pose.setdefault(uid, {})[channel] = tuple(sample(keys, time, context=f"control {uid}, {channel}"))
    return pose
