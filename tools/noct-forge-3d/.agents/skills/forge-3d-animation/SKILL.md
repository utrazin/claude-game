---
name: forge-3d-animation
description: Add or revise native Blockbench animation clips on an existing BBModel with a saved Python recipe, independently of UV and geometry recipes.
---

# Forge 3D Animation

Animate the current BBModel, including external files and manual edits. No UV or geometry recipe is required. The animation recipe replaces only clips it declares; unrelated clips remain.

```bash
py -3.12 -m Tools.forge animation PROJECT --asset ID --controls
py -3.12 -m Tools.forge animation PROJECT --asset ID --rig
py -3.12 -m Tools.forge animation PROJECT --asset ID
py -3.12 -m Tools.forge animation PROJECT --asset ID --check
```

Discover controls before authoring. Address transform groups and bones by semantic name, or full hierarchy path when ambiguous. `--rig` adds rest world pivots, local axes (the world direction of each control's x, y and z), bone tips and lengths for choosing IK chains, targets and `aim` axes. `--check` validates existing clips without running the recipe.

Use FK keys (`key`, `sample`) for motion that is rotation by nature: breathing, swings, tails, ears, secondary motion. Use IK (`clip.chain(start, end).reach(...)`, `clip.chain(control).aim(...)`) when something must touch or face a point in the world: planted feet, a hand on a prop, a head tracking a target. IK bakes plain rotation keys; animate parents first. Gait timing, stride, poses and body motion are the recipe's design for its own model: the skills give the tools and the checks, not values to copy.

Check chains numerically, not only by renders: `forge animation PROJECT --asset ID --inspect CLIP --chain START [END] [--rate 120]` samples between keys and prints bends, where each inner joint points, reach used, tip position and velocity. It warns about cuts (abrupt changes of angular velocity), tip jolts (sudden stops or starts), snaps near full reach and flips. Smooth curves, phase blends and springs for recipes are in `lib.motion` (`quintic`, `periodic_curve`, `periodic`, `spring_follow`, `smooth_periodic`).

Edit the registered `generate_animation.py` using `AnimationEditor.from_bbmodel(recipe_paths(__file__).model)`. Read [animation API](references/animation-api.md) for keys, interpolation, cycles and a recipe example. Full signatures: [generated lib reference](../../../docs/api/lib.md), [CLI](../../../docs/api/cli.md). Never build geometry as part of an animation recipe.

Inspect poses with `Tools.forge capture PROJECT --asset ID --view front --clip idle --time 0,0.25,0.5` or play/scrub in the official project viewer. For user-edited clips use `forge-3d-manual-edits` if reconciliation was requested. Model regeneration resets clips, but does not authorize running further stages automatically.

## Before presenting a clip
Three checks with different reach; report each for what it is:
1. `--check` (and the recipe's `PASS`): the clips are valid data. It says nothing about how they move.
2. `--inspect` on every limb chain of every clip (both sides, legs and arms, plus tails or other long chains): read the warnings and the numbers around them. No warning means no flagged cut, jolt, snap or flip in that chain, not a natural motion.
3. Captures across the cycle from the side and the front (`--time` at several phases): contact with the ground, posture, each limb moving in the phase the recipe intends (and on the side it intends), and clips that should read differently (walk and run) actually differing.

Present technical results as technical, and leave the artistic approval to the user.
