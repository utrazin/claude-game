import random
from typing import Tuple, Union

import numpy as np

ColorType = Union[str, Tuple[int, int, int], Tuple[int, int, int, int]]

_FORMATS = "'#rgb', '#rgba', '#rrggbb', '#rrggbbaa', or an (r, g, b[, a]) tuple of 0-255 integers"


def parse_color(c: ColorType) -> Tuple[int, int, int, int]:
    """Convert a hex string or an RGB/RGBA tuple to (r, g, b, a), each 0..255."""
    if isinstance(c, (tuple, list)):
        if len(c) not in (3, 4) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in c):
            raise ValueError(f"Invalid color {c!r}: use {_FORMATS}")
        if all(v <= 1 for v in c) and any(isinstance(v, float) and v != int(v) for v in c):
            raise ValueError(f"Color {c!r} looks like 0..1 floats: colors are 0-255 integers, multiply by 255")
        channels = tuple(int(round(v)) for v in c)
        if any(not 0 <= v <= 255 for v in channels):
            raise ValueError(f"Color {c!r} has a channel outside 0-255")
        return channels if len(channels) == 4 else (*channels, 255)

    if isinstance(c, str):
        text = c.strip().lstrip('#')
        try:
            if len(text) in (3, 4):
                values = [int(ch * 2, 16) for ch in text]
            elif len(text) in (6, 8):
                values = [int(text[i:i + 2], 16) for i in range(0, len(text), 2)]
            else:
                raise ValueError
        except ValueError:
            raise ValueError(f"Invalid color {c!r}: use {_FORMATS}") from None
        return (*values, 255) if len(values) == 3 else tuple(values)

    raise TypeError(f"Unknown color type {type(c).__name__}: use {_FORMATS}")


def clamp_byte(val: float) -> int:
    return max(0, min(255, int(round(val))))

def color_add_noise(color: ColorType, variance: int, rng=None) -> Tuple[int, int, int, int]:
    """Add random brightness variation to RGB channels while preserving alpha."""
    r, g, b, a = parse_color(color)
    if a == 0 or variance <= 0:
        return (r, g, b, a)
    
    delta = (rng or random).randint(-variance, variance)
    return (
        clamp_byte(r + delta),
        clamp_byte(g + delta),
        clamp_byte(b + delta),
        a
    )

def color_lerp(c1: ColorType, c2: ColorType, t: float) -> Tuple[int, int, int, int]:
    """Linearly interpolate between two colors (t between 0.0 and 1.0)."""
    r1, g1, b1, a1 = parse_color(c1)
    r2, g2, b2, a2 = parse_color(c2)
    t = max(0.0, min(1.0, float(t)))
    return (
        clamp_byte(r1 + (r2 - r1) * t),
        clamp_byte(g1 + (g2 - g1) * t),
        clamp_byte(b1 + (b2 - b1) * t),
        clamp_byte(a1 + (a2 - a1) * t)
    )

def color_adjust_brightness(c: ColorType, factor: float) -> Tuple[int, int, int, int]:
    """Multiply RGB brightness by a factor (e.g. 1.2 brightens 20%, 0.8 darkens 20%)."""
    r, g, b, a = parse_color(c)
    return (
        clamp_byte(r * factor),
        clamp_byte(g * factor),
        clamp_byte(b * factor),
        a
    )


def blend_colors(base: ColorType, overlay: ColorType, mode: str = "normal", opacity: float = 1.0) -> Tuple[int, int, int, int]:
    """
    Combine two RGBA colors using the specified blend mode and opacity.
    Supported modes: 'replace', 'normal', 'multiply', 'screen', 'overlay' (multiply where the base is dark, screen
    where it is light), 'add'.
    """
    base_rgba = parse_color(base)
    overlay_rgba = parse_color(overlay)
    mode = str(mode).lower()
    opacity = max(0.0, min(1.0, float(opacity)))
    alpha = (overlay_rgba[3] / 255.0) * opacity

    if alpha <= 0.0:
        return base_rgba

    if mode == "replace":
        target = overlay_rgba
    elif mode == "normal":
        target = overlay_rgba
    elif mode == "multiply":
        target = tuple(base_rgba[i] * overlay_rgba[i] / 255.0 for i in range(3)) + (overlay_rgba[3],)
    elif mode == "screen":
        target = tuple(255.0 - (255.0 - base_rgba[i]) * (255.0 - overlay_rgba[i]) / 255.0 for i in range(3)) + (overlay_rgba[3],)
    elif mode == "overlay":
        target = tuple((2.0 * base_rgba[i] * overlay_rgba[i] / 255.0) if base_rgba[i] <= 127.5 else
                       (255.0 - 2.0 * (255.0 - base_rgba[i]) * (255.0 - overlay_rgba[i]) / 255.0)
                       for i in range(3)) + (overlay_rgba[3],)
    elif mode == "add":
        target = tuple(min(255.0, base_rgba[i] + overlay_rgba[i]) for i in range(3)) + (overlay_rgba[3],)
    else:
        raise ValueError(f"Unsupported blend mode: {mode!r}. Expected replace, normal, multiply, screen, overlay, or add")

    if mode == "replace" and opacity == 1.0:
        return overlay_rgba

    rgb = tuple(clamp_byte(base_rgba[i] + (target[i] - base_rgba[i]) * alpha) for i in range(3))
    out_alpha = clamp_byte(base_rgba[3] + (255.0 - base_rgba[3]) * alpha)
    return rgb + (out_alpha,)


# ---------------------------------------------------------------- row versions
# Same arithmetic as the scalar helpers, over (N, 4) arrays of 0-255 channels.

def clamp_bytes(values):
    """Row version of clamp_byte (round half to even, then clamp to 0-255)."""
    return np.clip(np.rint(values), 0, 255).astype(np.int64)


def lerp_rows(c1: ColorType, c2: ColorType, t) -> np.ndarray:
    """Row version of color_lerp for an array of t."""
    first = np.array(parse_color(c1), dtype=float)
    second = np.array(parse_color(c2), dtype=float)
    t = np.clip(np.asarray(t, dtype=float), 0.0, 1.0)[:, None]
    return clamp_bytes(first + (second - first) * t)


def blend_rows(base, overlay, mode: str = "normal", opacity: float = 1.0) -> np.ndarray:
    """Row version of blend_colors: base and overlay are (N, 4) integer arrays."""
    base = np.asarray(base, dtype=np.int64)
    overlay = np.asarray(overlay, dtype=np.int64)
    mode = str(mode).lower()
    opacity = max(0.0, min(1.0, float(opacity)))
    alpha = (overlay[:, 3] / 255.0) * opacity
    if mode in ("replace", "normal"):
        target = overlay[:, :3].astype(float)
    elif mode == "multiply":
        target = base[:, :3] * overlay[:, :3] / 255.0
    elif mode == "screen":
        target = 255.0 - (255.0 - base[:, :3]) * (255.0 - overlay[:, :3]) / 255.0
    elif mode == "overlay":
        b, o = base[:, :3].astype(float), overlay[:, :3].astype(float)
        target = np.where(b <= 127.5, 2.0 * b * o / 255.0, 255.0 - 2.0 * (255.0 - b) * (255.0 - o) / 255.0)
    elif mode == "add":
        target = np.minimum(255.0, base[:, :3] + overlay[:, :3])
    else:
        raise ValueError(f"Unsupported blend mode: {mode!r}. Expected replace, normal, multiply, screen, overlay, or add")
    if mode == "replace" and opacity == 1.0:
        result = overlay.copy()
    else:
        result = np.empty_like(base)
        result[:, :3] = clamp_bytes(base[:, :3] + (target - base[:, :3]) * alpha[:, None])
        result[:, 3] = clamp_bytes(base[:, 3] + (255.0 - base[:, 3]) * alpha)
    return np.where((alpha <= 0.0)[:, None], base, result)

