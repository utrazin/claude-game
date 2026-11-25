import json
import tempfile
import unittest
import warnings
from pathlib import Path

from lib import AnimationEditor, ModelBuilder


def model(directory):
    builder = ModelBuilder("m", modeling_mode="box")
    builder.add_group("root")
    builder.add_transform_group("arm", "root", pivot=(0, 8, 0))
    builder.add_box("arm_box", "arm", size=(2, 6, 2), at=(0, 8, 0), anchor="top")
    return builder.export_bbmodel(Path(directory) / "model.bbmodel")


def names(path):
    return [a["name"] for a in json.loads(path.read_text(encoding="utf-8"))["animations"]]


class AnimationExtrasTests(unittest.TestCase):
    def test_catmullrom_and_hold_are_written_as_bbmodel_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = model(tmp)
            editor = AnimationEditor.from_bbmodel(path)
            clip = editor.animation("pose", duration=1, loop="hold")
            clip.group("arm").key(0, rotation=(0, 0, 0), interpolation="catmullrom").key(1, rotation=(10, 0, 0))
            editor.save()
            data = json.loads(path.read_text(encoding="utf-8"))["animations"][0]
        self.assertEqual(data["loop"], "hold")
        self.assertEqual(next(iter(data["animators"].values()))["keyframes"][0]["interpolation"], "catmullrom")

    def test_a_clip_can_be_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = model(tmp)
            editor = AnimationEditor.from_bbmodel(path)
            for name in ("a", "b"):
                editor.animation(name, duration=1).group("arm").key(0, rotation=(0, 0, 0))
            editor.save()
            self.assertEqual(names(path), ["a", "b"])
            editor = AnimationEditor.from_bbmodel(path)
            editor.remove_animation("a")
            editor.save()
            self.assertEqual(names(path), ["b"])
            with self.assertRaises(KeyError):
                AnimationEditor.from_bbmodel(path).remove_animation("missing")

    def test_a_loop_that_ends_on_another_pose_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = model(tmp)
            editor = AnimationEditor.from_bbmodel(path)
            editor.animation("swing", duration=1, loop=True).group("arm").key(0, rotation=(0, 0, 0)).key(1, rotation=(30, 0, 0))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                editor.save()
        self.assertTrue(any("the loop will jump" in str(w.message) for w in caught))

    def test_a_matching_loop_does_not_warn(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = model(tmp)
            editor = AnimationEditor.from_bbmodel(path)
            editor.animation("swing", duration=1, loop=True).group("arm").key(0, rotation=(0, 0, 0)).key(1, rotation=(0, 0, 0))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                editor.save()
        self.assertEqual(caught, [])

    def test_loop_warnings_reach_animation_export_and_a_full_turn_is_not_a_jump(self):
        from Tools.animation_export import export_animations
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset

        recipe = (
            "from Tools.recipe_context import recipe_paths\n"
            "from lib import AnimationEditor\n"
            "model = recipe_paths(__file__).model\n"
            "editor = AnimationEditor.from_bbmodel(model)\n"
            "editor.animation('jump', duration=1, loop=True).group('arm').key(0, rotation=(0, 0, 0)).key(1, rotation=(30, 0, 0))\n"
            "editor.animation('spin', duration=1, loop=True).group('arm').key(0, rotation=(0, 0, 0)).key(1, rotation=(360, 0, 0))\n"
            "editor.save()\n")
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            init_project(project, asset_id="anim", animation=True)
            model(resolve_asset(f"{project}#anim").model.parent)
            (resolve_asset(f"{project}#anim").scripts / "generate_animation.py").write_text(recipe, encoding="utf-8")
            report = export_animations(project)
        self.assertEqual(report["status"], "pass", report)
        self.assertTrue(any("'jump'" in note and "the loop will jump" in note for note in report["warnings"]))
        self.assertFalse(any("'spin'" in note for note in report["warnings"]))


if __name__ == "__main__":
    unittest.main()
