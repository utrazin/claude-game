"""Schema and topology validation for canonical mesh elements."""

from __future__ import annotations
from collections import Counter
import math

EPS = 1e-8
_ORIENT_HINT = ("neighbouring faces must run a shared edge in opposite directions and point "
                "outward; build closed meshes through MeshDraft(closed=True), which orients faces "
                "on build(), or call draft.orient_outward()")


def _sub(a,b): return tuple(a[i]-b[i] for i in range(3))
def _cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _dot(a,b): return sum(a[i]*b[i] for i in range(3))


def _validate_mesh_elements_base(elements):
    errors, warnings = [], []
    for element in elements:
        if element.kind != "mesh" or not element.vertices:
            continue
        vertices, edge_uses = element.vertices, Counter()
        oriented = Counter()
        signed_volume = 0.0
        face_sets = Counter()
        for face_name, face in element.faces.items():
            order = tuple(face.get("vertices", ()))
            label = f"Mesh {element.name!r} face {face_name!r}"
            if len(order) not in (3, 4):
                errors.append(f"{label} must contain exactly three or four vertices")
                continue
            if len(set(order)) != len(order):
                errors.append(f"{label} repeats a vertex")
                continue
            if any(key not in vertices for key in order):
                errors.append(f"{label} references a missing vertex")
                continue
            face_sets[frozenset(order)] += 1
            points=[vertices[k] for k in order]
            normal=tuple(sum((a[(i+1)%3]-b[(i+1)%3])*(a[(i+2)%3]+b[(i+2)%3])
                             for a,b in zip(points,points[1:]+points[:1])) for i in range(3))
            length = math.sqrt(_dot(normal,normal))
            if length <= EPS:
                errors.append(f"{label} is degenerate: it has zero area (collinear or repeated corners)")
                continue
            unit = tuple(v/length for v in normal)
            p0=points[0]
            axes=[i for i in range(3) if i != max(range(3),key=lambda i:abs(normal[i]))]
            try:
                from .polygon_math import validate_contour
                validate_contour(tuple((point[axes[0]],point[axes[1]]) for point in points))
            except ValueError as exc:
                errors.append(f"{label} has invalid contour: {exc}")
            for i in range(1,len(order)-1):
                a,b,c=(vertices[k] for k in (order[0],order[i],order[i+1]))
                signed_volume += (a[0]*(b[1]*c[2]-b[2]*c[1]) -
                                  a[1]*(b[0]*c[2]-b[2]*c[0]) +
                                  a[2]*(b[0]*c[1]-b[1]*c[0]))/6
            for a,b in zip(order, order[1:]+order[:1]):
                if math.dist(vertices[a],vertices[b]) <= EPS:
                    errors.append(f"{label} contains a zero-length edge")
                edge_uses[tuple(sorted((a,b)))] += 1
                oriented[a,b] += 1
        duplicate = [edge for edge,count in edge_uses.items() if count > 2]
        if duplicate: errors.append(f"Mesh {element.name!r} has non-manifold edges: {duplicate[:3]}")
        if any(count > 1 for count in face_sets.values()):
            errors.append(f"Mesh {element.name!r} contains duplicate or reversed duplicate faces")
        boundary = [edge for edge,count in edge_uses.items() if count == 1]
        if element.mesh_closed and boundary:
            errors.append(f"Mesh {element.name!r} is marked closed but has {len(boundary)} boundary edges")
        elif element.mesh_closed and signed_volume <= EPS:
            errors.append(f"Mesh {element.name!r} has inward or zero-volume winding: {_ORIENT_HINT}")
        elif boundary:
            warnings.append(f"Open mesh {element.name!r} has {len(boundary)} boundary edges")
        bad_edges = [(a,b) for a,b in edge_uses if edge_uses[a,b] == 2 and oriented[a,b] != 1]
        if bad_edges:
            faces_by_edge = {}
            for face_name, face in element.faces.items():
                order = tuple(face.get("vertices", ()))
                for a,b in zip(order, order[1:]+order[:1]):
                    faces_by_edge.setdefault(tuple(sorted((a,b))), []).append(face_name)
            examples = "; ".join(f"faces {faces_by_edge.get(edge, ['?'])} share edge {edge} in the same direction"
                                 for edge in bad_edges[:3])
            errors.append(f"Mesh {element.name!r} has inconsistent winding across {len(bad_edges)} "
                          f"edge(s) ({examples}): {_ORIENT_HINT}")
    return errors, warnings


def validate_geometry(geometry, *, check_intersections=False, name='geometry'):
    """Pure mesh validation, independent of builder and serialized UV data."""
    from types import SimpleNamespace
    if not geometry.vertices or not geometry.faces:
        return [f'Mesh {name!r} must have vertices and faces'],[]
    element=SimpleNamespace(kind='mesh',name=name,vertices=geometry.vertices,
                            faces={k:{'vertices':f.vertices} for k,f in geometry.faces.items()},
                            mesh_closed=geometry.closed)
    errors,warnings=_validate_mesh_elements_base([element])
    if errors: return errors,warnings
    # Closedness and outward orientation apply to each connected component.
    edge_faces={}
    for key,f in geometry.faces.items():
        for a,b in zip(f.vertices,f.vertices[1:]+f.vertices[:1]):
            edge_faces.setdefault(frozenset((a,b)),[]).append(key)
    neighbors={k:set() for k in geometry.faces}
    for refs in edge_faces.values():
        for key in refs: neighbors[key].update(refs)
    # A vertex shared by separate fans is non-manifold even if every edge has <=2 faces.
    vertex_faces={v:set() for v in geometry.vertices}
    for key,f in geometry.faces.items():
        for v in f.vertices: vertex_faces[v].add(key)
    for vertex,incident in vertex_faces.items():
        if not incident: continue
        reached=set(); pending=[next(iter(incident))]
        while pending:
            key=pending.pop()
            if key in reached: continue
            reached.add(key)
            for token,refs in edge_faces.items():
                if vertex in token and key in refs: pending.extend(set(refs)-reached)
        if reached!=incident: errors.append(f'Mesh {name!r}: Non-manifold vertex fan at {vertex!r}')
    todo=set(neighbors)
    while todo:
        seed=min(todo); component=set(); pending=[seed]
        while pending:
            key=pending.pop()
            if key in component: continue
            component.add(key); pending.extend(neighbors[key]-component)
        todo-=component
        if geometry.closed:
            volume=0.
            for key in component:
                order=geometry.faces[key].vertices
                for i in range(1,len(order)-1):
                    a,b,c=(geometry.vertices[k] for k in (order[0],order[i],order[i+1]))
                    volume+=_dot(a,_cross(b,c))/6
            if volume<=EPS: errors.append(f'Mesh {name!r} component containing face {seed!r} has inward or zero-volume winding: {_ORIENT_HINT}')
    if check_intersections and not errors:
        errors.extend(f'Mesh {name!r}: {error}' for error in _intersection_errors(geometry))
    return errors,warnings


def validate_mesh_elements(elements):
    from .geometry_types import MeshGeometry, MeshFace
    errors,warnings=[],[]
    for e in elements:
        if e.kind!='mesh' or not e.vertices: continue
        try:
            geometry=MeshGeometry(e.vertices,{k:MeshFace(tuple(f.get('vertices',()))) for k,f in e.faces.items()},e.mesh_closed)
        except ValueError as exc:
            errors.append(f'Mesh {e.name!r}: {exc}')
            continue
        ee,ww=validate_geometry(geometry,check_intersections=True,name=e.name)
        errors.extend(ee); warnings.extend(ww)
    return errors,warnings


def _intersection_errors(geometry):
    from itertools import combinations
    from .spatial import unit, sub, cross, dot, add, mul
    def face_triangles(face):
        from .polygon_decomposition import temporary_triangle_indices
        points=tuple(geometry.vertices[key] for key in face.vertices)
        return temporary_triangle_indices(points)

    triangles=[]
    for face,f in geometry.faces.items():
        for indices in face_triangles(f):
            keys=tuple(f.vertices[index] for index in indices)
            points=tuple(geometry.vertices[k] for k in keys)
            triangles.append((face,keys,points))
    errors=[]
    def bounds(points): return tuple((min(p[i] for p in points),max(p[i] for p in points)) for i in range(3))
    boxes=[bounds(t[2]) for t in triangles]
    def cut(points,origin,normal):
        distances=[dot(sub(p,origin),normal) for p in points]; result=[]
        for i,p in enumerate(points):
            j=(i+1)%3; q=points[j]; a,b=distances[i],distances[j]
            if abs(a)<=EPS: result.append(p)
            if (a < -EPS and b > EPS) or (a > EPS and b < -EPS): result.append(add(p,mul(sub(q,p),a/(a-b))))
        return result
    for i,j in combinations(range(len(triangles)),2):
        fa,ka,pa=triangles[i]; fb,kb,pb=triangles[j]
        if fa==fb or any(a[1]<b[0]-EPS or b[1]<a[0]-EPS for a,b in zip(boxes[i],boxes[j])): continue
        na=unit(cross(sub(pa[1],pa[0]),sub(pa[2],pa[0]))); nb=unit(cross(sub(pb[1],pb[0]),sub(pb[2],pb[0])))
        line=cross(na,nb); length=math.sqrt(dot(line,line)); bad=False
        if length<EPS:
            if abs(dot(sub(pb[0],pa[0]),na))>EPS: continue
            # Positive-area coplanar overlap by separating axes; shared boundaries are allowed.
            bad=True
            for points in (pa,pb):
                for x,y in zip(points,points[1:]+points[:1]):
                    axis=unit(cross(na,sub(y,x))); a=[dot(p,axis) for p in pa]; b=[dot(p,axis) for p in pb]
                    if min(max(a),max(b))-max(min(a),min(b))<=EPS: bad=False; break
                if not bad: break
        else:
            aa=cut(pa,pb[0],nb); bb=cut(pb,pa[0],na)
            if not aa or not bb: continue
            axis=mul(line,1/length)
            a=[dot(p,axis) for p in aa]; b=[dot(p,axis) for p in bb]
            low,high=max(min(a),min(b)),min(max(a),max(b))
            if high<low-EPS: continue
            # Internal decomposition triangles do not own topology.  Boundary
            # adjacency is determined from the persistent polygon faces.
            shared=set(geometry.faces[fa].vertices)&set(geometry.faces[fb].vertices)
            shared_positions=[dot(geometry.vertices[k],axis) for k in shared]
            if high-low>EPS:
                bad=not (len(shared)>=2 and low>=min(shared_positions)-EPS and high<=max(shared_positions)+EPS)
            else:
                bad=not any(abs(low-p)<=EPS for p in shared_positions)
        if bad: errors.append(f'Self-intersection between faces {fa!r} and {fb!r}')
    return list(dict.fromkeys(errors))
