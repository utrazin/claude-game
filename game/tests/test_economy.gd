extends SceneTree
## Headless tests: godot --headless --path game -s res://tests/test_economy.gd

var fails := 0

func check(cond: bool, msg: String) -> void:
	if cond:
		print("  ok   ", msg)
	else:
		fails += 1
		printerr("  FAIL ", msg)


func _init() -> void:
	var e := Economy.new()
	check(e.levels[0] == 1 and e.levels[1] == 0, "starts with great wheel only")
	check(is_equal_approx(e.ratio(0), 2.0), "level 1 ratio is 2")
	check(is_equal_approx(e.beat_rate(), e.bal.base_beat_rate * 2.0), "base beat rate")
	var g := e.wind()
	check(g > 0.0 and e.ticks == g, "winding gives ticks")
	e.ticks = 1e9
	check(e.buy(e.stage_option(0)), "buy wheel level")
	check(e.teeth(0) == 30, "30 teeth after one level")
	check(e.buy(e.stage_option(1)), "unlock center wheel")
	# efficiency drops when load exceeds power
	for i in 10: e.buy(e.stage_option(0))
	check(e.efficiency() < 1.0, "overloaded train loses efficiency")
	while e.efficiency() < 1.0: e.buy(e.drive_option())
	check(e.efficiency() == 1.0, "drive restores efficiency")
	# max level
	e.ticks = 1e30
	for i in 40: e.buy(e.stage_option(0))
	check(e.levels[0] == e.max_level() and e.teeth(0) == 120, "wheel capped at 120 teeth")
	# starlight requires moon
	check(not e.star_option().available, "stars locked before celestial complication")
	e.buy(e.comp_option(e.bal.complications[1]))
	check(e.starlight_rate() > 0.0, "moon produces starlight")
	# offline capped by reserve
	var r := e.apply_offline(10 * 3600.0)
	check(is_equal_approx(r.seconds, e.reserve_hours() * 3600.0), "offline capped at reserve")
	# save round trip
	var d := e.to_dict()
	var e2 := Economy.new(); e2.from_dict(JSON.parse_string(JSON.stringify(d)))
	check(e2.levels == e.levels and e2.comps == e.comps and is_equal_approx(e2.ticks, e.ticks), "save round trip")
	# corrupt values are clamped
	var e3 := Economy.new(); e3.from_dict({"levels": [999, -5]})
	check(e3.levels[0] == e3.max_level() and e3.levels[1] == 0, "levels clamped on load")
	# prestige
	e.stars = 7; e.comps["mercury"] = 1; e.total_starlight = 5000
	check(e.great_year_ready(), "great year ready")
	var a := e.do_great_year()
	check(a == 10 and e.aeons == 10 and e.levels[1] == 0, "great year grants aeons and resets")
	check(Num.fmt(1234567.0) == "1.23M" and Num.fmt(12.0) == "12", "number format")
	print("FAILS: ", fails)
	quit(1 if fails else 0)
