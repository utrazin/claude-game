"""
Model Inspector CLI.

Fast, token-efficient inspection of Blockbench .bbmodel files for developers and LLM agents.
Provides executive summaries, ASCII hierarchy trees, element lookups, and geometry validation.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


from lib.geometry_validation import faces_for
from lib.model_builder import ModelBuilder
from Tools.low_poly_audit import audit_low_poly
from Tools._resolve import resolve_read_model


def calculate_bounding_box(builder: ModelBuilder) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Calculates rest-pose world bounding box (min_coords, max_coords)."""
    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    has_geometry = False
    for element in builder._elements:
        for _name, _norm, points in faces_for(builder, element):
            has_geometry = True
            for x, y, z in points:
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
                if z < min_z:
                    min_z = z
                if z > max_z:
                    max_z = z

    if not has_geometry:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)

    return (min_x, min_y, min_z), (max_x, max_y, max_z)


def inspect_summary(data: dict[str, Any], builder: ModelBuilder) -> dict[str, Any]:
    """Generates an executive summary dictionary."""
    name = data.get("name", "unnamed")
    meta = data.get("meta", {})
    model_format = meta.get("model_format", "free")
    res = data.get("resolution", {})
    tex_w = res.get("width", 0)
    tex_h = res.get("height", 0)

    cubes = [e for e in builder._elements if e.kind == "cube"]
    meshes = [e for e in builder._elements if e.kind == "mesh"]
    polygon_meshes = [e for e in meshes if e.vertices]

    bmin, bmax = calculate_bounding_box(builder)
    dx = round(bmax[0] - bmin[0], 4)
    dy = round(bmax[1] - bmin[1], 4)
    dz = round(bmax[2] - bmin[2], 4)

    mac = data.get("unhandled_root_fields", {}).get("model_as_code", {})
    uv_ready = mac.get("uv_ready")
    uv_packing = mac.get("uv_packing", {})

    textures = data.get("textures", [])
    validation = builder.validate()
    spatial = builder.spatial_summary()
    if uv_ready:
        try:
            from Tools.TexturePainter.core.bbmodel_parser import BlockbenchModelParser
            BlockbenchModelParser.from_document(data)
            uv_status = "READY"
        except ValueError:
            uv_status = "INVALID"
    else:
        uv_status = "PENDING"
    tag_counts = {}
    for item in [*builder._groups.values(), *builder._armatures.values(),
                 *builder._armature_bones.values(), *builder._elements]:
        for tag in item.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    return {
        "name": name,
        "format": model_format,
        "modeling_mode": mac.get("modeling_mode", "free"),
        "validation_policy": mac.get("validation_policy", {"check_coplanar": True}),
        "orientation": mac.get("orientation", {"up": "+Y", "front": "+Z"}),
        "resolution": f"{tex_w}x{tex_h}",
        "bounding_box": {
            "min": [round(bmin[0], 2), round(bmin[1], 2), round(bmin[2], 2)],
            "max": [round(bmax[0], 2), round(bmax[1], 2), round(bmax[2], 2)],
            "size": [dx, dy, dz],
        },
        "groups_count": len(builder._groups),
        "armatures_count": len(builder._armatures),
        "armature_bones_count": len(builder._armature_bones),
        "skinned_meshes_count": len(builder._bindings),
        "weighted_vertices_count": sum(len(weights) for weights in builder._bindings.values()),
        "unweighted_vertices_count": sum(
            len(element.vertices) - len(builder._bindings.get(element.name, {}))
            for element in polygon_meshes if element.parent_kind == "armature"
        ),
        "maximum_influences": max(
            (len(influences) for weights in builder._bindings.values()
             for influences in weights.values()), default=0
        ),
        "elements_count": len(builder._elements),
        "cubes_count": len(cubes),
        "meshes_count": len(meshes),
        "polygon_meshes_count": len(polygon_meshes),
        "mesh_vertices_count": sum(len(e.vertices) for e in polygon_meshes),
        "mesh_faces_count": sum(len(e.faces) for e in polygon_meshes),
        "mesh_primitives": sorted({e.primitive for e in polygon_meshes if e.primitive}),
        "uv_status": uv_status,
        "uv_scale": uv_packing.get("uv_scale", 1),
        "tags": dict(sorted(tag_counts.items())),
        "textures": [
            {
                "name": t.get("name"),
                "size": f"{t.get('uv_width', tex_w)}x{t.get('uv_height', tex_h)}",
                "render_sides": t.get("render_sides", "auto"),
            }
            for t in textures
        ],
        "errors_count": len(validation["errors"]),
        "warnings_count": len(validation["warnings"]),
        "spatial": spatial,
    }


def print_summary(summary: dict[str, Any]) -> None:
    bb = summary["bounding_box"]
    tex_str = (
        ", ".join(f"{t['name']} ({t['size']}, {t['render_sides']})" for t in summary["textures"])
        if summary["textures"]
        else "none"
    )
    val_status = "OK" if summary["errors_count"] == 0 else f"FAIL ({summary['errors_count']} errors)"
    if summary["warnings_count"] > 0:
        val_status += f" [{summary['warnings_count']} warnings]"

    print(f"=== Model Summary: {summary['name']} ===")
    print(f"Format: {summary['format']} | Resolution: {summary['resolution']}")
    print(f"Bounds: X: [{bb['min'][0]}..{bb['max'][0]}], Y: [{bb['min'][1]}..{bb['max'][1]}], Z: [{bb['min'][2]}..{bb['max'][2]}] (Size: {bb['size'][0]} x {bb['size'][1]} x {bb['size'][2]})")
    print(f"Hierarchy: {summary['groups_count']} groups, {summary['armatures_count']} armatures, "
          f"{summary['armature_bones_count']} armature bones, {summary['elements_count']} elements "
          f"({summary['cubes_count']} cubes, {summary['meshes_count']} meshes)")
    if summary["armatures_count"]:
        print(f"Skinning: {summary['skinned_meshes_count']} meshes, "
              f"{summary['weighted_vertices_count']} weighted vertices, "
              f"{summary['unweighted_vertices_count']} unweighted, "
              f"max {summary['maximum_influences']} influences")
    if summary.get("polygon_meshes_count"):
        print(f"Topology: {summary['polygon_meshes_count']} polygon meshes, {summary['mesh_vertices_count']} vertices, "
              f"{summary['mesh_faces_count']} faces; primitives: {', '.join(summary['mesh_primitives']) or 'custom'}")
    spatial=summary.get("spatial",{})
    if any(spatial.get(key,0) for key in ("anchors","frames","sockets")):
        print(f"Spatial: {spatial.get('anchors',0)} anchors, {spatial.get('frames',0)} frames, "
              f"{spatial.get('sockets',0)} sockets, {spatial.get('chains',0)} chains")
    print(f"UV Status: {summary['uv_status']} (scale: {summary['uv_scale']} px/unit)")
    if summary["tags"]:
        print("Tags: " + ", ".join(f"{tag} ({count})" for tag, count in summary["tags"].items()))
    print(f"Textures ({len(summary['textures'])}): {tex_str}")
    print(f"Validation: {val_status}")


def build_tree_ascii(builder: ModelBuilder) -> str:
    """Generates an ASCII hierarchy tree of groups, armatures and elements."""
    children_map: dict[str | None, list[str]] = {}
    elements_per_group: dict[str, list[Any]] = {}

    for name, group in builder._groups.items():
        children_map.setdefault(group.parent, []).append(name)
        elements_per_group[name] = []

    for element in builder._elements:
        if element.parent in elements_per_group:
            elements_per_group[element.parent].append(element)

    lines: list[str] = []

    def render_node(group_name: str, prefix: str = "", is_last: bool = True) -> None:
        group = builder._groups[group_name]
        elems = elements_per_group.get(group_name, [])
        cubes = sum(1 for e in elems if e.kind == "cube")
        meshes = sum(1 for e in elems if e.kind == "mesh")

        elem_desc = []
        if cubes:
            elem_desc.append(f"{cubes} cube{'s' if cubes > 1 else ''}")
        if meshes:
            elem_desc.append(f"{meshes} mesh{'es' if meshes > 1 else ''}")
        elem_str = f" [{', '.join(elem_desc)}]" if elem_desc else ""

        p = [round(v, 2) for v in group.pivot]
        r = [round(v, 2) for v in group.rotation]
        rot_str = f", rot: {r}" if any(r) else ""

        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{group_name} (pivot: {p}{rot_str}){elem_str}")

        next_prefix = prefix + ("    " if is_last else "│   ")
        sub_groups = children_map.get(group_name, [])
        for i, sub_name in enumerate(sub_groups):
            render_node(sub_name, next_prefix, i == len(sub_groups) - 1)

    roots = children_map.get(None, [])
    if not roots:
        roots = list(builder._groups.keys())[:1]

    for i, root in enumerate(roots):
        render_node(root, "", i == len(roots) - 1)

    for armature_name, armature in builder._armatures.items():
        if lines:
            lines.append("")
        lines.append(f"Armature {armature_name} (origin: {[round(v, 2) for v in armature.origin]})")
        armature_meshes = sorted(
            element.name for element in builder._elements
            if element.parent_kind == "armature" and element.parent == armature_name
        )
        for mesh_name in armature_meshes:
            weighted = len(builder._bindings.get(mesh_name, {}))
            lines.append(f"├── mesh {mesh_name} ({weighted} weighted vertices)")
        bone_children = {}
        for bone in builder._armature_bones.values():
            if bone.armature == armature_name:
                bone_children.setdefault(bone.parent, []).append(bone.name)
        def render_armature_bone(name, prefix="", last=True):
            bone = builder._armature_bones[name]
            lines.append(f"{prefix}{'└── ' if last else '├── '}bone {name} "
                         f"(length: {bone.length:g}, connected: {bone.connected})")
            children = sorted(bone_children.get(name, []))
            for index, child in enumerate(children):
                render_armature_bone(child, prefix + ("    " if last else "│   "),
                                     index == len(children) - 1)
        roots_for_armature = sorted(bone_children.get(None, []))
        for index, bone_name in enumerate(roots_for_armature):
            render_armature_bone(bone_name, "", index == len(roots_for_armature) - 1)

    return "\n".join(lines)


def inspect_element(builder: ModelBuilder, target_name: str, *, include_faces=False,
                    face_name=None) -> dict[str, Any] | None:
    """Finds an element by name (exact or case-insensitive) and returns detailed data."""
    matched = None
    for elem in builder._elements:
        if elem.name == target_name:
            matched = elem
            break
    if not matched:
        for elem in builder._elements:
            if elem.name.lower() == target_name.lower():
                matched = elem
                break

    if not matched:
        return None

    size = (
        [round(matched.to_[i] - matched.from_[i], 2) for i in range(3)]
        if matched.kind == "cube" and matched.to_ is not None
        else list(matched.size or [1, 1])
    )

    faces = {}
    if include_faces or face_name:
        faces = matched.faces
        if face_name:
            matches = {name: face for name, face in faces.items()
                       if name.lower() == face_name.lower()}
            if not matches:
                return None
            faces = matches
    return {
        "name": matched.name,
        "kind": matched.kind,
        "parent_group": matched.parent if matched.parent_kind == "group" else None,
        "parent_armature": matched.parent if matched.parent_kind == "armature" else None,
        "parent_kind": matched.parent_kind,
        "from": list(matched.from_),
        "to": list(matched.to_) if matched.to_ else None,
        "size": size,
        "origin": list(matched.origin),
        "rotation": list(matched.rotation),
        "inflate": matched.inflate,
        "visibility": matched.visibility,
        "tags": list(matched.tags),
        "face_count": len(matched.faces),
        "faces": faces,
    }


def print_element(info: dict[str, Any]) -> None:
    print(f"=== Element: {info['name']} ({info['kind']}) ===")
    parent = info["parent_group"] or info["parent_armature"] or "none"
    print(f"Parent: {parent}")
    print(f"Position: from={info['from']}, to={info['to']} | Size={info['size']}")
    print(f"Origin (Pivot): {info['origin']} | Rotation: {info['rotation']} | Inflate: {info['inflate']}")
    if info["tags"]:
        print(f"Tags: {info['tags']}")
    print(f"Faces: {info['face_count']}")
    faces = info.get("faces", {})
    for face_name, face_data in faces.items():
        uv = face_data.get("uv", [])
        rot = face_data.get("rotation", 0)
        tex = face_data.get("texture", False)
        print(f"  - {face_name:<6}: UV={uv}, rot={rot}, texture_slot={tex}")


def inspect_tag(builder: ModelBuilder, tag: str) -> dict[str, list[str]]:
    return {
        "groups": [group.name for group in builder._groups.values() if tag in group.tags],
        "elements": [element.name for element in builder._elements if tag in element.tags],
    }


def inspect_group(builder: ModelBuilder, group_name: str) -> dict[str, Any] | None:
    """Finds a rigid group by name and returns its hierarchy and elements."""
    group = None
    for name, b in builder._groups.items():
        if name.lower() == group_name.lower():
            group = b
            break
    if not group:
        return None

    children_groups = [name for name, b in builder._groups.items() if b.parent == group.name]
    elements = [e.name for e in builder._elements if e.parent == group.name]

    return {
        "name": group.name,
        "parent": group.parent,
        "pivot": list(group.pivot),
        "rotation": list(group.rotation),
        "tags": group.tags,
        "children_groups": children_groups,
        "elements": elements,
    }


def print_group(info: dict[str, Any]) -> None:
    print(f"=== Group: {info['name']} ===")
    print(f"Parent: {info['parent'] or 'None (root)'}")
    print(f"Pivot: {info['pivot']} | Rotation: {info['rotation']}")
    if info["tags"]:
        print(f"Tags: {info['tags']}")
    print(f"Children Groups ({len(info['children_groups'])}): {', '.join(info['children_groups']) or 'none'}")
    print(f"Contained Elements ({len(info['elements'])}): {', '.join(info['elements']) or 'none'}")


def print_examples(items, prefix, limit=8):
    for item in items[:limit]:
        print(f"  [{prefix}] {item}")
    if len(items) > limit:
        print(f"  ... {len(items) - limit} more; use --json for complete output")


def print_low_poly_audit(report):
    print("=== Low-Poly Audit (heuristic; does not invalidate geometry) ===")
    budget = report["face_budget"]
    suffix = f" / budget {budget}" if budget is not None else ""
    print(f"Faces: {report['total_faces']}{suffix}")
    for element in report["elements"]:
        print(f"  {element['name']}: {element['faces']} faces, {element['vertices']} vertices, "
              f"{len(element['rings'])} rings, {element['components']} shell(s)")
    if report["warnings"]:
        print_examples(report["warnings"], "WARN")
    else:
        print("No heuristic warnings.")


def print_skinning_audit(report):
    print("=== Skinning Audit (diagnostic; does not invalidate geometry) ===")
    for mesh in report["meshes"]:
        mode=mesh.get("mode") or ("rigid" if mesh["rigid"] else "deformable")
        dominant=", ".join(f"{name}:{count}" for name,count in mesh["dominant_bones"].items())
        print(f"  {mesh['mesh']}: {mode}, {mesh['vertices']} vertices, dominant [{dominant}], "
              f"leakage {mesh['leaked_vertices']}")
    if report["warnings"]:
        print_examples(report["warnings"], "WARN")
    else:
        print("No suspicious non-local weights.")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Blockbench Model Inspector CLI")
    parser.add_argument("bbmodel", help="Path to .bbmodel file")
    parser.add_argument("--summary", action="store_true", help="Show compact executive summary (default)")
    parser.add_argument("--tree", action="store_true", help="Display ASCII group/armature hierarchy tree")
    parser.add_argument("--element", metavar="NAME", help="Inspect a specific element in detail")
    parser.add_argument("--face", metavar="NAME", help="Include one face/UV; requires --element")
    parser.add_argument("--group", metavar="NAME", help="Inspect a specific rigid group in detail")
    parser.add_argument("--tag", metavar="TAG", help="List groups/elements carrying one explicit tag")
    parser.add_argument("--check", "--validate", action="store_true", help="Run anti-coplanar, integer size and grid validations")
    parser.add_argument("--low-poly-audit", action="store_true", help="Run non-blocking low-poly diagnostics")
    parser.add_argument("--skinning-audit", action="store_true", help="Run non-blocking armature-weight diagnostics")
    parser.add_argument("--face-budget", type=int, metavar="N", help="Optional face budget for --low-poly-audit")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args(argv)
    if args.face and not args.element:
        parser.error("--face requires --element")
    _, model_path = resolve_read_model(args.bbmodel)

    if not model_path.exists():
        print(f"Error: File '{args.bbmodel}' not found.", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(model_path.read_text(encoding="utf-8"))
        builder = ModelBuilder.from_bbmodel_data(data)
    except Exception as e:
        print(f"Error parsing .bbmodel: {e}", file=sys.stderr)
        sys.exit(1)

    if args.face_budget is not None and not args.low_poly_audit:
        parser.error("--face-budget requires --low-poly-audit")
    has_action = (args.tree or args.element or args.group or args.tag or args.check or
                  args.low_poly_audit or args.skinning_audit or args.summary)
    show_summary = args.summary or not has_action

    if args.json:
        result: dict[str, Any] = {}
        if show_summary:
            result["summary"] = inspect_summary(data, builder)
        if args.tree:
            result["tree"] = build_tree_ascii(builder)
        if args.element:
            elem_data = inspect_element(builder, args.element, face_name=args.face)
            if not elem_data:
                print(f"Error: Element '{args.element}' not found.", file=sys.stderr)
                sys.exit(1)
            result["element"] = elem_data
        if args.tag:
            result["tag"] = {"name": args.tag, **inspect_tag(builder, args.tag)}
        if args.group:
            group_data = inspect_group(builder, args.group)
            if not group_data:
                print(f"Error: Group '{args.group}' not found.", file=sys.stderr)
                sys.exit(1)
            result["group"] = group_data
        if args.check:
            result["validation"] = builder.validate()
        if args.low_poly_audit:
            result["low_poly_audit"] = audit_low_poly(builder, face_budget=args.face_budget)
        if args.skinning_audit:
            result["skinning_audit"] = builder.skinning_audit()
        print(json.dumps(result, indent=2))
        if args.check and result["validation"]["errors"]:
            sys.exit(2)
        return

    if show_summary:
        print_summary(inspect_summary(data, builder))

    if args.tree:
        if show_summary:
            print()
        print("=== Hierarchy Tree ===")
        print(build_tree_ascii(builder))

    if args.element:
        elem_data = inspect_element(builder, args.element, face_name=args.face)
        if not elem_data:
            print(f"Error: Element '{args.element}' not found in model.", file=sys.stderr)
            sys.exit(1)
        if show_summary or args.tree:
            print()
        print_element(elem_data)

    if args.tag:
        info = inspect_tag(builder, args.tag)
        if show_summary or args.tree or args.element:
            print()
        print(f"=== Tag: {args.tag} ===")
        print(f"Groups ({len(info['groups'])}): {', '.join(info['groups']) or 'none'}")
        print(f"Elements ({len(info['elements'])}): {', '.join(info['elements']) or 'none'}")

    if args.group:
        group_data = inspect_group(builder, args.group)
        if not group_data:
            print(f"Error: Group '{args.group}' not found in model.", file=sys.stderr)
            sys.exit(1)
        if show_summary or args.tree or args.element:
            print()
        print_group(group_data)

    if args.check:
        if show_summary or args.tree or args.element or args.group or args.tag:
            print()
        print("=== Geometry & Integrity Validation ===")
        val = builder.validate()
        if not val["errors"] and not val["warnings"]:
            print("Validation PASSED! 0 errors, 0 warnings.")
        else:
            if val["errors"]:
                print(f"ERRORS ({len(val['errors'])}):")
                print_examples(val["errors"], "ERROR")
            if val["warnings"]:
                print(f"WARNINGS ({len(val['warnings'])}):")
                print_examples(val["warnings"], "WARN")
        if val["errors"]:
            sys.exit(2)

    if args.low_poly_audit:
        if show_summary or args.tree or args.element or args.group or args.tag or args.check:
            print()
        print_low_poly_audit(audit_low_poly(builder, face_budget=args.face_budget))

    if args.skinning_audit:
        if show_summary or args.tree or args.element or args.group or args.tag or args.check or args.low_poly_audit:
            print()
        print_skinning_audit(builder.skinning_audit())


if __name__ == "__main__":
    main()
