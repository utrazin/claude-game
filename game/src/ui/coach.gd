extends Control
## First-time coach (tutorial). One short engraved note at a time, pointing at what matters now.
## Steps advance on real actions; finished steps persist in user://settings.cfg [tutorial].

var eco: Economy
var hud: Node
var _note: PanelContainer
var _label: Label
var _step := ""
var _winds := 0
var _bought := 0
var _done := {}
const STEPS := ["wind", "buy", "preview", "remontoir", "sky"]


func setup(e: Economy, h: Node) -> void:
	eco = e; hud = h
	set_anchors_preset(Control.PRESET_FULL_RECT); mouse_filter = Control.MOUSE_FILTER_IGNORE
	var cfg := ConfigFile.new(); cfg.load(Settings.PATH)
	for s in STEPS: _done[s] = bool(cfg.get_value("tutorial", s, false))
	if eco.total_ticks > 200.0:          # returning players skip the basics
		for s in ["wind", "buy", "preview"]: _done[s] = true
	_note = PanelContainer.new(); _note.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sb := StyleBoxTexture.new(); sb.texture = load("res://assets/ui/plate_special.png")
	for side in [SIDE_LEFT, SIDE_RIGHT, SIDE_TOP, SIDE_BOTTOM]: sb.set_texture_margin(side, 26)
	sb.content_margin_left = 30; sb.content_margin_right = 30; sb.content_margin_top = 20; sb.content_margin_bottom = 20
	_note.add_theme_stylebox_override("panel", sb)
	_label = Label.new(); _label.autowrap_mode = TextServer.AUTOWRAP_WORD; _label.custom_minimum_size.x = 360
	_label.add_theme_color_override("font_color", Color(0.20, 0.13, 0.07)); _label.add_theme_font_size_override("font_size", 21)
	_label.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	_note.add_child(_label); add_child(_note); _note.visible = false
	eco.purchased.connect(func(k, _i):
		if k != "load": _bought += 1
		elif eco.total_ticks == 0.0:          # new game: the tutorial starts over
			for st in STEPS: _done[st] = false
			_winds = 0; _bought = 0)


func on_wind() -> void:
	_winds += 1


func _finish(s: String) -> void:
	_done[s] = true
	var cfg := ConfigFile.new(); cfg.load(Settings.PATH); cfg.set_value("tutorial", s, true); cfg.save(Settings.PATH)


func _process(_d: float) -> void:
	if not hud.visible:
		_note.visible = false; return
	# advance
	if _step == "wind" and _winds >= 3: _finish("wind")
	if _step == "buy" and _bought >= 1: _finish("buy")
	if _step == "preview" and _bought >= 3: _finish("preview")
	if _step == "remontoir" and eco.boost > 2.0: _finish("remontoir")
	if _step == "sky" and eco.stars >= 1: _finish("sky")
	# pick the current step (only when its moment has come)
	var next := ""
	if not _done.wind: next = "wind"
	elif not _done.buy and _any_affordable(): next = "buy"
	elif not _done.preview and _done.buy: next = "preview"
	elif not _done.remontoir and eco.is_fully_wound() and _bought >= 3: next = "remontoir"
	elif not _done.sky and eco.star_option().available and eco.starlight >= eco.star_option().cost: next = "sky"
	_step = next
	_note.visible = next != ""
	if next == "": return
	_label.text = tr("COACH_" + next.to_upper())
	var vp := get_viewport_rect().size
	_note.reset_size()
	var pulse := 4.0 * sin(Time.get_ticks_msec() * 0.004)
	match next:
		"wind": _note.position = Vector2(vp.x * 0.5 - 192.0 - _note.size.x * 0.5, vp.y - 210.0 - _note.size.y + pulse)
		"buy", "preview": _note.position = Vector2(vp.x - 384.0 - _note.size.x - 16.0 + pulse, 120.0)
		"remontoir": _note.position = Vector2(vp.x * 0.5 - 192.0 - _note.size.x * 0.5, vp.y - 210.0 - _note.size.y + pulse)
		"sky": _note.position = Vector2(190.0 + pulse, vp.y - 140.0 - _note.size.y)


func _any_affordable() -> bool:
	for k in hud.rows:
		if not hud.rows[k].button.disabled: return true
	return false
