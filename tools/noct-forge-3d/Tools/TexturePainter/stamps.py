"""Stamp engine: strokes of stamps laid over the model's 3D surface.

Every painted mark that is not a flat projection goes through here: brush layers over a material (short grainy
strokes), fur tufts (long tapered strokes out of a point), scattered or regular prints (``Tip.image``), and stamped
lines. The look of a mark is described by tokens (``Tools.TexturePainter.marks``): the ``Tip`` (what one stamp
leaves), the ``Brush`` (how a stroke of stamps moves), the ``Pattern`` (where strokes start).

How a stamp lands: its centre sits on the surface and it faces along the normal there. A texel takes ink when it
lies inside the stamp's outline (a ragged disc, or the motif's alpha), faces the same way, is close to the stamp's
plane and lies on the surface layer the stamp sits on (``occlusion``: of two layers under the same spot, such as a
cloak over a robe, only the one nearest the stamp is painted). Inside the outline the grain, turned with the stamp,
decides: a texel is ink where the grain is above ``1 - density * pressure * falloff``, so light pressure leaves
scattered hard specks and the stamp ends in scattered grain.

``lay`` computes the hits of a set of strokes; a ``TexelLayer`` collects them as a transparent layer over the texels
(premultiplied colour and the share of what is under it that still shows), the same result as painting each stroke
directly, and composites onto an image of the texels or onto the canvases.
"""
from __future__ import annotations

import colorsys
from dataclasses import dataclass
import math
from typing import Optional, Sequence

import numpy as np

from .core.color import parse_color
from .marks import Brush, Direction, Pattern, Tip

LAYER_DEPTH = 1.5        # texels: hits this close to the nearest layer under a stamp belong to the same surface


# ---------------------------------------------------------------- per-texel layers
class TexelLayer:
    """A transparent paint layer over ``count`` texels: premultiplied colour (N, 3) and ``keep``, the share of what
    is under it that still shows (N). Strokes laid on it, then composited onto an image, give exactly the image the
    same strokes laid on the image directly would (every stroke is ``under * (1 - a) + colour * a``)."""

    def __init__(self, count):
        self.color = np.zeros((count, 3))
        self.keep = np.ones(count)

    def lay(self, texel, colors, alpha):
        """Lay colours (K, 3) on texels with alpha (K,) or one alpha."""
        alpha = np.asarray(alpha, dtype=float)
        if alpha.ndim == 0:
            alpha = np.full(len(texel), float(alpha))
        self.color[texel] = self.color[texel] * (1 - alpha[:, None]) + colors * alpha[:, None]
        self.keep[texel] = self.keep[texel] * (1 - alpha)

    def over(self, image):
        """``image`` (N, 3) with this layer on top (in place)."""
        image *= self.keep[:, None]
        image += self.color
        return image

    def mirror(self, partner, copy):
        """Copy every source texel onto its mirror image (``SurfaceView.mirror_of``): an exactly symmetric layer."""
        has = copy & (partner >= 0)
        self.color[has] = self.color[partner[has]]
        self.keep[has] = self.keep[partner[has]]

    def rgba(self):
        """(indices, RGBA rows) of the texels this layer covers at all, as straight colour and alpha."""
        idx = np.flatnonzero(self.keep < 1.0)
        alpha = 1.0 - self.keep[idx]
        rgb = self.color[idx] / alpha[:, None]
        return idx, np.concatenate([rgb, alpha[:, None] * 255.0], axis=1)


@dataclass
class Hits:
    """The texels a set of strokes reaches: ``texel`` indices, their ``colors`` (K, 3) and ``alpha`` (K,), one hit
    per texel (the last stamp over a texel wins, as in a painted layer); ``strokes`` and ``stamps`` counted."""
    texel: np.ndarray
    colors: np.ndarray
    alpha: np.ndarray
    strokes: int
    stamps: int
    overlap: Optional[np.ndarray] = None

    def additive(self, opacity):
        """Alpha (K,) when ``opacity`` belongs to each stroke: a texel covered by n strokes gets
        ``1 - (1 - alpha * opacity) ** n``, so overlapping strokes add up instead of merging."""
        a = np.clip(self.alpha * float(opacity), 0.0, 1.0)
        return 1.0 - (1.0 - a) ** (np.ones(len(a)) if self.overlap is None else self.overlap)


# ---------------------------------------------------------------- colour
def jitter_color(rgb, rng, jitter):
    """``rgb`` with its hue turned by a normal of ``jitter[0]`` degrees and saturation / lightness scaled by
    ``1 + normal(jitter[1] / jitter[2])``."""
    h, l, s = colorsys.rgb_to_hls(*(np.asarray(rgb, dtype=float) / 255.0))
    h = (h + rng.normal(0, jitter[0] / 360.0)) % 1.0
    s = min(1.0, max(0.0, s * (1.0 + rng.normal(0, jitter[1]))))
    l = min(1.0, max(0.0, l * (1.0 + rng.normal(0, jitter[2]))))
    return np.array(colorsys.hls_to_rgb(h, l, s)) * 255.0


# ---------------------------------------------------------------- strokes -> stamps
_KEYS = ("centre", "normal", "d", "side", "r", "theta", "cos", "sin", "offset", "stroke", "bound", "along",
         "shift")


def _stamp_arrays(out):
    return {key: np.asarray(value, dtype=np.int64 if key == "stroke" else float) for key, value in out.items()}


def straight_strokes(view, starts, brush: Brush, colors, rng, size, tip_colors=None, tip_seed=0):
    """Straight strokes from each start texel along the brush's direction (projected on the surface there), centred
    on the start. The random choices are drawn in a fixed order (direction jitter, radius, length, colour, tip angle
    and offset, then each stamp's size), so the painting depends only on the seed. Returns (stamps, colors)."""
    out = {key: [] for key in _KEYS}
    direction = brush.direction or Direction.around()
    directions = direction(view.centre[starts], view.normal[starts])
    stroke_colors = []
    for s, start in enumerate(starts.tolist()):
        n = view.normal[start]
        d = directions[s] - n * float(directions[s] @ n)
        if np.linalg.norm(d) < 1e-6:
            d = np.cross(n, [0.0, 0.0, 1.0])
            if np.linalg.norm(d) < 1e-6:
                d = np.cross(n, [1.0, 0.0, 0.0])
        d /= np.linalg.norm(d)
        angle = math.radians(rng.normal(0.0, brush.spread))
        side = np.cross(n, d)
        d = d * math.cos(angle) + side * math.sin(angle)
        radius = rng.uniform(*brush.stamp_radius())
        count = int(rng.integers(brush.length[0], brush.length[1] + 1))
        stroke_colors.append(jitter_color(colors[int(rng.integers(len(colors)))], rng, brush.jitter))
        theta = rng.uniform(0, 2 * math.pi)
        offset = rng.uniform(0, size, 2)
        centre = view.centre[start] - d * radius * brush.spacing * (count - 1) / 2
        for k in range(count):
            r_k = radius * rng.uniform(*brush.size_jitter)
            if brush.taper > 0 and count > 1:          # a tapered stroke (a hair) thins towards both ends
                mid = (count - 1) / 2
                r_k *= 1.0 - brush.taper * abs(k - mid) / mid
            turn = theta * (1.0 - brush.align) + math.radians(brush.turn) * k
            # the stamp frame (d, side) is skewed by the stroke angle a: u^2 + v^2 < r^2 holds within a^2 + b^2 <
            # r^2 / (1 - |sin a|) in the orthonormal frame, and |w| < 0.6 r: far texels are dropped early by that
            bound = 1.0 / max(1.0 - abs(math.sin(angle)), 1e-3) + 0.36 + 1e-9
            for key, value in (("centre", centre + d * radius * brush.spacing * k), ("normal", n), ("d", d),
                               ("side", side), ("r", r_k), ("theta", theta), ("cos", math.cos(turn)),
                               ("sin", math.sin(turn)), ("offset", offset), ("stroke", s), ("bound", bound),
                               ("along", k / (count - 1) if count > 1 else 0.0), ("shift", 0.0)):
                out[key].append(value)
    stamps = _stamp_arrays(out)
    if not len(stamps["r"]):
        return stamps, np.zeros((0, 3))
    root = np.asarray(stroke_colors, dtype=float)[stamps["stroke"]]
    if tip_colors is None:
        return stamps, root
    # a gradient along each stroke (a lock of fur: dark root, light tip); its colours come from a generator of their
    # own, so the strokes themselves are the same as without it
    tip_rng = np.random.default_rng(tip_seed + 7919)
    ends = np.array([jitter_color(tip_colors[int(tip_rng.integers(len(tip_colors)))], tip_rng, brush.jitter)
                     for _ in range(len(stroke_colors))])[stamps["stroke"]]
    t = stamps["along"][:, None]
    return stamps, root * (1.0 - t) + ends * t


def path_strokes(view, pieces, brush: Brush, colors, rng, size, radius):
    """Strokes of stamps along lines on the surface (stamped lines): a stamp every ``spacing * radius``, facing the
    nearest texel's normal and turning with the path; ``radius`` the line's half width (model units).

    ``pieces``: 3D polylines, or ``PathPiece``s when one line was cut into pieces (a 2D path lifted onto several
    UV charts): each piece knows the distance of its points along the whole line, the line's length, whether it
    is closed and which line it belongs to, so the width profile (``taper`` to points within ``taper_length`` of
    the ends, the smooth ``swell``), the grain and the colour run along the whole line, not along each piece."""
    pieces = [p if isinstance(p, PathPiece) else PathPiece.of(p, number) for number, p in enumerate(pieces)]
    out = {key: [] for key in _KEYS}
    stroke_colors, lines, strokes = [], [], {}
    for piece in pieces:                            # stamp centres and path directions first, normals in one search
        points = np.asarray(piece.points, dtype=float)
        seg = np.linalg.norm(np.diff(points, axis=0), axis=1)
        length = float(seg.sum())
        if length <= 0:
            continue
        count = max(1, int(math.floor(length / max(brush.spacing * radius, 1e-4))) + 1)
        at = np.linspace(0.0, length, count)
        cum = np.r_[0.0, np.cumsum(seg)]
        i = np.minimum(np.searchsorted(cum, at, side="right") - 1, len(seg) - 1)
        t = np.where(seg[i] > 0, (at - cum[i]) / np.where(seg[i] > 0, seg[i], 1.0), 0.0)
        arc = np.interp(at, cum, piece.arc)          # where each stamp lies along the whole line
        lines.append((points[i] + (points[i + 1] - points[i]) * t[:, None], points[i + 1] - points[i], arc, piece))
    normals = nearest_normals(view, np.concatenate([c for c, _, _, _ in lines])) if lines else np.zeros((0, 3))
    first = 0
    for centres, tangents, arc, piece in lines:
        if piece.line not in strokes:               # one colour, grain offset and swell per line
            stroke_colors.append(jitter_color(colors[int(rng.integers(len(colors)))], rng, brush.jitter))
            strokes[piece.line] = (len(stroke_colors) - 1, rng.uniform(0, 2 * math.pi), rng.uniform(0, size, 2),
                                   rng.uniform(0, 2 * math.pi, 2))
        stroke, theta, offset, phase = strokes[piece.line]
        profile = width_profile(brush, arc, piece.total, piece.closed, phase)
        for k in range(len(centres)):
            centre, n = centres[k], normals[first + k]
            d = tangents[k] - n * float(tangents[k] @ n)
            d = d / max(np.linalg.norm(d), 1e-9)
            r_k = radius * brush.size * rng.uniform(*brush.size_jitter) * profile[k]
            turn = theta * (1.0 - brush.align) + math.radians(brush.turn) * k
            for key, value in (("centre", centre), ("normal", n), ("d", d), ("side", np.cross(n, d)), ("r", r_k),
                               ("theta", theta), ("cos", math.cos(turn)), ("sin", math.sin(turn)),
                               ("offset", offset), ("stroke", stroke), ("bound", 1.36 + 1e-9),
                               ("along", arc[k] / piece.total if piece.total > 0 else 0.0), ("shift", arc[k])):
                out[key].append(value)
        first += len(centres)
    stamps = _stamp_arrays(out)
    if not len(stamps["r"]):
        return stamps, np.zeros((0, 3))
    return stamps, np.asarray(stroke_colors, dtype=float)[stamps["stroke"]]


@dataclass
class PathPiece:
    """A piece of a line: its 3D ``points``, the distance of each along the whole line (``arc``), the line's
    length (``total``), whether the line is closed and which line it is (``line``)."""
    points: np.ndarray
    arc: np.ndarray
    total: float
    closed: bool
    line: int

    @classmethod
    def of(cls, points, line):
        """A whole line as one piece (closed when its ends meet)."""
        points = np.asarray(points, dtype=float)
        arc = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(points, axis=0), axis=1))]
        closed = len(points) > 2 and bool(np.allclose(points[0], points[-1]))
        return cls(points, arc, float(arc[-1]), closed, line)


def width_profile(brush: Brush, arc, total, closed, phase=(0.0, 0.0)):
    """Width factor of stamps at distances ``arc`` along a line of length ``total``: the ``taper`` to points at the
    ends (only within ``taper_length`` of them when given, and never more than a quarter of the line from each end;
    none on a closed line) and the smooth ``swell``."""
    arc = np.asarray(arc, dtype=float)
    factor = np.ones(len(arc))
    if brush.taper > 0 and not closed and total > 0:
        if brush.taper_length is None:
            factor *= 1.0 - brush.taper * np.abs(2.0 * arc / total - 1.0)
        else:
            end = np.minimum(arc, total - arc)
            reach = min(brush.taper_length, 0.25 * total)      # a short line keeps a full-width middle
            x = np.clip(end / reach, 0.0, 1.0)
            factor *= 1.0 - brush.taper * (1.0 - x) ** 2
    if brush.swell > 0:
        u = arc / brush.swell_length
        factor *= 1.0 + brush.swell * (0.65 * np.sin(2 * math.pi * u + phase[0])
                                       + 0.35 * np.sin(2 * math.pi * 2.17 * u + phase[1]))
    return factor


def nearest_normals(view, points, where=None):
    """The normal of the texel nearest each point (searched in growing cells, so it costs little); ``where``
    (bool per texel) limits the search to those texels."""
    points = np.asarray(points, dtype=float)
    out = np.zeros((len(points), 3))
    if not len(points):
        return out
    cell = 2.0 * texel_size(view)
    among = np.arange(view.count) if where is None else np.flatnonzero(where)
    if not len(among):
        return out
    grid = _Grid(view.centre, among, cell, 1)
    todo = np.arange(len(points))
    for reach in (1, 2, 4, 8):
        stamp, idx = grid.pairs(points[todo], np.full(len(todo), reach))
        if len(stamp):
            d = np.linalg.norm(view.centre[idx] - points[todo][stamp], axis=1)
            order = np.lexsort((d, stamp))
            firsts = order[np.r_[True, stamp[order][1:] != stamp[order][:-1]]]
            out[todo[stamp[firsts]]] = view.normal[idx[firsts]]
            found = np.zeros(len(todo), dtype=bool)
            found[stamp[firsts]] = True
            todo = todo[~found]
        if not len(todo):
            return out
    for p in todo.tolist():                             # far from every texel: the global nearest
        out[p] = view.normal[among[int(np.argmin(np.linalg.norm(view.centre[among] - points[p], axis=1)))]]
    return out


# ---------------------------------------------------------------- candidates
class _Grid:
    """Texels in cubic cells of size ``cell``. ``pairs`` lists the (stamp, texel) candidates of many stamps at once:
    the cells within ``reach`` of each stamp's cell (a stamp of radius r looks ``ceil(r / cell)`` cells around)."""

    def __init__(self, positions, indices, cell, max_reach):
        self.indices, self.cell = indices, cell
        keys = np.floor(positions[indices] / cell).astype(np.int64)
        self.low = keys.min(axis=0) - max_reach
        keys -= self.low
        self.dims = keys.max(axis=0) + max_reach + 1
        code = (keys[:, 0] * self.dims[1] + keys[:, 1]) * self.dims[2] + keys[:, 2]
        self.order = np.argsort(code, kind="stable")
        self.codes = code[self.order]

    def pairs(self, centres, reach):
        """(stamp index, texel index) pairs, grouped by stamp in stamp order."""
        base = np.floor(centres / self.cell).astype(np.int64) - self.low
        stamps, texels = [], []
        for r in np.unique(reach):
            which = np.flatnonzero(reach == r)
            span = range(-int(r), int(r) + 1)
            offsets = np.array([(a, b, c) for a in span for b in span for c in span])
            cells = base[which][:, None, :] + offsets[None, :, :]
            valid = ((cells >= 0) & (cells < self.dims)).all(axis=2)
            code = (cells[..., 0] * self.dims[1] + cells[..., 1]) * self.dims[2] + cells[..., 2]
            lo = np.searchsorted(self.codes, code, side="left")
            hi = np.searchsorted(self.codes, code, side="right")
            counts = np.where(valid, hi - lo, 0).ravel()
            stamp = np.repeat(np.repeat(which, len(offsets)), counts)
            starts = np.repeat(lo.ravel(), counts)
            within = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
            stamps.append(stamp)
            texels.append(self.indices[self.order[starts + within]])
        stamp, texel = np.concatenate(stamps), np.concatenate(texels)
        order = np.argsort(stamp, kind="stable")
        return stamp[order], texel[order]


def texel_size(view, where=None):
    """Mean model-space side of a texel (from each texel's step across the canvas)."""
    sel = slice(None) if where is None else where
    area = np.linalg.norm(np.cross(view.step_x[sel], view.step_y[sel]), axis=1)
    area = area[area > 0]
    if not len(area):
        raise ValueError("stamps need texel frames (painter.surface())")
    return float(np.sqrt(area.mean()))


def _front_of_stamp(stamp, idx, u, v, w, texel):
    """Bool per (stamp, texel) pair: on the surface layer nearest the stamp's plane under each texel-sized spot of
    the stamp (a cloak over a robe: a stamp on the cloak never reaches the robe under it, and the other way round)."""
    if not len(stamp):
        return np.zeros(0, dtype=bool)
    cu = np.floor(u / texel).astype(np.int64)
    cv = np.floor(v / texel).astype(np.int64)
    cu -= cu.min()
    cv -= cv.min()
    span_u, span_v = int(cu.max()) + 1, int(cv.max()) + 1
    _, group = np.unique((stamp * span_u + cu) * span_v + cv, return_inverse=True)   # one id per spot
    depth = np.abs(w)
    nearest = np.full(group.max() + 1, np.inf)
    np.minimum.at(nearest, group, depth)
    return depth <= nearest[group] + LAYER_DEPTH * texel


# ---------------------------------------------------------------- hits
def stamp_hits(view, stamps, colors, tip: Tip, brush: Brush, seed, *, where=None, pressure=None, clip=None,
               occlusion=True, edge="hard", softness=0.08, chunk=192, trace=None):
    """The texels the stamps reach and their colour and alpha (``Hits``). ``where``: texels the stamps may touch
    (bool (N,)); ``pressure``: 0..1 per texel (None: full); ``clip``: texels that may be written (strokes still start
    and run anywhere in ``where``). ``edge``: "hard" grain (a texel is ink or not) or "soft" (the grain threshold
    eased over ``softness`` of the rank: anti-aliased specks)."""
    if edge not in ("hard", "soft"):
        raise ValueError("edge must be 'hard' or 'soft'")
    n = view.count
    where = np.ones(n, dtype=bool) if where is None else np.asarray(where, dtype=bool)
    pressure = None if pressure is None else np.clip(np.asarray(pressure, dtype=float), 0.0, 1.0)
    count = len(stamps["r"])
    empty = Hits(np.zeros(0, np.int64), np.zeros((0, 3)), np.zeros(0), 0, 0)
    if not count or not where.any():
        return empty
    texel = texel_size(view, where)
    grain = tip.field(seed)
    motif = None if tip.motif is None else tip.motif.astype(float) / 255.0
    size = grain.shape[0] if grain is not None else 1
    cell = float(stamps["r"].max())
    reach = np.maximum(1, np.ceil(stamps["r"] / cell)).astype(np.int64)
    grid = _Grid(view.centre, np.flatnonzero(where), cell, int(reach.max()))
    hit_stamp, hit_texel, hit_alpha, hit_color, reached = [], [], [], [], 0
    for begin in range(0, count, chunk):
        sl = slice(begin, begin + chunk)
        stamp, idx = grid.pairs(stamps["centre"][sl], reach[sl])
        reached += len(np.unique(stamp))
        rel = view.centre[idx] - stamps["centre"][sl][stamp]
        r_k = stamps["r"][sl][stamp]
        near = (rel * rel).sum(axis=1) < stamps["bound"][sl][stamp] * r_k * r_k
        stamp, idx, rel, r_k = stamp[near], idx[near], rel[near], r_k[near]
        if not len(stamp):
            continue
        # the stamp frame coordinates, one matrix product per stamp (the pairs are grouped by stamp)
        u, v, w, facing = (np.empty(len(idx)) for _ in range(4))
        bounds = np.flatnonzero(np.r_[True, stamp[1:] != stamp[:-1], True])
        for a, b in zip(bounds[:-1], bounds[1:]):
            s = begin + int(stamp[a])
            u[a:b], v[a:b], w[a:b] = rel[a:b] @ stamps["d"][s], rel[a:b] @ stamps["side"][s], rel[a:b] @ stamps["normal"][s]
            facing[a:b] = view.normal[idx[a:b]] @ stamps["normal"][s]
        keep = (facing > 0.2) & (np.abs(w) < 0.6 * r_k)
        if pressure is not None:
            keep &= pressure[idx] > 0
        keep &= (u * u + v * v < r_k * r_k) if motif is None else ((np.abs(u) < r_k) & (np.abs(v) < r_k))
        stamp, idx, u, v, w, r_k = stamp[keep], idx[keep], u[keep], v[keep], w[keep], r_k[keep]
        if occlusion:
            front = _front_of_stamp(stamp, idx, u, v, w, texel)
            stamp, idx, u, v, r_k = stamp[front], idx[front], u[front], v[front], r_k[front]
        cos_t, sin_t = stamps["cos"][sl][stamp], stamps["sin"][sl][stamp]
        tu, tv = u * cos_t - v * sin_t, u * sin_t + v * cos_t           # the stamp's coordinates, turned
        press = pressure[idx] if pressure is not None else np.ones(len(idx))
        theta = stamps["theta"][sl][stamp]
        if motif is None:
            ang = np.arctan2(v, u)
            edge_r = r_k * (1.0 - tip.ragged + tip.ragged * np.sin(3 * ang + theta) * np.cos(5 * ang - theta))
            falloff = np.clip((1.0 - np.sqrt(u * u + v * v) / edge_r) / brush.falloff, 0.0, 1.0)
            shape = np.ones(len(idx))
            color = None
        else:
            h, wd = motif.shape[:2]
            mx = np.clip(((tu / r_k) * 0.5 + 0.5) * wd, 0, wd - 1).astype(np.int64)
            my = np.clip(((-tv / r_k) * 0.5 + 0.5) * h, 0, h - 1).astype(np.int64)
            shape = motif[my, mx, 3]
            color = motif[my, mx, :3] * 255.0 if tip.colored else None
            falloff = np.ones(len(idx))
        push = brush.density * falloff * press
        if grain is not None:
            off = stamps["offset"][sl][stamp]
            # the grain is anchored along the stroke (``shift``: a line's arc length), so overlapping stamps of a
            # line read the same grain at the same point and it shows instead of filling in
            su = u + stamps["shift"][sl][stamp]
            cell = tip.scale * brush.grain
            pu = (su * cos_t - v * sin_t) / cell + off[:, 0]
            pv = (su * sin_t + v * cos_t) / cell + off[:, 1]
            g = grain[np.floor(pv).astype(np.int64) % size, np.floor(pu).astype(np.int64) % size]
            if edge == "hard":
                ink = (g > 1.0 - push).astype(float)
            else:
                ink = np.clip((g - (1.0 - push)) / softness + 0.5, 0.0, 1.0)
        else:
            ink = (push > 0).astype(float) if edge == "hard" else np.clip(push / max(softness, 1e-6), 0.0, 1.0)
        alpha = ink * shape
        if clip is not None:
            alpha = alpha * clip[idx]
        hit = alpha > 0
        hit_stamp.append(stamp[hit] + begin)
        hit_texel.append(idx[hit])
        hit_alpha.append(alpha[hit])
        hit_color.append(None if color is None else color[hit])
        if trace is not None:
            trace.append((stamp[hit] + begin, idx[hit]))
    if not hit_texel:
        return Hits(empty.texel, empty.colors, empty.alpha, int(stamps["stroke"].max()) + 1, reached)
    stamp, texel_i, alpha = np.concatenate(hit_stamp), np.concatenate(hit_texel), np.concatenate(hit_alpha)
    own = None if motif is None or not tip.colored else np.concatenate(hit_color)
    order = np.lexsort((stamp, texel_i))                  # per texel, the last stamp wins
    stamp, texel_i, alpha = stamp[order], texel_i[order], alpha[order]
    last = np.r_[texel_i[1:] != texel_i[:-1], True] if len(texel_i) else np.zeros(0, bool)
    rgb = (colors[stamp] if own is None else own[order])[last]
    strokes = int(stamps["stroke"].max()) + 1
    pair = np.unique(texel_i * strokes + stamps["stroke"][stamp])         # one entry per (texel, stroke)
    overlap = np.unique(pair // strokes, return_counts=True)[1].astype(float)
    return Hits(texel_i[last], rgb, alpha[last], strokes, reached, overlap)


def lay(view, pattern: Pattern, *, tip: Tip, brush: Brush, colors: Sequence, where=None, pressure=None,
        clip=None, tip_colors=None, seed=0, occlusion=True, edge="hard", softness=0.08, trace=None) -> Hits:
    """Strokes started by ``pattern`` over ``where``, made with ``brush`` and ``tip``, coloured from ``colors``
    (each stroke picks one and jitters it; ``tip_colors``: the colours its other end reaches)."""
    if not colors:
        raise ValueError("lay: give at least one colour")
    rng = np.random.default_rng(seed)
    where = np.ones(view.count, dtype=bool) if where is None else np.asarray(where, dtype=bool)
    r_mean = 0.5 * sum(brush.stamp_radius())
    l_mean = 0.5 * (brush.length[0] + brush.length[1])
    stroke_area = math.pi * r_mean ** 2 + 2 * r_mean * (l_mean - 1) * brush.spacing * r_mean
    starts = pattern.starts(view, where, rng, stroke_area, texel_size(view, where) ** 2 if where.any() else 1.0)
    grain = tip.field(seed)
    size = grain.shape[0] if grain is not None else 1
    stamps, rgb = straight_strokes(view, np.asarray(starts, dtype=np.int64), brush,
                                   _rgb(colors), rng, size,
                                   None if tip_colors is None else _rgb(tip_colors), seed)
    return stamp_hits(view, stamps, rgb, tip, brush, seed, where=where, pressure=pressure, clip=clip,
                      occlusion=occlusion, edge=edge, softness=softness, trace=trace)


def paint(view, pattern: Pattern, *, tip: Tip, brush: Brush, colors: Sequence, opacity=1.0, blend=None,
          mirror=None, **options) -> Hits:
    """``lay`` the strokes on a transparent layer and composite it onto the canvases of the painter's active layer
    (``blend``: None/"normal", "multiply", "screen", "add"); ``mirror="x"`` makes the layer exactly symmetric (the
    source half copied onto the other, through the UV charts' mirror metadata)."""
    hits = lay(view, pattern, tip=tip, brush=brush, colors=colors, **options)
    layer = TexelLayer(view.count)
    layer.lay(hits.texel, hits.colors, hits.alpha * float(opacity))
    if mirror == "x":
        layer.mirror(*view.mirror_of())
    elif mirror is not None:
        raise ValueError("mirror must be None or 'x'")
    idx, rgba = layer.rgba()
    if len(idx):
        view.write(rgba, idx, blend=blend or "normal")
    return hits


def _rgb(colors):
    """Colours (RGB(A) tuples or hex strings) as float RGB arrays."""
    if isinstance(colors, (str, bytes)) or (len(colors) in (3, 4) and all(np.isscalar(c) for c in colors)):
        colors = [colors]
    return [np.asarray(parse_color(c)[:3], dtype=float) for c in colors]
