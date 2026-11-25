extends SceneTree
## Pacing check on the real Economy (replaces the v0.4 Python simulator for D15/D16).
## Policy: a casual-active player. Holds the crank 50% of the time; buys the bench item with
## the best "potential gain per cost" among affordable ones (falls back to the cheapest); lights
## stars as soon as possible; takes the Great Year when ready. Prints milestones.
func _init() -> void:
	var e := Economy.new()
	var marks := {}
	var dt := 0.5
	var t := 0.0
	while t < 8.0 * 3600.0 and not e.sky_complete():
		e.hand_rate = 3.0 if fmod(t, 20.0) < 10.0 else 0.0
		e.tick(dt); t += dt
		if fmod(t, 2.0) < dt:
			_shop(e)
		for m in [["moon", e.comps.moon > 0], ["mercury", e.comps.mercury > 0], ["clavis", e.complete("clavis")],
				["rota", e.complete("rota")], ["great_year_1", e.great_years >= 1], ["ventus", e.complete("ventus")],
				["horologium", e.complete("horologium")], ["great_year_2", e.great_years >= 2], ["great_year_3", e.great_years >= 3]]:
			if m[1] and not marks.has(m[0]):
				marks[m[0]] = t; print("%-13s at %5.1f min   prod=%s/s  stars=%d" % [m[0], t / 60.0, Num.fmt(e.production()), e.stars])
		if e.great_year_ready() and e.aeons_on_reset() >= maxi(3, e.aeons):   # reset when it at least doubles Aeons
			print("great year at %.1f min: +%d aeons" % [t / 60.0, e.do_great_year()])
	print("END %.1f h:" % (t / 3600.0), " prod=%s/s stars=%d aeons=%d gy=%d" % [Num.fmt(e.production()), e.stars, e.aeons, e.great_years])
	quit()


func _shop(e: Economy) -> void:
	var s := e.star_option()
	if e.can_afford(s): e.buy(s)
	var opts := []
	for i in e.levels.size(): opts.append(e.stage_option(i))
	opts += [e.regulator_option(), e.weight_option(), e.rotor_option(), e.shaft_option()]
	for c in e.bal.complications: opts.append(e.comp_option(c))
	var best := {}; var best_v := -1.0
	for o in opts:
		if not e.can_afford(o): continue
		var p := e.preview(o)
		var gain: float = p.production / maxf(e.production(), 1e-9) - 1.0
		if o.kind in ["build", "unlock"]: gain += 0.5          # new parts are worth it beyond raw output
		var v := gain / maxf(o.cost, 1.0)
		if v > best_v: best_v = v; best = o
	if not best.is_empty(): e.buy(best)
