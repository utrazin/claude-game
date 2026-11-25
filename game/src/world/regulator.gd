class_name RegulatorView
extends Node3D
## The regulator at the end of the train: a brass portal with a pendulum.
## Its swing is a diegetic gauge: rhythm = beat frequency, swing angle = amplitude,
## rod length shortens as the regulator is upgraded (faster pendulum).

var eco: Economy
var mech: Mechanism
var pivot: Node3D
var rod: MeshInstance3D
var bob: MeshInstance3D
var _phase := 0.0
var _len := 1.0
var _swing := 0.0


func setup(e: Economy, m: Mechanism) -> void:
	eco = e; mech = m
	var frame_m := Mats.brass_aged()
	for sx in [-1.0, 1.0]:
		var post := MeshInstance3D.new(); var c := CylinderMesh.new()
		c.top_radius = 0.025; c.bottom_radius = 0.04; c.height = 1.0; c.radial_segments = 24
		post.mesh = c; post.material_override = frame_m; post.name = "Post"; add_child(post)
		post.set_meta("side", sx)
	var beam := MeshInstance3D.new(); var b := BoxMesh.new(); b.size = Vector3(0.5, 0.05, 0.08)
	beam.mesh = b; beam.material_override = Mats.brass(); beam.name = "Beam"; add_child(beam)
	pivot = Node3D.new(); add_child(pivot)
	rod = MeshInstance3D.new(); var rc := CylinderMesh.new(); rc.top_radius = 0.008; rc.bottom_radius = 0.008; rc.height = 1.0
	rod.mesh = rc; rod.material_override = Mats.blued_steel(); pivot.add_child(rod)
	bob = MeshInstance3D.new(); var bs := CylinderMesh.new(); bs.top_radius = 0.09; bs.bottom_radius = 0.09; bs.height = 0.035; bs.radial_segments = 64
	bob.mesh = bs; bob.rotation.x = PI / 2; bob.material_override = Mats.brass(); pivot.add_child(bob)
	var lens := MeshInstance3D.new(); var ls := SphereMesh.new(); ls.radius = 0.06; ls.height = 0.05
	lens.mesh = ls; lens.position.z = 0.02; lens.material_override = Mats.brass(); bob.add_child(lens)


func _process(delta: float) -> void:
	if eco == null:
		return
	var f := eco.beat_freq()
	# visual length: physical length for half-period = 1/f, clamped to a readable range
	var target_len := clampf(9.81 / (PI * PI * maxf(f, 0.05) * maxf(f, 0.05)), 0.35, 0.9)   # early portal must not dominate the bench
	_len = lerpf(_len, target_len, 1.0 - exp(-2.0 * delta))
	var swing_target := 0.0 if f <= 0.0 else deg_to_rad(clampf(eco.amplitude() * 7.0, 2.5, 14.0))
	_swing = lerpf(_swing, swing_target, 1.0 - exp(-1.5 * delta))
	var vis_f := minf(f, 3.0)                       # above ~3 beats/s show a fast shimmer instead
	_phase += delta * vis_f * PI
	pivot.rotation.z = sin(_phase) * _swing
	# place the portal over the last arbor
	var last := 0
	for i in eco.levels.size():
		if eco.levels[i] > 0: last = i
	var top := mech.axle_height + _len + 0.35
	var r_last := eco.teeth(last) * Mechanism.MODULE * 0.5
	position = mech.position + mech.arbors[last].position + Vector3(r_last + 0.32, 0, 0.0)
	position.y = mech.position.y
	pivot.position = Vector3(0, top, 0)
	rod.scale.y = _len; rod.position.y = -_len * 0.5
	bob.position.y = -_len
	for c in get_children():
		if c.name.begins_with("Post"):
			var mi := c as MeshInstance3D
			mi.scale.y = top; mi.position = Vector3(0.22 * float(mi.get_meta("side")), top * 0.5, 0)
	get_node("Beam").position = Vector3(0, top, 0)
