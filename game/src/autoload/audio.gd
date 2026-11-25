extends Node
## Audio director. Ticks follow the real beat of the escapement (capped at 6/s so a fast
## regulator becomes a soft texture instead of a machine gun: anti-fatigue rule of the vision).

const MAX_TICKS_PER_SEC := 6.0
var _streams := {}
var _pool: Array[AudioStreamPlayer] = []
var _beat_phase := 0.0
var _tock := false
var _room: AudioStreamPlayer
var eco: Economy


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for b in ["SFX", "Ambience"]:
		if AudioServer.get_bus_index(b) == -1:
			AudioServer.add_bus(); var i := AudioServer.bus_count - 1
			AudioServer.set_bus_name(i, b); AudioServer.set_bus_send(i, "Master")
	for i in 12:
		var p := AudioStreamPlayer.new(); p.bus = "SFX"; add_child(p); _pool.append(p)
	_room = AudioStreamPlayer.new(); _room.bus = "Ambience"; add_child(_room)
	var rt := _load("room_tone") as AudioStreamWAV
	if rt:
		rt.loop_mode = AudioStreamWAV.LOOP_FORWARD; rt.loop_end = rt.get_length() * rt.mix_rate
		_room.stream = rt; _room.volume_db = -14.0; _room.play()
	await get_tree().process_frame
	bind(Game.eco)


func bind(e: Economy) -> void:
	eco = e
	eco.purchased.connect(_on_purchase)


func _load(name: String) -> AudioStream:
	if not _streams.has(name):
		var path := "res://assets/audio/%s.wav" % name
		_streams[name] = load(path) if ResourceLoader.exists(path) else null
	return _streams[name]


func play(name: String, volume_db := 0.0, pitch := 1.0) -> void:
	var s := _load(name)
	if s == null:
		return
	for p in _pool:
		if not p.playing:
			p.stream = s; p.volume_db = volume_db; p.pitch_scale = pitch; p.play()
			return


func _on_purchase(kind: String, _id: String) -> void:
	match kind:
		"level", "unlock", "regulator": play("engage", -6.0, randf_range(0.96, 1.04))
		"weight", "shaft": play("stopwork", -8.0, randf_range(0.8, 0.9))
		"rotor": play("engage", -8.0, 1.2)
		"build": play("chime", -4.0)
		"comp_level": play("chime", -10.0, 1.5)
		"star": play("star_%d" % (eco.stars % 7), -4.0)


func wind_click(stopped: bool) -> void:
	if stopped:
		play("stopwork", -6.0)
	else:
		play("ratchet_%d" % randi_range(0, 2), -9.0, randf_range(0.95, 1.08))


func _process(delta: float) -> void:
	if eco == null:
		return
	var f := minf(eco.beat_freq(), MAX_TICKS_PER_SEC)
	_beat_phase += f * delta
	if _beat_phase >= 1.0:
		_beat_phase = fmod(_beat_phase, 1.0)
		var dense := eco.beat_freq() > MAX_TICKS_PER_SEC
		var vol := -12.0 if not dense else -17.0
		play(("tock_%d" if _tock else "tick_%d") % randi_range(0, 2), vol + randf_range(-1.5, 0.5), randf_range(0.97, 1.03))
		_tock = not _tock
