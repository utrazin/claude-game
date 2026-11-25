# `edit_diff` output reference

Read this only for the ready-made code `edit_diff --full` prints.

## Summary lines
| Mark | Meaning |
|---|---|
| `~ kind name` + indented rows | Exists in both, differs. Rows: `field old -> new`; for meshes `vertex V (in faces ..): old -> new`, `+/- vertex`, `+/- face`, `face F: old -> new`; for clips `path.channel t=..: old -> new`. Long lists are cut unless `--full`. |
| `+ kind name` | New in Blockbench (a mesh shows counts and bounds; `--full` every vertex and face). |
| `- kind name` | The recipe builds it, the file lacks it. For a clip after regenerating the model this only means "not generated yet": run `Tools.animation_export`. |
| `? ...` | Note, never a failure: `locator X: the builder has no locators`, `also changed later by the recipe at L..`, `is gone but the recipe still mentions it at L..`, `may have been renamed to ..`, `new and sits under the armature: bind it`, cube anchors. |
| `! ...` | Not turned into code: the builder rejects the geometry as edited (concave or degenerate face, an edge on three faces, a polygon mesh in a box model), no single recipe statement to replace, mode mismatch, missing recipe, or a document that is not a readable model. Nothing is corrected for you: the report still shows what changed, so rebuild it in the recipe as close as the builder allows. |

## Code (printed with `--full` or `--emit`, as `# --- model|animation snippet: <title>`)
- `L54-64 [head]` + `# replace generate_model.py L54-64 (it creates: head)`: the statement(s) that created the part. If it is a loop, comprehension, helper or `mirror` call, the block recreates every part that statement makes. Several spans: put the code at the first, delete the others.
- `new [a, b]` + `# add after generate_model.py L189 ...`: parts new in Blockbench; paste after that line, before the return or export.
- `# delete ...`: everything that statement built was removed. `# create scripts/generate_animation.py with:` is a whole new file for clips no recipe declares.
- `# NOTE: this statement also creates bone x, bind y`: not part of the block; keep or recreate them.
- `# NOTE: this model is in box mode`: switch the recipe to `modeling_mode='free'` for polygon meshes.
- Blocks are already indented and use the recipe's own variable name.

## What the code is
| Part | Call |
|---|---|
| group | `add_group` / `add_transform_group` (a folder with a pivot or rotation becomes a transform group) |
| polygon mesh | a `MeshDraft` with every vertex, face (and face group), anchor and ring as saved, added with `builder.add_mesh(..., origin=, rotation=)` (`forge-3d-model/references/custom-mesh.md`) |
| native cube | `add_cube(from_=, to_=, origin=, rotation=, ...)`; a cube built with `add_box` and referenced as `"name:top"` loses those anchors, so edit the `add_box` call instead |
| socket | `add_socket(name, owner, at=, forward=, up=)` |
| clip | a `CLIP_<NAME>` table plus a replay loop over `clip.bone(...).key(...)` |

## Comparison
Tolerance 0.001 units. UVs, textures, visibility, lock and color are ignored. Only clips the recipe declares are compared against the file; other clips are `+`.
