# Independent BBModel stages

Recipes are authoring/regeneration instructions; the current BBModel is the serialized
working artifact (native JSON) shared by UV, painting, animation and delivery, parsed and emitted entirely in Python without requiring the Blockbench application. Manual BBModel edits
are valid inputs. Changes to recipes or outputs never trigger hash/version invalidation.

| Stage | Required data | Writes |
|---|---|---|
| model_export | explicitly requested model recipe | BBModel (resets UVs, texture links and clips) |
| uv_packer | BBModel geometry, embedded packing options and rules, explicit flags, or the asset's optional `generate_uv.py` | BBModel UVs |
| texture_export | BBModel with existing explicit UVs, paint recipe | PNG, optional BBModel texture registration |
| animation_export | BBModel controls, animation recipe | only declared BBModel clips |
| asset_status | existing artifacts | nothing |

UV options and UV rules are stored in BBModel packing metadata. Sidecar option files are not read.
An asset that needs a custom UV plan has `scripts/<asset>/generate_uv.py`: `forge uv` and
`asset_build --stages uv` run it (it reads the current BBModel through `UVBuilder`); without
it they pack with the saved options. Regenerating geometry drops the saved rules, so the
recipe is where a custom plan lives.
No stage runs a missing prerequisite. Existence and structural checks do not establish
that an output matches a newer recipe. Rerun only the stages the user requests.

`asset_build --stages uv,texture` is an optional explicit shortcut. `model` must be
selected and authorized to execute geometry; it never runs because a model is missing
or invalid. A literal `ASSET_BUILD_GEOMETRY = "manual"` in generate_model.py skips
geometry in this shortcut. Explicit model_export still runs the recipe.

An agent must avoid the shortcut when the conversation indicates manual BBModel
edits, unless the user has chosen to reconcile the recipe or mark geometry manual.
Inspecting edits for reconciliation is an explicit operation, never an automatic build.

UV, active texture registration and animation all write the same BBModel and must run
serially. Concurrent-write protections guard against lost edits, not artifact versions.
Unsigned PNGs are supported; registration validates UVs and dimensions only.

UV packing currently accepts free and hytale_character BBModels; unsupported model
formats fail explicitly without conversion or regeneration. Animation discovers
controls independently of that format restriction and without procedural metadata.
