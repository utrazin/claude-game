"""Heuristic low-poly diagnostics; never an integrity validator."""
from __future__ import annotations

import math


def _distance(a, b):
    return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def _center(points):
    return tuple(sum(p[i] for p in points)/len(points) for i in range(3))


def _components(element):
    faces=list(element.faces.values())
    if not faces:
        return 0
    linked=[set(face.get("vertices",())) for face in faces]
    remaining=set(range(len(linked))); count=0
    while remaining:
        count+=1; pending=[remaining.pop()]
        while pending:
            current=pending.pop()
            touched=[i for i in remaining if linked[i] & linked[current]]
            for index in touched:
                remaining.remove(index); pending.append(index)
    return count


def _bounds(points):
    return tuple((min(point[i] for point in points),max(point[i] for point in points)) for i in range(3))


def _box_gap(a,b):
    return math.sqrt(sum((0 if a[i][0] <= b[i][1] and b[i][0] <= a[i][1]
                          else min(abs(a[i][0]-b[i][1]),abs(b[i][0]-a[i][1])))**2
                          for i in range(3)))


def _relation_declared(first, second):
    tags=set(first.tags)&set(second.tags)
    return any(tag.startswith(("contact:","relation:","assembly:")) for tag in tags)


def _no_overlap_check(element) -> bool:
    """Return True if the element has opted out of the overlap bounds check."""
    return getattr(element, "no_overlap_check", False) or "no_overlap_check" in getattr(element, "tags", [])


def audit_low_poly(builder, *, face_budget: int | None = None, style: bool = True):
    """Heuristic low-poly diagnostics. style=False returns structural checks only (shells, budget)."""
    if face_budget is not None and face_budget <= 0:
        raise ValueError("face_budget must be positive")
    structural_warnings=[]; style_warnings=[]; elements=[]; boxes=[]
    total_faces=0
    for element in builder._elements:
        if not element.vertices:
            continue
        faces=len(element.faces); total_faces+=faces
        rings={}
        for name,keys in element.mesh_rings.items():
            points=[builder._element_vertex_world(element,key) for key in keys]
            center=_center(points)
            radii=[_distance(point,center) for point in points]
            rings[name]={"vertices":len(keys),"center":[round(v,5) for v in center],
                         "mean_radius":round(sum(radii)/len(radii),5)}
        component_count=_components(element)
        item={"name":element.name,"faces":faces,"vertices":len(element.vertices),
              "components":component_count,"rings":rings}
        elements.append(item)
        boxes.append((element,_bounds([builder._element_vertex_world(element,key)
                                      for key in element.vertices])))
        # --- Structural: disconnected shells ---
        if component_count > 1:
            structural_warnings.append(f"Element {element.name!r} contains {component_count} disconnected shells; review intent")
        if style:
            # --- Style: near-uniform collinear rings ---
            if len(rings) >= 3:
                radii=[info["mean_radius"] for info in rings.values()]
                average=sum(radii)/len(radii)
                variation=(max(radii)-min(radii))/average if average else 0
                centers=[tuple(info["center"]) for info in rings.values()]
                first,last=centers[0],centers[-1]
                axis=tuple(b-a for a,b in zip(first,last)); length=_distance(first,last)
                deviation=0.0
                if length:
                    for point in centers[1:-1]:
                        relative=tuple(p-a for p,a in zip(point,first))
                        projection=sum(a*b for a,b in zip(relative,axis))/(length*length)
                        closest=tuple(a+projection*b for a,b in zip(first,axis))
                        deviation=max(deviation,_distance(point,closest))
                if variation < .04 and (not length or deviation/max(length,1e-9) < .02):
                    style_warnings.append(f"Element {element.name!r} has near-uniform collinear rings; review silhouette")
            # --- Style: elongated faces ---
            extreme=0
            for face in element.faces.values():
                keys=face.get("vertices",())
                points=[builder._element_vertex_world(element,key) for key in keys]
                edges=[_distance(a,b) for a,b in zip(points,points[1:]+points[:1])]
                if edges and min(edges)>1e-9 and max(edges)/min(edges)>12:
                    extreme+=1
            if extreme:
                style_warnings.append(f"Element {element.name!r} has {extreme} highly elongated faces; review density or silhouette")
    # --- Structural: face budget ---
    if face_budget is not None and total_faces > face_budget:
        structural_warnings.append(f"Model uses {total_faces} faces, exceeding low-poly budget {face_budget}")
    if style:
        # --- Style: overlapping/very-close bounds without relation tag ---
        for index,(first,first_box) in enumerate(boxes):
            if _no_overlap_check(first):
                continue
            first_extent=max(high-low for low,high in first_box)
            for second,second_box in boxes[index+1:]:
                if _no_overlap_check(second):
                    continue
                if _relation_declared(first,second):
                    continue
                gap=_box_gap(first_box,second_box)
                threshold=max(first_extent,max(high-low for low,high in second_box))*.01
                if gap <= threshold:
                    kind="overlapping" if gap == 0 else "very close"
                    style_warnings.append(f"Elements {first.name!r} and {second.name!r} have {kind} bounds without a shared relation tag")
    warnings=sorted(set(structural_warnings)) + sorted(set(style_warnings))
    return {"face_budget":face_budget,"total_faces":total_faces,"elements":elements,
            "warnings":warnings,
            "structural_warnings":sorted(set(structural_warnings)),
            "style_warnings":sorted(set(style_warnings))}
