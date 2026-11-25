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
var stars := 0
var height := 0.0               ## current weight height (energy in the shaft)
var hand_rate := 0.0            ## winding supplied by the player this frame (height/s)
var boost := 0.0                ## remontoir charge (s): hand winding past the stopwork speeds the beat
var aeons := 0
var great_years := 0
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
	regulator = 0; weight = 0; shaft = 0; rotor = -1; stars = 0
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
	return 0.0 if rotor < 0 else bal.rotor.w0 * pow(bal.rotor.growth, rotor)
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
	for c in bal.complications:
		var lv: int = comps[c.id]
		if lv > 0: y *= c.yield_mult * (1.0 + c.get("level_yield", 0.0) * (lv - 1))
	var st: Dictionary = bal.stars
	y *= 1.0 + st.yield_add * stars
	y *= pow(st.constellation_mult, stars / int(st.constellation_size))
	y *= 1.0 + 0.1 * aeons
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
		return {"kind": "unlock", "id": st.id, "index": i, "currency": "ticks", "cost": float(st.unlock),
			"available": i > 0 and levels[i - 1] > 0}
	if levels[i] >= max_level():
		return {"kind": "level", "id": st.id, "index": i, "currency": "ticks", "cost": INF, "available": false, "maxed": true}
	return {"kind": "level", "id": st.id, "index": i, "currency": "ticks",
		"cost": st.cost0 * pow(st.cost_growth, levels[i] - 1), "available": true}

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

func star_option() -> Dictionary:
	var any := false
	for c in bal.complications:
		if comps[c.id] > 0 and c.has("starlight"): any = true
	return {"kind": "star", "id": "star", "currency": "starlight", "available": any,
		"cost": bal.stars.cost0 * pow(bal.stars.growth, stars)}

func can_afford(o: Dictionary) -> bool:
	if not o.available: return false
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
		"star": stars += 1


# ------------------------------------------------------------------ prestige
func great_year_ready() -> bool:
	return stars >= int(bal.stars.constellation_size) and comps.get("mercury", 0) > 0

func aeons_on_reset() -> int:
	return int(floor(sqrt(total_starlight / 50.0)))

func do_great_year() -> int:
	var g := aeons_on_reset()
	aeons += g; great_years += 1; total_starlight = 0.0
	reset_run(); changed.emit()
	return g


# ------------------------------------------------------------------ persistence
func to_dict() -> Dictionary:
	return {"v": 2, "ticks": ticks, "starlight": starlight, "total_ticks": total_ticks,
		"total_starlight": total_starlight, "levels": levels.duplicate(), "regulator": regulator,
		"weight": weight, "shaft": shaft, "rotor": rotor, "comps": comps.duplicate(), "stars": stars,
		"height": height, "aeons": aeons, "great_years": great_years, "play_time": play_time}

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
	stars = maxi(0, int(d.get("stars", 0)))
	height = clampf(float(d.get("height", shaft_height())), 0.0, shaft_height())
	aeons = maxi(0, int(d.get("aeons", 0))); great_years = maxi(0, int(d.get("great_years", 0)))
	play_time = float(d.get("play_time", 0.0))
