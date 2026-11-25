# Styles, Renderers and Themes (`StrokeStyle`, `ShapeStyle`, `_theme.ts`)

**Purpose.** Keep geometry separate from presentation. Geometry is built in `@core/brush`. Colors, strokes, fills and textures come from the project's `_theme.ts`, so every asset in a project shares one visual language.

**API reference:** [`core/docs/api/brush-styles.md`](../../docs/api/brush-styles.md). Signatures are not repeated here.

---

## 1. The theme is the source of tokens

Each project's `_theme.ts` holds the reusable tokens: palette colors, tonal ramps, `StrokeStyle` presets and `ShapeStyle` presets.

- Declare stroke tokens with `new StrokeStyle(...)`. Only `StrokeStyle` instances have `.with(overrides)`. A plain object literal breaks on the first derivation.
- Derive a local variation with `.with(...)`. Do not create a second token for a one-off change.
- Do not write raw hex colors in asset files. Use `alpha` and `lerpColor` to derive opacity and mid-tones from tokens (section 6).

---

## 2. Choosing a renderer

`StrokeStyle` takes a `renderer` name. The built-in renderers are `ribbon`, `clean`, `sketch`, `chalk`, `double`, `bristle`, `profile` and `dashed`.

| Renderer | Character | Suits |
| :--- | :--- | :--- |
| `clean` | Uniform, exact | Technical marks, UI frames, icons that must read at small size |
| `ribbon` | Calligraphic, tapered | Organic outlines, hand-inked contours |
| `sketch` | Multi-pass, slightly loose | Concept and sketchy styles; the style must be declared as such in `STYLE.md` |
| `chalk` | Dry grain | Chalk, dry media, worn surfaces |
| `double` | Two parallel lines | Frames, shields, crest borders |
| `bristle` | Parallel fibers | Painted or brushed looks |
| `profile` | Width varies along the line | Tapered strokes driven by a function |
| `dashed` | Dashes and gaps | Guides, stitches, dotted marks |

**Recommendation.** Choose one renderer family per project and state it in `STYLE.md`. Mixing `clean` and `sketch` in one asset is usually a sign that the line weight is inconsistent.

`join` controls corners (`round`, `miter`, `bevel`). For sharp corners on blades or gems, use `miter` and set `miterLimit` so acute angles do not spike.

---

## 3. Drawing order

`shape.draw(ctx, style)` runs these steps in order:

1. Drop shadow
2. Outside stroke
3. Fill (optionally cel-shaded)
4. Textures
5. `inside` callback
6. Center or inside stroke

Knowing the order matters when a texture or a highlight must sit above the fill but below the outline. Put decorations in `inside` or in a texture rather than drawing them after `draw`, because drawing after `draw` does not clip to the silhouette.

A drop shadow is rendered once per silhouette pass. Do not draw the same shadow twice to make it stronger; change its `blur` or `color` instead.

---

## 4. Fills and gradients

- Use a palette token for flat fills.
- Use `shape.createGradient(ctx, options)` when the gradient must follow the shape's own bounds. A gradient made from a manual rectangle drifts when the shape moves.
- Prefer ramp tokens for gradient stops, so the gradient stays inside the project's palette.

---

## 5. Details inside a shape

Anything that must stay inside a silhouette (bevels, highlights, wear, interior marks) belongs in the `inside` callback or in a texture on that shape. Both are clipped to the host shape automatically, and the clip is always restored.

Do not draw details on the shape's edge with separate paths. They overflow when the shape is resized, and they are not part of the silhouette.

---

## 6. Color helpers

- `alpha(color, opacity)` returns the same color with a new opacity. Use it for overlays and soft shadows built from tokens.
- `lerpColor(a, b, t)` interpolates between two colors. Use it to derive a mid-tone between two tokens.

Both are deterministic, so the same inputs always give the same output.

---

## 7. Text in game assets

Official exports of buttons, panels, frames, cards, health bars and inventory slots contain no rasterized text. Engines render localized, scalable text on top of these graphics.

When the user asks for a preview with sample labels, render the text only in preview mode (`if (context.preview)`), and remove it before the official export.

---

## 8. Custom brushes

Use `defineBrush` when no built-in renderer produces the line you need.

- Declare custom keys in `params`, each with a default and a description.
- Use `defaults` only to override a `StrokeOptions` value of the parent brush (for example `width`).
- Call `base()` inside `draw` to delegate to the parent renderer and add decoration on top, instead of reimplementing the whole stroke.

A custom brush is a token. Put it in `_theme.ts` next to the other strokes, so it is reused and not redefined per asset.

---

## 9. Quick decision table

| Situation | Recommended | Avoid | Reason |
| :--- | :--- | :--- | :--- |
| Flat color | Palette token in `fill` | A hex literal in the asset | Keeps the palette in one place. |
| Variation of a stroke | `STROKES.bold.with({ width })` | A second token | Keeps the token family consistent. |
| Gradient on a shape | `shape.createGradient(...)` | A gradient on a manual rectangle | Follows the shape when it moves. |
| Highlight or wear inside a shape | `inside` or a texture | A path drawn on the edge | Clipped to the silhouette. |
| Line with a new behavior | `defineBrush` extending a parent | A new renderer from scratch | Inherits the parent's stroke logic. |
