---
name: game-designer
description: >-
  Transforms market references and user concepts into an operational Game Design Document (GDD.md).
  Defines the Experience Map (every scene and screen with its own reason to exist), the resource and verb graph,
  the loops, and provisional tuning values. Scope comes from the user's declared ambition, not from a minimalism default.
---

# Game Designer Skill

This skill translates a concept into an actionable `GDD.md`. A GDD is good when a programmer can build every scene, screen and verb from it, and when each mechanic has a visible cause and effect. Numbers alone do not make a design coherent.

---

## 1. Core Philosophy

* **Scope Comes From the User.** Read the scope tier declared at intake (`prototype`, `vertical_slice`, `small_complete`). Design to that tier. Do not shrink it on your own.
* **Robust, Not Minimal.** "Always runs, never ships broken" is a gate for the programmer and QA. It is not a design limit. A game may have a hub, several scenes and real menus when they carry decisions.
* **Every Element Earns Its Place With a Verb.** Keep a scene, screen or system if it gives the player a verb or a decision that exists nowhere else. Cut it if it does not. Never cut an element only because it is "peripheral" or "a menu".
* **Depth Over the First 30 Seconds.** Check the design at minute 1 and at minute 10. If the player does the same thing at both, the design is shallow. Add a new verb, a new space, or a new decision.
* **Flow State.** Match challenge to skill. Telegraph threats. Avoid unfair punishment.
* **Decoupled Progression Is an Option, Not a Law.** For games with escalating threats, drive challenge by time, depth or waves, and player power by choices and resources, and never scale enemy health to player level. For games without threats (cozy, puzzle, management), use the equivalent that fits, or skip it.
* **No Preemptive Prejudices.** Never discard 3D or richer mechanics on an assumption of technical impossibility.

---

## 2. Intake Check

Before writing, confirm you have: the concept, the scope tier, and the stack (engine, language, assets folder, unit) in `design.md` section 0. If the scope tier or the stack is missing, ask the orchestrator to ask the user. Do not assume.

---

## 3. Viability Filtering

1. Review `references.md` (or the user prompt).
2. For each candidate mechanic or space, ask: what verb or decision does it add? Which scene hosts it? What resource does it read or write?
3. Keep elements that answer all three. Merge or cut elements that duplicate another element's verb.
4. Validate feasibility against the chosen stack.

---

## 4. Experience Map (Mandatory)

The Experience Map is the backbone of the GDD. It lists every distinct scene and screen.

* **Scene:** a space the player moves or acts in (camp, dungeon floor, shop street, boss arena).
* **Screen:** a menu, panel or overlay with its own layout and decisions (recipe screen, upgrade screen, map, results).
* Each entry states: purpose, unique verbs, entry and exit conditions, camera or layout, visual difference from the other entries, and the persistent state it reads and writes.
* **Differentiation Rule:** two entries with the same verbs, camera and layout are one entry.
* **Coverage Rule:** every verb in the GDD lives in at least one entry, and every entry hosts at least one verb or decision.
* A title or pause menu counts as an entry only when it holds real decisions (save slots, settings, a map). Otherwise list it as a one-line utility.

Scale to the scope tier:

| Tier | Minimum Experience Map |
| :--- | :--- |
| `prototype` | One scene plus the screens needed to play and restart. |
| `vertical_slice` | Every distinct kind of scene and screen the full game would have, each in one working instance. |
| `small_complete` | All scenes and screens, with the content count per scene. |

---

## 5. Resource and Verb Graph (Mandatory)

Mechanics must connect. Define:

* **Resources:** every currency, item, stat or state variable. For each: source (how it is gained), sink (how it is spent or lost), and where the player sees it.
* **Verbs:** every player action, as `input -> state change -> feedback -> where it shows in the UI`.
* **Orphan Check:** a resource with no source, sink or visible use is an orphan. A verb with no effect on a resource or scene is an orphan. Remove orphans or connect them before the critic review.

---

## 6. Dialectical Validation via Subagent (`game-design-critic`)

You are **forbidden** from simulating the critic in this session.

When the GDD draft is complete (Experience Map, graph, loops, provisional values), dispatch it once to an isolated subagent with the `game-design-critic` skill. Use `prototype` scope as an exception: the critic call is optional.

### Critic Report Processing
Proposals are advisory. For each finding, pick one: `ADOPT_OPTION`, `FUSE_OPTIONS`, `INVENT_ALTERNATIVE`, or `REJECT_WITH_RATIONALE` (retain the mechanic as a hypothesis to test in the build). Record the choices in a short `## 10. Design Decisions` section. Do not run extra critic rounds unless the critic reported a proven defect.

---

## 7. Progressive Reference Discovery

Use the references as lenses, not templates. All numbers in them are illustrative ranges. Calibrate to your game.

1. **Structure first:** consult [`references/structure_presets.md`](./references/structure_presets.md) to choose the macro shape (scenes, screens, loops) closest to the concept. Adapt it.
2. **Technique lenses** for micro-loop feel:

| Game Profile | Reference |
| :--- | :--- |
| Action / Arcade / Survival | [`references/techniques_action_arcade.md`](./references/techniques_action_arcade.md) |
| Cozy / Casual / Relaxing | [`references/techniques_cozy_relaxing.md`](./references/techniques_cozy_relaxing.md) |
| Puzzle / Tactical / Strategy | [`references/techniques_puzzle_tactical.md`](./references/techniques_puzzle_tactical.md) |
| Incremental / Idle / Management | [`references/techniques_incremental_idle.md`](./references/techniques_incremental_idle.md) |

Combine lenses when the game mixes profiles. A concept that fits no lens is allowed. Design it from the verb graph.

---

## 8. Output Specification: `GDD.md`

```markdown
# Game Design Document (GDD): [Game Title]

## 1. Executive Summary & Loops
* **Genre / Perspective:** [...]
* **Scope Tier:** [prototype | vertical_slice | small_complete]
* **Core Loop (seconds):** [Input -> Action -> Immediate Feedback]
* **Session Loop (minutes):** [...]
* **Meta Loop (across sessions or runs):** [... or "none" with a reason]
* **Minute-10 Test:** [What the player does at minute 10 that they did not do at minute 1]

## 2. Experience Map
| ID | Type (scene/screen) | Purpose | Unique Verbs | Enter From -> Exit To | Camera / Layout | Reads / Writes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
[Plus a small flow diagram of transitions.]

## 3. Verbs & Controls
| Verb | Input | State Change | Feedback (visual / audio) | Where in UI |
| :--- | :--- | :--- | :--- | :--- |

## 4. Resource Graph
| Resource | Source | Sink | Visible In | Cap / Start |
| :--- | :--- | :--- | :--- | :--- |

## 5. Challenge & Opposition (Parameter A)
[Enemies, hazards, puzzles or time pressure. Escalation formula driven by time, depth or stage. "N/A" with a reason if the game has none.]

## 6. Player Growth & Economy (Parameter B)
[Upgrades, unlocks, recipes, tools. How they are earned. Qualitative choices over +1% increments.]

## 7. Content Inventory
[Count per scene: enemy types, recipes, levels, items. This sets the production list for art and assets.]

## 8. Provisional Tuning Values
*(Starting values only. The programmer keeps them in one constants/data file. Use rows that fit the genre, e.g. move speed, cooldowns, spawn rates, move limits, harvest times, base yields.)*

| Parameter | Start | Cap | Step |
| :--- | :--- | :--- | :--- |

## 9. Open Hypotheses
[Mechanics retained against critic advice, with the playtest signal that would cut them.]

## 10. Design Decisions
[Critic findings and the resolution chosen.]
```

---

## 9. Handoff

When `GDD.md` is saved with all ten sections, the design milestone is complete. The next phase is Art Direction (`game-art-director`). Programming of the walking skeleton may start in parallel once the Experience Map exists.
