"""Show what changed in model.bbmodel compared with what the recipes generate, in the detail needed to edit them."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import sys
import textwrap
import traceback
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Tools._resolve import resolve_model_target, resolve_asset
from Tools.recipe_emit import KIND_ORDER, build_scene, changes, emit, same, summary
from lib.recipe_capture import capture_recipe

RIG_KINDS = ('armature', 'bone', 'bind')
_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.Module)


class RecipeSource:
    def __init__(self, path):
        text = self.text = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(text)
        self.parent = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        self.statements = [n for n in ast.walk(tree) if isinstance(n, ast.stmt)]

    def statement(self, line):
        inside = [s for s in self.statements if s.lineno <= line <= s.end_lineno]
        return min(inside, key=lambda s: s.end_lineno - s.lineno) if inside else None

    def lift(self, node):
        """Span of ``node``, widened to the outermost loop around it inside the same function."""
        best, cursor = node, self.parent.get(node)
        while cursor is not None and not isinstance(cursor, _SCOPES):
            if isinstance(cursor, _LOOPS):
                best = cursor
            cursor = self.parent.get(cursor)
        return best.lineno, best.end_lineno

    def in_loop(self, line):
        node = self.statement(line)
        return node is not None and self.lift(node) != (node.lineno, node.end_lineno)

    def is_entry(self, line):
        """True for the statement that exports or saves the whole document: never a replace target."""
        node = self.statement(line)
        return node is not None and any(
            isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr in ("export_bbmodel", "save") for n in ast.walk(node))

    def indent_at(self, line):
        columns = [s.col_offset for s in self.statements if s.lineno == line]
        return " " * (min(columns) if columns else 0)


class Sites:
    """Maps entities to the recipe statements that created them."""

    def __init__(self, source, sites, modifiers=None):
        self.source, self.sites, self.modifiers = source, sites, modifiers or {}
        self.suffixes, self.by_line = defaultdict(set), defaultdict(set)
        for key, chains in sites.items():
            for chain in chains:
                for index, line in enumerate(chain):
                    self.suffixes[line].add(chain[index:])
                    self.by_line[line].add(key)

    def _span(self, chain):
        # innermost statement reached through a single call path, then the outermost loop above it;
        # None when no such statement exists (only the recipe's entry point reaches it)
        level = next((i for i, line in enumerate(chain)
                      if len(self.suffixes[line]) == 1 and not self.source.is_entry(line)), None)
        if level is None:
            return None
        loops = [k for k in range(level, len(chain)) if self.source.in_loop(chain[k])]
        node = self.source.statement(chain[max(loops) if loops else level])
        return self.source.lift(node) if node else None

    def spans(self, key):
        found = [self._span(chain) for chain in self.sites.get(key, [])]
        if not found or None in found:
            return None
        merged = []
        for start, end in sorted(found):
            if merged and start <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        return tuple(merged)

    def touched(self, spans):
        return {key for start, end in spans for line in range(start, end + 1) for key in self.by_line[line]}

    def last_span(self):
        """The statement, after all others, that builds something: where new parts can go."""
        spans = [s for key in self.sites for s in (self.spans(key) or ())]
        return max(spans, key=lambda s: s[1]) if spans else None


def _site_key(key):
    return ("element", key[1]) if key[0] in ("mesh", "cube") else key


def _scene_keys(site_key, scene):
    if site_key[0] == "element":
        return [k for k in (("mesh", site_key[1]), ("cube", site_key[1])) if k in scene.entities]
    return [site_key] if site_key in scene.entities else []


def compare(gen, act):
    def ordered(keys):
        return sorted(keys, key=lambda k: (KIND_ORDER[k[0]], (act if k in act.entities else gen).entities[k].order))
    common = gen.entities.keys() & act.entities.keys()
    changed = [k for k in common if not same(k[0], gen.entities[k].sig, act.entities[k].sig)]
    return (ordered(changed), ordered(act.entities.keys() - gen.entities.keys()),
            ordered(gen.entities.keys() - act.entities.keys()))


def _spans_text(spans):
    return ", ".join(f"L{a}-{b}" if a != b else f"L{a}" for a, b in spans)


def _fit(code, spans, sites, names, default, var):
    """Give the block the recipe's own variable name and the indentation of the statement it replaces."""
    name = next((names[line] for a, b in spans for line in range(a, b + 1) if line in names), default)
    if var == "builder":
        code = re.sub(r"(?m)^(\s*)builder\.", lambda m: f"{m.group(1)}{name}.", code)
    else:
        code = code.replace("= editor.animation(", f"= {name}.animation(")
    return textwrap.indent(code, sites.source.indent_at(spans[0][0]))


def report(stage, recipe_name, gen, act, sites, mode, names, defaults, var, full=False):
    """Return (lines, snippet blocks, found differences)."""
    default = defaults.get(var, var)
    changed, new, removed = compare(gen, act)
    def detail(head, rows):
        return head + "".join(f"\n      {row}" for row in rows)
    lines = [detail(f"  ~ {k[0]} {k[1]}" + (f" (parent {act.entities[k].parent})" if act.entities[k].parent else ""),
                    changes(gen.entities[k], act.entities[k], full)) for k in changed]
    lines += [detail(f"  + {k[0]} {k[1]}" + (f" (parent {act.entities[k].parent})" if act.entities[k].parent else ""),
                     summary(act.entities[k], full)) for k in new]
    lines += [f"  - {k[0]} {k[1]}: the recipe builds it but the bbmodel no longer has it" if k[0] != "clip" else
              f"  - clip {k[1]}: the recipe declares it but the bbmodel has no such clip (if you only regenerated the "
              "model, run Tools.animation_export; delete the clip's code only if you removed it in Blockbench)"
              for k in removed]
    lines += [f"  ? {k[0]} {k[1]} is also changed later by the recipe at "
              f"{', '.join(f'L{n}' for n in sorted(set(sites.modifiers[_site_key(k)])))}: remove or adjust that call, "
              "or the new code will not converge"
              for k in changed if _site_key(k) in sites.modifiers]
    for gone in removed:
        if gone[0] not in ("mesh", "cube", "group"):
            continue
        own = sites.spans(_site_key(gone)) or ()
        mentions = [n for n, line in enumerate(sites.source.text.splitlines(), 1)
                    if re.search(r"[\"']" + re.escape(gone[1]) + r"([\"']|:)", line)
                    and not any(a <= n <= b for a, b in own)]
        twin = next((k for k in new if k[0] == gone[0] and {f: v for f, v in act.entities[k].sig.items() if f != "parent"}
                     == {f: v for f, v in gen.entities[gone].sig.items() if f != "parent"}), None)
        if twin:
            lines.append(f"  ? {gone[0]} {gone[1]} may have been renamed to {twin[1]} (identical geometry): "
                         f"rename it in the recipe instead of deleting and adding")
        if mentions:
            lines.append(f"  ? {gone[0]} {gone[1]} is gone but the recipe still mentions it at "
                         f"{', '.join(f'L{n}' for n in mentions[:8])}: update binds, mirrors and anchors that use it")
    lines += [f"  ? cube {k[1]}: the recipe references '{k[1]}:...' anchors, which add_cube does not define; "
              "if it was built with add_box, edit that call's numbers instead"
              for k in changed if k[0] == "cube" and re.search(r"[\"']" + re.escape(k[1]) + ":", sites.source.text)]
    armatures = act.builder._armatures if act.builder is not None else {}
    lines += [f"  ? mesh {k[1]} is new and sits under the armature: bind it in the recipe as if you had built it"
              for k in new if k[0] == "mesh" and act.entities[k].parent in armatures]
    blocks, by_spans = [], {}
    for key in [*changed, *removed]:
        spans = sites.spans(_site_key(key))
        if spans is None:
            lines.append(f"  ! {key[0]} {key[1]}: no recipe statement found; edit the recipe by hand")
        else:
            by_spans.setdefault(spans, []).append(key)
    for spans, keys in by_spans.items():
        touched = sites.touched(spans)
        scene_keys = [k for site_key in sorted(touched) for k in _scene_keys(site_key, act)]
        code, blockers = emit(act, scene_keys, mode)
        label = ", ".join(f"{k[1]}" for k in keys)
        if blockers:
            lines.append(f"  ! {recipe_name} {_spans_text(spans)} (for {label}) cannot be applied: "
                         + "; ".join(blockers))
            continue
        rig = sorted(f"{kind} {name}" for kind, name in touched if kind in RIG_KINDS)
        creates = ", ".join(sorted({k[1] for k in scene_keys})) or "nothing that still exists"
        action = (f"replace {recipe_name} {_spans_text(spans)} (it creates: {creates})" if code else
                  f"delete {recipe_name} {_spans_text(spans)} (everything it creates was removed)")
        if len(spans) > 1:
            action += "; put the code at the first span and delete the others"
        text = f"# {action}\n{code}" if code else f"# {action}"
        if not code and all(k[0] == "clip" for k in keys):
            text = "# NOTE: if you only regenerated the model, run Tools.animation_export instead of applying this\n" + text
        if rig:
            text = (f"# NOTE: this statement also creates {', '.join(rig[:6])}{' ...' if len(rig) > 6 else ''}: "
                    "bones, armatures and weights are not part of this block, so keep or recreate them in the "
                    "recipe\n" + text)
        blocks.append((f"{_spans_text(spans)} [{label}]", _fit(text, spans, sites, names, default, var)))
    if new:
        code, blockers = emit(act, new, mode)
        if blockers:
            lines.append("  ! new entities cannot be applied: " + "; ".join(blockers))
        else:
            last = sites.last_span()
            where = f"after {recipe_name} L{last[1]}" if last else "at the end of the build"
            text = f"# add {where} (the last statement that builds anything), before the return or export\n{code}"
            blocks.append((f"new [{', '.join(k[1] for k in new)}]", _fit(text, [last or (0, 0)], sites, names, default, var)))
    return lines, blocks, bool(changed or new or removed)


def _snapshot(model_path, project_dir):
    """Keep a copy of the edited bbmodel under history/ (once per distinct content); None if already there."""
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()[:8]
    folder = project_dir / "history"
    if any(folder.glob(f"model_*_{digest}.bbmodel")):
        return None
    folder.mkdir(exist_ok=True)
    target = folder / f"model_{datetime.now():%Y%m%d-%H%M%S}_{digest}.bbmodel"
    shutil.copyfile(model_path, target)
    return target


def _load(script, project_dir, model_path, actual, clips):
    recipe = resolve_asset(model_path).scripts / script
    capture = capture_recipe(recipe)
    if model_path.resolve() not in capture.documents:
        raise RuntimeError(f"{script} did not write {model_path.name}")
    gen = build_scene(capture.documents[model_path.resolve()], clips=clips, geometry_only=True)
    if clips:   # the bbmodel may hold clips the recipe never declared: those are new, not "already generated"
        gen.entities = {k: e for k, e in gen.entities.items() if k[1] in capture.declared_clips}
    act = build_scene(actual, clips=clips, geometry_only=True)
    return recipe, capture, gen, act


STAGES = (("model", "generate_model.py", False), ("animation", "generate_animation.py", True))

def _stage(label, script, project_dir, model_path, actual, clips, full=False):
    recipe, capture, gen, act = _load(script, project_dir, model_path, actual, clips)
    if clips and gen.entities and not actual.get("animations"):
        return ["  ? the recipe declares clips the model does not hold yet: run animation_export"], [], False
    sites = Sites(RecipeSource(recipe), capture.sites, capture.modifiers)
    mode = gen.mode
    lines = [f"  ? {note}" for note in act.notes]
    if not clips and act.mode != mode:
        lines.append(f"  ! modeling_mode: the recipe builds {mode!r}, the bbmodel says {act.mode!r}")
    more, blocks, found = report(label, script, gen, act, sites, mode, capture.names,
                                 capture.default_names, "editor" if clips else "builder", full)
    return lines + more, blocks, found or any(not line.startswith("  ?") for line in lines)


def _orphan_clips(actual, project_dir, model_path):
    """Clips in the bbmodel with no animation recipe: they vanish when the model is regenerated."""
    act = build_scene(actual, clips=True)
    code, blockers = emit(act, list(act.entities), "free")
    scaffold = ("from Tools.recipe_context import recipe_paths\nfrom lib import AnimationEditor\n\n"
                "model = recipe_paths(__file__).model\n"
                f"editor = AnimationEditor.from_bbmodel(model)\n{code}\neditor.save()")
    lines = [f"  ! scripts/generate_animation.py does not exist, so regenerating the model erases: "
             + ", ".join(k[1] for k in act.entities)]
    lines += [f"  ! cannot apply: {b}" for b in blockers]
    return lines, ([] if blockers else [("new file scripts/generate_animation.py",
                                         "# create scripts/generate_animation.py with:\n" + scaffold)])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Show what the user changed in model.bbmodel compared with what the recipes generate: which "
                    "part, which vertex or face, old and new values. The edited model is copied to history/.")
    parser.add_argument("project", help="projects/<name>")
    parser.add_argument("--only", choices=("model", "animation"), help="Check just one recipe")
    parser.add_argument("--full", action="store_true",
                        help="Everything: no line limit, every vertex and face of new parts, and ready-made code")
    parser.add_argument("--emit", metavar="NAME", help="Print ready-made code only for the parts that mention NAME")
    parser.add_argument("--verbose", action="store_true", help="Print the full traceback when a recipe fails")
    args = parser.parse_args(argv)
    project_dir, model_path = resolve_model_target(args.project)
    try:
        actual = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"[edit_diff] FAIL cannot read {model_path}: {exc}", file=sys.stderr)
        return 2
    differences, printed = False, []
    for label, script, clips in STAGES:
        if args.only not in (None, label):
            continue
        try:
            if (resolve_asset(args.project).scripts / script).is_file():
                lines, blocks, found = _stage(label, script, project_dir, model_path, actual, clips, args.full)
            elif clips and actual.get("animations"):
                (lines, blocks), found = _orphan_clips(actual, project_dir, model_path), True
            elif not clips:
                lines, blocks, found = [f"  ! scripts/generate_model.py does not exist: create it with "
                                        f"py -3.12 -m Tools.model_import {model_path} {project_dir}"], [], True
            else:
                continue
        except (Exception, SystemExit) as exc:
            frames = [f for f in traceback.extract_tb(exc.__traceback__) if Path(f.filename).name == script]
            where = f" (at {script} line {frames[-1].lineno}: {frames[-1].line})" if frames else ""
            print(f"[edit_diff] FAIL {label}: {type(exc).__name__}: {exc}{where}", file=sys.stderr)
            if args.verbose:
                traceback.print_exc()
            return 2
        differences |= found
        print(f"[edit_diff] {label}: {'differences' if found else 'no differences'}")
        print("\n".join(lines))
        printed += [(label, title, code) for title, code in blocks]
    if differences:
        saved = _snapshot(model_path, project_dir)
        if saved:
            print(f"[edit_diff] the edited model was copied to {saved.relative_to(project_dir).as_posix()}")
    for label, title, code in (printed if args.full or args.emit else []):
        if args.emit and args.emit not in title:
            continue
        print(f"\n# --- {label} snippet: {title}\n{code}")
    return 1 if differences else 0


if __name__ == "__main__":
    raise SystemExit(main())
