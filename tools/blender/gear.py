"""Procedural clock-wheel generator (Blender bpy, headless).

Builds a horological wheel: involute-approximated teeth, rim, crossed/curved
spokes ("crossings"), hub with arbor hole, then bevel + weighted normals so the
silhouette catches light. Exports GLB in metres, Y-up, wheel lying in the XZ
plane with the axis along +Y and the pivot at the arbor centre.

Usage:
  python3 tools/blender/gear.py --teeth 60 --module 0.004 --spokes 5 --out assets/models/gears/wheel_60.glb
"""
import argparse, math, sys
import bpy, bmesh


def parse():
    p = argparse.ArgumentParser()
    p.add_argument("--teeth", type=int, default=60)
    p.add_argument("--module", type=float, default=0.004, help="pitch diameter / teeth (m)")
    p.add_argument("--thickness", type=float, default=0.006)
    p.add_argument("--spokes", type=int, default=5, help="0 = solid disc (pinion)")
    p.add_argument("--curved", type=float, default=0.35, help="spoke sweep, 0 = straight")
    p.add_argument("--hub", type=float, default=0.18, help="hub radius / pitch radius")
    p.add_argument("--rim", type=float, default=0.14, help="rim width / pitch radius")
    p.add_argument("--out", required=True)
    return p.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])


def tooth_profile(n, m, samples=6):
    """Closed 2D outline of the toothed rim (list of (x, y)). Horological cycloidal-ish
    teeth: flat root, rounded ogival tip, slight undercut — reads as a clock wheel."""
    rp = n * m / 2.0
    ra = rp + 1.0 * m          # addendum (clock teeth are tall and pointed)
    rf = rp - 1.25 * m         # dedendum
    pts = []
    step = 2 * math.pi / n
    for i in range(n):
        a0 = i * step
        # root flat (~55% of pitch), flank up, ogival tip, flank down
        for k in range(samples):
            t = k / samples
            a = a0 + t * step * 0.50
            pts.append((rf * math.cos(a), rf * math.sin(a)))
        flank = step * 0.50
        tip_half = step * 0.25
        for k in range(samples * 2 + 1):
            t = k / (samples * 2)                  # 0..1 across the tooth
            s = math.sin(t * math.pi)              # 0 -> 1 -> 0
            r = rf + (ra - rf) * (s ** 0.6)        # ogival
            a = a0 + flank + t * (step - flank)
            pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def build(args):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    n, m = args.teeth, args.module
    rp = n * m / 2.0
    th = args.thickness
    bm = bmesh.new()

    # --- outer toothed outline as a face, extruded
    outline = tooth_profile(n, m)
    verts = [bm.verts.new((x, y, 0.0)) for x, y in outline]
    face = bm.faces.new(verts)

    # --- inner cut-outs (between spokes) as separate faces we will subtract via boolean
    res = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [e for e in res["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top, vec=(0, 0, th))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("wheel")
    bm.to_mesh(me)
    bm.free()
    wheel = bpy.data.objects.new("wheel", me)
    bpy.context.collection.objects.link(wheel)

    def add_cutter(points, name):
        b = bmesh.new()
        vs = [b.verts.new((x, y, -0.01)) for x, y in points]
        f = b.faces.new(vs)
        r = bmesh.ops.extrude_face_region(b, geom=[f])
        tv = [e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(b, verts=tv, vec=(0, 0, th + 0.02))
        bmesh.ops.recalc_face_normals(b, faces=b.faces)
        mm = bpy.data.meshes.new(name); b.to_mesh(mm); b.free()
        o = bpy.data.objects.new(name, mm); bpy.context.collection.objects.link(o)
        return o

    cutters = []
    r_in = rp - 1.25 * m - args.rim * rp           # inner edge of rim
    r_hub = args.hub * rp
    if args.spokes > 0 and r_in > r_hub * 1.4:
        k = args.spokes
        spoke_w = max(0.06 * rp, 1.2 * m)
        seg = 2 * math.pi / k
        for s in range(k):
            pts = []
            steps = 40
            # window bounded by rim arc (outer), two curved spokes, hub arc (inner)
            a_start = s * seg
            def spoke_angle(r):           # curved spoke centreline angle offset
                u = (r - r_hub) / (r_in - r_hub)
                return args.curved * math.sin(u * math.pi) * 0.6
            def half_w(r):                # angular half width of spoke at radius r
                return (spoke_w * (1.25 - 0.35 * (r - r_hub) / (r_in - r_hub))) / (2 * r)
            # outer arc
            a0 = a_start + spoke_angle(r_in) + half_w(r_in)
            a1 = a_start + seg + spoke_angle(r_in) - half_w(r_in)
            for i in range(steps + 1):
                a = a0 + (a1 - a0) * i / steps
                pts.append((r_in * math.cos(a), r_in * math.sin(a)))
            # down along next spoke (leading side)
            for i in range(1, steps):
                r = r_in - (r_in - r_hub * 1.25) * i / steps
                a = a_start + seg + spoke_angle(r) - half_w(r)
                pts.append((r * math.cos(a), r * math.sin(a)))
            rh = r_hub * 1.25
            a2 = a_start + seg + spoke_angle(rh) - half_w(rh)
            a3 = a_start + spoke_angle(rh) + half_w(rh)
            for i in range(steps + 1):
                a = a2 + (a3 - a2) * i / steps
                pts.append((rh * math.cos(a), rh * math.sin(a)))
            for i in range(1, steps):
                r = r_hub * 1.25 + (r_in - r_hub * 1.25) * i / steps
                a = a_start + spoke_angle(r) + half_w(r)
                pts.append((r * math.cos(a), r * math.sin(a)))
            cutters.append(add_cutter(pts, f"win{s}"))
    # arbor hole
    hole_r = max(0.8 * m, 0.04 * rp)
    cutters.append(add_cutter([(hole_r * math.cos(t), hole_r * math.sin(t))
                               for t in [i * 2 * math.pi / 48 for i in range(48)]], "arbor"))

    for c in cutters:
        mod = wheel.modifiers.new("cut", "BOOLEAN"); mod.operation = "DIFFERENCE"
        mod.object = c; mod.solver = "EXACT"
        bpy.context.view_layer.objects.active = wheel
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(c)

    # hub boss (raised collet) for depth
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=r_hub, depth=th * 1.8,
                                        location=(0, 0, th * 0.9))
    boss = bpy.context.active_object
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=hole_r, depth=th * 4, location=(0, 0, th))
    bore = bpy.context.active_object
    mod = boss.modifiers.new("bore", "BOOLEAN"); mod.operation = "DIFFERENCE"; mod.object = bore; mod.solver = "EXACT"
    bpy.context.view_layer.objects.active = boss; bpy.ops.object.modifier_apply(modifier="bore")
    bpy.data.objects.remove(bore)

    for o in (wheel, boss):
        bpy.context.view_layer.objects.active = o
        bv = o.modifiers.new("bevel", "BEVEL")
        bv.width = min(th * 0.12, m * 0.18); bv.segments = 2; bv.limit_method = "ANGLE"
        bv.angle_limit = math.radians(40); bv.harden_normals = True
        bpy.ops.object.modifier_apply(modifier="bevel")
        wn = o.modifiers.new("wn", "WEIGHTED_NORMAL"); wn.keep_sharp = True
        bpy.ops.object.modifier_apply(modifier="wn")

    # join, center on axis, rotate so axis is +Y in glTF (Blender Z-up -> glTF Y-up handled by exporter)
    bpy.ops.object.select_all(action="DESELECT")
    wheel.select_set(True); boss.select_set(True)
    bpy.context.view_layer.objects.active = wheel
    bpy.ops.object.join()
    wheel.location = (0, 0, -th / 2)
    bpy.ops.object.transform_apply(location=True)

    # cylindrical-ish UVs: planar top projection is fine for brushed/engraved brass
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.cube_project(cube_size=rp * 2.4); bpy.ops.object.mode_set(mode="OBJECT")

    mat = bpy.data.materials.new("brass"); mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.78, 0.56, 0.26, 1)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.32
    wheel.data.materials.append(mat)
    wheel.name = f"wheel_{n}"
    print("tris:", sum(len(p.vertices) - 2 for p in wheel.data.polygons))
    bpy.ops.export_scene.gltf(filepath=args.out, export_format="GLB", use_selection=False,
                              export_yup=True, export_apply=True)


if __name__ == "__main__":
    build(parse())
