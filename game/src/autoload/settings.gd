extends Node
## Player settings (graphics quality, volumes). Persisted in user://settings.cfg.
## Quality defaults by GPU type: integrated → LOW, otherwise HIGH.
## Hotkeys until the options menu exists: F3 shows FPS, F10 cycles graphics quality.

signal changed

enum Quality { LOW, MEDIUM, HIGH }
const PATH := "user://settings.cfg"
const NAMES := ["GFX_LOW", "GFX_MEDIUM", "GFX_HIGH"]

var quality: int = Quality.HIGH
var show_fps := false
var volumes := {"Master": 0.9, "SFX": 0.8, "Music": 0.6, "Ambience": 0.7}   ## linear 0..1
var locale := ""


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	var cfg := ConfigFile.new()
	if cfg.load(PATH) == OK and cfg.has_section_key("graphics", "quality"):
		quality = clampi(int(cfg.get_value("graphics", "quality")), 0, 2)
	else:
		quality = default_quality()
	for b in volumes:
		volumes[b] = clampf(float(cfg.get_value("audio", b, volumes[b])), 0.0, 1.0)
	show_fps = bool(cfg.get_value("graphics", "show_fps", false))
	locale = str(cfg.get_value("general", "locale", ""))
	if locale == "":
		locale = "pt_BR" if OS.get_locale_language() == "pt" else "en"
	TranslationServer.set_locale(locale)
	apply_viewport()
	apply_audio.call_deferred()


func save() -> void:
	var cfg := ConfigFile.new(); cfg.load(PATH)
	cfg.set_value("graphics", "quality", quality); cfg.set_value("graphics", "show_fps", show_fps)
	for b in volumes: cfg.set_value("audio", b, volumes[b])
	cfg.set_value("general", "locale", locale)
	cfg.save(PATH)


func apply_audio() -> void:
	for b in volumes:
		var i := AudioServer.get_bus_index(b)
		if i >= 0:
			AudioServer.set_bus_volume_db(i, linear_to_db(maxf(volumes[b], 0.0001)))
			AudioServer.set_bus_mute(i, volumes[b] <= 0.001)


func set_volume(bus: String, v: float) -> void:
	volumes[bus] = clampf(v, 0.0, 1.0); apply_audio(); save()


func set_locale(l: String) -> void:
	locale = l; TranslationServer.set_locale(l); save(); changed.emit()


func set_show_fps(on: bool) -> void:
	show_fps = on; save(); changed.emit()


func default_quality() -> int:
	var t := RenderingServer.get_video_adapter_type()
	if t == RenderingDevice.DEVICE_TYPE_INTEGRATED_GPU or t == RenderingDevice.DEVICE_TYPE_CPU:
		return Quality.LOW
	return Quality.HIGH


func set_quality(q: int) -> void:
	quality = clampi(q, 0, 2)
	save()
	apply_viewport()
	changed.emit()


func apply_viewport() -> void:
	var vp := get_viewport()
	match quality:
		Quality.LOW:
			vp.msaa_3d = Viewport.MSAA_DISABLED
			vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA
			vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR
			vp.scaling_3d_scale = 0.67
			RenderingServer.positional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_VERY_LOW)
			RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_VERY_LOW)
		Quality.MEDIUM:
			vp.msaa_3d = Viewport.MSAA_DISABLED
			vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_FXAA
			vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR
			vp.scaling_3d_scale = 0.85
			RenderingServer.positional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_LOW)
			RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_LOW)
		_:
			vp.msaa_3d = Viewport.MSAA_2X
			vp.screen_space_aa = Viewport.SCREEN_SPACE_AA_DISABLED
			vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
			vp.scaling_3d_scale = 1.0
			RenderingServer.positional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_HIGH)
			RenderingServer.directional_soft_shadow_filter_set_quality(RenderingServer.SHADOW_QUALITY_SOFT_HIGH)


## Environment/light settings that depend on quality (called by the world on build and on change).
func apply_environment(env: Environment) -> void:
	env.ssil_enabled = quality == Quality.HIGH
	env.ssao_enabled = quality != Quality.LOW
	env.glow_enabled = true
	# The sky twinkles (TIME), so its radiance re-bakes continuously: only HIGH pays for that.
	if quality == Quality.HIGH:
		env.sky.process_mode = Sky.PROCESS_MODE_INCREMENTAL
		env.sky.radiance_size = Sky.RADIANCE_SIZE_64
		env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
		env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	else:
		env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
		env.reflected_light_source = Environment.REFLECTION_SOURCE_DISABLED
	env.fog_enabled = quality != Quality.LOW
	RenderingServer.environment_set_ssao_quality(
		RenderingServer.ENV_SSAO_QUALITY_LOW if quality == Quality.MEDIUM else RenderingServer.ENV_SSAO_QUALITY_MEDIUM,
		quality == Quality.MEDIUM, 0.5, 2, 50, 300)


func shadows_for(light: Light3D, essential: bool) -> void:
	light.shadow_enabled = essential or quality == Quality.HIGH


func _unhandled_key_input(event: InputEvent) -> void:
	var k := event as InputEventKey
	if k == null or not k.pressed or k.echo: return
	if k.keycode == KEY_F3:
		set_show_fps(not show_fps)
	elif k.keycode == KEY_F10:
		set_quality((quality + 1) % 3)
