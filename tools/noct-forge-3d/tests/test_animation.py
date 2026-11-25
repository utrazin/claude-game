import json
import math
import tempfile
import unittest
from pathlib import Path

from lib.animation import AnimationEditor, validate_animations
from lib.model_builder import ModelBuilder
from Tools.asset_status import asset_status
from Tools.uv_builder import UVBuilder
from Tools.TexturePainter import TexturePainter
from Tools.animation_export import export_animations


class AnimationEditorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = Path(self.folder.name) / "model.bbmodel"
        builder = ModelBuilder("animated")
        builder.add_group("root")
        builder.add_transform_group("jaw", "root", pivot=(0, 2, 0))
        builder.add_cube("jaw_mesh", "jaw", from_=(-1, 1, -1), to_=(1, 3, 1))
        rig = builder.add_armature("rig", parent="root")
        rig.add_bone("upper", between=((0, 0, 0), (0, 2, 0)))
        builder.export_bbmodel(self.model)

    def test_controls_and_multiple_native_clips(self):
        editor = AnimationEditor.from_bbmodel(self.model)
        self.assertEqual({(c.kind, c.name) for c in editor.controls()},
                         {("group", "jaw"), ("bone", "upper")})
        talk = editor.animation("talk", duration=1, loop=True)
        talk.group("jaw").key(0, rotation=(0, 0, 0), interpolation="constant").key(0.5, rotation=(25, 0, 0))
        wave = editor.animation("wave", duration=2)
        wave.bone("upper", armature="rig").sample(
            "rotation", 0, 2, 4, lambda t: (0, 0, math.sin(math.pi * t) * 20))
        editor.save()
        data = json.loads(self.model.read_text(encoding="utf-8"))
        self.assertEqual(validate_animations(data)["animations"], 2)
        self.assertEqual(data["animations"][0]["loop"], "loop")
        jaw_uuid = next(c.uuid for c in editor.controls() if c.name == "jaw")
        self.assertEqual(data["animations"][0]["animators"][jaw_uuid]["type"], "bone")
        self.assertEqual(data["animations"][0]["animators"][jaw_uuid]["keyframes"][0]["interpolation"], "step")

    def test_sample_ends_exactly_on_the_requested_time(self):
        # first + span * count / count overshoots `end` for many intervals (0.8 s at 120 fps
        # gives 0.8000000000000002), which used to abort the recipe at the duration check.
        cases = [(0.0, 0.8, 120), (0.1, 0.4, 24), (0.2, 0.8, 24), (0.0, 1.7, 24), (0.35, 1.55, 60)]
        for first, last, fps in cases:
            with self.subTest(first=first, last=last, fps=fps):
                editor = AnimationEditor.from_bbmodel(self.model)
                clip = editor.animation("probe", duration=last)
                clip.group("jaw").sample("rotation", first, last, fps, lambda t: (t, 0, 0))
                times = sorted(kf["time"] for kf in clip._tracks[editor._resolve_any("jaw").uuid])
                self.assertEqual(times[0], first)
                self.assertEqual(times[-1], last)
                self.assertEqual(len(times), round((last - first) * fps) + 1)

    def test_upsert_preserves_unmentioned_and_clip_identity(self):
        editor = AnimationEditor.from_bbmodel(self.model)
        editor.animation("keep", duration=1).group("jaw").key(0, rotation=(0, 0, 0))
        editor.animation("change", duration=1).group("jaw").key(0, rotation=(0, 0, 0))
        editor.save()
        before = json.loads(self.model.read_text(encoding="utf-8"))["animations"]
        document = json.loads(self.model.read_text(encoding="utf-8"))
        root_uuid = next(group["uuid"] for group in document["groups"] if group["name"] == "root")
        document["animations"].append({"uuid": "manual", "name": "manual_folder",
            "length": 1, "loop": "once", "animators": {root_uuid: {"type": "bone",
            "keyframes": [{"time": 0, "channel": "rotation", "data_points": [{"x": 0, "y": 0, "z": 0}]}]}}})
        self.model.write_text(json.dumps(document), encoding="utf-8")
        editor = AnimationEditor.from_bbmodel(self.model)
        editor.animation("change", duration=2).group("jaw").key(0, rotation=(10, 0, 0))
        editor.save()
        after = json.loads(self.model.read_text(encoding="utf-8"))["animations"]
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1]["uuid"], before[1]["uuid"])
        self.assertEqual(after[1]["length"], 2)
        self.assertEqual(after[2], document["animations"][2])

    def test_ambiguous_name_and_transactional_validation(self):
        data = json.loads(self.model.read_text(encoding="utf-8"))
        second = dict(next(g for g in data["groups"] if g["name"] == "jaw"))
        second["uuid"] = "d2e9853d-c1ba-4729-948a-cf16366901f6"
        data["groups"].append(second)
        data["outliner"].append({"uuid": second["uuid"], "children": []})
        self.model.write_text(json.dumps(data), encoding="utf-8")
        editor = AnimationEditor.from_bbmodel(self.model)
        clip = editor.animation("ambiguous", duration=1)
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            clip.group("jaw")
        clip.group("root/jaw").key(0, rotation=(0, 0, 0))
        source = self.model.read_bytes()
        data["animations"] = [{"name": "broken", "length": 1, "loop": "once",
                               "animators": {"gone": {"keyframes": []}}}]
        self.model.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "changed"):
            editor.save()
        self.assertNotEqual(self.model.read_bytes(), source)
        editor = AnimationEditor.from_bbmodel(self.model)
        editor.animation("new", duration=1).group("root/jaw").key(0, rotation=(0, 0, 0))
        source = self.model.read_bytes()
        with self.assertRaisesRegex(ValueError, "missing control"):
            editor.save()
        self.assertEqual(self.model.read_bytes(), source)

    def test_model_regeneration_clears_then_animation_stage_restores(self):
        editor = AnimationEditor.from_bbmodel(self.model)
        editor.animation("jaw_open", duration=1).group("jaw").key(0, rotation=(0, 0, 0))
        editor.save()
        self.assertEqual(len(json.loads(self.model.read_text())["animations"]), 1)

    def test_model_uv_texture_animation_pipeline(self):
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        proj = Path(self.folder.name) / "proj"
        init_project(proj, asset_id="anim")
        context = resolve_asset(f"{proj}#anim")
        self.model = context.model
        builder = ModelBuilder("animated")
        builder.add_group("root")
        builder.add_transform_group("jaw", "root", pivot=(0, 2, 0))
        builder.add_cube("jaw_mesh", "jaw", from_=(-1, 1, -1), to_=(1, 3, 1))
        rig = builder.add_armature("rig", parent="root")
        rig.add_bone("upper", between=((0, 0, 0), (0, 2, 0)))
        builder.export_bbmodel(self.model)
        UVBuilder(self.model, start_size=(32, 32)).save()
        texture = context.texture
        painter = TexturePainter.from_bbmodel(self.model)
        painter.fill_all("#6699cc")
        painter.save(texture)
        editor = AnimationEditor.from_bbmodel(self.model)
        editor.animation("talk", duration=1).group("jaw").key(0, rotation=(0, 0, 0))
        editor.save()
        status = asset_status(proj)
        self.assertEqual(status["animation"]["status"], "PASS")
        self.assertEqual(status["texture"]["status"], "PASS")
        self.assertTrue(status["all_pass"])

    def test_saved_recipe_generates_multiple_clips(self):
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        proj = Path(self.folder.name) / "proj"
        init_project(proj, asset_id="anim", animation=True)
        self.model = resolve_asset(f"{proj}#anim").model
        script = resolve_asset(f"{proj}#anim").scripts / "generate_animation.py"
        script.write_text(
            "from Tools.recipe_context import recipe_paths\n"
            "from lib.animation import AnimationEditor\n"
            "editor = AnimationEditor.from_bbmodel(recipe_paths(__file__).model)\n"
            "editor.animation('open', duration=1).group('jaw').key(0, rotation=(0, 0, 0)).key(1, rotation=(25, 0, 0))\n"
            "editor.animation('nod', duration=2, loop=True).bone('upper', armature='rig').sample('rotation', 0, 2, 2, lambda t: (0, 0, t))\n"
            "editor.save()\n", encoding="utf-8")
        builder = ModelBuilder("animated")
        builder.add_group("root")
        builder.add_transform_group("jaw", "root", pivot=(0, 2, 0))
        builder.add_cube("jaw_mesh", "jaw", from_=(-1, 1, -1), to_=(1, 3, 1))
        rig = builder.add_armature("rig", parent="root")
        rig.add_bone("upper", between=((0, 0, 0), (0, 2, 0)))
        builder.export_bbmodel(self.model)
        report = export_animations(proj)
        self.assertEqual(report["status"], "pass", report)
        self.assertEqual(report["animations"], 2)
        builder = ModelBuilder("animated")
        builder.add_group("root")
        builder.add_transform_group("jaw", "root", pivot=(0, 2, 0))
        builder.add_cube("jaw_mesh", "jaw", from_=(-1, 1, -1), to_=(1, 3, 1))
        builder.export_bbmodel(self.model)
        self.assertEqual(json.loads(self.model.read_text())["animations"], [])
        editor = AnimationEditor.from_bbmodel(self.model)
        editor.animation("jaw_open", duration=1).group("jaw").key(0, rotation=(0, 0, 0))
        editor.save()
        self.assertEqual(len(json.loads(self.model.read_text())["animations"]), 1)
