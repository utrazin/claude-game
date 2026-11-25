extends SceneTree
## Headless tests: godot --headless --path game -s res://tests/test_economy.gd

var fails := 0

func check(cond: bool, msg: String) -> void:
	if cond: print("  ok   ", msg)
	else:
		fails += 1; printerr("  FAIL ", msg)


func _init() -> void:
	var e := Economy.new()
	check(e.levels[0] == 1 and e.levels[1] == 0, "starts with great wheel only")
	check(is_equal_approx(e.train_ratio(), 2.0), "great wheel 24/12 = ratio 2")
	check(e.height == e.shaft_height(), "starts fully wound")
	check(e.production() > 0.0, "clock runs at start")
	# run down the weight without winding: clock falls back to sustained speed (0 without rotor)
	for i in 4000: e.tick(0.1)
	check(e.height == 0.0 and e.beat_freq() == 0.0, "stops when the weight bottoms out with no winding")
	check(e.wind() > 0.0 and e.beat_freq() > 0.0, "winding restarts the clock")
	e.height = e.shaft_height()
	check(e.wind() == 0.0, "stopwork: cannot overwind")
	var fb := e.beat_freq() / e.boost_factor()
	check(e.boost > 0.0 and e.beat_freq() > fb * 1.5, "winding past the stopwork charges the remontoir (faster beat)")
	for i in 200: e.tick(0.1)
	check(e.boost == 0.0, "remontoir runs down")
	# ratio vs amplitude
	e.ticks = 1e12
	var a0 := e.amplitude()
	e.buy(e.stage_option(0))
	check(e.amplitude() < a0 and e.teeth(0) == 30, "more teeth = less torque at the escape")
	var amp1 := e.amplitude()
	e.buy(e.weight_option())
	check(e.amplitude() > amp1, "heavier weight restores amplitude")
	# rotor sustains the clock
	e.buy(e.rotor_option()); e.height = 0.0
	check(e.f_sustained() > 0.0 and e.bottleneck() in ["winding", "regulator"], "rotor keeps an empty clock running")
	# preview does not mutate
	var lv := e.levels.duplicate(); var pv := e.preview(e.stage_option(0))
	check(e.levels == lv and pv.has("amplitude"), "preview is side-effect free")
	# offline
	e.height = e.shaft_height()
	var r := e.apply_offline(3600.0)
	check(r.ticks > 0.0 and r.seconds == 3600.0, "offline produces")
	# save round trip
	var d: Dictionary = JSON.parse_string(JSON.stringify(e.to_dict()))
	var e2 := Economy.new(); e2.from_dict(d)
	check(e2.levels == e.levels and e2.rotor == e.rotor and is_equal_approx(e2.production(), e.production()), "save round trip")
	var e3 := Economy.new(); e3.from_dict({"levels": [999, 0, 5], "height": -4})
	check(e3.levels[0] == e3.max_level() and e3.levels[2] == 0 and e3.height == 0.0, "corrupt save sanitized")
	# stars and prestige
	check(not e.star_option().available, "stars locked before a celestial complication")
	e.buy(e.comp_option(e.bal.complications[1]))
	check(e.star_option().available and e.starlight_rate() > 0.0, "moon unlocks starlight")
	# D16: adjacency, magnitude, bonuses, persistent sky
	check(e.star_reachable("clavis", 0) and not e.star_reachable("clavis", 2), "only the root (or a neighbour of a lit star) is reachable")
	check(e.star_cost("clavis", 1) > e.star_cost("clavis", 3), "bright stars cost more than faint ones")
	check(not e.star_reachable("rota", 0), "Rota's region is closed until Mercury")
	e.starlight = 1e12
	var y0 := e.yield_per_beat()
	for n in 7:
		e.buy(e.star_option())
	check(e.complete("clavis") and e.yield_per_beat() > y0 * 2.0, "completing Clavis doubles yield")
	e.comps["mercury"] = 1; e.total_starlight = 5000
	check(e.star_reachable("rota", 0), "Mercury opens Rota")
	var lit_before := e.lit.duplicate()
	var expect_aeons := e.aeons_on_reset()
	check(e.great_year_ready() and expect_aeons > 0 and e.do_great_year() == expect_aeons and e.levels[1] == 0 and e.lit == lit_before, "great year rebuilds the machine and keeps the sky")
	check(e.star_reachable("ventus", 0), "a Great Year opens Ventus")
	var e4 := Economy.new(); e4.from_dict({"stars": 3})
	check(e4.lit == ["clavis:0", "clavis:1", "clavis:2"], "v0.4 saves migrate star count to lit stars")
	check(Num.fmt(1234567.0) == "1.23M", "number format")
	# D15: the bench never sells a worse clock
	var w := Economy.new(); w.ticks = 1e9
	var bought := 0
	for k in 40:
		var o := w.stage_option(0)
		if w.can_afford(o): w.buy(o); bought += 1
	check(w.amplitude() >= 1.0 and bought < 40, "wheel upgrades stop before the weight is overloaded")
	var p0 := w.potential(); w.buy(w.weight_option())
	check(w.can_afford(w.stage_option(0)) and w.potential() >= p0, "a heavier weight reopens the wheel")
	print("FAILS: ", fails)
	quit(1 if fails else 0)
