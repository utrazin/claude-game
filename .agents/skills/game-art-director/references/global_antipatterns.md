# Global Visual Anti-Patterns & Negative Constraints

> **Agent Directive:** This document establishes mandatory negative constraints to eliminate generative AI aesthetic tropes and web application patterns. You must enforce these rules strictly in `design.md`. Any violation of a directive below fails the self-audit in `game-art-director` section 4.

---

## 1. Prohibited AI Visual Tropes (Zero Tolerance)

LLMs possess statistical biases toward repetitive, synthetic aesthetics when generating game visuals. The following conventions are strictly forbidden:

### ❌ 1.1 Unmodulated Fluorescent Saturation
* **Violation:** Applying 100% pure saturated colors directly onto solid black (`#000000`) surfaces without atmospheric falloff, intermediate tones, or environmental reflection.
* **Agent Rule:** Every color channel must operate within a calibrated palette hierarchy. Light sources must exhibit physical falloff and interact with surface materials.

### ❌ 1.2 Blanket Additive Glow (Blind Bloom)
* **Violation:** Using blanket blur, radial glow (`shadowBlur`), or synthetic bloom across every sprite border to disguise geometric deficiency, lack of texture, or indistinct silhouettes.
* **Agent Rule:** Visual readability must be achieved through **luminance value separation (4:1 minimum)** and distinct geometry—never through artificial edge blurring.

### ❌ 1.3 Synthetic Laser Grids & Wireframe Horizons
* **Violation:** Generating ground planes composed of perspective wireframe laser grids receding into a black void (lazy synthwave/cyberpunk cliche).
* **Agent Rule:** Ground planes and world environments must feature physical surface materiality (modular tiles, structural seams, wear patterns, or organic textures).

---

## 2. Prohibited Web Application Patterns (Anti-Web Directive)

Games are immersive diegetic spaces, not administrative dashboards. You are strictly forbidden from porting web application UI tropes into game specifications:

### ❌ 2.1 Floating Cards & SaaS Containers
* **Violation:** Encapsulating game information inside rounded-corner cards with thin neutral borders and backdrop blurs that resemble Tailwind or Bootstrap dashboards.
* **Agent Rule:** In spatial games, UI must be a minimal heads-up overlay (HUD). In card/board games, cards and surfaces must be modeled as **tangible physical objects** with simulated drop shadows, material textures, and embossed edges.

### ❌ 2.2 Generic Call-To-Action (CTA) Pill Buttons
* **Violation:** Placing centered pill-shaped buttons with web-style hover states in menus or game-over screens.
* **Agent Rule:** Interactive triggers must be stylized as physical in-universe components: mechanical switches, ink stamps, stone tablets, tactile keys, or diegetic prompt glyphs.

---

## 3. Diegetic Materiality Directive

Every visual component (entity, UI element, world prop) must have an explicit material assignment:
* **Fantasy / Historical:** Carved stone, wrought iron, weathered leather, unbleached parchment, rough-hewn timber.
* **Industrial / Sci-Fi:** Riveted steel plating, matte graphite, oxidized copper, analog gauges with needle indicators.
* **Graphic Minimalist:** Woodcut print, slate blackboard, rough chalk, dense ink on textured paper.
* **Tactile Craft:** Molded clay, glazed ceramic, layered papercraft, matte vinyl.

Any asset resembling standard web-UI styling is **automatically non-compliant**.
