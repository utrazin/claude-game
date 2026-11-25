class_name Mats
## Central material library. Calibrated in look-dev; every 3D asset uses these.

static var _cache := {}


static func brass() -> StandardMaterial3D:
	return _mat("brass", func():
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.80, 0.60, 0.33)
		m.metallic = 1.0; m.roughness = 0.28
		m.anisotropy_enabled = true; m.anisotropy = 0.35
		return m)


static func brass_aged() -> StandardMaterial3D:
	return _mat("brass_aged", func():
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.55, 0.42, 0.24)
		m.metallic = 1.0; m.roughness = 0.45
		return m)


static func blued_steel() -> StandardMaterial3D:
	return _mat("blued", func():
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.17, 0.25, 0.47)
		m.metallic = 1.0; m.roughness = 0.22
		return m)


static func steel() -> StandardMaterial3D:
	return _mat("steel", func():
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.72, 0.72, 0.74)
		m.metallic = 1.0; m.roughness = 0.18
		return m)


static func enamel() -> StandardMaterial3D:
	return _mat("enamel", func():
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.93, 0.90, 0.84)
		m.roughness = 0.12; m.clearcoat_enabled = true; m.clearcoat = 0.8
		return m)


static func walnut() -> StandardMaterial3D:
	return _mat("walnut", func():
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.23, 0.14, 0.085)
		m.roughness = 0.5; m.clearcoat_enabled = true; m.clearcoat = 0.35; m.clearcoat_roughness = 0.4
		return m)


static func lead() -> StandardMaterial3D:
	return _mat("lead", func():
		var m := StandardMaterial3D.new()
		m.albedo_color = Color(0.28, 0.29, 0.31)
		m.metallic = 0.6; m.roughness = 0.6
		return m)


static func _mat(key: String, make: Callable) -> StandardMaterial3D:
	if not _cache.has(key):
		_cache[key] = make.call()
	return _cache[key]


static func apply(node: Node, mat: Material) -> void:
	for mi in node.find_children("*", "MeshInstance3D", true, false):
		(mi as MeshInstance3D).material_override = mat
	if node is MeshInstance3D:
		(node as MeshInstance3D).material_override = mat
