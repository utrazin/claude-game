"""Semantic, transactional authoring of native Blockbench animations."""
from __future__ import annotations

import warnings
import copy
import json
import math
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class AnimationControl:
    kind: str
    name: str
    path: str
    parent: str | None
    uuid: str
    armature: str | None = None


def _number(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _sample_times(first: float, last: float, fps: int) -> list[float]:
    """Evenly spaced times from ``first`` to ``last`` at about ``fps`` per second, both ends included.

    The last time is ``last`` itself: computed as ``first + span * count / count`` it can land a
    rounding error past the end (0.8 at 120 fps gives 0.8000000000000002) and leave the clip."""
    count = max(1, round((last - first) * fps))
    return [first + (last - first) * index / count for index in range(count)] + [last]


def _vector(value, label: str) -> tuple[float, float, float]:
    try:
        values = tuple(value)
    except TypeError as exc:
        raise ValueError(f"{label} must contain three numbers") from exc
    if len(values) != 3:
        raise ValueError(f"{label} must contain three numbers")
    return tuple(_number(item, label) for item in values)


def _catalog(data: dict) -> tuple[AnimationControl, ...]:
    groups = {item.get("uuid"): item for item in data.get("groups", []) if isinstance(item, dict)}
    elements = {item.get("uuid"): item for item in data.get("elements", []) if isinstance(item, dict)}
    controls: list[AnimationControl] = []

    def visit(node, path=(), armature=None, parent=None):
        if isinstance(node, str):
            return
        if not isinstance(node, dict):
            return
        uid = node.get("uuid")
        item = groups.get(uid) or elements.get(uid) or node
        name = item.get("name")
        kind = item.get("type") if uid in elements else "group"
        next_path = (*path, name) if name else path
        next_armature = name if kind == "armature" else armature
        if kind == "group":
            group_kind = "group" if item.get("model_as_code_role") != "folder" else "folder"
            controls.append(AnimationControl(group_kind, name, "/".join(next_path), parent, uid))
        elif kind == "armature_bone":
            controls.append(AnimationControl("bone", name, "/".join(next_path), parent, uid,
                                             next_armature))
        next_parent = "/".join(next_path) if kind in {"group", "armature_bone", "armature"} else parent
        for child in node.get("children", []):
            visit(child, next_path, next_armature, next_parent)

    for root in data.get("outliner", []):
        visit(root)
    ids = [control.uuid for control in controls]
    if len(ids) != len(set(ids)):
        raise ValueError("Outliner contains duplicate animation control UUIDs")
    return tuple(controls)


def _stable_uuid(*parts) -> str:
    """Ids derived from the clip, control and time, so the same recipe saves the same file every time."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "noctforge:" + ":".join(str(p) for p in parts)))


_INTERPOLATIONS = {"linear": "linear", "constant": "step", "catmullrom": "catmullrom",
                   "bezier": "bezier"}   # recipe name -> bbmodel name


class AnimationTrack:
    def __init__(self, clip: "AnimationClip", control: AnimationControl):
        self.clip = clip
        self.control = control

    def key(self, time: float, *, position=None, rotation=None, scale=None,
            interpolation: str = "linear", bezier_left_time=None, bezier_left_value=None,
            bezier_right_time=None, bezier_right_value=None) -> "AnimationTrack":
        moment = _number(time, "keyframe time")
        if moment < 0 or moment > self.clip.duration:
            raise ValueError("Keyframe time must be inside animation duration")
        if interpolation not in _INTERPOLATIONS:
            raise ValueError("interpolation must be 'linear', 'constant' or 'catmullrom'")
        channels = {"position": position, "rotation": rotation, "scale": scale}
        if all(value is None for value in channels.values()):
            raise ValueError("Keyframe requires position, rotation, or scale")
        track = self.clip._tracks.setdefault(self.control.uuid, [])
        pending = []
        for channel, value in channels.items():
            if value is None:
                continue
            xyz = _vector(value, channel)
            if any(kf["channel"] == channel and kf["time"] == moment for kf in track):
                raise ValueError(f"Duplicate {channel} keyframe at {moment:g}s for {self.control.path}")
            keyframe = {"uuid": _stable_uuid("keyframe", self.clip.name, self.control.uuid, channel, moment), "time": moment,
                        "channel": channel,
                        "interpolation": _INTERPOLATIONS[interpolation],
                        "data_points": [dict(zip("xyz", xyz))]}
            handles = {"bezier_left_time": bezier_left_time, "bezier_left_value": bezier_left_value,
                       "bezier_right_time": bezier_right_time, "bezier_right_value": bezier_right_value}
            if interpolation == "bezier":
                handles["bezier_left_time"] = bezier_left_time if bezier_left_time is not None else (-0.1, -0.1, -0.1)
                handles["bezier_left_value"] = bezier_left_value if bezier_left_value is not None else (0, 0, 0)
                handles["bezier_right_time"] = bezier_right_time if bezier_right_time is not None else (0.1, 0.1, 0.1)
                handles["bezier_right_value"] = bezier_right_value if bezier_right_value is not None else (0, 0, 0)
            elif any(value is not None for value in handles.values()):
                raise ValueError("Bezier handles require interpolation='bezier'")
            for name, value in handles.items():
                if value is not None:
                    keyframe[name] = list(_vector(value, name))
            pending.append(keyframe)
        track.extend(pending)
        return self

    def sample(self, channel: str, start: float, end: float, fps: int,
               function: Callable[[float], tuple[float, float, float]], *,
               interpolation: str = "linear") -> "AnimationTrack":
        if channel not in {"position", "rotation", "scale"}:
            raise ValueError("channel must be position, rotation, or scale")
        first, last = _number(start, "start"), _number(end, "end")
        if first < 0 or last > self.clip.duration or last <= first:
            raise ValueError("Sample interval must be inside animation duration")
        if isinstance(fps, bool) or not isinstance(fps, int) or not 1 <= fps <= 500:
            raise ValueError("fps must be an integer from 1 to 500")
        samples = [(time, _vector(function(time), channel)) for time in _sample_times(first, last, fps)]
        existing = self.clip._tracks.get(self.control.uuid, [])
        if any(kf["channel"] == channel and any(kf["time"] == t for t, _ in samples)
               for kf in existing):
            raise ValueError("Sampled keyframes collide with existing keyframes")
        for time, vector in samples:
            self.key(time, **{channel: vector}, interpolation=interpolation)
        return self


def _differs(a: float, b: float, period: float | None) -> bool:
    delta = abs(a - b)
    if period:
        delta = min(delta % period, period - delta % period)
    return delta > 1e-6


class AnimationClip:
    def __init__(self, editor: "AnimationEditor", name: str, duration: float, loop):
        self.editor = editor
        self.name = name
        self.duration = duration
        self.loop = loop
        self._tracks: dict[str, list[dict]] = {}
        self._ik_keys: set[str] = set()
        self._ik_solves: list[tuple] = []

    def group(self, name: str) -> AnimationTrack:
        return AnimationTrack(self, self.editor._resolve("group", name))

    def bone(self, name: str, *, armature: str | None = None) -> AnimationTrack:
        return AnimationTrack(self, self.editor._resolve("bone", name, armature))

    def chain(self, start: str, end: str | None = None, *, tip=None, limits=None) -> "IKChain":
        """IK chain of controls (groups or bones) from ``start`` down to its descendant ``end``.

        The tip is the end bone's tip, or the end group's pivot, or ``tip`` (a rest model-space point
        carried by the end control). ``limits`` maps control names to {'x'|'y'|'z': (min, max)}
        rotation-offset degrees. Call ``.reach(...)`` or, on one control, ``.aim(...)``.
        """
        from .ik import IKChain
        return IKChain(self, self.editor._chain_path(start, end), tip=tip, limits=limits)

    def world_point(self, control: str, time: float, point=None) -> tuple[float, float, float]:
        """World position at ``time`` (current keys of this clip) of a point carried by ``control``.

        ``point`` is a rest model-space point; omitted it is the control's pivot, ``"tip"`` a bone's tip.
        Use it inside IK targets to follow another control.
        """
        from .kinematics import pose_from_tracks
        return self.editor._point(control, self.editor.rig.fk(pose_from_tracks(self._tracks, float(time))), point)

    def _loop_mismatches(self) -> list[str]:
        """A looping clip should end on the pose it starts with; describe channels that do not."""
        if self.loop is not True:
            return []
        controls = {item.uuid: item for item in self.editor.controls()}
        found = []
        for uid, keyframes in self._tracks.items():
            for channel in ("position", "rotation", "scale"):
                frames = sorted((kf for kf in keyframes if kf["channel"] == channel), key=lambda kf: kf["time"])
                if len(frames) < 2 or frames[0]["time"] != 0 or abs(frames[-1]["time"] - self.duration) > 1e-9:
                    continue
                first, last = frames[0]["data_points"][0], frames[-1]["data_points"][0]
                spin = 360.0 if channel == "rotation" else None   # a full turn is the same pose
                if any(_differs(first[axis], last[axis], spin) for axis in "xyz"):
                    found.append(f"Animation {self.name!r} loops but {controls[uid].path} {channel} starts at "
                                 f"{tuple(first[a] for a in 'xyz')} and ends at {tuple(last[a] for a in 'xyz')}; "
                                 "the loop will jump")
        return found

    def _json(self, existing_uuid: str | None = None) -> dict:
        if not self._tracks:
            raise ValueError(f"Animation {self.name!r} has no keyframes")
        controls = {item.uuid: item for item in self.editor.controls()}
        animators = {}
        for uid, keyframes in self._tracks.items():
            control = controls[uid]
            animators[uid] = {"name": control.name,
                              "type": "bone" if control.kind == "group" else "armature_bone",
                              "keyframes": sorted(keyframes, key=lambda kf: (kf["time"], kf["channel"]))}
        return {"uuid": existing_uuid or _stable_uuid("animation", self.name), "name": self.name,
                "loop": "hold" if self.loop == "hold" else ("loop" if self.loop else "once"), "length": self.duration,
                "snapping": 20, "animators": animators}


class AnimationEditor:
    """Transactional authoring of native Blockbench animation clips on an existing BBModel.

    Open with ``from_bbmodel()``, declare clips with ``animation()``, delete
    with ``remove_animation()`` and persist with ``save()``. Clips the recipe
    does not declare are preserved; only declared clips are replaced.
    """
    def __init__(self, path: Path, source: bytes, data: dict):
        self.path = path
        self._source = source
        self._data = data
        self._controls = tuple(item for item in _catalog(data) if item.kind != "folder")
        self._control_ids = {item.uuid for item in self._controls}
        self._clips: dict[str, AnimationClip] = {}
        self._removed: list[str] = []
        self._rig = None

    @classmethod
    def from_bbmodel(cls, path: str | Path) -> "AnimationEditor":
        target = Path(path)
        source = target.read_bytes()
        data = json.loads(source)
        if not isinstance(data, dict) or not isinstance(data.get("outliner", []), list):
            raise ValueError("Animation editor requires a BBModel object with an outliner list")
        return cls(target, source, data)

    def controls(self) -> tuple[AnimationControl, ...]:
        return self._controls

    @property
    def group_names(self) -> tuple[str, ...]:
        """Names of all transform groups available in the model."""
        return tuple(c.name for c in self._controls if c.kind == "group")

    @property
    def bone_names(self) -> tuple[str, ...]:
        """Names of all armature bones available in the model."""
        return tuple(c.name for c in self._controls if c.kind == "bone")

    @property
    def control_names(self) -> tuple[str, ...]:
        """Names of all animatable controls in the model."""
        return tuple(c.name for c in self._controls)

    def _resolve(self, kind: str, name: str, armature: str | None = None) -> AnimationControl:
        matches = [item for item in self._controls if item.kind == kind and
                   (item.name == name or item.path == name) and
                   (armature is None or item.armature == armature)]
        if not matches:
            raise KeyError(f"Unknown {kind} control {name!r}")
        if len(matches) > 1:
            paths = ", ".join(item.path for item in matches)
            raise ValueError(f"Ambiguous {kind} control {name!r}: {paths}; use its full path")
        return matches[0]

    def _resolve_any(self, name: str) -> AnimationControl:
        matches = [item for item in self._controls if item.name == name or item.path == name]
        if not matches:
            raise KeyError(f"Unknown control {name!r}; see `forge animation --controls`")
        if len(matches) > 1:
            raise ValueError(f"Ambiguous control {name!r}: {', '.join(item.path for item in matches)}; "
                             "use its full path")
        return matches[0]

    def _chain_path(self, start: str, end: str | None = None) -> list[str]:
        """Control uuids from ``start`` down to its descendant ``end`` (inclusive)."""
        first = self._resolve_any(start)
        last = self._resolve_any(end) if end is not None else first
        rig = self.rig
        if first.uuid != last.uuid and first.uuid not in rig.ancestors(last.uuid):
            below = [self._control_path(uid) for uid in rig.descendants(first.uuid) if uid in self._control_ids][:24]
            raise ValueError(f"{last.path} is not below {first.path}; controls below it: {below}")
        path = [last.uuid]
        while path[-1] != first.uuid:
            parent = rig.nodes[path[-1]].parent
            if parent not in self._control_ids:
                raise ValueError(f"Chain {first.path} -> {last.path} passes through {rig.nodes[parent].name!r}, "
                                 "which is not an animatable control; start the chain below it")
            path.append(parent)
        return list(reversed(path))

    def inspect_chain(self, clip: str, start: str, end: str | None = None, *, rate: int = 120) -> dict:
        """Numbers of a saved clip for a chain, sampled ``rate`` times per second: bends, reach, bend
        direction, tip position and velocity, and per-control speed, with warnings for cuts, tip jolts,
        snaps near full reach and pops. See ``lib.ik.inspect_chain``."""
        from .ik import inspect_chain
        return inspect_chain(self, clip, start, end, rate=rate)

    def _control_path(self, uid: str) -> str:
        for item in self._controls:
            if item.uuid == uid:
                return item.path
        return self.rig.nodes[uid].name

    @property
    def rig(self):
        """Forward-kinematics view of the outliner (``lib.kinematics.Rig``), as the viewer evaluates it."""
        if self._rig is None:
            from .kinematics import Rig
            self._rig = Rig.from_document(self._data)
        return self._rig

    def _point(self, control: str, frames, point=None):
        uid = self._resolve_any(control).uuid
        if point is None:
            return frames[uid].origin
        if isinstance(point, str):
            if point != "tip" or self.rig.nodes[uid].kind != "bone":
                raise ValueError("point must be a rest model-space (x, y, z) or 'tip' (armature bones only)")
            return self.rig.tip(uid, frames)
        return self.rig.carried_point(uid, _vector(point, "point"), frames)

    def rest_point(self, control: str, point=None) -> tuple[float, float, float]:
        """Rest-pose world position of a control's pivot (default), of a bone's ``"tip"``, or of a
        model-space ``point`` it carries. IK targets are often written as rest point + offset."""
        return self._point(control, self.rig.rest, point)

    def animation(self, name: str, *, duration: float, loop: bool | str = False) -> AnimationClip:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Animation name cannot be empty")
        if name in self._clips:
            raise ValueError(f"Animation {name!r} already declared in this recipe")
        length = _number(duration, "animation duration")
        if length <= 0:
            raise ValueError("Animation duration must be positive")
        if not (isinstance(loop, bool) or loop == "hold"):
            raise TypeError("loop must be True, False or \"hold\" (play once, then keep the last pose)")
        clip = AnimationClip(self, name, length, loop)
        self._clips[name] = clip
        return clip

    def remove_animation(self, name: str) -> None:
        """Delete a clip that exists in the bbmodel (a recipe otherwise leaves clips it does not declare)."""
        if name in self._clips:
            raise ValueError(f"Animation {name!r} is declared in this recipe; it cannot also be removed")
        if not any(isinstance(item, dict) and item.get("name") == name for item in self._data.get("animations", [])):
            raise KeyError(f"Unknown animation {name!r}; the bbmodel has: "
                           f"{[item.get('name') for item in self._data.get('animations', [])]}")
        self._removed.append(name)

    def build_document(self) -> dict:
        """Return the bbmodel with the declared clips merged in, without writing it."""
        if not self._clips and not self._removed:
            raise ValueError("Declare at least one animation (or remove one) before saving")
        from .ik import check_solves
        for clip in self._clips.values():
            check_solves(clip)
        document = copy.deepcopy(self._data)
        animations = document.setdefault("animations", [])
        if not isinstance(animations, list):
            raise ValueError("bbmodel animations must be an array")
        existing = {}
        for index, item in enumerate(animations):
            name = item.get("name") if isinstance(item, dict) else None
            if not name or name in existing:
                raise ValueError("Existing animations must have unique nonempty names")
            existing[name] = index
        for name, clip in self._clips.items():
            old = animations[existing[name]] if name in existing else None
            value = clip._json(old.get("uuid") if old else None)
            if old is None:
                animations.append(value)
            else:
                animations[existing[name]] = value
        if self._removed:
            document["animations"] = [item for item in animations if item.get("name") not in self._removed]
        for clip in self._clips.values():
            for message in clip._loop_mismatches():
                warnings.warn(message, UserWarning, stacklevel=3)
        validate_animations(document)
        return document

    def save(self) -> Path:
        if self.path.read_bytes() != self._source:
            raise RuntimeError("bbmodel changed since it was opened; reload before saving animations")
        document = self.build_document()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".bbmodel",
                                             prefix=f".{self.path.stem}.", dir=self.path.parent,
                                             delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(document, handle, indent=2, ensure_ascii=False)
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        self._data = document
        self._source = self.path.read_bytes()
        self._clips.clear()
        self._removed.clear()
        return self.path


def validate_animations(data: dict) -> dict:
    controls = {item.uuid: item for item in _catalog(data)}
    known_nodes = controls.keys() | {
        item.get("uuid") for item in data.get("elements", []) if isinstance(item, dict)
    }
    animations = data.get("animations", [])
    if not isinstance(animations, list):
        raise ValueError("animations must be an array")
    names = set()
    for animation in animations:
        if not isinstance(animation, dict) or not isinstance(animation.get("name"), str) or not animation["name"]:
            raise ValueError("Animation must have a nonempty name")
        if animation["name"] in names:
            raise ValueError(f"Duplicate animation name {animation['name']!r}")
        names.add(animation["name"])
        duration = _number(animation.get("length"), "animation length")
        if duration <= 0 or animation.get("loop", "once") not in {"once", "loop", "hold"}:
            raise ValueError(f"Invalid duration or loop mode in {animation['name']!r}")
        animators = animation.get("animators", {})
        if not isinstance(animators, dict):
            raise ValueError("animators must be an object")
        for uid, animator in animators.items():
            if uid == "effects":
                continue
            if uid not in known_nodes:
                raise ValueError(f"Animation {animation['name']!r} targets missing control {uid}")
            if uid not in controls:
                # Retain native clips animating element types outside this authoring API.
                continue
            control = controls[uid]
            expected = "armature_bone" if control.kind == "bone" else "bone"
            if not isinstance(animator, dict) or animator.get("type", expected) != expected:
                raise ValueError(f"Animation {animation['name']!r} has wrong animator type for {control.path}")
            keyframes = animator.get("keyframes", [])
            if not isinstance(keyframes, list):
                raise ValueError("Animator keyframes must be an array")
            seen = set()
            for keyframe in keyframes:
                if not isinstance(keyframe, dict):
                    raise ValueError("Keyframe must be an object")
                channel = keyframe.get("channel")
                time = _number(keyframe.get("time"), "keyframe time")
                if channel not in {"position", "rotation", "scale"} or not 0 <= time <= duration:
                    raise ValueError(f"Invalid keyframe in animation {animation['name']!r}")
                if keyframe.get("interpolation", "linear") not in {"linear", "step", "catmullrom", "bezier"}:
                    raise ValueError("Unsupported keyframe interpolation")
                key = (channel, time)
                if key in seen:
                    raise ValueError(f"Duplicate {channel} keyframe at {time:g}s for {control.path}")
                seen.add(key)
                points = keyframe.get("data_points", [])
                if not isinstance(points, list) or not points:
                    raise ValueError("Keyframe needs at least one data point")
                for point in points:
                    if not isinstance(point, dict) or not all(axis in point for axis in "xyz"):
                        raise ValueError("Keyframe data point requires x, y, z")
                    for axis in "xyz":
                        value = point[axis]
                        if isinstance(value, (int, float)):
                            _number(value, f"keyframe {axis}")
                        elif not isinstance(value, str) or not value.strip():
                            raise ValueError(f"Invalid keyframe {axis} value")
                for handle in ("bezier_left_time", "bezier_left_value", "bezier_right_time", "bezier_right_value"):
                    if handle in keyframe:
                        _vector(keyframe[handle], f"{handle} in {animation['name']!r}")
    return {"animations": len(animations),
            "controls": sum(item.kind != "folder" for item in controls.values())}
