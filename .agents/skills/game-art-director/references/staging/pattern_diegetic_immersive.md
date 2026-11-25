# Staging Pattern: Diegetic Immersive (Zero Traditional HUD)

> **Agent Directive:** Activate this staging pattern when `GDD.md` specifies cinematic immersion, environmental horror, silhouette exploration, or atmospheric puzzle mechanics (e.g., Inside, Limbo, Journey, Dead Space, Little Nightmares).

---

## 1. Visual Hierarchy & Budget of Attention

This pattern enforces the **absolute rejection of floating overlay HUD elements**:
* **85% - Atmosphere, Lighting & Depth:** Chiaroscuro lighting, volumetric fog, and layered silhouettes.
* **15% - Diegetic Actors:** Physical entities responding organically to lighting and physics.
* **0% - HUD Overlay:** Completely eliminated.

---

## 2. Mandatory Contract Workbooks for `design.md`

### Section A: Atmospheric Light Staging Contract
* Environmental lighting drives gameplay visibility:
  * Directional light sources (lantern cones, window shafts, flickering embers).
  * Chiaroscuro contrast: Foreground objects frequently operate as solid black silhouettes against misty background light.
  * Environmental density: Ambient suspended particles (dust motes, rain streaks) catching light cones.

### Section B: Diegetic Actor Contracts
* Player status must be communicated via physical body state contracts:
  * Health / Stamina: Expressed through animation posture (`idle_normal` vs `idle_exhausted`, limping gait, heavy breathing cycles).
  * Direct Status Cues: Physical element embedded in character model (e.g., spine gauge lights, eye glow, cracked armor geometry).
  * Focal Points: High-contrast focal point (e.g., white mask on dark body) directing player eye travel.

### Section C: HUD Workbook (DEACTIVATED)
* **Do NOT generate any HUD, status bar, or counter contracts.**
* Pause and menu states must occur through in-world camera transitions (e.g., character rests against terrain, camera pulls back smoothly) rather than frozen modal overlays.
