extends CanvasLayer
## Title screen + options (Art Bible §8 skin). Shown over the live tower at launch;
## Esc reopens it as a pause sheet. The clock keeps ticking: it is an idle game.

signal closed

const UI := "res://assets/ui/"
const C_TEXT := Color(0.93, 0.90, 0.84)
const C_INK := Color(0.20, 0.13, 0.07)
const C_BRASS := Color(0.86, 0.70, 0.40)
const C_DIM := Color(0.66, 0.60, 0.50)

var F_TITLE: FontVariation
var F_TEXT: FontVariation
var _root: Control
var _main: Control
var _opts: Control
var _confirm: Control
var _first := true


func _ready() -> void:
	layer = 10
	var base: FontFile = load("res://assets/fonts/EBGaramond.ttf")
	F_TITLE = FontVariation.new(); F_TITLE.base_font = base; F_TITLE.variation_opentype = {"wght": 600}
	F_TEXT = FontVariation.new(); F_TEXT.base_font = base; F_TEXT.variation_opentype = {"wght": 600}
	Settings.changed.connect(_rebuild)
	_rebuild()
	if "--menu-options" in OS.get_cmdline_user_args(): _show(_opts)   # QA capture


func open() -> void:
	visible = true; _show(_main)


func close() -> void:
	visible = false; _first = false
	closed.emit()


func _unhandled_key_input(event: InputEvent) -> void:
	var k := event as InputEventKey
	if k and k.pressed and not k.echo and k.keycode == KEY_ESCAPE:
		if not visible: open()
		elif _opts.visible or _confirm.visible: _show(_main)
		elif not _first: close()
		get_viewport().set_input_as_handled()


# ------------------------------------------------------------------ build
func _rebuild() -> void:
	var was_opts := _opts != null and _opts.visible
	if _root: _root.queue_free()
	_root = Control.new(); _root.set_anchors_preset(Control.PRESET_FULL_RECT); add_child(_root)
	var th := Theme.new(); th.default_font = F_TEXT; th.default_font_size = 22; _root.theme = th
	var veil := ColorRect.new(); veil.set_anchors_preset(Control.PRESET_FULL_RECT)
	veil.color = Color(0.02, 0.015, 0.03, 0.55); _root.add_child(veil)
	var shade := TextureRect.new()   # left-side vignette so the title reads over the scene
	var g := GradientTexture2D.new(); var gr := Gradient.new()
	gr.set_color(0, Color(0, 0, 0, 0.75)); gr.set_color(1, Color(0, 0, 0, 0.0)); g.gradient = gr
	g.fill_to = Vector2(1, 0); shade.texture = g; shade.set_anchors_preset(Control.PRESET_LEFT_WIDE)
	shade.offset_right = 900; shade.expand_mode = TextureRect.EXPAND_IGNORE_SIZE; _root.add_child(shade)
	_main = _build_main(); _opts = _build_options(); _confirm = _build_confirm()
	_show(_opts if was_opts else _main)


func _show(c: Control) -> void:
	for x in [_main, _opts, _confirm]: x.visible = x == c


func _nine(name: String, m: int, content := 0.0) -> StyleBoxTexture:
	var sb := StyleBoxTexture.new(); sb.texture = load(UI + name + ".png")
	sb.texture_margin_left = m; sb.texture_margin_right = m; sb.texture_margin_top = m; sb.texture_margin_bottom = m
	if content > 0.0: sb.set_content_margin_all(content)
	return sb


func _label(t: String, size: int, col: Color, font: Font = null) -> Label:
	var l := Label.new(); l.text = t; l.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	l.add_theme_font_size_override("font_size", size); l.add_theme_color_override("font_color", col)
	l.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.75))
	l.add_theme_constant_override("shadow_offset_x", 1); l.add_theme_constant_override("shadow_offset_y", 2)
	if font: l.add_theme_font_override("font", font)
	return l


func _plate(text: String, cb: Callable) -> Button:
	var b := Button.new(); b.text = text; b.auto_translate_mode = Node.AUTO_TRANSLATE_MODE_DISABLED
	b.custom_minimum_size = Vector2(380, 70); b.focus_mode = Control.FOCUS_NONE
	b.add_theme_stylebox_override("normal", _nine("plate_polished", 26))
	b.add_theme_stylebox_override("pressed", _nine("plate_polished", 26))
	var hv := _nine("plate_hover", 44); hv.expand_margin_left = 18; hv.expand_margin_right = 18
	hv.expand_margin_top = 18; hv.expand_margin_bottom = 18
	b.add_theme_stylebox_override("hover", hv)
	b.add_theme_stylebox_override("focus", StyleBoxEmpty.new())
	b.add_theme_font_override("font", F_TITLE); b.add_theme_font_size_override("font_size", 26)
	for c in ["font_color", "font_hover_color", "font_pressed_color"]: b.add_theme_color_override(c, C_INK)
	b.pressed.connect(func(): Audio.play("engage", -14.0, 1.3); cb.call())
	return b


func _column(x: float) -> VBoxContainer:
	var v := VBoxContainer.new(); v.set_anchors_preset(Control.PRESET_LEFT_WIDE)
	v.offset_left = x; v.offset_right = x + 520; v.alignment = BoxContainer.ALIGNMENT_CENTER
	v.add_theme_constant_override("separation", 14); _root.add_child(v)
	return v


func _build_main() -> Control:
	var v := _column(120)
	var t := _label("ASTRARIUM", 96, C_BRASS, F_TITLE); v.add_child(t)
	v.add_child(_label(tr("TAGLINE"), 24, C_TEXT))
	var sp := Control.new(); sp.custom_minimum_size.y = 30; v.add_child(sp)
	if Game.has_progress():
		v.add_child(_plate(tr("MENU_CONTINUE"), close))
		v.add_child(_plate(tr("MENU_NEW"), func(): _show(_confirm)))
	else:
		v.add_child(_plate(tr("MENU_START"), close))
	v.add_child(_plate(tr("MENU_OPTIONS"), func(): _show(_opts)))
	v.add_child(_plate(tr("MENU_QUIT"), func(): Game.save_game(); get_tree().quit()))
	return v


func _build_confirm() -> Control:
	var v := _column(120)
	v.add_child(_label(tr("MENU_NEW"), 48, C_BRASS, F_TITLE))
	var l := _label(tr("CONFIRM_NEW"), 22, C_TEXT); l.autowrap_mode = TextServer.AUTOWRAP_WORD; v.add_child(l)
	v.add_child(_plate(tr("CONFIRM_YES"), func(): Game.new_game(); close()))
	v.add_child(_plate(tr("BACK"), func(): _show(_main)))
	return v


func _build_options() -> Control:
	var v := _column(120)
	v.add_child(_label(tr("MENU_OPTIONS"), 56, C_BRASS, F_TITLE))
	var panel := PanelContainer.new(); panel.add_theme_stylebox_override("panel", _nine("frame_brass", 28, 28)); v.add_child(panel)
	var grid := GridContainer.new(); grid.columns = 2; grid.add_theme_constant_override("h_separation", 24)
	grid.add_theme_constant_override("v_separation", 12); panel.add_child(grid)
	for bus in ["Master", "SFX", "Music", "Ambience"]:
		grid.add_child(_label(tr("VOL_" + bus.to_upper()), 22, C_TEXT))
		var s := HSlider.new(); s.min_value = 0; s.max_value = 1; s.step = 0.05; s.value = Settings.volumes[bus]
		s.custom_minimum_size = Vector2(240, 28); s.focus_mode = Control.FOCUS_NONE
		var grab := _nine("roller", 6); s.add_theme_icon_override("grabber", _knob()); s.add_theme_icon_override("grabber_highlight", _knob())
		var track := StyleBoxFlat.new(); track.bg_color = Color(0.08, 0.05, 0.03); track.content_margin_top = 4; track.content_margin_bottom = 4
		track.border_color = C_BRASS.darkened(0.4); track.set_border_width_all(1)
		var fill := StyleBoxFlat.new(); fill.bg_color = C_BRASS.darkened(0.15); fill.content_margin_top = 4; fill.content_margin_bottom = 4
		s.add_theme_stylebox_override("slider", track); s.add_theme_stylebox_override("grabber_area", fill)
		s.add_theme_stylebox_override("grabber_area_highlight", fill)
		s.value_changed.connect(func(x): Settings.set_volume(bus, x))
		grid.add_child(s)
	grid.add_child(_label(tr("OPT_GRAPHICS"), 22, C_TEXT))
	grid.add_child(_cycle([tr("GFX_LOW").get_slice(": ", 1), tr("GFX_MEDIUM").get_slice(": ", 1), tr("GFX_HIGH").get_slice(": ", 1)], Settings.quality, func(i): Settings.set_quality(i)))
	grid.add_child(_label(tr("OPT_LANGUAGE"), 22, C_TEXT))
	var locs := ["en", "pt_BR"]
	grid.add_child(_cycle(["English", "Português (Brasil)"], maxi(0, locs.find(Settings.locale)), func(i): Settings.set_locale(locs[i])))
	grid.add_child(_label(tr("OPT_FPS"), 22, C_TEXT))
	grid.add_child(_cycle([tr("OFF"), tr("ON")], 1 if Settings.show_fps else 0, func(i): Settings.set_show_fps(i == 1)))
	v.add_child(_plate(tr("BACK"), func(): _show(_main)))
	return v


func _knob() -> Texture2D:
	var img := Image.create(22, 22, false, Image.FORMAT_RGBA8)
	for y in 22:
		for x in 22:
			var d := Vector2(x - 10.5, y - 10.5).length()
			if d < 10.5:
				var l := 0.75 + 0.35 * (1.0 - (x + y) / 42.0)
				img.set_pixel(x, y, Color(0.86 * l, 0.70 * l, 0.40 * l, clampf(10.5 - d, 0.0, 1.0)))
	return ImageTexture.create_from_image(img)


## A brass plate that cycles through options on click (avoids OS-styled dropdown popups).
func _cycle(items: Array, idx: int, cb: Callable) -> Button:
	var b := _plate(items[idx], func(): pass)
	b.custom_minimum_size = Vector2(240, 52); b.add_theme_font_size_override("font_size", 20)
	var state := [idx]
	b.pressed.connect(func():
		state[0] = (state[0] + 1) % items.size(); b.text = items[state[0]]; cb.call(state[0]))
	return b
