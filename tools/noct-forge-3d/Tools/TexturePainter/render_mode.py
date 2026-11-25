"""Render mode of an asset: pixel art or smooth, declared once per asset and applied by every paint operation.

The asset's ``texture_filter`` picks the mode: ``nearest`` is pixel art, ``linear`` is smooth (the filter the
texture is viewed with decides how it must be painted). An optional ``render`` object in the asset record
overrides the preset values::

    "texture_filter": "linear",
    "render": {"density": 16, "padding": 4, "aa": 1.0, "samples": 4, "reference": 8}

density    texels per model unit the UV packs at (``forge uv --uv-scale``; used when an asset is created, for
           example by ``forge asset twin``)
padding    texels around every UV island (``--island-padding``); smooth textures dilate the whole padding
aa         smooth mode: width of the anti-aliasing box in texels (1 = exact area coverage, no blur)
samples    smooth mode: subsamples per texel side (4 = 16 per texel) for coverage and colour averaging
reference  texels per model unit that stroke widths are written in: a width of 2 is 2 texels at this
           density, the same size on the model at any density (pixel art default: the asset's own density)
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

MODES = ("pixel", "smooth")
PRESETS = {
    "pixel": dict(density=8, padding=1, aa=0.0, samples=1, reference=None),
    "smooth": dict(density=16, padding=4, aa=1.0, samples=4, reference=8),
}
_KEYS = ("density", "padding", "aa", "samples", "reference")


@dataclass(frozen=True)
class RenderMode:
    mode: str = "pixel"
    density: int = 8
    padding: int = 1
    aa: float = 0.0
    samples: int = 1
    reference: Optional[float] = None

    @property
    def smooth(self) -> bool:
        return self.mode == "smooth"

    def width_scale(self, uv_scale: float) -> float:
        """Texels per reference texel at ``uv_scale`` (1 when widths are already texels)."""
        return 1.0 if not self.reference else float(uv_scale) / float(self.reference)

    def offsets(self, box: Optional[float] = None):
        """Subsample offsets from a texel centre, in texels: a ``samples`` x ``samples`` grid over a box of
        ``box`` (default ``aa``) texels."""
        n = self.samples if self.smooth else 1
        size = self.aa if box is None else box
        if n <= 1 or size <= 0:
            return ((0.0, 0.0),)
        steps = [((i + 0.5) / n - 0.5) * size for i in range(n)]
        return tuple((dx, dy) for dy in steps for dx in steps)


def _check(values):
    if not isinstance(values["density"], int) or isinstance(values["density"], bool) or values["density"] <= 0:
        raise ValueError("render.density must be a positive integer (texels per model unit)")
    if not isinstance(values["padding"], int) or isinstance(values["padding"], bool) or values["padding"] < 0:
        raise ValueError("render.padding must be a non-negative integer")
    if not isinstance(values["samples"], int) or isinstance(values["samples"], bool) or not 1 <= values["samples"] <= 8:
        raise ValueError("render.samples must be an integer from 1 to 8")
    if not isinstance(values["aa"], (int, float)) or not 0 <= values["aa"] <= 4:
        raise ValueError("render.aa must be a number of texels from 0 to 4")
    reference = values["reference"]
    if reference is not None and (not isinstance(reference, (int, float)) or reference <= 0):
        raise ValueError("render.reference must be a positive number of texels per model unit")


def from_record(record: Optional[dict]) -> RenderMode:
    """The render mode of an asset record (``project.json``); pixel art when there is none."""
    record = record or {}
    mode = "smooth" if record.get("texture_filter", "nearest") == "linear" else "pixel"
    overrides = record.get("render") or {}
    if not isinstance(overrides, dict):
        raise ValueError("render must be an object")
    unknown = sorted(set(overrides) - set(_KEYS))
    if unknown:
        raise ValueError(f"render: unknown keys {unknown}; valid: {list(_KEYS)}")
    values = {**PRESETS[mode], **overrides}
    _check(values)
    return RenderMode(mode, int(values["density"]), int(values["padding"]), float(values["aa"]),
                      int(values["samples"]), None if values["reference"] is None else float(values["reference"]))


def preset(mode: str, **overrides) -> RenderMode:
    if mode not in MODES:
        raise ValueError(f"render mode must be one of {MODES}")
    values = {**PRESETS[mode], **overrides}
    _check(values)
    return replace(RenderMode(mode), **values)


def for_model(bbmodel_path) -> RenderMode:
    """Render mode of the registered asset owning ``bbmodel_path``; pixel art for an unregistered model."""
    try:
        from Tools._resolve import resolve_asset
        record = resolve_asset(bbmodel_path).record
    except (ValueError, KeyError, OSError):
        return RenderMode()
    return from_record(record)
