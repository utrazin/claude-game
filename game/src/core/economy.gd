class_name Economy
extends RefCounted
## Pure economy model of ASTRARIUM. No nodes, no rendering: testable headless.
## All tuning comes from res://data/balance.json (shared with tools/sim/economy.py).

signal changed
signal purchased(kind: String, id: String)

var bal: Dictionary
var ticks := 0.0
var starlight := 0.0
var total_ticks := 0.0
var total_starlight := 0.0
var levels: Array[int] = []          ## per stage, 0 = locked
var drive := 0
var comps := {}                      ## id -> level (0 = not built)
var stars := 0
var reserve_level := 0
var overwind_left := 0.0
var aeons := 0
var great_years := 0
var play_time := 0.0


static func load_balance(path := "res://data/balance.json") -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	assert(f, "balance.json missing")
	return JSON.parse_string(f.get_as_text())


func _init(balance: Dictionary = {}) -> void:
	bal = balance if not balance.is_empty() else load_balance()
	reset_run()


func reset_run() -> void:
	ticks = 0.0; starlight = 0.0
	levels.clear()
	for i in bal.stages.size():
		levels.append(1 if i == 0 else 0)
	drive = 0
	comps.clear()
	for c in bal.complications:
		comps[c.id] = 0
	stars = 0
	overwind_left = 0.0


# ---------------------------------------------------------------- derived
func teeth(i: int) -> int:
	if levels[i] <= 0:
		return 0
	return int(bal.base_teeth + bal.teeth_per_level * (levels[i] - 1))


func ratio(i: int) -> float:
	return float(teeth(i)) / float(bal.pinion_teeth) if levels[i] > 0 else 1.0


func max_level() -> int:
	return int(bal.get("max_level", 19))


func load_total() -> float:
	var l := 0.0
	for i in levels.size():
		l += bal.stages[i].load * levels[i]
	return l


func power() -> float:
	return bal.drive.power0 * pow(bal.drive.power_growth, drive)


func efficiency() -> float:
	var l := load_total(); var p := power()
	return 1.0 if l <= p else pow(p / l, bal.efficiency_exponent)


func global_mult() -> float:
	var m := 1.0
	for c in bal.complications:
		if comps[c.id] > 0 and c.has("effect"):
			m *= c.effect.get("global_mult", 1.0)
	var st: Dictionary = bal.stars
	m *= 1.0 + st.add_each * stars
	m *= pow(st.constellation_bonus, stars / int(st.constellation_size))
	m *= 1.0 + bal.prestige.aeon_mult_each * aeons
	if overwind_left > 0.0:
		m *= bal.click.overwind_mult
	return m


func beat_rate() -> float:
	var r: float = bal.base_beat_rate
	for i in levels.size():
		if levels[i] > 0:
			r *= ratio(i)
	return r * efficiency() * global_mult()


func starlight_rate() -> float:
	var b := beat_rate(); var tot := 0.0
	for c in bal.complications:
		var lv: int = comps[c.id]
		if lv > 0 and c.has("starlight_coef"):
			tot += c.starlight_coef * lv * pow(b, c.starlight_exp)
	return tot


func reserve_hours() -> float:
	return bal.offline.hours0 + bal.offline.hours_per_level * reserve_level


# ---------------------------------------------------------------- simulation
func tick(dt: float) -> void:
	var b := beat_rate()
	var s := starlight_rate()
	ticks += b * dt; total_ticks += b * dt
	starlight += s * dt; total_starlight += s * dt
	overwind_left = maxf(0.0, overwind_left - dt)
	play_time += dt


## Manual winding. Returns ticks gained.
func wind() -> float:
	var g: float = bal.click.ticks_per_wind + beat_rate() * bal.click.wind_seconds_of_production
	ticks += g; total_ticks += g
	changed.emit()
	return g


func start_overwind() -> void:
	overwind_left = bal.click.overwind_seconds
	changed.emit()


## Offline progress. Returns {seconds, ticks, starlight}.
func apply_offline(seconds: float) -> Dictionary:
	var s := clampf(seconds, 0.0, reserve_hours() * 3600.0)
	var e: float = bal.offline.efficiency
	var gt := beat_rate() * s * e
	var gs := starlight_rate() * s * e
	ticks += gt; total_ticks += gt; starlight += gs; total_starlight += gs
	changed.emit()
	return {"seconds": s, "requested": seconds, "ticks": gt, "starlight": gs}


# ---------------------------------------------------------------- shop
## Every purchasable option is described by a Dictionary:
## {kind, id, currency ("ticks"|"starlight"), cost, available}
func stage_option(i: int) -> Dictionary:
	var st: Dictionary = bal.stages[i]
	if levels[i] == 0:
		return {"kind": "unlock", "id": st.id, "index": i, "currency": "ticks", "cost": float(st.unlock),
			"available": i == 0 or levels[i - 1] > 0}
	if levels[i] >= max_level():
		return {"kind": "level", "id": st.id, "index": i, "currency": "ticks", "cost": INF, "available": false, "maxed": true}
	return {"kind": "level", "id": st.id, "index": i, "currency": "ticks",
		"cost": st.cost0 * pow(st.growth, levels[i]), "available": true}


func drive_option() -> Dictionary:
	return {"kind": "drive", "id": "drive", "currency": "ticks",
		"cost": bal.drive.cost0 * pow(bal.drive.growth, drive), "available": true}


func comp_option(c: Dictionary) -> Dictionary:
	var lv: int = comps[c.id]
	if lv == 0:
		return {"kind": "build", "id": c.id, "currency": "ticks", "cost": float(c.cost), "available": true}
	if c.has("level_cost0"):
		return {"kind": "comp_level", "id": c.id, "currency": "ticks",
			"cost": c.level_cost0 * pow(c.level_growth, lv - 1), "available": true}
	return {"kind": "built", "id": c.id, "currency": "ticks", "cost": INF, "available": false}


func star_option() -> Dictionary:
	var any_celestial := false
	for c in bal.complications:
		if comps[c.id] > 0 and c.has("starlight_coef"):
			any_celestial = true
	return {"kind": "star", "id": "star", "currency": "starlight",
		"cost": bal.stars.cost0 * pow(bal.stars.growth, stars), "available": any_celestial}


func reserve_option() -> Dictionary:
	return {"kind": "reserve", "id": "reserve", "currency": "ticks",
		"cost": bal.offline.cost0 * pow(bal.offline.growth, reserve_level), "available": true}


func can_afford(o: Dictionary) -> bool:
	if not o.available:
		return false
	return (ticks if o.currency == "ticks" else starlight) >= o.cost


func buy(o: Dictionary) -> bool:
	if not can_afford(o):
		return false
	if o.currency == "ticks":
		ticks -= o.cost
	else:
		starlight -= o.cost
	match o.kind:
		"unlock": levels[o.index] = 1
		"level": levels[o.index] += 1
		"drive": drive += 1
		"build", "comp_level": comps[o.id] += 1
		"star": stars += 1
		"reserve": reserve_level += 1
	purchased.emit(o.kind, o.id)
	changed.emit()
	return true


# ---------------------------------------------------------------- prestige
func great_year_ready() -> bool:
	var need: int = bal.prestige.requires_constellations * int(bal.stars.constellation_size)
	return stars >= need and comps.get("mercury", 0) > 0


func aeons_on_reset() -> int:
	return int(floor(pow(total_starlight / bal.prestige.aeon_divisor, bal.prestige.aeon_exp)))


func do_great_year() -> int:
	var gained := aeons_on_reset()
	aeons += gained
	great_years += 1
	total_starlight = 0.0
	reset_run()
	changed.emit()
	return gained


# ---------------------------------------------------------------- persistence
func to_dict() -> Dictionary:
	return {"v": 1, "ticks": ticks, "starlight": starlight, "total_ticks": total_ticks,
		"total_starlight": total_starlight, "levels": levels.duplicate(), "drive": drive,
		"comps": comps.duplicate(), "stars": stars, "reserve_level": reserve_level,
		"aeons": aeons, "great_years": great_years, "play_time": play_time}


func from_dict(d: Dictionary) -> void:
	reset_run()
	ticks = float(d.get("ticks", 0.0)); starlight = float(d.get("starlight", 0.0))
	total_ticks = float(d.get("total_ticks", 0.0)); total_starlight = float(d.get("total_starlight", 0.0))
	var lv: Array = d.get("levels", [])
	for i in mini(lv.size(), levels.size()):
		levels[i] = clampi(int(lv[i]), 0, max_level())
	if levels[0] == 0:
		levels[0] = 1
	drive = int(d.get("drive", 0))
	var cs: Dictionary = d.get("comps", {})
	for k in cs:
		if comps.has(k):
			comps[k] = int(cs[k])
	stars = int(d.get("stars", 0)); reserve_level = int(d.get("reserve_level", 0))
	aeons = int(d.get("aeons", 0)); great_years = int(d.get("great_years", 0))
	play_time = float(d.get("play_time", 0.0))
