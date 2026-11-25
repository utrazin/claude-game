extends Node3D
var w1; var w2
func brass(tint:Color, rough:float)->StandardMaterial3D:
	var m=StandardMaterial3D.new(); m.albedo_color=tint; m.metallic=1.0; m.roughness=rough
	m.anisotropy_enabled=true; m.anisotropy=0.4
	return m
func _ready():
	var env=Environment.new()
	var sky=Sky.new(); var ps=ProceduralSkyMaterial.new()
	ps.sky_top_color=Color(0.05,0.06,0.1); ps.sky_horizon_color=Color(0.35,0.22,0.12)
	ps.ground_bottom_color=Color(0.02,0.015,0.01); ps.ground_horizon_color=Color(0.25,0.15,0.08)
	sky.sky_material=ps; env.sky=sky; env.background_mode=Environment.BG_COLOR; env.background_color=Color(0.02,0.018,0.02)
	env.ambient_light_source=Environment.AMBIENT_SOURCE_SKY; env.reflected_light_source=Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode=Environment.TONE_MAPPER_AGX; env.ssao_enabled=true; env.glow_enabled=true; env.glow_intensity=0.4
	env.ssr_enabled=true
	var we=WorldEnvironment.new(); we.environment=env; add_child(we)
	var c=Camera3D.new(); add_child(c); c.fov=30; c.position=Vector3(0.05,0.32,0.38); c.look_at(Vector3(0.05,0,0))
	var key=SpotLight3D.new(); add_child(key); key.position=Vector3(-0.3,0.5,0.25); key.look_at(Vector3(0.05,0,0))
	key.light_color=Color(1.0,0.78,0.5); key.light_energy=18; key.spot_range=2; key.spot_angle=35; key.shadow_enabled=true
	var rim=OmniLight3D.new(); add_child(rim); rim.position=Vector3(0.35,0.12,-0.3); rim.light_color=Color(0.5,0.65,1.0); rim.light_energy=2.5; rim.omni_range=2
	var plate=MeshInstance3D.new(); var bm=BoxMesh.new(); bm.size=Vector3(1,0.02,1); plate.mesh=bm; plate.position.y=-0.02
	var pm=StandardMaterial3D.new(); pm.albedo_color=Color(0.12,0.06,0.035); pm.roughness=0.55; plate.material_override=pm; add_child(plate)
	w1=load("res://wheel60.glb").instantiate(); add_child(w1)
	w2=load("res://pinion10.glb").instantiate(); add_child(w2); w2.position=Vector3(0.14,0.004,0)
	_mat(w1, brass(Color(0.85,0.62,0.3),0.3)); _mat(w2, brass(Color(0.75,0.74,0.72),0.22))
	await get_tree().create_timer(1.0).timeout
	get_viewport().get_texture().get_image().save_png("/tmp/look/shot.png"); get_tree().quit()
func _mat(n,m):
	for ch in n.find_children("*","MeshInstance3D",true,false): ch.material_override=m
func _process(d):
	if w1: w1.rotate_y(d*0.2); w2.rotate_y(-d*1.2)
