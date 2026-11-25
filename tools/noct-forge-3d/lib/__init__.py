"""Utilities for generating Blockbench models as code.

The root holds the ergonomic authoring surface for recipes
(`ModelBuilder`, sections, profiles, frames, rigs, animation editing).
Mesh-construction cores (`loft`, `sweep`, `segment`, `revolve`,
`segment_sections`, `sweep_sections`), `MeshFace` and `box_surface_contacts`
are internal machinery: import them from `lib.procedural`, `lib.spatial` or
`lib.geometry_types`, and prefer the `ModelBuilder.add_*` constructors.
"""

from .model_builder import ChainSegment, ModelBuilder
from .geometry_types import CapSpec, MeshDraft, MeshGeometry, Placement, PrimitiveHandle
from .spatial import (Frame, SpatialFrame, SurfaceContact, ModelOrientation,
                      linear_falloff, smooth_falloff)
from .procedural import (Profile, Section, SegmentSection, PathSection, Path3D, RelativePath, Curve)
from .armature import ArmatureHandle, BindingReport, JointBlend
from .animation import AnimationEditor, AnimationControl
from .ik import IKChain, IKReport
from .motion import periodic, periodic_curve, quintic, smooth_periodic, spring_follow

__all__ = [
    "ModelBuilder", "ChainSegment", "CapSpec", "MeshDraft", "MeshGeometry",
    "Placement", "PrimitiveHandle", "Frame", "SpatialFrame", "SurfaceContact", "ModelOrientation",
    "Profile", "Section", "SegmentSection", "PathSection", "Path3D", "RelativePath", "Curve",
    "linear_falloff", "smooth_falloff", "ArmatureHandle", "BindingReport", "JointBlend",
    "AnimationEditor", "AnimationControl", "IKChain", "IKReport",
    "quintic", "periodic", "periodic_curve", "spring_follow", "smooth_periodic",
]
