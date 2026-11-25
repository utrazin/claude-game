class_name Economy
extends RefCounted
## Economy v0.4 (D10): regulator + going train + weight energy. Pure model, testable headless.
## Tuning: res://data/balance_v2.json (shared with tools/sim/economy_v2.py).
##   R      = Π teeth_i / 12                    (train ratio)
##   e      = f_reg + Σ complication loads      (impulse the regulator demands per beat)
##   amp    = torque / (R · e)                  (<1: regulator starved, f = f_reg·amp²)
##   v      = f / R                             (weight fall speed)
##   empty weight → f ≤ winding · R
##   ticks/s = f · Y

signal changed
signal purchased(kind: String, id: String)

var bal: Dictionary
var ticks := 0.0
var starlight := 0.0
var total_ticks := 0.0
var total_starlight := 0.0
var levels: Array[int] = []
var regulator := 0
var weight := 0
var shaft := 0
var rotor := -1                 ## -1 = not built
var comps := {}
var lit: Array[String] = []     ## lit stars "constellation:index" — the sky persists across Great Years (F5)
var stars: int:                 ## number of lit stars (read-only view)
	get: return lit.size()
var height := 0.0               ## current weight height (energy in the shaft)
var hand_rate := 0.0            ## winding supplied by the player this frame (height/s)
var boost := 0.0                ## remontoir charge (s): hand winding past the stopwork speeds the beat
var aeons := 0
var great_years := 0
var finale_seen := false
var play_time := 0.0
var _f_now := 0.0


static func load_balance(path := "res://data/balance_v2.json") -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	assert(f, "balance missing")
	return JSON.parse_string(f.get_as_text())


func _init(balance: Dictionary = {}) -> void:
	bal = balance if not balance.is_empty() else load_balance()
	reset_run()


func reset_run() -> void:
	ticks = 0.0; starlight = 0.0
	levels.clear()
	for i in bal.stages.size():
		levels.append(1 if i == 0 else 0)
	regulator = 0; weight = 0; shaft = 0; rotor = -1
	comps.clear()
	for c in bal.complications:
		comps[c.id] = 0
	height = shaft_height()


# ------------------------------------------------------------------ physics
func max_level() -> int: return int(bal.max_level)
func teeth(i: int) -> int:
	return 0 if levels[i] <= 0 else int(bal.base_teeth + bal.teeth_per_level * (levels[i] - 1))
func ratio(i: int) -> float:
	return float(teeth(i)) / float(bal.pinion_teeth) if levels[i] > 0 else 1.0
func train_ratio() -> float:
	var r := 1.0
	for i in levels.size():
		if levels[i] > 0: r *= ratio(i)
	return r
func f_reg() -> float: return bal.regulator.f0 * pow(bal.regulator.growth, regulator)
func torque() -> float: return bal.weight.m0 * pow(bal.weight.growth, weight)
func shaft_height() -> float: return bal.shaft.h0 + bal.shaft.per_level * shaft
func rotor_rate() -> float:
	return 0.0 if rotor < 0 else bal.rotor.w0 * pow(bal.rotor.growth, rotor) * bonus("wind_mult")
func winding() -> float: return rotor_rate() + hand_rate

func impulse() -> float:
	var e: float = bal.impulse.e_per_hz * f_reg()
	for c in bal.complications:
		var lv: int = comps[c.id]
		if lv > 0: e += c.load * (1.0 + 0.5 * (lv - 1))
	return e

func amplitude() -> float: return torque() / (train_ratio() * impulse())
func f_amp() -> float: return f_reg() * pow(minf(1.0, amplitude()), 2.0)
func f_sustained() -> float: return minf(f_amp(), winding() * train_ratio() / bal.cord_per_beat)

## Actual beat frequency right now.
func beat_freq() -> float:
	return (f_amp() if height > 1e-6 else f_sustained()) * boost_factor()

## Remontoir overdrive: active only while the weight still has height to give.
func boost_factor() -> float:
	return 1.0 + float(bal.winding.get("boost_mult", 0.0)) if boost > 0.0 and height > 1e-6 else 1.0

func yield_per_beat() -> float:
	var y: float = bal.yield0
	# finer train = finer division of time: more counted per beat (D15)
	var r0: float = float(bal.base_teeth) / float(bal.pinion_teeth)
	y *= pow(train_ratio() / r0, float(bal.get("ratio_yield_exp", 0.0)))
	for c in bal.complications:
		var lv: int = comps[c.id]
		if lv > 0: y *= c.yield_mult * (1.0 + c.get("level_yield", 0.0) * (lv - 1))
	var add := 0.0
	for k in lit: add += float(bal.sky.mag[str(star_mag(k))].yield)
	y *= 1.0 + add
	y *= bonus("yield_mult")
	y *= 1.0 + float(bal.get("great_year", {}).get("aeon_yield", 0.1)) * aeons
	return y

func production() -> float: return beat_freq() * yield_per_beat()
## Kept for the visual layer: beats per second.
func beat_rate() -> float: return beat_freq()

func fall_speed() -> float: return beat_freq() * bal.cord_per_beat / train_ratio()

## Seconds until the weight bottoms out at the current speed (INF if winding keeps up).
func autonomy() -> float:
	var net: float = f_amp() * bal.cord_per_beat / train_ratio() - rotor_rate()
	return INF if net <= 0.0 else height / net

func starlight_rate() -> float:
	var p := production(); var t := 0.0
	for c in bal.complications:
		var lv: int = comps[c.id]
		if lv > 0 and c.has("starlight"): t += c.starlight * lv * pow(p, bal.starlight_exp)
	return t

## Which constraint is limiting the clock now: "regulator", "amplitude" or "winding".
func bottleneck() -> String:
	if height <= 1e-6 and f_sustained() < f_amp() - 1e-9: return "winding"
	if amplitude() < 1.0: return "amplitude"
	return "regulator"


# ------------------------------------------------------------------ simulation
func tick(dt: float) -> void:
	var f := beat_freq()
	var v: float = f * bal.cord_per_beat / train_ratio()
	height = clampf(height + (winding() - v) * dt, 0.0, shaft_height())
	if height < 1e-6: height = 0.0
	var p := f * yield_per_beat()
	ticks += p * dt; total_ticks += p * dt
	var s := starlight_rate() * dt
	starlight += s; total_starlight += s
	play_time += dt
	_f_now = f
	var wb: Dictionary = bal.winding
	if hand_rate > 0.0 and is_fully_wound():
		boost = minf(float(wb.get("boost_max", 0.0)), boost + float(wb.get("boost_hold_rate", 0.0)) * dt)
	boost = maxf(0.0, boost - dt)


## One click of the crank: raises the weight; at the stopwork it charges the remontoir instead.
## Returns height gained (0 when the click went into the remontoir).
func wind() -> float:
	var before := height
	if is_fully_wound():
		var wb: Dictionary = bal.winding
		boost = minf(float(wb.get("boost_max", 0.0)), boost + float(wb.get("boost_per_click", 0.0)))
	height = minf(shaft_height(), height + bal.winding.per_click)
	changed.emit()
	return height - before


func is_fully_wound() -> bool: return height >= shaft_height() - 1e-6


## Offline: run on stored energy, then at the automatic winding speed. Analytical.
func apply_offline(seconds: float) -> Dictionary:
	var hr := hand_rate; hand_rate = 0.0; boost = 0.0
	var s := maxf(seconds, 0.0)
	var y := yield_per_beat()
	var fa := f_amp(); var R := train_ratio(); var w := rotor_rate()
	var net: float = fa * bal.cord_per_beat / R - w
	var t_full := s if net <= 0.0 else minf(s, height / net)
	var beats := fa * t_full
	if net > 0.0:
		height = maxf(0.0, height - net * t_full)
	else:
		height = minf(shaft_height(), height - net * t_full)
	var rest := s - t_full
	if rest > 0.0:
		beats += f_sustained() * rest
	var gt := beats * y
	ticks += gt; total_ticks += gt
	var gs := starlight_rate() * s
	starlight += gs; total_starlight += gs
	hand_rate = hr
	changed.emit()
	return {"seconds": s, "ticks": gt, "starlight": gs, "full_speed_seconds": t_full}


# ------------------------------------------------------------------ shop
func stage_option(i: int) -> Dictionary:
	var st: Dictionary = bal.stages[i]
	if levels[i] == 0:
		return {"kind": "unlock", "id": st.id, "index": i, "currency": "ticks", "cost": float(st.unlock) * bonus("wheel_cost"),
			"available": i > 0 and levels[i - 1] > 0}
	if levels[i] >= max_level():
		return {"kind": "level", "id": st.id, "index": i, "currency": "ticks", "cost": INF, "available": false, "maxed": true}
	return {"kind": "level", "id": st.id, "index": i, "currency": "ticks",
		"cost": st.cost0 * pow(st.cost_growth, levels[i] - 1) * bonus("wheel_cost"), "available": true}

func regulator_option() -> Dictionary:
	return {"kind": "regulator", "id": "regulator", "currency": "ticks", "available": true,
		"cost": bal.regulator.cost0 * pow(bal.regulator.cost_growth, regulator)}

func weight_option() -> Dictionary:
	return {"kind": "weight", "id": "weight", "currency": "ticks", "available": true,
		"cost": bal.weight.cost0 * pow(bal.weight.cost_growth, weight)}

func shaft_option() -> Dictionary:
	return {"kind": "shaft", "id": "shaft", "currency": "ticks", "available": true,
		"cost": bal.shaft.cost0 * pow(bal.shaft.cost_growth, shaft)}

func rotor_option() -> Dictionary:
	var c: float = bal.rotor.unlock if rotor < 0 else bal.rotor.cost0 * pow(bal.rotor.cost_growth, rotor)
	return {"kind": "rotor", "id": "rotor", "currency": "ticks", "available": true, "cost": c, "build": rotor < 0}

func comp_option(c: Dictionary) -> Dictionary:
	var lv: int = comps[c.id]
	if lv == 0:
		return {"kind": "build", "id": c.id, "currency": "ticks", "cost": float(c.cost), "available": true}
	if c.has("level_cost0"):
		return {"kind": "comp_level", "id": c.id, "currency": "ticks", "available": true,
			"cost": c.level_cost0 * pow(c.level_growth, lv - 1)}
	return {"kind": "built", "id": c.id, "currency": "ticks", "cost": INF, "available": false}

# ------------------------------------------------------------------ sky (D16)
func constellation(cid: String) -> Dictionary:
	for c in bal.sky.constellations:
		if c.id == cid: return c
	return {}

func star_mag(key: String) -> int:
	var p := key.split(":")
	return int(constellation(p[0]).stars[int(p[1])][2])

func gate_open(c: Dictionary) -> bool:
	match str(c.gate):
		"moon": return comps.get("moon", 0) > 0
		"mercury": return comps.get("mercury", 0) > 0
		"great_year": return great_years > 0
		"ventus_complete": return complete("ventus")
	return true

func complete(cid: String) -> bool:
	var c := constellation(cid)
	for i in c.stars.size():
		if not ("%s:%d" % [cid, i]) in lit: return false
	return true

## Finale (D17): every constellation of the sky is lit — the Astrarium is complete.
func sky_complete() -> bool:
	for c in bal.sky.constellations:
		if not complete(c.id): return false
	return true

## Product of the bonuses of completed constellations of a given type (1.0 = none).
func bonus(kind: String) -> float:
	var m := 1.0
	for c in bal.sky.constellations:
		if c.bonus.type == kind and complete(c.id): m *= float(c.bonus.value)
	return m

## A star can be lit if its region is open and it is the root or touches a lit star (F4).
func star_reachable(cid: String, i: int) -> bool:
	var c := constellation(cid)
	if c.is_empty() or not gate_open(c) or ("%s:%d" % [cid, i]) in lit: return false
	if i == 0: return true
	for e in c.edges:
		if (e[0] == i and ("%s:%d" % [cid, e[1]]) in lit) or (e[1] == i and ("%s:%d" % [cid, e[0]]) in lit):
			return true
	return false

func star_cost(cid: String, i: int) -> float:
	var mag := str(int(constellation(cid).stars[i][2]))
	return bal.stars.cost0 * pow(bal.stars.growth, lit.size()) * float(bal.sky.mag[mag].cost)

func star_option_at(cid: String, i: int) -> Dictionary:
	return {"kind": "star", "id": "%s:%d" % [cid, i], "currency": "starlight",
		"available": star_reachable(cid, i) and _has_starlight_source(), "cost": star_cost(cid, i)}

func _has_starlight_source() -> bool:
	for c in bal.complications:
		if comps[c.id] > 0 and c.has("starlight"): return true
	return false

## The bench offers the cheapest reachable star (the dome lets the player pick any reachable one).
func star_option() -> Dictionary:
	var best := {}
	for c in bal.sky.constellations:
		for i in c.stars.size():
			if star_reachable(c.id, i):
				var o := star_option_at(c.id, i)
				if best.is_empty() or o.cost < best.cost: best = o
	if best.is_empty():
		return {"kind": "star", "id": "", "currency": "starlight", "available": false, "cost": INF}
	return best


## Full-speed output of the clock (ignores the weight's current height and the remontoir).
func potential() -> float: return f_amp() * yield_per_beat()

## D15: the bench refuses any part that would make the clock worse (the weight could not drive it).
func worsens(o: Dictionary) -> bool:
	if o.kind in ["weight", "shaft", "rotor", "star"] or not o.get("available", false) or is_inf(float(o.cost)):
		return false
	var e := Economy.new(bal)
	e.from_dict(to_dict())
	e._apply(o)
	return e.potential() < potential() * 0.999

func can_afford(o: Dictionary) -> bool:
	if not o.available: return false
	if worsens(o): return false
	return (ticks if o.currency == "ticks" else starlight) >= o.cost

## Preview (F7): state after buying, without committing. Returns derived values.
func preview(o: Dictionary) -> Dictionary:
	var e := Economy.new(bal)
	e.from_dict(to_dict()); e.height = height; e.hand_rate = hand_rate
	e._apply(o)
	return {"production": e.production(), "amplitude": e.amplitude(), "f_sustained": e.f_sustained(),
		"autonomy": e.autonomy(), "bottleneck": e.bottleneck()}

func buy(o: Dictionary) -> bool:
	if not can_afford(o): return false
	if o.currency == "ticks": ticks -= o.cost
	else: starlight -= o.cost
	_apply(o)
	purchased.emit(o.kind, o.id)
	changed.emit()
	return true

func _apply(o: Dictionary) -> void:
	match o.kind:
		"unlock": levels[o.index] = 1
		"level": levels[o.index] += 1
		"regulator": regulator += 1
		"weight": weight += 1
		"shaft": shaft += 1
		"rotor": rotor += 1
		"build", "comp_level": comps[o.id] += 1
		"star": if o.id != "" and not o.id in lit: lit.append(o.id)


# ------------------------------------------------------------------ prestige
func great_year_ready() -> bool:
	return complete("clavis") and comps.get("mercury", 0) > 0

func aeons_on_reset() -> int:
	return int(floor(pow(total_starlight / float(bal.get("great_year", {}).get("aeon_div", 50.0)), 1.0 / 3.0)))   # cube root: Aeons must not run away (QA-01)

func do_great_year() -> int:
	var g := aeons_on_reset()
	aeons += g; great_years += 1; total_starlight = 0.0
	reset_run()            # the machine is rebuilt; `lit` (the sky) is kept
	purchased.emit("load", ""); changed.emit()
	return g


# ------------------------------------------------------------------ persistence
func to_dict() -> Dictionary:
	return {"v": 2, "ticks": ticks, "starlight": starlight, "total_ticks": total_ticks,
		"total_starlight": total_starlight, "levels": levels.duplicate(), "regulator": regulator,
		"weight": weight, "shaft": shaft, "rotor": rotor, "comps": comps.duplicate(), "lit": lit.duplicate(),
		"height": height, "aeons": aeons, "great_years": great_years, "play_time": play_time, "finale_seen": finale_seen}

func from_dict(d: Dictionary) -> void:
	reset_run()
	ticks = maxf(0.0, float(d.get("ticks", 0.0))); starlight = maxf(0.0, float(d.get("starlight", 0.0)))
	total_ticks = float(d.get("total_ticks", ticks)); total_starlight = float(d.get("total_starlight", 0.0))
	var lv: Array = d.get("levels", [])
	for i in mini(lv.size(), levels.size()):
		levels[i] = clampi(int(lv[i]), 0, max_level())
	levels[0] = maxi(levels[0], 1)
	for i in range(1, levels.size()):       # a stage cannot exist without the previous one
		if levels[i - 1] == 0: levels[i] = 0
	regulator = maxi(0, int(d.get("regulator", 0))); weight = maxi(0, int(d.get("weight", 0)))
	shaft = maxi(0, int(d.get("shaft", 0))); rotor = maxi(-1, int(d.get("rotor", -1)))
	var cs: Dictionary = d.get("comps", {})
	for k in cs:
		if comps.has(k): comps[k] = maxi(0, int(cs[k]))
	lit.clear()
	for k in d.get("lit", []):
		var p := str(k).split(":")
		var c := constellation(p[0]) if p.size() == 2 else {}
		if not c.is_empty() and int(p[1]) >= 0 and int(p[1]) < c.stars.size() and not str(k) in lit: lit.append(str(k))
	if d.has("stars") and not d.has("lit"):     # v0.4 saves: N stars of Clavis in the old unlock order
		var order := [0, 1, 2, 4, 3, 5, 6]
		for n in mini(int(d.stars), order.size()): lit.append("clavis:%d" % order[n])
	height = clampf(float(d.get("height", shaft_height())), 0.0, shaft_height())
	aeons = maxi(0, int(d.get("aeons", 0))); great_years = maxi(0, int(d.get("great_years", 0)))
	play_time = float(d.get("play_time", 0.0))
	finale_seen = bool(d.get("finale_seen", false))
