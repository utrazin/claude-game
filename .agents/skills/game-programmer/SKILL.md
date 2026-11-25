---
name: game-programmer
description: >-
  Implements the executable game from GDD.md in the engine and language the user chose. Builds a scene and screen
  manager from the GDD Experience Map, starts with a walking skeleton that uses marked placeholders, then swaps in
  project-local exported assets and explicitly specified runtime visuals. Keeps code simple but never skips scenes the GDD defines.
---

# Game Programmer Skill

This skill writes the executable game, input handling, scene flow and gameplay from `GDD.md` and `design.md`. It does not prescribe an engine or language. Those come from the user's stack decision.

---

## 0. Stack Gate (Blocking)

Before writing code, read section 0 of `design.md`. If the engine, language, game assets folder or unit is `TBD` or missing, stop. Ask the user through the orchestrator and wait. Do not pick a default.

---

## 1. Core Philosophy

### A. Simple Code, Complete Game
* Keep the code simple: plain collections, direct function calls, no speculative architecture (no entity-component frameworks, event buses or DI containers unless the GDD needs them).
* Simplicity applies to **how** you build, never to **what** you build. Every scene, screen and verb in the GDD Experience Map is built. Do not replace a scene with an overlay, or a screen with a menu manager, to save effort.

### B. Visual Separation
* Gameplay logic computes positions, health, cooldowns and state transitions.
* The presentation layer draws entities and UI. It uses project-local assets, the visual briefing and color tokens in `design.md`. Runtime visual code belongs in presentation modules. No magic colors or inlined asset geometry in gameplay logic.

### C. Missing Documents
* If `GDD.md` or `design.md` is absent, use the fallback palette and say so in the handoff: `bg: #181a1b, surface: #2c3032, border: #4f585d, actor: #e07a5f, threat: #d62828, accent: #f2cc8f`. The stack gate still applies.

### D. Tuning in One Place
* Put all balancing values from the GDD's Provisional Tuning Values in one constants or data file. Gameplay code reads from it. Never scatter numbers.

---

## 2. Architecture

### A. Scene and Screen Manager
Derive the structure from the GDD Experience Map, not from a fixed template.
* One entry per Experience Map ID. Each scene has `enter`, `update`, `render`, `exit`. Each screen has the same, plus input capture.
* A small manager owns the current scene, a screen stack and transitions. Transitions follow the Experience Map's `Enter From -> Exit To` column.
* Shared state (resources, unlocks, progress) lives in one game-state object that scenes read and write, matching the Resource Graph.
* Provide a clean reset or new-run function that restores initial state from the tuning file without restarting the app. Add save/load only when the GDD asks for it.
* A title or pause menu is built only as the GDD defines it.

### B. Core Loop
* Measure elapsed time per frame, clamp `dt` to at most 0.1 s, and scale velocities by `dt`.
* Use direct AABB or circle checks. Keep them linear unless entity counts exceed several hundred.

### C. Particles and Juice
* Simulate particles with lifetime and velocity. Draw them with engine primitives or with exported FX textures, with runtime emitter behavior specified in the brief.
* Wire feedback to the events listed in the GDD Verbs table (hit, pickup, craft, death, unlock).

### D. Sound
* Use the engine's audio facilities. Add no external sound files unless `design.md` lists them. Map cues to events from `design.md`.

---

## 3. Consuming Project-local Assets

Read the [delivery contract](../game-orchestrator/references/asset_handoff.md). Prefer GLB models and PNG artwork. Use stable project paths or normal engine resource references; a custom runtime manifest is optional. Do not regenerate exportable static artwork at game startup.

Distinguish exported art from runtime visuals in the brief. Use live engine text, controls, particles, shaders or deformation when behavior requires live state, consuming exported components where possible. Ask the user's art preference if unspecified; use [game-asset-kit](../game-asset-kit/SKILL.md) to assess direct meshes versus SDF/solids/Canvas. Production tools are not game-runtime dependencies.

Test actual files in the destination engine, including pivots, units, materials and clips. Consume sprite metadata only when needed. Preserve generation sources. Register development placeholders in one list and log PLACEHOLDER: <id>; replace them before final delivery. Approved runtime visuals are implementation, not placeholders. Broken required resources fail visibly with the asset ID.

---

## 4. Implementation Protocol (Vertical Slice First)

1. **Stack Gate.**
2. **Entry Point:** use the structure that the stack expects.
3. **Input Table:** bind keyboard, mouse, touch or gamepad.
4. **Walking Skeleton:** build the scene and screen manager and **every Experience Map entry** as a reachable instance with its core verb working, using placeholders. Order: the core scene first, then the other scenes and screens in the order a player reaches them. The player must be able to travel the whole map end to end.
5. **Resource Graph:** wire sources, sinks and the UI that shows each resource.
6. **Challenge (Parameter A) and Growth (Parameter B):** wire per the GDD, if present.
7. **Content Fill:** add content per the GDD Content Inventory.
8. **Assets and Juice:** swap placeholders for exported assets and implement the specified runtime visuals. Add particles and sound cues.
9. **Self-Check:** launch the game, travel every Experience Map entry, trigger each verb once, and confirm that there are no runtime errors.

If the build shows that the GDD is wrong or incomplete (a verb without a scene, an orphan resource), raise a **Change Request** to the orchestrator describing the gap. Do not patch around it silently.

---

## 5. Handoff

When all Experience Map entries are reachable and working, with real assets or logged placeholders, the milestone is complete. The next phase is Review & QA (`game-reviewer-qa`).
