"""Read a bbmodel as named entities and print recipe code that recreates them verbatim."""
from __future__ import annotations

import copy
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from types import SimpleNamespace

from lib.animation import _catalog
from lib.geometry_types import MeshDraft, MeshGeometry
from lib.model_builder import ModelBuilder

KIND_ORDER = {"group": 0, "armature": 1, "bone": 2, "socket": 3, "cube": 4, "mesh": 4, "bind": 5, "clip": 6}
CUBE_FIELDS = ("from", "to", "origin", "rotation", "inflate", "stretch")
DEFAULTS = {"rotation": [0, 0, 0], "inflate": 0}
INTERPOLATION = {"linear": "linear", "step": "constant", "catmullrom": "catmullrom"}   # bbmodel name -> AnimationTrack.key name


# ------------------------------------------------------------------ numbers
def _num(value, digits=6):
    value = round(float(value), digits) + 0.0
    return int(value) if value.is_integer() else value


def _numeric(value):
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _vec(values):
    return tuple(_num(v) for v in values)


def _pt(values):
    return tuple(_num(v, 9) for v in values)


def _key(values):
    return tuple(round(float(v), 3) + 0.0 for v in values)


def _value(item, field_name):
    value = item.get(field_name, DEFAULTS.get(field_name))
    if value is None:
        return None
    return _key(value) if isinstance(value, (list, tuple)) else round(float(value), 3) + 0.0


def _tags(tags):
    tags = list(tags or [])
    return f", tags={tags!r}" if tags else ""


# ------------------------------------------------------------------- scene
@dataclass
class Entity:
    kind: str
    name: str
    parent: str | None
    sig: dict
    raw: object
    order: int


@dataclass
class Scene:
    doc: dict
    entities: dict = field(default_factory=dict)
    builder: ModelBuilder | None = None
    controls: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    @property
    def mode(self):
        return self.doc.get("unhandled_root_fields", {}).get("model_as_code", {}).get("modeling_mode", "free")

    def add(self, kind, name, parent, sig, raw):
        self.entities[(kind, name)] = Entity(kind, name, parent, sig, raw, len(self.entities))

    def depth(self, entity):
        depth, cursor, seen = 0, entity.parent, set()
        while cursor and cursor not in seen:
            seen.add(cursor)
            depth += 1
            parent = self.entities.get((entity.kind, cursor))
            cursor = parent.parent if parent else None
        return depth


def _faces(mesh):
    """Faces as coordinate loops, independent of vertex names and of the loop's start."""
    loops = []
    for face in mesh["faces"].values():
        points = [_key(mesh["vertices"][k]) for k in face["vertices"]]
        start = points.index(min(points))
        loops.append(tuple(points[start:] + points[:start]))
    return Counter(loops)


def effective_role(group):
    return "transform" if group.role == "transform" or any(group.pivot) or any(group.rotation) else "folder"


def weights_by_mesh(builder):
    prefix = {e.uuid[:6]: e.name for e in builder._elements if e.kind == "mesh"}
    out = {}
    for bone in builder._armature_bones.values():
        for key, weight in bone.vertex_weights.items():
            head, _, vertex = key.partition(":")
            out.setdefault(prefix.get(head, head), {}).setdefault(vertex, {})[bone.name] = round(weight, 3)
    return out


def clip_signature(clip, labels):
    tracks = {}
    for uid, animator in clip.get("animators", {}).items():
        if uid == "effects":
            continue
        label = labels.get(uid, animator.get("name", uid))
        for kf in animator.get("keyframes", []):
            point = (kf.get("data_points") or [{}])[0]
            tracks.setdefault((label, kf["channel"]), []).append(
                (round(kf["time"], 4), tuple(_scalar(point.get(a, 0)) for a in "xyz"),
                 kf.get("interpolation", "linear")))
    return {"loop": clip.get("loop"), "length": round(clip["length"], 4),
            "tracks": {k: sorted(v, key=lambda item: item[0]) for k, v in tracks.items()}}


def _scalar(value):
    try:
        return round(float(value), 3) + 0.0
    except (TypeError, ValueError):
        return value


def _outliner_parents(doc):
    names = {i["uuid"]: i["name"] for i in [*doc.get("groups", []), *doc.get("elements", [])] if "uuid" in i}
    parents = {}

    def visit(node, parent):
        uid = node if isinstance(node, str) else node["uuid"]
        parents[uid] = names.get(parent)
        if isinstance(node, dict):
            for child in node.get("children", []):
                visit(child, uid)

    for root in doc.get("outliner", []):
        visit(root, None)
    return parents


def _quarantine(doc, mode):
    """Split off what the builder cannot parse: bad meshes (invalid geometry, polygons in box mode) and locators."""
    doc, bad, locators = copy.deepcopy(doc), [], []
    for element in list(doc.get("elements", [])):
        if element.get("type") == "locator":
            locators.append(element)
            doc["elements"].remove(element)
            continue
        if element.get("type") != "mesh":
            continue
        try:
            if mode == "box" and element.get("model_as_code_geometry_kind") != "rectangular_quad":
                raise ValueError("polygon mesh in box mode")
            MeshGeometry.create(element["vertices"], {k: f["vertices"] for k, f in element["faces"].items()})
        except (ValueError, KeyError):
            bad.append(element)
            doc["elements"].remove(element)
    gone = {e["uuid"] for e in [*bad, *locators]}

    def strip(node):
        if isinstance(node, dict):
            node["children"] = [c for c in node.get("children", [])
                                if (c if isinstance(c, str) else c["uuid"]) not in gone]
            for child in node["children"]:
                strip(child)

    for root in doc.get("outliner", []):
        strip(root)
    return doc, bad, locators


def build_scene(doc, *, clips=False, geometry_only=False):
    """Parse ``doc`` into comparable entities: model parts, or (``clips=True``) animation clips.

    Meshes the builder cannot parse are kept aside and reported as they are. ``geometry_only=True`` leaves out
    armatures, bones and weights: they belong to the recipe when hand edits are followed, and are only
    read when a recipe is created from an existing model. ``scene.notes`` holds information lines.
    """
    scene = Scene(doc)
    if clips:
        scene.controls = {c.uuid: c for c in _catalog(doc) if c.kind != "folder"}
        labels = {uid: c.path for uid, c in scene.controls.items()}
        for clip in doc.get("animations", []):
            scene.add("clip", clip["name"], None, clip_signature(clip, labels), clip)
        return scene
    parsable, unparsable, locators = _quarantine(doc, scene.mode)
    builder = scene.builder = ModelBuilder.from_bbmodel_data(parsable)
    for g in builder._groups.values():
        scene.add("group", g.name, g.parent, {"parent": g.parent, "role": effective_role(g),
                                              "pivot": _key(g.pivot), "rotation": _key(g.rotation)}, g)
    for a in ([] if geometry_only else builder._armatures.values()):
        scene.add("armature", a.name, a.parent, {"parent": a.parent}, a)
    for b in ([] if geometry_only else builder._armature_bones.values()):
        scene.add("bone", b.name, b.parent,
                  {"armature": b.armature, "parent": b.parent, "start": _key(b.start), "end": _key(b.end),
                   "connected": bone_connected(builder, b), "width": round(b.width, 3)}, b)
    raw = {e["name"]: e for e in doc.get("elements", []) if e.get("type") in ("mesh", "cube")}
    for e in builder._elements:
        element = raw[e.name]
        if e.kind == "cube":
            sig = {"parent": e.parent, **{f: _value(element, f) for f in CUBE_FIELDS}}
        else:
            sig = {"parent": e.parent, "faces": _faces(element),
                   "origin": _value(element, "origin"), "rotation": _value(element, "rotation")}
        scene.add(e.kind, e.name, e.parent, sig, element)
    parents = _outliner_parents(doc)
    for element in unparsable:
        scene.add("mesh", element["name"], parents.get(element["uuid"]),
                  {"parent": parents.get(element["uuid"]), "faces": _faces(element),
                   "origin": _value(element, "origin"), "rotation": _value(element, "rotation")}, element)
    for s in builder._sockets.values():
        scene.add("socket", s.name, s.parent, _socket_sig(s), s)
    for locator in locators:
        scene.notes.append(f"locator {locator['name']}: the builder has no locators; add_socket makes an attachment point")
    loose = [e for e in scene.entities.values() if e.kind in ("cube", "mesh", "socket") and not e.parent]
    first_group = next((e.name for e in scene.entities.values() if e.kind == "group"), None)
    if loose and first_group:
        for entity in loose:
            entity.parent = entity.sig["parent"] = first_group
            if entity.kind == "socket":
                entity.raw.parent, entity.raw.parent_kind = first_group, "group"
    elif loose:
        # the builder needs a group parent; Blockbench allows elements at the root of the outliner
        scene.add("group", "root", None,
                  {"parent": None, "role": "folder", "pivot": (0.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0)},
                  SimpleNamespace(name="root", parent=None, role="folder", pivot=(0, 0, 0),
                                  rotation=(0, 0, 0), tags=[]))
        for entity in loose:
            entity.parent = entity.sig["parent"] = "root"
            if entity.kind == "socket":
                entity.raw.parent, entity.raw.parent_kind = "root", "group"
    for mesh, per_vertex in ({} if geometry_only else weights_by_mesh(builder)).items():
        vertices = frozenset(raw.get(mesh, {}).get("vertices", per_vertex))
        scene.add("bind", mesh, None,
                  {"vertices": vertices, "weights": {v: tuple(sorted(w.items())) for v, w in per_vertex.items()}},
                  per_vertex)
    return scene


def _socket_sig(s):
    return {"parent": s.parent, "kind": s.parent_kind, "position": _key(s.position),
            "forward": _key(s.forward), "up": _key(s.up)}


def _weight_diffs(a, b):
    """Vertices both meshes have that carry weights in ``b`` (the bbmodel) and differ from ``a``.

    A vertex with no weights in the bbmodel is not a difference: it has no influence to freeze and the
    recipe's bind weights it; edit_diff lists such vertices as a note.
    """
    return [v for v in a["vertices"] & b["vertices"] if v in b["weights"] and a["weights"].get(v, ()) != b["weights"][v]]


def same(kind, a, b):
    if kind == "bind":
        return not _weight_diffs(a, b)
    return a == b


def describe(kind, a, b):
    if kind == "bind":
        return [f"weights differ on {len(_weight_diffs(a, b))} vertices"]
    if kind == "clip":
        notes = [f"{f} {a[f]} -> {b[f]}" for f in ("loop", "length") if a[f] != b[f]]
        changed = sorted(str(k[0]) + "." + k[1] for k in a["tracks"].keys() | b["tracks"].keys()
                         if a["tracks"].get(k) != b["tracks"].get(k))
        return notes + ([f"keyframes differ on {', '.join(changed[:3])}" + (" ..." if len(changed) > 3 else "")]
                        if changed else [])
    notes = []
    for f in a:
        if a[f] == b[f]:
            continue
        if f == "faces":
            notes.append(f"faces +{sum((b[f] - a[f]).values())}/-{sum((a[f] - b[f]).values())} "
                         f"(now {sum(b[f].values())})")
        else:
            show = lambda v: list(v) if isinstance(v, tuple) else v
            notes.append(f"{f} {show(a[f])} -> {show(b[f])}")
    return notes




def _fmt(values):
    return "[" + ", ".join(str(_num(v, 3)) for v in values) + "]"


def _cap(lines, full, limit=12):
    if full or len(lines) <= limit:
        return lines
    return lines[:limit] + [f"... {len(lines) - limit} more (run with --full)"]


def _mesh_lines(a, b):
    va, vb = a["vertices"], b["vertices"]
    fa = {k: tuple(f["vertices"]) for k, f in a["faces"].items()}
    fb = {k: tuple(f["vertices"]) for k, f in b["faces"].items()}
    lines = []
    for v, point in vb.items():
        if v not in va:
            lines.append(f"+ vertex {v}: {_fmt(point)}")
        elif _key(va[v]) != _key(point):
            used = sorted(k for k, order in fb.items() if v in order)
            lines.append(f"vertex {v} (in faces {', '.join(used) or 'none'}): {_fmt(va[v])} -> {_fmt(point)}")
    lines += [f"- vertex {v}" for v in va if v not in vb]
    for k, order in fb.items():
        if k not in fa:
            lines.append(f"+ face {k}: {' '.join(order)}")
        elif fa[k] != order:
            lines.append(f"face {k}: {' '.join(fa[k])} -> {' '.join(order)}")
    lines += [f"- face {k}" for k in fa if k not in fb]
    return lines


def _clip_lines(a, b):
    api = lambda name: "constant" if name == "step" else name
    lines = [f"{f} {a[f]} -> {b[f]}" for f in ("loop", "length") if a[f] != b[f]]
    for key in sorted(a["tracks"].keys() | b["tracks"].keys(), key=str):
        old = {t: (v, i) for t, v, i in a["tracks"].get(key, [])}
        new = {t: (v, i) for t, v, i in b["tracks"].get(key, [])}
        label = f"{key[0]}.{key[1]}"
        for t in sorted(old.keys() | new.keys()):
            if t not in old:
                lines.append(f"+ {label} t={t}: {_fmt(new[t][0])} {api(new[t][1])}")
            elif t not in new:
                lines.append(f"- {label} t={t}")
            elif old[t] != new[t]:
                lines.append(f"{label} t={t}: {_fmt(old[t][0])} {api(old[t][1])} -> {_fmt(new[t][0])} {api(new[t][1])}")
    return lines


def changes(entity_a, entity_b, full=False):
    """What differs between two versions of one part, at the level an agent needs to edit the recipe."""
    kind, a, b = entity_a.kind, entity_a.sig, entity_b.sig
    lines = []
    if kind == "clip":
        lines = _clip_lines(a, b)
    else:
        for f in a:
            if f != "faces" and a[f] != b[f]:
                show = lambda v: _fmt(v) if isinstance(v, tuple) else v
                lines.append(f"{f} {show(a[f])} -> {show(b[f])}")
        if kind == "mesh" and a["faces"] != b["faces"]:
            found = _mesh_lines(entity_a.raw, entity_b.raw)
            lines += found or [f"faces +{sum((b['faces'] - a['faces']).values())}/"
                               f"-{sum((a['faces'] - b['faces']).values())} (now {sum(b['faces'].values())})"]
    return _cap(lines, full)


def summary(entity, full=False):
    """One part that is new in the file: enough to place it, everything with --full."""
    sig, raw = entity.sig, entity.raw
    if entity.kind == "mesh":
        points = list(raw["vertices"].values())
        low = [min(p[i] for p in points) for i in range(3)]
        high = [max(p[i] for p in points) for i in range(3)]
        lines = [f"{len(points)} vertices, {len(raw['faces'])} faces, origin {_fmt(sig['origin'])}, "
                 f"rotation {_fmt(sig['rotation'])}, local bounds {_fmt(low)} .. {_fmt(high)}"]
        if full:
            lines += [f"vertex {v}: {_fmt(p)}" for v, p in raw["vertices"].items()]
            lines += [f"face {k}: {' '.join(f['vertices'])}" for k, f in raw["faces"].items()]
        return lines
    if entity.kind == "clip":
        return [f"length {sig['length']}, loop {sig['loop']}, tracks: "
                + ", ".join(f"{k[0]}.{k[1]}" for k in sorted(sig["tracks"], key=str))]
    return ["; ".join(f"{f} {_fmt(v) if isinstance(v, tuple) else v}" for f, v in sig.items() if f != "parent")]

# ---------------------------------------------------------------- emitters
def _group_code(g):
    if effective_role(g) == "transform":
        return (f"builder.add_transform_group({g.name!r}, {g.parent!r}, pivot={_pt(g.pivot)!r}, "
                f"rotation={_pt(g.rotation)!r}{_tags(g.tags)})")
    return f"builder.add_group({g.name!r}, {g.parent!r}{_tags(g.tags)})"


def _socket_code(s):
    owner = f"bone:{s.parent}" if s.parent_kind == "bone" else s.parent
    offset = f", offset={_pt(s.offset)!r}" if any(s.offset) else ""
    return (f"builder.add_socket({s.name!r}, {owner!r}, at={_pt(s.position)!r}, "
            f"forward={_pt(s.forward)!r}, up={_pt(s.up)!r}{offset})")


def _armature_code(a):
    parent = f", parent={a.parent!r}" if a.parent else ""
    return f"builder.add_armature({a.name!r}{parent}{_tags(a.tags)})"


def _default_width(bone):
    return abs(bone.width - max(.25, bone.length * .2)) <= 1e-6


def bone_connected(builder, bone):
    """``connected`` as the geometry supports it: only a child starting at its parent's tip."""
    parent = builder._armature_bones.get(bone.parent) if bone.parent else None
    return bool(parent and bone.connected and math.dist(bone.start, parent.end) <= 1e-6)


def _chain_ok(builder, names):
    bones = [builder._armature_bones[n] for n in names]
    for index, bone in enumerate(bones):
        if not _default_width(bone) or bone.tags != bones[0].tags or bone.armature != bones[0].armature:
            return False
        if index and (bone.parent != bones[index - 1].name or not bone_connected(builder, bone)):
            return False
    return True


def _bone_lines(scene, bones):
    builder = scene.builder
    present = {b.name for b in bones}
    chain_at, chained = {}, set()
    for name, names in builder._armature_chains.items():
        if names and all(n in present for n in names) and _chain_ok(builder, names):
            chain_at[names[0]] = (name, names)
            chained.update(names)
    lines = []
    for entity in bones:
        bone = entity.raw
        handle = f"builder.armature({bone.armature!r})"
        if bone.name in chain_at:
            chain, names = chain_at[bone.name]
            members = [builder._armature_bones[n] for n in names]
            joints = (_pt(members[0].start), *[_pt(m.end) for m in members])
            lines.append(f"{handle}.add_chain({chain!r}, joints={joints!r}, names={tuple(names)!r}, "
                         f"parent={bone.parent!r}, connected={bone_connected(builder, bone)!r}{_tags(bone.tags)})")
        elif bone.name not in chained:
            extra = "" if bone.parent is None or bone_connected(builder, bone) else ", connected=False"
            extra += "" if _default_width(bone) else f", width={_num(bone.width, 9)!r}"
            parent = f", parent={bone.parent!r}" if bone.parent else ""
            lines.append(f"{handle}.add_bone({bone.name!r}, between=({_pt(bone.start)!r}, {_pt(bone.end)!r})"
                         f"{parent}{extra}{_tags(bone.tags)})")
    for name, names in builder._armature_chains.items():
        if names and all(n in present for n in names) and name not in {c for c, _ in chain_at.values()}:
            armature = builder._armature_bones[names[0]].armature
            lines.append(f"builder.armature({armature!r}).register_chain({name!r}, {tuple(names)!r})")
    return lines


def mesh_snippet(name, mesh, parent):
    """A MeshDraft that rebuilds ``mesh`` as saved (a closed one is oriented outward, like any closed draft)."""
    meta = mesh.get("model_as_code_mesh", {})
    closed = bool(meta.get("closed")) and _is_closed(mesh)
    lines = [
        f"draft = MeshDraft(closed={closed!r})",
        "for name, point in {",
        *[f"    {k!r}: {_vec(v)!r}," for k, v in mesh["vertices"].items()],
        "}.items():",
        "    draft.vertex(name, point)",
        "for name, order, group in (",
        *[f"    ({k!r}, {tuple(f['vertices'])!r}, {f.get('model_as_code_group')!r})," for k, f in mesh["faces"].items()],
        "):",
        "    draft.face(name, order, group=group)",
    ]
    lines += [f"draft.anchor({k!r}, {_vec(v)!r})" for k, v in meta.get("anchors", {}).items()]
    for ring_name, ring in meta.get("rings", {}).items():
        if all(vertex in mesh["vertices"] for vertex in ring):
            lines.append(f"draft.ring_of({ring_name!r}, {tuple(ring)!r})")
        else:
            lines.append(f"# ring {ring_name!r} lost vertices in Blockbench and is not recreated (bones that target it need another ring)")
    extra = ", allow_triangles=True" if any(len(f["vertices"]) == 3 for f in mesh["faces"].values()) else ""
    tags = mesh.get("model_as_code_tags", [])
    if tags:
        extra += f", tags={tags!r}"
    if mesh.get("shading", "flat") != "flat":
        extra += f", shading_mode={mesh['shading']!r}"
    if mesh.get("visibility") is False:
        extra += ", visibility=False"
    lines.append(f"builder.add_mesh({name!r}, {parent!r}, draft, origin={_vec(mesh['origin'])!r}, "
                 f"rotation={_vec(mesh.get('rotation', (0, 0, 0)))!r}{extra})")
    return "\n".join(lines)


def cube_snippet(name, cube, parent):
    lines = [
        "builder.add_cube(",
        f"    {name!r}, {parent!r}, from_={_vec(cube['from'])!r}, to_={_vec(cube['to'])!r},",
        f"    origin={_vec(cube['origin'])!r}, rotation={_vec(cube.get('rotation', (0, 0, 0)))!r},",
    ]
    if cube.get("inflate"):
        lines.append(f"    inflate={_num(cube['inflate'])!r},")
    if cube.get("stretch"):
        lines.append(f"    stretch={_vec(cube['stretch'])!r},")
    if cube.get("model_as_code_tags"):
        lines.append(f"    tags={cube['model_as_code_tags']!r},")
    if cube.get("shading_mode") is not None:
        lines.append(f"    shading_mode={cube['shading_mode']!r},")
    if cube.get("visibility") is False:
        lines.append("    visibility=False,")
    lines.append(")")
    return "\n".join(lines)


def _is_closed(mesh):
    """Watertight: every edge is shared by exactly two faces."""
    edges = Counter()
    for face in mesh["faces"].values():
        ring = list(face["vertices"])
        for a, b in zip(ring, ring[1:] + ring[:1]):
            edges[frozenset((a, b))] += 1
    return bool(edges) and all(count == 2 for count in edges.values())


def _mesh_blocker(scene, mode, entity):
    mesh = entity.raw
    try:
        check = ModelBuilder("check", require_integer_dimensions=False, check_coplanar=False)
        check.add_group("g")
        draft = MeshDraft(closed=bool(mesh.get("model_as_code_mesh", {}).get("closed")) and _is_closed(mesh))
        for k, v in mesh["vertices"].items():
            draft.vertex(k, v)
        for k, face in mesh["faces"].items():
            draft.face(k, face["vertices"])
        check.add_mesh(entity.name, "g", draft, origin=mesh["origin"], allow_triangles=True)
        errors = check.validate()["errors"]
    except ValueError as exc:
        return f"the builder rejects this geometry ({exc}): rebuild it in the recipe as close as the builder allows"
    if errors:
        return f"the builder rejects this mesh ({'; '.join(errors[:2])}): rebuild it in the recipe as close as the builder allows"
    return None


def _bind_code(scene, entity):
    mesh = scene.entities.get(("mesh", entity.name))
    if mesh is None:
        return None, f"weights of {entity.name!r} refer to a mesh that no longer exists"
    if mesh.parent not in {a.name for a in scene.builder._armatures.values()}:
        return None, f"{entity.name!r} has weights but is not under an armature"
    vertices = list(mesh.raw["vertices"])
    weights, missing = dict(entity.raw), [v for v in vertices if v not in entity.raw]
    if missing:
        if not weights:
            return None, f"{entity.name!r} has no weights at all"
        points = mesh.raw["vertices"]
        for v in missing:
            nearest = min(entity.raw, key=lambda w: math.dist(points[w], points[v]))
            weights[v] = entity.raw[nearest]
    influences = {tuple(sorted(w.items())) for w in weights.values()}
    handle = f"builder.armature({mesh.parent!r})"
    if len(influences) == 1:
        (only,) = influences
        if len(only) == 1 and abs(only[0][1] - 1.0) < 1e-6:
            return f"{handle}.bind({entity.name!r}, bone={only[0][0]!r})", None
    body = [f"    {v!r}: {dict(sorted(weights[v].items()))!r}," for v in vertices]
    note = (f"# {len(missing)} vertices had no weights: each takes the weights of its nearest weighted vertex\n"
            if missing else "")
    return note + "\n".join([f"{handle}.bind({entity.name!r}, weights={{", *body, "})"]), None


def clip_snippet(name, clip, controls):
    """Return (code, None), or (None, reason) when the animation API cannot express the clip."""
    if clip.get("loop") not in ("loop", "once", "hold"):
        return None, f"loop mode {clip.get('loop')!r} is not expressible"
    grouped = {}
    for uid, animator in clip.get("animators", {}).items():
        if uid == "effects":
            continue
        control = controls.get(uid)
        if control is None:
            return None, f"animator {animator.get('name')!r} is not an armature bone or transform group"
        same_named = [c for c in controls.values()
                      if (c.kind, c.name, c.armature) == (control.kind, control.name, control.armature)]
        target = (control.kind, control.name if len(same_named) == 1 else control.path, control.armature)
        for kf in animator.get("keyframes", []):
            points = kf.get("data_points", [])
            interpolation = INTERPOLATION.get(kf.get("interpolation", "linear"))
            if interpolation is None or len(points) != 1:
                return None, (f"{control.path} at {kf['time']}s uses "
                              f"{kf.get('interpolation')!r} interpolation or several data points")
            if any(not _numeric(points[0].get(a, 0)) for a in "xyz"):
                return None, f"{control.path} at {kf['time']}s uses expressions"
            grouped.setdefault(target, {}).setdefault((round(kf["time"], 4), interpolation), {})[
                kf["channel"]] = _vec(points[0].get(a, 0) for a in "xyz")
    variable = "CLIP_" + re.sub(r"\W", "_", name).upper()
    lines = [f"{variable} = {{"]
    for target, keys in grouped.items():
        lines.append(f"    {target!r}: [")
        for (time, interpolation), channels in sorted(keys.items()):
            ordered = {c: channels[c] for c in ("position", "rotation", "scale") if c in channels}
            lines.append(f"        ({time!r}, {interpolation!r}, {ordered!r}),")
        lines.append("    ],")
    lines += [
        "}",
        f"clip = editor.animation({name!r}, duration={_num(clip['length'])!r}, "
        f"loop={ {'loop': True, 'once': False, 'hold': 'hold'}[clip['loop']]!r})",
        f"for (kind, name, armature), keys in {variable}.items():",
        "    track = clip.bone(name, armature=armature) if kind == 'bone' else clip.group(name)",
        "    for time, interpolation, channels in keys:",
        "        track.key(time, interpolation=interpolation, **channels)",
    ]
    return "\n".join(lines), None


def emit(scene, keys, mode):
    """Code that recreates ``keys`` (in dependency order) plus the reasons some could not be emitted."""
    chosen = sorted((scene.entities[k] for k in keys if k in scene.entities),
                    key=lambda e: (KIND_ORDER[e.kind], scene.depth(e), e.order))
    lines, blockers, box_note, imported = [], [], False, False
    bones = [e for e in chosen if e.kind == "bone"]
    for entity in chosen:
        if entity.kind == "group":
            lines.append(_group_code(entity.raw))
        elif entity.kind == "armature":
            lines.append(_armature_code(entity.raw))
        elif entity.kind == "socket":
            lines.append(_socket_code(entity.raw))
        elif entity.kind == "cube":
            lines.append(cube_snippet(entity.name, entity.raw, entity.parent))
        elif entity.kind == "mesh":
            reason = _mesh_blocker(scene, mode, entity)
            if reason:
                blockers.append(f"{entity.name}: {reason}")
            else:
                if mode == "box" and not box_note:
                    box_note = True
                    lines.append("# NOTE: this model is in box mode; polygon meshes need "
                                 "ModelBuilder(..., modeling_mode='free') in the recipe")
                if not imported:
                    imported = True
                    lines.append("from lib import MeshDraft")
                lines.append(mesh_snippet(entity.name, entity.raw, entity.parent))
        elif entity.kind == "bind":
            code, reason = _bind_code(scene, entity)
            if reason:
                blockers.append(reason)
            else:
                lines.append(code)
        elif entity.kind == "clip":
            code, reason = clip_snippet(entity.name, entity.raw, scene.controls)
            if reason:
                blockers.append(f"{entity.name}: {reason}")
            else:
                lines.append(f"# clip {entity.name!r}\n{code}")
    if bones:
        position = next(i for i, e in enumerate(chosen) if e.kind == "bone")
        at = sum(1 for e in chosen[:position] if e.kind in ("group", "armature"))
        lines[at:at] = _bone_lines(scene, bones)
    return "\n".join(lines), blockers
