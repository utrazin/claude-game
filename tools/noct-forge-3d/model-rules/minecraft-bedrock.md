# Rule Set: Minecraft Bedrock Specification

Strict constraints for Minecraft Bedrock entity models.

## Hard Constraints
- **Geometry Type:** Strict Box only (`add_box`, `add_cube`). Polygon meshes forbidden.
- **Rotation:** Single-axis rotation per bone (X, Y, or Z). Multi-axis bone rotations fail in Bedrock client.
- **Pivots:** Functional joint centers matching rotation axis.
- **Texture / UV:**
  - Default resolution: 16px or 32px base scale.
  - `require_integer_uvs=True`. Fractional UVs prohibited.
  - Mirrored UVs allowed only via explicit bone symmetry flags.
