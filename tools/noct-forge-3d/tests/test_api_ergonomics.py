"""Regression tests for the model-authoring ergonomics pass.

Covers: profile/frame axis control, distance-based and path-based sections,
pivot handling, MeshDraft orientation/extrusion/mirroring, ring edits in the
ring's own plane, hard binding on section anchors, unified mirroring, and the
diagnostics that name the offending object and the fix.
"""
from __future__ import annotations

import json
import math
import tempfile
import unittest
from pathlib import Path

from lib import (Frame, MeshDraft, ModelBuilder, Path3D, PathSection, Profile, SegmentSection,
                 SpatialFrame)


def _close(a, b, tol=1e-6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def _leg_sections():
    knee = Profile.oval(0.9, 1.1, 0.8, segments=8)          # asymmetric knee on purpose
    return (
        PathSection("hip_cap", Profile.circle(1.0), at=-0.5),
        PathSection("thigh", Profile.circle(1.2), at=2.0),
        PathSection("knee", knee, point=1),
        PathSection("calf", Profile.circle(1.0), at=7.0),
        PathSection("ankle", Profile.circle(0.6), point=2),
    )


LEG_PATH = Path3D.polyline([(2, 16, 0), (2.5, 10, 0.2), (3, 2, 0)])


class FrameAndProfileTests(unittest.TestCase):
    def test_from_normal_y_hint_sets_profile_up_direction(self):
        frame = Frame.from_normal((0, 0, 0), normal=(0, 1, 0), y_hint=(0, 0, 1))
        self.assertTrue(_close(frame.y, (0, 0, 1)))
        self.assertTrue(_close(frame.z, (0, 1, 0)))
        default = Frame.from_normal((0, 0, 0), normal=(0, 1, 0))
        self.assertTrue(_close(default.y, (0, 0, -1)))       # documented default mapping
        with self.assertRaisesRegex(ValueError, "parallel to normal"):
            Frame.from_normal(normal=(1, 0, 0), x_hint=(2, 0, 0))
        with self.assertRaisesRegex(ValueError, "not both"):
            Frame.from_normal(x_hint=(1, 0, 0), y_hint=(0, 1, 0))

    def test_oval_phase_and_nudge(self):
        oval = Profile.oval(2, 1.5, 0.5, segments=4)
        ys = sorted(round(p[1], 6) for p in oval.points)
        self.assertEqual(ys[0], -0.5)
        self.assertEqual(ys[-1], 1.5)
        face_first = Profile.oval(1, 1, 1, segments=8, phase=22.5)
        self.assertAlmostEqual(face_first.points[0][1], math.sin(math.radians(22.5)))
        nudged = oval.nudge({1: (0, 0.25)})
        self.assertAlmostEqual(nudged.points[1][1], oval.points[1][1] + 0.25)
        with self.assertRaises(IndexError):
            oval.nudge({9: (0, 1)})

    def test_spatial_frame_mirror_keeps_up(self):
        frame = SpatialFrame((2, 1, 0), (1, 0, 0), (0, 0, 1)).mirrored("X")
        self.assertTrue(_close(frame.origin, (-2, 1, 0)))
        self.assertTrue(_close(frame.forward, (-1, 0, 0)))
        self.assertTrue(_close(frame.up, (0, 0, 1)))


class SectionTests(unittest.TestCase):
    def test_segment_sections_by_distance_and_y_hint(self):
        builder = ModelBuilder("seg", require_integer_dimensions=False)
        builder.add_group("root")
        chest = Profile.oval(2, 1.5, 1.0, segments=8)          # +y = front with y_hint
        builder.add_segment("torso", "root", start=(0, 10, 0), end=(0, 16, 0), y_hint=(0, 0, 1),
                            sections=(SegmentSection("waist", profile=Profile.circle(1), distance=0),
                                      SegmentSection("chest", profile=chest, distance=4),
                                      SegmentSection("top", profile=Profile.circle(1), distance=6)))
        self.assertTrue(_close(builder.get_anchor("torso", "chest"), (0, 14, 0)))
        element = builder._elements[-1]
        ring = [builder._element_vertex_world(element, k) for k in element.mesh_rings["chest"]]
        self.assertAlmostEqual(max(p[2] for p in ring), 1.5)      # front bulge on +Z
        self.assertAlmostEqual(min(p[2] for p in ring), -1.0)
        with self.assertRaisesRegex(ValueError, "outside the segment length"):
            builder.add_segment("bad", "root", start=(5, 0, 0), end=(5, 2, 0), sections=(
                SegmentSection("a", profile=Profile.circle(1), distance=0),
                SegmentSection("b", profile=Profile.circle(1), distance=3)))

    def test_segment_section_float_rounding_tolerance(self):
        builder = ModelBuilder("seg_float", require_integer_dimensions=False)
        builder.add_group("root")
        dist = 6.0 * (1.0 - 1e-7)
        builder.add_segment("arm", "root", start=(0, 0, 0), end=(0, 6, 0),
                            sections=(SegmentSection("base", profile=Profile.circle(1), distance=0),
                                      SegmentSection("top", profile=Profile.circle(1), distance=dist)))
        self.assertEqual(len(builder._elements), 1)

    def test_path_sections_put_named_rings_on_joints(self):
        builder = ModelBuilder("leg", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_sweep("leg", "root", path=LEG_PATH, sections=_leg_sections(), y_hint=(0, 0, 1))
        self.assertTrue(_close(builder.get_anchor("leg", "knee"), (2.5, 10, 0.2)))
        self.assertTrue(_close(builder.get_anchor("leg", "ankle"), (3, 2, 0)))
        top = builder.get_anchor("leg", "hip_cap")
        self.assertGreater(top[1], 16)                          # extends past the first point
        self.assertTrue(_close(builder._elements[-1].origin, top))  # default pivot = base
        with self.assertRaisesRegex(ValueError, "exactly one of profile= or sections="):
            builder.add_sweep("x", "root", path=LEG_PATH)
        with self.assertRaisesRegex(ValueError, "advance along the path"):
            builder.add_sweep("y", "root", path=LEG_PATH, sections=(
                PathSection("a", Profile.circle(1), at=5), PathSection("b", Profile.circle(1), at=1)))


class PivotTests(unittest.TestCase):
    def test_pivot_keyword_keeps_geometry_and_lists_anchors(self):
        builder = ModelBuilder("pivot", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_sweep("leg", "root", path=LEG_PATH, sections=_leg_sections(), pivot="knee")
        element = builder._elements[-1]
        self.assertTrue(_close(element.origin, (2.5, 10, 0.2)))
        self.assertTrue(_close(builder.get_anchor("leg", "ankle"), (3, 2, 0)))
        with self.assertRaisesRegex(KeyError, "available: .*knee"):
            builder.add_sweep("leg2", "root", path=LEG_PATH, sections=_leg_sections(), pivot="nope")

    def test_skinned_world_space_meshes_do_not_warn_about_pivots(self):
        builder = ModelBuilder("skinned", require_integer_dimensions=False)
        rig = builder.add_armature("rig")
        draft = MeshDraft(closed=True)
        a = draft.ring_from_profile("a", Profile.rectangle(1, 1), Frame((20, 20, 0), z=(0, 0, 1)))
        b = draft.ring_from_profile("b", Profile.rectangle(1, 1), Frame((20, 20, 2), z=(0, 0, 1)))
        draft.connect_rings(a, b).cap(a, name="c0").cap(b, name="c1")
        builder.add_mesh("block", "rig", draft)
        rig.add_bone("bone", between=((20, 20, 0), (20, 20, 2)))
        rig.bind("block", bone="bone")
        warnings = builder.validate()["warnings"]
        self.assertFalse([w for w in warnings if "pivot" in w])


class MeshDraftTests(unittest.TestCase):
    def _tube(self, *, closed=True):
        draft = MeshDraft(closed=closed)
        rings = [draft.ring_from_profile(f"r{i}", Profile.rectangle(2, 2), Frame((0, 0, z)))
                 for i, z in enumerate((0, 1, 2))]
        return draft, rings

    def test_closed_drafts_orient_outward_on_build(self):
        draft, rings = self._tube()
        draft.connect_rings(rings[1], rings[0], prefix="s0")      # deliberately "inward" order
        draft.connect_rings(rings[1], rings[2], prefix="s1")      # and a clashing order
        draft.cap(rings[0], name="c0").cap(rings[2], name="c2")
        draft.validate()                                           # no error: oriented on build
        with self.assertRaisesRegex(ValueError, "orient"):
            from lib.mesh_validation import validate_geometry
            errors, _ = validate_geometry(draft.build(orient=False), name="tube")
            raise ValueError("; ".join(errors))

    def test_extrude_branch_from_skipped_quad(self):
        draft, rings = self._tube()
        draft.connect_rings(rings[0], rings[1], prefix="s0", skip=(1,))
        draft.connect_rings(rings[1], rings[2], prefix="s1")
        draft.cap(rings[0], name="c0").cap(rings[2], name="c2")
        root = (rings[0][1], rings[0][2], rings[1][2], rings[1][1])
        tip = draft.extrude(root, "thumb0", offset=(1, 0, 0.2), scale=0.7)
        tip = draft.extrude(tip, "thumb1", offset=(0.8, 0, 0.1), scale=0.8)
        draft.cap(tip, name="thumb_cap")
        draft.validate()
        self.assertIn("thumb1", draft.rings)

    def test_mirror_keeps_faces_outward(self):
        draft, rings = self._tube()
        draft.connect_rings(rings[0], rings[1], prefix="s0").connect_rings(rings[1], rings[2], prefix="s1")
        draft.cap(rings[0], name="c0").cap(rings[2], name="c2")
        draft.orient_outward().translate_vertices(tuple(draft.vertices), (3, 0, 0))
        draft.mirror("X")
        self.assertLess(max(p[0] for p in draft.vertices.values()), 0)
        from lib.mesh_validation import validate_geometry
        errors, _ = validate_geometry(draft.build(orient=False), name="mirrored")
        self.assertEqual(errors, [])

    def test_ring_edit_uses_ring_plane_and_moves_anchor_with_ring(self):
        builder = ModelBuilder("ring", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_segment("body", "root", start=(0, 0, 0), end=(0, 6, 0), sections=(
            SegmentSection("base", 0, Profile.rectangle(2, 2)),
            SegmentSection("waist", 0.5, Profile.rectangle(2, 2)),
            SegmentSection("top", 1, Profile.rectangle(2, 2))))
        with builder.edit_mesh("body") as mesh:
            mesh.edit_ring("waist").scale((0.5, 0.5))
        element = builder._elements[-1]
        ring = [builder._element_vertex_world(element, k) for k in element.mesh_rings["waist"]]
        self.assertTrue(all(abs(p[1] - 3) < 1e-9 for p in ring))  # height untouched
        self.assertAlmostEqual(max(abs(p[2]) for p in ring), 0.5)  # depth scaled
        with builder.edit_mesh("body") as mesh:
            mesh.edit_ring("waist").translate((0, 0, 1))          # along the ring normal (+Y)
        self.assertTrue(_close(builder.get_anchor("body", "waist"), (0, 4, 0)))
        with builder.edit_mesh("body") as mesh:
            mesh.translate_vertices(mesh.rings["top"][:2], (0.1, 0, 0))   # partial edit
        self.assertTrue(_close(builder.get_anchor("body", "top"), (0, 6, 0)))


class RigTests(unittest.TestCase):
    def _leg_builder(self):
        builder = ModelBuilder("rig", require_integer_dimensions=False)
        rig = builder.add_armature("rig")
        builder.add_sweep("leg_L", "rig", path=LEG_PATH, sections=_leg_sections())
        rig.add_bone("hips", between=((0, 16, 0), (0, 19, 0)))
        rig.add_chain("leg_chain_L", joints=("leg_L:thigh", "leg_L:knee", "leg_L:ankle"),
                      names=("thigh_L", "shin_L"), parent="hips", connected=False)
        return builder, rig

    def test_hard_bind_on_asymmetric_section_anchor(self):
        builder, rig = self._leg_builder()
        report = rig.bind("leg_L", mode="hard", chain="leg_chain_L")
        self.assertEqual(set(report.bones), {"thigh_L", "shin_L"})
        self.assertEqual(builder.validate()["errors"], [])

    def test_hard_bind_needs_only_the_joint_ring(self):
        builder, rig = self._leg_builder()
        element = builder._elements[-1]
        element.mesh_rings = {"knee": element.mesh_rings["knee"]}
        rig.bind("leg_L", mode="hard", chain="leg_chain_L")
        with self.assertRaisesRegex(ValueError, "needs 1 named ring"):
            rig.bind("leg_L", mode="smooth", chain="leg_chain_L")

    def test_unmatched_joint_reports_nearest_ring(self):
        builder, rig = self._leg_builder()
        rig.add_chain("wrong", joints=("leg_L:thigh", (2.55, 9.8, 0.2), "leg_L:ankle"),
                      names=("t2", "s2"), parent="hips", connected=False)
        with self.assertRaisesRegex(ValueError, "nearest ring 'knee'.*leg_L:knee"):
            rig.bind("leg_L", mode="hard", chain="wrong")

    def test_connected_bone_off_parent_tip_fails_early(self):
        builder, rig = self._leg_builder()
        with self.assertRaisesRegex(ValueError, "connected=False"):
            rig.add_bone("toe", between=((5, 0, 0), (5, 0, 1)), parent="shin_L")

    def test_mirror_bone_subtree_registers_chain_and_element(self):
        builder, rig = self._leg_builder()
        rig.add_bone("foot_L", between=("leg_L:ankle", (3, 0, 3)), parent="shin_L")
        builder.mirror("thigh_L")
        builder.mirror("leg_L")
        self.assertIn("shin_R", builder._armature_bones)
        self.assertIn("foot_R", builder._armature_bones)
        self.assertEqual(builder._armature_chains["leg_chain_R"], ("thigh_R", "shin_R"))
        self.assertTrue(_close(builder.get_anchor("leg_R", "knee"), (-2.5, 10, 0.2)))
        rig.bind("leg_L", mode="hard", chain="leg_chain_L")
        rig.bind("leg_R", mode="hard", chain="leg_chain_R")
        self.assertEqual(builder.validate()["errors"], [])

    def test_mirror_requires_kind_for_shared_names(self):
        builder, rig = self._leg_builder()
        rig.add_bone("leg_L", between=((1, 16, 0), (1, 15, 0)), parent="hips", connected=False)
        with self.assertRaisesRegex(ValueError, "pass kind="):
            builder.mirror("leg_L")
        builder.mirror("leg_L", kind="element")
        self.assertIn("leg_R", builder._element_names)
        with self.assertRaisesRegex(ValueError, "pass new_name"):
            builder.mirror("hips")


class MiscTests(unittest.TestCase):
    def test_mesh_box_matches_native_box_bounds(self):
        builder = ModelBuilder("boxes", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_box("cube", "root", size=(2, 4, 2), at=(1, 0, 0), anchor="base")
        builder.add_box("mesh", "root", size=(2, 4, 2), at=(1, 0, 0), anchor="base", native=False)
        low, high = builder._element_bounds(builder._elements[-1])
        self.assertTrue(_close(low, (0, 0, -1)) and _close(high, (2, 4, 1)))
        self.assertEqual(builder._elements[-1].kind, "mesh")
        with self.assertRaisesRegex(ValueError, "native=True"):
            builder.add_box("bad", "root", size=(1, 1, 1), rotation=(0, 45, 0), native=False)

    def test_validation_failure_lists_one_error_per_line(self):
        builder = ModelBuilder("broken", require_integer_dimensions=False)
        rig = builder.add_armature("rig")
        builder.add_box("m", "rig", size=(1, 1, 1), native=False)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, r"Model validation failed:\n  - .*not bound"):
                builder.export_bbmodel(Path(folder) / "m.bbmodel")

    def test_construction_errors_name_the_mesh(self):
        builder = ModelBuilder("named", require_integer_dimensions=False)
        builder.add_group("root")
        with self.assertRaisesRegex(ValueError, r"Mesh 'arm': Loft section 'b' has 4 points"):
            builder.add_segment("arm", "root", start=(0, 0, 0), end=(0, 2, 0), sections=(
                SegmentSection("a", 0, Profile.circle(1)),
                SegmentSection("b", 1, Profile.rectangle(1, 1))))


class ConsolidationErgonomicsTests(unittest.TestCase):
    def test_add_cube_exposes_standard_anchors_and_aliases(self):
        builder = ModelBuilder("cube_anchors", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_cube("box", "root", from_=(0, 0, 0), to_=(2, 4, 6))
        elem = builder._elements[-1]
        self.assertIn("center", elem.anchors)
        self.assertIn("top", elem.anchors)
        self.assertIn("base", elem.anchors)
        self.assertIn("left", elem.anchors)
        self.assertIn("right", elem.anchors)
        self.assertIn("+x", elem.anchors)
        self.assertIn("-x", elem.anchors)
        self.assertIn("anatomical_left", elem.anchors)
        self.assertIn("anatomical_right", elem.anchors)
        self.assertEqual(builder.get_anchor("box", "center"), (1.0, 2.0, 3.0))
        self.assertEqual(builder.get_anchor("box", "top"), (1.0, 4.0, 3.0))
        self.assertEqual(builder.get_anchor("box", "+x"), (2.0, 2.0, 3.0))
        self.assertEqual(builder.get_anchor("box", "-x"), (0.0, 2.0, 3.0))
        self.assertEqual(builder.get_anchor("box", "anatomical_left"), (2.0, 2.0, 3.0))
        self.assertEqual(builder.get_anchor("box", "anatomical_right"), (0.0, 2.0, 3.0))

    def test_add_axis_quad_exposes_center_anchor(self):
        builder = ModelBuilder("quad_center", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_axis_quad("banner", "root", from_=(0, 0, 0), size=(2, 4), normal="+Z")
        self.assertEqual(builder.get_anchor("banner", "center"), (1.0, 2.0, 0.0))

    def test_segment_section_polymorphic_argument_order(self):
        # 1. New intuitive order: (name, profile, t)
        s1 = SegmentSection("s1", Profile.circle(1), 0.5)
        self.assertEqual(s1.t, 0.5)
        self.assertEqual(len(s1.profile.points), 8)

        # 2. Legacy order: (name, t, profile)
        s2 = SegmentSection("s2", 0.5, Profile.circle(1))
        self.assertEqual(s2.t, 0.5)
        self.assertEqual(len(s2.profile.points), 8)

        # 3. Hybrid: (name, profile, t=0.5)
        s3 = SegmentSection("s3", Profile.circle(1), t=0.5)
        self.assertEqual(s3.t, 0.5)

        # 4. Hybrid with distance: (name, profile, distance=3.0)
        s4 = SegmentSection("s4", Profile.circle(1), distance=3.0)
        self.assertEqual(s4.distance, 3.0)

    def test_decal_canvas_direct_import(self):
        from Tools.TexturePainter import DecalCanvas
        canvas = DecalCanvas(32, 32)
        self.assertEqual(canvas.width, 32)
        self.assertEqual(canvas.height, 32)

    def test_combine_meshes_fluent_chaining(self):
        builder = ModelBuilder("combine_chain", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_cylinder("c1", "root", radius=1, height=2, segments=8)
        builder.add_cylinder("c2", "root", radius=1, height=2, segments=8)
        # Fluent chain: combine_meshes returns self so we can chain .add_group or .add_cylinder
        ret = builder.combine_meshes(("c1", "c2"), into="merged").add_group("child_folder")
        self.assertIs(ret, builder)
        self.assertIn("merged", builder._element_names)
        self.assertIn("child_folder", builder._groups)

    def test_asset_init_with_animation_flag(self):
        from Tools.asset_init import init_project
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp) / "hero"
            created = init_project(proj, animation=True)
            self.assertIn("generate_animation", created)
            self.assertTrue((proj / "scripts/hero/generate_animation.py").exists())
            content = (proj / "scripts/hero/generate_animation.py").read_text(encoding="utf-8")
            self.assertIn("AnimationEditor", content)

    def test_uv_packer_defaults_island_padding_to_one(self):
        from Tools.uv_packer import main as uv_main
        from Tools.asset_init import init_project
        from Tools._resolve import resolve_asset
        builder = ModelBuilder("test_pad", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_cube("body", "root", from_=(0, 0, 0), to_=(4, 4, 4))
        with tempfile.TemporaryDirectory() as tmp:
            init_project(Path(tmp) / "proj", asset_id="pad")
            model = resolve_asset(f"{Path(tmp) / 'proj'}#pad").model
            builder.export_bbmodel(model)
            uv_main([str(model)])
            options = json.loads(model.read_text(encoding="utf-8"))["unhandled_root_fields"]["model_as_code"]["uv_packing"]
            self.assertEqual(options["island_padding"], 1)

    def test_model_inspector_validate_flag(self):
        builder = ModelBuilder("test_insp", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_cube("body", "root", from_=(0, 0, 0), to_=(4, 4, 4))
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.bbmodel"
            builder.export_bbmodel(model)
            import sys
            orig_argv = sys.argv
            try:
                from Tools.model_inspector import main as inspector_main
                sys.argv = ["model_inspector.py", str(model), "--validate", "--summary"]
                inspector_main()
            finally:
                sys.argv = orig_argv

    def test_animation_editor_group_names_and_execution(self):
        from lib.animation import AnimationEditor
        builder = ModelBuilder("anim_test", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_transform_group("body", "root", pivot=(0, 0, 0))
        builder.add_cube("box", "body", from_=(0, 0, 0), to_=(2, 2, 2))
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / "model.bbmodel"
            builder.export_bbmodel(model)
            editor = AnimationEditor.from_bbmodel(model)
            self.assertIn("body", editor.group_names)
            self.assertIn("body", editor.control_names)
            self.assertEqual(len(editor.bone_names), 0)

            # Test execution of scaffolded pattern
            idle = editor.animation("idle", duration=2.0, loop=True)
            if "body" in editor.group_names:
                idle.group("body").key(0.0, position=(0, 0, 0)) \
                                  .key(1.0, position=(0, -0.2, 0), interpolation="catmullrom") \
                                  .key(2.0, position=(0, 0, 0), interpolation="catmullrom")
            editor.save()
            reloaded = json.loads(model.read_text(encoding="utf-8"))
            self.assertEqual(len(reloaded.get("animations", [])), 1)
            self.assertEqual(reloaded["animations"][0]["name"], "idle")

    def test_quad_sphere_lateral_and_cardinal_aliases(self):
        from lib.primitives import quad_sphere
        qs = quad_sphere(radius=4.0, subdivisions=2)
        # Cardinal aliases
        self.assertEqual(qs.anchors["-x"], (-4.0, 0.0, 0.0))
        self.assertEqual(qs.anchors["+x"], (4.0, 0.0, 0.0))
        self.assertEqual(qs.anchors["-y"], (0.0, -4.0, 0.0))
        self.assertEqual(qs.anchors["+y"], (0.0, 4.0, 0.0))
        # Lateral aliases matching box conventions
        self.assertEqual(qs.anchors["screen_left"], (-4.0, 0.0, 0.0))
        self.assertEqual(qs.anchors["screen_right"], (4.0, 0.0, 0.0))
        self.assertEqual(qs.anchors["anatomical_left"], (4.0, 0.0, 0.0))
        self.assertEqual(qs.anchors["anatomical_right"], (-4.0, 0.0, 0.0))
        self.assertIn("anatomical_left", qs.frames)
        self.assertIn("screen_left", qs.frames)
        self.assertIn("+x", qs.frames)


    def test_derived_mesh_anchors_and_frames_aliases(self):
        builder = ModelBuilder("test_wedge", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_wedge("ramp", "root", width=4.0, depth=6.0, height=2.0)
        # Test derived bounds anchors with aliases
        self.assertEqual(builder.get_anchor("ramp", "-x"), (-2.0, 0.0, 0.0))
        self.assertEqual(builder.get_anchor("ramp", "+x"), (2.0, 0.0, 0.0))
        self.assertEqual(builder.get_anchor("ramp", "screen_left"), (-2.0, 0.0, 0.0))
        self.assertEqual(builder.get_anchor("ramp", "screen_right"), (2.0, 0.0, 0.0))
        self.assertEqual(builder.get_anchor("ramp", "anatomical_left"), (2.0, 0.0, 0.0))
        self.assertEqual(builder.get_anchor("ramp", "anatomical_right"), (-2.0, 0.0, 0.0))
        # Test derived bounds frames with aliases
        frame_anat_l = builder.get_frame("ramp", "anatomical_left")
        self.assertEqual(frame_anat_l.origin, (2.0, 0.0, 0.0))
        self.assertEqual(frame_anat_l.forward, (1.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()

