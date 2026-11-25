# Game Design Techniques: Incremental & Idle Games

This document provides concrete, actionable design patterns for progression-heavy, clicker, and management micro-games.

---

## 1. Flow State Engineering (Dopamine Loops)

In incremental games, flow is driven by the compression of waiting times into explosion points of power:
* **The Manual-to-Automated Transition:**
  * Phase 1 (0 to 60s): Active clicking/tapping yields $100\%$ of resource generation.
  * Phase 2 (1 to 5 min): First automation tier unlocked (passive generation reaches $50\%$ of total output).
  * Phase 3 (5+ min): Automation handles raw collection; player focus shifts entirely to resource allocation and optimization.
* **Granular Visual Feedback on Numbers:** Floating numbers, ticker animations, and progress bars that fill rapidly to provide constant micro-dopamine hits.

---

## 2. Practical Risk vs. Reward Mechanisms

Risk in incremental games is economic opportunity cost:
* **The Hoard vs. Invest Gamble:**
  * High-tier generators cost significantly more but offer massive exponential yields. Saving for a top-tier asset stalls short-term gains, while buying cheap upgrades provides immediate but shallow scaling.
* **Overdrive / Frenzy Windows:**
  * Randomly appearing temporary multipliers ($10\times$ production for 15 seconds) that require intense active attention or manual tapping to capitalize on.

---

## 3. Decoupled Progression Formula

* **Cost Scaling (Parameter A):** Standard geometric growth:
  $$\text{Cost}(n) = \text{Base Cost} \times (1.15)^n$$
  *(Where $n$ is the number of units already purchased).*
* **Production Scaling (Parameter B):** Linear-step base multiplied by synergy milestones:
  $$\text{Output}(n) = n \times \text{Base Rate} \times 2^{\lfloor n / 25 \rfloor}$$
  *(Notice: Every 25 units bought doubles the entire generator's output, giving the player frequent "super-power" spikes).*
* **Prestige Reset Loop:**
  * Resetting progress grants permanent prestige currency:
    $$\text{Prestige Currency} = \lfloor \sqrt{\text{Total Lifetime Earnings} / 1000} \rfloor$$
  * Each prestige point grants a flat permanent $+5\%$ production multiplier to all future runs.
