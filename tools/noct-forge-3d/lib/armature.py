"""Declarative native Blockbench armatures and vertex-weight helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JointBlend:
    """Bound a smooth transition to three named rings around one child bone joint."""
    bone: str
    ring: str
    before: str
    after: str
    parent: str | None = None
    curve: str = "smooth"

    def __post_init__(self):
        for field in ("bone", "ring", "before", "after"):
            if not str(getattr(self, field)):
                raise ValueError(f"JointBlend {field} cannot be empty")
        if self.parent is not None and not str(self.parent):
            raise ValueError("JointBlend parent cannot be empty")
        if self.curve not in {"linear", "smooth"}:
            raise ValueError("JointBlend curve must be 'linear' or 'smooth'")

    def as_dict(self):
        return {"bone": self.bone, "ring": self.ring, "before": self.before,
                "after": self.after, "parent": self.parent, "curve": self.curve}


@dataclass(frozen=True)
class ArmatureHandle:
    """Compact façade over one armature owned by a ModelBuilder."""
    builder: Any
    name: str

    def add_bone(self, name, *, between, parent=None, connected=True, width=None, tags=None):
        self.builder._add_armature_bone(name, armature=self.name, between=between, parent=parent,
                              connected=connected, width=width, tags=tags)
        return self

    def add_chain(self, name, *, joints, names, parent=None, connected=True, width=None, tags=None):
        joints, names = tuple(joints), tuple(names)
        if len(joints) != len(names) + 1:
            raise ValueError("Armature chain needs one more joint than bone names")
        current_parent = parent
        created = []
        for index, (bone_name, start, end) in enumerate(zip(names, joints, joints[1:])):
            self.add_bone(bone_name, between=(start, end), parent=current_parent,
                          connected=(connected if index == 0 else True),
                          width=width, tags=tags)
            created.append(bone_name)
            current_parent = bone_name
        if not isinstance(name, str) or not name.strip():
            raise ValueError("add_chain needs a chain name (bind uses it: rig.bind(mesh, chain=name))")
        key = name
        if key in self.builder._armature_chains:
            raise ValueError(f"Duplicate armature chain {key!r}")
        self.builder._armature_chains[key] = tuple(created)
        return tuple(created)

    def register_chain(self, name, bones):
        """Name existing bones (root first) so ``bind(chain=name)`` can use them."""
        bones = tuple(str(bone) for bone in bones)
        for bone in bones:
            owner = self.builder._armature_bones.get(bone)
            if owner is None or owner.armature != self.name:
                raise KeyError(f"Unknown bone {bone!r} in armature {self.name!r}")
        if name in self.builder._armature_chains:
            raise ValueError(f"Duplicate armature chain {name!r}")
        self.builder._armature_chains[name] = bones
        return bones

    def bind(self, mesh, *, mode=None, bone=None, chain=None, blend="tight",
             curve="smooth", joints=None, weights=None, joint_owner="child"):
        """Bind through one explicit, intention-oriented façade.

        ``bone=`` infers rigid binding. Multi-bone bindings require
        ``mode='hard'`` or ``mode='smooth'`` and a named/explicit ``chain``.
        ``mode='explicit'`` accepts a complete per-vertex ``weights`` map.
        """
        supplied_mode=None if mode is None else str(mode)
        if weights is not None:
            if supplied_mode not in {None,"explicit"} or bone is not None or chain is not None or joints:
                raise ValueError("Explicit weights cannot be combined with bone, chain, or joint options")
            return self.builder._bind_armature_explicit(self.name,mesh,weights)
        if supplied_mode=="explicit":
            raise ValueError("mode='explicit' requires weights")
        if bone is not None:
            if supplied_mode not in {None,"rigid"}:
                raise ValueError("bone= implies mode='rigid'")
            if chain is not None or joints:
                raise ValueError("Rigid binding accepts one bone and no chain or joints")
            if blend!="tight" or curve!="smooth" or joint_owner!="child":
                raise ValueError("Rigid binding does not accept blend, curve, or joint_owner options")
            return self.builder._bind_armature_rigid(self.name,mesh,bone)
        if supplied_mode=="rigid":
            raise ValueError("mode='rigid' requires bone=")
        if supplied_mode not in {"hard","smooth"}:
            raise ValueError("Multi-bone binding requires mode='hard' or mode='smooth'")
        bones=self.builder._resolve_armature_chain(self.name,chain)
        if supplied_mode=="hard":
            if joints:
                raise ValueError("Hard binding does not accept smooth joint overrides")
            if blend!="tight" or curve!="smooth":
                raise ValueError("Hard binding does not accept blend or curve options")
            boundaries=self.builder._infer_armature_joint_blends(
                self.name,mesh,bones,blend="tight",curve="linear",support=False)
            return self.builder._bind_armature_hard(self.name,mesh,bones=bones,
                                                     joints=boundaries,joint_owner=joint_owner)
        if joint_owner!="child":
            raise ValueError("joint_owner applies only to hard binding")
        resolved_joints=(tuple(joints) if joints is not None else
                         self.builder._infer_armature_joint_blends(
                             self.name,mesh,bones,blend=blend,curve=curve))
        if not resolved_joints:
            raise ValueError("Smooth binding requires at least one joint blend")
        return self.builder._auto_weight_armature(self.name,mesh,bones=bones,joints=resolved_joints)

    def mirror(self, source, new_name=None, axis="X", *, target=None):
        """Mirror a bone subtree (and chains inside it); same rules as ``builder.mirror``."""
        bone = self.builder._armature_bones.get(source)
        if bone is None or bone.armature != self.name:
            raise KeyError(f"Unknown bone {source!r} in armature {self.name!r}")
        self.builder.mirror(source, new_name or target, axis=axis, kind="bone")   # target= is the old name of new_name=
        return self


@dataclass(frozen=True)
class BindingReport:
    mesh: str
    vertices: int
    bones: tuple[str, ...]
    average_influences: float
    maximum_influences: int
    overrides_applied: int
    ambiguities: int = 0

    def report(self) -> str:
        return (f"{self.mesh}: {self.vertices} vertices, {len(self.bones)} bones, "
                f"{self.average_influences:.2f} avg influences, max {self.maximum_influences}, "
                f"{self.overrides_applied} overrides")
