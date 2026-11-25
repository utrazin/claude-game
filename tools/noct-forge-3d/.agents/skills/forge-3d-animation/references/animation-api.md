# Animation authoring API

Full `AnimationEditor` signatures: [generated lib reference](../../../../docs/api/lib.md).

The CLI executes the registered saved recipe, supplies project/asset context and never runs the geometry recipe. Read [projects](../../../../docs/projects.md) for discovery and [pipeline](../../../../docs/pipeline.md) for dependencies.

```python
from lib import AnimationEditor
from Tools.recipe_context import recipe_paths

def main():
    editor = AnimationEditor.from_bbmodel(recipe_paths(__file__).model)
    clip = editor.animation("idle", duration=1.0, loop=True)
    clip.group("head").key(0, rotation=(0, 0, 0)).key(.5, rotation=(0, 15, 0)).key(1, rotation=(0, 0, 0))
    editor.save()

if __name__ == "__main__":
    main()
```

Use controls actually present in the selected BBModel. `clip.group(name)` and `clip.bone(name, armature="rig")` return tracks. Their `key(time, position=(x,y,z), rotation=(x,y,z), scale=(x,y,z), interpolation="linear")` calls chain; omit untouched channels. Values are offsets from the rest pose, rotations in degrees, scale factors with rest=1. Interpolation is `linear`, `constant` (STEP), `catmullrom`, or `bezier`. Bezier accepts per-axis `bezier_left_time`, `bezier_left_value`, `bezier_right_time`, and `bezier_right_value` vectors; defaults match Blockbench's standard handles.

For cycles, `track.sample("rotation", start, end, fps, function)` takes a function returning a three-number vector and includes both endpoints (the last key lands exactly on `end`, so sampling the same channel over adjacent intervals collides at the shared time: start the next interval one sample later, or sample the whole span once). `loop=True` loops; `loop="hold"` keeps the last pose. Saving warns when a loop's first and last poses differ.

## Inverse kinematics

IK solves rotations so a chain's tip lands on a world point, then writes them as ordinary linear rotation keys (editable in Blockbench, exported like any key). Coordinates are model units in rest world space, the numbers `--rig` prints.

```python
clip = editor.animation("walk", duration=1.2, loop=True)
clip.bone("hips").sample("position", 0, 1.2, 24, lambda t: (0, -0.3 * abs(math.sin(math.pi * t / 0.6)), 0))

foot = editor.rest_point("shin_L", "tip")                        # rest position of the tip
leg = clip.chain("thigh_L", "shin_L", limits={"shin_L": {"x": (-150, 0)}})
report = leg.reach(0, 1.2, 24, target=lambda t: step(foot, t), bend_toward=(0.1, 0, 1))  # knee forward

clip.chain("upper_arm_R", "forearm_R").reach(0, 1.2, 24,
    target=lambda t: clip.world_point("chest", t, point=(3, 9, -2)))   # hand follows the chest
clip.chain("head").aim(0, 1.2, 24, target=(0, 14, -30), axis="-z")
clip.chain("thigh_R", "shin_R").reach(0.3, 0.6, 24, target=clip.chain("thigh_R", "shin_R").pin(at=0.3))
```

- `clip.chain(start, end=None, *, tip=None, limits=None)` takes groups or bones, `end` a descendant of `start`. Its tip is the end bone's tip, or the end group's pivot (that group is not rotated), or `tip=(x, y, z)`, a rest model-space point carried by the end control.
- `reach(start, end, fps, *, target, pole=None, bend_toward=None, tolerance=0.01)`: `target`, `pole` and `bend_toward` are values or `t -> value` functions. Two segments solve analytically and fold about their rest hinge axis. Steer the knee or elbow with `bend_toward`, a world direction such as `(0, 0, 1)`, or with `pole`, a world point it turns toward. The default follows the rest bend: it never flips, but on real models it is often several degrees off, so prefer an explicit direction. Three or more segments use FABRIK. A chain straight at rest needs one of the two.
- `aim(start, end, fps, *, target, axis="+y", up=None, up_axis=None)` turns one control's local `axis` (`"-z"`, `"+x"`, ... or a vector) toward the target and keeps it level (`up` overrides the world up). `axis` is in the control's own frame, not in model space: `--rig` lists where each local axis points in the world at rest. Pick the local axis whose listed direction matches the model direction you mean (for a foot, the one pointing from ankle to toe); for a direction between axes, its local vector is `(dot(d, x), dot(d, y), dot(d, z))` with `x`, `y`, `z` the listed directions.
- `limits` are rotation-offset degrees per axis, the same values `key()` takes. Clamped solutions are refined and reported.
- Helpers: `editor.rest_point(control, point=None)` (pivot, `"tip"`, or a carried model-space point), `clip.world_point(control, t, point=None)` (the same at time `t`, from the keys declared so far), `chain.pin(at=t)` (where the tip is at `t`).

Rules: animate a chain's parents before calling `reach`/`aim`, since each sample is solved against the pose already keyed (saving fails if an ancestor gets keys afterwards). IK owns the rotation of chain controls inside its interval, so existing rotation keys there are refused. Consecutive intervals of the same chain may share a boundary time. Position and scale of chain controls stay free, and scaled controls are refused. Euler values are kept continuous between samples, including through gimbal lock.

Each call returns an `IKReport` (`max_error`, `unit`, `unreachable` time ranges, `limited` controls, `ok`) and warns when the tolerance is exceeded. The warning shows up as `[animation] WARN` in `forge animation`.

After saving, `forge animation PROJECT --asset ID --inspect CLIP --chain START [END] [--rate N] [--json]` (or `editor.inspect_chain(clip, start, end, rate=120)`) samples the saved clip `N` times per second, between keys, as the viewer interpolates them.

- Per sample: the bend of each inner joint, the direction each one points, the reach used, and the tip's position and velocity.
- Per control: the fastest rotation and the sharpest jerk, in °/s.
- Warnings:
  - **cuts**: a control's angular velocity jumps against its trend. Velocities are measured over 1/30 s windows and compared by second difference.
  - **tip jolts**: the tip stops or starts abruptly.
  - **snaps**: above 99.8 % reach while the inner joint still bends fast.
  - **pops**: a gross rotation flip.

The warnings are review hints: read the numbers around each one, then look at `forge capture --clip`. The text view prints about 30 rows and `--json` has every sample.

## Motion helpers (`lib.motion`)

Plain deterministic functions for recipes. `quintic` and `periodic_curve` take numbers (call them per axis for a vector), `spring_follow` takes points, `periodic` and `smooth_periodic` take numbers or 3-vectors.

- `quintic(p0, p1, v0, v1, s)`: from `p0` to `p1` as `s` goes 0 → 1, with slopes `v0`, `v1` (per unit of `s`, so multiply a speed by the duration `s` spans) and no acceleration at the ends. Use it to join phases without a jolt.
- `periodic_curve(keys, x)`: a looping curve through `(x in [0, 1), value)` keys, with continuous slope. It is flat at plateaus and turning keys, so it never overshoots.
- `periodic(samples, period)`: a function of time interpolating evenly spaced samples over a loop.
- `spring_follow(target, frequency, damping, period)`: a point trailing `target(t)` on a damped spring, settled into its loop. Aim or reach a control at it for follow-through.
- `smooth_periodic(samples, period, seconds)`: a Gaussian blur that wraps around the loop; vectors are blurred per axis. It returns the blurred samples as a list: wrap it in `periodic(..., period)` for a function of time. Blurring a target path also moves its extremes, so a planted foot no longer stays exactly on its contact height; check contact after blurring.

`editor.remove_animation(name)` explicitly removes a clip. Saving preserves clips the recipe does not declare. GLB delivery bakes curves and deterministic arithmetic expressions to numeric samples; expression evaluation needs project/editor context for some Molang variables. See [exports](../../../../docs/exports.md) and the [animation export plan](../../../../docs/animation-export-plan.md).
