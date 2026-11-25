# Staging Pattern: Tactile Board (Cards, Pieces & Physical Surfaces)

> **Agent Directive:** Activate this staging pattern when `GDD.md` specifies game loop mechanics centered on manipulable physical elements (e.g., Deckbuilders, Card Roguelikes, Tabletop Games, Dice/Token Puzzles, Inspector Desk Simulators).

---

## 1. Visual Hierarchy & Budget of Attention

There is **no conventional navigable world**. The tabletop surface and physical objects constitute the game's physical reality:
* **60% - Active Zone & Hand:** Player's hand of cards, active token pool, or inspectable documents.
* **25% - Board / Opponent State:** The tabletop matrix, opposing encounter card, or target score threshold.
* **15% - Tactile Hardware Controls:** Mechanical turn-end levers, physical dice rollers, or ink stamp triggers.

---

## 2. Mandatory Contract Workbooks for `design.md`

### Section A: Tabletop Surface Contract (Replaces Scenery)
* Define the primary surface material:
  * e.g., Casino felt, weathered oak timber, industrial iron plate, or desk blotter.
* Cast shadow specifications: Directional light casting distinct contact shadows beneath cards and pieces.
* **Traditional figurative scenery (skies, platforms, parallaxes) is DEACTIVATED.**

### Section B: Physical Pieces & Cards Contract (Replaces Actors)
* Define contracts for all cards/pieces:
  * Aspect ratio (e.g., $5:7$ ratio, $100\times 140\text{px}$).
  * Mandatory physical states: `idle`, `hover` (elevation + shadow expansion), `drag` (angular tilt following velocity), `deploy` (surface impact), `exhaust` (desaturation / alpha drop).
  * Embossed borders and physical corner radii.

### Section C: Tactile Mechanical Controls (Replaces Web Menus)
* Interactive controls must exist as physical mechanical objects:
  * Chunky push buttons with visible depressed state travel.
  * Mechanical rotary dials or ink stamps with sound/visual recoil.
  * **Strict Prohibition:** Never generate generic flat web-UI button cards or floating modal dialogs.
