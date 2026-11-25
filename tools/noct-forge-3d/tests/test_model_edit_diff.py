import contextlib
import io
import json
import re
import runpy
import tempfile
import textwrap
import unittest
import uuid
from pathlib import Path

from Tools.edit_diff import main as edit_diff
from Tools.asset_init import init_project
from Tools._resolve import resolve_asset

MODEL_RECIPE = '''
from pathlib import Path
from Tools.recipe_context import recipe_paths
from lib.model_builder import ModelBuilder


def build():
    builder = ModelBuilder("t")
    builder.add_group("root")
    builder.add_transform_group("jaw", "root", pivot=(0, 2, 0))
    builder.add_cylinder("part", "jaw", radius=1, height=2, segments=8)
    rig = builder.add_armature("rig", parent="root")
    rig.add_bone("upper", between=((0, 0, 0), (0, 2, 0)))
    return builder


if __name__ == "__main__":
    build().export_bbmodel(recipe_paths(__file__).model)
'''

ANIMATION_RECIPE = '''
from pathlib import Path
from Tools.recipe_context import recipe_paths
from lib.animation import AnimationEditor

model = recipe_paths(__file__).model
editor = AnimationEditor.from_bbmodel(model)
clip = editor.animation("nod", duration=1, loop=True)
clip.group("jaw").key(0, rotation=(0, 0, 0)).key(0.5, rotation=(20, 0, 0), interpolation="constant")
clip.bone("upper", armature="rig").key(0, rotation=(0, 0, 5))
editor.save()
'''

BOX_RECIPE = '''
from pathlib import Path
from Tools.recipe_context import recipe_paths
from lib.model_builder import ModelBuilder


def build():
    builder = ModelBuilder("b", modeling_mode="box")
    builder.add_group("root")
    builder.add_transform_group("arm", "root", pivot=(0, 4, 0))
    builder.add_box("block", "arm", size=(2, 4, 2), at=(0, 0, 0), anchor="base")
    builder.add_box("cap", "arm", size=(2, 1, 2), at="block:top", anchor="base")
    return builder


if __name__ == "__main__":
    build().export_bbmodel(recipe_paths(__file__).model)
'''

LOOP_RECIPE = '''
from pathlib import Path
from Tools.recipe_context import recipe_paths
from lib.model_builder import ModelBuilder


def crate(builder, name, x):
    builder.add_box(name, "root", size=(2, 2, 2), at=(x, 1, 0))


def build():
    builder = ModelBuilder("loops")
    builder.add_group("root")
    for i in range(3):
        builder.add_box(f"crate_{i}", "root", size=(2, 2, 2), at=(i * 4, 1, 0))
    crate(builder, "solo_a", 20)
    crate(builder, "solo_b", 24)
    return builder


if __name__ == "__main__":
    build().export_bbmodel(recipe_paths(__file__).model)
'''

RIG_RECIPE = '''
from pathlib import Path
from Tools.recipe_context import recipe_paths
from lib import ModelBuilder, Profile, SegmentSection

RINGS = (("base", 0), ("before", .4), ("joint", .5), ("after", .6), ("tip", 1))


def build():
    builder = ModelBuilder("rigged", require_integer_dimensions=False)
    rig = builder.add_armature("character")
    for side, x in (("L", 3), ("R", -3)):
        builder.add_segment(f"limb_{side}", rig, start=(x, 0, 0), end=(x, 10, 0), sections=tuple(
            SegmentSection(name, t, Profile.circle(1, segments=4)) for name, t in RINGS))
    for side in ("L", "R"):
        rig.add_chain(f"limb_chain_{side}", joints=(f"limb_{side}:base", f"limb_{side}:joint", f"limb_{side}:tip"),
                      names=(f"proximal_{side}", f"distal_{side}"), connected=False)
    for side in ("L", "R"):
        rig.bind(f"limb_{side}", mode="hard", chain=f"limb_chain_{side}")
    return builder


if __name__ == "__main__":
    build().export_bbmodel(recipe_paths(__file__).model)
'''

COMPREHENSION_RECIPE = '''
from pathlib import Path
from Tools.recipe_context import recipe_paths
from lib.model_builder import ModelBuilder


def build():
    b = ModelBuilder("comp", modeling_mode="box")
    b.add_group("root")
    cubes = [b.add_cube(f"d{i}", "root", from_=(20 + i, 0, 0), to_=(21 + i, 1, 1)) for i in range(2)]
    if True:
        b.add_cube("inner", "root", from_=(40, 0, 0), to_=(41, 1, 1))
    return b


if __name__ == "__main__":
    build().export_bbmodel(recipe_paths(__file__).model)
'''

SOCKET_RECIPE = MODEL_RECIPE.replace(
    "    rig = builder.add_armature",
    "    builder.add_socket(\"hand\", \"jaw\", at=(0, 3, 0))\n    rig = builder.add_armature")

RIG_ONE_LOOP_RECIPE = '''
from pathlib import Path
from Tools.recipe_context import recipe_paths
from lib import ModelBuilder, Profile, SegmentSection

RINGS = (("base", 0), ("before", .4), ("joint", .5), ("after", .6), ("tip", 1))


def build():
    builder = ModelBuilder("rigged", require_integer_dimensions=False)
    rig = builder.add_armature("character")
    for side, x in (("L", 3), ("R", -3)):
        builder.add_segment(f"limb_{side}", rig, start=(x, 0, 0), end=(x, 10, 0), sections=tuple(
            SegmentSection(name, t, Profile.circle(1, segments=4)) for name, t in RINGS))
        rig.add_chain(f"limb_chain_{side}", joints=(f"limb_{side}:base", f"limb_{side}:joint", f"limb_{side}:tip"),
                      names=(f"proximal_{side}", f"distal_{side}"), connected=False)
        rig.bind(f"limb_{side}", mode="hard", chain=f"limb_chain_{side}")
    return builder


if __name__ == "__main__":
    build().export_bbmodel(recipe_paths(__file__).model)
'''

BLOCK = re.compile(r"# --- (model|animation) snippet: ([^\n]*)\n(.*?)(?=\n# --- |\Z)", re.S)


class ProjectCase(unittest.TestCase):
    model_recipe_text = MODEL_RECIPE
    animation_recipe_text = ANIMATION_RECIPE

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.project = Path(folder.name) / "proj"
        init_project(self.project, asset_id="proj")
        context = resolve_asset(f"{self.project}#proj")
        self.model_recipe = context.scripts / "generate_model.py"
        self.animation_recipe = context.scripts / "generate_animation.py"
        if not self.animation_recipe_text:
            self.animation_recipe.unlink(missing_ok=True)
        self.model = context.model
        self.model_recipe.write_text(self.model_recipe_text, encoding="utf-8")
        if self.animation_recipe_text:
            self.animation_recipe.write_text(self.animation_recipe_text, encoding="utf-8")
        self.regenerate()

    def regenerate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            runpy.run_path(str(self.model_recipe), run_name="__main__")
            if self.animation_recipe.exists():
                runpy.run_path(str(self.animation_recipe), run_name="__main__")

    def diff(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = edit_diff([str(self.project), "--full", *extra])
        return code, out.getvalue() + err.getvalue()

    def edit_model(self, change):
        data = json.loads(self.model.read_text(encoding="utf-8"))
        change(data)
        self.model.write_text(json.dumps(data), encoding="utf-8")

    def read_model(self):
        return json.loads(self.model.read_text(encoding="utf-8"))

    @staticmethod
    def blocks(output):
        return [(m.group(2), m.group(3).rstrip("\n")) for m in BLOCK.finditer(output)]

    def block(self, output, needle):
        found = next(((t, b) for t, b in self.blocks(output) if needle in t), None)
        self.assertIsNotNone(found, f"no snippet block for {needle!r} in:\n{output}")
        return found

    def apply(self, output, *needles, recipe=None):
        """Do what the agent does: put each block where its header says, bottom of the file first."""
        recipe = recipe or self.model_recipe
        lines = recipe.read_text(encoding="utf-8").splitlines()
        edits = []
        for title, body in self.blocks(output):
            if needles and not any(n in title for n in needles):
                continue
            code = "\n".join(body.splitlines()[1:])
            spans = [(int(a), int(b or a)) for a, b in re.findall(r"L(\d+)(?:-(\d+))?", title.split("[")[0])]
            edits.append((spans, code, title))
        for spans, code, title in sorted(edits, key=lambda e: -(e[0][0][0] if e[0] else 10 ** 9)):
            if not spans:
                anchor = max(i for i, l in enumerate(lines) if l.strip().startswith(("return ", "editor.save()")))
                lines[anchor:anchor] = code.splitlines()
                continue
            first, last = spans[0]
            for start, end in reversed(spans[1:]):
                del lines[start - 1:end]
            lines[first - 1:last] = code.splitlines() if code else []
        recipe.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def settle(self, *extra, rounds=4):
        for _ in range(rounds):
            code, output = self.diff(*extra)
            if code == 0:
                return output
            self.assertEqual(code, 1, output)
            self.apply(output, recipe=self.model_recipe if "animation" not in extra else self.animation_recipe)
        self.fail(f"still differences after {rounds} rounds:\n{output}")


def element(data, name, kind=None):
    return next(e for e in data["elements"] if e.get("name") == name and (kind is None or e["type"] == kind))


def find_node(data, uid):
    stack = [(None, n) for n in data["outliner"]]
    while stack:
        parent, node = stack.pop()
        if (node if isinstance(node, str) else node["uuid"]) == uid:
            return parent, node
        if isinstance(node, dict):
            stack.extend((node, c) for c in node.get("children", []))
    raise KeyError(uid)


def move_node(data, uid, new_parent_uuid):
    parent, node = find_node(data, uid)
    parent["children"].remove(node)
    find_node(data, new_parent_uuid)[1]["children"].append(node)


def add_child(data, parent_name, new_element):
    data["elements"].append(new_element)
    parent = next(g for g in data["groups"] if g["name"] == parent_name)
    find_node(data, parent["uuid"])[1]["children"].append(new_element["uuid"])


class FreeModelEditTests(ProjectCase):
    def test_untouched_project_has_no_differences(self):
        code, output = self.diff()
        self.assertEqual(code, 0, output)
        self.assertIn("model: no differences", output)
        self.assertIn("animation: no differences", output)

    def test_moved_vertex_is_reported_frozen_and_stable(self):
        def move(data):
            mesh = element(data, "part", "mesh")
            mesh["vertices"][next(iter(mesh["vertices"]))][0] += 0.25
        self.edit_model(move)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("vertex bottom_000 (in faces", output)
        self.assertIn("MeshDraft", self.block(output, "[part]")[1])

        self.apply(output)
        self.assertEqual(self.diff()[0], 0)
        self.regenerate()
        element(self.read_model(), "part", "mesh")
        self.assertEqual(self.diff()[0], 0)

    def test_frozen_mesh_stays_editable_in_code(self):
        def move(data):
            element(data, "part", "mesh")["vertices"]["bottom_000"][0] = 1.25
        self.edit_model(move)
        self.apply(self.diff()[1])
        self.model_recipe.write_text(
            self.model_recipe.read_text(encoding="utf-8").replace("(1.25, -1, 0)", "(1.3, -1, 0)"),
            encoding="utf-8")
        self.assertEqual(self.diff()[0], 1)
        self.regenerate()
        self.assertEqual(element(self.read_model(), "part", "mesh")["vertices"]["bottom_000"][0], 1.3)
        self.assertEqual(self.diff()[0], 0)

    def test_added_vertices_and_faces_survive_freezing_and_regeneration(self):
        def add_tetrahedron(data):
            mesh = element(data, "part", "mesh")
            mesh["vertices"].update({"t0": [0, 9, 0], "t1": [1, 9, 0], "t2": [0, 9, 1], "t3": [0, 10, 0]})
            for name, tri in {"tf0": ("t0", "t1", "t2"), "tf1": ("t0", "t3", "t1"),
                              "tf2": ("t1", "t3", "t2"), "tf3": ("t2", "t3", "t0")}.items():
                mesh["faces"][name] = {"vertices": list(tri), "texture": False}
        before = element(self.read_model(), "part", "mesh")
        self.edit_model(add_tetrahedron)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("+ face tf0: t0 t1 t2", output)
        self.apply(output)
        self.assertEqual(self.diff("--only", "model")[0], 0)
        self.regenerate()
        after = element(self.read_model(), "part", "mesh")
        self.assertEqual((len(after["vertices"]), len(after["faces"])),
                         (len(before["vertices"]) + 4, len(before["faces"]) + 4))
        self.assertEqual(self.diff("--only", "model")[0], 0)

    def test_a_deleted_vertex_does_not_leave_a_ring_that_breaks_the_code(self):
        def remove(data):
            mesh = element(data, "part", "mesh")
            mesh["faces"] = {k: f for k, f in mesh["faces"].items() if "bottom_000" not in f["vertices"]}
            del mesh["vertices"]["bottom_000"]
        self.edit_model(remove)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        block = self.block(output, "[part]")[1]
        self.assertIn("lost vertices in Blockbench and is not recreated", block)
        self.apply(output)
        self.regenerate()
        self.assertNotIn("bottom_000", element(self.read_model(), "part", "mesh")["vertices"])

    def test_deleting_a_face_opens_the_mesh_instead_of_breaking_the_recipe(self):
        before = element(self.read_model(), "part", "mesh")
        self.edit_model(lambda data: element(data, "part", "mesh")["faces"].pop(sorted(before["faces"])[0]))
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("- face cap_bottom_000", output)
        self.assertIn("closed=False", self.block(output, "[part]")[1])
        self.apply(output)
        self.regenerate()
        self.assertEqual(len(element(self.read_model(), "part", "mesh")["faces"]), len(before["faces"]) - 1)
        self.assertEqual(self.diff("--only", "model")[0], 0)

    def test_an_edge_shared_by_three_faces_is_reported_but_never_repaired(self):
        def fin(data):
            mesh = element(data, "part", "mesh")
            mesh["vertices"]["nv"] = [0, 5, 0]
            mesh["faces"]["fin"] = {"vertices": ["bottom_000", "bottom_001", "nv"], "texture": False}
        self.edit_model(fin)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("+ face fin: bottom_000 bottom_001 nv", output)
        self.assertIn("the builder rejects this", output)
        self.assertEqual(self.blocks(output), [])

    def test_a_concave_quad_is_reported_but_never_repaired(self):
        def arrow(data):
            new = {"name": "arrow", "origin": [0, 0, 0], "rotation": [0, 0, 0], "visibility": True,
                   "vertices": {"p0": [0, 0, 0], "p1": [2, 0, 0], "p2": [2, 2, 0], "p3": [1, 0.5, 0]},
                   "faces": {"f": {"vertices": ["p0", "p1", "p2", "p3"], "texture": False}},
                   "type": "mesh", "uuid": str(uuid.uuid4())}
            add_child(data, "jaw", new)
        self.edit_model(arrow)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("+ mesh arrow (parent jaw)", output)
        self.assertIn("the builder rejects this geometry", output)
        self.assertEqual(self.blocks(output), [])

    def test_a_locator_is_only_mentioned(self):
        def locate(data):
            jaw = next(g for g in data["groups"] if g["name"] == "jaw")
            locator = {"type": "locator", "name": "hand_socket", "position": [1, 3, 1], "rotation": [0, 0, 0],
                       "uuid": str(uuid.uuid4())}
            data["elements"].append(locator)
            find_node(data, jaw["uuid"])[1]["children"].append(locator["uuid"])
        self.edit_model(locate)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 0, output)
        self.assertIn("? locator hand_socket: the builder has no locators", output)

    def test_geometry_the_builder_would_reject_is_reported_with_the_change(self):
        def break_cap(data):
            element(data, "part", "mesh")["vertices"]["bottom_000"][0] = 2.5
        self.edit_model(break_cap)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("vertex bottom_000 (in faces", output)
        self.assertIn("the builder rejects this geometry", output)
        self.assertEqual(self.blocks(output), [])

    def test_new_mesh_is_frozen_under_its_parent(self):
        def add(data):
            copy = json.loads(json.dumps(element(data, "part", "mesh")))
            copy["name"], copy["uuid"] = "part2", str(uuid.uuid4())
            for vertex in copy["vertices"].values():
                vertex[1] += 5
            add_child(data, "jaw", copy)
        self.edit_model(add)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("+ mesh part2 (parent jaw)", output)
        self.assertIn("'part2', 'jaw'", self.block(output, "new")[1])
        self.apply(output)
        self.assertEqual(self.diff()[0], 0)

    def test_mesh_moved_to_another_group_is_reported_and_frozen(self):
        def reparent(data):
            root = next(g for g in data["groups"] if g["name"] == "root")
            move_node(data, element(data, "part", "mesh")["uuid"], root["uuid"])
        self.edit_model(reparent)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("parent jaw -> root", output)
        self.settle()
        self.regenerate()
        self.assertEqual(self.diff()[0], 0)

    def test_new_group_is_reported_and_frozen(self):
        def add(data):
            jaw = next(g for g in data["groups"] if g["name"] == "jaw")
            root = next(g for g in data["groups"] if g["name"] == "root")
            hat = json.loads(json.dumps(jaw))
            hat["name"], hat["uuid"] = "hat", str(uuid.uuid4())
            data["groups"].append(hat)
            find_node(data, root["uuid"])[1]["children"].append({"uuid": hat["uuid"], "isOpen": True, "children": []})
        self.edit_model(add)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("+ group hat (parent root)", output)
        self.assertIn("add_transform_group('hat', 'root'", self.block(output, "new")[1])
        self.apply(output)
        self.assertEqual(self.diff("--only", "model")[0], 0)

    def test_group_pivot_moved_is_frozen(self):
        def move(data):
            next(g for g in data["groups"] if g["name"] == "jaw")["origin"][1] += 1
        self.edit_model(move)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("pivot [0, 2, 0] -> [0, 3, 0]", output)
        self.settle("--only", "model")

    def test_group_and_its_mesh_deleted(self):
        def delete(data):
            jaw = next(g for g in data["groups"] if g["name"] == "jaw")
            part = element(data, "part", "mesh")
            parent, node = find_node(data, jaw["uuid"])
            parent["children"].remove(node)
            data["groups"].remove(jaw)
            data["elements"].remove(part)
        self.edit_model(delete)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("- group jaw", output)
        self.assertIn("- mesh part", output)
        self.settle("--only", "model")

    def test_renamed_mesh_is_a_removal_plus_a_new_mesh(self):
        element(json.loads(self.model.read_text(encoding="utf-8")), "part")
        self.edit_model(lambda data: element(data, "part", "mesh").update(name="part_renamed"))
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("+ mesh part_renamed", output)
        self.assertIn("- mesh part", output)
        self.settle("--only", "model")

    def test_a_missing_model_exits_2_and_a_failing_recipe_shows_its_traceback_on_request(self):
        self.model_recipe.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 2)
        self.assertIn("boom", output)
        self.assertNotIn("Traceback", output)
        self.assertIn("Traceback", self.diff("--only", "model", "--verbose")[1])
        self.model.unlink()
        code, output = self.diff()
        self.assertEqual(code, 2)
        self.assertIn("cannot read", output)

    def test_hidden_locked_and_recolored_are_ignored(self):
        self.edit_model(lambda data: element(data, "part", "mesh").update(visibility=False, locked=True, color=5))
        self.assertEqual(self.diff("--only", "model")[0], 0)

    def test_edited_keyframe_is_frozen_and_stable(self):
        def retime(data):
            clip = next(c for c in data["animations"] if c["name"] == "nod")
            jaw = next(g["uuid"] for g in data["groups"] if g["name"] == "jaw")
            key = next(k for k in clip["animators"][jaw]["keyframes"] if k["time"] == 0.5)
            key["data_points"][0]["x"] = 35
        self.edit_model(retime)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("~ clip nod", output)
        self.apply(output, recipe=self.animation_recipe)
        self.assertEqual(self.diff()[0], 0)
        self.regenerate()
        clip = next(c for c in self.read_model()["animations"] if c["name"] == "nod")
        values = [k["data_points"][0]["x"] for a in clip["animators"].values() for k in a["keyframes"]
                  if k["channel"] == "rotation" and k["time"] == 0.5]
        self.assertEqual(values, [35])

    def test_clips_without_an_animation_recipe_are_reported_and_scaffolded(self):
        self.animation_recipe.unlink()
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("does not exist, so regenerating the model erases: nod", output)
        title, body = self.block(output, "generate_animation.py")
        self.animation_recipe.write_text("\n".join(body.splitlines()[1:]) + "\n", encoding="utf-8")
        self.assertEqual(self.diff()[0], 0)


class BoxModelEditTests(ProjectCase):
    model_recipe_text = BOX_RECIPE
    animation_recipe_text = None

    def test_edited_cube_is_frozen_with_add_cube(self):
        self.edit_model(lambda data: element(data, "cap")["to"].__setitem__(0, element(data, "cap")["to"][0] + 1))
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("to [1, 5, 1] -> [2, 5, 1]", output)
        self.assertIn("builder.add_cube(", self.block(output, "[cap]")[1])
        self.apply(output)
        self.assertEqual(self.diff()[0], 0)
        self.regenerate()
        self.assertEqual(self.diff()[0], 0)

    def test_cube_that_others_anchor_to_warns_before_freezing(self):
        self.edit_model(lambda data: element(data, "block")["to"].__setitem__(1, element(data, "block")["to"][1] + 1))
        _, output = self.diff()
        self.assertIn("references 'block:...' anchors", output)

    def test_new_cube_is_frozen_under_its_parent(self):
        def add(data):
            copy = json.loads(json.dumps(element(data, "cap")))
            copy["name"], copy["uuid"] = "cap2", str(uuid.uuid4())
            for key in ("from", "to", "origin"):
                copy[key][1] += 10
            add_child(data, "arm", copy)
        self.edit_model(add)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("'cap2', 'arm'", self.block(output, "new")[1])
        self.apply(output)
        self.assertEqual(self.diff()[0], 0)

    def test_polygon_mesh_in_box_mode_is_emitted_with_a_note_about_the_mode(self):
        def add(data):
            add_child(data, "arm", {
                "name": "wedge", "origin": [0, 0, 0], "rotation": [0, 0, 0], "visibility": True,
                "vertices": {"a": [0, 0, 0], "b": [1, 0, 0], "c": [0, 1, 0]},
                "faces": {"f": {"vertices": ["a", "b", "c"], "texture": False}},
                "type": "mesh", "uuid": str(uuid.uuid4())})
        self.edit_model(add)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("+ mesh wedge", output)
        body = self.block(output, "new")[1]
        self.assertIn("# NOTE: this model is in box mode", body)
        self.assertIn("MeshDraft", body)


class LoopAndHelperEditTests(ProjectCase):
    model_recipe_text = LOOP_RECIPE
    animation_recipe_text = None

    def test_edit_inside_a_loop_unrolls_the_whole_loop(self):
        self.edit_model(lambda data: element(data, "crate_1")["to"].__setitem__(0, element(data, "crate_1")["to"][0] + 1))
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("~ cube crate_1", output)
        title, body = self.block(output, "[crate_1]")
        for name in ("crate_0", "crate_1", "crate_2"):
            self.assertIn(f"'{name}'", body)
        self.assertNotIn("solo_a", body)
        self.apply(output)
        text = self.model_recipe.read_text(encoding="utf-8")
        self.assertNotIn("for i in range(3)", text)
        self.assertEqual(self.diff()[0], 0)

    def test_edit_to_a_helper_call_replaces_only_that_call(self):
        self.edit_model(lambda data: element(data, "solo_b")["to"].__setitem__(1, element(data, "solo_b")["to"][1] + 3))
        code, output = self.diff()
        self.assertEqual(code, 1)
        title, body = self.block(output, "[solo_b]")
        self.assertIn("'solo_b'", body)
        self.assertNotIn("solo_a", body)
        self.apply(output)
        text = self.model_recipe.read_text(encoding="utf-8")
        self.assertIn('crate(builder, "solo_a", 20)', text)
        self.assertNotIn('crate(builder, "solo_b", 24)', text)
        self.assertEqual(self.diff()[0], 0)


class ComprehensionAndIndentationTests(ProjectCase):
    model_recipe_text = COMPREHENSION_RECIPE
    animation_recipe_text = None

    def test_entity_made_in_a_comprehension_is_replaced_without_touching_the_export(self):
        self.edit_model(lambda data: element(data, "d1")["to"].__setitem__(0, element(data, "d1")["to"][0] + 1))
        code, output = self.diff()
        self.assertEqual(code, 1)
        title, body = self.block(output, "[d1]")
        self.assertIn("'d0'", body)
        self.assertIn("'d1'", body)
        self.assertTrue(body.splitlines()[1].startswith("    b.add_cube("), body)
        self.apply(output)
        self.assertIn("export_bbmodel", self.model_recipe.read_text(encoding="utf-8"))
        self.assertEqual(self.diff()[0], 0)

    def test_block_uses_the_recipes_variable_and_indentation(self):
        self.edit_model(lambda data: element(data, "inner")["to"].__setitem__(1, element(data, "inner")["to"][1] + 2))
        code, output = self.diff()
        self.assertEqual(code, 1)
        title, body = self.block(output, "[inner]")
        self.assertTrue(body.splitlines()[1].startswith("        b.add_cube("), body)
        self.apply(output)
        self.assertEqual(self.diff()[0], 0)


def cube_json(name, frm, to):
    return {"name": name, "box_uv": False, "rescale": False, "locked": False, "visibility": True,
            "from": frm, "to": to, "autouv": 0, "color": 0, "origin": frm, "rotation": [0, 0, 0],
            "inflate": 0, "faces": {f: {"uv": [0, 0, 1, 1], "texture": 0}
                                    for f in ("north", "east", "south", "west", "up", "down")},
            "type": "cube", "uuid": str(uuid.uuid4())}


def bone(data, name):
    return next(e for e in data["elements"] if e["type"] == "armature_bone" and e["name"] == name)


class RiggedModelEditTests(ProjectCase):
    model_recipe_text = RIG_RECIPE
    animation_recipe_text = None

    def test_untouched_rig_has_no_differences(self):
        code, output = self.diff()
        self.assertEqual(code, 0, output)

    def test_repainted_weights_are_ignored_completely(self):
        def paint(data):
            distal = bone(data, "distal_L")
            key = next(k for k, w in distal["vertex_weights"].items() if w == 1.0)
            distal["vertex_weights"][key] = 0.5
            bone(data, "proximal_L")["vertex_weights"][key] = 0.5
        self.edit_model(paint)
        code, output = self.diff()
        self.assertEqual(code, 0, output)
        self.assertNotIn("bind", output)
        self.assertEqual(self.blocks(output), [])
    def test_weight_edits_are_ignored_completely(self):
        def unweight(data):
            distal = bone(data, "distal_L")
            key = next(k for k, w in distal["vertex_weights"].items() if w == 1.0)
            del distal["vertex_weights"][key]
        self.edit_model(unweight)
        code, output = self.diff()
        self.assertEqual(code, 0, output)
        self.assertNotIn("bind", output)
        self.assertNotIn("weights", output)
    def test_added_vertices_of_a_bound_mesh_converge_weighted_or_not(self):
        def add(weight_bone):
            def mutate(data):
                mesh = element(data, "limb_L", "mesh")
                pts = {"t0": [0, 30, 0], "t1": [1, 30, 0], "t2": [0, 30, 1], "t3": [0, 31, 0]}
                mesh["vertices"].update(pts)
                for name, tri in {"tf0": ("t0", "t1", "t2"), "tf1": ("t0", "t3", "t1"),
                                  "tf2": ("t1", "t3", "t2"), "tf3": ("t2", "t3", "t0")}.items():
                    mesh["faces"][name] = {"vertices": list(tri), "texture": False}
                if weight_bone:
                    for key in pts:
                        bone(data, weight_bone)["vertex_weights"][f"{mesh['uuid'][:6]}:{key}"] = 1.0
            return mutate
        for weight_bone in (None, "distal_L"):
            with self.subTest(weighted=bool(weight_bone)):
                self.setUp()
                self.edit_model(add(weight_bone))
                self.settle()
                self.regenerate()
                self.assertEqual(self.diff()[0], 0)

    def test_new_cube_at_the_outliner_root_gets_a_root_group(self):
        def add(data):
            new = cube_json("crate", [10, 0, 0], [12, 2, 2])
            data["elements"].append(new)
            data["outliner"].append(new["uuid"])
        self.edit_model(add)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("+ group root", output)
        self.assertIn("add_group('root'", self.block(output, "new")[1])
        self.apply(output)
        self.assertEqual(self.diff()[0], 0)

    def test_a_moved_bone_is_ignored_completely(self):
        self.edit_model(lambda data: bone(data, "distal_R")["rotation"].__setitem__(2, bone(data, "distal_R")["rotation"][2] + 10))
        code, output = self.diff()
        self.assertEqual(code, 0, output)
        self.assertNotIn("bone", output)
        self.assertEqual(self.blocks(output), [])
    def test_a_new_bone_is_ignored_completely(self):
        def add(data):
            source = bone(data, "distal_L")
            new = json.loads(json.dumps(source))
            new["name"], new["uuid"], new["children"], new["vertex_weights"] = "tip_L", str(uuid.uuid4()), [], {}
            data["elements"].append(new)
            source["children"].append(new["uuid"])
            find_node(data, source["uuid"])[1]["children"].append({"uuid": new["uuid"], "isOpen": True, "children": []})
        self.edit_model(add)
        code, output = self.diff()
        self.assertEqual(code, 0, output)
        self.assertNotIn("bone", output)
        self.assertEqual(self.blocks(output), [])


class SocketEditTests(ProjectCase):
    model_recipe_text = SOCKET_RECIPE
    animation_recipe_text = None

    def test_untouched_socket_has_no_differences(self):
        self.assertEqual(self.diff()[0], 0)

    def test_a_moved_socket_is_frozen_with_add_socket(self):
        def move(data):
            sockets = data["unhandled_root_fields"]["model_as_code"]["sockets"]
            sockets["hand"]["position"] = [1, 4, 0]
        self.edit_model(move)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("position [0, 3, 0] -> [1, 4, 0]", output)
        self.assertIn("builder.add_socket('hand', 'jaw'", self.block(output, "[hand]")[1])
        self.apply(output)
        self.assertEqual(self.diff()[0], 0)


class RigRepairTests(ProjectCase):
    model_recipe_text = RIG_RECIPE
    animation_recipe_text = None

    def test_a_new_mesh_under_the_armature_is_never_bound_automatically(self):
        def add(data):
            source = element(data, "limb_L", "mesh")
            new = json.loads(json.dumps(source))
            new["name"], new["uuid"] = "limb_C", str(uuid.uuid4())
            for vertex in new["vertices"].values():
                vertex[0] += 6
            for face in new["faces"].values():
                face.pop("uv", None)
            data["elements"].append(new)
            next(e for e in data["elements"] if e["type"] == "armature")["children"].append(new["uuid"])
            data["outliner"][0]["children"].append(new["uuid"])
        self.edit_model(add)
        code, output = self.diff()
        self.assertEqual(code, 1)
        self.assertIn("? mesh limb_C is new and sits under the armature: bind it in the recipe as if you had built it", output)
        body = self.block(output, "new")[1]
        self.assertNotIn(".bind(", body)
        self.assertNotIn("nearest", output)
        self.apply(output)
        recipe = self.model_recipe.read_text(encoding="utf-8")
        recipe = recipe.replace("    return builder", "    rig.bind('limb_C', bone='distal_L')\n    return builder")
        self.model_recipe.write_text(recipe, encoding="utf-8")
        self.assertEqual(self.diff()[0], 0)


class OneLoopRigTests(ProjectCase):
    model_recipe_text = RIG_ONE_LOOP_RECIPE
    animation_recipe_text = None

    def test_unrolling_a_loop_that_also_builds_bones_leaves_them_to_the_agent(self):
        def add_tetrahedron(data):
            mesh = element(data, "limb_L", "mesh")
            mesh["vertices"].update({"t0": [0, 30, 0], "t1": [1, 30, 0], "t2": [0, 30, 1], "t3": [0, 31, 0]})
            for name, tri in {"tf0": ("t0", "t1", "t2"), "tf1": ("t0", "t3", "t1"),
                              "tf2": ("t1", "t3", "t2"), "tf3": ("t2", "t3", "t0")}.items():
                mesh["faces"][name] = {"vertices": list(tri), "texture": False}
        self.edit_model(add_tetrahedron)
        code, output = self.diff()
        self.assertEqual(code, 1)
        title, body = self.block(output, "[limb_L]")
        self.assertIn("# NOTE: this statement also creates bind limb_L, bind limb_R, bone distal_L", body)
        self.assertIn("bone distal_L", body)
        self.assertIn("keep or recreate them in the recipe", body)
        self.assertNotIn("add_chain", body)
        self.assertNotIn(".bind(", body)


MODIFIER_RECIPE = MODEL_RECIPE.replace(
    "    rig = builder.add_armature",
    "    builder.rotate_element(\"part\", (0, 30, 0))\n    rig = builder.add_armature")


def add_clip(data, name="extra"):
    jaw = next(g["uuid"] for g in data["groups"] if g["name"] == "jaw")
    data["animations"].append({
        "uuid": str(uuid.uuid4()), "name": name, "loop": "once", "length": 1, "snapping": 20,
        "animators": {jaw: {"name": "jaw", "type": "bone", "keyframes": [
            {"uuid": str(uuid.uuid4()), "time": 0, "channel": "rotation", "interpolation": "linear",
             "data_points": [{"x": 0, "y": 0, "z": 0}]},
            {"uuid": str(uuid.uuid4()), "time": 0.5, "channel": "rotation", "interpolation": "linear",
             "data_points": [{"x": 30, "y": 0, "z": 0}]}]}}})


class SafetyNetTests(ProjectCase):
    def test_a_clip_added_in_blockbench_is_reported_and_frozen(self):
        self.edit_model(add_clip)
        code, output = self.diff("--only", "animation")
        self.assertEqual(code, 1, output)
        self.assertIn("+ clip extra", output)
        self.assertIn("editor.animation('extra'", self.block(output, "new")[1])
        self.apply(output, recipe=self.animation_recipe)
        self.assertEqual(self.diff("--only", "animation")[0], 0)
        self.regenerate()
        self.assertEqual({c["name"] for c in self.read_model()["animations"]}, {"nod", "extra"})

    def test_a_clip_the_recipe_declares_but_the_file_lacks_says_to_run_animation_export(self):
        self.edit_model(lambda data: data["animations"].clear())
        code, output = self.diff("--only", "animation")
        self.assertEqual(code, 0, output)
        self.assertIn("run animation_export", output)
        self.assertNotIn("delete", output)

    def test_numeric_string_keyframes_are_frozen_like_numbers(self):
        def edit(data):
            for animator in data["animations"][0]["animators"].values():
                for kf in animator["keyframes"]:
                    kf["data_points"][0] = {a: str(v) for a, v in kf["data_points"][0].items()}
            first = next(iter(data["animations"][0]["animators"].values()))["keyframes"][0]
            first["data_points"][0]["x"] = "12"
        self.edit_model(edit)
        code, output = self.diff("--only", "animation")
        self.assertEqual(code, 1, output)
        self.assertNotIn("cannot be frozen", output)
        self.apply(output, recipe=self.animation_recipe)
        self.assertEqual(self.diff("--only", "animation")[0], 0)

    def test_a_recipe_failure_names_the_line_that_raised(self):
        self.model_recipe.write_text("x = 1\nraise RuntimeError('boom')\n", encoding="utf-8")
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 2)
        self.assertIn("(at generate_model.py line 2: raise RuntimeError('boom'))", output)

    def test_emit_prints_only_the_named_block(self):
        def edit(data):
            part = element(data, "part", "mesh")
            part["vertices"]["bottom_000"][0] = 1.25
            copy = json.loads(json.dumps(part))
            copy["name"], copy["uuid"] = "part2", str(uuid.uuid4())
            for vertex in copy["vertices"].values():
                vertex[1] += 5
            add_child(data, "jaw", copy)
        self.edit_model(edit)
        _, emitted = self.diff("--only", "model", "--emit", "part2")
        self.assertEqual([t for t, _ in self.blocks(emitted)], ["new [part2]"])

    def test_a_project_without_a_recipe_is_told_the_exact_import_command(self):
        self.model_recipe.unlink()
        _, output = self.diff("--only", "model")
        self.assertIn("py -3.12 -m Tools.model_import", output)
        self.assertIn(str(self.project), output)


class ModifierTests(ProjectCase):
    model_recipe_text = MODIFIER_RECIPE

    def test_a_later_call_that_changes_the_part_is_pointed_out(self):
        self.edit_model(lambda data: element(data, "part", "mesh")["vertices"]["bottom_000"].__setitem__(0, 1.25))
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertRegex(output, r"\? mesh part is also changed later by the recipe at L\d+: remove or adjust that call")


class RemovedReferenceTests(ProjectCase):
    model_recipe_text = BOX_RECIPE
    animation_recipe_text = None

    def test_a_removed_part_the_recipe_still_uses_is_flagged(self):
        def drop(data):
            block = element(data, "block")
            data["elements"].remove(block)
            parent, node = find_node(data, block["uuid"])
            parent["children"].remove(node)
        self.edit_model(drop)
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertRegex(output, r"\? cube block is gone but the recipe still mentions it at L\d+")

    def test_a_rename_is_recognised_from_identical_geometry(self):
        self.edit_model(lambda data: element(data, "cap").update(name="cap_renamed"))
        code, output = self.diff("--only", "model")
        self.assertEqual(code, 1)
        self.assertIn("? cube cap may have been renamed to cap_renamed (identical geometry)", output)


class CaptureTests(unittest.TestCase):
    def test_the_recipe_sees_only_its_own_argv_and_argv_is_restored(self):
        from lib.recipe_capture import capture_recipe
        import sys
        with tempfile.TemporaryDirectory() as folder:
            recipe = Path(folder) / "recipe.py"
            recipe.write_text("import sys\nassert sys.argv == [__file__], sys.argv\n", encoding="utf-8")
            before = list(sys.argv)
            capture_recipe(recipe)
            self.assertEqual(sys.argv, before)

if __name__ == "__main__":
    unittest.main()


class DetailedReportTests(ProjectCase):
    """By default edit_diff only reports, precisely; the agent edits the recipe."""

    def run_diff(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = edit_diff([str(self.project), *extra])
        return code, out.getvalue() + err.getvalue()

    def test_a_moved_vertex_names_the_mesh_the_vertex_the_faces_and_both_positions(self):
        self.edit_model(lambda data: element(data, "part", "mesh")["vertices"]["bottom_000"].__setitem__(0, 1.25))
        recipe = self.model_recipe.read_bytes()
        code, output = self.run_diff()
        self.assertEqual(code, 1)
        self.assertIn("~ mesh part (parent jaw)", output)
        self.assertIn("vertex bottom_000 (in faces cap_bottom_000, cap_bottom_003, side_000, side_007): "
                      "[1, -1, 0] -> [1.25, -1, 0]", output)
        self.assertNotIn("MeshDraft", output)
        self.assertLess(len(output.splitlines()), 8, output)
        self.assertEqual(self.model_recipe.read_bytes(), recipe)

    def test_a_rotation_change_shows_only_the_rotation(self):
        self.edit_model(lambda data: element(data, "part", "mesh").__setitem__("rotation", [0, 45, 0]))
        output = self.run_diff()[1]
        self.assertIn("rotation [0, 0, 0] -> [0, 45, 0]", output)
        self.assertNotIn("vertex", output)

    def test_a_deleted_mesh_says_only_that_it_is_gone(self):
        self.edit_model(lambda data: data["elements"].remove(element(data, "part", "mesh")))
        output = self.run_diff()[1]
        self.assertIn("- mesh part", output)
        self.assertNotIn("rotation", output.split("- mesh part")[1].splitlines()[0])

    def test_a_new_mesh_is_summarised_and_full_lists_every_vertex_and_the_code(self):
        def add(data):
            copy = json.loads(json.dumps(element(data, "part", "mesh")))
            copy["name"], copy["uuid"] = "extra", str(uuid.uuid4())
            for vertex in copy["vertices"].values():
                vertex[1] += 5
            add_child(data, "jaw", copy)
        self.edit_model(add)
        short = self.run_diff()[1]
        self.assertIn("+ mesh extra (parent jaw)", short)
        self.assertIn("18 vertices, 16 faces", short)
        self.assertNotIn("vertex bottom_000:", short)
        self.assertNotIn("MeshDraft", short)
        full = self.run_diff("--full")[1]
        self.assertIn("vertex bottom_000: [1, 4, 0]", full)
        self.assertIn("MeshDraft", full)

    def test_a_changed_keyframe_names_the_track_time_and_values(self):
        def edit(data):
            animator = next(iter(data["animations"][0]["animators"].values()))
            animator["keyframes"][1]["data_points"][0]["x"] = 35
        self.edit_model(edit)
        output = self.run_diff("--only", "animation")[1]
        self.assertRegex(output, r"t=0\.5: \[20, 0, 0\] constant -> \[35, 0, 0\] constant")

    def test_the_edited_model_is_copied_to_history_once_and_only_when_it_differs(self):
        self.assertEqual(self.run_diff()[0], 0)
        self.assertFalse((self.project / "history").exists())
        self.edit_model(lambda data: element(data, "part", "mesh")["vertices"]["bottom_000"].__setitem__(0, 1.25))
        edited = self.model.read_bytes()
        self.assertIn("copied to history/model_", self.run_diff()[1])
        self.assertNotIn("copied to history", self.run_diff()[1])
        (saved,) = (self.project / "history").glob("model_*.bbmodel")
        self.assertEqual(saved.read_bytes(), edited)

    def test_a_long_report_is_capped_and_full_shows_everything(self):
        def edit(data):
            for vertex in element(data, "part", "mesh")["vertices"].values():
                vertex[1] += 0.5
        self.edit_model(edit)
        short, full = self.run_diff()[1], self.run_diff("--full")[1]
        self.assertIn("more (run with --full)", short)
        self.assertNotIn("more (run with --full)", full)
        self.assertLess(len(short.splitlines()), len(full.splitlines()))


if __name__ == "__main__":
    unittest.main()
