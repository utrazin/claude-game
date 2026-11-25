shader_type sky;
// Night sky of ASTRARIUM. `awake` (0..1) is driven by progression: stars and the
// milky band fade in as the player restores the firmament.

uniform vec3 zenith : source_color = vec3(0.012, 0.022, 0.06);
uniform vec3 horizon : source_color = vec3(0.04, 0.055, 0.11);
uniform vec3 ground : source_color = vec3(0.02, 0.015, 0.012);
uniform float awake : hint_range(0.0, 1.0) = 0.15;
uniform float star_density = 260.0;

float hash(vec3 p) {
	p = fract(p * 0.3183099 + 0.1);
	p *= 17.0;
	return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float stars(vec3 dir, float scale, float threshold) {
	vec3 p = dir * scale;
	vec3 cell = floor(p);
	vec3 f = fract(p) - 0.5;
	float h = hash(cell);
	if (h < threshold) return 0.0;
	vec3 off = vec3(hash(cell + 3.1), hash(cell + 7.7), hash(cell + 1.3)) - 0.5;
	float d = length(f - off * 0.6);
	float bright = (h - threshold) / (1.0 - threshold);
	return smoothstep(0.08, 0.0, d) * bright;
}

void sky() {
	vec3 d = EYEDIR;
	float up = clamp(d.y, -1.0, 1.0);
	vec3 col = mix(horizon, zenith, smoothstep(0.0, 0.7, up));
	if (up < 0.0) col = mix(horizon * 0.6, ground, smoothstep(0.0, 0.3, -up));
	if (!AT_CUBEMAP_PASS) {
		// milky band along a tilted great circle
		vec3 n = normalize(vec3(0.35, 0.25, 0.9));
		float band = exp(-pow(dot(d, n) * 4.0, 2.0));
		float grain = hash(floor(d * 400.0));
		col += vec3(0.08, 0.09, 0.16) * band * (0.6 + 0.4 * grain) * awake * smoothstep(-0.05, 0.2, up);
		// stars: faint ones always (dim), bright ones appear with awake
		float s1 = stars(d, star_density, 1.0 - 0.06);
		float s2 = stars(d, star_density * 0.5, 1.0 - 0.10 * awake);
		float tw = 0.75 + 0.25 * sin(TIME * 2.0 + hash(floor(d * star_density)) * 30.0);
		col += vec3(0.85, 0.88, 1.0) * s1 * 0.25 * smoothstep(0.0, 0.15, up);
		col += vec3(1.0, 0.92, 0.75) * s2 * 3.0 * tw * awake * smoothstep(0.0, 0.15, up);
	}
	COLOR = col;
}
