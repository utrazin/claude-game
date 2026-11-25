class_name SkyChart
extends Node3D
## The dome is the upgrade tree (pillar "the world is the dial"). Each star of the first
## constellation, "The Key" (Clavis), is a purchasable node; lit stars are joined by gold lines.
## A star can be lit only if it is adjacent to an already lit star (or is the root).

const DOME_R := 6.3
## (azimuth°, elevation°) of each star, original constellation shaped like a winding key.
const STARS := [[-20, 58], [-8, 63], [6, 61], [14, 54], [-2, 70], [-14, 74], [20, 67]]
const EDGES := [[0, 1], [1, 2], [2, 3], [1, 4], [4, 5], [2, 6]]

var eco: Economy
var base_y := 5.5
var nodes: Array[MeshInstance3D] = []
var lines: Array[MeshInstance3D] = []
var _lit_m: StandardMaterial3D
var _dim_m: StandardMaterial3D
var _avail_m: StandardMaterial3D
var _line_m: StandardMaterial3D


func setup(e: Economy, y: float) -> void:
	eco = e; base_y = y
	_lit_m = _emit(Color(1.0, 0.86, 0.55), 9.0)
	_avail_m = _emit(Color(0.7, 0.78, 1.0), 2.5)
	_dim_m = _emit(Color(0.4, 0.45, 0.6), 0.4)
	_line_m = _emit(Color(0.95, 0.75, 0.4), 2.2)
	for i in STARS.size():
		var mi := MeshInstance3D.new(); var sm := SphereMesh.new(); sm.radius = 0.045; sm.height = 0.09
		mi.mesh = sm; mi.position = _pos(i); add_child(mi); nodes.append(mi)
		var area := Area3D.new(); var cs := CollisionShape3D.new(); var sp := SphereShape3D.new(); sp.radius = 0.35
		cs.shape = sp; area.add_child(cs); mi.add_child(area)
		area.input_event.connect(_on_star_input.bind(i))
	for ed in EDGES:
		var a := _pos(ed[0]); var b := _pos(ed[1])
		var ln := MeshInstance3D.new(); var bx := BoxMesh.new(); bx.size = Vector3(0.018, 0.018, a.distance_to(b) - 0.2)
		ln.mesh = bx; ln.material_override = _line_m; add_child(ln)
		ln.look_at_from_position((a + b) * 0.5, b, Vector3.UP); lines.append(ln)
	eco.changed.connect(refresh)
	refresh()


func _emit(c: Color, energy: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new(); m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = c * energy * 0.25
	m.emission_enabled = true; m.emission = c; m.emission_energy_multiplier = energy
	return m


func _pos(i: int) -> Vector3:
	var az := deg_to_rad(STARS[i][0]); var el := deg_to_rad(STARS[i][1])
	return Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el)) * DOME_R + Vector3(0, base_y, 0)


## Star i is "lit" if i < eco.stars mapped through a deterministic unlock order (tree walk).
func order() -> Array:
	return [0, 1, 2, 4, 3, 5, 6]


func lit(i: int) -> bool:
	var size: int = eco.bal.stars.constellation_size
	return order().find(i) < eco.stars % (size + 1) or eco.stars >= size


func next_star() -> int:
	return order()[eco.stars] if eco.stars < STARS.size() else -1


func refresh() -> void:
	var nxt := next_star()
	var can: bool = eco.star_option().available
	for i in nodes.size():
		var m := _dim_m
		if lit(i): m = _lit_m
		elif i == nxt and can: m = _avail_m
		nodes[i].material_override = m
		nodes[i].scale = Vector3.ONE * (1.6 if lit(i) else (1.25 if i == nxt and can else 0.8))
	for k in EDGES.size():
		lines[k].visible = lit(EDGES[k][0]) and lit(EDGES[k][1])


func _on_star_input(_cam: Node, event: InputEvent, _pos3: Vector3, _n: Vector3, _shape: int, i: int) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		if i == next_star():
			eco.buy(eco.star_option())


func _process(_d: float) -> void:
	var t := Time.get_ticks_msec() * 0.001
	var nxt := next_star()
	if nxt >= 0 and nxt < nodes.size() and not lit(nxt):
		nodes[nxt].scale = Vector3.ONE * (1.15 + 0.15 * sin(t * 3.0))
