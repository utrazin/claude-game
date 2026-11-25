"""Rest-pose face tests for the builder's free-format cubes and quads.

Blockbench uses ZYX Euler matrices and absolute bind-space pivots. Apply
element rotation, then each ancestor rotation; never add Euler angles.
This checks the exported pose, not every possible animation frame.
"""
import math
from itertools import combinations, product

EPS = 1e-5


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def rotate(point, pivot, angles):
    x, y, z = sub(point, pivot)
    rx, ry, rz = map(math.radians, angles)
    y, z = math.cos(rx)*y-math.sin(rx)*z, math.sin(rx)*y+math.cos(rx)*z
    x, z = math.cos(ry)*x+math.sin(ry)*z, -math.sin(ry)*x+math.cos(ry)*z
    x, y = math.cos(rz)*x-math.sin(rz)*y, math.sin(rz)*x+math.cos(rz)*y
    return (x+pivot[0], y+pivot[1], z+pivot[2])


def world_point(builder, element, point):
    point = rotate(point, element.origin, element.rotation)
    if getattr(element, 'parent_kind', 'group') == 'armature':
        origin = builder._armatures[element.parent].origin
        return tuple(point[i] + origin[i] for i in range(3))
    parent = element.parent
    seen = set()
    while parent is not None:
        if parent in seen:
            raise ValueError('Group hierarchy cycle during geometry validation')
        seen.add(parent)
        bone = builder._groups[parent]
        point = rotate(point, bone.pivot, bone.rotation)
        parent = bone.parent
    return point


def faces_for(builder, element):
    """Return outward normal and cyclic world-space corners per face."""
    local_faces = []
    if element.kind == 'cube':
        bounds = builder._cube_bounds(element)
        axes = [(bounds[2*i], bounds[2*i+1]) for i in range(3)]
        for axis in range(3):
            u, v = (axis+1) % 3, (axis+2) % 3
            for side in (0, 1):
                points = []
                for su, sv in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    p = [0., 0., 0.]
                    p[axis], p[u], p[v] = axes[axis][side], axes[u][su], axes[v][sv]
                    points.append(p)
                if side == 0:
                    points.reverse()
                local_faces.append((('West', 'East', 'Down', 'Up', 'North', 'South')[axis*2+side], points))
    elif element.vertices:
        for face_name, face in element.faces.items():
            order = face.get('vertices', [])
            if len(order) not in (3, 4) or any(key not in element.vertices for key in order):
                continue
            points = [tuple(element.origin[i] + element.vertices[key][i] for i in range(3))
                      for key in order]
            local_faces.append((face_name, points))
    else:
        norm, plane, u1, u2, v1, v2 = builder._quad_face_info(element)
        axis = 'XYZ'.index(norm[-1])
        uv = [i for i in range(3) if i != axis]
        points = []
        for u, v in ((u1,v1), (u2,v1), (u2,v2), (u1,v2)):
            p = [0., 0., 0.]
            p[axis], p[uv[0]], p[uv[1]] = plane, u, v
            points.append(p)
        n = cross(sub(points[1], points[0]), sub(points[2], points[0]))
        if n[axis] * (1 if norm[0] == '+' else -1) < 0:
            points.reverse()
        local_faces.append(('quad', points))
    result = []
    for name, points in local_faces:
        points = [world_point(builder, element, p) for p in points]
        n = cross(sub(points[1], points[0]), sub(points[2], points[0]))
        length = math.sqrt(dot(n, n))
        if length > EPS:
            result.append((name, tuple(x/length for x in n), points))
    return result


def faces_overlap(a, b):
    _, normal, pa = a
    _, nb, pb = b
    if dot(normal, nb) < 1 - 1e-10:
        return False
    if any(abs(dot(normal, sub(p, pa[0]))) > EPS for p in pb):
        return False
    # Separating axes of the two convex polygons, within their common plane.
    # A shared edge or point alone has zero area and is allowed.
    for points in (pa, pb):
        for i in range(len(points)):
            axis = cross(normal, sub(points[(i+1) % len(points)], points[i]))
            length = math.sqrt(dot(axis, axis))
            axis = tuple(x/length for x in axis)
            aa, bb = [dot(p, axis) for p in pa], [dot(p, axis) for p in pb]
            if min(max(aa), max(bb)) - max(min(aa), min(bb)) <= EPS:
                return False
    return True


def contained(inner, outer):
    return all(dot(n, sub(p, corners[0])) <= EPS
               for _, _, vertices in inner for p in vertices
               for _, n, corners in outer)


def check_articulation_conflicts(builder):
    errors = []
    warnings = []
    for child_group in builder._groups.values():
        if child_group.parent is None or child_group.parent not in builder._groups:
            continue
        parent_group = builder._groups[child_group.parent]
        child_cubes = [e for e in builder._elements if e.parent == child_group.name and e.kind == 'cube']
        parent_cubes = [e for e in builder._elements if e.parent == parent_group.name and e.kind == 'cube']
        for p_cube, c_cube in product(parent_cubes, child_cubes):
            p_bounds = builder._cube_bounds(p_cube)
            c_bounds = builder._cube_bounds(c_cube)
            for k in range(3):
                abuts = (math.isclose(p_bounds[2 * k + 1], c_bounds[2 * k], abs_tol=EPS) or
                         math.isclose(p_bounds[2 * k], c_bounds[2 * k + 1], abs_tol=EPS))
                if not abuts:
                    continue
                u, v = (k + 1) % 3, (k + 2) % 3
                u_overlap = min(p_bounds[2 * u + 1], c_bounds[2 * u + 1]) - max(p_bounds[2 * u], c_bounds[2 * u]) > EPS
                v_overlap = min(p_bounds[2 * v + 1], c_bounds[2 * v + 1]) - max(p_bounds[2 * v], c_bounds[2 * v]) > EPS
                if not (u_overlap and v_overlap):
                    continue
                u_same = (math.isclose(p_bounds[2 * u], c_bounds[2 * u], abs_tol=EPS) and
                          math.isclose(p_bounds[2 * u + 1], c_bounds[2 * u + 1], abs_tol=EPS))
                v_same = (math.isclose(p_bounds[2 * v], c_bounds[2 * v], abs_tol=EPS) and
                          math.isclose(p_bounds[2 * v + 1], c_bounds[2 * v + 1], abs_tol=EPS))
                axis_name = 'XYZ'[k]
                if u_same and v_same:
                    errors.append(
                        f"Coplanar articulation conflict: '{p_cube.name}' (group '{parent_group.name}') and "
                        f"'{c_cube.name}' (group '{child_group.name}') share identical cross-section across joint "
                        f"along {axis_name} axis. Articulated segments must differentiate thickness to prevent Z-fighting: "
                        "make one part slightly larger or smaller in cross-section, or build with "
                        "ModelBuilder(..., check_coplanar=False) if the overlap is intended."
                    )
                elif u_same or v_same:
                    warnings.append(
                        f"Partial coplanar articulation warning: '{p_cube.name}' and '{c_cube.name}' share coplanar "
                        f"lateral walls across joint along {axis_name} axis."
                    )
    return errors, warnings


def check_geometry_conflicts(builder):
    errors = []
    warnings = []
    elements = [(e, faces_for(builder, e)) for e in builder._elements]
    for (a, fa), (b, fb) in combinations(elements, 2):
        for af, bf in product(fa, fb):
            if faces_overlap(af, bf):
                errors.append(f"Z-fighting coplanar face conflict between '{a.name}' ({af[0]}) and '{b.name}' ({bf[0]}) in exported pose")
        if a.kind == b.kind == 'cube' and math.isclose(a.inflate, b.inflate, abs_tol=EPS):
            ab, ba = contained(fa, fb), contained(fb, fa)
            if ab and ba:
                errors.append(f"Duplicate identical cube detected between '{a.name}' and '{b.name}'")
            elif ab or ba:
                inner, outer = (a, b) if ab else (b, a)
                errors.append(f"Element '{inner.name}' is completely submerged inside '{outer.name}' without visual protrusion")

    art_errors, art_warnings = check_articulation_conflicts(builder)
    errors.extend(art_errors)
    warnings.extend(art_warnings)
    return errors, warnings
