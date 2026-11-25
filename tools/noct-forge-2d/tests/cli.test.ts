import assert from 'node:assert/strict';
import { execSync } from 'node:child_process';
import { existsSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

console.log('🧪 Checking agent commands (new-project, new-asset, list, inspect, export --mockup)...\n');

const project = `zz-cli-test-${Date.now()}`;
const projectDir = resolve('projects', project);

interface Result {
  code: number;
  stdout: string;
  stderr: string;
}

// Runs an npm script. Never throws: callers check the exit code.
function run(command: string): Result {
  try {
    const stdout = execSync(command, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] });
    return { code: 0, stdout, stderr: '' };
  } catch (err: any) {
    return { code: err.status ?? 1, stdout: String(err.stdout ?? ''), stderr: String(err.stderr ?? '') };
  }
}

const badgeSource = `import { defineAsset } from '@core';
import { Polygon } from '@core/brush';

export default defineAsset({
  width: 32,
  height: 32,
  scale: 1,
  render({ ctx, preview }) {
    Polygon.circle(12, { cx: 16, cy: 16 }).draw(ctx, { fill: preview ? '#00ff00' : '#ff0000' });
  },
});
`;

try {
  // 1. new-project creates the template and refuses to overwrite it.
  const created = run(`npm run --silent new-project -- ${project}`);
  assert.equal(created.code, 0, `new-project failed: ${created.stderr}`);
  assert.ok(existsSync(resolve(projectDir, 'source', '_theme.ts')), 'new-project must copy the theme');
  assert.ok(!existsSync(resolve(projectDir, 'PROJECT.md')), 'PROJECT.md is optional and must not be created by default');
  assert.ok(!existsSync(resolve(projectDir, 'STYLE.md')), 'STYLE.md is optional and must not be created by default');
  const withOptional = run(`npm run --silent new-project -- ${project}-opt --style --doc`);
  assert.equal(withOptional.code, 0, `new-project --style --doc failed: ${withOptional.stderr}`);
  const optionalDir = resolve('projects', `${project}-opt`);
  try {
    assert.ok(readFileSync(resolve(optionalDir, 'PROJECT.md'), 'utf8').includes(`${project}-opt`), 'PROJECT.md must carry the name');
    assert.ok(readFileSync(resolve(optionalDir, 'STYLE.md'), 'utf8').includes(`${project}-opt`), 'STYLE.md must carry the name');
  } finally {
    rmSync(optionalDir, { recursive: true, force: true });
  }
  const again = run(`npm run --silent new-project -- ${project}`);
  assert.notEqual(again.code, 0, 'new-project must refuse an existing project');

  // 2. new-asset with space-separated values, and refusal to overwrite.
  const asset = run(`npm run --silent new-asset -- ${project} hud/button --engine brush --size 96x64`);
  assert.equal(asset.code, 0, `new-asset failed: ${asset.stderr}`);
  const assetFile = readFileSync(resolve(projectDir, 'source', 'hud', 'button.ts'), 'utf8');
  assert.ok(assetFile.includes('width: 96') && assetFile.includes('height: 64'), 'new-asset must honor --size');
  assert.notEqual(
    run(`npm run --silent new-asset -- ${project} hud/button --engine brush`).code,
    0,
    'new-asset must refuse an existing file',
  );

  // 2b. A freshly created project must type-check: the template theme may not depend on missing files.
  const checked = run(`npm run --silent check -- ${project}`);
  assert.equal(checked.code, 0, `a new project must pass check: ${checked.stdout}`);

  // 3. list --json reports the source.
  const listed = JSON.parse(run(`npm run --silent list -- ${project} --json`).stdout);
  assert.deepEqual(listed.projects[0].sources, ['hud/button']);

  // 4. Mockup isolation: an official export is not changed by a mockup export.
  writeFileSync(resolve(projectDir, 'source', 'badge.ts'), badgeSource, 'utf8');
  const official = run(`npm run --silent export -- ${project} badge --json`);
  assert.equal(official.code, 0, `official export failed: ${official.stderr}`);
  const officialPath = resolve(projectDir, 'assets', 'badge.png');
  const before = readFileSync(officialPath);

  const mockup = run(`npm run --silent export -- ${project} badge --mockup --json`);
  assert.equal(mockup.code, 0, `mockup export failed: ${mockup.stderr}`);
  const mockupSummary = JSON.parse(mockup.stdout);
  assert.equal(mockupSummary.mode, 'mockup');
  assert.equal(mockupSummary.outputDir, `projects/${project}/preview-assets`);
  assert.ok(existsSync(resolve(projectDir, 'preview-assets', 'badge.png')), 'mockup must write to preview-assets/');
  assert.ok(readFileSync(officialPath).equals(before), 'mockup export must not change assets/badge.png');

  // 5. The old --preview flag is rejected, with a pointer to --mockup.
  const oldFlag = run(`npm run --silent export -- ${project} badge --preview`);
  assert.notEqual(oldFlag.code, 0, '--preview must be rejected');

  // 6. inspect returns numbers for an official output.
  const inspected = JSON.parse(run(`npm run --silent inspect -- projects/${project}/assets/badge.png --json`).stdout);
  assert.equal(inspected.width, 32);
  assert.equal(inspected.height, 32);
  assert.ok(inspected.distinctOpaqueColors > 0, 'inspect must count opaque colors');

  // 7. capture screenshots a sandbox page, accepting a relative projects/ path.
  const sandbox = run(`npm run --silent new-sandbox -- ${project}`);
  assert.equal(sandbox.code, 0, `new-sandbox failed: ${sandbox.stderr}`);
  assert.ok(existsSync(resolve(projectDir, 'sandboxes', 'main', 'open.bat')), 'new-sandbox must create sandboxes/main/open.bat');
  assert.ok(readFileSync(resolve(projectDir, 'sandboxes', 'main', 'open.bat'), 'utf8').startsWith('@echo off\r\n'));
  const shot = run(`npm run --silent capture -- projects/${project}/sandboxes/main/ --at 200 --out projects/${project}/temp/shot.png --json`);
  assert.equal(shot.code, 0, `capture failed: ${shot.stderr}`);
  assert.ok(existsSync(resolve(projectDir, 'temp', 'shot.png')), 'capture must write the PNG');

  // 8. Named animations reach the atlas; an out-of-range index fails before any PNG is written.
  writeFileSync(resolve(projectDir, 'source', 'strip.ts'), `import { defineAsset } from '@core';
import { Polygon } from '@core/brush';

export default defineAsset({
  width: 32,
  height: 32,
  scale: 1,
  frames: 2,
  fps: 4,
  animations: { idle: [0, 1] },
  render({ ctx, frameIndex }) {
    Polygon.circle(8 + frameIndex * 2, { cx: 16, cy: 16 }).draw(ctx, { fill: '#2244ff' });
  },
});
`, 'utf8');
  const strip = run(`npm run --silent export -- ${project} strip --json`);
  assert.equal(strip.code, 0, `strip export failed: ${strip.stderr}`);
  const atlas = JSON.parse(readFileSync(resolve(projectDir, 'assets', 'strip.json'), 'utf8'));
  assert.deepEqual(atlas.meta.animations, { idle: [0, 1] }, 'atlas must carry the named animations');
  assert.equal(atlas.meta.frameCount, 2);

  writeFileSync(resolve(projectDir, 'source', 'badstrip.ts'), `import { defineAsset } from '@core';

export default defineAsset({
  width: 32,
  height: 32,
  scale: 1,
  frames: 2,
  animations: { idle: [0, 5] },
  render({ ctx }) {},
});
`, 'utf8');
  const bad = run(`npm run --silent export -- ${project} badstrip`);
  assert.notEqual(bad.code, 0, 'an out-of-range animation index must fail the export');
  assert.ok(!existsSync(resolve(projectDir, 'assets', 'badstrip.png')), 'a failed animation must not leave a PNG behind');

  // 9. --help on a subcommand prints its usage and exits 0.
  const help = run('npm run --silent new-asset -- --help');
  assert.equal(help.code, 0, '--help must exit 0');
  assert.ok(help.stdout.includes('--frames'), '--help must describe the options');

  console.log('✔ new-project, new-asset, list, export --mockup, --preview rejection and inspect behave as documented.\n');
} finally {
  rmSync(projectDir, { recursive: true, force: true });
}
