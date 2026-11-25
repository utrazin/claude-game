# Procedural Fields (noise, masks, dithering)

Compose varied patterns (stone, wood, cloth, rust, moss, scales, clouds...) from small parts instead of hand-writing noise per recipe. The same expression makes pixel art (dithered, palette only) or painted textures (smooth). Full signatures: [generated TexturePainter reference](../../../../docs/api/texture-painter.md) (`Field`, `Shader`). This is the default way to make procedural variation in this repository; ask an external producer only when the user explicitly requests it ([art requests](art-requests.md)).

## Model
```
generator (where is the pattern)  ->  operators (shape it)  ->  output (colors)  ->  paint_field / image
Field.cells(...)                      .warp .fbm .contrast      .ramp / .dither     element.paint_field(shader)
```
- A `Field` returns values in [0, 1] for positions. It never knows about faces or pixels, so a pattern is **continuous across faces and elements** when evaluated in model space.
- `scale` is features per model unit (`scale=2` gives a feature every half unit). Units follow the painted `space`: `model` (default), `element`, `normalized` (0..1 per element) or `uv` (atlas pixels).
- Everything is deterministic: same expression, same seeds, same values on every run. Change `seed=` for another variation of the same look.
- Cost: one batched numpy evaluation per `paint_field` call (a heavy 4-layer expression over a whole 900k-texel asset takes a few seconds). Never loop over texels in Python for this.

```python
# example: field-basics
rock = (Field.cells(0.75, seed=1, mode="edge").invert().threshold(0.9, 0.1)
        .mix(Field.gradient(1.5, seed=2).fbm(4), 0.5))   # scale * tile length must be whole: 0.75 * 4 = 3
shader = rock.ramp(["#2b2a33", "#5b5963", "#9c99a4"])           # painted: smooth
painter.body.paint_field(shader)                                   # on the model
painter.cap.paint_field(Field.value(2).dither(["#222", "#888", "#ddd"], "blue"))   # pixel art
tile = shader.image((256, 256), extent=(4, 4), tileable=True)      # seamless PNG for project_triplanar
```

## Generators (`Field.<name>(...)`)
| Generator | Looks like | Main controls |
|---|---|---|
| `value(scale, seed, stretch)` | soft round blobs | `stretch=(1, 6, 1)` for streaks |
| `gradient(scale, seed, stretch)` | finer, less blobby (Perlin-style); base for `fbm`/`ridge` | same |
| `cells(scale, seed, mode, jitter, metric)` | `f1` bubbles/scales, `f2` plates, `edge` cracks and mortar, `id` flat patches | `jitter=0` regular grid; `metric` manhattan/chebyshev gives diamonds/squares |
| `white(scale, seed)` | speckle, grain, per-patch random value | high `scale` for fine grain |
| `stripes(frequency, direction, shape, duty)` | bands, weave, planks | `shape` saw/sine/triangle/square; bend with `warp` |
| `rings(center, frequency, axis)` | tree rings, ripples | `axis="y"` for cylinders |
| `height(axis, low, high)` | 0..1 along an axis | dripping, ground contact, gradients |
| `facing(direction, power)` | surface turned toward a direction (needs normals: inside `paint_field`) | moss on top, dust, sun side |
| `constant(v)` | the same value | bias a `mix` |
| `from_function(fn)` / `from_frame_function(fn)` | anything you write | see "Extending" |

## Operators (return a new `Field`)
| Operator | Effect |
|---|---|
| `fbm(octaves, lacunarity, gain)` | detail on detail; fewer octaves read smoother, higher `gain` rougher |
| `warp(by, strength)` | bends the pattern with another field (strength in units); the biggest step away from "cloudy" |
| `ridge(sharpness)` / `billow()` | fold into creases / round lumps; `.ridge().fbm()` gives veins, ridges |
| `remap(low, high)`, `contrast(amount, pivot)`, `gamma(p)`, `curve(points)` | reshape the value distribution |
| `threshold(at, softness)`, `steps(n)`, `invert()`, `clip()` | hard shapes, posterize, flip |
| `mix(other, by)`, `+ - *`, `\|` max, `&` min, `~` | combine fields; `by` may be a field used as a mask |
| `scale`, `stretch`, `offset`, `rotate` | transform coordinates (`rotate` blocks seamless tiles) |

## Outputs
| Output | Use |
|---|---|
| `field.ramp(colors, stops=None, smooth=True)` | values to colors; `smooth=False` gives hard bands (cel/pixel look) |
| `field.dither(colors, method, scale=1, strength=1)` | picks between neighboring palette colors: pixel-art texture from only those colors |
| `shader.masked(field)` | alpha multiplied by a field; paint only where it is high |
| `shader.over(below)` | alpha-composite several shaders into one layered surface |
| `shader.image(size, extent, z, tileable)` / `field.image(...)` | RGBA / grayscale image, for tiles, masks and previews |
| `element.paint_field(shader, space, where, blend, opacity)` | paint on any element, face group, selection or region (`painter.select(tag=...)`, `element.band(...)`), also inside `with painter.layer(...)` |

`where` limits painting: a `Field` (soft mask) or `lambda rows: bool_array` (same `rows` as `paint_surface_arrays`).

## Dither methods
| Method | Character |
|---|---|
| `bayer2`, `bayer4`, `bayer8` | regular crosshatch grids; 8 is finest |
| `blue` | even, organic grain without grid or clumps (best default for natural surfaces) |
| `white` | harsh random grain |
| `ign` | soft diagonal grain |
| `cluster` | halftone dots |
| `lines`, `diagonal` | engraved hatching |
| `floyd`, `atkinson` | error diffusion, **images only** (`Shader.image`); atkinson keeps more contrast |

`scale=2` makes pattern pixels 2 canvas pixels wide; `strength=0` removes the pattern (hard bands), values between blend. The pattern is anchored to each face's canvas pixels, so it is regular within a face and restarts on the next; use `blue`/`white` when that matters. Keep one palette per material so dithered and flat areas share colors.

## Make it look different (when everything looks the same)
| Symptom | Change |
|---|---|
| Blobby clouds everywhere | `warp` with a lower-scale field; switch generator (`cells`, `stripes`); add `ridge`/`billow` |
| Repeating dither | `blue` or `ign` instead of `bayer`; change `scale`; `strength` 0.6 |
| Uniform noise | `mix` two scales; multiply by `height`/`facing`; use a `where` mask |
| Looks digital | `stretch` the field (anisotropy), add `white` grain at low strength, add a second layer with `over` |
| Too smooth / too busy | fewer / more `fbm` octaves; `contrast`; `remap` to crop ends |
| Pattern follows UV not form | evaluate in `space="model"` (default) instead of `uv` |

## Recipes
`py -3.12 -m Tools.field_gallery out.png [--style pixel|painted|both] [--only stone,wood]` renders every expression below as seamless tiles in both styles; `Tools/field_gallery.py` holds them as copyable code (`RECIPES`, `shader(name, style)`). Each is a starting point: change scales, seeds and palette.

| Recipe | Idea |
|---|---|
| stone | `cells` cracks (edge, inverted, thresholded) over `gradient.fbm` and per-cell patches |
| wood | `stripes` warped by `gradient.fbm`, plus stretched `value` fibers |
| cloth | two triangle `stripes` multiplied (weave) over low-contrast noise |
| rust | warped `gradient.fbm` blotches times `height` falloff, plus `white` pits |
| moss | `gradient.fbm` times `height`, plus sparse `white` tufts |
| scales | inverted `cells` with low jitter plus `id` tint |
| sand | `white` grain over stretched `gradient` ripples |
| fur | stretched `value` plus noise |
| marble | warped `stripes` folded with `ridge(3)` |
| leather | high-jitter `cells` plus fine noise |
| clouds | warped `value.fbm` folded with `billow` |

## Seamless tiles
`shader.image(size, extent=(L, L), tileable=True)` makes a tile that repeats exactly every `L` units; project it with `project_triplanar(img, scale=1 / L)` or `project_planar`. Rules: every generator must fit a whole number of cells in `L` (`scale * L` integer; use integer `lacunarity`, default 2); stripes need whole repeats; `rotate`, `rings` and `from_function` cannot tile (an error tells which). Painting directly with `paint_field` in model space never repeats, so prefer it for large surfaces and use tiles when a projected image is wanted.

## Extending per project
Compose first; most looks need no new code. For behavior the core does not offer:
```python
# example: field-extension
import numpy as np
from Tools.TexturePainter.fields import hash_cells, unit_hash

def planks(width=1.0, seed=0):
    """Horizontal planks: random tone per plank row plus a dark seam between them."""
    def evaluate(frame):                       # frame.x/y/z arrays, frame.normal, frame.pixel, frame.wrap
        row = np.floor(frame.y / width).astype(np.int64)
        tone = unit_hash(row, 0, 0, seed)
        seam = np.abs(frame.y / width - row - 0.5) > 0.47
        return np.where(seam, 0.0, 0.3 + 0.7 * tone)
    return Field.from_frame_function(evaluate, "planks")

shader = planks(0.5).warp(Field.gradient(2), 0.05).mix(Field.gradient(6).fbm(3), 0.2).ramp(["#2a1a10", "#8b5a35"])
painter.body.paint_field(shader)
```
- `Field.from_function(fn)`: `fn(x, y, z)` on float arrays, returns values in [0, 1]. `Field.from_frame_function(fn)`: `fn(frame)` also gets `frame.normal` (N, 3 when painting), `frame.pixel` (canvas x, y) and `frame.wrap` (tile lengths or None: raise or honor it when tiling).
- Use `hash_cells`/`unit_hash` (integer cell coordinates plus a seed) for any random value so results stay deterministic. Never use `random` or unseeded numpy.
- Everything stays vectorized: write array math, not per-texel loops. Keep returned values finite and within [0, 1] (errors name the field).
- Project-only generators live next to the recipe (for example `scripts/<asset>/fields_local.py`, imported like `generate_model`). Promote one to the core only when more than one project needs it, with a stability test of its values.
- Stability rule: a generator's values are a contract (recipes depend on them). Fix behavior only by adding a new generator name.
- For one-off arrays beyond fields, `paint_surface_arrays(callback)` remains the escape hatch; a `Shader.render(Frame(...))` can be called inside it.

## Common mistakes
- Passing a `Field` to `paint_field`: finish with `.ramp(...)` or `.dither(...)`.
- Colors as 0..1 floats: colors are hex strings or 0-255 tuples.
- `facing` or `dither` outside `paint_field`/`image`: they need surface normals or canvas pixels.
- Tiling a field with a non-integer cell count: pick `scale` and `L` so `scale * L` is whole.
- Old `apply_noise(variance)` still exists for plain per-texel brightness jitter; use fields for anything structured.
