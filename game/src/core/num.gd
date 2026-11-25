class_name Num
## Number formatting for large values. Short scale names up to decillion, then
## engineering-style scientific notation. Always 3 significant digits.

const SUFFIXES := ["", "K", "M", "B", "T", "Qa", "Qi", "Sx", "Sp", "Oc", "No", "Dc"]


static func fmt(v: float) -> String:
	if is_inf(v):
		return "∞"
	if is_nan(v):
		return "—"
	var a := absf(v)
	if a < 1000.0:
		if a < 10.0 and a != floorf(a):
			return "%.2f" % v if a < 1.0 else "%.1f" % v
		return str(int(floor(v)))
	var e := int(floor(log(a) / log(1000.0)))
	if e < SUFFIXES.size():
		var m := v / pow(1000.0, e)
		var digits := 2 if absf(m) < 10.0 else (1 if absf(m) < 100.0 else 0)
		return ("%." + str(digits) + "f%s") % [m, SUFFIXES[e]]
	var exp10 := int(floor(log(a) / log(10.0)))
	return "%.2fe%d" % [v / pow(10.0, exp10), exp10]


static func duration(seconds: float) -> String:
	var s := int(seconds)
	if s < 60:
		return "%ds" % s
	if s < 3600:
		return "%dm %02ds" % [s / 60, s % 60]
	return "%dh %02dm" % [s / 3600, (s % 3600) / 60]
