# Style Baseline: Pulp Retro / Comic Print

> **Agent Directive:** Use this reference as a modular aesthetic baseline for vintage pulp adventure, 1970s–1980s comic book print, Ben-Day dot screens, and graphic serialized illustration (e.g., Void Bastards, Comix Zone, classic EC Comics).

---

## 1. Materiality & Surface Treatment

* **Primary Materials:** Coarse pulped newsprint, CMYK offset printing ink with slight plate misregistration, yellowed vintage cardstock.
* **Contour & Edges:** Bold, dynamic brush ink outlines with tapered terminals. Heavy black spot shadows grounding figures.
* **Shading Model:** Ben-Day halftone dot grids and parallel line screens for midtone gradients. Pure flat color fills within ink boundaries.
* **Surface Finish:** Printed paper grain with occasional slight ink bleed or paper fiber imperfections.

---

## 2. Semantic Palette Baseline

| Token Name | Semantic Role | Luminance Range | Hue / Saturation Behavior |
| :--- | :--- | :--- | :--- |
| `--newsprint-base` | Paper background / World base | $75\% - 85\%$ | Warm aged ivory, yellowed pulp newsprint |
| `--ink-shadow` | Line art / Solid drop shadows | $0\% - 8\%$ | Dense carbon black print ink |
| `--comic-primary` | Hero body / Action focus | $50\% - 70\%$ | Offset primary red, cobalt cyan, warm cadmium |
| `--halftone-screen`| Secondary depth / Volume shade | $40\% - 55\%$ | Patterned dot screen of primary hue on newsprint |

---

## 3. Calibration Instructions for `game-art-director`
1. Use solid black drop shadows offset at $45^{\circ}$ behind floating UI banners and title text.
2. Incorporate Ben-Day dot patterns into entity shading when rendering 2D procedural graphics.
3. Keep ink strokes bold (minimum $2\text{px}$ to $3\text{px}$) to evoke the look of classic four-color press plates.
