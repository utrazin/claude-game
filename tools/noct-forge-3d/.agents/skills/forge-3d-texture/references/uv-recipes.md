# UV recipes: density, layout and packing per region

Without a UV recipe every face takes the automatic packing (one `uv_scale`, `faces` or `charts`). Write a recipe
only when the asset needs a different plan: flat-coloured parts that waste atlas space, a face drawn at a fixed
size, a region painted finer than the rest, a readable atlas layout.

`scripts/<asset>/generate_uv.py` (`forge uv` runs it; `--dry-run` writes nothing, `--no-recipe` ignores it):

```python
from Tools.recipe_context import recipe_paths
from Tools.uv_builder import UVBuilder

uv = UVBuilder(recipe_paths(__file__).model, uv_scale=4, island_padding=1, packer="grouped").clear()
uv.rule(tag="flat", layout="flat")                                   # each flat part: one texel
uv.rule(element="head", density=8)                                   # head painted twice as fine
uv.rule(element="head", face="north", layout="fixed", size=(32, 32), pin=(1, 1))   # face drawing
uv.save(verbose=True)
```

The constructor options are the defaults of every face no rule changes. `clear()` starts from an empty plan (saved
rules and `share_uv` pairs are otherwise kept). Rules are saved in the BBModel (`uv_packing.rules`), so a later
`forge uv --no-recipe` repeats them; regenerating geometry drops them and the recipe restores them.

## Rules

`uv.rule(**selectors, **attributes)`: for every face, the last matching rule wins, attribute by attribute.
A rule that selects no face is an error.

| Selector (glob) | Matches |
|---|---|
| `element` | element name (`arm_*`) |
| `tag` | a `model_as_code_tags` entry |
| `parent` | any outliner group above the element |
| `face` | face name (`north`, `side_000`, ...) |
| `face_group` | `model_as_code_group` of a mesh face |

| Attribute | Values |
|---|---|
| `density` | pixels per model unit (positive integer) for these faces |
| `layout` | `box` (cube cross, cube default), `faces`, `charts` (mesh only, fractional UVs), `flat`, `fixed` |
| `per` | `flat` only: `element` (default), `face` or `rule` (every face the rule selects shares one island) |
| `size` | `(w, h)` pixels: a `fixed` face's island, a `flat` island (default `(1, 1)`) |
| `pin` | `(u, v)`: atlas position of the island's content; exactly one island |
| `block` | `grouped` packer: islands of one block stay together (default: the element's parent group) |
| `texture` | atlas slot name (identifier, default `"default"`): packs selected faces into their own independent PNG atlas |

- **A cube with mixed rules.** Its faces resolve differently (one `fixed` face, two densities), so the cross splits
  into one island per face.
- **`charts` in a mesh with several densities.** The mesh unfolds one chart set per density.
- **`flat`.** Faces show their owner's island (`uv_sharing` entries with `region: true`, rebuilt on every packing).
  Paint the owner: `element.fill_all(...)`, `select(tag=...).fill(...)`. Spatial painting skips the other faces,
  and a region is one colour by design.
- **`share_uv`.** It still works with the `faces`/`box` layouts. Both faces need the same rules, and it is refused
  on `flat`, `fixed` and `charts` faces.
- **Multiple textures (`texture="<slot>"`).** Different objects or different faces of the same cube/mesh can be packed into separate texture slots (`uv.rule(element="head", face="north", texture="face")`), each with its own POT atlas size.

## Packers

| `packer` | Atlas |
|---|---|
| `maxrects` | default, tightest |
| `shelf` | rows in document order, predictable between runs |
| `grouped` | each `block` packed together, then the blocks: a readable atlas to retouch by hand |

Pinned islands keep their position in every packer. Check the space each layout takes with
`forge uv PROJECT --asset ID --dry-run` (`texels {...}` per layout).

## Painting with mixed densities

Strokes, stamps and front-layer masks measure widths in texels of the faces they paint
(`painter.texel_density(...)`). A stroke that crosses regions of different densities uses the density of most of
its texels. A twin (`forge asset twin`) keeps the source's rules; give it its own `generate_uv.py` when it needs
other densities.
