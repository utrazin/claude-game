# NoctAssetForge

A programmatic environment for creating visual game assets (UI, icons, tiles, textures and sprites) with code. Assets are written in TypeScript on two engines: `@core/brush` (vector geometry, boolean operations, stroke renderers, procedural textures) and `@core/pixel` (pixel art on an integer grid). Outputs are rasterized to PNG or JPEG through headless Chromium.

## Install

Requires Node.js 20 or newer.

```bash
npm install
npx playwright install chromium
npm run doctor
npm test
```

To open the viewer: on Windows, run `dev.bat`; on macOS and Linux, run `sh dev.sh`. Any system can run `npm run view` and then open `http://localhost:5173`. Each sandbox has its own launcher, `preview.bat` or `preview.sh`, which uses the same server.

## Start with a coding agent

Open this folder in a coding agent and ask:

> Read `.agents/skills/noct-setup/SKILL.md` and prepare this environment.

When the setup passes, ask for the asset you want. Before writing asset code, the agent reads `.agents/skills/noct-asset-forge/SKILL.md`, which holds the production rules, and `.agents/skills/noct-review/SKILL.md`, which covers checking the output.

## Commands

| Task | Command |
| :--- | :--- |
| Create a project | `npm run new-project -- <project> [--style] [--doc]` |
| Create an asset | `npm run new-asset -- <project> <subpath> --engine brush\|pixel [--size WxH] [--frames N] [--fps N]` |
| Create a sandbox | `npm run new-sandbox -- <project>` |
| Check types | `npm run check -- <project>` |
| Export | `npm run export -- <project> [subpath] [options]` |
| List | `npm run list -- [project] [--json]` |
| Measure a PNG | `npm run inspect -- <file.png> [--json]` |
| Capture a page | `npm run capture -- projects/<project>/sandboxes/main/ [--at <ms>]` |
| Open the viewer | `npm run view` |

Projects live in `projects/`. Each project has `source/` (asset code), `assets/` (outputs), and optionally `STYLE.md`, `PROJECT.md` and `preview/` (a sandbox).

## Documentation for agents

The `.agents/skills/` folder holds the instructions for coding agents: `noct-setup`, `noct-asset-forge` and `noct-review`. The API reference is generated in `core/docs/api/`, and the guides in `core/brush/docs/` explain when to use each module.

## License

This software is distributed under the terms in [LICENSE](LICENSE). Third-party components and their licenses are listed in [THIRD_PARTY.md](THIRD_PARTY.md). Build information is in [BUILD_INFO.json](BUILD_INFO.json), and file hashes are in [checksums.sha256](checksums.sha256).
