"""Declarative geometry-derived crease and inter-element contact fields."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
import heapq
import math

from lib.geometry_validation import faces_for
from .color import clamp_byte, parse_color


EPSILON = 1e-6


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _add(a, b):
    return tuple(a[i] + b[i] for i in range(3))


def _mul(a, value):
    return tuple(component * value for component in a)


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _length(value):
    return math.sqrt(_dot(value, value))


def _unit(value):
    length = _length(value)
    return tuple(component / length for component in value)


def _distance(a, b):
    return _length(_sub(a, b))


def _centroid(points):
    return tuple(sum(point[i] for point in points) / len(points) for i in range(3))


def _polygon_triangles(points):
    """Temporary decomposition used only by geometric field predicates."""
    from lib.polygon_decomposition import temporary_triangle_indices
    points=tuple(points)
    return tuple(tuple(points[index] for index in indices)
                 for indices in temporary_triangle_indices(points))


def _closest_segment(point, a, b):
    edge = _sub(b, a)
    denominator = _dot(edge, edge)
    t = 0.0 if denominator <= EPSILON else max(0.0, min(1.0, _dot(_sub(point, a), edge) / denominator))
    candidate = _add(a, _mul(edge, t))
    return candidate, _distance(point, candidate)


def _segment_polygon_distance(segment, polygon):
    """Exact distance from a contact segment to a planar texel footprint."""
    if len(polygon) < 3:
        return min((_closest_segment(point,*segment)[1] for point in polygon), default=math.inf)
    distances = []
    for index in range(1,len(polygon)-1):
        triangle=(polygon[0],polygon[index],polygon[index+1])
        valid_triangle=_length(_cross(_sub(triangle[1],triangle[0]),
                                      _sub(triangle[2],triangle[0])))>EPSILON
        if valid_triangle:
            for endpoint in segment:
                distances.append(_distance(endpoint,_closest_triangle_point(endpoint,*triangle)))
        for point in triangle:
            distances.append(_closest_segment(point,*segment)[1])
        for edge in range(3):
            distances.append(_closest_segments(segment[0],segment[1],
                                                triangle[edge],triangle[(edge+1)%3])[0])
        if valid_triangle and _segment_triangle_intersection(segment[0],segment[1],triangle) is not None:
            return 0.0
    return min(distances,default=math.inf)


def _sample_segment_distance(sample, segment, limit=None):
    """Distance from a contact segment to a texel; with ``limit``, ``inf`` for texels that cannot be within it."""
    polygons=getattr(sample,"coverage_model_polygons",())
    if limit is not None:
        points=[p for polygon in polygons for p in polygon] or list(
            sample.coverage_model_points or (sample.model_position,))
        low,high=_bounds(points); seg_low,seg_high=_bounds(segment)
        gap=math.sqrt(sum(max(0.0,low[i]-seg_high[i],seg_low[i]-high[i])**2 for i in range(3)))
        if gap>limit:
            return math.inf
    if polygons:
        return min(_segment_polygon_distance(segment,polygon) for polygon in polygons)
    return min(_closest_segment(point,*segment)[1]
               for point in (sample.coverage_model_points or (sample.model_position,)))


def _closest_segments(a0, a1, b0, b1):
    u, v, w = _sub(a1,a0), _sub(b1,b0), _sub(a0,b0)
    a, b, c, d, e = _dot(u,u), _dot(u,v), _dot(v,v), _dot(u,w), _dot(v,w)
    denominator = a*c-b*b
    s_denominator = t_denominator = denominator
    if denominator < EPSILON:
        s_numerator, s_denominator = 0.0, 1.0
        t_numerator, t_denominator = e, c
    else:
        s_numerator, t_numerator = b*e-c*d, a*e-b*d
        if s_numerator < 0:
            s_numerator, t_numerator, t_denominator = 0.0, e, c
        elif s_numerator > s_denominator:
            s_numerator, t_numerator, t_denominator = s_denominator, e+b, c
    if t_numerator < 0:
        t_numerator = 0.0
        if -d < 0: s_numerator = 0.0
        elif -d > a: s_numerator = s_denominator
        else: s_numerator, s_denominator = -d, a
    elif t_numerator > t_denominator:
        t_numerator = t_denominator
        if -d+b < 0: s_numerator = 0.0
        elif -d+b > a: s_numerator = s_denominator
        else: s_numerator, s_denominator = -d+b, a
    s = 0.0 if abs(s_numerator) < EPSILON else s_numerator/s_denominator
    t = 0.0 if abs(t_numerator) < EPSILON else t_numerator/t_denominator
    first, second = _add(a0,_mul(u,s)), _add(b0,_mul(v,t))
    return _distance(first,second), (first,second)


def _closest_triangle_point(point, a, b, c):
    # Ericson's closest-point regions, kept dependency-free.
    ab, ac, ap = _sub(b,a), _sub(c,a), _sub(point,a)
    d1, d2 = _dot(ab,ap), _dot(ac,ap)
    if d1 <= 0 and d2 <= 0: return a
    bp = _sub(point,b); d3, d4 = _dot(ab,bp), _dot(ac,bp)
    if d3 >= 0 and d4 <= d3: return b
    vc = d1*d4-d3*d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return _add(a, _mul(ab, d1/(d1-d3)))
    cp = _sub(point,c); d5, d6 = _dot(ab,cp), _dot(ac,cp)
    if d6 >= 0 and d5 <= d6: return c
    vb = d5*d2-d1*d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return _add(a, _mul(ac, d2/(d2-d6)))
    va = d3*d6-d5*d4
    if va <= 0 and d4-d3 >= 0 and d5-d6 >= 0:
        return _add(b, _mul(_sub(c,b), (d4-d3)/((d4-d3)+(d5-d6))))
    denominator = 1.0/(va+vb+vc)
    return _add(a, _add(_mul(ab, vb*denominator), _mul(ac, vc*denominator)))


def _segment_triangle_intersection(start, end, triangle):
    a, b, c = triangle
    direction = _sub(end, start)
    edge1, edge2 = _sub(b, a), _sub(c, a)
    h = _cross(direction, edge2)
    determinant = _dot(edge1, h)
    if abs(determinant) <= EPSILON:
        return None
    inverse = 1.0 / determinant
    s = _sub(start, a)
    u = inverse * _dot(s, h)
    if u < -EPSILON or u > 1 + EPSILON:
        return None
    q = _cross(s, edge1)
    v = inverse * _dot(direction, q)
    if v < -EPSILON or u + v > 1 + EPSILON:
        return None
    t = inverse * _dot(edge2, q)
    if t < -EPSILON or t > 1 + EPSILON:
        return None
    return _add(start, _mul(direction, max(0.0, min(1.0, t))))


def _triangle_intersection_segment(first, second):
    """Return the complete non-coplanar intersection segment, not one hit point."""
    points = []
    for index in range(3):
        point = _segment_triangle_intersection(first[index], first[(index+1)%3], second)
        if point is not None:
            points.append(point)
        point = _segment_triangle_intersection(second[index], second[(index+1)%3], first)
        if point is not None:
            points.append(point)
    unique = []
    for point in points:
        if not any(_distance(point, existing) <= EPSILON for existing in unique):
            unique.append(point)
    if not unique:
        return None
    if len(unique) == 1:
        return unique[0], unique[0]
    return max(((a, b) for index, a in enumerate(unique) for b in unique[index+1:]),
               key=lambda pair: _distance(*pair))


def _triangle_distance(first, second):
    candidates = []
    segment = _triangle_intersection_segment(first, second)
    if segment is not None:
        return 0.0, segment[0], segment[1]
    for point in first:
        other = _closest_triangle_point(point, *second)
        candidates.append((_distance(point, other), point, other))
    for point in second:
        other = _closest_triangle_point(point, *first)
        candidates.append((_distance(point, other), other, point))
    for ai in range(3):
        for bi in range(3):
            distance, pair = _closest_segments(first[ai], first[(ai+1)%3],
                                                second[bi], second[(bi+1)%3])
            candidates.append((distance, pair[0], pair[1]))
    return min(candidates, key=lambda item: item[0])


def _bounds(points):
    return tuple(min(p[i] for p in points) for i in range(3)), tuple(max(p[i] for p in points) for i in range(3))


def _overlaps(a, b, padding=0.0):
    return all(a[0][i]-padding <= b[1][i] and b[0][i]-padding <= a[1][i] for i in range(3))


def _edge_key(a, b):
    clean = lambda p: tuple(round(value, 7) for value in p)
    return tuple(sorted((clean(a), clean(b))))


def _merge_collinear_segments(segments):
    """Remove triangulation duplicates and join touching collinear fragments."""
    merged = []
    for start, end in segments:
        if _distance(start, end) <= EPSILON:
            continue
        key = _edge_key(start, end)
        if not any(_edge_key(*existing) == key for existing in merged):
            merged.append((tuple(start), tuple(end)))
    changed = True
    while changed:
        changed = False
        for first_index in range(len(merged)):
            a, b = merged[first_index]
            direction = _unit(_sub(b, a))
            for second_index in range(first_index + 1, len(merged)):
                c, d = merged[second_index]
                if (_length(_cross(direction, _sub(c, a))) > EPSILON or
                        _length(_cross(direction, _sub(d, a))) > EPSILON):
                    continue
                first_range = sorted((_dot(_sub(a,a),direction), _dot(_sub(b,a),direction)))
                second_range = sorted((_dot(_sub(c,a),direction), _dot(_sub(d,a),direction)))
                if second_range[0] > first_range[1] + EPSILON or first_range[0] > second_range[1] + EPSILON:
                    continue
                endpoints = (a, b, c, d)
                replacement = max(((x,y) for i,x in enumerate(endpoints) for y in endpoints[i+1:]),
                                  key=lambda pair: _distance(*pair))
                merged[first_index] = replacement
                del merged[second_index]
                changed = True
                break
            if changed:
                break
    return tuple(sorted(merged, key=lambda segment: _edge_key(*segment)))


@dataclass(frozen=True)
class GeometryFace:
    element_name: str
    face_name: str
    points: tuple
    normal: tuple
    bounds: tuple

    @property
    def triangles(self):
        return _polygon_triangles(self.points)


@dataclass(frozen=True)
class FieldHit:
    surface: object
    distance: float
    normalized_distance: float
    intensity: float
    kind: str
    sources: tuple
    inside_contact: bool = False
    occluded_fraction: float = 0.0


def _blend(base, overlay, mode, opacity):
    base, overlay = parse_color(base), parse_color(overlay)
    alpha = (overlay[3] / 255.0) * opacity
    if mode == "replace":
        target = overlay
    elif mode == "normal":
        target = overlay
    elif mode == "multiply":
        target = tuple(base[i] * overlay[i] / 255.0 for i in range(3)) + (overlay[3],)
    elif mode == "screen":
        target = tuple(255-(255-base[i])*(255-overlay[i])/255.0 for i in range(3)) + (overlay[3],)
    elif mode == "add":
        target = tuple(min(255, base[i]+overlay[i]) for i in range(3)) + (overlay[3],)
    else:
        raise ValueError("blend must be replace, normal, multiply, screen, or add")
    if mode == "replace" and opacity == 1:
        return overlay
    rgb = tuple(clamp_byte(base[i] + (target[i]-base[i])*alpha) for i in range(3))
    out_alpha = clamp_byte(base[3] + (255-base[3])*alpha)
    return rgb + (out_alpha,)


class ContactField:
    """Immutable detected field; paint mutates only its owning face canvases."""

    def __init__(self, targets=(), *, events=(), ambiguities=()):
        self._targets = tuple(targets)
        self._events = tuple(events)
        self._ambiguities = tuple(ambiguities)

    def __len__(self):
        return len(self._targets)

    def __iter__(self):
        return (target[1] for target in self._targets)

    def __or__(self, other):
        if not isinstance(other, ContactField):
            return NotImplemented
        merged = {}
        for face, hit in self._targets + other._targets:
            key = (hit.surface.element_name, hit.surface.face_name, hit.surface.pixel)
            previous = merged.get(key)
            if previous is None or (hit.distance, hit.kind, hit.sources) < (
                    previous[1].distance, previous[1].kind, previous[1].sources):
                merged[key] = (face, hit)
        return ContactField((merged[key] for key in sorted(merged)),
                            events=self._events + other._events,
                            ambiguities=self._ambiguities + other._ambiguities)

    def mask(self, predicate):
        if not callable(predicate):
            raise TypeError("field mask predicate must be callable")
        return ContactField(((face, hit) for face, hit in self._targets if predicate(hit)),
                            events=self._events, ambiguities=self._ambiguities)

    def require_nonempty(self):
        if not self._targets:
            raise ValueError("Geometry field is empty; no matching crease or contact was detected")
        return self

    @property
    def stats(self):
        kinds = {}
        elements = set()
        for _, hit in self._targets:
            kinds[hit.kind] = kinds.get(hit.kind, 0) + 1
            elements.add(hit.surface.element_name)
        return MappingProxyType({
            "events": len(self._events), "texels": len(self._targets),
            "kinds": MappingProxyType(dict(sorted(kinds.items()))),
            "elements": tuple(sorted(elements)),
            "max_distance": max((hit.distance for _, hit in self._targets), default=0.0),
            "ambiguities": self._ambiguities,
        })

    def report(self, json=False):
        data = dict(self.stats)
        data["kinds"] = dict(data["kinds"])
        if json:
            return __import__("json").dumps(data, ensure_ascii=False, sort_keys=True)
        kinds = ", ".join(f"{key}={value}" for key, value in data["kinds"].items()) or "none"
        return (f"GeometryField: {data['events']} events, {data['texels']} texels; "
                f"{kinds}; elements={list(data['elements'])}; "
                f"ambiguities={len(data['ambiguities'])}")

    def paint(self, callback, *, blend="normal", opacity=1.0):
        if not callable(callback):
            raise TypeError("field paint callback must be callable")
        if isinstance(opacity, bool) or not isinstance(opacity, (int,float)) or not 0 <= opacity <= 1:
            raise ValueError("opacity must be between 0 and 1")
        if blend not in {"replace", "normal", "multiply", "screen", "add"}:
            raise ValueError("blend must be replace, normal, multiply, screen, or add")
        for face, hit in self._targets:
            color = callback(hit)
            if color is not None:
                current = face.get_pixel(*hit.surface.pixel)
                face.set_pixel(*hit.surface.pixel, _blend(current, color, blend, float(opacity)))
        return self


class ContactFieldDetector:
    def __init__(self, painter):
        self.painter = painter
        self.builder = painter.surface_sampler.builder
        for element in self.builder._elements:
            if element.parent == "":
                element.parent = None
        self.faces = self._faces()
        self._cache = {}
        self._surface_graph_cache = {}
        self.broad_phase_pairs = 0
        self.narrow_phase_pairs = 0

    def _faces(self):
        result = []
        for element in self.builder._elements:
            for face_name, normal, points in faces_for(self.builder, element):
                points = tuple(tuple(point) for point in points)
                result.append(GeometryFace(element.name, face_name.lower(), points,
                                           tuple(normal), _bounds(points)))
        return tuple(result)

    @staticmethod
    def _names(selection, all_names):
        if selection is None:
            return tuple(sorted(all_names))
        if not hasattr(selection, "elements"):
            raise TypeError("sources/receivers must be an ElementSelection or None")
        return tuple(sorted(element.name for element in selection.elements))

    def _surface_graph(self, receiver_names):
        key=tuple(sorted(receiver_names))
        if key in self._surface_graph_cache:
            return self._surface_graph_cache[key]
        nodes={}; faces={}; adjacency={}; by_face={}
        geometry_faces={(face.element_name,face.face_name):face for face in self.faces}
        for element_name in key:
            element=self.painter.element(element_name)
            for face_name,face in element.faces.items():
                if face.uv_info.get("owner"):
                    raise ValueError("Geometry fields cannot paint shared UV followers")
                samples=self.painter.surface_sampler.samples(element_name,face_name,face)
                by_face[(element_name,face_name)]=samples
                pixels={sample.pixel:sample for sample in samples}
                for sample in samples:
                    node=(element_name,face_name,sample.pixel)
                    nodes[node]=sample; faces[node]=face; adjacency[node]=[]
                for sample in samples:
                    node=(element_name,face_name,sample.pixel)
                    x,y=sample.pixel
                    for dx,dy in ((1,0),(0,1),(1,1),(1,-1)):
                        other=pixels.get((x+dx,y+dy))
                        if other is None: continue
                        other_node=(element_name,face_name,other.pixel)
                        weight=_distance(sample.model_position,other.model_position)
                        adjacency[node].append((other_node,weight))
                        adjacency[other_node].append((node,weight))
        edge_faces={}
        for face_key,geometry in geometry_faces.items():
            if face_key[0] not in key or face_key not in by_face: continue
            for index,point in enumerate(geometry.points):
                edge_faces.setdefault(_edge_key(point,geometry.points[(index+1)%len(geometry.points)]),[]).append(face_key)
        for edge,face_keys in edge_faces.items():
            if len(face_keys)!=2 or face_keys[0][0]!=face_keys[1][0]: continue
            first,second=face_keys
            a,b=edge
            sides=[]
            for face_key in (first,second):
                samples=by_face[face_key]
                ranked=sorted(((min(_closest_segment(point,a,b)[1]
                                        for point in sample.coverage_model_points),sample)
                               for sample in samples),
                              key=lambda item:(item[0],item[1].pixel))
                minimum=ranked[0][0]
                sides.append([sample for distance,sample in ranked
                              if distance<=minimum+EPSILON])
            for source_side,target_side in ((sides[0],sides[1]),(sides[1],sides[0])):
                for sample in source_side:
                    other=min(target_side,key=lambda candidate:_distance(
                        sample.model_position,candidate.model_position))
                    source_node=(sample.element_name,sample.face_name,sample.pixel)
                    target_node=(other.element_name,other.face_name,other.pixel)
                    weight=_distance(sample.model_position,other.model_position)
                    adjacency[source_node].append((target_node,weight))
                    adjacency[target_node].append((source_node,weight))
        result=(nodes,faces,adjacency,by_face)
        self._surface_graph_cache[key]=result
        return result

    def _build_field(self, seeds, spread, receiver_names, ambiguities=()):
        nodes,faces,adjacency,by_face=self._surface_graph(receiver_names)
        distances={}; provenance={}; queue=[]; serial=0
        for kind,receiver_face,segment,sources,source_faces in seeds:
            for sample in by_face.get((receiver_face.element_name,receiver_face.face_name),()):
                distance=_sample_segment_distance(sample,segment,spread+EPSILON)
                if distance>spread+EPSILON: continue
                node=(sample.element_name,sample.face_name,sample.pixel)
                previous=distances.get(node)
                marker=(kind,tuple(sources),tuple(source_faces))
                if previous is None or distance<previous-EPSILON:
                    distances[node]=distance; provenance[node]=marker
                    heapq.heappush(queue,(distance,serial,node)); serial+=1
        while queue:
            distance,_,node=heapq.heappop(queue)
            if distance>distances[node]+EPSILON: continue
            for other,weight in adjacency[node]:
                candidate=distance+weight
                if candidate>spread+EPSILON or candidate>=distances.get(other,math.inf)-EPSILON: continue
                distances[other]=candidate; provenance[other]=provenance[node]
                heapq.heappush(queue,(candidate,serial,other)); serial+=1
        targets={}
        for node,distance in distances.items():
            sample=nodes[node]; kind,sources,source_faces=provenance[node]
            normalized=min(1.0,distance/spread)
            occluded=self._occluded_fraction(sample,source_faces)
            inside=occluded>=1.0-EPSILON
            targets[node]=(faces[node],FieldHit(sample,distance,normalized,1.0-normalized,
                                                kind,sources,inside,occluded))
        return ContactField((targets[key] for key in sorted(targets)), events=seeds,
                            ambiguities=ambiguities)

    _PREPARED = {}

    @classmethod
    def _prepared(cls, source_faces):
        """Points, bounds and triangle boxes of a source, computed once per source tuple."""
        entry = cls._PREPARED.get(id(source_faces))
        if entry is not None and entry[0] is source_faces:
            return entry[1]
        all_points = [position for face in source_faces for position in face.points]
        triangles = []
        for face in source_faces:
            for triangle in face.triangles:
                triangles.append((triangle, _bounds(triangle)))
        prepared = (all_points, _bounds(all_points), triangles) if all_points else ([], None, [])
        if len(cls._PREPARED) > 256:
            cls._PREPARED.clear()
        cls._PREPARED[id(source_faces)] = (source_faces, prepared)   # keeps the tuple alive, so its id is never reused
        return prepared

    @classmethod
    def _point_inside(cls, point, source_faces):
        if not source_faces:
            return False
        all_points, bounds, triangles = cls._prepared(source_faces)
        if bounds is None or any(point[index] < bounds[0][index]-EPSILON or
                                 point[index] > bounds[1][index]+EPSILON for index in range(3)):
            return False
        reach = max(_distance(point, (bounds[side][0], bounds[side2][1], bounds[side3][2]))
                    for side in (0, 1) for side2 in (0, 1) for side3 in (0, 1)) + 10
        end = _add(point, _mul(_unit((1.0, .371390676, .529109)), reach))
        low = tuple(min(point[i], end[i]) - EPSILON for i in range(3))
        high = tuple(max(point[i], end[i]) + EPSILON for i in range(3))
        hits = []
        for triangle, (t_low, t_high) in triangles:
            if (t_high[0] < low[0] or t_low[0] > high[0] or t_high[1] < low[1] or t_low[1] > high[1]
                    or t_high[2] < low[2] or t_low[2] > high[2]):
                continue
            hit = _segment_triangle_intersection(point, end, triangle)
            if hit is not None and _distance(point, hit) > EPSILON and not any(
                    _distance(hit, existing) <= EPSILON for existing in hits):
                hits.append(hit)
        return len(hits) % 2 == 1

    @classmethod
    def _occluded_fraction(cls,sample,source_faces):
        if not source_faces:
            return 0.0
        points=[]
        for polygon in getattr(sample,"coverage_model_polygons",()):
            points.extend(polygon)
            if polygon:
                points.append(_centroid(polygon))
        if not points:
            points.extend(sample.coverage_model_points or (sample.model_position,))
        points.append(sample.model_position)
        unique=[]
        for point in points:
            if not any(_distance(point,other)<=EPSILON for other in unique):
                unique.append(point)
        return sum(cls._point_inside(point,source_faces) for point in unique)/len(unique)

    @staticmethod
    def _positive(value, label, allow_zero=False):
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number")
        if value < 0 or (not allow_zero and value == 0):
            raise ValueError(f"{label} must be {'non-negative' if allow_zero else 'positive'}")
        return float(value)

    def creases(self, receivers=None, *, max_internal_angle=100, spread=1.0):
        spread = self._positive(spread, "spread")
        if not 0 < max_internal_angle < 180:
            raise ValueError("max_internal_angle must be between 0 and 180")
        names = self._names(receivers, self.painter.elements)
        key = ("creases", names, float(max_internal_angle), spread)
        if key in self._cache: return self._cache[key]
        edge_map = {}
        for face in self.faces:
            if face.element_name not in names: continue
            for index, point in enumerate(face.points):
                edge_map.setdefault(_edge_key(point, face.points[(index+1)%len(face.points)]), []).append(face)
        seeds, ambiguities = [], []
        for edge, adjacent in sorted(edge_map.items()):
            unique = {(face.element_name, face.face_name): face for face in adjacent}
            if len(unique) > 2:
                ambiguities.append(f"non-manifold edge {edge}")
                continue
            if len(unique) != 2: continue
            first, second = unique.values()
            if first.element_name != second.element_name: continue
            normal_angle = math.degrees(math.acos(max(-1.0,min(1.0,_dot(first.normal,second.normal)))))
            internal_angle = 180.0-normal_angle
            midpoint = _mul(_add(edge[0],edge[1]), .5)
            inward_test = _dot(_add(first.normal,second.normal),
                               _sub(_mul(_add(_centroid(first.points),_centroid(second.points)),.5), midpoint))
            if internal_angle <= max_internal_angle and inward_test > EPSILON:
                sources = ((first.element_name, first.face_name), (second.element_name, second.face_name))
                seeds.extend(("crease", face, edge, sources, ()) for face in (first,second))
        field = self._build_field(tuple(seeds), spread, names, tuple(ambiguities))
        self._cache[key] = field
        return field

    def contacts(self, sources=None, receivers=None, *, tolerance, spread=1.0):
        tolerance = self._positive(tolerance, "tolerance", allow_zero=True)
        spread = self._positive(spread, "spread")
        source_names = self._names(sources, self.painter.elements)
        receiver_names = self._names(receivers, self.painter.elements)
        key = ("contacts", source_names, receiver_names, tolerance, spread)
        if key in self._cache: return self._cache[key]
        source_faces = [face for face in self.faces if face.element_name in source_names]
        receiver_faces = [face for face in self.faces if face.element_name in receiver_names]
        candidates = [(source, receiver) for source in source_faces for receiver in receiver_faces
                      if source.element_name != receiver.element_name and
                      _overlaps(source.bounds, receiver.bounds, tolerance)]
        self.broad_phase_pairs = len(candidates)
        seeds = []
        intersection_groups = {}
        checked = set()
        self.narrow_phase_pairs = 0
        for source, receiver in candidates:
            pair_key = (source.element_name,source.face_name,receiver.element_name,receiver.face_name)
            if pair_key in checked: continue
            checked.add(pair_key); self.narrow_phase_pairs += 1
            best = None
            intersections = []
            for first in source.triangles:
                for second in receiver.triangles:
                    segment = _triangle_intersection_segment(first, second)
                    if segment is not None:
                        intersections.append(segment)
                    candidate = _triangle_distance(first, second)
                    if best is None or candidate[0] < best[0]: best = candidate
            if best is None or best[0] > tolerance + EPSILON: continue
            kind = "intersection" if intersections else "proximity"
            if kind == "proximity" and _dot(source.normal, receiver.normal) > -0.1:
                continue
            if intersections:
                group_key = (source.element_name, receiver.element_name, receiver.face_name)
                group = intersection_groups.setdefault(group_key, {
                    "receiver": receiver, "segments": [], "source_refs": set()})
                group["segments"].extend(intersections)
                group["source_refs"].add((source.element_name, source.face_name))
            else:
                seeds.append((kind, receiver, (best[2], best[2]),
                              ((source.element_name,source.face_name),), ()))
        for (source_name, _, _), group in sorted(intersection_groups.items()):
            source_geometry = tuple(face for face in self.faces if face.element_name == source_name)
            sources = tuple(sorted(group["source_refs"]))
            for segment in _merge_collinear_segments(group["segments"]):
                seeds.append(("intersection", group["receiver"], segment,
                              sources, source_geometry))
        field = self._build_field(tuple(seeds), spread, receiver_names)
        self._cache[key] = field
        return field
