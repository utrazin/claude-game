import tempfile
import unittest
from pathlib import Path

from lib import AnimationEditor, ModelBuilder, Profile, SegmentSection


def build():
    builder = ModelBuilder("stable", require_integer_dimensions=False)
    rig = builder.add_armature("rig")
    builder.add_segment("pelvis", "rig", start=(0, 0, 0), end=(0, 4, 0), y_hint=(0, 0, 1),
                        sections=[SegmentSection(n, t, Profile.oval(2, 1.3, 1.7, segments=8))
                                  for n, t in (("low", 0), ("high", 1))])
    rig.add_bone("hips", between=("pelvis:low", "pelvis:high"))
    rig.bind("pelvis", bone="hips")
    builder.add_group("props")
    builder.add_box("crate_L", "props", size=(2, 2, 2), at=(3, 1, 0), anchor="base")
    builder.mirror("crate_L")
    return builder


class DeterministicExportTests(unittest.TestCase):
    def test_the_same_recipe_writes_the_same_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = build().export_bbmodel(Path(tmp) / "a.bbmodel").read_bytes()
            second = build().export_bbmodel(Path(tmp) / "b.bbmodel").read_bytes()
        self.assertEqual(first, second)

    def test_animations_are_stable_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = build().export_bbmodel(Path(tmp) / "m.bbmodel")
            outputs = []
            for _ in range(2):
                editor = AnimationEditor.from_bbmodel(model)
                clip = editor.animation("wave", duration=1, loop=True)
                clip.bone("hips", armature="rig").key(0, rotation=(0, 0, 0)).key(0.5, rotation=(0, 20, 0))
                editor.save()
                outputs.append(model.read_bytes())
        self.assertEqual(outputs[0], outputs[1])

    def test_ids_are_unique_within_one_file(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            data = json.loads(build().export_bbmodel(Path(tmp) / "u.bbmodel").read_text(encoding="utf-8"))
        ids = [e["uuid"] for e in data["elements"]]
        self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
