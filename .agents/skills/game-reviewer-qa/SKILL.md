---
name: game-reviewer-qa
description: >-
  Audits the completed game by launching it and traveling every scene and screen in the GDD Experience Map,
  then checks resource and verb coherence, tuning and palette compliance, and a short code checklist.
  Operates strictly as an isolated subagent and emits qa_report.md with a verdict of APPROVED, REVISION REQUIRED or BLOCKED.
---

# Game Reviewer & QA Skill (Isolated QA Subagent)

This skill guides an independent auditor. The primary evidence is **the running game**. The code and documents are secondary evidence.

---

## 1. Core Directives

* **Run It.** Launch the game with whatever the stack allows (local server plus a headless browser with screenshots, the engine's CLI, or the project's run instructions). Capture a screenshot or log for every scene and screen visited.
* **Cannot Run = BLOCKED.** If the game cannot be launched, the verdict is `BLOCKED`, with the cause. Never `APPROVED` from code reading alone.
* **Zero Author Bias.** No memory of implementation trade-offs.
* **Contract and Coherence.** Verify against `GDD.md` and `design.md`. In addition, report structural gaps you observe (see Pillar 2), even when the document is silent. Report them as findings with evidence. Do not design new features yourself.
* **Standalone Mode.** If `GDD.md` or `design.md` is absent, mark document-based items `SKIPPED (Standalone)` and audit Pillars 0, 2 (observed gaps only), 4 and 5.
* **Surgical Reporting.** Cite file, line, and violated requirement.

---

## 2. The Pillars

### Pillar 0: It Runs
* Starts with no console or runtime errors. Reaches the first interactive moment. A new run or reset works without restarting the app. `dt` is clamped.
* Placeholder check: list every `PLACEHOLDER:` log line. Any placeholder in a final build is a FAIL.

### Pillar 1: Experience Map Coverage
For every entry in the GDD Experience Map:
* Reachable by normal play, via the listed `Enter From` path.
* Its unique verbs work (trigger each once).
* Exit transitions work and land where the map says.
* Visibly distinct from the other entries (camera, layout, backdrop), as the GDD states.
* A scene or screen that exists in the GDD but not in the game is a FAIL. A menu manager standing in for a defined scene is a FAIL.

### Pillar 2: Coherence of Systems
* **Orphans:** a resource that is gained but never spent, or spent but never gained, or never visible in the UI.
* **Dead ends:** a screen with no exit, a scene the player cannot leave, a state that cannot be recovered from.
* **Meta loop:** does the result of one session visibly change the next?
* **Minute-10 Test:** after playing the equivalent of ten minutes (or the content available), does the player do something new compared with minute 1?

### Pillar 3: Tuning and Design Compliance
* Constants match the GDD Provisional Tuning Values and live in one place. Flag hardcoded deviations.
* Palette: colors come from `design.md` tokens. Flag magic color literals.
* UI: HUD and screens follow the layouts in `design.md` Screens & Menus.

### Pillar 4: Feedback (Juice)
* Impacts show deformation or hit flash. Deaths and pickups spawn particles. Major events give screen feedback. Cues map to the Verbs table.

### Asset delivery checks
* Read the asset briefing and [delivery contract](../game-orchestrator/references/asset_handoff.md). Confirm exported files load in the destination engine and match dimensions, pivots, appearance and clips. Review technical evidence and inspect actual appearance.
* Runtime visuals require the stated live-state reason and engine execution. Do not count approved runtime items as placeholders or demand a custom manifest. Browser preview and validator success alone do not prove game integration.

### Pillar 5: Code Checklist (short)
* Presentation code has no physics or input logic. No duplicated drawing routines made only for scale. Report only what blocks maintenance. Style opinions are out of scope.

---

## 3. Output Specification: `qa_report.md`

```markdown
# Quality Assurance & Compliance Report

## 1. Executive Status
* **Verdict:** [APPROVED | REVISION REQUIRED | BLOCKED]
* **How the game was run:** [command / method and evidence paths]
* **Target Stack:** [from design.md section 0]
* **Date of Audit:** [timestamp]

## 2. Experience Map Walkthrough
| Map ID | Reached | Verbs Work | Exit Works | Distinct | Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |

## 3. Compliance Checklist
| Item | Pillar | Status | Observations |
| :--- | :--- | :--- | :--- |
| Runs without errors | 0 | PASS / FAIL | |
| No placeholders in final | 0 | PASS / FAIL | |
| Experience Map coverage | 1 | PASS / FAIL | |
| Resource graph (no orphans) | 2 | PASS / FAIL | |
| No dead ends | 2 | PASS / FAIL | |
| Minute-10 Test | 2 | PASS / FAIL | |
| Tuning values | 3 | PASS / FAIL | |
| Palette / UI layouts | 3 | PASS / FAIL | |
| Feedback / juice | 4 | PASS / FAIL | |
| Code checklist | 5 | PASS / FAIL | |

## 4. Defect Log
| ID | Target | Location | Contract / Gap | Required Correction | Owner Skill |
| :--- | :--- | :--- | :--- | :--- | :--- |

## 5. Final Recommendation
* [APPROVED: launch instructions.]
* [REVISION REQUIRED: which skill should fix which defects.]
* [BLOCKED: what prevents running and who must fix it.]
```

---

## 4. Handoff

* **APPROVED:** deliver to the user with launch instructions.
* **REVISION REQUIRED / BLOCKED:** return `qa_report.md` to `game-orchestrator`, which re-engages the owner skill of each defect. Gaps owned by the GDD go back through a Change Request to `game-designer`.
