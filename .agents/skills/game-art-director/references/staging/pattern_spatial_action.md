# Staging Pattern: Spatial Action (Scene & World First)

> **Agent Directive:** Activate this staging pattern when `GDD.md` specifies spatial movement, navigation, physics, or entity combat in a continuous 2D or 3D world (e.g., Platformers, Top-down Shooters, Metroidvanias, Action Roguelites, 3D Brawlers).

---

## 1. Visual Hierarchy & Budget of Attention

This budget applies only to the Experience Map entries that use this pattern (the active-play scenes). Menus, hubs and screens follow their own pattern. Allocate visual prominence in those scenes according to this ratio:
* **70% - World & Environment:** Navigable ground, collision boundaries, and layered depth planes.
* **25% - Actors (Entities):** Controllable character, enemies, projectiles, and pickups.
* **5% - HUD Overlay:** Peripheral meters and transient status indicators.

---

## 2. Mandatory Contract Workbooks for `design.md`

When this pattern is selected, you must generate the following contract sections in `design.md`:

### Section A: World & Environment Contracts
1. **Navigable Ground Surface:**
   * High-contrast top edge marking walkable collision boundary.
   * Internal fill value separated from background by at least $2:1$ luminance.
2. **Parallax Layers (Depth Planes):**
   * *Deep Background ($0.1\times - 0.3\times$ scroll):* Reduced luminance and muted saturation; zero high-frequency noise.
   * *Midground Scenery ($0.5\times$ scroll):* Structural silhouettes.
   * *Active Plane ($1.0\times$ scroll):* Interactive collision layer.

### Section B: Entity Specification Contracts
Define explicit contracts for:
* **Player Entity:** Forward directional cue, thruster/footing contact point.
* **Hostile Entities:** Sharp geometric tells communicating attack trajectory.
* **Projectiles:** Minimum $8\times 8\text{px}$ footprint, luminance $\ge 80\%$, with trailing decay vector.
* **Collectibles:** Distinct rounded contour with rhythmic hover/pulse.

### Section C: Minimal HUD Overlay
* Anchor health and objective meters strictly to the outer perimeter (top-left, top-right).
* Never occlude the center $60\%$ action zone during gameplay states.
