"""Project themes: the visual tokens every asset of a project shares, declared once in ``projects/<p>/theme.py``.

A theme is the project's design system for painting: named colours and ramps, the grains and motifs of its stamps
(``Tip``), its brushes (``Brush``), print patterns (``Pattern``), line styles (``ink.style``), the paint layers a
texture is built in (``PaintLayer``) and the styles of its texture variants (``Style``: a ``Look`` per material).
Recipes take tokens from it instead of writing colours and sizes inline, and derive variations with ``with_`` /
``but``; ``STYLE.md`` next to it says in words what the theme cannot (art direction, edge treatment, layer rules).

    # projects/<p>/theme.py
    from Tools.TexturePainter.theme import define_theme
    THEME = define_theme("my_project", palette={"ink": "#0d0f22"}, tips={"chalk": Tip.grain(...)}, ...)

    # a recipe
    theme = recipe_paths(__file__).theme()
    painter.paint_strokes([theme.line("contour")(curve(...))])

``py -3.12 -m Tools.forge theme PROJECT`` lists and checks the tokens; ``--sheet OUT.png`` draws them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
import sys
from typing import Dict, Optional, Tuple

from .core.color import parse_color
from .ink import Style as LineStyle
from .looks import PaintLayer, Style
from .marks import Brush, Pattern, Tip

KINDS = ("palette", "ramps", "tips", "brushes", "patterns", "lines", "styles")


@dataclass(frozen=True)
class Theme:
    """The tokens of one project (see the module notes). Look tokens up with ``color``, ``tip``, ``brush``,
    ``pattern``, ``line`` and ``style``: an unknown name fails with the list of known ones. ``layers`` are the paint
    layers textures are built in, bottom first; ``extras`` holds anything else the project wants to share."""
    name: str
    palette: Dict[str, object] = field(default_factory=dict)
    ramps: Dict[str, Tuple] = field(default_factory=dict)
    tips: Dict[str, Tip] = field(default_factory=dict)
    brushes: Dict[str, Brush] = field(default_factory=dict)
    patterns: Dict[str, Pattern] = field(default_factory=dict)
    lines: Dict[str, LineStyle] = field(default_factory=dict)
    layers: Tuple[PaintLayer, ...] = ()
    styles: Dict[str, Style] = field(default_factory=dict)
    extras: Dict[str, object] = field(default_factory=dict)

    def _get(self, kind, name):
        table = getattr(self, kind)
        try:
            return table[name]
        except KeyError:
            raise KeyError(f"theme {self.name!r} has no {kind[:-1] if kind.endswith('s') else kind} {name!r}; "
                           f"known: {sorted(table)}") from None

    def color(self, name):
        """A palette colour as an RGBA tuple."""
        return tuple(parse_color(self._get("palette", name)))

    def ramp(self, name):
        """A ramp as RGBA tuples."""
        return tuple(tuple(parse_color(c)) for c in self._get("ramps", name))

    def tip(self, name) -> Tip:
        """A tip token."""
        return self._get("tips", name)

    def brush(self, name) -> Brush:
        """A brush token."""
        return self._get("brushes", name)

    def pattern(self, name) -> Pattern:
        """A pattern token."""
        return self._get("patterns", name)

    def line(self, name) -> LineStyle:
        """A line style (``ink.style``)."""
        return self._get("lines", name)

    def style(self, name) -> Style:
        """A texture variant's style."""
        return self._get("styles", name)

    def problems(self):
        """Every problem of the tokens (bad colours, wrong types, styles whose looks do not check)."""
        out = []
        for name, value in self.palette.items():
            try:
                parse_color(value)
            except (ValueError, TypeError) as exc:
                out.append(f"palette.{name}: {exc}")
        for name, ramp in self.ramps.items():
            for value in ramp:
                try:
                    parse_color(value)
                except (ValueError, TypeError) as exc:
                    out.append(f"ramps.{name}: {exc}")
        for kind, cls in (("tips", Tip), ("brushes", Brush), ("patterns", Pattern), ("lines", LineStyle),
                          ("styles", Style)):
            for name, value in getattr(self, kind).items():
                if not isinstance(value, cls):
                    out.append(f"{kind}.{name}: expected a {cls.__name__}")
                elif hasattr(value, "problems") and kind in ("tips", "brushes"):
                    out += value.problems(f"{kind}.{name}")
        layer_names = [layer.name for layer in self.layers]
        for layer in self.layers:
            if not isinstance(layer, PaintLayer):
                out.append(f"layers: expected PaintLayer, got {layer!r}")
            elif layer.blend not in ("normal", "multiply", "screen", "overlay", "add") or not 0 <= layer.opacity <= 1:
                out.append(f"layers.{layer.name}: blend normal/multiply/screen/add and opacity 0..1")
        if len(set(layer_names)) != len(layer_names):
            out.append("layers: names must be unique")
        if self.styles and not self.layers:
            out.append("styles need the theme's paint layers (layers=...)")
        for name, value in self.styles.items():
            if isinstance(value, Style):
                out += [f"styles.{name}: {p}" for p in value.problems((), layer_names)]
        return out

    def summary(self):
        """One line per kind: how many tokens and their names."""
        lines = [f"theme {self.name}"]
        for kind in KINDS:
            names = sorted(getattr(self, kind))
            lines.append(f"  {kind:9} {len(names):3}  {', '.join(names)}")
        lines.append(f"  layers    {len(self.layers):3}  {', '.join(l.name for l in self.layers)}")
        if self.extras:
            lines.append(f"  extras    {len(self.extras):3}  {', '.join(sorted(self.extras))}")
        return "\n".join(lines)


def define_theme(name, **tokens) -> Theme:
    """Declare a project's theme (see ``Theme``); raises ValueError listing every problem."""
    unknown = set(tokens) - set(KINDS) - {"layers", "extras"}
    if unknown:
        raise TypeError(f"define_theme: unknown token kinds {sorted(unknown)}; kinds: {list(KINDS) + ['layers', 'extras']}")
    if "layers" in tokens:
        tokens["layers"] = tuple(tokens["layers"])
    theme = Theme(name, **tokens)
    problems = theme.problems()
    if problems:
        raise ValueError(f"theme {name!r} is not valid:\n  " + "\n  ".join(problems))
    return theme


def theme_path(project) -> Path:
    """Where a project's theme lives: ``<project>/theme.py``."""
    return Path(project) / "theme.py"


def load_theme(project, *, required=True) -> Optional[Theme]:
    """The ``THEME`` of ``projects/<p>/theme.py`` (``project``: the project folder); None when the project has no
    theme and ``required`` is False."""
    path = theme_path(project).resolve()
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"project has no theme: {path} (see .agents/skills/forge-3d-texture/references/theme.md)")
        return None
    name = f"_forge_theme_{Path(project).resolve().name}"
    if name in sys.modules and getattr(sys.modules[name], "__file__", None) == str(path):
        module = sys.modules[name]                  # loaded once per process
    else:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module                  # dataclasses in the theme look their module up
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    theme = getattr(module, "THEME", None)
    if not isinstance(theme, Theme):
        raise ValueError(f"{path}: define THEME = define_theme(...)")
    return theme
