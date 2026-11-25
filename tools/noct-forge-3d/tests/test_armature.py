import json
import tempfile
import unittest
from pathlib import Path

from lib import JointBlend, ModelBuilder, Profile, SegmentSection
from lib.primitives import quad_sphere
from Tools.uv_packer import BoxUVPacker
from Tools.TexturePainter import TexturePainter


def rigged_builder():
    builder = ModelBuilder("native rig", format_id="free", require_integer_dimensions=False)
    rig = builder.add_armature("character")
    geometry = quad_sphere(radius=3, subdivisions=1)
    builder.add_mesh("body", rig, geometry)
    mesh = builder.last
    rig.add_bone("lower", between=((0, -3, 0), (0, 0, 0)), connected=False)
    rig.add_bone("upper", parent="lower", between=((0, 0, 0), (0, 3, 0)))
    return builder, rig, mesh


def rigid_weights(builder, mesh, bone):
    element = next(item for item in builder._elements if item.name == mesh.name)
    return {key: {bone: 1.0} for key in element.vertices}


def jointed_builder(*, dense=False):
    builder = ModelBuilder("jointed", require_integer_dimensions=False)
    rig = builder.add_armature("character")
    rings = [("base",0), ("before",.4)]
    if dense: rings.append(("near_before",.45))
    rings.append(("joint",.5))
    if dense: rings.append(("near_after",.55))
    rings.extend((("after",.6), ("tip",1)))
    builder.add_segment("limb",rig,start=(0,0,0),end=(0,10,0),sections=tuple(
        SegmentSection(name,t,Profile.circle(1,segments=4)) for name,t in rings))
    limb = builder.last
    rig.add_chain("limb_chain",joints=("limb:base","limb:joint","limb:tip"),
                  names=("proximal","distal"),connected=False)
    return builder,rig,limb


class ArmatureTests(unittest.TestCase):
    def test_native_export_and_roundtrip_preserve_weights(self):
        builder, rig, mesh = rigged_builder()
        report = rig.bind(mesh, weights=rigid_weights(builder, mesh, "lower"))
        self.assertEqual(report.vertices, len(builder._elements[0].vertices))
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "rig.bbmodel"
            builder.export_bbmodel(target)
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual([item["type"] for item in data["elements"][:3]],
                             ["armature", "armature_bone", "armature_bone"])
            self.assertNotIn("origin", data["elements"][0])
            self.assertIsInstance(data["outliner"][0], dict)
            self.assertEqual(data["outliner"][0]["uuid"], data["elements"][0]["uuid"])
            self.assertEqual(data["outliner"][0]["children"][0]["uuid"],
                             data["elements"][1]["uuid"])
            loaded = ModelBuilder.from_bbmodel_data(data)
        self.assertEqual(set(loaded._armatures), {"character"})
        self.assertEqual(set(loaded._armature_bones), {"lower", "upper"})
        self.assertEqual(loaded._armature_bones["upper"].parent, "lower")
        self.assertEqual(loaded._bindings, builder._bindings)

    def test_rigid_inference_is_deterministic_normalized_and_bounded(self):
        first, first_rig, mesh = rigged_builder()
        first_rig.bind(mesh,bone="lower")
        second, second_rig, second_mesh = rigged_builder()
        second_rig.bind(second_mesh,bone="lower")
        self.assertEqual(first._bindings["body"], second._bindings["body"])
        for influences in first._bindings["body"].values():
            self.assertLessEqual(len(influences), 4)
            self.assertAlmostEqual(sum(influences.values()), 1)
            self.assertTrue(all(weight >= 0 for weight in influences.values()))

    def test_explicit_weights_override_the_automatic_default(self):
        builder, rig, mesh = rigged_builder()
        rig.bind(mesh,bone="lower")
        automatic = dict(builder._bindings["body"])
        explicit = rigid_weights(builder, mesh, "upper")
        rig.bind(mesh, weights=explicit)
        self.assertNotEqual(builder._bindings["body"], automatic)
        self.assertTrue(all(value == {"upper": 1.0}
                            for value in builder._bindings["body"].values()))

    def test_rigid_mode_assigns_every_vertex_to_exactly_one_bone(self):
        builder, rig, mesh = rigged_builder()
        report = rig.bind(mesh, bone="upper")
        self.assertEqual(report.maximum_influences, 1)
        self.assertTrue(all(value == {"upper": 1.0}
                            for value in builder._bindings["body"].values()))

    def test_hard_mode_assigns_one_bone_per_vertex(self):
        builder,rig,mesh=jointed_builder()
        report=rig.bind(mesh,mode="hard",chain="limb_chain")
        self.assertEqual(report.maximum_influences, 1)
        self.assertTrue(all(len(value) == 1 and next(iter(value.values())) == 1
                            for value in builder._bindings["limb"].values()))
        self.assertEqual(builder._binding_policies["limb"]["mode"], "hard")

    def test_binding_rejects_ambiguous_or_unknown_configuration(self):
        builder, rig, mesh = rigged_builder()
        with self.assertRaisesRegex(ValueError,"requires mode"):
            rig.bind(mesh)
        with self.assertRaisesRegex(ValueError,"requires chain"):
            rig.bind(mesh,mode="hard")
        with self.assertRaisesRegex(KeyError,"Unknown armature chain"):
            rig.bind(mesh,mode="hard",chain="missing")
        with self.assertRaisesRegex(ValueError,"bone= implies"):
            rig.bind(mesh,mode="smooth",bone="upper")

    def test_automatic_binding_does_not_depend_on_visual_bone_width(self):
        first, first_rig, mesh = rigged_builder()
        first._armature_bones["lower"].width = .01
        first._armature_bones["upper"].width = 100
        first_rig.bind(mesh,bone="lower")
        second, second_rig, second_mesh = rigged_builder()
        second._armature_bones["lower"].width = 100
        second._armature_bones["upper"].width = .01
        second_rig.bind(second_mesh,bone="lower")
        self.assertEqual(first._bindings["body"], second._bindings["body"])

    def test_joint_ring_contract_uses_named_geometry(self):
        builder = ModelBuilder("joint ring", require_integer_dimensions=False)
        rig = builder.add_armature("character")
        limb = builder.add_segment(
            "limb", rig, start=(0, 0, 0), end=(0, 10, 0),
            sections=(
                SegmentSection("base", 0, Profile.circle(1, segments=4)),
                SegmentSection("joint", .5, Profile.circle(1, segments=4)),
                SegmentSection("tip", 1, Profile.circle(1, segments=4)),
            ))
        rig.add_bone("proximal", between=("limb:base", "limb:joint"), connected=False)
        rig.add_bone("distal", parent="proximal", between=("limb:joint", "limb:tip"))
        rig.bind(limb,mode="hard",chain=("proximal","distal"))
        self.assertFalse(builder.skinning_audit()["warnings"])

    def test_joint_blend_is_local_and_zeroes_distant_influence(self):
        builder = ModelBuilder("local joint", require_integer_dimensions=False)
        rig = builder.add_armature("character")
        limb = builder.add_segment(
            "limb", rig, start=(0, 0, 0), end=(0, 10, 0),
            sections=tuple(
                SegmentSection(name, t, Profile.circle(1, segments=4))
                for name, t in (("base", 0), ("before", .4), ("joint", .5),
                                ("after", .6), ("tip", 1))
            ))
        rig.add_bone("proximal", between=("limb:base", "limb:joint"), connected=False)
        rig.add_bone("distal", parent="proximal", between=("limb:joint", "limb:tip"))
        rig.bind(limb,mode="smooth",chain=("proximal","distal"),joints=(
            JointBlend("distal", ring="joint", before="before", after="after"),
        ))
        weights = builder._bindings["limb"]
        self.assertEqual(weights["base_v000"], {"proximal": 1.0})
        self.assertEqual(weights["before_v000"], {"proximal": 1.0})
        self.assertEqual(weights["joint_v000"], {"proximal": .5, "distal": .5})
        self.assertEqual(weights["after_v000"], {"distal": 1.0})
        self.assertEqual(weights["tip_v000"], {"distal": 1.0})
        self.assertEqual(builder._binding_policies["limb"]["joints"][0]["ring"], "joint")

    def test_smooth_presets_infer_named_chain_support_rings(self):
        tight_builder,tight_rig,tight_limb=jointed_builder(dense=True)
        tight_rig.bind(tight_limb,mode="smooth",chain="limb_chain",blend="tight",
                       curve="linear")
        tight=tight_builder._binding_policies["limb"]["joints"][0]
        self.assertEqual((tight["before"],tight["ring"],tight["after"]),
                         ("near_before","joint","near_after"))
        soft_builder,soft_rig,soft_limb=jointed_builder(dense=True)
        soft_rig.bind(soft_limb,mode="smooth",chain="limb_chain",blend="soft",
                      curve="linear")
        soft=soft_builder._binding_policies["limb"]["joints"][0]
        self.assertEqual((soft["before"],soft["ring"],soft["after"]),
                         ("before","joint","after"))
        self.assertEqual(soft_builder._bindings["limb"]["near_before_v000"],
                         {"proximal":.75,"distal":.25})

    def test_hard_rejects_chain_whose_joint_is_not_a_mesh_ring(self):
        builder,rig,mesh=rigged_builder()
        with self.assertRaisesRegex(ValueError,"exactly one named ring"):
            rig.bind(mesh,mode="hard",chain=("lower","upper"))

    def test_joint_blend_rejects_missing_or_unordered_rings(self):
        builder = ModelBuilder("invalid joint", require_integer_dimensions=False)
        rig = builder.add_armature("character")
        limb = builder.add_segment(
            "limb", rig, start=(0, 0, 0), end=(0, 10, 0),
            sections=tuple(SegmentSection(name, t, Profile.circle(1, segments=4))
                           for name, t in (("base", 0), ("joint", .5), ("tip", 1))))
        rig.add_bone("proximal", between=("limb:base", "limb:joint"), connected=False)
        rig.add_bone("distal", parent="proximal", between=("limb:joint", "limb:tip"))
        with self.assertRaisesRegex(KeyError, "no ring 'missing'"):
            rig.bind(limb,mode="smooth",chain=("proximal","distal"),joints=(
                JointBlend("distal", ring="joint", before="missing", after="tip"),
            ))
        with self.assertRaisesRegex(ValueError, "must lie between"):
            rig.bind(limb,mode="smooth",chain=("proximal","distal"),joints=(
                JointBlend("distal", ring="base", before="joint", after="tip"),
            ))

    def test_bind_rejects_combining_explicit_weights_and_automatic_options(self):
        builder, rig, mesh = rigged_builder()
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            rig.bind(mesh,mode="explicit",weights=rigid_weights(builder,mesh,"upper"),
                     bone="upper")

    def test_explicit_binding_requires_complete_normalized_weights(self):
        builder, rig, mesh = rigged_builder()
        weights = rigid_weights(builder, mesh, "upper")
        rig.bind(mesh, weights=weights)
        self.assertTrue(all(value == {"upper": 1.0}
                            for value in builder._bindings["body"].values()))
        first_vertex = next(iter(weights))
        invalid = dict(weights)
        invalid[first_vertex] = {"upper": .4}
        with self.assertRaisesRegex(ValueError, "total 1.0"):
            rig.bind(mesh, weights=invalid)

    def test_explicit_binding_rejects_missing_vertices_and_unknown_bones(self):
        builder, rig, mesh = rigged_builder()
        weights = rigid_weights(builder, mesh, "upper")
        weights.pop(next(iter(weights)))
        with self.assertRaisesRegex(ValueError, "omit vertices"):
            rig.bind(mesh, weights=weights)
        weights = rigid_weights(builder, mesh, "missing")
        with self.assertRaisesRegex(KeyError, "outside its armature"):
            rig.bind(mesh, weights=weights)

    def test_socket_can_follow_real_bone_frame(self):
        builder, rig, mesh = rigged_builder()
        builder.add_socket("upper_tip", "bone:upper", at="bone:upper", offset=(0, 3, 0))
        self.assertEqual(builder.get_socket("upper_tip").origin, (0.0, 3.0, 0.0))
        rig.bind(mesh,bone="lower")

    def test_armature_mesh_can_be_edited_before_its_final_bind(self):
        builder, rig, mesh = rigged_builder()
        with builder.edit_mesh(mesh.name) as draft:
            draft.translate_vertices(draft.select_vertices(axis="Y", t=(.9,1)), (0,.1,0))
        self.assertFalse(builder.validate(require_armature_bindings=False)["errors"])
        self.assertTrue(any("not bound" in error for error in builder.validate()["errors"]))
        rig.bind(mesh,bone="lower")
        self.assertFalse(builder.validate()["errors"])

    def test_topology_change_requires_rebind_and_merge_rejects_binding(self):
        builder, rig, mesh = rigged_builder()
        builder.add_mesh("second", rig, quad_sphere(radius=1, subdivisions=1))
        second = builder.last
        rig.bind(mesh,bone="lower")
        rig.bind(second,bone="lower")
        with self.assertRaisesRegex(ValueError, "merge first"):
            builder.combine_meshes(("body", "second"), "merged")
        builder._elements[0].vertices["added"] = (0, 0, 0)
        self.assertTrue(any("bind it again" in error for error in builder.validate()["errors"]))

    def test_uv_pack_preserves_native_armature_payload(self):
        builder, rig, mesh = rigged_builder()
        rig.bind(mesh,bone="lower")
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "rig.bbmodel"
            builder.export_bbmodel(target)
            before = json.loads(target.read_text(encoding="utf-8"))
        mapped, _, _ = BoxUVPacker.pack_document(
            before, start_size=32, require_integer_uvs=False
        )
        before_rig = [item for item in before["elements"]
                      if item.get("type") in {"armature", "armature_bone"}]
        after_rig = [item for item in mapped["elements"]
                     if item.get("type") in {"armature", "armature_bone"}]
        self.assertEqual(before_rig, after_rig)

    def test_texture_registration_preserves_native_armature_and_weights(self):
        builder, rig, mesh = rigged_builder()
        rig.bind(mesh,bone="lower")
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "rig.bbmodel"
            texture = Path(temp) / "texture.png"
            builder.export_bbmodel(model)
            before = json.loads(model.read_text(encoding="utf-8"))
            mapped, _, _ = BoxUVPacker.pack_document(
                before, start_size=32, require_integer_uvs=False
            )
            model.write_text(json.dumps(mapped), encoding="utf-8")
            rig_before = [item for item in mapped["elements"]
                          if item.get("type") in {"armature", "armature_bone"}]
            TexturePainter.from_bbmodel(model).save(texture)
            after = json.loads(model.read_text(encoding="utf-8"))
            rig_after = [item for item in after["elements"]
                         if item.get("type") in {"armature", "armature_bone"}]
        self.assertEqual(rig_before, rig_after)

    def test_armature_mirror_creates_bilateral_bones_before_binding(self):
        builder = ModelBuilder("mirror", require_integer_dimensions=False)
        rig = builder.add_armature("character")
        builder.add_mesh("body", rig, quad_sphere(radius=3, subdivisions=1))
        mesh = builder.last
        rig.add_bone("arm_left", between=((-1, 0, 0), (-4, 0, 0)), connected=False)
        rig.mirror("arm_left", "arm_right")
        rig.bind(mesh,bone="arm_left")
        left, right = builder._armature_bones["arm_left"], builder._armature_bones["arm_right"]
        self.assertEqual(right.start, (-left.start[0], left.start[1], left.start[2]))
        self.assertEqual(right.end, (-left.end[0], left.end[1], left.end[2]))
        self.assertEqual(builder.validate()["errors"], [])

    def test_folder_can_organize_armature_without_becoming_a_second_transform(self):
        builder = ModelBuilder("mixed", require_integer_dimensions=False)
        builder.add_group("root")
        builder.add_group("accessories", "root")
        builder.add_transform_group("hat_joint", "accessories", pivot=(0, 4, 0))
        builder.add_cylinder("hat", "hat_joint", radius=1, height=1, segments=4)
        rig = builder.add_armature("body_rig", parent="root")
        builder.add_mesh("body", rig, quad_sphere(radius=2, subdivisions=1))
        mesh = builder.last
        rig.add_bone("spine", between=((0, -2, 0), (0, 2, 0)))
        rig.bind(mesh, weights=rigid_weights(builder, mesh, "spine"))
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "mixed.bbmodel"
            builder.export_bbmodel(target)
            document = json.loads(target.read_text(encoding="utf-8"))
            loaded = ModelBuilder.from_bbmodel_data(document)
        self.assertEqual(loaded._armatures["body_rig"].parent, "root")
        root_node = next(node for node in document["outliner"] if node["uuid"] == builder._groups["root"].uuid)
        self.assertTrue(any(
            isinstance(child, dict) and child.get("uuid") == builder._armatures["body_rig"].uuid
            for child in root_node["children"]
        ))
        with self.assertRaisesRegex(ValueError, "folder groups"):
            builder.add_armature("invalid", parent="hat_joint")

    def test_import_rejects_unsupported_unknown_element_types(self):
        with self.assertRaisesRegex(ValueError, "Unsupported Blockbench element types"):
            ModelBuilder.from_bbmodel_data({
                "name": "unknown",
                "elements": [{"type": "unknown_armature", "uuid": "unknown"}],
                "groups": [],
                "outliner": [],
            })

    def test_import_rejects_non_native_armature_offset(self):
        with self.assertRaisesRegex(ValueError, "do not support an offset origin"):
            ModelBuilder.from_bbmodel_data({
                "name": "offset",
                "elements": [{"type": "armature", "uuid": "rig", "name": "rig",
                              "origin": [1, 0, 0], "children": []}],
                "groups": [],
                "outliner": ["rig"],
            })


if __name__ == "__main__":
    unittest.main()
