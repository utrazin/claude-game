import contextlib
import io
import json
import math
import subprocess
import tempfile
import unittest
import warnings
from pathlib import Path

from lib import AnimationEditor, IKReport
from lib.kinematics import Rig, cross, dot, mv, norm, pose_from_tracks, reject, sub, unit
from lib.model_builder import ModelBuilder
from Tools.animation_export import print_inspection, rig_report

VIEWER_CHECK = Path(__file__).with_name("kinematics_viewer_check.js")


def build_fixture(path: Path) -> None:
    """Transform groups (rotated rest, nested pivots) beside an armature with a leg and a tail."""
    builder = ModelBuilder("ik_fixture", check_coplanar=False)
    builder.add_group("root")
    builder.add_transform_group("body", "root", pivot=(0, 8, 0), rotation=(5, 10, 0))
    builder.add_cube("body_mesh", "body", from_=(-1, 7, -1), to_=(1, 9, 1))
    builder.add_transform_group("head", "body", pivot=(0, 10, 0))
    builder.add_cube("head_mesh", "head", from_=(-1, 10, -1), to_=(1, 12, 1))
    builder.add_transform_group("upper", "body", pivot=(2, 8, 0), rotation=(0, 0, -20))
    builder.add_cube("upper_mesh", "upper", from_=(2, 5, -1), to_=(3, 8, 0))
    builder.add_transform_group("lower", "upper", pivot=(2, 5, 1))
    builder.add_cube("lower_mesh", "lower", from_=(2, 2, 0), to_=(3, 5, 1))
    builder.add_transform_group("hand", "lower", pivot=(2, 2, 0))
    builder.add_cube("hand_mesh", "hand", from_=(2, 1, 0), to_=(3, 2, 1))
    rig = builder.add_armature("rig", parent="root")
    rig.add_bone("hips", between=((0, 6, 0), (0, 7, 0)))
    rig.add_bone("thigh", between=((-2, 6, 0), (-2, 3, 0.5)), parent="hips", connected=False)
    rig.add_bone("shin", between=((-2, 3, 0.5), (-2, 0, 0)), parent="thigh")
    rig.add_bone("toe", between=((-2, 0, 0), (-2, 0, -1.5)), parent="shin")
    previous = None
    for index in range(4):
        start = (0, 6, 2 + 1.5 * index)
        end = (0, 6 + 0.4 * (index + 1), 2 + 1.5 * (index + 1))
        start = previous or start
        rig.add_bone(f"tail_{index + 1}", between=(start, end), parent=f"tail_{index}" if index else "hips",
                     connected=bool(index))
        previous = end
    builder.export_bbmodel(path)


def saved_frames(path: Path, clip: str, time: float):
    data = json.loads(path.read_text(encoding="utf-8"))
    rig = Rig.from_document(data)
    animation = next(item for item in data["animations"] if item["name"] == clip)
    tracks = {uid: animator["keyframes"] for uid, animator in animation["animators"].items()}
    return rig, rig.fk(pose_from_tracks(tracks, time))


def uid_of(path: Path, name: str) -> str:
    editor = AnimationEditor.from_bbmodel(path)
    return editor._resolve_any(name).uuid


class IKTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.model = Path(self.folder.name) / "model.bbmodel"
        build_fixture(self.model)

    def editor(self):
        return AnimationEditor.from_bbmodel(self.model)

    def tip(self, clip, chain_end, time, *, point="tip"):
        rig, frames = saved_frames(self.model, clip, time)
        uid = uid_of(self.model, chain_end)
        return rig.tip(uid, frames) if point == "tip" else frames[uid].origin

    # ------------------------------------------------------------------ conventions
    @unittest.skipUnless(__import__("shutil").which("node"), "node missing: see `py -3.12 -m Tools.forge doctor`")
    def test_forward_kinematics_matches_the_viewer(self):
        editor = self.editor()
        clip = editor.animation("pose", duration=1)
        clip.group("body").key(0, rotation=(0, 0, 0), position=(0, 0, 0)).key(1, rotation=(20, -35, 15),
                                                                             position=(1, 2, -1))
        clip.group("upper").key(0, rotation=(0, 0, 0)).key(1, rotation=(-40, 10, 30))
        clip.group("lower").key(0.5, rotation=(25, 0, 0), interpolation="catmullrom")
        clip.bone("hips").key(0, position=(0, 0, 0)).key(1, position=(0.5, -1, 0), rotation=(0, 30, 0))
        clip.bone("thigh").key(0, rotation=(0, 0, 0)).key(1, rotation=(-50, 20, 10))
        clip.bone("shin").key(1, rotation=(70, 0, -15))
        clip.bone("tail_2").key(1, rotation=(10, 45, 80))
        editor.save()
        result = subprocess.run(["node", str(VIEWER_CHECK), str(self.model), "pose", "0,0.5,1"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        viewer = json.loads(result.stdout)
        for time in ("0", "0.5", "1"):
            _, frames = saved_frames(self.model, "pose", float(time))
            self.assertEqual(set(viewer[time]), {c.uuid for c in self.editor().controls()})
            for uid, elements in viewer[time].items():
                frame = frames[uid]
                for row in range(3):
                    self.assertAlmostEqual(frame.origin[row], elements[12 + row], places=4, msg=(time, uid))
                    for column in range(3):
                        self.assertAlmostEqual(frame.linear[row][column], elements[column * 4 + row], places=4)

    def test_rest_bone_tips_are_the_modelled_endpoints(self):
        editor = self.editor()
        for name, end in (("thigh", (-2, 3, 0.5)), ("shin", (-2, 0, 0)), ("toe", (-2, 0, -1.5))):
            for got, want in zip(editor.rest_point(name, "tip"), end):
                self.assertAlmostEqual(got, want, places=5)
        self.assertEqual(tuple(round(v, 5) for v in editor.rest_point("body")), (0, 8, 0))
        self.assertNotEqual(tuple(round(v, 5) for v in editor.rest_point("upper")), (2, 8, 0))  # carried by body

    # ------------------------------------------------------------------ reach
    @unittest.skipUnless(__import__("shutil").which("node"), "node missing: see `py -3.12 -m Tools.forge doctor`")
    def test_two_bone_reach_lands_on_the_target_in_viewer_and_python(self):
        editor = self.editor()
        clip = editor.animation("step", duration=1, loop=True)
        rest = editor.rest_point("shin", "tip")
        target = lambda t: (rest[0], rest[1] + 1.5 * math.sin(math.pi * t), rest[2] + 2 * math.sin(2 * math.pi * t))
        report = clip.chain("thigh", "shin").reach(0, 1, 12, target=target)
        self.assertIsInstance(report, IKReport)
        self.assertTrue(report.ok, report)
        self.assertEqual(report.chain, ("thigh", "shin"))
        editor.save()
        result = subprocess.run(["node", str(VIEWER_CHECK), str(self.model), "step", "0.25,0.5"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        viewer = json.loads(result.stdout)
        shin = uid_of(self.model, "shin")
        length = Rig.from_document(json.loads(self.model.read_text(encoding="utf-8"))).nodes[shin].length
        for time in (0.25, 0.5):
            e = viewer[str(time)][shin]
            tip = tuple(e[4 + row] * length + e[12 + row] for row in range(3))   # bone tip = (0, length, 0)
            self.assertLess(norm(sub(tip, target(time))), 1e-3)
            self.assertLess(norm(sub(self.tip("step", "shin", time), target(time))), 1e-3)

    def test_pole_chooses_the_side_the_knee_bends_to(self):
        sides = {}
        for name, pole in (("front", (-2, 3, -20)), ("back", (-2, 3, 20))):
            editor = self.editor()
            clip = editor.animation(name, duration=1)
            clip.chain("thigh", "shin").reach(0, 1, 2, target=(-2, 2, 0), pole=pole)
            editor.save()
            sides[name] = self.tip(name, "shin", 0.5, point="joint")[2]
        self.assertLess(sides["front"], -0.5)
        self.assertGreater(sides["back"], 0.5)

    def test_two_bone_knee_folds_about_one_local_axis(self):
        clip = self.editor().animation("fold", duration=1)
        clip.chain("thigh", "shin").reach(0, 1, 6, target=lambda t: (-2, 1.5 + 2 * t, -1 + 2 * t))
        shin = clip.editor._resolve_any("shin").uuid
        values = [[kf["data_points"][0][a] for a in "xyz"] for kf in clip._tracks[shin]]
        dominant = max(range(3), key=lambda axis: max(abs(v[axis]) for v in values))
        for value in values:
            for axis in range(3):
                if axis != dominant:
                    self.assertAlmostEqual(value[axis], 0.0, places=3)

    def test_limb_twist_stays_continuous_through_full_extension(self):
        editor = self.editor()
        clip = editor.animation("stretch", duration=1)
        hip = editor.rest_point("thigh")
        reach = sum(editor.rig.nodes[editor._resolve_any(n).uuid].length for n in ("thigh", "shin"))
        down = unit(sub(editor.rest_point("shin", "tip"), hip))
        # the target travels from a bent knee past full extension (the leg locks straight) and back
        target = lambda t: tuple(h + d * reach * (0.88 + 0.16 * math.sin(math.pi * t)) for h, d in zip(hip, down))
        thigh = editor._resolve_any("thigh").uuid
        rest_side = mv(editor.rig.rest[thigh].linear, (1, 0, 0))

        def twist(frames):
            """Thigh roll about its own axis relative to rest, in degrees."""
            axis = unit(mv(frames[thigh].linear, (0, 1, 0)))
            now, ref = reject(mv(frames[thigh].linear, (1, 0, 0)), axis), reject(rest_side, axis)
            return math.degrees(math.atan2(dot(axis, cross(ref, now)), dot(ref, now)))

        # a pole off the rest bend plane makes the thigh roll; that roll must not pop when the leg straightens
        for pole in (None, (4, 3, -20)):
            clip = editor.animation(f"stretch_{pole is None}", duration=1)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")          # the stretched samples are out of reach on purpose
                clip.chain("thigh", "shin").reach(0, 1, 40, target=target, pole=pole)
            times = sorted(kf["time"] for kf in clip._tracks[thigh])
            rolls = [twist(editor.rig.fk(pose_from_tracks(clip._tracks, t))) for t in times]
            self.assertLess(max(abs(a - b) for a, b in zip(rolls, rolls[1:])), 1.0, (pole, rolls))

    def test_euler_extraction_is_continuous_through_gimbal_lock(self):
        from lib.kinematics import continuous_euler, rot_zyx
        for previous in ((12.0, 89.0, 3.0), (-30.0, -89.5, 10.0)):
            locked = (previous[0] + 1, 90.0 if previous[1] > 0 else -90.0, previous[2] - 1)
            got = continuous_euler(rot_zyx(locked), previous)
            self.assertLess(max(abs(a - b) for a, b in zip(got, previous)), 5)
            matrix, again = rot_zyx(locked), rot_zyx(got)
            for row in range(3):
                for column in range(3):
                    self.assertAlmostEqual(matrix[row][column], again[row][column], places=6)

    def test_bend_toward_is_a_direction_for_the_middle_joint(self):
        sides = {}
        for name, direction in (("front", (0, 0, -1)), ("back", (0, 0, 1))):
            editor = self.editor()
            editor.animation(name, duration=1).chain("thigh", "shin").reach(
                0, 1, 2, target=(-2, 2, 0), bend_toward=direction)
            editor.save()
            sides[name] = self.tip(name, "shin", 0.5, point="joint")[2]
        self.assertLess(sides["front"], -0.5)
        self.assertGreater(sides["back"], 0.5)
        clip = self.editor().animation("both", duration=1)
        with self.assertRaisesRegex(ValueError, "not both"):
            clip.chain("thigh", "shin").reach(0, 1, 2, target=(-2, 2, 0), pole=(0, 0, 9), bend_toward=(0, 0, 1))

    def test_inspect_chain_reports_bends_directions_and_problems(self):
        editor = self.editor()
        clip = editor.animation("check", duration=1)
        clip.chain("thigh", "shin").reach(0, 1, 10, target=(-2, 2, 0), bend_toward=(0, 0, -1))
        clip.bone("tail_1").key(0, rotation=(0, 0, 0), interpolation="constant").key(0.5, rotation=(0, 0, 90))
        editor.save()
        editor = self.editor()
        leg = editor.inspect_chain("check", "thigh", "shin", rate=20)
        self.assertEqual(leg["chain"], ["thigh", "shin"])
        self.assertEqual(len(leg["frames"]), 21)
        knee = leg["frames"][10]
        self.assertGreater(knee["bends"]["shin"], 30)
        self.assertLess(knee["bend_directions"]["shin"][2], -0.9)        # the knee points -Z, as asked
        self.assertEqual(knee["tip_velocity"], [0.0, 0.0, 0.0])
        self.assertEqual(leg["warnings"], [])
        tail = editor.inspect_chain("check", "tail_1", "tail_2", rate=20)
        self.assertTrue(any("tail_1 pops at" in note for note in tail["warnings"]), tail["warnings"])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            stretched = self.editor()
            hip = stretched.rest_point("thigh")
            down = unit(sub(stretched.rest_point("shin", "tip"), hip))
            length = sum(stretched.rig.nodes[stretched._resolve_any(n).uuid].length for n in ("thigh", "shin"))
            clip = stretched.animation("straight", duration=1)
            clip.chain("thigh", "shin").reach(0, 1, 60, target=(-2, -30, 0))          # held straight: fine
            clip = stretched.animation("snap", duration=1)
            clip.chain("thigh", "shin").reach(0, 1, 60, target=lambda t: tuple(
                h + d * length * (0.9 + 0.15 * t) for h, d in zip(hip, down)))        # driven through full reach
            stretched.save()
        held = self.editor().inspect_chain("straight", "thigh", "shin")
        self.assertFalse(any("snaps" in note for note in held["warnings"]), held["warnings"])
        report = self.editor().inspect_chain("snap", "thigh", "shin")
        self.assertTrue(any("snaps near full reach" in note for note in report["warnings"]), report["warnings"])
        with self.assertRaisesRegex(KeyError, "Unknown animation"):
            self.editor().inspect_chain("missing", "thigh")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            print_inspection(report)
        self.assertIn("thigh -> shin", printed.getvalue())
        self.assertIn("[inspect] WARN", printed.getvalue())

    def test_inspect_flags_cuts_and_tip_jolts_but_not_smooth_motion(self):
        editor = self.editor()
        stop = editor.animation("stop", duration=1)
        stop.bone("tail_1").key(0, rotation=(0, 0, 0)).key(0.25, rotation=(90, 0, 0)).key(1, rotation=(90, 0, 0))
        smooth = editor.animation("smooth", duration=1, loop=True)
        smooth.bone("tail_1").sample("rotation", 0, 1, 60, lambda t: (40 * math.sin(2 * math.pi * t), 0, 0))
        editor.save()
        editor = self.editor()
        abrupt = editor.inspect_chain("stop", "tail_1", "tail_2")
        self.assertTrue(any("tail_1 cuts at" in note for note in abrupt["warnings"]), abrupt["warnings"])
        self.assertTrue(any("tail_2 tip jolts at" in note for note in abrupt["warnings"]), abrupt["warnings"])
        self.assertFalse(any("pops" in note for note in abrupt["warnings"]))        # fast, but not a flip
        calm = editor.inspect_chain("smooth", "tail_1", "tail_2")
        self.assertEqual(calm["warnings"], [])
        self.assertGreater(calm["joint_speed"]["tail_1"]["max_degrees_per_second"], 200)

    def test_inspect_ignores_a_parent_scale_when_measuring_rotation(self):
        # A breathing parent (non-uniform scale) used to turn a slow sway into spurious spins of
        # hundreds of °/s, flagged as pops and cuts.
        editor = self.editor()
        clip = editor.animation("breathe", duration=3, loop=True)
        wave = lambda t: math.sin(2 * math.pi * t / 3)
        clip.bone("hips").sample("scale", 0, 3, 30, lambda t: (1 + .012 * wave(t), 1 + .008 * wave(t), 1 + .018 * wave(t)))
        clip.bone("tail_1").sample("rotation", 0, 3, 30, lambda t: (.8 * wave(t), 0, .8 * wave(t)))
        editor.save()
        report = self.editor().inspect_chain("breathe", "tail_1", "tail_2")
        self.assertEqual(report["warnings"], [])
        expected = .8 * math.sqrt(2) * 2 * math.pi / 3          # peak sway speed, °/s
        self.assertLess(report["joint_speed"]["tail_1"]["max_degrees_per_second"], 2 * expected)

    def test_unreachable_target_warns_and_reports(self):
        clip = self.editor().animation("far", duration=1)
        with self.assertWarnsRegex(UserWarning, "out of reach"):
            report = clip.chain("thigh", "shin").reach(0, 1, 4, target=(-2, -20, 0))
        self.assertFalse(report.ok)
        self.assertEqual(report.unreachable, ((0.0, 1.0),))

    def test_long_chain_reaches_with_fabrik(self):
        editor = self.editor()
        clip = editor.animation("tail", duration=1, loop=True)
        base = editor.rest_point("tail_4", "tip")
        target = lambda t: (2.5 * math.sin(2 * math.pi * t), base[1] + 1, base[2] - 1.5)
        report = clip.chain("tail_1", "tail_4").reach(0, 1, 8, target=target)
        self.assertTrue(report.ok, report)
        editor.save()
        self.assertLess(norm(sub(self.tip("tail", "tail_4", 0.25), target(0.25))), 0.01)

    def test_group_chain_uses_the_end_pivot_as_tip(self):
        editor = self.editor()
        clip = editor.animation("arm", duration=1)
        goal = (4.0, 3.5, -1.0)
        report = clip.chain("upper", "hand").reach(0, 1, 2, target=goal)
        self.assertTrue(report.ok, report)
        editor.save()
        self.assertLess(norm(sub(self.tip("arm", "hand", 1, point="joint"), goal)), 0.01)
        animation = json.loads(self.model.read_text(encoding="utf-8"))["animations"][0]
        self.assertNotIn(uid_of(self.model, "hand"), animation["animators"])

    def test_limits_clamp_and_are_reported(self):
        clip = self.editor().animation("stiff", duration=1)
        with self.assertWarns(UserWarning):
            report = clip.chain("thigh", "shin", limits={"shin": {"x": (0, 0), "y": (0, 0), "z": (0, 0)}}).reach(
                0, 1, 2, target=(-2, 2, -1.5))
        self.assertEqual(report.limited, ("shin",))
        shin = clip.editor._resolve_any("shin").uuid
        for kf in clip._tracks[shin]:
            self.assertEqual(tuple(kf["data_points"][0][a] for a in "xyz"), (0, 0, 0))

    def test_pin_keeps_the_tip_planted_while_the_parent_moves(self):
        editor = self.editor()
        clip = editor.animation("crouch", duration=1)
        clip.bone("hips").sample("position", 0, 1, 10, lambda t: (0.3 * t, -1.2 * math.sin(math.pi * t), 0))
        leg = clip.chain("thigh", "shin")
        planted = leg.pin(at=0)
        report = leg.reach(0, 1, 10, target=planted)
        self.assertTrue(report.ok, report)
        editor.save()
        for time in (0.3, 0.5, 0.8):
            self.assertLess(norm(sub(self.tip("crouch", "shin", time), planted)), 1e-3)

    def test_target_can_follow_another_control(self):
        editor = self.editor()
        clip = editor.animation("follow", duration=1)
        clip.bone("hips").key(0, position=(0, 0, 0)).key(1, position=(0, 0, 3))
        report = clip.chain("tail_1", "tail_4").reach(
            0, 1, 6, target=lambda t: clip.world_point("hips", t, point=(0, 7, 7)))
        self.assertTrue(report.ok, report)

    # ------------------------------------------------------------------ aim
    def test_aim_points_the_axis_and_stays_continuous(self):
        editor = self.editor()
        clip = editor.animation("look", duration=1, loop=True)
        target = lambda t: (12 * math.sin(2 * math.pi * t), 11, -12 * math.cos(2 * math.pi * t))
        report = clip.chain("head").aim(0, 1, 24, target=target, axis="-z")
        self.assertTrue(report.ok, report)
        self.assertEqual(report.unit, "degrees")
        editor.save()
        rig, frames = saved_frames(self.model, "look", 0.25)
        head = uid_of(self.model, "head")
        facing = unit(mv(frames[head].linear, (0, 0, -1)))
        wanted = unit(sub(target(0.25), frames[head].origin))
        self.assertGreater(sum(a * b for a, b in zip(facing, wanted)), 0.9999)
        keys = json.loads(self.model.read_text(encoding="utf-8"))["animations"][0]["animators"][head]["keyframes"]
        values = [[kf["data_points"][0][a] for a in "xyz"] for kf in sorted(keys, key=lambda kf: kf["time"])]
        for before, after in zip(values, values[1:]):
            self.assertLess(max(abs(a - b) for a, b in zip(before, after)), 90)

    # ------------------------------------------------------------------ integration rules
    def test_animating_a_parent_after_the_chain_fails_on_save(self):
        editor = self.editor()
        clip = editor.animation("late", duration=1)
        clip.chain("thigh", "shin").reach(0, 1, 2, target=(-2, 2, -1))
        clip.bone("hips").key(0.5, position=(0, -1, 0))
        with self.assertRaisesRegex(ValueError, "solved before"):
            editor.save()

    def test_existing_rotation_keys_inside_the_interval_are_refused(self):
        clip = self.editor().animation("mixed", duration=1)
        clip.bone("thigh").key(0.5, rotation=(10, 0, 0))
        with self.assertRaisesRegex(ValueError, "IK owns the rotation"):
            clip.chain("thigh", "shin").reach(0, 1, 2, target=(-2, 2, -1))

    def test_contiguous_intervals_share_their_boundary(self):
        editor = self.editor()
        clip = editor.animation("phases", duration=1)
        leg = clip.chain("thigh", "shin")
        leg.reach(0, 0.5, 4, target=(-2, 2, -1))
        leg.reach(0.5, 1, 4, target=lambda t: (-2, 2 + t, -1))
        editor.save()
        self.assertLess(norm(sub(self.tip("phases", "shin", 0.5), (-2, 2.5, -1))), 1e-3)

    def test_reach_and_aim_end_exactly_on_the_interval(self):
        # Same rounding as sample(): 0.8 s at 120 fps used to bake a key at 0.8000000000000002.
        editor = self.editor()
        clip = editor.animation("edge", duration=0.8)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            clip.chain("thigh", "shin").reach(0, 0.8, 120, target=(-2, 2, -1))
            clip.chain("head").aim(0.2, 0.8, 24, target=(0, 14, -30), axis="-z")
        for name, first in (("shin", 0.0), ("head", 0.2)):
            times = sorted(kf["time"] for kf in clip._tracks[uid_of(self.model, name)])
            self.assertEqual((times[0], times[-1]), (first, 0.8))

    def test_end_must_be_below_start(self):
        clip = self.editor().animation("bad", duration=1)
        with self.assertRaisesRegex(ValueError, "is not below"):
            clip.chain("shin", "thigh")
        with self.assertRaisesRegex(ValueError, "no segment"):
            clip.chain("head").reach(0, 1, 2, target=(0, 0, 0))

    def test_rig_report_lists_pivots_and_tips(self):
        rows = {row["path"]: row for row in rig_report(self.editor())}
        thigh = next(row for path, row in rows.items() if path.endswith("thigh"))
        self.assertEqual(thigh["kind"], "bone")
        self.assertEqual([round(v, 3) for v in thigh["tip"]], [-2, 3, 0.5])
        self.assertTrue(any(path.endswith("shin") for path in thigh["children"]))
        upper = next(row for path, row in rows.items() if path.endswith("upper"))   # rest rotation (5,10,0)·(0,0,-20)
        rig = self.editor().rig
        linear = rig.rest[uid_of(self.model, "upper")].linear
        for column, name in enumerate("xyz"):
            self.assertEqual(upper["axes"][name], [round(linear[i][column], 4) + 0.0 for i in range(3)])
            # the listed direction is where aim() sends that local axis
            self.assertLess(norm(sub(upper["axes"][name], mv(linear, tuple(float(column == k) for k in range(3))))), 1e-3)
        self.assertNotEqual(upper["axes"]["x"], [1.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
