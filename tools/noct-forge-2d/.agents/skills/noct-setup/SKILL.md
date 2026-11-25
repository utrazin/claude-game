---
name: noct-setup
description: Prepare a NoctProceduralAssetForge checkout to run tests, the viewer and asset exports. Use when the environment is new, when `npm run doctor` fails, or after cloning or copying the repository.
---

# NoctAssetForge setup

This skill only prepares the environment and checks that it works. For producing assets, use the `noct-asset-forge` skill.

## 1. Check the environment

Run:

```bash
npm run doctor
```

It checks the Node.js version, the installed dependencies, the headless Chromium used by the exporter, and `tsconfig.json`. Each failure prints the command that fixes it. Go to the next step only when it prints `Environment is ready.`

## 2. Install

Requires Node.js 20 or newer.

```bash
npm install
npx playwright install chromium
```

`npm install` uses the committed `package-lock.json`. Do not run `npm update` as part of setup, because it changes the locked versions.

## 3. Verify

Run the checks in this order. Each one must pass before moving on.

```bash
npm test
npx tsc --noEmit -p tsconfig.json
```

- `npm test` runs the core tests, the public boundary check, the documentation snippet check, and the agent command checks. The command checks create a temporary project under `projects/`, export it through Chromium, and remove it afterwards. A passing run therefore confirms that the exporter and the capture command render.
- The `tsc` command reports errors from every project in the repository. Errors in `core/`, `tests/`, `scripts/` and `tools/` mean the setup is broken. Errors in `projects/` are not caused by setup and are not blocking.

## 4. Open the viewer (optional)

```bash
npm run view
```

Then open `http://localhost:5173`. On Windows, `dev.bat` starts the same server and opens the browser; on macOS and Linux, `sh dev.sh` does the same. The `noct-review` skill explains what to look at.

## Troubleshooting

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `doctor` says Chromium is missing | `npx playwright install chromium` was not run, or the browser cache is elsewhere | Run the install command. To use a different browser cache, set `PLAYWRIGHT_BROWSERS_PATH` before installing. |
| `npm run export` fails before writing a file | Chromium is missing | Run `npm run doctor` first, then the install command. The exporter does not need port 5173: it reuses a running viewer or starts its own server. |
| `npm test` fails in `docs.test.ts` | A guide has a fenced `ts` block that is too long or does not compile | Fix the block. Do not add `docs:allow-long` to hide it. |
| `npm run docs:api` changes files in `core/docs/api/` after setup | The API changed in source, and the generated reference was not updated | Commit the regenerated files. They are generated and must not be edited by hand. |

## Rules for this skill

- Do not install packages outside `package.json`. If a package is needed, add it to the file and reinstall.
- Do not edit `package-lock.json` by hand.
- Do not change files in `projects/` while setting up. Setup only reads them.
