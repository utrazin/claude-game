# Style Baseline: Vibrant Flat / Stylized Cartoon

> **Agent Directive:** Use this reference as a modular aesthetic baseline for playful dynamism, pop clarity, modern 2D character animation, charismatic geometric anatomy, and bold high-impact silhouettes (e.g., Bad North, Brotato, Guacamelee, Don't Starve, Cult of the Lamb).

---

## 1. Materiality & Surface Treatment

* **Primary Materials:** Opaque gouache paint, heavy papercraft cutouts, matte vinyl toy finish, traditional cel animation.
* **Contour & Edges:** Consistent, clean outer strokes (uniform $2\text{px}$ line weight across all actors on the same depth plane). Deliberate alternation between smooth curves and exaggerated sharp angles.
* **Shading Model:** Stepped cel-shading (maximum 1 or 2 flat shadow tiers). Zero soft airbrush gradients.
* **Surface Finish:** Flat modulated color blocks ensuring readable character actions even in dense mob encounters.

---

## 2. Semantic Palette Baseline

| Token Name | Semantic Role | Luminance Range | Hue / Saturation Behavior |
| :--- | :--- | :--- | :--- |
| `--scenery-flat` | Environment base / Ground planes | $30\% - 45\%$ | Controlled saturation; modulated background tones |
| `--hero-pop` | Player character primary body | $65\% - 85\%$ | Signature high-luminance primary color |
| `--threat-contrasting` | Hostile mobs / Harm zones | $50\% - 70\%$ | Opposing color wheel quadrant; complementary to hero |
| `--pickup-solar` | Coins / Powerups / Collectibles | $80\% - 95\%$ | High-value warm yellow, radiant gold, or white-core star |

---

## 3. Calibration Instructions for `game-art-director`
1. Pick a signature dominant hue for the player character before selecting enemy hues.
2. Ensure enemy hues occupy contrasting color wheel segments to prevent visual blending during combat swarms.
3. Keep outer stroke weights strictly identical across the player and all enemy entities.
