class_name Room
extends Node3D
## Tower chamber: stone drum, floor, iron-ribbed glass dome, plinth for the train.
## Procedural textures (NoiseTexture2D) stand in until the texture pass (A-006). [PH-texture]

const RADIUS := 6.5
const WALL_H := 5.5

var plinth: MeshInstance3D
var _plinth_target := 2.0


func _ready() -> void:
	_floor(); _wall(); _dome(); _plinth(); _sconces()


## Oil-lamp sconces around the drum: warm pools of light and bright points for brass to reflect.
func _sconces() -> void:
	var flame_m := StandardMaterial3D.new(); flame_m.emission_enabled = true
	flame_m.emission = Color(1.0, 0.62, 0.28); flame_m.emission_energy_multiplier = 6.0; flame_m.albedo_color = Color(1, 0.8, 0.5)
	var glass_m := StandardMaterial3D.new(); glass_m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	glass_m.albedo_color = Color(1.0, 0.85, 0.65, 0.25); glass_m.roughness = 0.05
	for k in 6:
		var a := TAU * (k + 0.5) / 6.0 + 0.3
		var s := Node3D.new(); s.name = "Sconce%d" % k; add_child(s)
		s.position = Vector3(cos(a) * (RADIUS - 0.25), 2.3, sin(a) * (RADIUS - 0.25))
		var flame := MeshInstance3D.new(); var fs := SphereMesh.new(); fs.radius = 0.035; fs.height = 0.11
		flame.mesh = fs; flame.material_override = flame_m; s.add_child(flame)
		var chimney := MeshInstance3D.new(); var cs := CylinderMesh.new(); cs.top_radius = 0.06; cs.bottom_radius = 0.08; cs.height = 0.28
		chimney.mesh = cs; chimney.material_override = glass_m; chimney.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF; s.add_child(chimney)
		var cup := MeshInstance3D.new(); var cu := CylinderMesh.new(); cu.top_radius = 0.09; cu.bottom_radius = 0.05; cu.height = 0.08
		cup.mesh = cu; cup.position.y = -0.17; cup.material_override = Mats.brass_aged(); s.add_child(cup)
		var l := OmniLight3D.new(); l.light_color = Color(1.0, 0.68, 0.38); l.light_energy = 1.6; l.omni_range = 3.2
		l.omni_attenuation = 1.4; s.add_child(l)


func _noise_tex(freq: float, seed: int, as_normal := false, w := 1024) -> NoiseTexture2D:
	var n := FastNoiseLite.new(); n.seed = seed; n.frequency = freq
	n.fractal_octaves = 5; n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	var t := NoiseTexture2D.new(); t.width = w; t.height = w; t.seamless = true; t.noise = n
	t.as_normal_map = as_normal; t.bump_strength = 6.0
	if not as_normal:
		var g := Gradient.new(); g.set_color(0, Color(0.78, 0.78, 0.78)); g.set_color(1, Color(1, 1, 1))
		t.color_ramp = g
	return t


func _floor() -> void:
	var mi := MeshInstance3D.new(); var pm := PlaneMesh.new(); pm.size = Vector2(RADIUS * 2, RADIUS * 2)
	mi.mesh = pm
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.30, 0.27, 0.24); m.albedo_texture = _noise_tex(0.02, 3)
	m.normal_enabled = true; m.normal_texture = _noise_tex(0.05, 4, true); m.normal_scale = 0.4
	m.roughness = 0.62; m.uv1_scale = Vector3(4, 4, 1)
	mi.material_override = m; add_child(mi)


func _wall() -> void:
	var mi := MeshInstance3D.new(); var cm := CylinderMesh.new()
	cm.top_radius = RADIUS; cm.bottom_radius = RADIUS; cm.height = WALL_H; cm.radial_segments = 128
	cm.cap_top = false; cm.cap_bottom = false; mi.mesh = cm; mi.position.y = WALL_H * 0.5
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.50, 0.48, 0.45); m.albedo_texture = _noise_tex(0.015, 7)
	m.normal_enabled = true; m.normal_texture = _noise_tex(0.03, 8, true); m.normal_scale = 0.3
	m.roughness = 0.92; m.uv1_scale = Vector3(6, 2, 1)
	m.cull_mode = BaseMaterial3D.CULL_FRONT
	mi.material_override = m; add_child(mi)
	# cornice ring where the dome starts
	var ring := MeshInstance3D.new(); var tm := TorusMesh.new()
	tm.inner_radius = RADIUS - 0.25; tm.outer_radius = RADIUS + 0.05; tm.rings = 128; tm.ring_segments = 16
	ring.mesh = tm; ring.position.y = WALL_H; ring.material_override = m; add_child(ring)


func _dome() -> void:
	# glass shell
	var glass := MeshInstance3D.new(); var sm := SphereMesh.new()
	sm.radius = RADIUS; sm.height = RADIUS; sm.is_hemisphere = true; sm.radial_segments = 96; sm.rings = 32
	glass.mesh = sm; glass.position.y = WALL_H
	var gm := StandardMaterial3D.new(); gm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	gm.albedo_color = Color(0.35, 0.45, 0.6, 0.10); gm.roughness = 0.05; gm.metallic = 0.2
	gm.cull_mode = BaseMaterial3D.CULL_DISABLED
	glass.material_override = gm; glass.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(glass)
	# wrought iron meridian ribs and parallels
	var iron := StandardMaterial3D.new(); iron.albedo_color = Color(0.08, 0.08, 0.09); iron.metallic = 0.7; iron.roughness = 0.5
	for k in 16:
		var a := TAU * k / 16.0
		for j in 12:
			var e0 := PI * 0.5 * j / 12.0; var e1 := PI * 0.5 * (j + 1) / 12.0
			var p0 := Vector3(cos(a) * cos(e0), sin(e0), sin(a) * cos(e0)) * (RADIUS - 0.02)
			var p1 := Vector3(cos(a) * cos(e1), sin(e1), sin(a) * cos(e1)) * (RADIUS - 0.02)
			var seg := MeshInstance3D.new(); var b := BoxMesh.new()
			b.size = Vector3(0.07, p0.distance_to(p1) + 0.02, 0.1); seg.mesh = b; seg.material_override = iron
			add_child(seg)
			seg.position = Vector3(0, WALL_H, 0) + (p0 + p1) * 0.5
			seg.look_at_from_position(seg.position, seg.position + (p1 - p0), (p0 + p1).normalized())
			seg.rotate_object_local(Vector3.RIGHT, PI / 2.0)
	for j in [3, 6, 9]:
		var e: float = PI * 0.5 * j / 12.0
		var tor := MeshInstance3D.new(); var tm := TorusMesh.new()
		tm.inner_radius = RADIUS * cos(e) - 0.05; tm.outer_radius = RADIUS * cos(e); tm.rings = 96; tm.ring_segments = 8
		tor.mesh = tm; tor.position.y = WALL_H + RADIUS * sin(e) - 0.03; tor.material_override = iron; add_child(tor)


func _plinth() -> void:
	plinth = MeshInstance3D.new(); plinth.name = "Plinth"
	var bm := BoxMesh.new(); bm.size = Vector3(1, 0.42, 1.1); plinth.mesh = bm
	plinth.material_override = Mats.walnut()
	add_child(plinth)
	var trim := MeshInstance3D.new(); var tb := BoxMesh.new(); tb.size = Vector3(1.0, 0.025, 1.12)
	trim.mesh = tb; trim.position.y = 0.2; trim.material_override = Mats.brass(); plinth.add_child(trim)


## Size the plinth under the train: x0..x1 in world space, top at y_top.
func fit_plinth(x0: float, x1: float, z: float, y_top: float) -> void:
	_plinth_target = maxf(x1 - x0, 1.0)
	plinth.position = Vector3((x0 + x1) * 0.5, y_top - 0.21, z)
	plinth.scale.x = _plinth_target
