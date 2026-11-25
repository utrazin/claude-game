shader_type spatial;
// Turned / brushed brass for clock wheels. Mesh-local axis is +Y (GLB from tools/blender/gear.py).
// Circular brushing in roughness + anisotropy flowing around the axis, subtle tarnish in low areas.

uniform vec3 base_color : source_color = vec3(0.86, 0.70, 0.40);
uniform vec3 tarnish_color : source_color = vec3(0.42, 0.33, 0.18);
uniform float metallic_v = 0.85;
uniform float roughness_v = 0.28;
uniform float brush_strength = 0.12;
uniform float tarnish = 0.25;

varying vec3 lp;

float hash(float n) { return fract(sin(n) * 43758.5453); }
float noise1(float x) { float i = floor(x); float f = fract(x); return mix(hash(i), hash(i + 1.0), smoothstep(0.0, 1.0, f)); }
float hash2(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
	vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash2(i), hash2(i + vec2(1, 0)), f.x), mix(hash2(i + vec2(0, 1)), hash2(i + vec2(1, 1)), f.x), f.y);
}

void vertex() {
	lp = VERTEX;
}

void fragment() {
	float r = length(lp.xz);
	// concentric lathe marks: fine radial frequency noise
	float brush = noise1(r * 900.0) * 0.6 + noise1(r * 2600.0) * 0.4;
	// broad tarnish blotches
	float blot = vnoise(lp.xz * 7.0) * 0.6 + vnoise(lp.xz * 23.0) * 0.4;
	float t = smoothstep(0.55, 0.95, blot) * tarnish;
	ALBEDO = mix(base_color * (0.92 + 0.12 * brush), tarnish_color, t);
	METALLIC = metallic_v;
	ROUGHNESS = clamp(roughness_v + (brush - 0.5) * brush_strength + t * 0.25, 0.05, 1.0);
	// anisotropy flowing around the wheel axis (tangential direction in tangent space approx)
	ANISOTROPY = 0.45;
	vec2 tang = normalize(vec2(-lp.z, lp.x) + 1e-5);
	ANISOTROPY_FLOW = tang;
}
