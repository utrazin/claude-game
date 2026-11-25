extends CanvasLayer
## PROTOTYPE HUD [PH]. Functional layout and data flow are final-intent; visual skin is placeholder
## until the UI mockup (U-001) is approved. Built in code to iterate quickly.

signal wind_pressed
signal wind_hold(holding: bool)
signal look_up(up: bool)

var eco: Economy
var lbl_ticks: Label
var lbl_rate: Label
var lbl_star: Label
var lbl_eff: Label
var shop: VBoxContainer
var rows := {}          ## key -> {button, name, info}
var _refresh_t := 0.0

const C_PANEL := Color(0.10, 0.065, 0.045, 0.92)
const C_BRASS := Color(0.86, 0.68, 0.38)
const C_TEXT := Color(0.93, 0.89, 0.80)
const C_DIM := Color(0.62, 0.56, 0.47)


func _ready() -> void:
	eco = Game.eco
	var root := Control.new(); root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(root)
	# ---- top-left odometer
	var top := _panel(); top.position = Vector2(28, 24); root.add_child(top)
	var tv := VBoxContainer.new(); top.add_child(tv)
	lbl_ticks = _label("", 44, C_BRASS); tv.add_child(lbl_ticks)
	lbl_rate = _label("", 20, C_TEXT); tv.add_child(lbl_rate)
	lbl_star = _label("", 20, Color(0.75, 0.82, 1.0)); tv.add_child(lbl_star)
	lbl_eff = _label("", 16, C_DIM); tv.add_child(lbl_eff)
	# ---- right: bench shop
	var side := _panel(); side.set_anchors_preset(Control.PRESET_RIGHT_WIDE)
	side.offset_left = -440; side.offset_right = -24; side.offset_top = 24; side.offset_bottom = -24
	root.add_child(side)
	var sv := VBoxContainer.new(); sv.add_theme_constant_override("separation", 10); side.add_child(sv)
	sv.add_child(_label(tr("BENCH"), 26, C_BRASS))
	var scroll := ScrollContainer.new(); scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; sv.add_child(scroll)
	shop = VBoxContainer.new(); shop.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	shop.add_theme_constant_override("separation", 8); scroll.add_child(shop)
	# ---- bottom: wind button
	var wind := Button.new(); wind.text = tr("WIND"); wind.custom_minimum_size = Vector2(260, 64)
	wind.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	wind.offset_left = -130; wind.offset_right = 130; wind.offset_top = -110; wind.offset_bottom = -46
	_style_button(wind, 26); root.add_child(wind)
	wind.button_down.connect(func(): wind_pressed.emit(); wind_hold.emit(true))
	wind.button_up.connect(func(): wind_hold.emit(false))
	var hint := _label(tr("WIND_HINT"), 15, C_DIM); hint.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	hint.offset_left = -200; hint.offset_right = 200; hint.offset_top = -40; hint.offset_bottom = -16
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; root.add_child(hint)
	var sky := Button.new(); sky.toggle_mode = true; sky.text = tr("LOOK_UP")
	sky.custom_minimum_size = Vector2(200, 48); _style_button(sky, 18)
	sky.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	sky.offset_left = 28; sky.offset_right = 228; sky.offset_top = -86; sky.offset_bottom = -38
	sky.toggled.connect(func(on): look_up.emit(on); sky.text = tr("LOOK_DOWN") if on else tr("LOOK_UP"))
	root.add_child(sky)
	eco.changed.connect(_refresh_shop)
	Game.offline_report.connect(_show_offline)
	_refresh_shop()


func _panel() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new(); sb.bg_color = C_PANEL
	sb.border_color = C_BRASS.darkened(0.35); sb.set_border_width_all(2)
	sb.set_corner_radius_all(3); sb.set_content_margin_all(18)
	sb.shadow_color = Color(0, 0, 0, 0.45); sb.shadow_size = 10
	p.add_theme_stylebox_override("panel", sb)
	return p


func _label(t: String, size: int, col: Color) -> Label:
	var l := Label.new(); l.text = t
	l.add_theme_font_size_override("font_size", size); l.add_theme_color_override("font_color", col)
	return l


func _style_button(b: Button, size: int) -> void:
	b.add_theme_font_size_override("font_size", size)
	for st in ["normal", "hover", "pressed", "disabled"]:
		var sb := StyleBoxFlat.new()
		sb.bg_color = {"normal": Color(0.20, 0.13, 0.08), "hover": Color(0.28, 0.18, 0.10),
			"pressed": Color(0.14, 0.09, 0.06), "disabled": Color(0.13, 0.10, 0.08)}[st]
		sb.border_color = C_BRASS if st != "disabled" else C_DIM.darkened(0.4)
		sb.set_border_width_all(2); sb.set_corner_radius_all(2); sb.set_content_margin_all(10)
		b.add_theme_stylebox_override(st, sb)
	b.add_theme_color_override("font_color", C_TEXT)
	b.add_theme_color_override("font_disabled_color", C_DIM)


func _options() -> Array:
	var out := []
	for i in eco.levels.size():
		var o := eco.stage_option(i)
		if o.kind == "unlock" and not o.available:
			continue
		if o.kind == "unlock" and eco.total_ticks < o.cost * 0.25:
			continue
		out.append(o)
	out.append(eco.drive_option())
	for c in eco.bal.complications:
		var o := eco.comp_option(c)
		if o.kind == "build" and eco.total_ticks < o.cost * 0.25:
			continue
		if o.kind != "built":
			out.append(o)
	var s := eco.star_option()
	if s.available:
		out.append(s)
	if eco.total_ticks > 200:
		out.append(eco.reserve_option())
	return out


func _title(o: Dictionary) -> String:
	match o.kind:
		"unlock": return tr("UNLOCK") + " · " + tr("STAGE_" + o.id)
		"level": return tr("STAGE_" + o.id)
		"drive": return tr("DRIVE") + " · " + tr("LEVEL") % (eco.drive + 1)
		"build": return tr("BUILD") + " · " + tr("COMP_" + o.id)
		"comp_level": return tr("COMP_" + o.id) + " · " + tr("LEVEL") % (eco.comps[o.id] + 1)
		"star": return tr("STAR")
		"reserve": return tr("RESERVE") + " · %dh" % int(eco.reserve_hours() + 1)
	return o.id


func _info(o: Dictionary) -> String:
	if o.kind == "level":
		return tr("TEETH") % [eco.teeth(o.index), "%.1f" % eco.ratio(o.index)]
	if o.kind == "drive":
		return tr("POWER_LOAD") % [Num.fmt(eco.power()), Num.fmt(eco.load_total())]
	return ""


func _refresh_shop() -> void:
	var opts := _options()
	var keys := []
	for o in opts:
		var key: String = o.kind + ":" + o.id
		if o.kind == "unlock" or o.kind == "level":
			key = "stage:" + o.id
		if o.kind == "build" or o.kind == "comp_level":
			key = "comp:" + o.id
		keys.append(key)
		if not rows.has(key):
			var b := Button.new(); b.alignment = HORIZONTAL_ALIGNMENT_LEFT
			b.custom_minimum_size = Vector2(0, 62); _style_button(b, 18)
			b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			shop.add_child(b)
			rows[key] = {"button": b}
			b.pressed.connect(func(): _buy(key))
		rows[key].option = o
		var b: Button = rows[key].button
		var cost_txt := tr("MAXED") if is_inf(o.cost) else Num.fmt(o.cost) + " " + (tr("TICKS") if o.currency == "ticks" else tr("STARLIGHT"))
		var info := _info(o)
		b.text = _title(o) + "\n" + cost_txt + ("   ·   " + info if info != "" else "")
		b.disabled = not eco.can_afford(o)
	for k in rows.keys():
		if not k in keys:
			rows[k].button.queue_free(); rows.erase(k)


func _buy(key: String) -> void:
	if rows.has(key):
		eco.buy(rows[key].option)


func _process(delta: float) -> void:
	lbl_ticks.text = Num.fmt(eco.ticks) + "  " + tr("TICKS")
	lbl_rate.text = Num.fmt(eco.beat_rate()) + " " + tr("TICKS") + tr("PER_SEC") + ("   " + tr("OVERWIND") if eco.overwind_left > 0 else "")
	lbl_star.visible = eco.starlight_rate() > 0 or eco.starlight > 0
	lbl_star.text = Num.fmt(eco.starlight) + " " + tr("STARLIGHT") + "  (+" + Num.fmt(eco.starlight_rate()) + tr("PER_SEC") + ")"
	lbl_eff.text = tr("EFFICIENCY") + " %d%%   ·   " % int(eco.efficiency() * 100) + tr("POWER_LOAD") % [Num.fmt(eco.power()), Num.fmt(eco.load_total())]
	_refresh_t += delta
	if _refresh_t > 0.25:
		_refresh_t = 0.0
		for k in rows:
			rows[k].button.disabled = not eco.can_afford(rows[k].option)


func _show_offline(rep: Dictionary) -> void:
	var p := _panel(); p.set_anchors_preset(Control.PRESET_CENTER)
	p.offset_left = -300; p.offset_right = 300; p.offset_top = -120; p.offset_bottom = 120
	var v := VBoxContainer.new(); p.add_child(v)
	v.add_child(_label(tr("OFFLINE_TITLE"), 28, C_BRASS))
	v.add_child(_label(tr("OFFLINE_BODY") % Num.duration(rep.seconds), 18, C_TEXT))
	v.add_child(_label("+" + Num.fmt(rep.ticks) + " " + tr("TICKS"), 24, C_TEXT))
	var ok := Button.new(); ok.text = "OK"; _style_button(ok, 20); v.add_child(ok)
	ok.pressed.connect(p.queue_free)
	get_child(0).add_child(p)
