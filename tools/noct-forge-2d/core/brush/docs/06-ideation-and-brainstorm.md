# Ideation and Brainstorm Mode

**Purpose.** Settle the art direction (silhouette, line character, palette) with the user before writing `STYLE.md` and `_theme.ts`. Ideation is a short loop of drafts, feedback and a decision.

---

## 1. When to use it

Ideation runs only when the user asks for it, for example "let's brainstorm", "explore some directions first", or "test styles before defining STYLE.md".

If the project already has its theme (`_theme.ts`) and the user did not ask for exploration, skip this guide and produce the requested asset.

---

## 2. Workflow

1. **Frame the directions.** Choose 2 or 3 options that differ on clear axes (section 3).
2. **Draft a comparison board.** Put the options side by side in one temporary file, in `source/temp/` or `source/brainstorm/`. Label each option in the file's comments.
3. **Export and present.** Run `npm run export -- <project> temp/<draft>` and describe each option to the user.
4. **Formalize.** After the user picks a direction, write `STYLE.md` and `_theme.ts`, then start normal production.

The draft is throwaway. Do not reuse its geometry in production assets. Reuse the decisions, not the code.

---

## 3. Axes of contrast

Options should differ on a few of these axes, so the user can see the trade-off:

- **Line character.** One renderer family against another (see [guide 03, section 2](03-styles-and-themes.md#2-choosing-a-renderer)).
- **Corner treatment.** Rounded fillets against sharp or chamfered corners (see [guide 01](01-shapes-and-geometry.md)).
- **Surface.** Flat fill against textured or gradient fill (see [guide 04](04-procedural-textures.md)).
- **Palette.** Warm or cool, high or low contrast, and how many ramps.

Pick axes that matter for the project. Do not vary every axis at once, or the user cannot tell which change produced which result.

---

## 4. Presenting the options

For each option, state in plain terms:

- The silhouette: weight, tactile feel, how the outline reads at the export size.
- The line renderer used and why.
- Luminosity and palette balance.

Then ask the user to pick one option, or to combine parts of several. Record the decision in `STYLE.md`, not in the draft.

---

## 5. Formalizing

`STYLE.md` records the resolution, the layer order of the universal layers, the contrast rules and the chosen renderer family. `_theme.ts` records the palette, ramps, stroke presets and shape styles that the chosen direction needs. After these exist, the draft is no longer a source of truth.
