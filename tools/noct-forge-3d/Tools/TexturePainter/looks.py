"""Looks: how each material of a model is painted, as stacks of brush passes on named paint layers.

A painted texture is built in layers the theme names and orders (for example "texture", "shading", "lighting"):
the first layer is opaque (every material's flat ``base`` colour, then that layer's passes); every other layer is
transparent over it, holds its own passes and an optional ``Overlay`` (a flat colour eased in by the light: a
shadow veil, a light veil), and composites with its own blend and opacity. Each layer is written to the painter
layer of the same name, so ``painter.save(hide=("shading",))`` shows the painting without it.

    Look      one material: base colour, named colour lists, named tips, the brush, size classes, the pass stack,
              strengths, and per layer a ``LayerStyle`` (brush, tip, overlay)
    Pass      one brush pass: which colour list, where strokes start (``weight``) and how hard they press
              (``pressure``), both smooth steps of a shading field, its layer, opacity, coverage, size class, tip
    Region    part of a material painted its own way (element prefixes and/or face groups)
    Style     one look per material plus regions: one texture variant
    paint_looks(painter, style, materials, layers)   paints it

The shading fields come from the material map (``MaterialMap.value``, how lit each texel is): ``value`` is that
value normalised to the material's own range (8th to 92nd percentile), ``lit`` the same raised where the surface
faces up. What the layers mean (shade, light) is the theme's business: the engine only stacks them.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Dict, Optional, Sequence, Tuple, Union

import numpy as np

from .core.color import parse_color
from .marks import Brush, Pattern, Tip
from .stamps import TexelLayer, lay


def smoothstep(e0, e1, x):
    """0 at ``e0``, 1 at ``e1`` (decreasing when ``e0 > e1``), smooth in between."""
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _rgb(color):
    return tuple(int(c) for c in parse_color(color)[:3])


# ---------------------------------------------------------------- tokens
@dataclass(frozen=True)
class Overlay:
    """A flat ``color`` laid over a whole layer of the material, eased in along the ``lit`` field from ``ramp[0]``
    (none) to ``ramp[1]`` (``amount``): ``Overlay((0, 0, 0), 0.4, (0.75, 0.1))`` darkens the shaded side,
    ``Overlay((255, 255, 255), 0.2, (0.55, 1.0))`` lightens the lit side. ``tip`` breaks its edge with a grain
    (box-projected on the surface, cells of ``scale`` model units), shifting the field by up to ``grain``."""
    color: tuple = (0, 0, 0)
    amount: float = 0.0
    ramp: Tuple[float, float] = (0.75, 0.1)
    tip: Optional[Tip] = None
    grain: float = 0.35
    scale: float = 0.27

    def problems(self, label):
        """Problems of this overlay (empty: valid)."""
        out = []
        if not 0 <= self.amount <= 1 or not 0 <= self.grain <= 1:
            out.append(f"{label}: amount and grain must be between 0 and 1")
        if len(self.ramp) != 2 or self.ramp[0] == self.ramp[1]:
            out.append(f"{label}: ramp must be two different values")
        if self.tip is not None and not isinstance(self.tip, Tip):
            out.append(f"{label}: tip must be a Tip")
        return out


@dataclass(frozen=True)
class LayerStyle:
    """A look's settings for one paint layer: its own ``brush`` and ``tip`` (None: the look's) and an overlay."""
    brush: Optional[Brush] = None
    tip: Optional[Tip] = None
    overlay: Optional[Overlay] = None


@dataclass(frozen=True)
class Pass:
    """One brush pass of a look's stack.

    ``colors``: the name of one of the look's colour lists; ``tip_colors``: a list the strokes' far ends reach.
    ``weight``: where strokes start, a (start, end) smooth step of the shading ``field`` or None (everywhere);
    ``pressure``: a smooth step or a constant, reshaped as ``pressure * scale + offset``.
    ``layer``: the paint layer it belongs to; ``strength``: a strength of the look multiplying its opacity.
    ``size``: a size class of the look (stamp radius before the brush's ``size``); ``tip``: a tip of the look;
    ``grain``: multiplies the tip's grain size. ``seed``: offsets the pass's random seed. ``brush``: this pass's own
    brush (None: its layer's), so one layer can mix strokes (fur tufts and chalk patches).
    ``texel``: instead of strokes, a regular pattern ``texel(x, y) -> coverage 0..1`` of the atlas texel
    coordinates (stitches, weaves); it lays the first colour of ``colors`` at ``opacity`` times that coverage.
    ``additive``: ``opacity`` belongs to each stroke, so strokes overlapping on a texel add up
    (``1 - (1 - opacity) ** strokes``) instead of the pass being laid once at ``opacity``.
    ``even``: strokes start evenly spread (``Pattern.even``) instead of by chance, so no clumps and no holes.
    ``curve``: the start ``weight`` raised to this power: above 1 the strokes thin out towards the edge of the
    weighted area and are densest at its core."""
    name: str
    colors: str
    weight: Optional[Tuple[float, float]]
    pressure: Union[Tuple[float, float], float]
    opacity: float
    coverage: float
    size: str = "big"
    tip: str = "tip"
    grain: float = 1.0
    field: str = "value"
    scale: float = 1.0
    offset: float = 0.0
    layer: str = "texture"
    strength: Optional[str] = None
    seed: int = 0
    tip_colors: Optional[str] = None
    brush: Optional[Brush] = None
    texel: Optional[Callable] = None
    additive: bool = False
    even: bool = False
    curve: float = 1.0

    def problems(self, label, look, layers):
        """Problems of this pass against its look and the theme's layers."""
        out = []
        for key in ("colors", "tip_colors"):
            name = getattr(self, key)
            if name is not None and name not in look.colors:
                out.append(f"{label}: {key} {name!r} is not a colour list of the look ({sorted(look.colors)})")
        if self.size not in look.sizes:
            out.append(f"{label}: size {self.size!r} not in the look's sizes {sorted(look.sizes)}")
        if self.tip not in look.tips:
            out.append(f"{label}: tip {self.tip!r} not in the look's tips {sorted(look.tips)}")
        if self.field not in ("value", "lit"):
            out.append(f"{label}: field must be 'value' or 'lit'")
        if layers and self.layer not in layers:
            out.append(f"{label}: layer {self.layer!r} not in the theme's layers {list(layers)}")
        if self.strength is not None and self.strength not in look.strengths:
            out.append(f"{label}: strength {self.strength!r} not in the look's strengths {sorted(look.strengths)}")
        if not 0 <= self.opacity <= 1 or not self.coverage > 0 or not self.grain > 0:
            out.append(f"{label}: opacity 0..1, a positive coverage and grain")
        return out


@dataclass(frozen=True)
class Look:
    """How one material is painted. ``colors``: named colour lists (strokes pick one colour of a list);
    ``tips``: named tips (``Pass.tip`` picks one; "tip" is the default); ``brush``: the strokes;
    ``sizes``: named (min, max) stamp radii in model units; ``stack``: the passes; ``strengths``: named multipliers
    of pass opacities (0 switches those passes off); ``layers``: per paint layer a ``LayerStyle``."""
    base: tuple
    colors: Dict[str, tuple]
    tips: Dict[str, Tip]
    brush: Brush
    sizes: Dict[str, Tuple[float, float]]
    stack: Tuple[Pass, ...]
    strengths: Dict[str, float] = field(default_factory=dict)
    layers: Dict[str, LayerStyle] = field(default_factory=dict)

    def but(self, **changes) -> "Look":
        """A copy with some fields changed."""
        return replace(self, **changes)

    def layer_style(self, name) -> LayerStyle:
        """The brush, tip and overlay of one layer, the look's own brush and tip filling what it leaves out."""
        own = self.layers.get(name, LayerStyle())
        return LayerStyle(own.brush or self.brush, own.tip or self.tips["tip"], own.overlay)

    def problems(self, label, layers=()):
        """Every problem of this look (colours, tips, brush, sizes, layers, passes)."""
        out = []
        for name, colors in [("base", [self.base])] + list(self.colors.items()):
            if not colors:
                out.append(f"{label}.{name}: no colour")
            for c in colors:
                try:
                    parse_color(c)
                except (ValueError, TypeError) as exc:
                    out.append(f"{label}.{name}: {exc}")
        if "tip" not in self.tips:
            out.append(f"{label}: tips need a 'tip' (the default tip)")
        for name, tip in self.tips.items():
            out += [f"{label}.tips.{name}: expected a Tip"] if not isinstance(tip, Tip) else tip.problems(
                f"{label}.tips.{name}")
        out += self.brush.problems(f"{label}.brush") if isinstance(self.brush, Brush) else [
            f"{label}.brush: expected a Brush"]
        for name, (lo, hi) in self.sizes.items():
            if not 0 < lo <= hi:
                out.append(f"{label}.sizes.{name}: (min, max) with 0 < min <= max")
        for name, value in self.strengths.items():
            if not 0 <= value <= 3:
                out.append(f"{label}.strengths.{name} must be between 0 and 3")
        for name, style in self.layers.items():
            if layers and name not in layers:
                out.append(f"{label}.layers: {name!r} is not a theme layer ({list(layers)})")
            if not isinstance(style, LayerStyle):
                out.append(f"{label}.layers.{name}: expected a LayerStyle")
                continue
            if style.brush is not None and not isinstance(style.brush, Brush):
                out.append(f"{label}.layers.{name}.brush: expected a Brush")
            if style.tip is not None and not isinstance(style.tip, Tip):
                out.append(f"{label}.layers.{name}.tip: expected a Tip")
            if style.overlay is not None:
                out += style.overlay.problems(f"{label}.layers.{name}.overlay")
        for p in self.stack:
            out += p.problems(f"{label}/{p.name}", self, layers)
        return out


@dataclass(frozen=True)
class Region:
    """Part of a material painted its own way: the texels of ``material`` on elements whose name starts with one of
    ``on`` and/or on faces of one of ``groups``. Give a whole ``look``, or only what changes (``brush``, ``tip``);
    the rest comes from the material's look. The shading range stays the material's, so no seam shows."""
    material: str
    on: tuple = ()
    groups: tuple = ()
    look: Optional[Look] = None
    brush: Optional[Brush] = None
    tip: Optional[Tip] = None

    def resolve(self, base: Look) -> Look:
        """The look this region paints with, from the material's ``base`` look."""
        look = self.look or base
        changes = {}
        if self.brush is not None:
            changes["brush"] = self.brush
        if self.tip is not None:
            changes["tips"] = {**look.tips, "tip": self.tip}
        return look.but(**changes) if changes else look


@dataclass(frozen=True)
class PaintLayer:
    """A paint layer of the theme: its name (and the painter layer it is written to), blend and opacity."""
    name: str
    blend: str = "normal"
    opacity: float = 1.0


@dataclass
class Style:
    """One texture variant: a look per material and the regions painted their own way (matched in order)."""
    name: str
    looks: Dict[str, Look]
    regions: Dict[str, Region] = field(default_factory=dict)

    def problems(self, materials=(), layers=()):
        """Every problem: unstyled materials, bad looks and regions."""
        out = []
        missing = [m for m in materials if m not in self.looks]
        if missing:
            out.append(f"materials without a look: {missing}")
        for name, look in self.looks.items():
            out += [f"{name}: expected a Look"] if not isinstance(look, Look) else look.problems(name, layers)
        for name, region in self.regions.items():
            if not isinstance(region, Region):
                out.append(f"region {name}: expected a Region")
                continue
            if region.material not in self.looks:
                out.append(f"region {name}: material {region.material!r} has no look")
                continue
            if not region.on and not region.groups:
                out.append(f"region {name}: give element prefixes (on) and/or face groups (groups)")
            out += region.resolve(self.looks[region.material]).problems(f"region {name}", layers)
        return out

    def validate(self, materials=(), layers=()):
        """The style itself, or ValueError listing every problem."""
        problems = self.problems(materials, layers)
        if problems:
            raise ValueError(f"style {self.name!r} is not valid:\n  " + "\n  ".join(problems))
        return self


# ---------------------------------------------------------------- painting
def _units(style, view, materials):
    """Per material present: (index, name, all its texels, units), a unit being (label, texels, look, region number
    or None, clip). Regions take their texels first, in order; the material's own look lays its strokes over the
    whole material (the same strokes as without regions) and only writes outside them."""
    out = []
    for index, name in enumerate(materials.names):
        where = materials.material == index
        if not where.any():
            continue
        look = style.looks[name]
        remaining, units = where.copy(), []
        for number, (label, region) in enumerate(style.regions.items()):
            if region.material != name:
                continue
            taken = remaining & view.select(region.on or None, region.groups or None)
            if taken.any():
                units.append((f"{name}/{label}", taken, region.resolve(look), number, None))
                remaining &= ~taken
        clip = remaining if units else None
        out.append((index, name, where, [(name, where if units else remaining, look, None, clip)] + units))
    return out


def shading_fields(view, materials, where, per_element=False):
    """(value, lit) over every texel, normalised to the range of the material texels ``where``. With
    ``per_element`` each element (the cloak, the collar, a sleeve...) is normalised to its own range, so every part
    of one material gets the same share of light and shade whatever its geometry."""
    up = np.clip(view.normal[:, 1], 0.0, 1.0)
    v = np.zeros(view.count)
    groups = [where]
    if per_element:
        groups = [where & (view.element == name) for name in np.unique(view.element[where])]
    for part in groups:
        lo, hi = np.percentile(materials.value[part], [8, 92])
        v[part] = np.clip((materials.value[part] - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    if materials.occlusion is not None:
        v = v * (1.0 - materials.occlusion)
    return v, np.clip(v * (0.65 + 0.35 * up) + 0.12 * up, 0.0, 1.0)


def _step(spec, v, lit, field_name):
    if spec is None:
        return np.ones_like(v)
    if np.isscalar(spec):
        return np.full_like(v, float(spec))
    return smoothstep(spec[0], spec[1], lit if field_name == "lit" else v)


def paint_looks(painter, style: Style, materials, layers: Sequence[PaintLayer], *, log=None, per_element=False):
    """Paint ``style`` over every texel of ``painter`` by the material map ``materials`` (``painter.material_map``),
    layer by layer (``layers``, bottom first; the first one opaque), each written to the painter layer of its
    name. Texels of no material keep the map's fixed colour. Returns the composited per-texel RGB (N, 3)."""
    layers = tuple(layers)
    if not layers:
        raise ValueError("paint_looks: give the theme's paint layers")
    names = [layer.name for layer in layers]
    style.validate(materials.present(), names)
    view = painter.surface()
    if materials.material.shape != (view.count,):
        raise ValueError("paint_looks: the material map was made for another surface")
    units = _units(style, view, materials)
    fields = {index: shading_fields(view, materials, where, per_element) for index, _name, where, _u in units}
    image = np.array(materials.fixed, dtype=float)
    for _index, _name, _where, unit_list in units:
        for _label, where, look, _region, clip in unit_list:
            image[where if clip is None else clip] = _rgb(look.base)
    result = image.copy()
    for rank_layer, paint_layer in enumerate(layers):
        target = image if rank_layer == 0 else TexelLayer(view.count)
        for rank, (index, _name, _where, unit_list) in enumerate(units):
            v, lit = fields[index]
            for label, where, look, region, clip in unit_list:
                if not where.any():
                    continue
                for k, p in enumerate(look.stack):
                    if p.layer != paint_layer.name:
                        continue
                    strength = look.strengths.get(p.strength, 1.0) if p.strength else 1.0
                    if strength <= 0:
                        continue
                    seed = 1000 * rank + 100 * (0 if region is None else region + 1) + 10 * k + p.seed
                    if p.texel is not None:
                        sel = np.flatnonzero(where if clip is None else clip)
                        alpha = np.clip(p.texel(view.x[sel], view.y[sel]), 0.0, 1.0) * min(1.0, p.opacity * strength)
                        keep = alpha > 0
                        sel, alpha = sel[keep], alpha[keep]
                        colors = np.tile(np.asarray(_rgb(look.colors[p.colors][0]), float), (len(sel), 1))
                        if rank_layer == 0:
                            image[sel] = image[sel] * (1 - alpha[:, None]) + colors * alpha[:, None]
                        else:
                            target.lay(sel, colors, alpha)
                        continue
                    ls = look.layer_style(p.layer)
                    tip = look.tips[p.tip] if p.tip != "tip" else ls.tip
                    tip = tip.with_(scale=tip.scale * p.grain)
                    brush = (p.brush or ls.brush).with_(radius=look.sizes[p.size])
                    pressure = _step(p.pressure, v, lit, p.field) * p.scale + p.offset
                    start_weight = _step(p.weight, v, lit, p.field) ** p.curve
                    make = Pattern.even if p.even else Pattern.scatter
                    pattern = make(coverage=p.coverage * brush.coverage, weight=start_weight)
                    hits = lay(view, pattern,
                               tip=tip, brush=brush, colors=look.colors[p.colors], where=where,
                               pressure=pressure, clip=clip, seed=seed,
                               tip_colors=None if p.tip_colors is None else look.colors[p.tip_colors])
                    alpha = (hits.additive(p.opacity * strength) if p.additive
                             else hits.alpha * min(1.0, p.opacity * strength))
                    if rank_layer == 0:
                        image[hits.texel] = image[hits.texel] * (1 - alpha[:, None]) + hits.colors * alpha[:, None]
                    else:
                        target.lay(hits.texel, hits.colors, alpha)
                    if log:
                        log(f"[paint] {label} {p.name}: {hits.strokes} strokes, {hits.stamps} stamps, "
                            f"{len(hits.texel)} texels")
        if rank_layer > 0:
            for index, _name, _where, unit_list in units:
                _v, lit = fields[index]
                for _label, where, look, _region, clip in unit_list:
                    overlay = look.layer_style(paint_layer.name).overlay
                    if overlay is None or overlay.amount <= 0:
                        continue
                    sel = np.flatnonzero(where if clip is None else clip)
                    shift = 0.0
                    if overlay.tip is not None:
                        shift = overlay.tip.on_surface(view.centre[sel], view.normal[sel],
                                                       3000 + 10 * index + rank_layer, scale=overlay.scale)
                        shift = shift * overlay.grain
                    alpha = overlay.amount * smoothstep(overlay.ramp[0], overlay.ramp[1],
                                                        np.clip(lit[sel] + shift, 0.0, 1.0))
                    target.lay(sel, np.tile(np.asarray(_rgb(overlay.color), float), (len(sel), 1)), alpha)
        with painter.layer(paint_layer.name, blend=paint_layer.blend, opacity=paint_layer.opacity):
            if rank_layer == 0:
                view.write(np.concatenate([image, np.full((view.count, 1), 255.0)], axis=1))
                result = image.copy()
            else:
                idx, rgba = target.rgba()
                if len(idx):
                    view.write(rgba, idx)
                if paint_layer.blend == "normal":
                    blended = result.copy()
                    target.over(blended)
                    result = result + (blended - result) * paint_layer.opacity
    return result
