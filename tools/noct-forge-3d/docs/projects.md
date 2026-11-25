# Projects, assets and recipes

Initialize: `py -3.12 -m Tools.forge project init projects/characters --asset hero`.
Add: `py -3.12 -m Tools.forge asset init projects/characters --asset sword --mode box`.
Both create saved deterministic recipes and directories, never execute geometry.
Initialization skips existing files; --force explicitly replaces recipes only.

```
projects/characters/
  project.json
  theme.py           (optional: the project's visual tokens)
  STYLE.md           (optional: its art direction in words)
  references/
  scripts/hero/generate_model.py
  scripts/hero/generate_texture.py
  scripts/hero/generate_animation.py
  assets/hero/model.bbmodel
  assets/hero/texture.png
```

project.json has `schema: 1` (file schema, not stage version), project `id`, `name`
and an `assets` object indexed by stable asset IDs. Each asset declares `name`,
`model` (project-relative BBModel path), `scripts` (project-relative recipe directory),
`variants` (named records containing project-relative PNG `path`, optional `recipe`)
and `default_variant`. A manifest registers sources, never infers them from exports.
All registered paths remain inside the selected project; models live under assets/.
`assets/` holds only registered sources and requested products: keep intermediate copies, backups and
staging files of a recipe outside it (for example in the project's `.cache/`), and remove them when done.
Optional: `texture_filter` (`nearest` pixel art, `linear` smooth: the render mode every paint
operation follows), `render` (overrides of the mode's density, padding and anti-aliasing) and
`twin_of` (a twin asset: a copy of another asset's model in another render mode, painted with that
asset's recipes; `forge asset twin PROJECT --asset SOURCE --id TWIN` creates it and `--sync`
refreshes its model). See `.agents/skills/forge-3d-texture/references/render-modes.md`.

## Delegation

Select explicitly with `Tools.forge model projects/characters --asset hero`, or
`Tools.model_export projects/characters#hero`. Individual Tools CLIs also accept the
registered asset directory or exact registered BBModel path. An ambiguous project
fails instead of choosing the first asset. Every project carries `project.json`;
directories without one are rejected — create them with
`Tools.forge project init` instead.

Saved recipes use `Tools.recipe_context.recipe_paths(__file__)` for model, texture,
asset and project paths. The CLI supplies the same context through environment
variables; no hard-coded relative depth or duplicated viewer is required. External
projects run their recipes through the CLI, which supplies repository imports.

A project may declare its visual tokens once for every asset: `theme.py` (`THEME = define_theme(...)`: palette,
grains and motifs, brushes, patterns, line styles, paint layers, looks) and `STYLE.md` (art direction and what
the tokens cannot express). Recipes read it with `recipe_paths(__file__).theme()`; `py -3.12 -m Tools.forge theme
PROJECT` checks it, `--init` writes both templates. See the texture skill's themes reference.

## Delegation

An orchestrator can pass a project path, asset ID, requested stage and relevant
constraints to a subagent. The subagent starts from forge-3d-orchestrator and reads
the selected stage skill and this manifest. Different assets have different paths;
stages writing the same BBModel must execute serially. A repository maintenance
request can inspect shared Tools/lib code; asset work stays in the selected project.

Project/asset init and variant registration hold a nonblocking OS lock
for their read/modify/write transaction. Another registration fails clearly and can
be retried. The ignored `.forge-project.lock` file is not build state: the OS releases
the actual lock when its process exits. Duplicate writable texture paths across
registered assets and source paths under recipe directories are rejected.
