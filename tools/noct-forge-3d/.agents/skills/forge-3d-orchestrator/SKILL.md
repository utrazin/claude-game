---
name: forge-3d-orchestrator
description: Decide which forge-3d skill applies and in what order for an asset request, and the rules that hold across all of them. Use first when a request spans several stages or it is unclear where to start.
---

# Forge 3D Orchestrator

Recipes describe regeneration. The current `.bbmodel` is the serialized working artifact between stages, including manual edits. Read [the pipeline contract](../../../docs/pipeline.md) for stage dependencies.

## Which skill
| The user wants | Skill |
|---|---|
| A new shape, a rig, a change to geometry | `forge-3d-model` |
| A critique of the shape against a reference | `forge-3d-visual-conformance` |
| UVs or a texture | `forge-3d-texture` |
| Images produced outside the repository (2D asset forge, another tool or person), only when explicitly asked | `forge-3d-texture` ([art requests](../forge-3d-texture/references/art-requests.md)) |
| Clips | `forge-3d-animation` |
| To keep something they changed in Blockbench, or to use a `.bbmodel` no recipe made | `forge-3d-manual-edits` |
| To see the asset from several views | `forge-3d-visualize` |
| Final GLB/PNG/BBModel products, parts or expression variants | `forge-3d-export` |
| A new machine, a missing module/browser/node error, or "does this computer have what it needs" | `forge-3d-setup` |

## Order
Run only requested stages. UV reads BBModel geometry; painting requires existing UV; animation reads BBModel controls independently of UV and model recipes. Missing prerequisites stop the command. Regenerating geometry resets UVs, texture registration and clips; discuss the required subsequent work in the requested scope. A clay review happens when asked.

## Unified Build
Individual stage commands are canonical. The optional shortcut requires explicit stages:
```bash
py -3.12 -m Tools.forge build projects/<name> --asset <id> --stages uv,texture
```
Include `model` only when geometry regeneration was requested. Never use the shortcut if the conversation indicates manual BBModel edits unless those edits have been reconciled into the recipe or the user chose `ASSET_BUILD_GEOMETRY = "manual"`. That literal in generate_model.py skips geometry only in the shortcut. A missing/invalid model never authorizes regeneration.

## A vague or one-line request
Do the smallest stage that satisfies it: a model only, unless texture or animation is named. Reuse the selected project; register another asset when requested, rather than creating a project per asset. Default to free-form modeling unless the user says voxel, blocky or Minecraft-style. Without a size, characters are about 32 units tall and hand-held items proportionate to that.

## Project context and delegation
Initialize with `Tools.forge project init PROJECT --asset ID`; add another source with `Tools.forge asset init PROJECT --asset ID`. Init writes deterministic recipes and a manifest, never runs geometry. The project viewer is shared, automatic and scoped to that project. Read [projects](../../../docs/projects.md) for paths, recipe context and multi-asset rules.

A subagent handoff supplies the project path, asset ID or exact BBModel, requested stage, user constraints, manual geometry policy and requested products. Only requested stages run. Jobs writing the same BBModel or manifest must run serially; independent assets can be delegated when authorized. A subagent reports artifacts changed and unmet prerequisites, without implicitly rebuilding them.

## Rules that hold everywhere
- Work only on the project the user named; sibling projects are off-limits unless asked.
- Never automate a GUI editor. For manual changes, reconcile the recipe or mark geometry manual according to the user's choice; downstream stages use the edited BBModel directly.
- Consult `model-rules/` only when the user asks for one of its styles.
- Use skill references as the authoring API guide. Repository maintenance may inspect implementation files as needed.
- Full code-derived signatures and CLI options are in the [generated API reference](../../../docs/api/index.md); skills keep only the operational subset.
