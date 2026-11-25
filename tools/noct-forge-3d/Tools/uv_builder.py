"""Explicit UV recipe operating on a saved model, never a geometry recipe."""
import copy
import json
import os
from pathlib import Path

from .uv_packer import BoxUVPacker
from .uv_rules import ATTRIBUTES, SELECTORS, validate_rules


class UVBuilder:
    """Explicit UV recipe operating on a saved BBModel file, never on a geometry recipe.

    Declare per-region choices with ``rule()`` and follower-to-owner face pairs with ``share_uv()``; start over
    with ``clear()`` (or ``clear_sharing()`` for the pairs only), then repack and write with ``save()``. Options
    (``uv_scale``, ``island_padding``, ``layout``, ``packer``...) are the defaults of every face no rule changes.
    Saving refuses when the model changed since the recipe loaded it.
    """
    def __init__(self, model_path, **options):
        self.path = Path(model_path)
        self.source = json.loads(self.path.read_text(encoding='utf-8'))
        self.options = options
        self.last_stats = None
        meta = self.source.get('unhandled_root_fields', {}).get('model_as_code', {})
        self.links = [copy.deepcopy(link) for link in meta.get('uv_sharing', [])
                      if not (isinstance(link, dict) and link.get('region'))]
        self.rules = copy.deepcopy(meta.get('uv_packing', {}).get('rules', []))

    def rule(self, **values):
        """Select faces and set their packing; the last matching rule wins, attribute by attribute.

        Selectors (glob patterns): ``element``, ``tag``, ``parent``, ``face``, ``face_group``.
        Attributes: ``density`` (px per unit), ``layout`` (``box``, ``faces``, ``charts``, ``flat``, ``fixed``),
        ``per`` (flat: ``face``, ``element``, ``rule``), ``size`` ((w, h) px), ``pin`` ((u, v) px), ``block``,
        ``texture`` (atlas slot name).
        See ``Tools.uv_rules``.
        """
        unknown = set(values) - set(SELECTORS) - set(ATTRIBUTES)
        if unknown:
            raise ValueError(f'Unknown UV rule keyword {sorted(unknown)}; selectors: {", ".join(SELECTORS)}; '
                             f'attributes: {", ".join(ATTRIBUTES)}')
        rule = {'select': {key: values[key] for key in SELECTORS if key in values}}
        for key in ATTRIBUTES:
            if values.get(key) is not None:
                rule[key] = list(values[key]) if key in ('size', 'pin') else values[key]
        validate_rules([rule])
        self.rules.append(rule)
        return self

    def share_uv(self, target, *, source, mirror=False):
        """References are (element name, face name); followers point to owners directly.

        ``mirror=True`` shares with a mirrored part (left/right): the follower
        must be the owner's reflection and shows the owner's pixels reflected.
        """
        if not isinstance(mirror, bool):
            raise ValueError('mirror must be a boolean')
        link = {'target': list(target), 'source': list(source)}
        if mirror:
            link['mirror'] = True
        self.links.append(link)
        return self

    def clear_sharing(self):
        """Use at the start of recipes that declare the complete sharing plan."""
        self.links = []
        return self

    def clear(self):
        """Forget saved rules and sharing: the recipe declares the whole UV plan from scratch."""
        self.links, self.rules = [], []
        return self

    def save(self, output_path=None, *, verbose=False, dry_run=None):
        """Repack and write; ``dry_run`` (default: ``FORGE_UV_DRY_RUN`` from ``forge uv --dry-run``) writes nothing."""
        self.last_stats = None
        if dry_run is None:
            dry_run = os.environ.get('FORGE_UV_DRY_RUN') == '1'
        if json.loads(self.path.read_text(encoding='utf-8')) != self.source:
            raise ValueError('Model changed since UV recipe loaded it')
        data = copy.deepcopy(self.source)
        meta = data.setdefault('unhandled_root_fields', {}).setdefault('model_as_code', {})
        meta['uv_sharing'] = self.links
        if self.rules:
            meta.setdefault('uv_packing', {})['rules'] = self.rules
        elif 'rules' in meta.get('uv_packing', {}):
            del meta['uv_packing']['rules']
        mapped, size, stats = BoxUVPacker.pack_document(data, **self.options)
        target = Path(output_path) if output_path else self.path
        self.last_stats = dict(stats, width=size.width, height=size.height)
        if verbose or dry_run:
            layouts = stats.get('texels_by_layout')
            textures = stats.get('textures')
            tex_map = {t['name']: f"{t['width']}x{t['height']}" for t in textures} if textures else {}
            tex_info = (f"; textures {tex_map}"
                        if textures and (len(textures) > 1 or textures[0]['name'] != 'default') else '')
            print(f"[UV]{' DRY-RUN' if dry_run else ''} {stats['uv_scale']} px/unit; padding "
                  f"{stats['island_padding']} px; {size.width}x{size.height}; {stats['element_count']} regions"
                  + (f"; texels {layouts}" if layouts else '') + tex_info)
        if dry_run:
            return target
        BoxUVPacker.write_document(mapped, target)
        if target == self.path:
            self.source = mapped
        return target
