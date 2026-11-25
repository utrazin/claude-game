# Empirical Heuristics & Market Data Patterns

This reference document serves as the repository of empirical evidence, quantitative metrics, and player behavior patterns for the `game-design-critic` subagent. Its objective is to supply objective criteria to ground critiques in **observable facts**, eliminating subjective opinions and baseless industry conventions.

---

## 1. The Empirical Burden of Proof

When auditing a gameplay mechanic, the critic must classify findings under three strict categories:

| Category | Definition | Critic Action |
| :--- | :--- | :--- |
| **Proven Defect (Empirical Data)** | The mechanic has a documented history of technical failure, mathematical contradiction, or quantifiable churn in player reviews. | **Hard Critique & Veto.** Demand structural modification or removal. |
| **Observed Risk / Unproven Hypothesis** | The mechanic is unusual, counter-intuitive, or breaks conventional wisdom, but **lacks objective data proving failure**. | **Do Not Veto.** Document as an open risk hypothesis and establish telemetry metrics for playtesting. |
| **Validated by Precedent** | The mechanic mirrors configurations with proven player retention and positive review velocity in comparable benchmark titles. | **Baseline Approval.** Focus solely on ensuring the implementation scope is minimal and feasible. |

---

## 2. Objective Mathematical & Systemic Deficiencies (Fact-Based Vetos)

These flaws stem directly from computational logic and game theory, independent of personal taste:

### A. Trivial Strategic Dominance (Degenerate Gameplay)
* **Symptom:** A single action or ability is strictly superior to all other options in cost-benefit (DPS/safety), rendering every other player decision meaningless.
* **Empirical Impact:** Players quickly converge on the single optimal strategy and abandon the game due to boredom (*"the game plays itself"* or *"just spam X"*).
* **Audit Check:** Calculate whether Player Evolution (Parameter $B$) creates an imbalance that invalidates Challenge Scaling (Parameter $A$).

### B. Irreversible Snowballing (Runaway Feedback Loops)
* **Symptom:** An initial player mistake triggers a cumulative disadvantage that is mathematically impossible to overcome (death spiral), OR early success removes all remaining tension prior to session mid-point.
* **Empirical Impact:** Severe churn spikes immediately following the first player death, or premature abandonment by moderately skilled players.
* **Audit Check:** Verify whether dynamic containment exists or if challenge scales independently without linking enemy health pools directly to player level.

### C. Deadlocks & Permanent Stun-Locking
* **Symptom:** Cooldown timings, animation locks, or hitstuns allow either the player or enemies to permanently incapacitate the opponent.
* **Empirical Impact:** Consistent negative reviews citing "broken controls" or "cheap/unfair deaths" across Steam and Itch.io communities.

---

## 3. Cognitive Friction Patterns & Time to Fun (TTF)

Retention data across indie, arcade, and casual titles reveals strong correlations between specific design patterns and player drop-off:

> Time to fun measures the **first** minute only. It must not be used to reject structure that pays off later (hubs, meta loops, extra scenes). Check depth separately with the Minute-10 Test.

### A. Early Cognitive Overhead (The Rule-to-Action Ratio)
* **Evidence:** In prototypes and fast-paced arcade games, players decide whether to continue playing within the first 30 to 60 seconds.
* **Proven Defect:** Mechanics that require reading text-heavy tutorials before the first satisfying input correlate with disproportionately high Day-0 churn in usability tests.
* **Audit Check:** If a mechanic cannot be intuitively grasped through *direct audiovisual feedback* (animation, sound, particles) within the first 3 interaction cycles, it constitutes an immediate retention risk.

### B. The Illusion of Choice (Micro-Stat Clutter)
* **Evidence:** Presenting 10 upgrade tiers that increase stats by +1% causes decision fatigue with virtually zero emotional payoff.
* **Empirical Recommendation:** Players respond significantly better to binary or ternary choices featuring perceptible qualitative shifts (e.g., "short-range triple spread" vs "long-range piercing shot") rather than microscopic arithmetic increments.

---

## 3b. Structural Deficiencies (Fact-Based)

* **Orphan resource:** gained but never spent, spent but never gained, or never shown to the player.
* **Orphan verb or scene:** a verb with no effect on state, or a scene/screen with no verb that exists only there.
* **Duplicate scene:** two entries with the same verbs, camera and layout.
* **Numeric-only progression:** upgrades that only raise numbers. Players respond to qualitative shifts.
* **Same-at-minute-10:** the player does the same thing, only faster, after ten minutes.

Each of these is observable in the GDD and counts as a `PROVEN DEFECT`.

---

## 4. What Is NOT a Defect: Respecting Counter-Intuitive Innovation

Many of the most successful indie breakthroughs defied "conventional wisdom" at the time of their release:

* **Example 1 (Vampire Survivors):** Removing the manual attack button and making firing purely automatic contradicted traditional action game design. *Result:* Reduced motor strain, prioritized tactical positioning, and established an industry-defining retention loop.
* **Example 2 (Getting Over It / Flappy Bird):** Punitive difficulty paired with intentionally unstable controls and zero checkpoints violated standard usability guidelines. *Result:* Generated intense vicarious challenge and massive streaming engagement.
* **Example 3 (Crypt of the NecroDancer):** Binding the tactical movement of a roguelike grid directly to a musical tempo beat was considered counterproductive by traditionalists. *Result:* Created near-flawless synergy between rhythm and tactical strategy.

**Supreme Directive for the Critic:** If a proposed mechanic appears strange, uncomfortable, or unconventional, ask yourself: *"Does objective mathematical data or market evidence prove that this cannot work, or is this merely my own genre bias?"* If it is personal or conventional bias, **allow the mechanic**, document the risks honestly, and define clear telemetry thresholds for initial playtest validation.
