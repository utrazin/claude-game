extends Node3D
## The single scene of the game: the top chamber of the observatory tower.
## PROTOTYPE: room geometry is placeholder (marked [PH]); mechanism, crank and lighting are real systems.

var eco: Economy
var mech: Mechanism
var cam: OrbitCamera
var crank: Node3D
var weight: Node3D
var room: Room
var sky_mat: ShaderMaterial
var _crank_spin := 0.0
var _hold := 0.0
var _holding := false


func _ready() -> void:
	eco = Game.eco
	_build_environment()
	_build_room()
	mech = Mechanism.new(); mech.name = "Mechanism"; add_child(mech)
	mech.position = Vector3(-1.2, 0.42, 0.0)
	cam = OrbitCamera.new(); cam.fov = 38.0; add_child(cam); cam.current = true
	mech.layout_changed.connect(_fit_room)
	mech.setup(eco)
	cam.snap()
	_build_crank()
	_build_weight()
	var hud := preload("res://src/ui/hud.gd").new(); hud.name = "HUD"; add_child(hud)
	hud.wind_pressed.connect(_on_wind)
	hud.wind_hold.connect(func(h): _holding = h)


func _build_environment() -> void:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new(); var ps := ShaderMaterial.new(); ps.shader = preload("res://shaders/night_sky.gdshader")
	sky_mat = ps
	sky.sky_material = ps; env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.5
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.1
	env.ssao_enabled = true; env.ssao_radius = 0.6; env.ssao_intensity = 1.6
	env.ssil_enabled = true
	env.glow_enabled = true; env.glow_intensity = 0.25; env.glow_hdr_threshold = 1.4
	env.fog_enabled = true; env.fog_density = 0.012; env.fog_light_color = Color(0.12, 0.1, 0.12)
	env.adjustment_enabled = true; env.adjustment_saturation = 1.05; env.adjustment_contrast = 1.06
	var we := WorldEnvironment.new(); we.environment = env; add_child(we)
	var probe := ReflectionProbe.new(); probe.name = "RoomProbe"; probe.size = Vector3(12, 8, 12)
	probe.position = Vector3(0, 2.5, 0); probe.box_projection = true; probe.interior = true
	probe.update_mode = ReflectionProbe.UPDATE_ONCE; add_child(probe)
	# warm lamp light at bench height (key)
	var key := SpotLight3D.new(); key.name = "LampKey"; add_child(key)
	key.position = Vector3(-2.4, 2.6, 2.4); key.look_at_from_position(key.position, Vector3(0.6, 1.6, 0.0))
	key.light_color = Color(1.0, 0.80, 0.58); key.light_energy = 9.0; key.spot_range = 9.0
	key.spot_angle = 38.0; key.spot_attenuation = 0.8; key.shadow_enabled = true; key.light_size = 0.15
	# cool moonlight from the dome (rim)
	var moon := DirectionalLight3D.new(); moon.name = "Moonlight"; add_child(moon)
	moon.rotation_degrees = Vector3(-62, 160, 0); moon.light_color = Color(0.55, 0.68, 1.0)
	moon.light_energy = 0.55; moon.shadow_enabled = true
	# candle fill near the bench
	var fill := OmniLight3D.new(); fill.name = "Candle"; add_child(fill)
	fill.position = Vector3(1.6, 1.2, 1.4); fill.light_color = Color(1.0, 0.6, 0.3); fill.light_energy = 0.6; fill.omni_range = 4.0


func _build_room() -> void:
	room = Room.new(); room.name = "Room"; add_child(room)


func _fit_room(b: AABB) -> void:
	var wb := AABB(b.position + mech.position, b.size)
	room.fit_plinth(wb.position.x - 0.45, wb.end.x + 0.45, mech.position.z + 0.05, mech.position.y)
	cam.frame(wb.merge(AABB(Vector3(wb.position.x - 0.6, 0.0, 0.0), Vector3(0.1, 0.1, 0.1))))


func _build_crank() -> void:
	crank = Node3D.new(); crank.name = "Crank"
	var arm := MeshInstance3D.new(); var b := BoxMesh.new(); b.size = Vector3(0.36, 0.05, 0.03)
	arm.mesh = b; arm.position.x = 0.15; arm.material_override = Mats.blued_steel(); crank.add_child(arm)
	var knob := MeshInstance3D.new(); var c := CylinderMesh.new(); c.top_radius = 0.035; c.bottom_radius = 0.04; c.height = 0.16
	knob.mesh = c; knob.rotation.x = PI / 2; knob.position = Vector3(0.31, 0, 0.09); knob.material_override = Mats.walnut(); crank.add_child(knob)
	var hub := MeshInstance3D.new(); var h := CylinderMesh.new(); h.top_radius = 0.05; h.bottom_radius = 0.05; h.height = 0.06
	hub.mesh = h; hub.rotation.x = PI / 2; hub.material_override = Mats.brass(); crank.add_child(hub)
	crank.position = mech.position + Vector3(0, 0, 0.12)
	add_child(crank)


func _build_weight() -> void:
	weight = Node3D.new(); weight.name = "Weight"; add_child(weight)
	_refresh_weight()
	eco.purchased.connect(func(k, _i): if k == "drive": _refresh_weight())


func _refresh_weight() -> void:
	for c in weight.get_children(): c.queue_free()
	var discs := 1 + eco.drive
	for d in discs:
		var m := MeshInstance3D.new(); var cy := CylinderMesh.new()
		cy.top_radius = 0.11; cy.bottom_radius = 0.11; cy.height = 0.07; cy.radial_segments = 48
		m.mesh = cy; m.position.y = -d * 0.075; m.material_override = Mats.lead()
		weight.add_child(m)
	var cord := MeshInstance3D.new(); var cc := CylinderMesh.new()
	cc.top_radius = 0.006; cc.bottom_radius = 0.006; cc.height = 0.5
	cord.mesh = cc; cord.position.y = 0.28; cord.material_override = Mats.steel(); weight.add_child(cord)
	weight.position = mech.position + Vector3(-0.55, -0.1, 0.05)


func _on_wind() -> void:
	eco.wind()
	_crank_spin += TAU * 0.25


func _process(delta: float) -> void:
	if _holding:
		_hold += delta
		_crank_spin += delta * TAU * 1.5
		if _hold > 1.5 and eco.overwind_left <= 0.0:
			eco.start_overwind()
	else:
		_hold = 0.0
	var spin := minf(_crank_spin, delta * TAU * 3.0)
	_crank_spin -= spin
	if crank:
		crank.rotation.z -= spin
		crank.position = mech.position + mech.arbors[0].position + Vector3(0, 0, 0.42)
	if weight:
		var r0 := eco.teeth(0) * Mechanism.MODULE * 0.5
		weight.position = mech.position + Vector3(-r0 - 0.95, mech.arbors[0].position.y * 0.55, 0.05)
