# Style Baseline: Pastel Cozy / Tactile Craft

> **Agent Directive:** Use this reference as a modular aesthetic baseline for emotional warmth, low-stress gameplay, handcrafted tactile toy aesthetics, satin ceramic, and soft felt papercraft (e.g., Unpacking, A Short Hike, Dorfromantik, Yoshi's Crafted World).

---

## 1. Materiality & Surface Treatment

* **Primary Materials:** Glazed ceramic with satin sheen, hand-molded clay, smooth sanded pine, soft wool felt, matte watercolor paper.
* **Contour & Edges:** Generously rounded corners on all geometry and interactive buttons. Lineless rendering or soft tinted outlines (slightly darker than fill; never harsh solid black).
* **Surface Finish:** Subtle tactile micro-textures (watercolor grain, clay thumbprints, fabric weave).
* **Lighting Model:** Diffuse, warm sunlight with warm contact ambient occlusion (caramel or soft lavender contact shadows instead of cold grey).

---

## 2. Semantic Palette Baseline

| Token Name | Semantic Role | Luminance Range | Hue / Saturation Behavior |
| :--- | :--- | :--- | :--- |
| `--surface-cozy` | Background tabletop / Ground lawn | $70\% - 85\%$ | Warm sand, soft mint, pastel lavender, oat beige |
| `--craft-actor` | Interactive pieces / Characters | $55\% - 70\%$ | Terracotta, warm sage, soft mustard, rose clay |
| `--contact-shadow` | Ambient occlusion under pieces | $30\% - 45\%$ | Warm brown-amber or tinted violet; never pure black |
| `--accent-tender` | Targets, successful snaps, stars | $80\% - 92\%$ | Sunny peach, buttercup yellow, sky blossom |

---

## 3. Calibration Instructions for `game-art-director`
1. Forbid harsh 90-degree angular vertices on interactive cards or buttons; specify minimum 6px corner radii.
2. Ensure drop shadows use warm tinted alphas (`rgba(60, 40, 30, 0.25)`) instead of desaturated black.
3. Keep overall luminance in the upper 60% tier to evoke tranquility and warmth.
