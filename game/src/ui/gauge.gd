class_name Gauge
extends Control
## Enamel dial with a blued-steel needle (Art Bible §8). Drawn in code: crisp at any scale.
## value/zone are fractions of the dial range (0..1). The needle eases toward its target.

var value := 0.0
var zone := Vector2(-1, -1)        ## ideal band (dark green), fractions; x < 0 disables
var accent := 0.0                  ## blued arc along the rim (e.g. remontoir charge), 0..1
var caption := ""
var font: Font
var _shown := 0.0
const SWEEP := 240.0               ## degrees of the scale
const BRASS := Color(0.86, 0.70, 0.40)
const ENAMEL := Color(0.93, 0.90, 0.82)
const INK := Color(0.16, 0.12, 0.09)
const BLUED := Color(0.17, 0.25, 0.42)


func _process(delta: float) -> void:
	_shown = lerpf(_shown, clampf(value, 0.0, 1.0), 1.0 - exp(-6.0 * delta))
	queue_redraw()


func _ang(f: float) -> float:
	return deg_to_rad(90.0 + (360.0 - SWEEP) * 0.5 + SWEEP * f)


func _draw() -> void:
	var c := size * 0.5 - Vector2(0, 6)
	var r := minf(size.x, size.y - 12) * 0.5
	draw_circle(c + Vector2(2, 3), r, Color(0, 0, 0, 0.45))                     # drop shadow on the panel
	draw_circle(c, r, BRASS.darkened(0.35))
	draw_circle(c, r * 0.95, BRASS)
	draw_arc(c, r * 0.95, PI * 1.1, PI * 1.6, 24, BRASS.lightened(0.35), 2.0, true)   # rim highlight
	draw_circle(c, r * 0.84, ENAMEL)
	draw_arc(c, r * 0.84, 0, TAU, 48, ENAMEL.darkened(0.25), 1.5, true)
	if zone.x >= 0.0:
		draw_arc(c, r * 0.70, _ang(zone.x), _ang(zone.y), 24, Color(0.18, 0.36, 0.24, 0.85), r * 0.09, true)
	if accent > 0.0:
		draw_arc(c, r * 0.89, _ang(0.0), _ang(clampf(accent, 0.0, 1.0)), 32, BLUED.lightened(0.2), r * 0.06, true)
	for i in 13:
		var a := _ang(i / 12.0); var dir := Vector2(cos(a), sin(a))
		var l := 0.14 if i % 3 == 0 else 0.08
		draw_line(c + dir * r * (0.80 - l), c + dir * r * 0.80, INK, 2.0 if i % 3 == 0 else 1.0, true)
	if font and caption != "":
		var fs := int(r * 0.26)
		var w := font.get_string_size(caption, HORIZONTAL_ALIGNMENT_CENTER, -1, fs).x
		draw_string(font, c + Vector2(-w * 0.5, r * 0.45), caption, HORIZONTAL_ALIGNMENT_CENTER, -1, fs, INK)
	var a := _ang(_shown); var d := Vector2(cos(a), sin(a)); var n := Vector2(-d.y, d.x)
	var tip := c + d * r * 0.74; var tail := c - d * r * 0.16
	draw_colored_polygon(PackedVector2Array([tail + n * 2.5, tip, tail - n * 2.5]), BLUED)
	draw_circle(c, r * 0.08, BLUED.darkened(0.3))
	draw_circle(c + Vector2(-1, -1), r * 0.03, BLUED.lightened(0.5))
