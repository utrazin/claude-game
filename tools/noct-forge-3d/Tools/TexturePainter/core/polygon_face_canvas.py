"""Masked face canvas for arbitrary polygon UV islands."""
from functools import lru_cache

import numpy as np
from PIL import Image

from .face_canvas import FaceCanvas
from .surface_sampling import _clip_rows, python_sum

# A texel square can only touch the polygon boundary when its center is within
# half a diagonal (~0.7071) of an edge; a small margin keeps the test conservative.
_BOUNDARY_REACH = 0.75


def _conservative_pixel(points, x, y):
    """Exact test: does the polygon cover a positive area of texel (x, y)?"""
    clipped = list(points)
    for axis, boundary, sign in ((0, x, 1), (0, x + 1, -1), (1, y, 1), (1, y + 1, -1)):
        output = []
        for a, b in zip(clipped, clipped[1:] + clipped[:1]):
            ain = (a[axis] - boundary) * sign >= 0
            bin = (b[axis] - boundary) * sign >= 0
            if ain != bin:
                t = (boundary - a[axis]) / (b[axis] - a[axis])
                output.append(tuple(a[i] + t * (b[i] - a[i]) for i in range(2)))
            if bin:
                output.append(b)
        clipped = output
        if not clipped:
            break
    area = abs(sum((a[0] - x) * (b[1] - y) - (b[0] - x) * (a[1] - y)
                   for a, b in zip(clipped, clipped[1:] + clipped[:1])))
    # Ignore numerical corner/edge touches; they have no positive
    # texel area and otherwise disagree with surface sampling.
    return area > 2e-9


def _centers_inside(width, height, points):
    """Even-odd test of every texel center, same arithmetic as a per-pixel ray cast."""
    px, py = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    inside = np.zeros((height, width), dtype=bool)
    j = len(points) - 1
    for i in range(len(points)):
        xi, yi = points[i]
        xj, yj = points[j]
        straddle = (yi > py) != (yj > py)
        if straddle.any():
            with np.errstate(divide="ignore", invalid="ignore"):
                crossing = (xj - xi) * (py - yi) / (yj - yi) + xi
            inside ^= straddle & (px < crossing)
        j = i
    return inside, px, py


def _near_boundary(px, py, points):
    """Texels whose square may touch a polygon edge."""
    near = np.zeros(px.shape, dtype=bool)
    for (ax, ay), (bx, by) in zip(points, points[1:] + points[:1]):
        dx, dy = bx - ax, by - ay
        length = dx * dx + dy * dy
        t = np.zeros(px.shape) if length == 0 else np.clip(((px - ax) * dx + (py - ay) * dy) / length, 0.0, 1.0)
        near |= np.hypot(px - (ax + t * dx), py - (ay + t * dy)) <= _BOUNDARY_REACH
    return near


def _conservative_rows(points, xs, ys):
    """Vectorized ``_conservative_pixel`` for texels (xs, ys)."""
    left, top = xs.astype(float), ys.astype(float)
    cx, cy, counts = _clip_rows(points, left, top, left + 1, top + 1, epsilon=0.0)
    rows = np.arange(len(xs))
    terms = []
    for k in range(cx.shape[1]):
        valid = k < counts
        following = np.where(valid, (k + 1) % np.maximum(counts, 1), 0)
        ax, ay = cx[:, k], cy[:, k]
        bx, by = cx[rows, following], cy[rows, following]
        terms.append(np.where(valid, (ax - left) * (by - top) - (bx - left) * (ay - top), 0.0))
    return np.abs(python_sum(terms)) > 2e-9


@lru_cache(maxsize=4096)
def _mask_bytes(width, height, points, conservative):
    inside, px, py = _centers_inside(width, height, list(points))
    if conservative:
        # Away from the boundary a texel is fully inside or fully outside; only
        # texels touching an edge need the exact clipped area.
        ys, xs = np.nonzero(_near_boundary(px, py, list(points)))
        if len(xs):
            inside[ys, xs] = _conservative_rows(points, xs, ys)
    return (inside.astype(np.uint8) * 255).tobytes()


def polygon_mask(width, height, points, conservative=False):
    """Rasterize polygon coverage by testing deterministic pixel centers.

    ``conservative`` instead marks every texel the polygon covers with positive area.
    """
    key = tuple(tuple(point) for point in points)
    return Image.frombytes("L", (width, height), _mask_bytes(int(width), int(height), key, bool(conservative)))


class PolygonFaceCanvas(FaceCanvas):
    """
    FaceCanvas com máscara pré-calculada para contornos de polígonos arbitrários.
    Herda nativamente todas as primitivas de FaceCanvas com clipping automático.
    """
    def __init__(self, width, height, points, default_color=(0, 0, 0, 0), *, conservative=True, mask=None):
        """``mask`` (bool array, height x width) replaces the polygon coverage: faces of a UV chart own
        exactly the texels the parser assigned them."""
        self.points = tuple(tuple(point) for point in points)
        if mask is not None:
            # a chart face may own no texel at all (a sliver whose texel a neighbour owns): an empty canvas
            mask = Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255, "L")
        else:
            mask = polygon_mask(int(width), int(height), self.points, conservative)
            if not mask.getbbox():
                raise ValueError("Polygon UV does not cover any texture pixel")
        super().__init__(width, height, default_color, mask=mask)
