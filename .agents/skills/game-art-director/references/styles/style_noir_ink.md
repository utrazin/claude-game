# Style Baseline: Noir / Nanquim / Woodcut

> **Agent Directive:** Use this reference as a modular aesthetic baseline for high-contrast graphic drama, printmaking/woodcut aesthetics, detective noir, and stark chiaroscuro comic illustration (e.g., Downwell, Return of the Obra Dinn, Mörk Borg, MadWorld).

---

## 1. Materiality & Surface Treatment

* **Primary Materials:** Dense black carbon ink, aged ivory/cream paper, relief-carved woodblocks, newsprint grain.
* **Contour & Edges:** Dynamic line weights (thick outlines grounding heavy masses, razor-thin lines for delicate internal detail). Hand-cut chisel imperfections along borders.
* **Shading Model:** Binary chiaroscuro. Shading is achieved strictly through **manual cross-hatching, parallel linework, and stippling**—never smooth digital alpha gradients.
* **Lighting Model:** Hard-edged directional light with cast shadows that merge into solid black.

---

## 2. Semantic Palette Baseline

| Token Name | Semantic Role | Luminance Range | Hue / Saturation Behavior |
| :--- | :--- | :--- | :--- |
| `--ink-black` | Solid shadow / Deep background | $0\% - 6\%$ | Pure dense black ink |
| `--paper-white` | Illuminated planes / Actor bodies | $85\% - 95\%$ | Warm ivory, parchment cream, newsprint |
| `--hatch-mid` | Perceived half-tone areas | $40\% - 60\%$ | Optical blend generated via cross-hatch density |
| `--accent-focal` | Critical danger / Gold / Blood | $45\% - 60\%$ | Deep crimson, dried blood red, or cinnabar (single accent) |

---

## 3. Calibration Instructions for `game-art-director`
1. Strictly limit active colors to 2 tones (monochrome) or 3 tones (monochrome + 1 focal accent).
2. Forbid anti-aliased soft transparency on game entities; preserve crisp hard-edged rasterization.
3. Apply cross-hatch shading patterns to convey volume on characters without breaking silhouette read.
