extends Node
## Capture helper. Run: xvfb-run godot --path game -- --shot=<png> [--wait=<s>] [--state=<json>]
## --state preloads an economy dict (for capturing later game states).

func _ready() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else ""
	if args.has("autoplay"):
		await _autoplay(int(args.autoplay))
		if not args.has("shot"):
			get_tree().quit(); return
	if args.has("perf"):   # render cost snapshot (draw calls / primitives / objects) at the current quality
		await get_tree().create_timer(3.0).timeout
		var rs := RenderingServer
		print("PERF draw_calls=%d primitives=%d objects=%d vram_MB=%.0f" % [
			rs.get_rendering_info(rs.RENDERING_INFO_TOTAL_DRAW_CALLS_IN_FRAME),
			rs.get_rendering_info(rs.RENDERING_INFO_TOTAL_PRIMITIVES_IN_FRAME),
			rs.get_rendering_info(rs.RENDERING_INFO_TOTAL_OBJECTS_IN_FRAME),
			rs.get_rendering_info(rs.RENDERING_INFO_VIDEO_MEM_USED) / 1048576.0])
		get_tree().quit(); return
	if not args.has("shot"):
		queue_free(); return
	if args.has("state"):
		var d = JSON.parse_string(FileAccess.get_file_as_string(args.state))
		Game.eco.from_dict(d)
		Game.eco.purchased.emit("load", "")
		Game.eco.changed.emit()
	if args.has("qa"):   # open a specific panel for QA captures: gy | finale
		await get_tree().create_timer(0.5).timeout
		var hud: Node = get_tree().current_scene.get_node("HUD")
		match args.qa:
			"gy": hud.call("_confirm_great_year")
			"finale":
				for c in Game.eco.bal.sky.constellations:
					for i in c.stars.size(): Game.eco.lit.append("%s:%d" % [c.id, i])
				Game.eco.finale_seen = false; Game.eco.changed.emit()
	if args.has("lookup"):
		await get_tree().create_timer(0.3).timeout
		get_tree().current_scene._on_look_up(true)
	if args.has("seq"):   # frames of the observatory shot: --seq=<prefix>
		await get_tree().create_timer(1.0).timeout
		get_tree().current_scene._on_look_up(true)
		for k in 5:
			await get_tree().create_timer(0.8).timeout
			await RenderingServer.frame_post_draw
			get_viewport().get_texture().get_image().save_png("%s_%d.png" % [args.seq, k])
	await get_tree().create_timer(float(args.get("wait", "2.0"))).timeout
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(args.shot)
	print("SHOT ", args.shot)
	get_tree().quit()


## QA: presses the bench buttons like a player (first affordable, top to bottom) and logs frame cost.
func _autoplay(n: int) -> void:
	await get_tree().create_timer(1.0).timeout
	var hud: Node = get_tree().current_scene.get_node("HUD")
	for i in n:
		Game.eco.ticks += 1e9
		await get_tree().process_frame
		var bought := ""
		var keys: Array = hud.rows.keys()
		for j in keys.size():
			var k: String = keys[(i + j) % keys.size()]
			var b: Button = hud.rows[k].button
			if not b.disabled:
				var t0 := Time.get_ticks_usec()
				b.pressed.emit()
				await get_tree().process_frame
				await get_tree().process_frame
				bought = k + " (%.1f ms)" % ((Time.get_ticks_usec() - t0) / 1000.0)
				break
		var ts := Time.get_ticks_usec()
		for f in 30: await get_tree().process_frame
		print("AUTO #%d %s  | 30 frames: %.1f ms/frame" % [i + 1, bought, (Time.get_ticks_usec() - ts) / 30000.0])
