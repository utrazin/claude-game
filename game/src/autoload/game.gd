extends Node
## Global game state: owns the Economy, the fixed-step simulation, saving,
## loading and offline progress. Everything visual listens to signals here.

signal offline_report(report: Dictionary)
signal saved

const SAVE_PATH := "user://astrarium_save.json"
const STEP := 0.1                 ## simulation step (s)
const AUTOSAVE_SECONDS := 30.0

var eco: Economy
var _acc := 0.0
var _autosave := 0.0
var headless_test := false


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	eco = Economy.new()
	if not headless_test and not OS.has_feature("no_save"):
		load_game()


func _process(delta: float) -> void:
	_acc += minf(delta, 1.0)
	while _acc >= STEP:
		eco.tick(STEP)
		_acc -= STEP
	_autosave += delta
	if _autosave >= AUTOSAVE_SECONDS:
		_autosave = 0.0
		save_game()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST or what == NOTIFICATION_APPLICATION_PAUSED:
		save_game()


func save_game() -> bool:
	var data := eco.to_dict()
	data["saved_at"] = Time.get_unix_time_from_system()
	var tmp := SAVE_PATH + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		push_error("save failed: %s" % FileAccess.get_open_error())
		return false
	f.store_string(JSON.stringify(data))
	f.close()
	var dir := DirAccess.open("user://")
	if dir.file_exists(SAVE_PATH.get_file()):
		dir.copy(SAVE_PATH, SAVE_PATH + ".bak")
	var err := dir.rename(tmp.get_file(), SAVE_PATH.get_file())
	if err != OK:
		push_error("save rename failed: %d" % err)
		return false
	saved.emit()
	return true


## Fresh start: wipes the run and the save (the menu asks for confirmation first).
func new_game() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(Settings.PATH) == OK and cfg.has_section("tutorial"):
		cfg.erase_section("tutorial"); cfg.save(Settings.PATH)
	eco.from_dict({})
	eco.purchased.emit("load", "")
	eco.changed.emit()
	var dir := DirAccess.open("user://")
	for f in [SAVE_PATH.get_file(), SAVE_PATH.get_file() + ".bak"]:
		if dir.file_exists(f): dir.remove(f)
	save_game()


func has_progress() -> bool:
	return eco.total_ticks > 0.0


func load_game() -> bool:
	for path in [SAVE_PATH, SAVE_PATH + ".bak"]:
		if not FileAccess.file_exists(path):
			continue
		var txt := FileAccess.get_file_as_string(path)
		var d = JSON.parse_string(txt)
		if typeof(d) != TYPE_DICTIONARY:
			push_warning("corrupt save at %s, trying backup" % path)
			continue
		eco.from_dict(d)
		var away := Time.get_unix_time_from_system() - float(d.get("saved_at", Time.get_unix_time_from_system()))
		if away > 30.0:
			var rep := eco.apply_offline(away)
			offline_report.emit.call_deferred(rep)
		return true
	return false


func wipe_save() -> void:
	for p in [SAVE_PATH, SAVE_PATH + ".bak"]:
		if FileAccess.file_exists(p):
			DirAccess.remove_absolute(ProjectSettings.globalize_path(p))
	eco = Economy.new()
