"""UV rules: per-region packing choices stored in the BBModel (``model_as_code.uv_packing.rules``).

A rule selects faces and sets attributes. For every face the last matching rule wins, attribute by attribute;
unset attributes keep the document defaults (``uv_scale``, ``layout``). Without rules every face takes the defaults
and packing is exactly the automatic one.

Selectors (all optional, glob patterns, combined with AND): ``element`` (element name), ``tag``
(``model_as_code_tags``), ``parent`` (any outliner group above the element), ``face`` (face name) and
``face_group`` (``model_as_code_group`` of a mesh face).

Attributes:

* ``density``: pixels per model unit for these faces (positive integer), in place of ``uv_scale``;
* ``layout``: ``box`` (cube cross), ``faces`` (one island per face), ``charts`` (mesh faces unfolded on one texel
  grid), ``flat`` (faces share one small island: one colour) or ``fixed`` (each face gets exactly ``size`` pixels);
* ``per``: for ``flat``, which faces share an island: ``face``, ``element`` (default) or ``rule`` (every face the
  rule selects);
* ``size``: ``[w, h]`` pixels of a ``flat`` (default ``[1, 1]``) or ``fixed`` island;
* ``pin``: ``[u, v]`` atlas position of the island the faces form (exactly one island);
* ``block``: name of the block the ``grouped`` packer keeps these islands in (default: the element's parent group);
* ``texture``: name of the texture atlas slot these faces are packed into (default: ``default``).
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass

LAYOUTS = ("box", "faces", "charts", "flat", "fixed")
PER = ("face", "element", "rule")
SELECTORS = ("element", "tag", "parent", "face", "face_group")
ATTRIBUTES = ("density", "layout", "per", "size", "pin", "block", "texture")
CUBE_FACES = ("north", "south", "east", "west", "up", "down")


@dataclass(frozen=True)
class FaceSpec:
    """Resolved packing choices of one face."""
    layout: str
    density: int
    per: str = "element"
    size: tuple | None = None
    pin: tuple | None = None
    block: str | None = None
    flat_rule: int | None = None          # index of the rule that made the face flat (``per="rule"``)
    texture: str = "default"


def _pair(value, label, minimum):
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) or v < minimum for v in value)):
        raise ValueError(f"UV rule {label} must be two integers >= {minimum}")
    return tuple(value)


def validate_rules(rules):
    """Return the rules as plain dicts; reject unknown keys and invalid values."""
    if rules is None:
        return []
    if not isinstance(rules, list):
        raise ValueError("uv_packing.rules must be a list")
    clean = []
    for number, rule in enumerate(rules):
        if not isinstance(rule, dict) or not isinstance(rule.get("select", {}), dict):
            raise ValueError(f"UV rule {number}: expected {{'select': {{...}}, attribute: value}}")
        select = rule.get("select", {})
        unknown = set(select) - set(SELECTORS)
        if unknown:
            raise ValueError(f"UV rule {number}: unknown selector {sorted(unknown)}; use {', '.join(SELECTORS)}")
        if any(not isinstance(v, str) or not v for v in select.values()):
            raise ValueError(f"UV rule {number}: selectors are non-empty strings")
        unknown = set(rule) - {"select", *ATTRIBUTES}
        if unknown:
            raise ValueError(f"UV rule {number}: unknown attribute {sorted(unknown)}; use {', '.join(ATTRIBUTES)}")
        if not set(rule) & set(ATTRIBUTES):
            raise ValueError(f"UV rule {number}: sets no attribute")
        if "density" in rule and (isinstance(rule["density"], bool) or not isinstance(rule["density"], int)
                                  or rule["density"] < 1):
            raise ValueError(f"UV rule {number}: density must be a positive integer (pixels per model unit)")
        if "layout" in rule and rule["layout"] not in LAYOUTS:
            raise ValueError(f"UV rule {number}: layout must be one of {', '.join(LAYOUTS)}")
        if "per" in rule and rule["per"] not in PER:
            raise ValueError(f"UV rule {number}: per must be one of {', '.join(PER)}")
        if "size" in rule:
            _pair(rule["size"], f"{number} size", 1)
        if "pin" in rule:
            _pair(rule["pin"], f"{number} pin", 0)
        if "block" in rule and (not isinstance(rule["block"], str) or not rule["block"]):
            raise ValueError(f"UV rule {number}: block must be a non-empty string")
        if "texture" in rule:
            from .project_manifest import identifier
            try:
                identifier(rule["texture"])
            except ValueError as exc:
                raise ValueError(f"UV rule {number}: texture must be a valid identifier ({exc})") from exc
        clean.append(rule)
    return clean


def element_parents(data):
    """Element uuid -> names of every outliner group above it."""
    names = {group.get("uuid"): group.get("name") for group in data.get("groups", []) if isinstance(group, dict)}
    parents = {}

    def walk(children, chain):
        for child in children or ():
            if isinstance(child, dict):
                walk(child.get("children"), chain + (child.get("name") or names.get(child.get("uuid")),))
            else:
                parents[child] = chain
    walk(data.get("outliner"), ())
    return parents


def textured_faces(elem):
    """Face names of an element that take texture (disabled faces excluded)."""
    if elem.get("type", "cube") == "cube":
        faces = elem.get("faces", {})
        return [name for name in CUBE_FACES if faces.get(name, {}).get("texture", False) is not None]
    return [name for name, face in (elem.get("faces") or {}).items()
            if not ("texture" in face and face["texture"] is None)]


def _matches(select, elem, face_name, chain):
    if "element" in select and not fnmatch.fnmatchcase(elem.get("name", ""), select["element"]):
        return False
    if "tag" in select and not any(fnmatch.fnmatchcase(tag, select["tag"])
                                   for tag in elem.get("model_as_code_tags", ())):
        return False
    if "parent" in select and not any(name and fnmatch.fnmatchcase(name, select["parent"]) for name in chain):
        return False
    if "face" in select and not fnmatch.fnmatchcase(face_name, select["face"]):
        return False
    if "face_group" in select:
        group = (elem.get("faces", {}).get(face_name) or {}).get("model_as_code_group") or ""
        if not fnmatch.fnmatchcase(group, select["face_group"]):
            return False
    return True


def resolve_specs(data, rules, *, uv_scale, layout):
    """FaceSpec of every textured face, keyed by (element name, face name).

    ``layout`` is the document layout for meshes (``faces`` or ``charts``); cubes default to ``box``."""
    rules = validate_rules(rules)
    parents = element_parents(data)
    specs, hits = {}, [0] * len(rules)
    for elem in data.get("elements", []):
        kind = elem.get("type", "cube")
        if kind not in ("cube", "mesh"):
            continue
        chain = parents.get(elem.get("uuid"), ())
        for face_name in textured_faces(elem):
            values = dict(layout="box" if kind == "cube" else layout, density=uv_scale, per="element",
                          size=None, pin=None, block=chain[-1] if chain else None, flat_rule=None,
                          texture="default")
            for number, rule in enumerate(rules):
                if not _matches(rule.get("select", {}), elem, face_name, chain):
                    continue
                hits[number] += 1
                for key in ATTRIBUTES:
                    if key in rule:
                        values[key] = tuple(rule[key]) if key in ("size", "pin") else rule[key]
                if rule.get("layout") == "flat":
                    values["flat_rule"] = number
            ref = (elem["name"], face_name)
            if kind == "cube" and values["layout"] == "charts":
                raise ValueError(f"{ref}: the charts layout unfolds mesh faces; a cube face takes box, faces, "
                                 "flat or fixed")
            if kind == "mesh" and values["layout"] == "box":
                raise ValueError(f"{ref}: the box layout is the cube cross; a mesh face takes faces, charts, "
                                 "flat or fixed")
            if values["layout"] == "fixed" and values["size"] is None:
                raise ValueError(f"{ref}: the fixed layout needs size=[w, h] in pixels")
            if values["layout"] == "flat" and values["size"] is None:
                values["size"] = (1, 1)
            specs[ref] = FaceSpec(**values)
    unused = [number for number, count in enumerate(hits) if not count]
    if unused:
        raise ValueError(f"UV rule {unused[0]} selects no textured face: {rules[unused[0]].get('select', {})}")
    return specs


def ordered_textures(specs, rules=()):
    """Deterministic slot order of the textures used by ``specs``: ``default`` first when any face keeps it,
    then each texture name in the order the rules (and ``specs``) introduce it."""
    used = {spec.texture for spec in specs.values()}
    if not used:
        return ["default"]
    order = ["default"] if "default" in used else []
    for name in [r.get("texture") for r in (rules or ()) if "texture" in r] + [s.texture for s in specs.values()]:
        if name in used and name not in order:
            order.append(name)
    return order
