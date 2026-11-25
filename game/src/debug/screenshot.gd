extends Node
## Capture helper. Run: xvfb-run godot --path game -- --shot=<png> [--wait=<s>] [--state=<json>]
## --state preloads an economy dict (for capturing later game states).

func _ready() -> void:
	var args := {}
	for a in OS.get_cmdline_user_args():
		var kv := a.trim_prefix("--").split("=", true, 1)
		args[kv[0]] = kv[1] if kv.size() > 1 else ""
	if not args.has("shot"):
		queue_free(); return
	if args.has("state"):
		var d = JSON.parse_string(FileAccess.get_file_as_string(args.state))
		Game.eco.from_dict(d)
		Game.eco.purchased.emit("load", "")
		Game.eco.changed.emit()
	if args.has("lookup"):
		await get_tree().create_timer(0.3).timeout
		get_tree().current_scene.cam.look_up(true)
	await get_tree().create_timer(float(args.get("wait", "2.0"))).timeout
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png(args.shot)
	print("SHOT ", args.shot)
	get_tree().quit()
