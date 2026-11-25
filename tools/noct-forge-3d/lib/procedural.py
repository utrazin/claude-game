"""Profiles and deterministic polygon construction, independent of Blockbench."""
from dataclasses import dataclass, replace
import math
from .geometry_types import MeshDraft, MeshFace, parse_cap_spec, vector3
from .spatial import Frame, SpatialFrame, add, sub, mul, dot, cross, unit, turn


def _count(value, minimum=3):
    if isinstance(value,bool) or not isinstance(value,int) or not minimum <= value <= 4096:
        raise ValueError(f'Count must be an integer between {minimum} and 4096')
    return value


def _positive(value):
    value = float(value)
    if not math.isfinite(value) or value <= 0: raise ValueError('Dimension must be positive and finite')
    return value


from .polygon_math import validate_contour


@dataclass(frozen=True)
class Profile:
    points: tuple
    allow_triangles: bool = False

    def __post_init__(self):
        points = tuple(tuple(float(v) for v in p) for p in self.points)
        min_pts = 3 if self.allow_triangles else 4
        if len(points) < min_pts:
            if self.allow_triangles:
                raise ValueError('Profiles need at least three vertices')
            else:
                raise ValueError('Profiles need at least four vertices; triangular profiles are forbidden')
        validate_contour(points)
        object.__setattr__(self, 'points', points)
        object.__setattr__(self, 'allow_triangles', bool(self.allow_triangles))

    @classmethod
    def polygon(cls, points, *, allow_triangles: bool = False):
        return cls(tuple(points), allow_triangles=allow_triangles)

    @classmethod
    def triangle(cls, p0, p1, p2):
        return cls((p0, p1, p2), allow_triangles=True)

    @classmethod
    def circle(cls, radius=1, *, segments=8, phase=0.0):
        return cls.ellipse(2*_positive(radius),2*radius,segments=segments,phase=phase)
    @classmethod
    def ellipse(cls, width, depth, *, segments=8, phase=0.0):
        """Counter-clockwise ellipse; vertex ``i`` sits at ``phase + 360*i/segments`` degrees."""
        w,d=_positive(width)/2,_positive(depth)/2
        return cls.oval(w,d,d,segments=segments,phase=phase)
    @classmethod
    def oval(cls, half_width, pos_y, neg_y, *, segments=8, phase=0.0):
        """Ellipse with different radii toward profile +y and -y (e.g. chest vs back).

        ``half_width`` is the +/-x radius.  ``phase`` (degrees) rotates where the
        vertices start: 0 puts a vertex on +x; ``180/segments`` puts a face there.
        Vertex ``i`` is at angle ``phase + 360*i/segments``, counter-clockwise.
        """
        w,py,ny=_positive(half_width),_positive(pos_y),_positive(neg_y)
        n=_count(segments); start=math.radians(float(phase))
        if not math.isfinite(start): raise ValueError('Profile phase must be finite')
        points=[]
        for i in range(n):
            a=start+math.tau*i/n; s=math.sin(a)
            points.append((w*math.cos(a),(py if s>0 else ny)*s))
        return cls(tuple(points))
    def nudge(self, offsets):
        """Return a copy with selected vertices moved: ``{index: (dx, dy)}``."""
        points=list(self.points)
        for index,delta in dict(offsets).items():
            if not isinstance(index,int) or not -len(points)<=index<len(points):
                raise IndexError(f'Profile has {len(points)} vertices; cannot nudge index {index!r}')
            dx,dy=(float(v) for v in delta)
            points[index]=(points[index][0]+dx,points[index][1]+dy)
        return Profile(tuple(points), allow_triangles=self.allow_triangles)
    @classmethod
    def rectangle(cls, width, depth):
        w,d=_positive(width)/2,_positive(depth)/2
        return cls(((-w,-d),(w,-d),(w,d),(-w,d)))
    @classmethod
    def rounded_rectangle(cls, width, depth, corner_radius, *, corner_segments=3):
        w,d=_positive(width)/2,_positive(depth)/2
        r=_positive(corner_radius)
        if r>=min(w,d): raise ValueError('Corner radius must be smaller than half the smallest dimension')
        n=_count(corner_segments,1)
        points=[]
        for cx,cy,start in ((w-r,d-r,0),(-w+r,d-r,90),(-w+r,-d+r,180),(w-r,-d+r,270)):
            for i in range(n+1):
                angle=math.radians(start+90*i/n)
                points.append((cx+r*math.cos(angle),cy+r*math.sin(angle)))
        return cls(tuple(points))
    def scale(self, factors):
        sx,sy=(factors,factors) if isinstance(factors,(float,int)) else factors
        sx,sy=_positive(sx),_positive(sy)
        return Profile(tuple((x*sx,y*sy) for x,y in self.points), allow_triangles=self.allow_triangles)
    def expand(self, margin):
        """Mitered offset in model units; concave offsets that cross are rejected."""
        margin=float(margin)
        if not math.isfinite(margin): raise ValueError('Margin must be finite')
        sign=1 if validate_contour(self.points)>0 else -1
        result=[]
        for i,p in enumerate(self.points):
            prev,nxt=self.points[i-1],self.points[(i+1)%len(self.points)]
            e1=(p[0]-prev[0],p[1]-prev[1]); e2=(nxt[0]-p[0],nxt[1]-p[1])
            l1,l2=math.hypot(*e1),math.hypot(*e2)
            n1=(sign*e1[1]/l1,-sign*e1[0]/l1); n2=(sign*e2[1]/l2,-sign*e2[0]/l2)
            denominator=1+n1[0]*n2[0]+n1[1]*n2[1]
            if denominator<1e-10: raise ValueError('Undefined offset corner')
            result.append(tuple(p[k]+margin*(n1[k]+n2[k])/denominator for k in (0,1)))
        candidate=Profile(tuple(result), allow_triangles=self.allow_triangles)
        if validate_contour(candidate.points)*sign<=0: raise ValueError('Offset collapsed profile')
        for i in range(len(result)):
            old=sub(self.points[(i+1)%len(result)],self.points[i]); new=sub(result[(i+1)%len(result)],result[i])
            if dot(old,new)<=0: raise ValueError('Offset collapsed profile edge')
        return candidate
    def resample(self,count):
        n=_count(count, 3 if self.allow_triangles else 4)
        edges=list(zip(self.points,self.points[1:]+self.points[:1]))
        lengths=[math.dist(a,b) for a,b in edges]; total=sum(lengths)
        result=[]; edge=0; start=0.
        for i in range(n):
            distance=total*i/n
            while edge<len(edges)-1 and distance>start+lengths[edge]: start+=lengths[edge]; edge+=1
            t=(distance-start)/lengths[edge]; a,b=edges[edge]
            result.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
        return Profile(tuple(result), allow_triangles=self.allow_triangles)


@dataclass(frozen=True)
class Section:
    name: str
    profile: Profile
    frame: Frame = Frame()

    def scale(self, factors): return replace(self,profile=self.profile.scale(factors))
    def expand(self, margin): return replace(self,profile=self.profile.expand(margin))
    def offset(self, delta): return replace(self,frame=self.frame.offset(delta))
    def rotate(self, degrees): return replace(self,frame=self.frame.rotate(degrees))


def _section_common(owner, name, profile, rotation, offset):
    if not name:
        raise ValueError(f"{owner} needs a non-empty name")
    if not isinstance(profile, Profile):
        raise TypeError(f"{owner} {name!r} needs a Profile")
    rotation = float(rotation)
    if not math.isfinite(rotation):
        raise ValueError(f"{owner} {name!r} rotation must be finite")
    offset = tuple(float(v) for v in offset)
    if len(offset) != 2 or not all(math.isfinite(v) for v in offset):
        raise ValueError(f"{owner} {name!r} offset must contain two finite numbers")
    return rotation, offset


@dataclass(frozen=True, init=False)
class SegmentSection:
    """A named cross-section along a straight segment.

    Position it with ``t`` (0..1 along the segment) or ``distance`` (model
    units from ``start``).  The first section must land on the start and the
    last on the end.  ``offset`` shifts the section centre in profile x/y.

    Accepts both ``(name, profile, t=...)`` and ``(name, t, profile=...)``
    positional orders.
    """
    name: str
    t: float | None = None
    profile: Profile | None = None
    rotation: float = 0.0
    offset: tuple = (0.0, 0.0)
    distance: float | None = None

    def __init__(
        self,
        name: str,
        arg2=None,
        arg3=None,
        *,
        t: float | None = None,
        profile: Profile | None = None,
        rotation: float = 0.0,
        offset: tuple = (0.0, 0.0),
        distance: float | None = None,
    ):
        actual_t = t
        actual_profile = profile
        actual_distance = distance

        if arg2 is not None:
            if isinstance(arg2, Profile):
                actual_profile = arg2
                if arg3 is not None:
                    if isinstance(arg3, (int, float)):
                        actual_t = arg3
                    else:
                        raise TypeError(f"SegmentSection {name!r}: expected t/distance as number, got {arg3!r}")
            elif isinstance(arg2, (int, float)):
                actual_t = arg2
                if arg3 is not None:
                    if isinstance(arg3, Profile):
                        actual_profile = arg3
                    else:
                        raise TypeError(f"SegmentSection {name!r}: expected Profile, got {arg3!r}")
            else:
                actual_profile = arg2
                if arg3 is not None:
                    actual_t = arg3

        object.__setattr__(self, "name", str(name))
        object.__setattr__(self, "t", actual_t)
        object.__setattr__(self, "profile", actual_profile)
        object.__setattr__(self, "rotation", rotation)
        object.__setattr__(self, "offset", offset)
        object.__setattr__(self, "distance", actual_distance)
        self.__post_init__()

    def __post_init__(self):
        if (self.t is None) == (self.distance is None):
            raise ValueError(f"SegmentSection {self.name!r} needs exactly one of t or distance")
        rotation, offset = _section_common("SegmentSection", self.name, self.profile,
                                           self.rotation, self.offset)
        if self.t is not None:
            t = float(self.t)
            if not 0 <= t <= 1:
                raise ValueError(f"SegmentSection {self.name!r} t={t:g} must be within [0, 1]")
            object.__setattr__(self, "t", t)
        else:
            distance = float(self.distance)
            if not math.isfinite(distance):
                raise ValueError(f"SegmentSection {self.name!r} distance must be finite")
            object.__setattr__(self, "distance", distance)
        object.__setattr__(self, "rotation", rotation)
        object.__setattr__(self, "offset", offset)

    def resolved_t(self, length):
        if self.t is not None:
            return self.t
        t = self.distance / length
        if -1e-9 <= t <= 1 + 1e-9:
            return min(1.0, max(0.0, t))
        raise ValueError(f"SegmentSection {self.name!r} distance {self.distance:g} is outside "
                         f"the segment length {length:g}")


@dataclass(frozen=True)
class PathSection:
    """A named cross-section along a ``Path3D`` (used by ``add_sweep(sections=...)``).

    ``at`` is the arc-length distance from the first path point; values
    before 0 or past the end extend straight along the end directions.
    ``point`` instead places the section exactly on path vertex ``point``
    (its frame bisects the bend there).  The section name becomes a mesh
    anchor and ring, so bones can target ``"mesh:name"``.
    """
    name: str
    profile: Profile
    at: float | None = None
    point: int | None = None
    rotation: float = 0.0
    offset: tuple = (0.0, 0.0)
    distance: float | None = None   # same as at

    def __post_init__(self):
        if self.distance is not None:
            if self.at is not None:
                raise ValueError(f"PathSection {self.name!r}: give at or distance, not both")
            object.__setattr__(self, "at", self.distance)
            object.__setattr__(self, "distance", None)
        if (self.at is None) == (self.point is None):
            raise ValueError(f"PathSection {self.name!r} needs exactly one of at or point")
        rotation, offset = _section_common("PathSection", self.name, self.profile,
                                           self.rotation, self.offset)
        if self.at is not None:
            at = float(self.at)
            if not math.isfinite(at): raise ValueError(f"PathSection {self.name!r} at must be finite")
            object.__setattr__(self, "at", at)
        elif isinstance(self.point, bool) or not isinstance(self.point, int):
            raise TypeError(f"PathSection {self.name!r} point must be a path vertex index")
        object.__setattr__(self, "rotation", rotation)
        object.__setattr__(self, "offset", offset)


@dataclass(frozen=True)
class Path3D:
    points: tuple

    def __post_init__(self):
        points=tuple(vector3(p) for p in self.points)
        if len(points)<2 or math.dist(points[0],points[-1])<1e-10: raise ValueError('Path must be open with at least two points')
        tangents=[unit(sub(b,a)) for a,b in zip(points,points[1:])]
        if any(dot(a,b)<-1+1e-8 for a,b in zip(tangents,tangents[1:])): raise ValueError('Path reverses 180 degrees')
        object.__setattr__(self,'points',points)
    @classmethod
    def line(cls,start,end,*,samples=2):
        n=_count(samples,2); start,end=vector3(start),vector3(end)
        return cls(tuple(add(start,mul(sub(end,start),i/(n-1))) for i in range(n)))
    @classmethod
    def polyline(cls,points): return cls(tuple(points))
    @classmethod
    def bezier(cls,p0,p1,p2,p3,*,samples):
        n=_count(samples,2); controls=tuple(vector3(p) for p in (p0,p1,p2,p3)); result=[]
        for i in range(n):
            t=i/(n-1); weights=((1-t)**3,3*(1-t)**2*t,3*(1-t)*t*t,t**3)
            result.append(tuple(sum(p[k]*w for p,w in zip(controls,weights)) for k in range(3)))
        return cls(tuple(result))
    def lengths(self):
        """Cumulative arc length at every path point (first is 0)."""
        result=[0.]
        for a,b in zip(self.points,self.points[1:]): result.append(result[-1]+math.dist(a,b))
        return tuple(result)

    def frames(self, *, x_hint=None, y_hint=None):
        directions=[unit(sub(b,a)) for a,b in zip(self.points,self.points[1:])]
        tangents=[directions[0]]+[unit(add(a,b)) for a,b in zip(directions,directions[1:])]+[directions[-1]]
        frame=Frame.from_normal(self.points[0],normal=tangents[0],x_hint=x_hint,y_hint=y_hint)
        result=[frame]
        for origin,z in zip(self.points[1:],tangents[1:]):
            axis=cross(frame.z,z); sine=math.sqrt(dot(axis,axis)); cosine=dot(frame.z,z)
            if cosine<-1+1e-8: raise ValueError('Undefined transport at reversal')
            x=turn(frame.x,axis,math.degrees(math.atan2(sine,cosine))) if sine>1e-10 else frame.x
            frame=Frame.from_normal(origin,normal=z,x_hint=x); result.append(frame)
        return tuple(result)


@dataclass(frozen=True)
class RelativePath:
    reference: object
    points: tuple
    scale: float = 1.0

    @classmethod
    def from_frame(cls, ref, *, points, scale=1.0):
        value=float(scale)
        if not math.isfinite(value) or value <= 0: raise ValueError("Relative path scale must be positive")
        return cls(ref, tuple(vector3(point) for point in points), value)

    def resolve(self, resolver) -> Path3D:
        frame=resolver.resolve_frame(self.reference)
        return Path3D.polyline(tuple(frame.point(mul(point,self.scale)) for point in self.points))


@dataclass(frozen=True)
class Curve:
    start: object
    end: object
    bend: tuple = (0.0, 0.0, 0.0)
    samples: int = 6

    @classmethod
    def between(cls,start,end,*,bend=(0,0,0),samples=6):
        return cls(start,end,vector3(bend,"curve bend"),_count(samples,2))

    def resolve(self,resolver) -> Path3D:
        a,b=resolver.resolve_point(self.start),resolver.resolve_point(self.end)
        if self.bend == (0.0,0.0,0.0): return Path3D.line(a,b,samples=self.samples)
        try: frame=resolver.resolve_frame(self.start)
        except KeyError: frame=SpatialFrame(a,unit(sub(b,a)),(0,0,1))
        control=frame.point(self.bend)
        c1=tuple((a[i]+2*control[i])/3 for i in range(3))
        c2=tuple((b[i]+2*control[i])/3 for i in range(3))
        return Path3D.bezier(a,c1,c2,b,samples=self.samples)


def check_reserved(anchors, own):
    """A section may reuse a reserved anchor name only where the shape's own anchor lands anyway."""
    for name, position in own:
        if name in anchors and math.dist(anchors[name], position) > 1e-6:
            raise ValueError(f"Section {name!r} is not where the shape's own {name!r} anchor is, and the shape's "
                             "anchor would replace it: rename the section "
                             "(reserved names: base, top, center, start, end)")


def _is_convex(points, sign):
    """True when every turn of the outline bends the same way (collinear corners allowed)."""
    n = len(points)
    for i in range(n):
        ax, ay = points[i]; bx, by = points[(i + 1) % n]; cx, cy = points[(i + 2) % n]
        if ((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) * sign < -1e-9:
            return False
    return True


def loft(sections, *, start_cap="flat", end_cap="flat", allow_cap_triangles: bool = False):
    """Bridge explicit ``Section`` rings with quads and close the ends with caps.

    Every section needs the same point count and counter-clockwise winding.
    Section names become rings, anchors and frames; ``base``/``top``/``center``
    anchors are reserved for the loft ends and midpoint.
    """
    sections=tuple(sections)
    if len(sections)<2: raise ValueError('Loft requires at least two sections')
    names=[s.name for s in sections]
    if any(not name for name in names): raise ValueError('Section names must be nonempty')
    repeated=sorted({name for name in names if names.count(name)>1})
    if repeated: raise ValueError(f'Section names must be unique; repeated: {repeated}')
    n=len(sections[0].profile.points); sign=validate_contour(sections[0].profile.points)
    for s in sections:
        if len(s.profile.points)!=n:
            raise ValueError(f'Loft section {s.name!r} has {len(s.profile.points)} points but '
                             f'{sections[0].name!r} has {n}; use Profile.resample({n})')
        if validate_contour(s.profile.points)*sign<=0:
            raise ValueError(f'Loft section {s.name!r} winds opposite to {sections[0].name!r}; '
                             'list every profile counter-clockwise')
    bottom_spec=parse_cap_spec(start_cap); top_spec=parse_cap_spec(end_cap)
    for section, spec in ((sections[0], bottom_spec), (sections[-1], top_spec)):
        if (spec.style != 'open' and (len(section.profile.points) % 2 == 0 or allow_cap_triangles)
                and not _is_convex(section.profile.points, sign)):
            raise ValueError(f"Section {section.name!r} has a concave profile: flat caps fan around the centre and "
                             "need a convex outline. Use start_cap='open' / end_cap='open' and close it yourself, "
                             "or build the shape from several convex parts")
    draft=MeshDraft(closed=bottom_spec.style!='open' and top_spec.style!='open'); rings=[]
    for s in sections:
        keys=[]
        for i,(x,y) in enumerate(s.profile.points):
            key=f'{s.name}_v{i:03d}'; draft.vertex(key,s.frame.point((x,y,0))); keys.append(key)
        draft.rings[s.name]=tuple(keys); draft.anchor(s.name,s.frame.origin)
        draft.frame(s.name,SpatialFrame(s.frame.origin,s.frame.z,mul(s.frame.y,-1)))
        rings.append(tuple(keys))
    for i,(a,b) in enumerate(zip(rings,rings[1:])):
        for j in range(n):
            k=(j+1)%n
            draft.face(f'{names[i]}__{names[i+1]}_side_{j:03d}',(a[j],a[k],b[k],b[j]),group='side')
    has_triangles = allow_cap_triangles or n == 3
    for ring,reverse,group,spec in ((rings[0],True,'cap_start',bottom_spec),
                                    (rings[-1],False,'cap_end',top_spec)):
        if spec.style=='open': continue
        draft.cap(ring,name=group,reverse=reverse,group=group,
                  inset=spec.inset if spec.style=='inset' else None,
                  allow_triangles=has_triangles)
    check_reserved(draft.anchors, (('base', sections[0].frame.origin), ('top', sections[-1].frame.origin),
                            ('center', draft.bounds_point())))
    draft.anchor('base',sections[0].frame.origin).anchor('top',sections[-1].frame.origin)
    draft.anchor('center',draft.bounds_point())
    draft.frame('base',SpatialFrame(sections[0].frame.origin,sections[0].frame.z,mul(sections[0].frame.y,-1)))
    draft.frame('top',SpatialFrame(sections[-1].frame.origin,sections[-1].frame.z,mul(sections[-1].frame.y,-1)))
    return _finish(draft)


def segment_frame(direction, *, x_hint=None, y_hint=None):
    """Profile frame of a straight segment (origin at 0).

    Without hints, profile +x is the world axis least parallel to the segment
    (ties: X, then Y, then Z) and profile +y = direction x (+x).  Example: a
    segment running +Y gets profile x=+X and profile y=-Z.  Pass ``y_hint``
    to say directly where profile +y must point (e.g. ``(0, 0, 1)`` = front).
    """
    direction = unit(direction)
    if x_hint is None and y_hint is None:
        x_hint = min(((1., 0., 0.), (0., 1., 0.), (0., 0., 1.)),
                     key=lambda axis: abs(dot(axis, direction)))
    return Frame.from_normal((0, 0, 0), normal=direction, x_hint=x_hint, y_hint=y_hint)


def segment_sections(start, end, sections, *, x_hint=None, y_hint=None):
    """Normalize parametric segment sections into explicit loft sections.

    Internal routing helper: lets :class:`ModelBuilder` route segments
    through the single loft path rather than maintaining a second mesh
    construction implementation. Recipes use ``add_segment``.
    """
    start, end = vector3(start, "segment start"), vector3(end, "segment end")
    delta = sub(end, start)
    length = math.sqrt(dot(delta, delta))
    if length < 1e-10:
        raise ValueError("Segment start and end must differ")
    specs = tuple(sections)
    if len(specs) < 2:
        raise ValueError("A segment needs at least two sections")
    ts = [spec.resolved_t(length) for spec in specs]
    if math.isclose(ts[0], 0.0, abs_tol=1e-5):
        ts[0] = 0.0
    if math.isclose(ts[-1], 1.0, abs_tol=1e-5):
        ts[-1] = 1.0
    if ts[0] != 0 or ts[-1] != 1:
        raise ValueError(f"Segment sections must start at t=0 and end at t=1; got "
                         f"{specs[0].name!r} at t={ts[0]:g} and {specs[-1].name!r} at t={ts[-1]:g}")
    for (a, ta), (b, tb) in zip(zip(specs, ts), zip(specs[1:], ts[1:])):
        if ta >= tb:
            raise ValueError(f"Segment sections must advance strictly: {a.name!r} (t={ta:g}) "
                             f"is not before {b.name!r} (t={tb:g})")
    frame = segment_frame(delta, x_hint=x_hint, y_hint=y_hint)
    built = [
        Section(spec.name, spec.profile,
                Frame(add(mul(delta, t),
                          add(mul(frame.x,spec.offset[0]),mul(frame.y,spec.offset[1]))),
                      frame.x, frame.y, frame.z).rotate(spec.rotation))
        for spec, t in zip(specs, ts)
    ]
    return tuple(built)


def path_sections(path, sections, *, x_hint=None, y_hint=None):
    """Turn ``PathSection`` specs into explicit loft sections along ``path``.

    Frames are parallel-transported along the path (no twist).  A section
    exactly on a path vertex uses the bisecting frame of that bend; a
    section inside a span is perpendicular to that span.
    """
    if not isinstance(path, Path3D):
        raise TypeError("path_sections needs a Path3D")
    specs = tuple(sections)
    if len(specs) < 2:
        raise ValueError("A path loft needs at least two sections")
    lengths = path.lengths()
    vertex_frames = path.frames(x_hint=x_hint, y_hint=y_hint)
    directions = [unit(sub(b, a)) for a, b in zip(path.points, path.points[1:])]
    built = []; previous = None
    for spec in specs:
        if spec.point is not None:
            if not -len(path.points) <= spec.point < len(path.points):
                raise IndexError(f"PathSection {spec.name!r} point {spec.point} is not a vertex "
                                 f"of a {len(path.points)}-point path")
            index = spec.point % len(path.points)
            distance, frame = lengths[index], vertex_frames[index]
        else:
            distance = spec.at
            vertex = next((i for i, value in enumerate(lengths) if abs(value - distance) <= 1e-9), None)
            if vertex is not None:
                frame = vertex_frames[vertex]
            else:
                span = next((i for i in range(len(directions)) if distance < lengths[i + 1]),
                            len(directions) - 1)
                if distance < 0: span = 0
                origin = add(path.points[span], mul(directions[span], distance - lengths[span]))
                frame = Frame.from_normal(origin, normal=directions[span],
                                          x_hint=vertex_frames[span].x)
        if previous is not None and distance <= previous[1] + 1e-9:
            raise ValueError(f"Path sections must advance along the path: {spec.name!r} "
                             f"(at {distance:g}) is not after {previous[0]!r} (at {previous[1]:g})")
        previous = (spec.name, distance)
        frame = frame.rotate(spec.rotation).offset((spec.offset[0], spec.offset[1], 0.0))
        built.append(Section(spec.name, spec.profile, frame))
    return tuple(built)


def segment(start, end, sections, *, x_hint=None, y_hint=None, start_cap="flat",
            end_cap="flat", allow_cap_triangles: bool = False):
    """Build a locally anchored mesh between two endpoints from normalized sections."""
    start, end = vector3(start, "segment start"), vector3(end, "segment end")
    delta = sub(end, start)
    direction = unit(delta)
    built = segment_sections(start, end, sections, x_hint=x_hint, y_hint=y_hint)
    frame = segment_frame(direction, x_hint=x_hint, y_hint=y_hint)
    draft = loft(built, start_cap=start_cap, end_cap=end_cap,
                 allow_cap_triangles=allow_cap_triangles)
    check_reserved(draft.anchors, (('start', (0.0, 0.0, 0.0)), ('end', delta)))
    draft.anchors["start"] = (0.0, 0.0, 0.0)
    draft.anchors["end"] = delta
    draft.frames["start"] = SpatialFrame((0,0,0),direction,mul(frame.y,-1))
    draft.frames["end"] = SpatialFrame(delta,direction,mul(frame.y,-1))
    return draft


def _table(table, width, label="table"):
    if isinstance(table, (int, float)) or not hasattr(table, "__iter__"):
        raise ValueError(f"{label} must be a table ((t, value), ...) such as ((0, 1), (1, 0.5)), not {table!r}")
    result=[]
    for entry in table:
        try:
            t,value=entry
            t=float(t)
            values=(float(value),)*width if isinstance(value,(float,int)) else tuple(float(v) for v in value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} entries are (t, value) with {width} number(s) per value; got {entry!r}") from None
        if not math.isfinite(t) or not 0<=t<=1 or len(values)!=width or not all(math.isfinite(v) for v in values):
            raise ValueError(f"{label} entry {entry!r} is invalid: t must be between 0 and 1 and the value {width} finite number(s)")
        result.append((t,values))
    if not result or result[0][0]!=0 or result[-1][0]!=1 or any(a[0]>=b[0] for a,b in zip(result,result[1:])):
        raise ValueError(f"{label} must start at t=0, end at t=1 and increase in between")
    return result


def _at(table,t):
    for (a,av),(b,bv) in zip(table,table[1:]):
        if t<=b: return tuple(x+(y-x)*(t-a)/(b-a) for x,y in zip(av,bv))
    return table[-1][1]


def sweep_sections(profile,path,*,x_hint=None,y_hint=None,scale=((0,1),(1,1)),twist=((0,0),(1,0))):
    """Turn a path and profile into explicit sections for the shared loft core.

    Internal routing helper for ``add_sweep``; recipes use the builder method.
    """
    scales,angles=_table(scale,2,"scale"),_table(twist,1,"twist")
    if any(min(v)<=0 for _,v in scales): raise ValueError('Sweep scale must be positive')
    lengths=path.lengths()
    return tuple(Section(f'section_{i:03d}',profile.scale(_at(scales,d/lengths[-1])),f.rotate(_at(angles,d/lengths[-1])[0]))
                 for i,(d,f) in enumerate(zip(lengths,path.frames(x_hint=x_hint,y_hint=y_hint))))


def sweep(profile,path,*,x_hint=None,y_hint=None,scale=((0,1),(1,1)),twist=((0,0),(1,0)),
          start_cap="flat", end_cap="flat", allow_cap_triangles: bool = False):
    """Sweep one ``Profile`` along a ``Path3D`` through the shared loft core.

    ``scale``/``twist`` are ``((t, value), ...)`` tables from ``t=0`` to
    ``t=1``; frames are parallel-transported along the path without twist.
    """
    sections=sweep_sections(profile,path,x_hint=x_hint,y_hint=y_hint,scale=scale,twist=twist)
    return loft(sections,start_cap=start_cap,end_cap=end_cap,
                allow_cap_triangles=allow_cap_triangles)


def revolve(points, *, segments=8, angle=360, start_cap="flat", end_cap="flat",
            allow_cap_triangles: bool = False):
    """Revolve an open (radius, height) meridian around +Y, bottom to top."""
    n=_count(segments); angle=float(angle)
    points=tuple(tuple(float(v) for v in p) for p in points)
    if len(points)<2 or any(len(p)!=2 or not all(math.isfinite(v) for v in p) or p[0]<0 for p in points): raise ValueError(f'Invalid meridian: give at least two (radius, height) pairs of finite numbers with radius >= 0; got {len(points)} point(s)')
    if not math.isfinite(angle) or not 0<angle<=360: raise ValueError('Angle must be in (0,360]')
    if n < 4: raise ValueError('Revolve needs at least four segments; triangles are forbidden')
    if any(math.dist(a,b)<1e-10 for a,b in zip(points,points[1:])): raise ValueError('Degenerate meridian edge')
    if any(p[0]<=0 for p in points):
        raise ValueError('Revolve radii must stay positive; singular poles would create triangles')
    bottom_spec=parse_cap_spec(start_cap); top_spec=parse_cap_spec(end_cap)
    if n % 2 and not allow_cap_triangles and (bottom_spec.style!='open' or top_spec.style!='open'):
        raise ValueError('Odd segment counts require open ends or allow_cap_triangles=True')
    full=angle==360; count=n if full else n+1
    if not full and (bottom_spec.style!='open' or top_spec.style!='open'):
        raise ValueError('Partial revolve requires start_cap and end_cap to be open')
    d=MeshDraft(closed=(full and bottom_spec.style!='open' and top_spec.style!='open')); rings=[]
    for i,(radius,height) in enumerate(points):
        name=f'section_{i:03d}'
        ring=tuple(f'{name}_v{j:03d}' for j in range(count))
        for j,key in enumerate(ring):
            theta=math.radians(angle*j/n); d.vertex(key,(radius*math.cos(theta),height,radius*math.sin(theta)))
        rings.append(ring); d.rings[name]=tuple(dict.fromkeys(ring)); d.anchor(name,(0,height,0))
        d.frame(name,SpatialFrame((0,height,0),(0,1,0),(0,0,1)))
    for i,(a,b) in enumerate(zip(rings,rings[1:])):
        for j in range(n):
            k=(j+1)%count
            d.face(f'band_{i:03d}_{j:03d}',(a[j],b[j],b[k],a[k]),group='side')
    if bottom_spec.style!='open' or top_spec.style!='open' or not full:
        for i,reverse,spec in ((0,False,bottom_spec),(len(rings)-1,True,top_spec)):
            if spec.style=='open': continue
            name='cap_start' if i==0 else 'cap_end'
            d.cap(rings[i],name=name,reverse=reverse,group='cap',
                  inset=spec.inset if spec.style=='inset' else None,
                  allow_triangles=allow_cap_triangles)
        if not full:
            axis=[]
            for index,(_,height) in enumerate(points):
                key=f'seam_axis_{index:03d}'; d.vertex(key,(0,height,0)); axis.append(key)
            for index in range(len(rings)-1):
                d.face(f'seam_start_{index:03d}',
                       (axis[index+1],rings[index+1][0],rings[index][0],axis[index]),group='seam')
                d.face(f'seam_end_{index:03d}',
                       (axis[index],rings[index][-1],rings[index+1][-1],axis[index+1]),group='seam')
    d.anchor('base',(0,points[0][1],0)).anchor('top',(0,points[-1][1],0)).anchor('center',d.bounds_point())
    d.frame('base',SpatialFrame((0,points[0][1],0),(0,1,0),(0,0,1)))
    d.frame('top',SpatialFrame((0,points[-1][1],0),(0,1,0),(0,0,1)))
    return _finish(d)


def _finish(draft):
    geometry=draft.build()
    if draft.closed:
        volume=sum(dot(geometry.vertices[f.vertices[0]],cross(geometry.vertices[f.vertices[i]],geometry.vertices[f.vertices[i+1]]))/6
                   for f in geometry.faces.values() for i in range(1,len(f.vertices)-1))
        if volume<0:
            draft.faces={k:MeshFace(tuple(reversed(f.vertices)),f.group,f.source_face) for k,f in draft.faces.items()}
    draft.validate()
    return draft
