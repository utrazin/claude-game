# Art Requests (external producer)

Use this **only when the user explicitly asks** for images made elsewhere (the 2D asset forge, another tool, a person) and gives where they will be produced. Otherwise every texture, pixel art or painted, is made by the recipe in this repository.

The request is a hand-off between two independent processes: this repository writes `projects/<name>/art.json` and later pulls finished PNGs; the producer only receives the path of `art.json` (or the `prompt` text) and never needs to know this repository. How an image is printed on the model is decided by the texture recipe, not by the manifest.

## Manifest template
```json
{
  "schema": 2,
  "source": "../path/where/the/producer/saves/images",
  "requests": {
    "face": {
      "asset": "hero",
      "description": "Angry glowing mint eyes, heavy brow, small pink nose, scowling mouth. Soft hand-painted look, NOT pixel art: smooth anti-aliased strokes. Transparent background: transparent pixels keep the base color. One picture covering the whole head seen from the front; draw over the guide.",
      "pixels": [512, 320],
      "guide": {"element": "head", "side": "front", "points": {"eye_L": [-2.4, 26.5], "eye_R": [2.4, 26.5]}}
    },
    "cloth-grain": {
      "asset": "hero",
      "description": "Seamless 32x32 pixel-art cloth weave, 4-color plum palette, hard pixel edges, no anti-aliasing; must tile on both axes.",
      "pixels": [32, 32],
      "file": "tiles/cloth.png"
    }
  }
}
```

| Field | Meaning |
|---|---|
| `source` | Folder where the producer saves the images; `pull` reads from it. |
| request id (`face`) | Name of the image; delivered to `assets/<asset>/art/<id>.png`. |
| `asset` | Registered asset that receives the image. |
| `description` | Everything that is not a number: subject, style (pixel art, painted, vector look, palette, line weight), transparency, tiling, what must be avoided. It is sent to the producer as written, so make it complete. |
| `pixels` | Exact size of the delivered PNG; `pull` refuses other sizes. |
| `file` | Optional path inside `source` (default `<id>.png`). |
| `guide` | Optional, for pictures that must line up with the model: `element`, `side` (front, back, east, west, top, bottom) and named `points` as `[u, v]` in that side's axes (element units). |

Any other key is kept and ignored. Choose `pixels` from the area covered: about `uv_scale` x the element size in units per side gives one image pixel per texel; double it for smooth painted art, use it as is for pixel art.

## Commands
```bash
py -3.12 -m Tools.forge art guide PROJECT --asset ID     # render guide images, write mapping and point pixels
py -3.12 -m Tools.forge art prompt PROJECT [--request ID] # the message to send to the producer
py -3.12 -m Tools.forge art pull PROJECT [--check]        # copy finished PNGs of the right size
```
`guide` writes `assets/<asset>/art/guides/<id>.png` at the requested size (the element seen from the side, colored by the current texture) and adds `image`, `mapping` and `points_px` to the request's `guide`. `pull` reports `copied`, `unchanged`, `missing` or `wrong_size`; with `--check` it only reports and exits 1 while something is not ready.

## Printing in the recipe
`painter.art(id)` returns the pulled PNG path, or `None` with a warning while it is missing, so the recipe still runs before delivery. Print it with the normal tools after the base colors:
```python
from PIL import Image, ImageOps

face = painter.art("face")
if face:      # the guide covers the whole element seen from the side: size=(1, 1)
    painter.head.project_decal(face, side="front", size=(1.0, 1.0), filtering="bilinear")
ear = painter.art("ear-inner")
if ear:       # one picture reused, mirrored, on the opposite part
    image = Image.open(ear).convert("RGBA")
    painter.ear_L.project_decal(image, side="front", size=(1.0, 1.0), filtering="bilinear")
    painter.ear_R.project_decal(ImageOps.mirror(image), side="front", size=(1.0, 1.0), filtering="bilinear")
grain = painter.art("cloth-grain")
if grain:     # seamless tile: one repeat every 8 model units
    for name in ("cloak", "collar"):
        painter.element(name).project_triplanar(grain, scale=1 / 8, filtering="nearest")
```
Use `filtering="nearest"` and the asset's default `texture_filter` for pixel art; `filtering="bilinear"` and `"texture_filter": "linear"` for painted art (see [painted textures](texture-painter-api.md#painted-non-pixel-art-textures)).
