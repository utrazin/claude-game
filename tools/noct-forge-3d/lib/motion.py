"""Small, generic motion helpers for animation recipes: smooth transitions, periodic curves and springs.

Everything is deterministic, so recipes stay reproducible. ``quintic`` and ``periodic_curve`` take numbers
(call them once per axis for a vector), ``spring_follow`` takes points (3-vectors), ``periodic`` and
``smooth_periodic`` take either.
Typical uses: blend two phases of a cycle with matching speeds (``quintic``), drive a looping value
through a few keys (``periodic_curve``), let a point trail another with inertia (``spring_follow``).
"""
from __future__ import annotations

import math
from typing import Callable, Sequence


def _lerp(a, b, k):
    if isinstance(a, tuple):
        return tuple(p + (q - p) * k for p, q in zip(a, b))
    return a + (b - a) * k


def quintic(p0: float, p1: float, v0: float, v1: float, s: float) -> float:
    """Value going from ``p0`` (s = 0) to ``p1`` (s = 1) with slopes ``v0`` and ``v1`` (per unit of s)
    and no acceleration at either end.

    Use it to join two phases of a motion without a jolt: pass each phase's speed at the joint,
    multiplied by the duration that ``s`` spans.
    """
    s3, s4, s5 = s ** 3, s ** 4, s ** 5
    return (p0 * (1 - 10 * s3 + 15 * s4 - 6 * s5) + v0 * (s - 6 * s3 + 8 * s4 - 3 * s5)
            + p1 * (10 * s3 - 15 * s4 + 6 * s5) + v1 * (-4 * s3 + 7 * s4 - 3 * s5))


def periodic(samples: Sequence, period: float) -> Callable[[float], object]:
    """Function of time interpolating evenly spaced ``samples`` (numbers or 3-vectors) over one ``period``,
    repeating outside it. ``samples[i]`` is the value at ``i * period / len(samples)``."""
    values, count = list(samples), len(samples)
    if count < 2:
        raise ValueError("periodic needs at least two samples")
    if period <= 0:
        raise ValueError("period must be positive")

    def value(t: float):
        x = (t % period) / period * count
        i = int(x) % count
        return _lerp(values[i], values[(i + 1) % count], x - int(x))
    return value


def periodic_curve(keys: Sequence[tuple[float, float]], x: float) -> float:
    """Value at ``x`` of a looping curve through ``(x, value)`` keys with x in [0, 1).

    The curve has continuous value and slope everywhere, including across the loop. Its slope is zero
    at keys that are plateaus or turning points, so it never overshoots between keys: a value held
    between two equal keys stays exactly there.
    """
    ordered = sorted(keys)
    xs, vs = [k for k, _ in ordered], [v for _, v in ordered]
    n = len(ordered)
    if n < 2 or any(not 0 <= k < 1 for k in xs) or len(set(xs)) != n:
        raise ValueError("periodic_curve needs at least two keys with distinct x in [0, 1)")
    x %= 1.0
    i = max((j for j in range(n) if xs[j] <= x), default=n - 1)
    wrap = 1.0 if x < xs[0] else 0.0                    # x before the first key: segment from the last
    x0 = xs[i] - wrap
    x1 = xs[(i + 1) % n] + (1.0 if i + 1 == n else 0.0) - wrap
    xm = xs[i - 1] - (1.0 if i == 0 else 0.0) - wrap
    x2 = xs[(i + 2) % n] + (1.0 if i + 2 >= n else 0.0) - wrap
    pm, p0, p1, p2 = vs[i - 1], vs[i], vs[(i + 1) % n], vs[(i + 2) % n]
    m0 = (p1 - pm) / (x1 - xm) * (x1 - x0)              # Catmull-Rom slopes, scaled to this segment
    m1 = (p2 - p0) / (x2 - x0) * (x1 - x0)
    if (p0 - pm) * (p1 - p0) <= 0:
        m0 = 0.0
    if (p1 - p0) * (p2 - p1) <= 0:
        m1 = 0.0
    s = (x - x0) / (x1 - x0)
    s2, s3 = s * s, s * s * s
    return (2 * s3 - 3 * s2 + 1) * p0 + (s3 - 2 * s2 + s) * m0 + (-2 * s3 + 3 * s2) * p1 + (s3 - s2) * m1


def spring_follow(target: Callable[[float], tuple], frequency: float, damping: float, period: float, *,
                  rate: int = 240, cycles: int = 3) -> Callable[[float], tuple]:
    """A point pulled toward ``target(t)`` by a damped spring, for a motion repeating every ``period``.

    The spring is simulated for ``cycles`` periods so it settles into its repeating motion, and the last
    one is returned as a looping function of time. ``frequency`` (Hz) sets how quickly it catches up and
    ``damping`` (1 = no overshoot) how much it swings past. Use it to make a point trail another with
    inertia, then aim or reach a control at it.
    """
    if frequency <= 0 or damping < 0 or period <= 0:
        raise ValueError("frequency and period must be positive and damping non-negative")
    omega, dt = 2 * math.pi * frequency, 1.0 / rate
    substeps = max(1, math.ceil(omega * dt / 0.1))      # keep each integration step well inside stability
    h = dt / substeps
    steps = max(2, round(period * rate))
    position = tuple(float(v) for v in target(0.0))
    velocity, last = (0.0, 0.0, 0.0), []
    for step in range(steps * cycles):
        for sub_step in range(substeps):
            goal = target((step * dt + sub_step * h) % period)
            accel = tuple(omega * omega * (g - p) - 2 * damping * omega * v
                          for g, p, v in zip(goal, position, velocity))
            velocity = tuple(v + a * h for v, a in zip(velocity, accel))
            position = tuple(p + v * h for p, v in zip(position, velocity))
        if step >= steps * (cycles - 1):
            last.append(position)
    return periodic(last, period)


def smooth_periodic(samples: Sequence, period: float, seconds: float) -> list:
    """``samples`` (numbers or 3-vectors) evenly spaced over one ``period``, blurred by a Gaussian of
    ``seconds`` (one standard deviation) that wraps around the loop. Softens corners in a repeating curve
    without moving its mean. Returns the blurred samples as a list; pass it to ``periodic`` for a
    function of time."""
    count = len(samples)
    if count < 2 or period <= 0 or seconds < 0:
        raise ValueError("smooth_periodic needs two samples, a positive period and non-negative seconds")
    if isinstance(samples[0], (tuple, list)):
        axes = [smooth_periodic([sample[axis] for sample in samples], period, seconds)
                for axis in range(len(samples[0]))]
        return [tuple(values) for values in zip(*axes)]
    sigma = seconds / period * count
    if sigma < 1e-9:
        return list(samples)
    reach = int(3 * sigma) + 1
    kernel = [math.exp(-0.5 * (k / sigma) ** 2) for k in range(-reach, reach + 1)]
    total = sum(kernel)
    return [sum(w * samples[(i + k - reach) % count] for k, w in enumerate(kernel)) / total
            for i in range(count)]
