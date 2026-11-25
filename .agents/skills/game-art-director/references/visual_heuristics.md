# Visual Heuristics & Objective Quality Metrics

> **Agent Directive:** This document provides operational visual metrics and mathematical rules. The `game-art-director` must use these heuristics to calibrate `design.md`. The self-audit in `game-art-director` section 4 uses these exact rules as binary criteria.

---

## 1. Luminance Staging Heuristic (4:1 Contrast Ratio)

Backgrounds and interactive entities must **never** occupy the same luminance value range:

$$\text{Contrast Ratio} = \frac{L_{\text{foreground}} + 0.05}{L_{\text{background}} + 0.05} \ge 4.0$$

### Value Separation Tiers:
* **Dark Staging Palette:**
  * Background / Non-interactive terrain: $L \in [10\%, 25\%]$
  * Interactive Entities / Projectiles / Critical HUD: $L \in [60\%, 95\%]$
* **Light / Pastel Staging Palette:**
  * Background / Non-interactive terrain: $L \in [75\%, 90\%]$
  * Interactive Entities / Projectiles / Critical HUD: $L \in [10\%, 35\%]$

**Prohibited Grey Zone:** Interactive entities with $L \in [40\%, 55\%]$ placed against backgrounds with $L \in [40\%, 55\%]$ are strictly prohibited. Camouflage is non-compliant unless explicitly defined as an intentional stealth mechanic in `GDD.md`.

---

## 2. The 0.1-Second Silhouette Readability Test

Every interactive asset must be identifiable by functional role and orientation within a $100\text{ms}$ glance using peripheral vision alone:

### Shape Language Taxonomy:
1. **Acute Triangles & Sharp Vertices:** Signal active threat, penetration, acceleration, and projectile velocity. Reserved for hostile entities, hazard spikes, and primary ammunition.
2. **Convex Circles & Smooth Arcs:** Signal safety, collectibility, recovery, or organic vulnerability. Reserved for coins, health pickups, and player character elements.
3. **Rectangles & Cubic Blocks:** Signal mechanical stability, anchoring, immovable terrain, or defensive shielding.

### Binary Verification Procedure:
1. Produce a solid monochrome silhouette of the asset render, on a transparent background.
2. Inspect the solid monochrome output:
   * **Pass Condition:** The entity's facing direction, functional role (allied, enemy, item), and center of mass are unmistakable from contour lines alone.
   * **Fail Condition:** The silhouette resembles an amorphous box or indistinct blob without perimeter protrusions.

---

## 3. Stroke & Outline Integrity Rule

Visual coherence requires strict geometric outline consistency across identical gameplay planes:

* **Unified Stroke Weight:** If the player asset utilizes a 2-pixel outer stroke, **all enemies, interactive hazards, and dynamic items on that depth plane must also use a 2-pixel stroke**.
* **Zero Outline Mixing:** Outlined vector sprites must never be mixed with lineless flat assets on the same interactive layer.
* **Depth Attenuation:** Foreground gameplay elements require sharp outlines; background scenery elements must reduce stroke weight to zero or match background hue to push them backward in visual hierarchy.

---

## 4. Peripheral HUD Glance Efficiency

In games utilizing HUD overlays:
* Vital metrics (HP, Energy, Cooldowns) must occupy the **outer 10% screen perimeter**.
* Value changes must be communicated via **shape alteration or high-contrast luminance shifts**, requiring zero foveal eye redirection from the center of action.
