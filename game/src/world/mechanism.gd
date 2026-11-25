class_name Mechanism
extends Node3D
## Builds and animates the going train from the Economy state.
## Layout (D09): horizontal train on a walnut base, wheels shrinking left → right.
## Arbors are perpendicular to the viewer (axis = +Z). Wheel i sits on arbor i at layer z_i and
## meshes with the 12-leaf pinion of arbor i+1 (same layer).

signal layout_changed(bounds: AABB)

const MODULE := 0.02
const PINION := 12
const LAYER := 0.09            ## z spacing between stage layers
const WRAP := TAU * 248832.0   ## 12^5 turns: every derived arbor stays visually continuous on wrap
const ZIG := [deg_to_rad(12.0), deg_to_rad(-9.0)]

var eco: Economy
var arbors: Array[Node3D] = []        ## static node per stage (position, pillar)
var spins: Array[Node3D] = []         ## rotating child (wheel, pinion, rod)
var wheels: Array[Node3D] = []
var pinions: Array[Node3D] = []
var pillars: Array[MeshInstance3D] = []
var _target_pos: Array[Vector3] = []
var _theta0 := 0.0
var _shown_teeth: Array[int] = []
var axle_height := 0.6
var _scenes := {}


func setup(e: Economy) -> void:
	eco = e
	eco.purchased.connect(func(_k, _i): rebuild())
	rebuild(true)


func _scene(key: String) -> PackedScene:
	if not _scenes.has(key):
		_scenes[key] = load("res://assets/models/gears/%s.glb" % key)
	return _scenes[key]


func _ensure(n: int) -> void:
	while arbors.size() < n:
		var i := arbors.size()
		var a := Node3D.new(); a.name = "Arbor%d" % i; add_child(a)
		var s := Node3D.new(); s.name = "Spin"; a.add_child(s)
		arbors.append(a); spins.append(s); wheels.append(null); pinions.append(null)
		_target_pos.append(Vector3.ZERO); _shown_teeth.append(0)
		# arbor rod (blued steel), turns with the arbor
		var rod := MeshInstance3D.new(); rod.name = "Rod"
		var cm := CylinderMesh.new(); cm.top_radius = 0.016; cm.bottom_radius = 0.016
		cm.height = (i + 1) * LAYER + 0.22; cm.radial_segments = 32
		rod.mesh = cm; rod.rotation.x = PI / 2.0; rod.position.z = cm.height * 0.5 - 0.17
		rod.material_override = Mats.blued_steel(); s.add_child(rod)
		# pillar + bearing (static)
		var p := MeshInstance3D.new(); p.name = "Pillar"
		var pc := CylinderMesh.new(); pc.top_radius = 0.032; pc.bottom_radius = 0.048; pc.radial_segments = 32; pc.height = 1.0
		p.mesh = pc; p.material_override = Mats.brass_aged(); p.position.z = -0.14
		a.add_child(p); pillars.append(p)
		var cap := MeshInstance3D.new(); var sm := CylinderMesh.new()
		sm.top_radius = 0.055; sm.bottom_radius = 0.055; sm.height = 0.05; sm.radial_segments = 40
		cap.mesh = sm; cap.rotation.x = PI / 2.0; cap.position.z = -0.13; cap.material_override = Mats.brass(); a.add_child(cap)
		var screw := MeshInstance3D.new(); var ss := CylinderMesh.new()
		ss.top_radius = 0.022; ss.bottom_radius = 0.022; ss.height = 0.02; ss.radial_segments = 24
		screw.mesh = ss; screw.rotation.x = PI / 2.0; screw.position.z = -0.1; screw.material_override = Mats.blued_steel(); a.add_child(screw)


## Rebuild geometry where it changed and recompute target layout.
func rebuild(instant := false) -> void:
	var n := eco.levels.size()
	_ensure(n)
	var max_r := 0.0
	for i in n:
		if eco.levels[i] > 0:
			max_r = maxf(max_r, eco.teeth(i) * MODULE * 0.5)
	axle_height = max_r + 0.22
	var pos := Vector3(0, axle_height, 0)
	for i in n:
		var active := eco.levels[i] > 0
		arbors[i].visible = active
		if not active:
			continue
		var t := eco.teeth(i)
		if _shown_teeth[i] != t:
			if wheels[i]:
				wheels[i].queue_free()
			var w := _scene("wheel_%d" % t).instantiate() as Node3D
			w.rotation.x = PI / 2.0            # GLB axis is +Y; train axis is +Z
			w.position.z = i * LAYER
			Mats.apply(w, Mats.brass())
			spins[i].add_child(w); wheels[i] = w
			_shown_teeth[i] = t
			if not instant:
				_pop(w)
		if i > 0 and pinions[i] == null:
			var p := _scene("pinion_12").instantiate() as Node3D
			p.rotation.x = PI / 2.0
			p.position.z = (i - 1) * LAYER
			Mats.apply(p, Mats.blued_steel())
			spins[i].add_child(p); pinions[i] = p
		_target_pos[i] = pos
		if instant:
			arbors[i].position = pos
		var d := (t + PINION) * MODULE * 0.5
		var ang: float = ZIG[i % 2]
		pos += Vector3(cos(ang), sin(ang), 0.0) * d
	layout_changed.emit(bounds())


func _pop(w: Node3D) -> void:
	w.scale = Vector3.ONE * 0.9
	var tw := create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_property(w, "scale", Vector3.ONE, 0.5)


func bounds() -> AABB:
	var box := AABB(Vector3(0, 0, 0), Vector3(0.01, 0.01, 0.01))
	for i in eco.levels.size():
		if eco.levels[i] <= 0:
			continue
		var r := eco.teeth(i) * MODULE * 0.5 + MODULE
		var c := _target_pos[i]
		box = box.merge(AABB(c - Vector3(r, r, 0), Vector3(2 * r, 2 * r, LAYER * (i + 1))))
	return box


## Rightmost x of the train (used by the base to size itself).
func train_extent() -> float:
	return bounds().end.x


func _process(delta: float) -> void:
	if eco == null:
		return
	var k := 1.0 - exp(-6.0 * delta)
	for i in arbors.size():
		arbors[i].position = arbors[i].position.lerp(_target_pos[i], k)
		# pillar spans from the base top (y=0 in mechanism space) to the bearing
		var h := maxf(arbors[i].position.y, 0.05)
		pillars[i].scale.y = h
		pillars[i].position.y = -h * 0.5
	var last := 0
	var prod := 1.0
	for i in eco.levels.size():
		if eco.levels[i] > 0:
			last = i
	for i in last:
		prod *= eco.ratio(i)
	# last arbor turns 1/60 of a revolution per beat
	var w_last := eco.beat_rate() * TAU / 60.0
	_theta0 = fmod(_theta0 + w_last / prod * delta, WRAP)
	var theta := _theta0
	for i in last + 1:
		if i > 0:
			var r := eco.ratio(i - 1)
			var step_w := TAU / eco.teeth(i - 1)
			var step_p := TAU / PINION
			var phi: float = ZIG[(i - 1) % 2]
			var c := phi + PI - 0.25 * step_p + r * (phi - 0.75 * step_w)
			theta = c - r * theta
		spins[i].rotation.z = fmod(theta, TAU)
