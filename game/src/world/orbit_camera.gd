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

## --- Observatory shot ("look at the sky"): an authored crane move, not an orbit lerp.
## The camera leaves the bench, rises along the tower axis while leaning back like an
## astronomer, with a slight roll at mid-move; then it drifts slowly with the sky.
signal sky_shot(progress: float)          ## 0 = at the bench, 1 = under the dome
var sky_focus := Vector3(0, 7.5, -3.0)    ## constellation centre (set by the world)
var sky_eye := Vector3(0.0, 1.55, 1.6)    ## where the astronomer stands
var sky_blend := 0.0
var base_fov := 38.0
var _sky_tween: Tween
var _drift := 0.0
var _look_dx := 0.0
var _look_dy := 0.0
const SKY_IN := 2.8
const SKY_OUT := 2.2


## Toggle the "look at the sky" shot (P3 in the GDD).
func look_up(up: bool) -> void:
	if up == _looking_up:
		return
	_looking_up = up
	if _sky_tween: _sky_tween.kill()
	_sky_tween = create_tween().set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	_sky_tween.tween_method(_set_blend, sky_blend, 1.0 if up else 0.0, (SKY_IN if up else SKY_OUT) * absf((1.0 if up else 0.0) - sky_blend))
	if not up:
		_look_dx = 0.0; _look_dy = 0.0


func _set_blend(v: float) -> void:
	sky_blend = v
	sky_shot.emit(v)


func is_looking_up() -> bool: return _looking_up


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
	elif event is InputEventMouseMotion and _dragging and _looking_up:
		var mm := event as InputEventMouseMotion
		_look_dx = clampf(_look_dx - mm.relative.x * 0.002, -0.6, 0.6)
		_look_dy = clampf(_look_dy + mm.relative.y * 0.002, -0.35, 0.35)
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
	var orbit_pos := target + dir * distance
	if sky_blend <= 0.0001:
		global_position = orbit_pos
		look_at(target, Vector3.UP)
		fov = base_fov
		return
	# orbit pose
	var t_orbit := Transform3D(Basis(), orbit_pos).looking_at(target, Vector3.UP)
	# sky pose: drifts like the sky turning, plus the player's gentle look-around
	_drift += delta * 0.012
	var focus := sky_focus
	var rel := (focus - sky_eye).rotated(Vector3.UP, sin(_drift) * 0.08 + _look_dx)
	rel.y += _look_dy * rel.length()
	var t_sky := Transform3D(Basis(), sky_eye).looking_at(sky_eye + rel, Vector3.UP)
	# crane path: quadratic arc through a raised point between the two poses
	var b := sky_blend
	var mid := (orbit_pos + sky_eye) * 0.5 + Vector3(0, 0.9, 0.6)
	var p0 := orbit_pos.lerp(mid, b); var p1 := mid.lerp(sky_eye, b)
	global_position = p0.lerp(p1, b)
	# orientation: rotation lags the move slightly (head follows body), with a breath of roll
	var rb := smoothstep(0.15, 1.0, b)
	var q := t_orbit.basis.get_rotation_quaternion().slerp(t_sky.basis.get_rotation_quaternion(), rb)
	var roll := sin(b * PI) * deg_to_rad(5.0)
	global_basis = Basis(q) * Basis(Vector3.FORWARD, roll)
	fov = lerpf(base_fov, 32.0, smoothstep(0.3, 1.0, b))   # telescope-like narrowing


func snap() -> void:
	target = _t_target; distance = _t_distance
	_process(0.0)
