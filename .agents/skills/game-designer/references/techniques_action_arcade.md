# Game Design Techniques: Action & Arcade

> **Note on Metrics:** The numbers, durations and formulas below are illustrative ranges, not sourced baselines. Treat them as starting points to calibrate in playtest. This lens covers micro-loop feel. For the macro shape of the game, see `structure_presets.md`.

---

## 1. Flow State Engineering (Action Loops)

In action games, flow is maintained by matching cognitive load to player reflex windows:
* **The 3-Second Micro-Loop:** The player must make a micro-decision every 1 to 3 seconds (dodge, shoot, reposition, dash). If more than 5 seconds pass without an active stimulus, the pacing collapses.
* **Predictable Telegraphing:** Every threat must provide a visual or spatial tell (0.3s to 0.8s anticipation window) before executing damage. Untelegraphed damage destroys flow and produces frustration instead of mastery.
* **Grace Periods (Coyote Time & Input Buffering):**
  * Allow jumping 0.1s *after* walking off a ledge (Coyote Time).
  * Buffer jump/attack inputs pressed 0.1s *before* touching the ground.

---

## 2. Practical Risk vs. Reward Mechanisms

Never offer flat choices. Tie every high reward to active vulnerability:
* **The Proximity Bonus (Near-Miss):**
  * Award $2\times$ score or instant stamina recharge when dodging hazards within pixels of collision.
* **The Decaying Multiplier:**
  * Score multiplier increases with aggressive actions ($1\times \to 2\times \to 4\times$), but drains completely if no enemy is hit within 2.5 seconds. This forces the player into calculated danger.
* **Greed vs. Safety Windows:**
  * Collectibles (gems, coins) appear in hazardous zones with short despawn timers (4 to 6 seconds). The player must gamble their health pool to maximize progression.

---

## 3. Decoupled Progression Formula

To prevent the player from feeling that leveling up makes enemies artificially spongier:
* **Challenge Scaling (Parameter A):** Driven strictly by **Time Elapsed ($t$)** or **Wave Index ($w$)**:
  $$\text{Spawn Rate} = \text{Base Spawn} \times (1 + 0.08 \times w)$$
  $$\text{Enemy Density} = \min(\text{Max Density}, \text{Base Density} + 2 \times w)$$
  *(Notice: Scale density and variety, NOT raw bullet-sponge health).*
* **Player Power Scaling (Parameter B):** Driven strictly by **Collected Resources / Active Upgrades**:
  $$\text{Player DPS} = \text{Base Damage} \times (1 + 0.15 \times \text{Upgrades}) \times \text{Attack Speed Multiplier}$$
* **The Perception Guarantee:** Because player power grows in distinct tactical spikes (e.g., gaining piercing shots or a wider blast radius), the player experiences moments of overwhelming dominance before the increasing enemy numbers re-establish tension.
