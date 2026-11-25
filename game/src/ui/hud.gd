extends CanvasLayer
## HUD v1 (Art Bible §8, from AST-UI-001): diegetic-physical skin. Walnut, engraved brass
## plates, enamel gauges, brass odometer rollers, winding-key button. Built in code.
## Layout budget: bench ≤ 20% width, total UI ≤ 30% of the screen.

signal wind_pressed
signal wind_hold(holding: bool)
signal look_up(up: bool)

var eco: Economy
var lbl_rate: Label
var lbl_star: Label
var lbl_status: Label
var lbl_preview: Label
var lbl_fps: Label
var g_amp: Gauge
var g_res: Gauge
var _side: Control
var _wind: Control
var _hint: Label
var _sky_btn: Button
var _odo: HBoxContainer
var _odo_text := ""
var shop: VBoxContainer
var rows := {}          ## key -> {button, option, title, info, icon}
var _refresh_t := 0.0
var _hover := ""

const C_TEXT := Color(0.93, 0.90, 0.84)      ## cream #EDE6D6
const C_INK := Color(0.20, 0.13, 0.07)       ## engraving on brass
const C_INK_DIM := Color(0.80, 0.72, 0.58, 0.85)    ## cream on darkened brass (too expensive)
const C_BRASS := Color(0.86, 0.70, 0.40)
const C_DIM := Color(0.66, 0.60, 0.50)
const C_STAR := Color(0.74, 0.80, 1.0)
const BENCH_W := 384.0                        ## 20% of 1920
const UI := "res://assets/ui/"

var F_TEXT: FontVariation
var F_TITLE: FontVariation
var F_NUM: FontVariation


func _ready() -> void:
	eco = Game.eco
	_fonts()
	var root := Control.new(); root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE; add_child(root)
	var th := Theme.new(); th.default_font = F_TEXT; th.default_font_size = 20; root.theme = th
	_build_odometer(root)
	_build_bench(root)
	_build_actions(root)
	lbl_fps = _label("", 15, C_DIM); lbl_fps.set_anchors_preset(Control.PRESET_CENTER_TOP)
	lbl_fps.offset_left = -200; lbl_fps.offset_right = 200; lbl_fps.offset_top = 8
	lbl_fps.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; root.add_child(lbl_fps)
	eco.changed.connect(_refresh_shop)
	Game.offline_report.connect(_show_offline)
	_refresh_shop()


# ------------------------------------------------------------------ skin primitives
func _fonts() -> void:
	var base: FontFile = load("res://assets/fonts/EBGaramond.ttf")
	F_TEXT = FontVariation.new(); F_TEXT.base_font = base; F_TEXT.variation_opentype = {"wght": 600}
	F_TITLE = FontVariation.new(); F_TITLE.base_font = base; F_TITLE.variation_opentype = {"wght": 650}
	F_NUM = FontVariation.new(); F_NUM.base_font = base; F_NUM.variation_opentype = {"wght": 600}
	F_NUM.opentype_features = {"lnum": 1, "tnum": 1}


func _tex(name: String) -> Texture2D:
	return load(UI + name + ".png")


func _nine(name: String, m: int, content := 0.0, expand := 0.0) -> StyleBoxTexture:
	var sb := StyleBoxTexture.new(); sb.texture = _tex(name)
	sb.texture_margin_left = m; sb.texture_margin_right = m; sb.texture_margin_top = m; sb.texture_margin_bottom = m
	if content > 0.0: sb.set_content_margin_all(content)
	if expand > 0.0:
		sb.expand_margin_left = expand; sb.expand_margin_right = expand
		sb.expand_margin_top = expand; sb.expand_margin_bottom = expand
	return sb


func _label(t: String, size: int, col: Color, font: Font = null) -> Label:
	var l := Label.new(); l.text = t
	l.add_theme_font_size_override("font_size", size); l.add_theme_color_override("font_color", col)
	if font: l.add_theme_font_override("font", font)
	l.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return l


func _shadowed(l: Label) -> Label:
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.7))
	l.add_theme_constant_override("shadow_offset_x", 1); l.add_theme_constant_override("shadow_offset_y", 2)
	return l


func _framed() -> PanelContainer:
	var p := PanelContainer.new()
	p.add_theme_stylebox_override("panel", _nine("frame_brass", 28, 26))
	return p


# ------------------------------------------------------------------ odometer (top-left)
func _build_odometer(root: Control) -> void:
	var top := _framed(); top.position = Vector2(24, 20); root.add_child(top)
	var v := VBoxContainer.new(); v.add_theme_constant_override("separation", 4); top.add_child(v)
	var rollers := PanelContainer.new()
	var slot := StyleBoxFlat.new(); slot.bg_color = Color(0.06, 0.04, 0.02); slot.set_content_margin_all(5)
	slot.border_color = C_BRASS.darkened(0.45); slot.set_border_width_all(2)
	rollers.add_theme_stylebox_override("panel", slot); v.add_child(rollers)
	rollers.size_flags_horizontal = Control.SIZE_SHRINK_BEGIN
	_odo = HBoxContainer.new(); _odo.add_theme_constant_override("separation", 3); rollers.add_child(_odo)
	var cap := _shadowed(_label(tr("TICKS"), 18, C_BRASS, F_TITLE)); v.add_child(cap)
	lbl_rate = _shadowed(_label("", 19, C_TEXT, F_NUM)); v.add_child(lbl_rate)
	lbl_star = _shadowed(_label("", 19, C_STAR, F_NUM)); v.add_child(lbl_star)
	var gauges := HBoxContainer.new(); gauges.add_theme_constant_override("separation", 14); v.add_child(gauges)
	g_amp = Gauge.new(); g_amp.custom_minimum_size = Vector2(128, 138); g_amp.font = F_TITLE
	g_amp.caption = tr("AMPLITUDE"); g_amp.zone = Vector2(1.0 / 3.0, 2.0 / 3.0); gauges.add_child(g_amp)
	g_res = Gauge.new(); g_res.custom_minimum_size = Vector2(128, 138); g_res.font = F_TITLE
	g_res.caption = tr("RESERVE"); gauges.add_child(g_res)
	lbl_status = _shadowed(_label("", 16, C_DIM)); v.add_child(lbl_status)
	lbl_preview = _shadowed(_label("", 16, C_STAR)); lbl_preview.autowrap_mode = TextServer.AUTOWRAP_WORD
	lbl_preview.custom_minimum_size.x = 300; v.add_child(lbl_preview)


func _set_odometer(text: String) -> void:
	if text == _odo_text: return
	var old := _odo_text; _odo_text = text
	while _odo.get_child_count() < text.length():
		var r := TextureRect.new(); r.texture = _tex("roller"); r.custom_minimum_size = Vector2(44, 64)
		r.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; r.clip_contents = true
		var l := _label("", 46, C_INK, F_NUM); l.set_anchors_preset(Control.PRESET_FULL_RECT)
		l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; l.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		r.add_child(l); _odo.add_child(r)
	while _odo.get_child_count() > text.length():
		var c := _odo.get_child(_odo.get_child_count() - 1); _odo.remove_child(c); c.queue_free()
	for i in text.length():
		var r := _odo.get_child(i) as TextureRect
		var l := r.get_child(0) as Label
		var ch := text[i]
		r.custom_minimum_size.x = 44 if ch.is_valid_int() else 30
		if l.text != ch:
			l.text = ch
			if i < old.length():   # roll the digit in from below
				l.position.y = 26.0
				create_tween().tween_property(l, "position:y", 0.0, 0.22).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)


# ------------------------------------------------------------------ the bench (right rail)
func _build_bench(root: Control) -> void:
	var side := PanelContainer.new(); _side = side
	var wood := StyleBoxTexture.new(); wood.texture = _tex("walnut")
	wood.texture_margin_left = 12; wood.texture_margin_right = 12; wood.texture_margin_top = 12; wood.texture_margin_bottom = 12
	wood.axis_stretch_vertical = StyleBoxTexture.AXIS_STRETCH_MODE_TILE_FIT
	wood.content_margin_left = 16; wood.content_margin_right = 16; wood.content_margin_top = 18; wood.content_margin_bottom = 18
	side.add_theme_stylebox_override("panel", wood)
	side.set_anchors_preset(Control.PRESET_RIGHT_WIDE)
	side.offset_left = -BENCH_W; side.offset_right = 0; side.offset_top = 0; side.offset_bottom = 0
	root.add_child(side)
	var sv := VBoxContainer.new(); sv.add_theme_constant_override("separation", 12); side.add_child(sv)
	var title := _shadowed(_label(tr("BENCH"), 30, C_BRASS, F_TITLE)); title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sv.add_child(title)
	var rule := ColorRect.new(); rule.color = C_BRASS.darkened(0.3); rule.custom_minimum_size = Vector2(0, 2); sv.add_child(rule)
	var scroll := ScrollContainer.new(); scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED; sv.add_child(scroll)
	shop = VBoxContainer.new(); shop.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	shop.add_theme_constant_override("separation", 6); scroll.add_child(shop)


func _icon_for(o: Dictionary) -> String:
	match o.kind:
		"unlock", "level": return "gear"
		"regulator": return "pendulum"
		"weight": return "weight"
		"shaft": return "shaft"
		"rotor": return "rotor"
		"star": return "star"
		"build", "comp_level":
			match o.id:
				"hour_dial": return "dial"
				"moon": return "moon"
				_: return "planet"
	return "gear"


func _make_plate(key: String) -> Dictionary:
	var b := Button.new(); b.custom_minimum_size = Vector2(0, 80); b.focus_mode = Control.FOCUS_NONE
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.add_theme_stylebox_override("normal", _nine("plate_polished", 26))
	b.add_theme_stylebox_override("hover", _nine("plate_hover", 44, 0, 4))
	b.add_theme_stylebox_override("pressed", _nine("plate_polished", 26))
	b.add_theme_stylebox_override("disabled", _nine("plate_dull", 26))
	b.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	var h := HBoxContainer.new(); h.set_anchors_preset(Control.PRESET_FULL_RECT)
	h.offset_left = 18; h.offset_right = -18; h.offset_top = 8; h.offset_bottom = -8
	h.add_theme_constant_override("separation", 10); h.mouse_filter = Control.MOUSE_FILTER_IGNORE; b.add_child(h)
	var ic := TextureRect.new(); ic.custom_minimum_size = Vector2(56, 56); ic.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	ic.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED; ic.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ic.size_flags_vertical = Control.SIZE_SHRINK_CENTER; h.add_child(ic)
	var v := VBoxContainer.new(); v.size_flags_horizontal = Control.SIZE_EXPAND_FILL; v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 0); v.mouse_filter = Control.MOUSE_FILTER_IGNORE; h.add_child(v)
	var t := _label("", 23, C_INK, F_TITLE); t.clip_text = true; v.add_child(t)
	var i := _label("", 17, C_INK, F_NUM); i.clip_text = true; v.add_child(i)
	shop.add_child(b)
	b.pressed.connect(func(): _buy(key))
	b.mouse_entered.connect(func():
		_hover = key
		if not b.disabled: create_tween().tween_property(h, "position:y", h.position.y - 2.0, 0.08))
	b.mouse_exited.connect(func():
		if _hover == key: _hover = ""
		h.offset_top = 8; h.offset_bottom = -8)
	return {"button": b, "title": t, "info": i, "icon": ic}


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
			rows[key] = _make_plate(key)
		var row: Dictionary = rows[key]
		row.option = o
		var cost_txt := tr("MAXED") if is_inf(o.cost) else Num.fmt(o.cost) + " " + (tr("TICKS") if o.currency == "ticks" else tr("STARLIGHT"))
		var info := _info(o)
		(row.title as Label).text = _title(o)
		(row.info as Label).text = cost_txt + ("  ·  " + info if info != "" else "")
		(row.icon as TextureRect).texture = _tex("icon_" + _icon_for(o))
		_set_plate_state(row)
	for k in rows.keys():
		if not k in keys:
			rows[k].button.queue_free(); rows.erase(k)


func _set_plate_state(row: Dictionary) -> void:
	var b: Button = row.button
	var ok := eco.can_afford(row.option)
	b.disabled = not ok
	var col := C_INK if ok else C_INK_DIM
	(row.title as Label).add_theme_color_override("font_color", col)
	(row.info as Label).add_theme_color_override("font_color", col)
	(row.icon as TextureRect).modulate = Color(1, 1, 1, 1.0 if ok else 0.55)


func _buy(key: String) -> void:
	if rows.has(key):
		eco.buy(rows[key].option)


# ------------------------------------------------------------------ actions (bottom)
func _build_actions(root: Control) -> void:
	var wind := Button.new(); wind.focus_mode = Control.FOCUS_NONE
	wind.custom_minimum_size = Vector2(300, 84)
	wind.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	wind.offset_left = -150 - BENCH_W * 0.5; wind.offset_right = 150 - BENCH_W * 0.5
	wind.offset_top = -124; wind.offset_bottom = -40
	for st in ["normal", "pressed", "disabled"]:
		wind.add_theme_stylebox_override(st, _nine("frame_brass", 28, 10))
	wind.add_theme_stylebox_override("hover", _nine("frame_brass", 28, 10))
	wind.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	wind.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	wind.text = tr("WIND").to_upper()
	wind.add_theme_font_override("font", F_TITLE); wind.add_theme_font_size_override("font_size", 30)
	wind.add_theme_color_override("font_color", C_TEXT); wind.add_theme_color_override("font_hover_color", Color(1.0, 0.86, 0.6))
	wind.add_theme_color_override("font_pressed_color", C_BRASS)
	root.add_child(wind); _wind = wind
	var key := TextureRect.new(); key.texture = _tex("icon_key"); key.custom_minimum_size = Vector2(92, 92)
	key.size = Vector2(92, 92)
	key.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; key.modulate = Color(2.4, 1.9, 1.1)   # brass key over the plaque
	key.position = Vector2(150 - 46, -66); key.mouse_filter = Control.MOUSE_FILTER_IGNORE; wind.add_child(key)
	wind.button_down.connect(func():
		wind_pressed.emit(); wind_hold.emit(true)
		create_tween().tween_property(key, "rotation", key.rotation + PI * 0.5, 0.25).set_trans(Tween.TRANS_BACK))
	wind.button_up.connect(func(): wind_hold.emit(false))
	key.pivot_offset = Vector2(46, 46)
	var hint := _shadowed(_label(tr("WIND_HINT"), 16, C_DIM)); hint.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	hint.offset_left = -300 - BENCH_W * 0.5; hint.offset_right = 300 - BENCH_W * 0.5; hint.offset_top = -36; hint.offset_bottom = -12
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; root.add_child(hint); _hint = hint
	var sky := Button.new(); sky.toggle_mode = true; sky.focus_mode = Control.FOCUS_NONE
	sky.custom_minimum_size = Vector2(150, 112)
	sky.set_anchors_preset(Control.PRESET_BOTTOM_LEFT)
	sky.offset_left = 24; sky.offset_right = 174; sky.offset_top = -136; sky.offset_bottom = -24
	for st in ["normal", "hover", "pressed", "hover_pressed"]:
		sky.add_theme_stylebox_override(st, _nine("frame_brass", 28, 8))
	sky.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	var dome := TextureRect.new(); dome.texture = _tex("icon_dome"); dome.set_anchors_preset(Control.PRESET_FULL_RECT)
	dome.offset_left = 22; dome.offset_right = -22; dome.offset_top = 14; dome.offset_bottom = -30
	dome.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; dome.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	dome.modulate = Color(2.2, 1.8, 1.1); dome.mouse_filter = Control.MOUSE_FILTER_IGNORE; sky.add_child(dome)
	var cap := _label(tr("LOOK_UP"), 17, C_TEXT, F_TITLE); cap.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED; cap.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	cap.offset_top = -30; cap.offset_bottom = -8; cap.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER; sky.add_child(cap)
	sky.toggled.connect(func(on): look_up.emit(on); cap.text = tr("LOOK_DOWN") if on else tr("LOOK_UP"))
	root.add_child(sky); _sky_btn = sky


func _options() -> Array:
	var out := []
	for i in eco.levels.size():
		var o := eco.stage_option(i)
		if o.kind == "unlock" and (not o.available or eco.total_ticks < o.cost * 0.25):
			continue
		out.append(o)
	out.append(eco.regulator_option())
	out.append(eco.weight_option())
	var r := eco.rotor_option()
	if not r.build or eco.total_ticks >= r.cost * 0.4:
		out.append(r)
	if eco.total_ticks > 40:
		out.append(eco.shaft_option())
	for c in eco.bal.complications:
		var o := eco.comp_option(c)
		if o.kind == "build" and eco.total_ticks < o.cost * 0.25:
			continue
		if o.kind != "built":
			out.append(o)
	var s := eco.star_option()
	if s.available:
		out.append(s)
	return out


func _title(o: Dictionary) -> String:
	match o.kind:
		"unlock": return tr("UNLOCK") + " · " + tr("STAGE_" + o.id)
		"level": return tr("STAGE_" + o.id)
		"regulator": return tr("REGULATOR") + " · " + tr("LEVEL") % (eco.regulator + 1)
		"weight": return tr("DRIVE") + " · " + tr("LEVEL") % (eco.weight + 1)
		"shaft": return tr("SHAFT") + " · " + tr("LEVEL") % (eco.shaft + 1)
		"rotor": return (tr("BUILD") + " · " + tr("ROTOR")) if o.build else tr("ROTOR") + " · " + tr("LEVEL") % (eco.rotor + 2)
		"build": return tr("BUILD") + " · " + tr("COMP_" + o.id)
		"comp_level": return tr("COMP_" + o.id) + " · " + tr("LEVEL") % (eco.comps[o.id] + 1)
		"star": return tr("STAR")
	return o.id


func _info(o: Dictionary) -> String:
	if eco.worsens(o): return tr("NEEDS_WEIGHT")
	match o.kind:
		"level": return tr("TEETH") % [eco.teeth(o.index), "%.1f" % eco.ratio(o.index)]
		"regulator": return "%.2f " % eco.f_reg() + tr("BEATS_PER_SEC")
		"weight": return tr("TORQUE") + " " + Num.fmt(eco.torque())
		"shaft": return tr("DEPTH") + " " + Num.fmt(eco.shaft_height())
		"rotor": return Num.fmt(eco.rotor_rate()) + tr("PER_SEC")
	return ""


func _preview_text(o: Dictionary) -> String:
	if not o.available or is_inf(o.cost):
		return ""
	var p := eco.preview(o)
	var now := eco.production()
	var d: float = p.production / maxf(now, 1e-9) - 1.0
	var t := tr("PREVIEW") % ["%+.0f%%" % (d * 100.0), "%d%%" % int(minf(p.amplitude, 9.99) * 100.0)]
	if p.amplitude < 1.0 and eco.amplitude() >= 1.0:
		t += "  ·  " + tr("WARN_AMP")
	return t




func _process(delta: float) -> void:
	lbl_fps.visible = Settings.show_fps
	if Settings.show_fps:
		lbl_fps.text = "%d FPS  ·  %s (F10)" % [Engine.get_frames_per_second(), tr(Settings.NAMES[Settings.quality])]
	_set_odometer(Num.fmt(eco.ticks))
	lbl_rate.text = Num.fmt(eco.production()) + " " + tr("TICKS") + tr("PER_SEC") + "   ·   %.2f " % eco.beat_freq() + tr("BEATS_PER_SEC")
	lbl_star.visible = eco.starlight_rate() > 0 or eco.starlight > 0
	lbl_star.text = Num.fmt(eco.starlight) + " " + tr("STARLIGHT") + "  (+" + Num.fmt(eco.starlight_rate()) + tr("PER_SEC") + ")"
	g_amp.value = minf(eco.amplitude(), 3.0) / 3.0
	g_res.value = eco.height / maxf(eco.shaft_height(), 1e-9)
	g_res.accent = eco.boost / maxf(float(eco.bal.winding.get("boost_max", 1.0)), 1e-9)
	var au := eco.autonomy()
	var st := tr("LIMIT_" + eco.bottleneck()) + "   ·   " + tr("RESERVE") + " " + ("∞" if is_inf(au) else Num.duration(au))
	if eco.boost > 0.0:
		st += "\n" + tr("REMONTOIR") % ["%+d%%" % int((eco.boost_factor() - 1.0) * 100.0), "%.0f" % ceilf(eco.boost)]
	lbl_status.text = st
	lbl_preview.text = _preview_text(rows[_hover].option) if rows.has(_hover) else ""
	_refresh_t += delta
	if _refresh_t > 0.25:
		_refresh_t = 0.0
		for k in rows:
			_set_plate_state(rows[k])


func _show_offline(rep: Dictionary) -> void:
	var p := _framed(); p.set_anchors_preset(Control.PRESET_CENTER)
	p.offset_left = -320; p.offset_right = 320; p.offset_top = -140; p.offset_bottom = 140
	var v := VBoxContainer.new(); v.add_theme_constant_override("separation", 10); p.add_child(v)
	v.add_child(_shadowed(_label(tr("OFFLINE_TITLE"), 32, C_BRASS, F_TITLE)))
	v.add_child(_shadowed(_label(tr("OFFLINE_BODY") % Num.duration(rep.seconds), 20, C_TEXT)))
	v.add_child(_shadowed(_label("+" + Num.fmt(rep.ticks) + " " + tr("TICKS"), 30, C_TEXT, F_NUM)))
	var ok := Button.new(); ok.text = "OK"; ok.focus_mode = Control.FOCUS_NONE; ok.custom_minimum_size = Vector2(0, 64)
	for st in ["normal", "hover", "pressed"]:
		ok.add_theme_stylebox_override(st, _nine("plate_hover" if st == "hover" else "plate_polished", 44 if st == "hover" else 26, 0, 4.0 if st == "hover" else 0.0))
	ok.add_theme_font_override("font", F_TITLE); ok.add_theme_font_size_override("font_size", 24)
	ok.add_theme_color_override("font_color", C_INK); ok.add_theme_color_override("font_hover_color", C_INK)
	v.add_child(ok)
	ok.pressed.connect(p.queue_free)
	get_child(0).add_child(p)


## Observatory shot: the bench slides away, winding is hidden, the hint points at the sky.
func sky_progress(b: float) -> void:
	var k := smoothstep(0.1, 0.6, b)
	_side.modulate.a = 1.0 - k
	_side.offset_left = -BENCH_W + BENCH_W * 0.5 * k; _side.offset_right = BENCH_W * 0.5 * k
	_side.visible = k < 0.99
	_wind.modulate.a = 1.0 - k; _wind.visible = k < 0.99
	_hint.text = tr("SKY_HINT") if b > 0.5 else tr("WIND_HINT")
	_hint.offset_left = -300 - BENCH_W * 0.5 * (1.0 - k); _hint.offset_right = 300 - BENCH_W * 0.5 * (1.0 - k)
