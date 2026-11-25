"""Inverse kinematics baked into native rotation keyframes.

A chain is a run of animatable controls (transform groups or armature bones) from a start control
down to an end control. ``reach`` moves the chain's tip onto a world target; ``aim`` points one
control's axis at a target. Every sample is solved against the pose the clip already has at that
time (so parents must be animated first) and written as ordinary rotation keys through
``AnimationTrack.key``: the result is plain FK data, editable in Blockbench and exported like any key.
"""
from __future__ import annotations

import json
import math
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .kinematics import (Frame, IDENTITY, Rig, add, axis_rotation, continuous_euler, cross, dot, inverse, mm, mv, norm,
                         pose_from_tracks, reject, rot_zyx, scale, shortest_rotation, signed_angle, sub,
                         transpose, unit)

if TYPE_CHECKING:
    from .animation import AnimationClip

_AXES = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


@dataclass(frozen=True)
class IKReport:
    """Outcome of one ``reach``/``aim`` bake.

    ``max_error`` is the largest tip-to-target distance in model units (``reach``) or the largest
    angle in degrees between the aimed axis and the target (``aim``). ``unreachable`` lists the time
    intervals where the target was farther than the chain can stretch, ``limited`` the controls whose
    rotation limits clamped the solution. ``ok`` is true when every sample met the tolerance.
    """
    chain: tuple[str, ...]
    samples: int
    max_error: float
    unit: str
    unreachable: tuple[tuple[float, float], ...]
    limited: tuple[str, ...]
    ok: bool


def _value_at(value, time: float, label: str):
    point = value(time) if callable(value) else value
    try:
        values = tuple(float(item) for item in point)
    except TypeError as exc:
        raise ValueError(f"{label} must be three numbers or a function of time returning three numbers") from exc
    if len(values) != 3 or not all(math.isfinite(item) for item in values):
        raise ValueError(f"{label} must be three finite numbers, got {point!r}")
    return values


def _axis(value, label: str):
    if isinstance(value, str):
        text = value.strip().lower()
        sign = -1.0 if text.startswith("-") else 1.0
        key = text.lstrip("+-")
        if key not in _AXES:
            raise ValueError(f"{label} must be '+x', '-x', '+y', '-y', '+z', '-z' or a vector, got {value!r}")
        return scale(_AXES[key], sign)
    return unit(_value_at(value, 0.0, label))


def _intervals(samples: list[tuple[int, float]]) -> tuple[tuple[float, float], ...]:
    """Merge (sample index, time) pairs of consecutive samples into (first, last) time runs."""
    runs: list[list] = []
    for index, time in samples:
        if runs and runs[-1][2] == index - 1:
            runs[-1][1], runs[-1][2] = time, index
        else:
            runs.append([time, time, index])
    return tuple((round(first, 6), round(last, 6)) for first, last, _ in runs)


# ----------------------------------------------------------------------------- position solvers
def two_bone(p0, p1, p2, target, pole=None, *, label="chain"):
    """Joint positions (q1, q2) and bend-plane normal of a two-segment chain reaching toward ``target``.

    The bend plane follows ``pole`` (a world point the middle joint turns toward) when given, otherwise
    the rest bend carried along with the chain, so the middle joint never flips sides. The normal is
    defined even when the chain is fully stretched (it is None only for a chain straight at rest
    without pole), so callers can keep the joints' hinge orientation continuous through extension.
    """
    l1, l2 = norm(sub(p1, p0)), norm(sub(p2, p1))
    offset = sub(target, p0)
    distance = norm(offset)
    rest_axis = sub(p2, p0)
    if distance < 1e-9:
        direction = unit(rest_axis) if norm(rest_axis) > 1e-9 else unit(sub(p1, p0))
    else:
        direction = unit(offset)
    distance = min(max(distance, abs(l1 - l2) + 1e-9), l1 + l2)
    if pole is not None:
        bend = reject(sub(pole, p0), direction)
    else:
        bend = (0.0, 0.0, 0.0)
        if norm(rest_axis) > 1e-9:
            rest_bend = reject(sub(p1, p0), unit(rest_axis))
            bend = reject(mv(shortest_rotation(unit(rest_axis), direction), rest_bend), direction)
    along = (l1 * l1 - l2 * l2 + distance * distance) / (2 * distance)
    height = math.sqrt(max(0.0, l1 * l1 - along * along))
    if norm(bend) < 1e-9:
        if height > 1e-6:
            raise ValueError(f"{label} is straight in its rest pose, so the bend direction is undefined; pass "
                             "pole=(x, y, z), a world point the middle joint should turn toward")
        bend_dir = (0.0, 0.0, 0.0)
    else:
        bend_dir = unit(bend)
    q1 = add(add(p0, direction, along), bend_dir, height)
    normal = unit(cross(bend_dir, direction)) if norm(bend_dir) > 0 else None   # = cross(q1 - p0, q2 - q1)
    return q1, add(p0, direction, distance), normal


def fabrik(points, target, pole=None, *, iterations=64, tolerance=1e-5):
    """Joint positions of an N-segment chain reaching toward ``target`` (FABRIK, optional pole)."""
    lengths = [norm(sub(b, a)) for a, b in zip(points, points[1:])]
    base = points[0]
    if norm(sub(target, base)) >= sum(lengths):
        direction = unit(sub(target, base))
        out, cursor = [base], base
        for length in lengths:
            cursor = add(cursor, direction, length)
            out.append(cursor)
        return out
    joints = list(points)
    for _ in range(iterations):
        joints[-1] = target
        for i in range(len(joints) - 2, -1, -1):
            joints[i] = add(joints[i + 1], unit(sub(joints[i], joints[i + 1])), lengths[i])
        joints[0] = base
        for i in range(1, len(joints)):
            joints[i] = add(joints[i - 1], unit(sub(joints[i], joints[i - 1])), lengths[i - 1])
        if pole is not None:
            for i in range(1, len(joints) - 1):
                axis = sub(joints[i + 1], joints[i - 1])
                if norm(axis) < 1e-9:
                    continue
                axis = unit(axis)
                current = reject(sub(joints[i], joints[i - 1]), axis)
                wanted = reject(sub(pole, joints[i - 1]), axis)
                if norm(current) < 1e-9 or norm(wanted) < 1e-9:
                    continue
                turn = axis_rotation(axis, signed_angle(current, wanted, axis))
                joints[i] = add(joints[i - 1], mv(turn, sub(joints[i], joints[i - 1])))
        if norm(sub(joints[-1], target)) < tolerance:
            break
    return joints


# ----------------------------------------------------------------------------- chain
class IKChain:
    """A run of controls solved together; create with ``clip.chain(start, end)``."""

    def __init__(self, clip: "AnimationClip", path: list[str], *, tip=None, limits=None):
        self.clip = clip
        self.rig: Rig = clip.editor.rig
        self.path = path
        node = self.rig.nodes
        end = node[path[-1]]
        self.tip = None if tip is None else _value_at(tip, 0.0, "tip")
        if self.tip is not None or (end.kind == "bone" and (end.length or 0) > 1e-9):
            self.joints = list(path)
        else:
            self.joints = list(path[:-1])        # the end control's pivot is the tip
        self.names = tuple(node[uid].name for uid in path)
        self.label = " -> ".join(self.names)
        self.limits = self._limits(limits or {})

    def _limits(self, limits: dict) -> dict[str, tuple]:
        resolved = {}
        for name, axes in limits.items():
            matches = [uid for uid in self.path if self.rig.nodes[uid].name == name or
                       self.clip.editor._control_path(uid) == name]
            if not matches:
                raise KeyError(f"Limit for {name!r} is not a control of chain {self.label}")
            bounds = [(-math.inf, math.inf)] * 3
            for axis, pair in axes.items():
                if axis not in _AXES or len(pair) != 2 or pair[0] > pair[1]:
                    raise ValueError(f"Limits of {name!r} must map 'x'/'y'/'z' to (minimum, maximum) degrees")
                bounds["xyz".index(axis)] = (float(pair[0]), float(pair[1]))
            resolved[matches[0]] = tuple(bounds)
        return resolved

    # --- evaluation helpers
    def _base(self, time: float, rotating: list[str]):
        pose = pose_from_tracks(self.clip._tracks, time, skip={(uid, "rotation") for uid in rotating})
        frames = self.rig.fk(pose)
        for uid in [*self.rig.ancestors(self.path[0]), *self.path]:
            linear = frames[uid].linear
            gram = mm(transpose(linear), linear)
            if any(abs(gram[i][j] - (1.0 if i == j else 0.0)) > 1e-6 for i in range(3) for j in range(3)):
                raise ValueError(f"IK on {self.label} needs unscaled controls, but "
                                 f"{self.clip.editor._control_path(uid)} is scaled at t={time:g}")
        return pose, frames

    def _effector(self, frames_by_uid: dict[str, Frame]):
        end = self.path[-1]
        if self.tip is not None:
            return self.rig.carried_point(end, self.tip, frames_by_uid)
        tip = self.rig.tip(end, frames_by_uid)
        return tip if tip is not None and (self.rig.nodes[end].length or 0) > 1e-9 else frames_by_uid[end].origin

    def _frames(self, base_frames, pose, rotations: dict[str, tuple]):
        """World frames of the chain's path for the given joint rotation offsets."""
        rig = self.rig
        frames = dict(base_frames)
        parent = rig.parent_container(self.path[0], frames)
        for uid in self.path:
            node = rig.nodes[uid]
            offsets = pose.get(uid, {})
            rotation = rotations.get(uid, offsets.get("rotation", (0.0, 0.0, 0.0)) if uid not in self.joints
                                     else (0.0, 0.0, 0.0))
            factor = offsets.get("scale", (1.0, 1.0, 1.0))
            linear = mm(rot_zyx(add(node.rotation, rotation)),
                        ((factor[0], 0.0, 0.0), (0.0, factor[1], 0.0), (0.0, 0.0, factor[2])))
            frame = parent.compose(linear, add(node.origin, offsets.get("position", (0.0, 0.0, 0.0))))
            frames[uid] = frame
            parent = frame.compose(IDENTITY, scale(node.origin, -1.0)) if node.pivots_children else frame
        return frames

    def _clamp(self, uid, offset):
        bounds = self.limits.get(uid)
        if bounds is None:
            return offset, False
        clamped = tuple(min(max(value, low), high) for value, (low, high) in zip(offset, bounds))
        return clamped, any(abs(a - b) > 1e-9 for a, b in zip(clamped, offset))

    def _offset(self, uid, parent_linear, world_linear, previous):
        rest = self.rig.nodes[uid].rotation
        euler = continuous_euler(mm(transpose(parent_linear), world_linear), add(rest, previous))
        return self._clamp(uid, sub(euler, rest))

    def _parent_linear(self, uid, frames):
        return self.rig.parent_container(uid, frames).linear

    # --- solving one sample
    def _solve_reach(self, time, target, pole, previous, tolerance, bend_toward=None):
        pose, base_frames = self._base(time, self.joints)
        rest_frames = self._frames(base_frames, pose, {})
        points = [rest_frames[uid].origin for uid in self.joints] + [self._effector(rest_frames)]
        lengths = [norm(sub(b, a)) for a, b in zip(points, points[1:])]
        if bend_toward is not None:          # a direction is a pole infinitely far that way
            pole = add(points[0], unit(bend_toward), 1e4 * sum(lengths))
        reachable = norm(sub(target, points[0])) <= sum(lengths) + 1e-6 and \
            (len(lengths) != 2 or norm(sub(target, points[0])) >= abs(lengths[0] - lengths[1]) - 1e-6)
        hinge = None
        if len(points) == 2:
            solved = [points[0], add(points[0], unit(sub(target, points[0])), lengths[0])] \
                if norm(sub(target, points[0])) > 1e-9 else points
        elif len(points) == 3:
            q1, q2, new_normal = two_bone(*points, target, pole, label=self.label)
            solved = [points[0], q1, q2]
            # Two segments bend in one plane: keep each joint's rest hinge axis on the new plane's normal, so
            # a knee or elbow folds about the axis it folds about at rest (and per-axis limits mean it). The
            # solver's normal stays defined when the limb is fully stretched, so the twist never pops there.
            rest_normal = cross(sub(points[1], points[0]), sub(points[2], points[1]))
            if new_normal is not None and norm(rest_normal) > 1e-6 * lengths[0] * lengths[1]:
                hinge = (unit(rest_normal), new_normal)
        else:
            solved = fabrik(points, target, pole, tolerance=tolerance * 0.01)

        rotations, limited, frames = {}, set(), dict(base_frames)
        for i, uid in enumerate(self.joints):
            frames = self._frames(base_frames, pose, rotations)
            current = frames[uid]
            rest_segment = mv(transpose(rest_frames[uid].linear), sub(points[i + 1], points[i]))
            if norm(rest_segment) < 1e-9 or norm(sub(solved[i + 1], current.origin)) < 1e-9:
                rotations[uid] = previous.get(uid, (0.0, 0.0, 0.0))
                continue
            now = unit(mv(current.linear, rest_segment))
            wanted = unit(sub(solved[i + 1], current.origin))
            world = mm(shortest_rotation(now, wanted), current.linear)
            if hinge is not None:
                local_axis = mv(transpose(rest_frames[uid].linear), hinge[0])
                have, want = reject(mv(world, local_axis), wanted), reject(hinge[1], wanted)
                if norm(have) > 1e-9 and norm(want) > 1e-9:
                    world = mm(axis_rotation(wanted, signed_angle(have, want, wanted)), world)
            rotations[uid], hit = self._offset(uid, self._parent_linear(uid, frames), world,
                                               previous.get(uid, (0.0, 0.0, 0.0)))
            if hit:
                limited.add(uid)
        frames = self._frames(base_frames, pose, rotations)
        error = norm(sub(self._effector(frames), target))
        if error > tolerance and reachable and self.limits:
            rotations, error, more = self._refine(base_frames, pose, rotations, target, tolerance, previous)
            limited |= more
        return rotations, error, reachable, limited

    def _refine(self, base_frames, pose, rotations, target, tolerance, previous):
        """Cyclic coordinate descent within the rotation limits, starting from the analytic solution."""
        rotations, limited = dict(rotations), set()
        frames = self._frames(base_frames, pose, rotations)
        error = norm(sub(self._effector(frames), target))
        for _ in range(48):
            for uid in reversed(self.joints):
                frames = self._frames(base_frames, pose, rotations)
                pivot = frames[uid].origin
                to_tip, to_target = sub(self._effector(frames), pivot), sub(target, pivot)
                if norm(to_tip) < 1e-9 or norm(to_target) < 1e-9:
                    continue
                world = mm(shortest_rotation(unit(to_tip), unit(to_target)), frames[uid].linear)
                rotations[uid], hit = self._offset(uid, self._parent_linear(uid, frames), world,
                                                   previous.get(uid, rotations[uid]))
                if hit:
                    limited.add(uid)
            frames = self._frames(base_frames, pose, rotations)
            improved = norm(sub(self._effector(frames), target))
            if improved < tolerance or error - improved < 1e-7:
                error = improved
                break
            error = improved
        return rotations, error, limited

    def _solve_aim(self, time, target, axis, up, up_axis, previous):
        uid = self.path[0]
        pose, base_frames = self._base(time, [uid])
        frames = self._frames(base_frames, pose, {})
        current = frames[uid]
        aimed = mv(current.linear, axis)
        offset = sub(target, current.origin)
        if norm(offset) < 1e-9:
            return {uid: previous.get(uid, (0.0, 0.0, 0.0))}, 0.0, set()
        wanted = unit(offset)
        if up is None:                       # keep the up direction the control has before aiming
            up = mv(current.linear, up_axis)
        world = mm(shortest_rotation(unit(aimed), wanted), current.linear)
        have, want = reject(mv(world, up_axis), wanted), reject(up, wanted)
        if norm(have) > 1e-9 and norm(want) > 1e-9:
            world = mm(axis_rotation(wanted, signed_angle(have, want, wanted)), world)
        rotation, hit = self._offset(uid, self._parent_linear(uid, frames), world, previous.get(uid, (0.0, 0.0, 0.0)))
        final = self._frames(base_frames, pose, {uid: rotation})[uid]
        error = math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(mv(final.linear, axis)), wanted)))))
        return {uid: rotation}, error, ({uid} if hit else set())

    # --- baking
    def _times(self, start, end, fps):
        from .animation import _number, _sample_times
        first, last = _number(start, "start"), _number(end, "end")
        if first < 0 or last > self.clip.duration or last <= first:
            raise ValueError(f"IK interval {first:g}-{last:g}s must lie inside the {self.clip.duration:g}s clip")
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 500:
            raise ValueError("fps must be an integer from 1 to 500")
        return first, last, _sample_times(first, last, fps)

    def _claim(self, rotating, first, last):
        """Rotation keys of the chain inside the interval belong to IK; earlier IK keys on its ends are replaced."""
        owned = self.clip._ik_keys
        for uid in rotating:
            keyframes = self.clip._tracks.get(uid, [])
            inside = [kf for kf in keyframes if kf["channel"] == "rotation" and first - 1e-9 <= kf["time"] <= last + 1e-9]
            foreign = [kf["time"] for kf in inside
                       if kf["uuid"] not in owned or first + 1e-9 < kf["time"] < last - 1e-9]
            if foreign:
                raise ValueError(
                    f"{self.clip.editor._control_path(uid)} already has rotation keys at {foreign} inside "
                    f"{first:g}-{last:g}s of {self.clip.name!r}; IK owns the rotation of chain controls in its "
                    "interval. Remove those keys or solve a different interval")
            for kf in inside:
                keyframes.remove(kf)

    def _write(self, results, rotating):
        from .animation import AnimationTrack
        controls = {item.uuid: item for item in self.clip.editor.controls()}
        for time, rotations in results:
            for uid in rotating:
                track = AnimationTrack(self.clip, controls[uid])
                track.key(time, rotation=tuple(round(value, 6) for value in rotations[uid]), interpolation="linear")
                self.clip._ik_keys.add(self.clip._tracks[uid][-1]["uuid"])

    def _record(self, rotating, first, last):
        dependencies = [(uid, None) for uid in self.rig.ancestors(self.path[0])]
        dependencies += [(uid, channel) for uid in self.path for channel in ("position", "scale")]
        dependencies += [(uid, "rotation") for uid in self.path if uid not in rotating]
        self.clip._ik_solves.append((self.label, dependencies, _fingerprint(self.clip, dependencies),
                                     tuple(rotating), first, last))

    def _report(self, samples, errors, unreachable, limited, tolerance, unit_name, what):
        worst = max(errors) if errors else 0.0
        report = IKReport(self.names, samples, round(worst, 6), unit_name, _intervals(unreachable),
                          tuple(sorted(self.rig.nodes[uid].name for uid in limited)), worst <= tolerance)
        if not report.ok:
            detail = [f"max error {worst:.4g} {unit_name} (tolerance {tolerance:g})"]
            if report.unreachable:
                detail.append(f"target out of reach at {list(report.unreachable)}s")
            if report.limited:
                detail.append(f"limited by {list(report.limited)}")
            warnings.warn(f"IK {what} {self.label} in {self.clip.name!r}: " + "; ".join(detail),
                          UserWarning, stacklevel=3)
        return report

    def reach(self, start: float, end: float, fps: int, *, target, pole=None, bend_toward=None,
              tolerance: float = 0.01) -> IKReport:
        """Bake rotation keys so the chain's tip reaches ``target`` for every sample in [start, end].

        ``target`` and ``pole`` are world points (model units) or functions of time returning one.
        The middle joints (knee, elbow) turn toward ``pole``, or along ``bend_toward``, a world
        direction such as (0, 0, 1) for knees facing +Z; give one or neither. Without both, the rest
        bend is kept, which on real models is often a few degrees off. Two segments solve
        analytically, longer chains with FABRIK. Parents must be animated before calling this.
        Returns an ``IKReport`` and warns when ``tolerance`` is exceeded.
        """
        if not self.joints:
            raise ValueError(f"Chain {self.label} has no segment to move; give an end control or tip=(x, y, z) "
                             "(a rest model-space point carried by the last control)")
        if pole is not None and bend_toward is not None:
            raise ValueError("Give pole (a point) or bend_toward (a direction), not both")
        first, last, times = self._times(start, end, fps)
        self._claim(self.joints, first, last)
        results, errors, unreachable, limited = [], [], [], set()
        previous: dict[str, tuple] = {}
        for index, time in enumerate(times):
            goal = _value_at(target, time, "target")
            hint = None if pole is None else _value_at(pole, time, "pole")
            toward = None if bend_toward is None else _value_at(bend_toward, time, "bend_toward")
            if toward is not None and norm(toward) < 1e-9:
                raise ValueError("bend_toward must be a nonzero direction")
            rotations, error, reachable, hit = self._solve_reach(time, goal, hint, previous, tolerance, toward)
            results.append((time, rotations))
            errors.append(error)
            limited |= hit
            if not reachable:
                unreachable.append((index, time))
            previous = rotations
        self._write(results, self.joints)
        self._record(self.joints, first, last)
        return self._report(len(times), errors, unreachable, limited, tolerance, "model units", "reach")

    def aim(self, start: float, end: float, fps: int, *, target, axis="+y", up=None, up_axis=None,
            tolerance: float = 0.5) -> IKReport:
        """Bake rotation keys so the control's local ``axis`` points at ``target`` in [start, end].

        Works on a single control (``clip.chain("head")``). ``axis`` is '+x'...'-z' or a vector in the
        control's own frame. The roll keeps the local ``up_axis`` (default '+y', or '+z' when aiming
        along y) facing ``up``, a world direction; without ``up`` it faces where it faced before aiming
        (so a head turning far stays level instead of tilting).
        """
        if len(self.path) != 1:
            raise ValueError(f"aim works on one control; use clip.chain({self.names[0]!r}).aim(...)")
        uid = self.path[0]
        aim_axis = _axis(axis, "axis")
        roll_axis = _axis(up_axis or ("+z" if abs(aim_axis[1]) > 0.9 else "+y"), "up_axis")
        if abs(dot(roll_axis, aim_axis)) > 0.999:
            raise ValueError("up_axis must differ from axis")
        first, last, times = self._times(start, end, fps)
        self._claim([uid], first, last)
        results, errors, limited, previous = [], [], set(), {}
        for time in times:
            goal = _value_at(target, time, "target")
            up_dir = None if up is None else unit(_value_at(up, time, "up"))
            rotations, error, hit = self._solve_aim(time, goal, aim_axis, up_dir, roll_axis, previous)
            results.append((time, rotations))
            errors.append(error)
            limited |= hit
            previous = rotations
        self._write(results, [uid])
        self._record([uid], first, last)
        return self._report(len(times), errors, [], limited, tolerance, "degrees", "aim")

    def pin(self, at: float):
        """World point where the chain's tip is at time ``at`` with the clip's current keys.

        Use it as a ``reach`` target to keep a hand or foot planted while the body keeps moving.
        """
        frames = self.rig.fk(pose_from_tracks(self.clip._tracks, float(at)))
        return self._effector(frames)


def _fingerprint(clip: "AnimationClip", dependencies) -> str:
    rows = []
    for uid, channel in dependencies:
        keys = [kf for kf in clip._tracks.get(uid, []) if channel is None or kf["channel"] == channel]
        rows.append([uid, channel, sorted((kf["channel"], kf["time"], json.dumps(kf, sort_keys=True)) for kf in keys)])
    return json.dumps(rows, sort_keys=True)


def check_solves(clip: "AnimationClip") -> None:
    """Fail when a control a chain depends on was keyed after the chain was solved."""
    for label, dependencies, fingerprint, rotating, first, last in clip._ik_solves:
        if _fingerprint(clip, dependencies) == fingerprint:
            continue
        changed = sorted({clip.editor._control_path(uid) for uid, channel in dependencies
                          if _fingerprint(clip, [(uid, channel)]) != _fingerprint_snapshot(fingerprint, uid, channel)})
        raise ValueError(f"IK chain {label} in {clip.name!r} was solved before {changed} were (re)animated; "
                         "animate the controls above a chain first, then call reach()/aim()")


def _fingerprint_snapshot(fingerprint: str, uid: str, channel) -> str:
    for row in json.loads(fingerprint):
        if row[0] == uid and row[1] == channel:
            return json.dumps([row], sort_keys=True)
    return ""


# ----------------------------------------------------------------------------- inspection
EXTENSION_WARNING = 0.998     # reach fraction (about a 7° bend) near which a two-segment chain snaps straight...
EXTENSION_RATE = 90.0         # ...when its inner joint is still bending or straightening faster than this (°/s);
                              # passing slowly through near-full reach is normal
POP_SPEED = 720.0             # a control turning faster than this (degrees per second)...
POP_FACTOR = 5.0              # ...and this many times its median speed is a gross error such as a rotation
                              # flipping; fast but smooth motion (a swinging segment reaches 300-400°/s) is not
# Cuts are measured on velocities over perceptual windows (keys interpolate linearly, so finer samples see
# steps at every key). A cut is a jump in acceleration: the second difference of the windowed velocity,
# |v[i+1] - 2 v[i] + v[i-1]|: a 40° sine swing at 1 Hz gives ~11°/s, fast natural swings of a limb-like
# chain up to ~120°/s, a kink that read as a cut ~180°/s and a dead stop the full speed lost. These are
# review hints calibrated on approved and rejected clips, not hard limits.
CUT_WINDOW = 1 / 30           # seconds per velocity window
CUT_JERK = 150.0              # angular second difference (°/s) that reads as a cut
TIP_JERK = 3.0                # tip second difference, in chain lengths per second, that reads as a jolt


def _rotation_part(m):
    """The rotation of a world linear map (polar decomposition), without the scale a parent may add.

    A scaled ancestor (a breathing chest) makes ``b · aᵀ`` non-orthogonal, and the angle read from
    it turns tiny motions into spurious spins of hundreds of degrees per second."""
    x = m
    for _ in range(8):
        x = tuple(tuple((p + q) / 2 for p, q in zip(row, inv_row))
                  for row, inv_row in zip(x, transpose(inverse(x))))
    return x


def _angular_velocity(a, b, rate) -> tuple[float, float, float]:
    """World angular velocity (°/s) turning orientation ``a`` into ``b`` over one sample at ``rate``."""
    w = mm(_rotation_part(b), transpose(_rotation_part(a)))
    axis = (w[2][1] - w[1][2], w[0][2] - w[2][0], w[1][0] - w[0][1])   # 2 sin(angle) · axis
    size = norm(axis)
    angle = math.atan2(size / 2, (w[0][0] + w[1][1] + w[2][2] - 1) / 2)   # stable for small angles
    if angle < 1e-9 or size < 1e-12:
        return (0.0, 0.0, 0.0)
    return scale(axis, math.degrees(angle) * rate / size)


def inspect_chain(editor, clip: str, start: str, end: str | None = None, *, rate: int = 120) -> dict:
    """Sample a saved clip ``rate`` times per second and describe a chain the way a reviewer reads it.

    Sampling between keys shows what the viewer interpolates, so use a rate above the keys' fps.
    Per sample: the bend at each inner joint (0 = straight), the unit direction each inner joint bends
    toward (away from the line through its neighbours), the reach used (base-to-tip distance over the
    chain's length), and the tip's position and velocity in world space. Per control: the fastest
    rotation and the largest change of angular velocity. ``warnings`` flags cuts (a control's angular
    velocity changing abruptly), tip jolts (the tip suddenly stopping or starting), snaps (near-full
    reach while the inner joint still moves fast) and pops (a control turning far faster than its usual
    pace). Values come from the same forward kinematics as the viewer.
    """
    from .animation import _number
    animations = {item.get("name"): item for item in editor._data.get("animations", []) if isinstance(item, dict)}
    if clip not in animations:
        raise KeyError(f"Unknown animation {clip!r}; the bbmodel has: {sorted(animations)}")
    if isinstance(rate, bool) or not isinstance(rate, int) or not 1 <= rate <= 1000:
        raise ValueError("rate must be an integer from 1 to 1000")
    animation = animations[clip]
    duration = _number(animation.get("length"), "animation length")
    tracks = {uid: animator.get("keyframes", []) for uid, animator in animation.get("animators", {}).items()
              if uid != "effects" and isinstance(animator, dict)}
    rig, path = editor.rig, editor._chain_path(start, end)
    names = [rig.nodes[uid].name for uid in path]
    end_node = rig.nodes[path[-1]]
    has_tip = end_node.kind == "bone" and (end_node.length or 0) > 1e-9

    def points(frames):
        found = [frames[uid].origin for uid in path]
        return found + [rig.tip(path[-1], frames)] if has_tip else found

    rest = points(rig.rest)
    length = sum(norm(sub(b, a)) for a, b in zip(rest, rest[1:]))
    count = max(2, round(duration * rate))
    step = duration / count
    sampled = [rig.fk(pose_from_tracks(tracks, duration * i / count)) for i in range(count + 1)]
    chains = [points(frames) for frames in sampled]
    frames_out = []
    for index, joints in enumerate(chains):
        bends = [round(math.degrees(math.acos(max(-1.0, min(1.0, dot(unit(sub(b, a)), unit(sub(c, b))))))), 2)
                 for a, b, c in zip(joints, joints[1:], joints[2:])]
        directions = {}
        for name, (a, b, c) in zip(names[1:], zip(joints, joints[1:], joints[2:])):
            line = sub(c, a)
            offset = reject(sub(b, a), unit(line)) if norm(line) > 1e-9 else (0.0, 0.0, 0.0)
            directions[name] = [round(v, 3) for v in unit(offset)] if norm(offset) > 1e-6 else None
        velocity = scale(sub(chains[index + 1][-1], joints[-1]), 1 / step) if index < count else None
        frames_out.append({"time": round(index * step, 4), "bends": dict(zip(names[1:], bends)),
                           "bend_directions": directions,
                           "reach": round(norm(sub(joints[-1], joints[0])) / length, 4) if length > 1e-9 else 0.0,
                           "tip": [round(v, 4) for v in joints[-1]],
                           "tip_velocity": [round(v, 3) for v in velocity] if velocity else None})

    warnings_out = []
    snapping = []
    for i in range(count):
        row, following = frames_out[i], frames_out[i + 1]
        moving = any(abs(following["bends"][n] - row["bends"][n]) / step > EXTENSION_RATE for n in row["bends"])
        if row["reach"] > EXTENSION_WARNING and moving:
            snapping.append((i, row["time"]))
    if snapping and len(path) >= 2:
        warnings_out.append(f"{names[0]} -> {names[-1]} snaps near full reach at {list(_intervals(snapping))}s "
                            f"(above {EXTENSION_WARNING:.1%} while bending faster than {EXTENSION_RATE:g}°/s); "
                            "keep the target a little closer there")
    windows = max(4, round(duration / CUT_WINDOW))
    span = duration / windows
    coarse = sampled if windows == count else [rig.fk(pose_from_tracks(tracks, duration * i / windows))
                                               for i in range(windows + 1)]

    def jerks(values):
        """(time, size) of the second difference of windowed velocities, at each inner window boundary."""
        return [(round((i + 1) * span, 4), norm(add(sub(values[i + 1], scale(values[i], 2.0)), values[i - 1])))
                for i in range(1, len(values) - 1)]

    tips = [points(frames)[-1] for frames in coarse]
    tip_jerks = jerks([scale(sub(b, a), 1 / span / max(length, 1e-9)) for a, b in zip(tips, tips[1:])])
    jolts = [(t, j) for t, j in tip_jerks if j > TIP_JERK]
    if jolts:
        warnings_out.append(f"{names[-1]} tip jolts at {[t for t, _ in jolts]}s (its velocity jumps by up to "
                            f"{max(j for _, j in jolts):.1f} chain lengths/s against the trend around it): it "
                            "stops or starts abruptly")
    joint_speed = {}
    for uid, name in zip(path, names):
        omegas = [_angular_velocity(sampled[i][uid].linear, sampled[i + 1][uid].linear, 1 / step)
                  for i in range(count)]
        speeds = [(norm(w), round((i + 0.5) * step, 4)) for i, w in enumerate(omegas)]
        values = sorted(v for v, _ in speeds)
        median = values[len(values) // 2]
        fastest, at = max(speeds)
        window_omegas = [_angular_velocity(coarse[i][uid].linear, coarse[i + 1][uid].linear, 1 / span)
                         for i in range(windows)]
        found = jerks(window_omegas)
        sharp_at, sharpest = max(found, key=lambda item: item[1]) if found else (0.0, 0.0)
        joint_speed[name] = {"max_degrees_per_second": round(fastest, 2), "at": at,
                             "median_degrees_per_second": round(median, 2),
                             "max_jerk_degrees_per_second": round(sharpest, 1), "jerk_at": sharp_at}
        cuts = [(t, j) for t, j in found if j > CUT_JERK]
        if cuts:
            warnings_out.append(f"{name} cuts at {[t for t, _ in cuts]}s (its angular velocity jumps by up to "
                                f"{max(j for _, j in cuts):.0f}°/s against the trend around it): ease the motion "
                                "there")
        pops = [t for v, t in speeds if v > POP_SPEED and v > POP_FACTOR * max(median, 1e-6)]
        if pops:
            warnings_out.append(f"{name} pops at {pops}s (up to {fastest:.0f}°/s against a usual {median:.0f}°/s)")
    return {"clip": clip, "chain": names, "rate": rate, "length": round(length, 4), "frames": frames_out,
            "joint_speed": joint_speed, "warnings": warnings_out}
