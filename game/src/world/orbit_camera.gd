class_name OrbitCamera
extends Camera3D
## Calm orbit camera: drag to orbit, wheel to zoom, smooth auto-framing on the mechanism.

var target := Vector3.ZERO
var yaw := deg_to_rad(-18.0)
var pitch := deg_to_rad(4.0)
var distance := 3.0
var _t_target := Vector3.ZERO
var _t_distance := 3.0
var _dragging := false
var _pitch_vis := deg_to_rad(4.0)
var min_distance := 2.5
var max_distance := 14.0
var auto_frame := true
var _looking_up := false
var _saved := {}


## Toggle the "look at the sky" framing (P3 in the GDD).
func look_up(up: bool) -> void:
	if up == _looking_up:
		return
	_looking_up = up
	if up:
		_saved = {"t": _t_target, "d": _t_distance, "p": pitch, "y": yaw}
		_t_target = Vector3(0, 9.6, -2.5); _t_distance = 6.5
		pitch = deg_to_rad(-55.0); yaw = 0.0
		auto_frame = false
	else:
		_t_target = _saved.t; _t_distance = _saved.d; pitch = _saved.p; yaw = _saved.y
		auto_frame = true


func frame(box: AABB) -> void:
	if not auto_frame:
		return
	_t_target = box.get_center() + Vector3(0, box.size.y * 0.22, 0)
	var radius := maxf(box.size.length() * 0.5, 0.6)
	_t_distance = clampf(radius / tan(deg_to_rad(fov * 0.5)) * 1.15, min_distance, max_distance)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_RIGHT or mb.button_index == MOUSE_BUTTON_MIDDLE:
			_dragging = mb.pressed
		elif mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_UP:
			_t_distance = maxf(min_distance, _t_distance * 0.9)
		elif mb.pressed and mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			_t_distance = minf(max_distance, _t_distance * 1.1)
	elif event is InputEventMouseMotion and _dragging:
		var mm := event as InputEventMouseMotion
		yaw -= mm.relative.x * 0.005
		pitch = clampf(pitch + mm.relative.y * 0.004, deg_to_rad(-70), deg_to_rad(60))


func _process(delta: float) -> void:
	var k := 1.0 - exp(-3.0 * delta)
	target = target.lerp(_t_target, k)
	distance = lerpf(distance, _t_distance, k)
	var p := lerp_angle(_pitch_vis, pitch, k); _pitch_vis = p
	var dir := Vector3(sin(yaw) * cos(p), sin(p), cos(yaw) * cos(p))
	global_position = target + dir * distance
	look_at(target, Vector3.UP)


func snap() -> void:
	target = _t_target; distance = _t_distance
	_process(0.0)
