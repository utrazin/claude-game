class_name SkyChart
extends Node3D
## The dome is the upgrade tree (pillar "the world is the dial"), D16 / CRIT-01 F4-F5.
## Constellations live in regions of the dome; a region opens with an orbit (Moon → Clavis,
## Mercury → Rota) or with the first Great Year (Ventus). Stars have magnitudes (bright = costly,
## strong); a star can be lit only from a lit neighbour or the root. The sky persists across
## Great Years. Click a pulsing star to light it.

const DOME_R := 6.3

var eco: Economy
var focus := 0.0   ## 0..1 during the observatory shot: lines and stars brighten
var base_y := 5.5
var stars := {}    ## "cid:i" -> MeshInstance3D
var lines := []    ## [cid, a, b, MeshInstance3D]
var groups := {}   ## cid -> Node3D (hidden while the region is closed)
var _lit_m: StandardMaterial3D
var _dim_m: StandardMaterial3D
var _avail_m: StandardMaterial3D
var _line_m: StandardMaterial3D


func setup(e: Economy, y: float) -> void:
	eco = e; base_y = y
	_lit_m = _emit(Color(1.0, 0.86, 0.55), 9.0)
	_avail_m = _emit(Color(0.7, 0.78, 1.0), 3.5)
	_dim_m = _emit(Color(0.6, 0.68, 0.95), 3.0)
	_line_m = _emit(Color(0.95, 0.75, 0.4), 2.2)
	for c in eco.bal.sky.constellations:
		var g := Node3D.new(); g.name = c.id; add_child(g); groups[c.id] = g
		for i in c.stars.size():
			var key := "%s:%d" % [c.id, i]
			var mi := MeshInstance3D.new(); var sm := SphereMesh.new()
			var r := 0.06 - 0.012 * (int(c.stars[i][2]) - 1)          # magnitude → size
			sm.radius = r; sm.height = r * 2.0
			mi.mesh = sm; mi.position = _pos(c.stars[i]); g.add_child(mi); stars[key] = mi
			var area := Area3D.new(); var cs := CollisionShape3D.new(); var sp := SphereShape3D.new(); sp.radius = 0.35
			cs.shape = sp; area.add_child(cs); mi.add_child(area)
			area.input_event.connect(_on_star_input.bind(c.id, i))
		for ed in c.edges:
			var a := _pos(c.stars[ed[0]]); var b := _pos(c.stars[ed[1]])
			var ln := MeshInstance3D.new(); var bx := BoxMesh.new(); bx.size = Vector3(0.018, 0.018, a.distance_to(b) - 0.2)
			ln.mesh = bx; ln.material_override = _line_m; g.add_child(ln)
			ln.look_at_from_position((a + b) * 0.5, b, Vector3.UP); lines.append([c.id, ed[0], ed[1], ln])
	eco.changed.connect(refresh)
	eco.purchased.connect(func(_k, _i): refresh())
	refresh()


func _emit(c: Color, energy: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new(); m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = c * energy * 0.25
	m.emission_enabled = true; m.emission = c; m.emission_energy_multiplier = energy
	return m


func _pos(st: Array) -> Vector3:
	var az := deg_to_rad(float(st[0])); var el := deg_to_rad(float(st[1]))
	return Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el)) * DOME_R + Vector3(0, base_y, 0)


## Centre of the constellation the player should look at now (first open and incomplete).
func centre() -> Vector3:
	var target: Dictionary = eco.bal.sky.constellations[0]
	for c in eco.bal.sky.constellations:
		if eco.gate_open(c) and not eco.complete(c.id):
			target = c; break
	var p := Vector3.ZERO
	for st in target.stars: p += _pos(st)
	return p / target.stars.size()


func refresh() -> void:
	for c in eco.bal.sky.constellations:
		var any_lit := false
		for k in eco.lit: if k.begins_with(c.id + ":"): any_lit = true
		groups[c.id].visible = eco.gate_open(c) or any_lit     # a lit sky stays visible after a Great Year
	for key in stars:
		var p: PackedStringArray = key.split(":")
		var mi: MeshInstance3D = stars[key]
		var on: bool = key in eco.lit
		var o := eco.star_option_at(p[0], int(p[1]))
		var can: bool = o.available and eco.starlight >= o.cost
		mi.material_override = _lit_m if on else (_avail_m if o.available else _dim_m)
		mi.set_meta("pulse", can)
		mi.scale = Vector3.ONE * (1.6 if on else (1.2 if o.available else 0.8))
	for l in lines:
		(l[3] as MeshInstance3D).visible = ("%s:%d" % [l[0], l[1]]) in eco.lit and ("%s:%d" % [l[0], l[2]]) in eco.lit


func _on_star_input(_cam: Node, event: InputEvent, _pos3: Vector3, _n: Vector3, _shape: int, cid: String, i: int) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index == MOUSE_BUTTON_LEFT:
		eco.buy(eco.star_option_at(cid, i))


var _t_refresh := 0.0

func _process(d: float) -> void:
	var t := Time.get_ticks_msec() * 0.001
	if _line_m: _line_m.emission_energy_multiplier = 2.2 * (1.0 + 1.5 * focus)
	_t_refresh += d
	if _t_refresh > 0.5:            # starlight accrues continuously: re-check which stars are affordable
		_t_refresh = 0.0; refresh()
	for key in stars:
		var mi: MeshInstance3D = stars[key]
		if mi.get_meta("pulse", false):
			mi.scale = Vector3.ONE * (1.15 + 0.2 * sin(t * 3.0))
