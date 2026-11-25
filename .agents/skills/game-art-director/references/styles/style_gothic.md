# Style Baseline: Gothic / Grim Desaturated

> **Agent Directive:** Use this reference as a modular aesthetic baseline for dark fantasy, late medieval ruin, solemn ecclesiastical architecture, ritualistic asceticism, and desolate gothic horror (e.g., Darkest Dungeon, Blasphemous, Salt and Sanctuary, Fear & Hunger).

---

## 1. Materiality & Surface Treatment

* **Primary Materials:** Damp ashlar masonry, hammered wrought iron, tarnished brass, unbleached linen, dried candle tallow, cracked fresco plaster.
* **Contour & Edges:** Lancet arches, elongated vertical geometry, pointed cusps, and barbed contours. Heavy structural shadow blocks.
* **Surface Finish:** Low-reflectance matte textures with cracked mineral fissures and moisture staining.
* **Lighting Model:** Flickering torchlight, brazier embers, or dust-mote light shafts penetrating high narrow windows. Smoke and soot softening background silhouettes.

---

## 2. Semantic Palette Baseline

| Token Name | Semantic Role | Luminance Range | Hue / Saturation Behavior |
| :--- | :--- | :--- | :--- |
| `--stone-crypt` | Vaulted masonry / Background walls | $12\% - 22\%$ | Deep cold stone gray, tomb soot, ash black |
| `--linen-bone` | Actor garments / Unarmored bodies | $60\% - 72\%$ | Raw unbleached linen, bone ivory, weathered vellum |
| `--relic-brass` | Sacred icons / Reliquaries / Coins | $65\% - 78\%$ | Tarnished brass, dull antique gold leaf |
| `--dried-blood` | Fanatical wounds / Hostile intent | $38\% - 50\%$ | Dried burgundy, clotted carmine, oxidic red |

---

## 3. Calibration Instructions for `game-art-director`
1. Strictly enforce desaturation across background scenery to keep background luminance below $25\%$.
2. Maintain high vertical proportions on character silhouettes (tall hoods, pointed helmets, elongated blades).
3. Restrict high-luminance accents to sacred relics or lethal attacks.
