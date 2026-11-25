# Rule Set: Hytale Model Specification

Geometric constraints and proportions inspired by the Hytale aesthetic.

## Technical Limitations
- **Node Limit:** Maximum 255 total nodes (groups + bones + cubes + meshes).
- **Geometry:** Integer cube dimensions for primary volumes. Cardinal quads only (`+X`, `-X`, `+Y`, `-Y`, `+Z`, `-Z`).
- **Layers & Armor:** Outer attachments (collars, belts, armor plates) require minimum 0.2 unit clearance offset or positive `inflate`.
- **Shading:** Cube property `shading: standard`.
- **Animation Target:** 60 FPS standard keyframe grid.
