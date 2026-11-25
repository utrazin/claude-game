# Style Baseline: Dark Earthy / Organic

> **Agent Directive:** Use this reference as a modular aesthetic baseline for dense organic environments, ancient overgrown forests, damp subterranean caverns, and rustic wilderness (e.g., Darkwood, Inscryption, Hollow Knight - Greenpath). Adopt its material and luminance rules into `design.md`, calibrating tokens to the game's specific theme.

---

## 1. Materiality & Surface Treatment

* **Primary Materials:** Rugged tree bark, damp soil/loam, velvety moss, weathered timber, river stone, unbleached twine, plant resin.
* **Contour & Edges:** Soft organic contours with slight structural asymmetry. Avoid perfectly straight synthetic vector edges.
* **Surface Finish:** Matte, non-reflective textures. Contact ambient occlusion where actors and props meet the ground.
* **Lighting Model:** Diffuse, filtered canopy light and subtle organic bioluminescence. Short, natural falloff creating penumbral gradients rather than harsh pitch-black cutoffs.

---

## 2. Semantic Palette Baseline

| Token Name | Semantic Role | Luminance Range | Hue / Saturation Behavior |
| :--- | :--- | :--- | :--- |
| `--bg-deep` | Deep backdrop / Distant woods | $10\% - 20\%$ | Muted moss green, damp loam, deep mud |
| `--surface-ground` | Navigable soil / Wood planking | $25\% - 35\%$ | Warm clay, weathered bark, dried peat |
| `--actor-primary` | Main character body / Focus entity | $60\% - 75\%$ | Bleached bone, pale lichen, unvarnished wood |
| `--hazard-threat` | Enemies, spikes, toxic hazards | $45\% - 65\%$ | Burnt ochre, dried venom, fungal red |
| `--accent-reward` | Collectibles, resin, seeds | $75\% - 90\%$ | Warm amber, golden pollen, sap drop |

---

## 3. Calibration Instructions for `game-art-director`
1. Inherit the semantic token structure into `design.md` Table 2.
2. Adjust hue bias according to narrative setting (e.g., cooler hues for stagnant swamps; warmer hues for autumn leaf decay).
3. Enforce the 4:1 luminance ratio between `--actor-primary` and `--bg-deep`.
