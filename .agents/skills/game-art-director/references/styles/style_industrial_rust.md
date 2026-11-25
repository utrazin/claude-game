# Style Baseline: Industrial / Rust & Slate

> **Agent Directive:** Use this reference as a modular aesthetic baseline for retro sci-fi, dieselpunk engineering, heavy shipyard machinery, analog piping, and functional structural wear (e.g., FTL, Machinarium, Hardspace: Shipbreaker, Duskers).

---

## 1. Materiality & Surface Treatment

* **Primary Materials:** Heavy plate steel, graphite gray chassis, embossed brass/iron rivets, oxidized copper patina, vulcanized black rubber, analog needle dials.
* **Contour & Edges:** Robust structural bevels ($45^{\circ}$ chamfers). Visible weld seams, seam joints, and screw heads.
* **Surface Finish:** Matte, non-specular metallic textures with localized edge rust and oil stains.
* **Lighting Model:** Incandescent filament bulbs, spotlight cones, welding torch flares. Zero synthetic neon lines.

---

## 2. Semantic Palette Baseline

| Token Name | Semantic Role | Luminance Range | Hue / Saturation Behavior |
| :--- | :--- | :--- | :--- |
| `--chassis-dark` | Structural framework / Shadow zones | $18\% - 28\%$ | Dark slate, matte cast iron, weathered graphite |
| `--armor-plate` | Exterior plating / Machinery hull | $40\% - 52\%$ | Industrial steel gray, battleship blue-gray |
| `--rust-wear` | Seam oxidation / Weathered bevels | $45\% - 58\%$ | Burnt sienna, oxidic rust orange, raw umber |
| `--indicator-lamp` | Active sensors / Eyes / Gauges | $70\% - 85\%$ | Warm incandescent amber, oxidized copper teal |
| `--hazard-stripe` | Hazard zones / Critical warnings | $65\% - 75\%$ | Industrial diagonal caution yellow, red lead primer |

---

## 3. Calibration Instructions for `game-art-director`
1. Anchor entity silhouettes to chunky, mechanical polygons with distinct chamfered corners.
2. Ensure interactive elements feature mechanical fasteners (rivets, bolts) to ground physical assembly.
3. Keep accent light sources strictly localized as physical lamps rather than whole-body glows.
