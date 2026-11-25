# Game Design Techniques: Cozy & Relaxing Games

This document provides concrete, actionable design patterns for low-stress, satisfying, and aesthetically engaging games. Numbers are illustrative. The A/B split below is optional here: use it only if the game has pacing that escalates. For the macro shape, see `structure_presets.md`.

---

## 1. Flow State Engineering (Relaxing Loops)

In cozy games, flow is achieved through rhythmic predictability, tactile completion, and zero penalty friction:
* **The "Clear and Complete" Rhythm:** Gameplay relies on micro-actions that have a 100% success rate (clearing dust, plucking crops, sorting items, placing blocks). The cognitive pleasure comes from order overcoming chaos.
* **No Fatal Game Over:** Remove death, time-out losses, or permanent penalty. If a condition is not met, the consequence is a soft redirection or minor delay, never a screen wipe.
* **Tactile Interactions:** Ensure every click or movement produces immediate, pleasant micro-responses (soft audio chime, gentle bounce or pop animation, particle glitter).

---

## 2. Low-Stress Risk vs. Reward

Replace survival anxiety with aesthetic curiosity and prioritization choices:
* **Opportunity Cost over Lethal Risk:** The player chooses between cultivating a fast-growing common resource vs. a slow-growing rare resource. The "risk" is simply patience and planning.
* **Curiosity Rewards:** Exploring edges or taking leisurely detours unlocks cosmetic variants, color palettes, or charming animations rather than defensive stats.
* **Cumulative Generosity:** Actions always yield net-positive gains. Missing a timing window still grants partial rewards, ensuring the player's time is always respected.

---

## 3. Decoupled Progression Formula

* **Pacing Scaling (Parameter A):** Driven by **Catalog Completeness or Discovery Radius**:
  $$\text{Available World Items} = \text{Base Types} + \lfloor \text{Milestones Completed} \times 1.5 \rfloor$$
* **Player Capability (Parameter B):** Driven by **Inventory Capacity & Quality-of-Life Tools**:
  $$\text{Gather Radius / Efficiency} = \text{Base Radius} \times (1 + 0.2 \times \text{Tool Tier})$$
* **The Perception Guarantee:** The world broadens in variety, color, and interaction choices as the player advances, without ever imposing demanding twitch reflexes or time pressure.
