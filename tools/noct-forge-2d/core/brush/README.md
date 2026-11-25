# `@core/brush`

Vector 2D engine for procedural game assets: parametric geometry, extensible brushes, boolean operations, deformations, modeling operations and declarative rendering.

## Where to look

| Need | Read |
| :--- | :--- |
| Signatures and types, all packages | [`core/docs/api/`](../docs/api/). Generated; do not edit. `brush-*.md` for this package, `core.md` for `@core`, `pixel.md` for `@core/pixel`. |
| When and how to use a module | [`docs/`](docs/), guides 01 to 08 |
| Project production policy | [`.agents/skills/noct-asset-forge/SKILL.md`](../../.agents/skills/noct-asset-forge/SKILL.md) |

The generated API reference is the only place where signatures are written. The guides explain choices and trade-offs and do not repeat them.

## Public surface

Import only from `@core`, `@core/brush` and `@core/pixel`. Files under `internal/` are not public, and projects must not import them.

Regenerate the API reference after changing exported symbols:

```bash
npm run docs:api
```
