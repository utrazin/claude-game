class_name Complications
extends Node3D
## Visual side of the complications: hour dial, the Moon and Mercury on an orrery post.
## Each appears with a rise animation when built; the sky wakes up accordingly.

var eco: Economy
var mech: Mechanism
var dial: Node3D
var hand_min: Node3D
var hand_hour: Node3D
var orrery: Node3D
var bodies := {}             ## id -> {arm: Node3D, speed: float}


func setup(e: Economy, m: Mechanism) -> void:
	eco = e; mech = m
	_build_dial(); _build_orrery()
	eco.purchased.connect(_on_purchase)
	_sync(true)


func _on_purchase(kind: String, id: String) -> void:
	if kind == "build" or kind == "load":
		_sync(false)


func _sync(instant: bool) -> void:
	_reveal(dial, eco.comps.get("hour_dial", 0) > 0, instant)
	_reveal(orrery, eco.comps.get("moon", 0) > 0, instant)
	for id in bodies:
		_reveal(bodies[id].arm, eco.comps.get(id, 0) > 0, instant)


func _reveal(n: Node3D, on: bool, instant: bool) -> void:
	if on == n.visible:
		return
	n.visible = on
	if on and not instant:
		n.scale = Vector3.ONE * 0.01
		create_tween().set_trans(Tween.TRANS_ELASTIC).set_ease(Tween.EASE_OUT).tween_property(n, "scale", Vector3.ONE, 1.6)
	else:
		n.scale = Vector3.ONE


func _cyl(r_top: float, r_bot: float, h: float, mat: Material, seg := 48) -> MeshInstance3D:
	var mi := MeshInstance3D.new(); var c := CylinderMesh.new()
	c.top_radius = r_top; c.bottom_radius = r_bot; c.height = h; c.radial_segments = seg
	mi.mesh = c; mi.material_override = mat
	return mi


func _build_dial() -> void:
	dial = Node3D.new(); dial.name = "HourDial"; add_child(dial)
	var face := _cyl(0.42, 0.42, 0.03, Mats.enamel(), 96); face.rotation.x = PI / 2; dial.add_child(face)
	var ring := MeshInstance3D.new(); var t := TorusMesh.new(); t.inner_radius = 0.41; t.outer_radius = 0.48; t.rings = 96; t.ring_segments = 16
	ring.mesh = t; ring.rotation.x = PI / 2; ring.material_override = Mats.brass(); dial.add_child(ring)
	for k in 60:
		var major := k % 5 == 0
		var mk := MeshInstance3D.new(); var b := BoxMesh.new()
		b.size = Vector3(0.012 if not major else 0.022, 0.03 if not major else 0.075, 0.006)
		mk.mesh = b; mk.material_override = Mats.blued_steel() if major else Mats.lead()
		var a := TAU * k / 60.0
		var rr := 0.37 if not major else 0.345
		mk.position = Vector3(sin(a) * rr, cos(a) * rr, 0.02); mk.rotation.z = -a; dial.add_child(mk)
	hand_hour = _hand(0.22, 0.03); hand_hour.position.z = 0.03; dial.add_child(hand_hour)
	hand_min = _hand(0.34, 0.02); hand_min.position.z = 0.04; dial.add_child(hand_min)
	var boss := _cyl(0.03, 0.03, 0.04, Mats.brass(), 32); boss.rotation.x = PI / 2; boss.position.z = 0.05; dial.add_child(boss)
	var post := _cyl(0.035, 0.05, 1.0, Mats.brass_aged(), 32); post.name = "Post"; post.position.z = -0.08; dial.add_child(post)


func _hand(length: float, width: float) -> Node3D:
	var n := Node3D.new()
	var mi := MeshInstance3D.new(); var b := BoxMesh.new(); b.size = Vector3(width, length, 0.006)
	mi.mesh = b; mi.position.y = length * 0.42; mi.material_override = Mats.blued_steel(); n.add_child(mi)
	var tip := MeshInstance3D.new(); var p := PrismMesh.new(); p.size = Vector3(width * 2.0, width * 2.5, 0.006)
	tip.mesh = p; tip.position.y = length * 0.92; tip.material_override = Mats.blued_steel(); n.add_child(tip)
	return n


func _build_orrery() -> void:
	orrery = Node3D.new(); orrery.name = "Orrery"; add_child(orrery)
	var post := _cyl(0.04, 0.08, 1.6, Mats.brass_aged(), 40); post.position.y = 0.8; orrery.add_child(post)
	var cap := MeshInstance3D.new(); var s := SphereMesh.new(); s.radius = 0.07; s.height = 0.14
	cap.mesh = s; cap.position.y = 1.62; cap.material_override = Mats.brass(); orrery.add_child(cap)
	_body("moon", 1.5, 0.22, _silver(), 1.25, 0.09)
	_body("mercury", 0.9, 0.13, _amber(), 1.45, 0.23)


func _silver() -> StandardMaterial3D:
	var m := StandardMaterial3D.new(); m.albedo_color = Color(0.82, 0.83, 0.86); m.metallic = 1.0; m.roughness = 0.35
	return m


func _amber() -> StandardMaterial3D:
	var m := StandardMaterial3D.new(); m.albedo_color = Color(0.85, 0.45, 0.12); m.roughness = 0.15
	m.subsurf_scatter_enabled = true; m.subsurf_scatter_strength = 0.6; m.clearcoat_enabled = true
	return m


func _body(id: String, radius: float, size: float, mat: Material, height: float, speed: float) -> void:
	var arm := Node3D.new(); arm.name = id; arm.position.y = height; orrery.add_child(arm)
	var rod := MeshInstance3D.new(); var b := CylinderMesh.new(); b.top_radius = 0.008; b.bottom_radius = 0.008; b.height = radius
	rod.mesh = b; rod.rotation.z = PI / 2; rod.position.x = radius * 0.5; rod.material_override = Mats.brass(); arm.add_child(rod)
	var drop := _cyl(0.008, 0.008, 0.18, Mats.brass(), 16); drop.position = Vector3(radius, 0.09, 0); arm.add_child(drop)
	var ball := MeshInstance3D.new(); var sm := SphereMesh.new(); sm.radius = size; sm.height = size * 2; sm.radial_segments = 64; sm.rings = 32
	ball.mesh = sm; ball.position = Vector3(radius, 0.18 + size, 0); ball.material_override = mat; arm.add_child(ball)
	var collar := MeshInstance3D.new(); var tm := TorusMesh.new(); tm.inner_radius = size * 1.02; tm.outer_radius = size * 1.12; tm.rings = 64
	collar.mesh = tm; collar.position = ball.position; collar.rotation.x = 0.3; collar.material_override = Mats.brass(); arm.add_child(collar)
	bodies[id] = {"arm": arm, "speed": speed}


func _process(delta: float) -> void:
	if mech == null or mech.arbors.is_empty():
		return
	# place the dial above the right end of the train, the orrery behind the great wheel
	var right := mech.train_extent()
	dial.position = mech.position + Vector3(right - 0.1, mech.axle_height + 0.95, 0.35)
	var post := dial.get_node("Post") as MeshInstance3D
	var ph := dial.position.y - mech.position.y
	post.scale.y = ph; post.position.y = -ph * 0.5
	orrery.position = mech.position + Vector3(right * 0.35, mech.axle_height + 0.25, -0.45)
	# the centre wheel turns once per "hour": minute hand follows arbor 1, hour hand 1/12
	if mech.spins.size() > 1 and eco.levels[1] > 0:
		var a := -mech.spins[1].rotation.z
		hand_min.rotation.z = a
		hand_hour.rotation.z = a / 12.0
	else:
		hand_min.rotation.z -= delta * 0.05; hand_hour.rotation.z -= delta * 0.004
	var rate := clampf(log(1.0 + eco.beat_rate()) / 12.0, 0.05, 1.0)
	for id in bodies:
		var b: Dictionary = bodies[id]
		(b.arm as Node3D).rotation.y += delta * b.speed * rate


## 0..1 how much of the firmament is awake (drives the sky shader).
func awake() -> float:
	var a := 0.06
	if eco.comps.get("hour_dial", 0) > 0: a += 0.06
	if eco.comps.get("moon", 0) > 0: a += 0.12
	if eco.comps.get("mercury", 0) > 0: a += 0.12
	a += 0.64 * clampf(float(eco.stars) / float(eco.bal.stars.constellation_size), 0.0, 1.0)
	return clampf(a, 0.0, 1.0)
