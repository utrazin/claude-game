"""Material maps: which material every texel of a model is and how lit it is, computed once and cached.

A recipe that paints by material (a look per material, brush layers driven by the light) first needs, per texel,
the material, a shading value and, for texels that are no material (voids, rims), a fixed colour. That
classification depends only on the model (geometry and UVs) and on the recipe's region code, not on the colours,
so it is cached on disk in ``<project>/.cache/texture`` and reused by every variant::

    def classify(view):                     # view: painter.surface(); per texel arrays
        ...
        return names, material, value, fixed

    materials = painter.material_map(classify)
    fur = materials.mask("fur")

The cache key covers the texels (positions, normals and atlas pixels), the source of every Python file next to the
module defining ``classify`` and ``key``; any change recomputes it.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

VERSION = "v2"


@dataclass(frozen=True)
class MaterialMap:
    """Per texel of a ``SurfaceView``: ``material`` index into ``names`` (-1: no material, keeps ``fixed``),
    ``value`` the shading value (0 dark .. 1 lit), ``fixed`` the RGB of texels that are no material, ``occlusion``
    (optional, 0..1 per texel) an extra darkening applied to the value after it is normalised per part, so a darker
    hem or crease adds shade without squeezing the rest of the part's range."""
    names: tuple
    material: np.ndarray
    value: np.ndarray
    fixed: np.ndarray
    occlusion: Optional[np.ndarray] = None

    def index(self, name):
        """The index of material ``name``."""
        try:
            return self.names.index(name)
        except ValueError:
            raise KeyError(f"no material {name!r}; materials: {list(self.names)}") from None

    def mask(self, name):
        """Bool per texel: of material ``name``."""
        return self.material == self.index(name)

    def present(self):
        """Names of the materials that have texels, in ``names`` order."""
        used = set(np.unique(self.material[self.material >= 0]).tolist())
        return [name for i, name in enumerate(self.names) if i in used]


def _check(view, result) -> MaterialMap:
    names, material, value, fixed, *rest = result
    names = tuple(str(n) for n in names)
    material = np.asarray(material, dtype=np.int64).reshape(-1)
    value = np.asarray(value, dtype=float).reshape(-1)
    fixed = np.asarray(fixed, dtype=float).reshape(-1, 3)
    for label, array in (("material", material), ("value", value), ("fixed", fixed)):
        if len(array) != view.count:
            raise ValueError(f"classify: {label} has {len(array)} rows for {view.count} texels")
    if len(material) and (material.max() >= len(names) or material.min() < -1):
        raise ValueError("classify: material indices must be -1 or index names")
    occlusion = None
    if rest and rest[0] is not None:
        occlusion = np.clip(np.asarray(rest[0], dtype=float).reshape(-1), 0.0, 1.0)
        if len(occlusion) != view.count:
            raise ValueError(f"classify: occlusion has {len(occlusion)} rows for {view.count} texels")
    return MaterialMap(names, material, value, fixed, occlusion)


def _cache_dir(painter):
    for parent in Path(painter.bbmodel_path).resolve().parents:
        if (parent / "project.json").is_file():
            return parent / ".cache" / "texture"
    return None


def _digest(view, classify, key: Sequence):
    h = hashlib.sha1()
    for array in (view.position, view.normal, view.x, view.y):
        h.update(np.ascontiguousarray(array).tobytes())
    module = sys.modules.get(getattr(classify, "__module__", ""), None)
    source = getattr(module, "__file__", None)
    if source:
        for path in sorted(Path(source).resolve().parent.glob("*.py")):
            h.update(path.read_bytes())
    h.update(json.dumps([str(k) for k in key]).encode("utf-8"))
    h.update(VERSION.encode("utf-8"))
    return h.hexdigest()[:20]


def material_map(painter, view, classify, *, key=()) -> MaterialMap:
    """``classify(view)`` through the on-disk cache of the painter's project (no cache outside a project)."""
    folder = _cache_dir(painter)
    path = None if folder is None else folder / f"materials_{_digest(view, classify, key)}.npz"
    if path is not None and path.exists():
        with np.load(path, allow_pickle=False) as f:
            occlusion = f["occlusion"] if "occlusion" in f.files else None
            return MaterialMap(tuple(json.loads(str(f["names"]))), f["material"], f["value"], f["fixed"], occlusion)
    result = _check(view, classify(view))
    if path is not None:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npz")
        extra = {} if result.occlusion is None else {"occlusion": result.occlusion}
        np.savez(tmp, names=json.dumps(list(result.names)), material=result.material, value=result.value,
                 fixed=result.fixed, **extra)
        tmp.replace(path)
    return result
