extends SceneTree
# Naive player: holds wind, buys the first affordable option in HUD order. Detects soft-locks.
func _init() -> void:
	var e := Economy.new()
	var hud_order := func() -> Array:
		var out := []
		for i in e.levels.size():
			var o := e.stage_option(i)
			if o.kind == "unlock" and (not o.available or e.total_ticks < o.cost * 0.25): continue
			out.append(o)
		out.append(e.regulator_option()); out.append(e.weight_option())
		out.append(e.rotor_option())
		if e.total_ticks > 40: out.append(e.shaft_option())
		return out
	var n := 0
	for step in 3000:
		var t := step * 0.1
		e.hand_rate = 3.0 if fmod(t, 20.0) < 10.0 else 0.0
		e.tick(0.1)
		for o in hud_order.call():
			if e.can_afford(o):
				e.buy(o); n += 1
				print("t=%.1f buy#%d %s:%s  amp=%.2f prod=%.3f f=%.3f h=%.1f bn=%s" % [t, n, o.kind, o.id, e.amplitude(), e.production(), e.beat_freq(), e.height, e.bottleneck()])
				break
		if n >= 12: break
	print("end ticks=", e.ticks, " prod=", e.production())
	quit()
