# Game Design Techniques: Puzzle & Tactical Games

This document provides concrete, actionable design patterns for logic-driven, turn-based, and spatial puzzle games. Numbers are illustrative. For the macro shape, see `structure_presets.md`.

---

## 1. Flow State Engineering (Cognitive Loops)

In puzzle games, flow is generated through progressive mental models and "Eureka" moments:
* **Rule Isolation (No Text Tutorials):** Introduce a new rule in a sandbox room where only that single interaction is physically possible to succeed. The player deduces the rule through self-discovery.
* **The Rule Combination Step:** Once two individual mechanics ($A$ and $B$) are mastered separately, construct puzzles that require using $A$ to activate $B$. The cognitive satisfaction comes from synthesis.
* **Instant Undo / Frictionless Reset:** Always provide a one-key instant undo or board reset. Friction in puzzle games comes from sluggish resets, not from hard problems.

---

## 2. Practical Risk vs. Reward Mechanisms

In turn-based or grid logic, risk is represented by commitment and resource consumption:
* **The Turn Budget (Par Score):**
  * Beating the level grants standard completion.
  * Beating the level within a strict move threshold ($N$ moves) unlocks secret tiers, bonus cosmetics, or mastery medals.
* **Greed Paths on the Grid:**
  * Optional bonus tokens placed in positions that require complex, non-obvious sub-solutions before reaching the exit.
* **Irreversible Actions:**
  * Certain floor tiles crumble or keys break upon use. The risk is committing to a path before visualizing the 3-step sequence ahead.

---

## 3. Decoupled Progression Formula

* **Puzzle Complexity (Parameter A):** Driven by **Combinatorial Variables**:
  $$\text{Interactive Elements per Stage} = \text{Base Elements} + \lfloor \text{Stage Index} / 3 \rfloor$$
  *(Keep grid sizes compact; scale the interplay between elements, not the walking distance).*
* **Player Arsenal (Parameter B):** Driven by **Tool Utility & Perspective Shifts**:
  * The player acquires distinct abilities (e.g., ability to push vs. pull, ability to rotate the board, color-shifting).
* **The Perception Guarantee:** The player feels smarter with each stage because the solution demands creative insight with existing simple rules, rather than memorization or manual dexterity.
