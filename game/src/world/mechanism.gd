class_name Mechanism
extends Node3D
## Builds and animates the going train from the Economy state.
## Front view: arbors are perpendicular to the back plate (axis = +Z).
## Wheel i sits on arbor i at layer z_i and meshes with the 12-leaf pinion of arbor i+1.

signal layout_changed(bounds: AABB)

const MODULE := 0.02
const PINION := 12
const LAYER := 0.09            ## z spacing between stage layers
const WRAP := TAU * 248832.0   ## 12^5 turns: keeps every derived arbor visually continuous on wrap

var eco: Economy
var arbors: Array[Node3D] = []        ## one Node3D per stage (arbor i)
var wheels: Array[Node3D] = []
var pinions: Array[Node3D] = []
var _target_pos: Array[Vector3] = []
var _theta0 := 0.0
var _shown_teeth: Array[int] = []
var _zig := [deg_to_rad(62.0), deg_to_rad(118.0)]

@onready var _scenes := {}


func setup(e: Economy) -> void:
	eco = e
	eco.purchased.connect(func(_k, _i): rebuild())
	rebuild(true)


func _gear_scene(teeth: int) -> PackedScene:
	var key := "wheel_%d" % teeth
	if not _scenes.has(key):
		_scenes[key] = load("res://assets/models/gears/%s.glb" % key)
	return _scenes[key]


func _pinion_scene() -> PackedScene:
	if not _scenes.has("pinion"):
		_scenes["pinion"] = load("res://assets/models/gears/pinion_12.glb")
	return _scenes["pinion"]


## Rebuild geometry where it changed and recompute target layout.
func rebuild(instant := false) -> void:
	var n := eco.levels.size()
	while arbors.size() < n:
		var a := Node3D.new(); a.name = "Arbor%d" % arbors.size(); add_child(a)
		arbors.append(a); wheels.append(null); pinions.append(null)
		_target_pos.append(Vector3.ZERO); _shown_teeth.append(0)
	var pos := Vector3.ZERO
	for i in n:
		var active := eco.levels[i] > 0
		arbors[i].visible = active
		if not active:
			continue
		var t := eco.teeth(i)
		if _shown_teeth[i] != t:
			if wheels[i]: wheels[i].queue_free()
			var w := _gear_scene(t).instantiate() as Node3D
			w.rotation.x = PI / 2.0            # GLB axis is +Y; train axis is +Z
			w.position.z = i * LAYER
			Mats.apply(w, Mats.brass())
			arbors[i].add_child(w); wheels[i] = w
			_shown_teeth[i] = t
			if not instant:
				_pop(w)
		if i > 0 and pinions[i] == null:
			var p := _pinion_scene().instantiate() as Node3D
			p.rotation.x = PI / 2.0
			p.position.z = (i - 1) * LAYER
			Mats.apply(p, Mats.blued_steel())
			arbors[i].add_child(p); pinions[i] = p
			_add_arbor_rod(arbors[i], i)
		elif i == 0 and arbors[0].get_node_or_null("Rod") == null:
			_add_arbor_rod(arbors[0], 0)
		_target_pos[i] = pos
		if instant:
			arbors[i].position = pos
		# next arbor centre: wheel i pitch radius + pinion pitch radius
		var d := (t + PINION) * MODULE * 0.5
		var ang: float = _zig[i % 2]
		pos += Vector3(cos(ang), sin(ang), 0.0) * d
	layout_changed.emit(bounds())


func _add_arbor_rod(parent: Node3D, i: int) -> void:
	var rod := MeshInstance3D.new(); rod.name = "Rod"
	var cm := CylinderMesh.new(); cm.top_radius = 0.018; cm.bottom_radius = 0.018
	cm.height = (i + 1) * LAYER + 0.25; cm.radial_segments = 32
	rod.mesh = cm; rod.rotation.x = PI / 2.0; rod.position.z = cm.height * 0.5 - 0.2
	rod.material_override = Mats.steel()
	parent.add_child(rod)


func _pop(w: Node3D) -> void:
	w.scale = Vector3.ONE * 0.92
	var tw := create_tween().set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_property(w, "scale", Vector3.ONE, 0.45)


func bounds() -> AABB:
	var box := AABB(Vector3.ZERO, Vector3.ZERO)
	for i in eco.levels.size():
		if eco.levels[i] <= 0:
			continue
		var r := eco.teeth(i) * MODULE * 0.5 + MODULE
		var c := _target_pos[i]
		box = box.merge(AABB(c - Vector3(r, r, 0), Vector3(2 * r, 2 * r, LAYER * (i + 1))))
	return box


## Angular speed of the last active arbor follows the beat: 1/60 turn per beat.
func _process(delta: float) -> void:
	if eco == null:
		return
	for i in arbors.size():
		arbors[i].position = arbors[i].position.lerp(_target_pos[i], 1.0 - exp(-6.0 * delta))
	var last := 0
	var prod := 1.0
	for i in eco.levels.size():
		if eco.levels[i] > 0:
			last = i
	for i in last:
		prod *= eco.ratio(i)
	var w_last := eco.beat_rate() * TAU / 60.0
	_theta0 = fmod(_theta0 + w_last / prod * delta, WRAP)
	# propagate: arbor i+1 turns opposite, r_i times faster; phase c_i keeps teeth meshed
	var theta := _theta0
	for i in last + 1:
		if i > 0:
			var r := eco.ratio(i - 1)
			var step_w := TAU / eco.teeth(i - 1)
			var step_p := TAU / PINION
			var phi: float = _zig[(i - 1) % 2]
			var c := phi + PI - 0.25 * step_p + r * (phi - 0.75 * step_w)
			theta = c - r * theta
		arbors[i].rotation.z = fmod(theta, TAU)
