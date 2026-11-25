---
name: game-orchestrator
description: >-
  Orchestrates end-to-end game creation through specialized skills and isolated subagents.
  Runs a single intake (engine, language, assets folder, unit, scope tier), lazily activates each phase,
  runs the programmer's walking skeleton in parallel with asset production, and supports project-local GLB/PNG production with explicit runtime-art decisions.
---

# Game Orchestrator Skill

This skill governs the execution lifecycle of a game. It assesses the workspace, activates the next phase on demand, and dispatches work to isolated subagents. It does not choose an engine, language or scope. Those belong to the user.

---

## 1. Core Principles

1. **Always Playable, Never Broken.** The final deliverable is a launchable, interactive game that QA has actually run. Robustness is a gate. It does not limit the design's scope.
2. **Scope Is Declared by the User.** The scope tier (`prototype`, `vertical_slice`, `small_complete`) is recorded at intake. Skills do not shrink it on their own.
3. **Lazy Loading.** Read a phase's skill only when that phase becomes active.
4. **Approved Artifacts Are Baselines, Not Frozen.** `GDD.md`, `design.md` and the asset briefing are consumed downstream. They may change only through a **Change Request**: the programmer, QA or a critic names the gap, the owning skill revises the artifact, and the change is noted in the artifact's changelog. Never change an artifact silently.
5. **No Rework Without Cause.** If an artifact exists and meets requirements, keep it and advance.
6. **The User Decides the Stack.** Never choose an engine, language or framework. Record answers once, in `design.md` section 0.
7. **Project-local Art.** Sources and exports belong to the consuming project. Prefer GLB/PNG; explicitly specify live engine visuals. Use the [delivery contract](references/asset_handoff.md) and [asset kit](../game-asset-kit/SKILL.md).

---

## 2. Intake (One Message, Then Wait)

Before the design phase, ask the user once, in a single message, for whatever the prompt and workspace do not already answer:

1. Engine or framework, and programming language.
2. Absolute path of the game assets folder.
3. Unit of measure (for example, 1 unit = 1 metre, or pixels).
4. **Scope tier:** `prototype` (one scene, proves the loop), `vertical_slice` (every kind of scene and screen in one working instance), `small_complete` (all scenes and content).

5. Art style and useful references if unspecified: ask what kind of art the user wants; do not silently choose a preset.

Rules:
* Do not choose defaults. If the user declines, stop and say which step is blocked.
* If the prompt or `GDD.md` already names an item, record it and do not ask again.
* Record the answers in `design.md` section 0 (stack) and in the GDD (scope tier).
* Standalone requests that do not involve code or assets skip the stack questions.

---

## 2b. Environment & Setup Gate (Prerequisites)

When the project workflow requires local tooling, procedural assets, or scripts:
1. **Node.js Verification**: Check if Node.js (v22+) is installed on the system (`node -v`).
   * **If Node.js is NOT installed**: Instruct the user immediately on how to install it:
     * **Windows**: Run `winget install OpenJS.NodeJS.LTS` in PowerShell or download from [nodejs.org](https://nodejs.org). Note: Restart the terminal if `node -v` is not recognized immediately after install.
     * **macOS**: Run `brew install node` or download from [nodejs.org](https://nodejs.org).
     * **Linux**: Run `nvm install --lts` or install via NodeSource (`curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs`).
   * Halt any operations that depend on Node.js until installation is completed.
2. **Asset Kit Dependencies**: If procedural asset generation (`tools/asset-kit`) is required:
   * Check if `tools/asset-kit/node_modules` exists.
   * If missing (e.g., cleared to reduce workspace footprint), automatically run `npm install` (or `npm ci`) inside `tools/asset-kit` before executing preview, verify, or export tasks.

---

## 3. Workspace State Audit Matrix

| Milestone | Required Artifacts | Next Action |
| :--- | :--- | :--- |
| **0. Unstarted** | Nothing | Run intake (section 2). If theme or loop is undefined, dispatch isolated subagent `game-researcher`. Otherwise load `game-designer`. |
| **1. Researched** | `references.md` | Load `game-designer` (it dispatches `game-design-critic` once). |
| **2. Designed** | `GDD.md` with Experience Map, Resource Graph, loops and provisional tuning | Load `game-art-director`. The programmer's walking skeleton may start now (Step 3b). |
| **3. Art Directed** | `design.md` with section 0 filled, per-scene staging, Screens & Menus, Asset Briefing Table | Produce assets (section 5). In parallel, continue the walking skeleton. |
| **4. Assets Delivered** | Project-local GLB/PNG outputs, sources and checks; runtime items specified | Integrate files and implement runtime visuals in the destination engine. |
| **5. Assets Integrated** | Files import correctly and runtime visuals run in-engine | Remove placeholders and inspect appearance in context. |
| **6. Programmed** | Every Experience Map entry reachable. Zero placeholders. | Dispatch isolated subagent `game-reviewer-qa`. |
| **7. Verified** | `qa_report.md` with `APPROVED` (the game was run) | Deliver with launch instructions. |

---

## 4. Stack Gate

The stack is required before any code is written and before any asset is dispatched, because export format depends on it. It is collected at intake. If a later phase finds section 0 incomplete, stop and ask the user.

---

## 5. Project-local Asset Production

Read [game-asset-kit](../game-asset-kit/SKILL.md) and the [delivery contract](references/asset_handoff.md) when production activates. Ask for missing art style; record file/runtime delivery, technique/rationale and destination in the existing briefing. Prefer GLB/PNG and justify live-state behavior.

Projects choose tools and order of work. Sources, checks and exports stay in the project. No external repositories, mandatory manifest or allocation phase. If delegating asset families, assign disjoint outputs and one owner for shared lists. Reopen exported files, inspect appearance and test destination-engine integration. Implement and exercise runtime visuals in that engine. Fix failed deliveries without rebuilding unrelated art.

---

## 6. Operational Pipeline

### Targeted & Standalone Requests
If the user asks for one deliverable, activate that skill or section directly, without forcing the cascade. Apply the intake rules only if the deliverable involves code or assets.

### Full Pipeline

#### Step 1: Assess & Route
Scan the workspace, cross-reference the matrix, and run intake if the next milestone needs it.

#### Step 2: Activate the Current Phase
* Research -> isolated subagent with `.agents/skills/game-researcher/SKILL.md`
* Design -> `.agents/skills/game-designer/SKILL.md`
* Art direction -> `.agents/skills/game-art-director/SKILL.md`
* Assets -> section 5
* Code -> `.agents/skills/game-programmer/SKILL.md`
* QA -> isolated subagent with `.agents/skills/game-reviewer-qa/SKILL.md`

#### Step 3: Validate Completion
1. Confirm the phase's output exists on disk.
2. On success, return to Step 1.
3. If QA or a critic flags a defect, re-engage only the owning skill. If the defect is a gap in `GDD.md` or `design.md`, open a Change Request.

#### Step 3b: Parallel Skeleton
Once the GDD's Experience Map exists, the programmer can build the walking skeleton with marked placeholders while art direction and asset production run. Assets then replace the placeholders.

---

## 7. Rules That Hold Everywhere

* Work only inside the game workspace and the project the request names.
* Preserve project-local art sources and unrelated user work; no external asset repository is required.
* Never rebuild a prerequisite on a subagent's behalf unless the user asked. A missing file is reported.
* Never change the stack after programming has started without asking the user.
* Changes to `GDD.md` or `design.md` go through the owning skill by Change Request.
