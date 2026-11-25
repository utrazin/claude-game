---
name: forge-3d-visual-conformance
description: "Give artistic feedback on a clay render of a NoctAssetForge3D model against the user's request or reference: silhouette, proportions, posture, composition. Use when the user asks for a review or an opinion on how the model looks."
---

# Forge 3D Visual Conformance

Evaluate model shape, silhouette, and proportions against the request or reference using a two-step workflow:

### Step 1: Instant Technical Pre-flight (Numbers & Integrity)
Before spending time rendering images, verify quantitative data and structure in ~20ms:
```bash
py -3.12 -m Tools.forge inspect projects/<name> --asset <id> --validate --summary
```
Verify:
- Bounding box and dimensions match expectations (e.g. height, width).
- Pivot points and hierarchy are correctly placed (e.g. feet on Y=0).
- Zero non-manifold or degenerate geometry errors.

### Step 2: Visual Clay Review (Aesthetics & Silhouette)
Render the untextured (clay) model to judge readability, posture, and silhouette:
```bash
py -3.12 -m Tools.forge preview projects/<name> --asset <id>
py -3.12 -m Tools.forge preview projects/<name> --asset <id> --no-reference --view right
```
Open the images in `renders/` and compare them with the request and any reference. Judge shape, proportions, silhouette, posture and readability as the requested object; colors and textures belong to `forge-3d-texture`.

Give concrete feedback part by part ("torso too wide -> narrow it", "ears misaligned -> ..."), or confirm the model matches and why. Apply changes only if the user asks.
