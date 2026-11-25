"""Small, dependency-free spatial vocabulary. Distances are model units, angles degrees."""
from dataclasses import dataclass
import math
from .geometry_types import vector3


def add(a, b): return tuple(x+y for x, y in zip(a, b))
def sub(a, b): return tuple(x-y for x, y in zip(a, b))
def mul(a, s): return tuple(x*s for x in a)
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def unit(a):
    a = vector3(a)
    length = math.sqrt(dot(a, a))
    if length < 1e-10: raise ValueError('Undefined direction: a zero-length vector (duplicate consecutive path points or coincident sections?)')
    return mul(a, 1/length)


def turn(v, axis, degrees):
    axis = unit(axis)
    angle = math.radians(float(degrees))
    if not math.isfinite(angle): raise ValueError('Angle must be finite')
    c, s = math.cos(angle), math.sin(angle)
    return add(add(mul(v, c), mul(cross(axis, v), s)), mul(axis, dot(axis, v)*(1-c)))


@dataclass(frozen=True)
class Frame:
    """Right-handed frame; profile XY plane, normal along local Z."""
    origin: tuple = (0., 0., 0.)
    x: tuple = (1., 0., 0.)
    y: tuple = (0., 1., 0.)
    z: tuple = (0., 0., 1.)

    def __post_init__(self):
        for name in ('origin', 'x', 'y', 'z'):
            object.__setattr__(self, name, vector3(getattr(self, name), name))
        if any(abs(dot(v, v)-1) > 1e-7 for v in (self.x, self.y, self.z)) or any(
                abs(dot(a,b)) > 1e-7 for a,b in ((self.x,self.y),(self.x,self.z),(self.y,self.z))) or dot(cross(self.x,self.y),self.z) < 1-1e-7:
            raise ValueError('Frame must be orthonormal and right-handed')

    @classmethod
    def from_normal(cls, origin=(0,0,0), *, normal=(0,0,1), x_hint=None, y_hint=None):
        """Frame whose local Z is ``normal``.

        Steer the profile plane with ``x_hint`` (where profile +x points) or
        ``y_hint`` (where profile +y points); the hint is projected onto the
        plane.  Default: ``x_hint=(1, 0, 0)``, which gives ``y = normal x x``.
        """
        if x_hint is not None and y_hint is not None:
            raise ValueError("Pass x_hint or y_hint, not both")
        z = unit(normal)
        hint_name, hint = ("y_hint", y_hint) if y_hint is not None else (
            "x_hint", (1., 0., 0.) if x_hint is None else x_hint)
        hint = vector3(hint, hint_name)
        projected = sub(hint, mul(z, dot(hint, z)))
        if dot(projected, projected) < 1e-12:
            raise ValueError(f"{hint_name} {hint} is parallel to normal {z}; choose another hint")
        if y_hint is not None:
            y = unit(projected)
            return cls(origin, cross(y, z), y, z)
        x = unit(projected)
        return cls(origin, x, cross(z, x), z)

    @property
    def right(self): return self.x

    @property
    def forward(self): return self.y

    @property
    def up(self): return self.z

    def vector(self, value):
        a,b,c = vector3(value)
        return add(add(mul(self.x,a),mul(self.y,b)),mul(self.z,c))

    def point(self, value): return add(self.origin, self.vector(value))
    def local(self, value):
        delta = sub(value,self.origin)
        return tuple(dot(delta,v) for v in (self.x,self.y,self.z))
    def offset(self, value): return Frame(self.point(value),self.x,self.y,self.z)
    def rotate(self, degrees):
        return Frame(self.origin,turn(self.x,self.z,degrees),turn(self.y,self.z,degrees),self.z)


@dataclass(frozen=True)
class SpatialFrame:
    """Immutable attachment frame: ``forward`` is local +Y and ``up`` local +Z."""
    origin: tuple = (0., 0., 0.)
    forward: tuple = (0., 1., 0.)
    up: tuple = (0., 0., 1.)

    def __post_init__(self):
        origin = vector3(self.origin, "frame origin")
        forward = unit(self.forward)
        up_hint = unit(self.up)
        if abs(dot(forward, up_hint)) > 1 - 1e-8:
            raise ValueError("SpatialFrame forward and up cannot be collinear")
        right = unit(cross(forward, up_hint))
        up = unit(cross(right, forward))
        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "forward", forward)
        object.__setattr__(self, "up", up)

    @property
    def right(self): return unit(cross(self.forward, self.up))
    @property
    def x(self): return self.right
    @property
    def y(self): return self.forward
    @property
    def z(self): return self.up

    def vector(self, value):
        x, y, z = vector3(value)
        return add(add(mul(self.right, x), mul(self.forward, y)), mul(self.up, z))

    def point(self, value): return add(self.origin, self.vector(value))

    def local(self, value):
        delta = sub(vector3(value), self.origin)
        return (dot(delta, self.right), dot(delta, self.forward), dot(delta, self.up))

    def offset(self, value): return SpatialFrame(self.point(value), self.forward, self.up)
    def as_frame(self): return Frame(self.origin, self.right, self.forward, self.up)

    @classmethod
    def from_frame(cls, frame: Frame): return cls(frame.origin, frame.y, frame.z)

    def transformed(self, *, point_transform, vector_transform):
        return SpatialFrame(point_transform(self.origin), vector_transform(self.forward),
                            vector_transform(self.up))

    def mirrored(self, axis: str = "X"):
        """Bilateral mirror: forward and up are reflected (up stays up, a
        front-facing up stays front-facing); ``right`` is recomputed, so the
        frame stays right-handed and its lateral axis flips sides."""
        axis = axis.upper()
        if axis not in {"X", "Y", "Z"}: raise ValueError("axis must be X, Y, or Z")
        index = "XYZ".index(axis)
        reflect = lambda value: tuple(-v if i == index else v for i, v in enumerate(value))
        return SpatialFrame(reflect(self.origin), reflect(self.forward), reflect(self.up))


_CARDINAL_VECTORS = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def _cardinal_direction(value, label):
    text = str(value).strip().upper()
    if text not in {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}:
        raise ValueError(f"{label} must be one of +X, -X, +Y, -Y, +Z, -Z")
    axis = "XYZ".index(text[1])
    return tuple((1. if text[0] == "+" else -1.) if index == axis else 0.
                 for index in range(3)), text


@dataclass(frozen=True)
class ModelOrientation:
    """Persisted, cardinal interpretation of model front and up."""
    up: str = "+Y"
    front: str = "+Z"

    def __post_init__(self):
        up_vector, up = _cardinal_direction(self.up, "up")
        front_vector, front = _cardinal_direction(self.front, "front")
        if abs(dot(up_vector, front_vector)) > 1e-9:
            raise ValueError("ModelOrientation front and up must be perpendicular")
        object.__setattr__(self, "up", up)
        object.__setattr__(self, "front", front)

    @property
    def up_vector(self): return _cardinal_direction(self.up, "up")[0]

    @property
    def front_vector(self): return _cardinal_direction(self.front, "front")[0]

    def as_metadata(self): return {"up": self.up, "front": self.front}


def _deterministic_tangent(normal):
    """Return a stable tangent for ``normal`` without an arbitrary Euler angle.

    The least-aligned world axis gives the largest projected vector.  Ties use
    X, then Y, then Z, which makes the result deterministic for all cardinal
    contacts and for generated primitives.
    """
    hint = min(_CARDINAL_VECTORS, key=lambda axis: abs(dot(normal, axis)))
    return unit(sub(hint, mul(normal, dot(hint, normal))))


@dataclass(frozen=True)
class SurfaceContact:
    """An oriented point on an outer surface.

    ``normal`` always points out of the owning geometry.  ``tangent_u`` and
    ``tangent_v`` are an orthonormal, right-handed basis of the contact plane:
    ``cross(tangent_u, tangent_v) == normal``.  This is deliberately distinct
    from :class:`SpatialFrame`: an attachment needs a surface normal, while a
    generic socket only has a forward/up convention.

    Supplying no tangents chooses a deterministic world-aligned basis.  A
    caller may supply either tangent to preserve a meaningful seam direction;
    supplying both is accepted only when they describe the same oriented
    contact plane.
    """
    origin: tuple = (0., 0., 0.)
    normal: tuple = (0., 1., 0.)
    tangent_u: tuple | None = None
    tangent_v: tuple | None = None

    def __post_init__(self):
        origin = vector3(self.origin, "contact origin")
        normal = unit(self.normal)
        provided_u = self.tangent_u is not None
        provided_v = self.tangent_v is not None

        if provided_u:
            raw_u = vector3(self.tangent_u, "contact tangent_u")
            tangent_u = unit(sub(raw_u, mul(normal, dot(raw_u, normal))))
        elif provided_v:
            raw_v = vector3(self.tangent_v, "contact tangent_v")
            tangent_v_hint = unit(sub(raw_v, mul(normal, dot(raw_v, normal))))
            tangent_u = unit(cross(tangent_v_hint, normal))
        else:
            tangent_u = _deterministic_tangent(normal)

        tangent_v = unit(cross(normal, tangent_u))
        if provided_v:
            raw_v = vector3(self.tangent_v, "contact tangent_v")
            expected_v = unit(sub(raw_v, mul(normal, dot(raw_v, normal))))
            if dot(tangent_v, expected_v) < 1 - 1e-7:
                raise ValueError("SurfaceContact tangents must form a right-handed basis")

        object.__setattr__(self, "origin", origin)
        object.__setattr__(self, "normal", normal)
        object.__setattr__(self, "tangent_u", tangent_u)
        object.__setattr__(self, "tangent_v", tangent_v)

    @property
    def frame(self):
        """A conventional frame whose Z axis is the outward normal."""
        return Frame(self.origin, self.tangent_u, self.tangent_v, self.normal)

    def as_spatial_frame(self):
        """Adapt this contact to a SpatialFrame convention with forward along normal.

        The returned frame has ``forward == normal`` and ``right == tangent_u``.
        ``SpatialFrame`` consequently stores ``-tangent_v`` as its up axis.
        """
        return SpatialFrame(self.origin, self.normal, mul(self.tangent_v, -1))

    @classmethod
    def from_frame(cls, frame: Frame):
        return cls(frame.origin, frame.z, frame.x, frame.y)

    @classmethod
    def from_spatial_frame(cls, frame: SpatialFrame):
        return cls(frame.origin, frame.forward, frame.right, mul(frame.up, -1))

    def point(self, value):
        """Map local (u, v, normal) coordinates into model coordinates."""
        u, v, n = vector3(value, "contact-local point")
        return add(self.origin, add(add(mul(self.tangent_u, u), mul(self.tangent_v, v)),
                                    mul(self.normal, n)))

    def local(self, value):
        delta = sub(vector3(value, "point"), self.origin)
        return (dot(delta, self.tangent_u), dot(delta, self.tangent_v), dot(delta, self.normal))

    def opposite(self):
        """Return the mating contact at the same point with opposed normal."""
        return SurfaceContact(self.origin, mul(self.normal, -1), self.tangent_u,
                              mul(self.tangent_v, -1))

    def offset(self, value):
        return SurfaceContact(add(self.origin, vector3(value, "contact offset")), self.normal,
                              self.tangent_u, self.tangent_v)

    def transformed(self, *, point_transform, vector_transform):
        """Apply an affine point/vector transform while preserving outer normal.

        Reflections invert tangent handedness.  The outward normal follows the
        supplied vector transform and one tangent is flipped to restore the
        contact's required right-handed basis.
        """
        origin = point_transform(self.origin)
        normal = unit(vector_transform(self.normal))
        tangent_u = unit(vector_transform(self.tangent_u))
        tangent_v = unit(vector_transform(self.tangent_v))
        if dot(cross(tangent_u, tangent_v), normal) < 0:
            tangent_v = mul(tangent_v, -1)
        return SurfaceContact(origin, normal, tangent_u, tangent_v)


def box_surface_contacts(from_, to_):
    """Return semantic outer contacts for an axis-aligned cube/box.

    This intentionally returns value objects only.  ``ModelBuilder`` can use
    it for native cubes and primitive factories can expose the same names
    without creating a second attachment API.
    """
    low = vector3(from_, "box from")
    high = vector3(to_, "box to")
    if any(a >= b for a, b in zip(low, high)):
        raise ValueError("box contact bounds require from < to on every axis")
    center = tuple((a + b) / 2 for a, b in zip(low, high))
    return {
        "left": SurfaceContact((low[0], center[1], center[2]), (-1, 0, 0)),
        "right": SurfaceContact((high[0], center[1], center[2]), (1, 0, 0)),
        "bottom": SurfaceContact((center[0], low[1], center[2]), (0, -1, 0)),
        "top": SurfaceContact((center[0], high[1], center[2]), (0, 1, 0)),
        "back": SurfaceContact((center[0], center[1], low[2]), (0, 0, -1)),
        "front": SurfaceContact((center[0], center[1], high[2]), (0, 0, 1)),
    }


def linear_falloff(t):
    """Linear per-vertex weight factor: 1 at ``t=0`` falling to 0 at ``t>=1`` (clamped).

    Turns a normalized distance into a ``weights`` factor for the
    ``translate/rotate/scale_vertices`` mesh-edit helpers.
    """
    if not math.isfinite(t): raise ValueError('Falloff input must be finite')
    return max(0.,min(1.,1-t))


def smooth_falloff(t):
    """Smooth (smoothstep) per-vertex weight factor over the ``linear_falloff`` range."""
    w = linear_falloff(t)
    return w*w*(3-2*w)
