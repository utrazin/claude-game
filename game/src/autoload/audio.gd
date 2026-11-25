extends Node
## Audio director. Ticks follow the real beat of the escapement (capped at 6/s so a fast
## regulator becomes a soft texture instead of a machine gun: anti-fatigue rule of the vision).

const MAX_TICKS_PER_SEC := 6.0
var _streams := {}
var _pool: Array[AudioStreamPlayer] = []
var _beat_phase := 0.0
var _tock := false
var _room: AudioStreamPlayer
var _pad: AudioStreamPlayer
var _note_t := 0.0
var _sky := false
var _last_note := 0
var eco: Economy


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for b in ["SFX", "Ambience", "Music"]:
		if AudioServer.get_bus_index(b) == -1:
			AudioServer.add_bus(); var i := AudioServer.bus_count - 1
			AudioServer.set_bus_name(i, b); AudioServer.set_bus_send(i, "Master")
	# the tower is stone: every mechanical sound gets a short, dark room
	var rv := AudioEffectReverb.new(); rv.room_size = 0.55; rv.damping = 0.7; rv.wet = 0.16; rv.dry = 0.95
	rv.spread = 0.8; rv.hipass = 0.15
	AudioServer.add_bus_effect(AudioServer.get_bus_index("SFX"), rv)
	var mrv := AudioEffectReverb.new(); mrv.room_size = 0.85; mrv.damping = 0.5; mrv.wet = 0.35; mrv.dry = 0.8
	AudioServer.add_bus_effect(AudioServer.get_bus_index("Music"), mrv)
	for i in 16:
		var p := AudioStreamPlayer.new(); p.bus = "SFX"; add_child(p); _pool.append(p)
	_room = AudioStreamPlayer.new(); _room.bus = "Ambience"; add_child(_room)
	_loop(_room, "room_tone", -12.0)
	_pad = AudioStreamPlayer.new(); _pad.bus = "Music"; add_child(_pad)
	_loop(_pad, "pad", -20.0)
	_note_t = 4.0
	await get_tree().process_frame
	bind(Game.eco)


func _loop(p: AudioStreamPlayer, name: String, db: float) -> void:
	var w := _load(name) as AudioStreamWAV
	if w == null: return
	w.loop_mode = AudioStreamWAV.LOOP_FORWARD; w.loop_begin = 0; w.loop_end = int(w.get_length() * w.mix_rate)
	p.stream = w; p.volume_db = db; p.play()


## Observatory shot: the dome mechanism turns, the score opens up.
func sky_move(up: bool) -> void:
	_sky = up
	play("dome", -6.0 if up else -9.0, 1.0 if up else 0.88)
	var tw := create_tween().set_parallel()
	tw.tween_property(_pad, "volume_db", -13.0 if up else -20.0, 2.5)
	tw.tween_property(_room, "volume_db", -16.0 if up else -12.0, 2.5)
	_note_t = minf(_note_t, 1.2)


func _score(delta: float) -> void:
	# generative celesta: sparse, stepwise motifs in D dorian; denser under the open sky
	_note_t -= delta
	if _note_t > 0.0: return
	_note_t = randf_range(2.5, 5.0) if _sky else randf_range(7.0, 15.0)
	var step: int = [-2, -1, 1, 1, 2, 3, -3].pick_random()
	_last_note = clampi(_last_note + step, 0, 7)
	var p := _free()
	if p:
		p.bus = "Music"; p.stream = _load("note_%d" % _last_note); p.volume_db = randf_range(-20.0, -15.0); p.pitch_scale = 1.0; p.play()


func _free() -> AudioStreamPlayer:
	for p in _pool:
		if not p.playing: return p
	return null


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
	var p := _free()
	if p:
		p.bus = "SFX"; p.stream = s; p.volume_db = volume_db; p.pitch_scale = pitch; p.play()


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
	_score(delta)
	var f := minf(eco.beat_freq(), MAX_TICKS_PER_SEC)
	_beat_phase += f * delta
	if _beat_phase >= 1.0:
		_beat_phase = fmod(_beat_phase, 1.0)
		var dense := eco.beat_freq() > MAX_TICKS_PER_SEC
		var vol := -12.0 if not dense else -17.0
		play(("tock_%d" if _tock else "tick_%d") % randi_range(0, 2), vol + randf_range(-1.5, 0.5), randf_range(0.97, 1.03))
		_tock = not _tock
