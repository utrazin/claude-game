class_name Props
extends Node3D
## Set dressing that is also a readout (pillar "the world is the dial"):
## - drive weight on a real chain over a pulley, sinking into its stone-rimmed shaft as energy is spent;
## - the winding crank (turned walnut handle, brass arm);
## - two columns and an entablature framing the bench (AST-CA-003 panel 3);
## - the wind rotor in the dome lantern, spinning with the automatic winding rate.

var eco: Economy
var mech: Mechanism
var crank: Node3D
var weight: Node3D
var _weight_body: Node3D
var _chain: MultiMeshInstance3D
var _pulley: Node3D
var _well: Node3D
var _frame: Node3D
var _rotor: Node3D
var _rotor_spin := 0.0
const LINK := 0.028


func setup(e: Economy, m: Mechanism) -> void:
	eco = e; mech = m
	_build_crank(); _build_weight(); _build_frame(); _build_rotor()
	eco.purchased.connect(func(k, _i):
		if k in ["weight", "load"]: _refresh_weight()
		if k in ["rotor", "load"]: _rotor.visible = eco.rotor >= 0)
	_refresh_weight()
	_rotor.visible = eco.rotor >= 0


func _cyl(rt: float, rb: float, h: float, mat: Material, seg := 48) -> MeshInstance3D:
	var mi := MeshInstance3D.new(); var c := CylinderMesh.new()
	c.top_radius = rt; c.bottom_radius = rb; c.height = h; c.radial_segments = seg
	mi.mesh = c; mi.material_override = mat
	return mi


# ------------------------------------------------------------------ crank
func _build_crank() -> void:
	crank = Node3D.new(); crank.name = "Crank"; add_child(crank)
	var boss := _cyl(0.045, 0.05, 0.05, Mats.brass()); boss.rotation.x = PI / 2; crank.add_child(boss)
	# swan-neck arm: three brass segments along a gentle arc
	var pts := [Vector3(0, 0, 0.03), Vector3(0.11, 0.025, 0.035), Vector3(0.22, 0.02, 0.04), Vector3(0.30, 0.0, 0.045)]
	for i in 3:
		var a: Vector3 = pts[i]; var b: Vector3 = pts[i + 1]
		var seg := _cyl(0.014 - i * 0.002, 0.016 - i * 0.002, a.distance_to(b) + 0.01, Mats.brass(), 24)
		seg.position = (a + b) * 0.5
		seg.look_at_from_position(seg.position, b, Vector3.FORWARD); seg.rotate_object_local(Vector3.RIGHT, PI / 2)
		crank.add_child(seg)
	var ferrule := _cyl(0.018, 0.018, 0.02, Mats.brass(), 32); ferrule.rotation.x = PI / 2
	ferrule.position = Vector3(0.30, 0.0, 0.06); crank.add_child(ferrule)
	var handle := MeshInstance3D.new(); var cap := CapsuleMesh.new(); cap.radius = 0.024; cap.height = 0.13; cap.radial_segments = 32
	handle.mesh = cap; handle.material_override = Mats.walnut(); handle.rotation.x = PI / 2
	handle.position = Vector3(0.30, 0.0, 0.13); crank.add_child(handle)
	var nut := _cyl(0.012, 0.012, 0.012, Mats.blued_steel(), 6); nut.rotation.x = PI / 2
	nut.position = Vector3(0, 0, 0.06); crank.add_child(nut)


# ------------------------------------------------------------------ weight, chain, pulley, shaft
func _build_weight() -> void:
	weight = Node3D.new(); weight.name = "Weight"; add_child(weight)
	_weight_body = Node3D.new(); weight.add_child(_weight_body)
	_pulley = Node3D.new(); add_child(_pulley)
	var wheel := _cyl(0.06, 0.06, 0.018, Mats.brass(), 48); wheel.rotation.x = PI / 2; _pulley.add_child(wheel)
	var groove := MeshInstance3D.new(); var t := TorusMesh.new(); t.ring_segments = 12; t.inner_radius = 0.05; t.outer_radius = 0.066
	groove.mesh = t; groove.rotation.x = PI / 2; groove.material_override = Mats.brass_aged(); _pulley.add_child(groove)
	var post := _cyl(0.014, 0.018, 1.0, Mats.blued_steel(), 24); post.name = "Post"; _pulley.add_child(post)
	_chain = MultiMeshInstance3D.new(); var mm := MultiMesh.new(); mm.transform_format = MultiMesh.TRANSFORM_3D
	var link := TorusMesh.new(); link.ring_segments = 12; link.inner_radius = 0.006; link.outer_radius = 0.011; link.rings = 10; link.ring_segments = 6
	mm.mesh = link; mm.instance_count = 160; mm.visible_instance_count = 0; _chain.multimesh = mm
	_chain.material_override = Mats.steel(); add_child(_chain)
	_well = Node3D.new(); add_child(_well)
	var rim := MeshInstance3D.new(); var rt := TorusMesh.new(); rt.ring_segments = 12; rt.inner_radius = 0.16; rt.outer_radius = 0.24; rt.rings = 48
	rim.mesh = rt; rim.scale.y = 0.5; var stone := StandardMaterial3D.new(); stone.albedo_color = Color(0.22, 0.21, 0.20); stone.roughness = 0.95
	rim.material_override = stone; _well.add_child(rim)
	var hole := _cyl(0.17, 0.17, 0.02, StandardMaterial3D.new(), 48)
	(hole.material_override as StandardMaterial3D).albedo_color = Color(0.01, 0.01, 0.01); hole.position.y = -0.005; _well.add_child(hole)


func _refresh_weight() -> void:
	for c in _weight_body.get_children(): c.queue_free()
	var h := 0.16 + 0.025 * mini(eco.weight, 14)          # heavier weight = taller lead body
	var body := _cyl(0.085, 0.085, h, Mats.lead(), 48); body.position.y = -h * 0.5 - 0.03; _weight_body.add_child(body)
	for i in mini(eco.weight, 14):                         # a fine groove per added slab
		var g := MeshInstance3D.new(); var t := TorusMesh.new(); t.ring_segments = 12; t.inner_radius = 0.084; t.outer_radius = 0.089; t.rings = 40; t.ring_segments = 6
		g.mesh = t; g.material_override = Mats.lead(); g.position.y = -0.03 - 0.16 * 0.5 - 0.025 * i; _weight_body.add_child(g)
	var top := _cyl(0.07, 0.09, 0.03, Mats.brass(), 48); top.position.y = -0.015; _weight_body.add_child(top)
	var bot := _cyl(0.09, 0.07, 0.025, Mats.brass(), 48); bot.position.y = -h - 0.045; _weight_body.add_child(bot)
	var hook := MeshInstance3D.new(); var t2 := TorusMesh.new(); t2.ring_segments = 12; t2.inner_radius = 0.012; t2.outer_radius = 0.02
	hook.mesh = t2; hook.rotation.x = PI / 2; hook.position.y = 0.015; hook.material_override = Mats.brass(); _weight_body.add_child(hook)


func update_weight(frac: float) -> void:
	var a0: Vector3 = mech.position + mech.arbors[0].position
	var x := a0.x - eco.teeth(0) * Mechanism.MODULE * 0.5 - 0.75
	var top_y := a0.y + 0.15
	_pulley.position = Vector3(x, top_y, 0.05)
	var post := _pulley.get_node("Post") as MeshInstance3D
	post.position = Vector3(0, -top_y * 0.5, -0.04); post.scale.y = top_y
	_well.position = Vector3(x, 0.012, 0.05)
	var wy := lerpf(-0.15, top_y - 0.35, frac)
	weight.position = Vector3(x, wy, 0.05)
	# chain from the pulley rim down to the hook, links alternating 90°
	var from := Vector3(x, top_y - 0.06, 0.05); var to := Vector3(x, wy + 0.035, 0.05)
	var n := clampi(int(from.distance_to(to) / LINK), 0, _chain.multimesh.instance_count)
	_chain.multimesh.visible_instance_count = n
	for i in n:
		var p := from.lerp(to, (i + 0.5) / maxf(n, 1))
		var b := Basis(Vector3.RIGHT, PI / 2) if i % 2 == 0 else Basis(Vector3.UP, PI / 2) * Basis(Vector3.RIGHT, PI / 2)
		_chain.multimesh.set_instance_transform(i, Transform3D(b, p))


# ------------------------------------------------------------------ framing columns
func _build_frame() -> void:
	_frame = Node3D.new(); add_child(_frame)


func layout_frame(x0: float, x1: float, z: float) -> void:
	for c in _frame.get_children(): c.queue_free()
	var stone := StandardMaterial3D.new()
	stone.albedo_texture = load("res://assets/textures/limestone_albedo.png"); stone.uv1_scale = Vector3(0.6, 1.4, 1)
	stone.normal_enabled = true; stone.normal_texture = load("res://assets/textures/limestone_normal.png"); stone.roughness = 0.88
	var hgt := 3.4
	for x in [x0 - 0.55, x1 + 0.55]:
		var col := Node3D.new(); col.position = Vector3(x, 0, z - 0.75); _frame.add_child(col)
		var base := MeshInstance3D.new(); var bb := BoxMesh.new(); bb.size = Vector3(0.42, 0.28, 0.42); base.mesh = bb
		base.material_override = stone; base.position.y = 0.14; col.add_child(base)
		var torus := MeshInstance3D.new(); var tt := TorusMesh.new(); tt.ring_segments = 12; tt.inner_radius = 0.13; tt.outer_radius = 0.19; tt.rings = 48
		torus.mesh = tt; torus.material_override = Mats.brass_aged(); torus.position.y = 0.30; col.add_child(torus)
		var shaft := _cyl(0.125, 0.15, hgt - 0.6, stone, 48); shaft.position.y = 0.3 + (hgt - 0.6) * 0.5; col.add_child(shaft)
		var neck := MeshInstance3D.new(); var nt := TorusMesh.new(); nt.ring_segments = 12; nt.inner_radius = 0.11; nt.outer_radius = 0.16; nt.rings = 48
		neck.mesh = nt; neck.material_override = Mats.brass(); neck.position.y = hgt - 0.3; col.add_child(neck)
		var cap := MeshInstance3D.new(); var cb := BoxMesh.new(); cb.size = Vector3(0.40, 0.2, 0.40); cap.mesh = cb
		cap.material_override = stone; cap.position.y = hgt - 0.12; col.add_child(cap)
	var beam := MeshInstance3D.new(); var bm := BoxMesh.new(); bm.size = Vector3(x1 - x0 + 1.6, 0.18, 0.36)
	beam.mesh = bm; beam.material_override = Mats.walnut(); beam.position = Vector3((x0 + x1) * 0.5, hgt + 0.07, z - 0.75); _frame.add_child(beam)
	var strip := MeshInstance3D.new(); var sm := BoxMesh.new(); sm.size = Vector3(x1 - x0 + 1.6, 0.03, 0.01)
	strip.mesh = sm; strip.material_override = Mats.brass(); strip.position = Vector3((x0 + x1) * 0.5, hgt + 0.07, z - 0.75 + 0.185); _frame.add_child(strip)


# ------------------------------------------------------------------ wind rotor (dome lantern)
func _build_rotor() -> void:
	_rotor = Node3D.new(); _rotor.name = "WindRotor"; add_child(_rotor)
	_rotor.position = Vector3(0, Room.WALL_H + Room.RADIUS - 0.55, 0)
	var ring := MeshInstance3D.new(); var t := TorusMesh.new(); t.ring_segments = 12; t.inner_radius = 0.62; t.outer_radius = 0.68; t.rings = 64
	ring.mesh = t; ring.material_override = Mats.brass_aged(); _rotor.add_child(ring)
	var hub := _cyl(0.07, 0.07, 0.12, Mats.brass(), 32); _rotor.add_child(hub)
	var spin := Node3D.new(); spin.name = "Spin"; _rotor.add_child(spin)
	for k in 8:
		var vane := MeshInstance3D.new(); var b := BoxMesh.new(); b.size = Vector3(0.55, 0.012, 0.13)
		vane.mesh = b; vane.material_override = Mats.brass()
		var piv := Node3D.new(); piv.rotation.y = TAU * k / 8.0; spin.add_child(piv)
		vane.position = Vector3(0.34, 0, 0); vane.rotation.x = deg_to_rad(28.0); piv.add_child(vane)


func _process(delta: float) -> void:
	if _rotor.visible:
		_rotor_spin += delta * (0.4 + 0.6 * log(1.0 + eco.rotor_rate()))
		(_rotor.get_node("Spin") as Node3D).rotation.y = _rotor_spin
