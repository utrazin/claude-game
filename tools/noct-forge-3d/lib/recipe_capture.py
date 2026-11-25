"""Run a recipe without writing files, capturing its documents and which statements created what."""

from __future__ import annotations

import contextlib
import inspect
import io
import runpy
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .animation import AnimationEditor, AnimationTrack
from .armature import ArmatureHandle
from .model_builder import ModelBuilder


@dataclass
class Capture:
    documents: dict[Path, dict] = field(default_factory=dict)
    # (kind, name) -> recipe line stacks (innermost first) of the statements that created or filled it
    sites: dict[tuple[str, str], list[tuple[int, ...]]] = field(default_factory=dict)
    # recipe line -> name of the local variable holding the builder/editor there; default_names by kind
    names: dict[int, str] = field(default_factory=dict)
    default_names: dict[str, str] = field(default_factory=dict)
    # clip names the recipe declares (the bbmodel may hold other clips the recipe knows nothing about)
    declared_clips: set[str] = field(default_factory=set)
    # (kind, name) -> recipe lines of later calls that changed an entity without creating anything
    modifiers: dict[tuple[str, str], list[int]] = field(default_factory=dict)


def _snapshot(owner) -> set[tuple[str, str]]:
    if isinstance(owner, AnimationEditor):
        return {("clip", name) for name in owner._clips}
    keys = {("element", e.name) for e in owner._elements}
    keys |= {("group", n) for n in owner._groups}
    keys |= {("armature", n) for n in owner._armatures}
    keys |= {("bone", n) for n in owner._armature_bones}
    keys |= {("bind", n) for n in owner._binding_policies}
    keys |= {("socket", n) for n in owner._sockets}
    return keys


def _state(owner) -> dict:
    """Numbers a later call could change on entities that already exist."""
    if isinstance(owner, AnimationEditor):
        return {}
    state = {}
    for e in owner._elements:
        vertices = hash(tuple(sorted((k, tuple(v)) for k, v in e.vertices.items())))
        state[("element", e.name)] = (tuple(e.origin), tuple(e.rotation), tuple(e.from_), tuple(e.to_ or ()), vertices)
    for name, g in owner._groups.items():
        state[("group", name)] = (tuple(g.pivot), tuple(g.rotation))
    for name, b in owner._armature_bones.items():
        state[("bone", name)] = (tuple(b.start), tuple(b.end))
    return state


def _owner(target):
    if isinstance(target, ArmatureHandle):
        return target.builder
    if isinstance(target, AnimationTrack):
        return target.clip.editor
    return target


def capture_recipe(recipe: str | Path) -> Capture:
    """Execute ``recipe`` as ``__main__`` without writing anything.

    ``ModelBuilder.export_bbmodel`` and ``AnimationEditor.save`` record their document instead of
    writing it, and every public builder or animation call records the recipe lines that were on
    the stack when it created an entity, so callers can map entities back to recipe statements.
    The recipe sees ``sys.argv == [recipe]``; any other side effect it has (files, network) still happens.
    """
    recipe_path = Path(recipe).resolve()
    capture = Capture()
    originals = {}
    depth = [0]

    def capture_export(self, filepath, **_options):
        capture.documents[Path(filepath).resolve()] = self.to_bbmodel_data()
        return Path(filepath)

    def capture_save(self):
        capture.documents[self.path.resolve()] = self.build_document()
        capture.declared_clips.update(self._clips)
        return self.path

    def chain_of(frame, owner):
        lines, kind = [], ("editor" if isinstance(owner, AnimationEditor) else "builder")
        while frame:
            if Path(frame.f_code.co_filename).resolve() == recipe_path:
                # a comprehension frame repeats its caller's line: keep one
                if not lines or lines[-1] != frame.f_lineno:
                    lines.append(frame.f_lineno)
                for name, value in list(frame.f_locals.items()):
                    if value is owner and not name.startswith("_"):
                        capture.names.setdefault(frame.f_lineno, name)
                        capture.default_names.setdefault(kind, name)
                        break
            frame = frame.f_back
        return tuple(lines)

    def wrap(function):
        def wrapper(target, *args, **kwargs):
            owner = _owner(target)
            before, before_state = _snapshot(owner), _state(owner)
            depth[0] += 1
            try:
                return function(target, *args, **kwargs)
            finally:
                depth[0] -= 1
                if depth[0] == 0:
                    if isinstance(target, AnimationTrack):
                        touched = {("clip", target.clip.name)}
                    else:
                        touched = _snapshot(owner) - before
                    chain = chain_of(sys._getframe(1), owner)
                    for key in touched:
                        if chain and chain not in capture.sites.setdefault(key, []):
                            capture.sites[key].append(chain)
                    if chain and not touched:
                        after_state = _state(owner)
                        for key, value in after_state.items():
                            if before_state.get(key) not in (None, value):
                                capture.modifiers.setdefault(key, []).append(chain[0])
        wrapper.__wrapped__ = function
        return wrapper

    def patch(cls, name, replacement):
        originals[(cls, name)] = vars(cls)[name]
        setattr(cls, name, replacement)

    patch(ModelBuilder, "export_bbmodel", capture_export)
    patch(AnimationEditor, "save", capture_save)
    for cls in (ModelBuilder, ArmatureHandle, AnimationEditor, AnimationTrack):
        for name, member in list(vars(cls).items()):
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            if (cls, name) in originals or name in {"save", "controls", "build_document"}:
                continue
            patch(cls, name, wrap(member))
    saved_argv = sys.argv
    sys.argv = [str(recipe_path)]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                runpy.run_path(str(recipe_path), run_name="__main__")
            except SystemExit as exit_:   # `raise SystemExit(main())` is a normal ending
                if exit_.code not in (None, 0):
                    raise
    finally:
        sys.argv = saved_argv
        for (cls, name), original in originals.items():
            setattr(cls, name, original)
    return capture
