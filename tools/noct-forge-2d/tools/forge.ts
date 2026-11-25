#!/usr/bin/env node
/**
 * NoctAssetForge - agent-facing commands for projects, assets and checks.
 *
 *   npm run new-project -- <project>
 *   npm run new-asset -- <project> <subpath> [--engine brush|pixel] [--size 128x128]
 *   npm run new-sandbox -- <project>
 *   npm run list -- [project] [--json]
 *   npm run check -- <project> [--json]
 *   npm run inspect -- <file.png> [--json]
 *
 * Commands that create files refuse to overwrite anything. Use --json (with
 * `npm run --silent`) to get output that can be parsed.
 */

import { execFileSync } from 'node:child_process';
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { extname, join, relative, resolve, sep } from 'node:path';
import { inflateSync } from 'node:zlib';
import { chromium } from 'playwright';
import { ensureForgeServer } from './forge-server';
import pc from 'picocolors';

const ROOT = resolve(process.cwd());
const PROJECTS = resolve(ROOT, 'projects');
const TEMPLATES = resolve(ROOT, 'templates');
const PROJECT_NAME_RE = /^[a-z0-9][a-z0-9_-]*$/;
const SUBPATH_RE = /^[a-zA-Z0-9][a-zA-Z0-9_/-]*$/;

type Json = Record<string, unknown>;

function fail(message: string, hint?: string): never {
  console.error(pc.red(`Error: ${message}`));
  if (hint) console.error(pc.gray(hint));
  process.exit(1);
}

const VALUE_FLAGS = ['engine', 'size', 'frames', 'fps', 'at', 'out', 'viewport'];

function parseFlags(argv: string[]): { positionals: string[]; flags: Record<string, string | true> } {
  const positionals: string[] = [];
  const flags: Record<string, string | true> = {};
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (!arg.startsWith('--')) {
      positionals.push(arg);
      continue;
    }
    const [key, inline] = arg.slice(2).split(/=(.*)/s);
    if (inline !== undefined) {
      flags[key] = inline;
    } else if (VALUE_FLAGS.includes(key)) {
      const next = argv[i + 1];
      if (next === undefined || next.startsWith('--')) fail(`--${key} needs a value, for example --${key}=<value>.`);
      flags[key] = next;
      i++;
    } else {
      flags[key] = true;
    }
  }
  return { positionals, flags };
}

function requireProject(name: string | undefined): string {
  if (!name) fail('a project name is required.');
  const dir = resolve(PROJECTS, name);
  if (!existsSync(dir) || !statSync(dir).isDirectory()) {
    const available = existsSync(PROJECTS)
      ? readdirSync(PROJECTS).filter(n => statSync(join(PROJECTS, n)).isDirectory())
      : [];
    fail(`project "${name}" does not exist.`, available.length ? `Available: ${available.join(', ')}` : undefined);
  }
  return dir;
}

function printJson(value: Json): void {
  process.stdout.write(JSON.stringify(value, null, 2) + '\n');
}

// ---------------------------------------------------------------------------
// new-project
// ---------------------------------------------------------------------------

function newProject(positionals: string[], flags: Record<string, string | true>): void {
  const name = positionals[0];
  if (!name || !PROJECT_NAME_RE.test(name)) {
    fail('project names use lowercase letters, digits, "-" and "_", and must start with a letter or digit.');
  }
  const target = resolve(PROJECTS, name);
  if (existsSync(target)) fail(`project "${name}" already exists. Nothing was changed.`);

  // Only the theme is required. STYLE.md and PROJECT.md are optional and added on request.
  cpSync(resolve(TEMPLATES, 'project'), target, { recursive: true, errorOnExist: true, force: false });
  mkdirSync(resolve(target, 'assets'), { recursive: true });

  const optional: string[] = [];
  if (flags['style']) optional.push('STYLE.md');
  if (flags['doc']) optional.push('PROJECT.md');
  for (const file of optional) {
    const content = readFileSync(resolve(TEMPLATES, 'optional', file), 'utf8').replace('[Project Name]', name);
    writeFileSync(resolve(target, file), content, 'utf8');
  }

  console.log(pc.green(`Created projects/${name}/`));
  console.log('Next steps:');
  console.log(`  1. Edit projects/${name}/source/_theme.ts (add projects/${name}/STYLE.md with --style if the style is defined first)`);
  console.log(`  2. npm run new-asset -- ${name} <subpath> --engine brush|pixel`);
}

// ---------------------------------------------------------------------------
// new-asset
// ---------------------------------------------------------------------------

function parseSize(value: string | true | undefined): { width: number; height: number } {
  const raw = value === undefined || value === true ? '128x128' : value;
  const match = /^(\d+)x(\d+)$/.exec(raw);
  if (!match) fail(`--size must look like 128x128, got "${raw}".`);
  return { width: Number(match[1]), height: Number(match[2]) };
}

function assetSource(engine: 'brush' | 'pixel', width: number, height: number, frames: number, fps: number): string {
  // Animation lines only appear when the asset has more than one frame.
  const animated = frames > 1;
  const animLines = animated ? `  frames: ${frames},\n  fps: ${fps},\n` : '';
  const renderArgs = animated ? '{ ctx, frameIndex }' : '{ ctx }';
  if (engine === 'pixel') {
    return `import { defineAsset } from '@core';
import { PixelCanvas } from '@core/pixel';

export default defineAsset({
  width: ${width},
  height: ${height},
  scale: 1,
${animLines}  antialiasing: 'none',
  render(${renderArgs}) {
    const pc = new PixelCanvas(${width}, ${height});
    // Draw on the integer grid, then commit to the canvas.
    pc.render(ctx);
  },
});
`;
  }
  return `import { defineAsset } from '@core';

export default defineAsset({
  width: ${width},
  height: ${height},
  scale: 2,
${animLines}  render(${renderArgs}) {
    // Build the geometry first, then draw it with palette tokens.
  },
});
`;
}

const ASSET_SCALE: Record<'brush' | 'pixel', number> = { brush: 2, pixel: 1 };

function newAsset(positionals: string[], flags: Record<string, string | true>): void {
  const [projectName, subpath] = positionals;
  const projectDir = requireProject(projectName);
  if (!subpath || !SUBPATH_RE.test(subpath)) {
    fail('asset subpath must use letters, digits, "/", "-" and "_", for example hud/button.');
  }
  const engine = (flags['engine'] ?? 'brush') as string;
  if (engine !== 'brush' && engine !== 'pixel') fail('--engine must be "brush" or "pixel".');
  const { width, height } = parseSize(flags['size']);
  const frames = flags['frames'] !== undefined ? Number(flags['frames']) : 1;
  if (!Number.isInteger(frames) || frames < 1) fail('--frames must be a whole number, 1 or more.');
  const fps = flags['fps'] !== undefined ? Number(flags['fps']) : 6;
  if (!Number.isFinite(fps) || fps <= 0) fail('--fps must be a positive number.');

  const file = resolve(projectDir, 'source', `${subpath}.ts`);
  if (existsSync(file)) fail(`${relative(ROOT, file)} already exists. Nothing was changed.`);
  if (!existsSync(resolve(projectDir, 'source', '_theme.ts'))) {
    fail(`projects/${projectName}/source/_theme.ts is missing.`, 'Create the project with npm run new-project, or restore _theme.ts.');
  }

  mkdirSync(resolve(file, '..'), { recursive: true });
  writeFileSync(file, assetSource(engine, width, height, frames, fps), 'utf8');
  const scale = ASSET_SCALE[engine];
  const perFrame = frames > 1 ? ` per frame, ${frames} frames in a strip` : '';
  console.log(pc.green(`Created ${relative(ROOT, file).split(sep).join('/')}`));
  console.log(`Logical size ${width}x${height}. The export is ${width * scale}x${height * scale}${perFrame} (scale ${scale}, set in the file).`);
  console.log(`Export it with: npm run export -- ${projectName} ${subpath}`);
}

// ---------------------------------------------------------------------------
// new-sandbox
// ---------------------------------------------------------------------------

function newSandbox(positionals: string[]): void {
  const projectName = positionals[0], name = positionals[1] || 'main';
  const projectDir = requireProject(projectName);
  if (!PROJECT_NAME_RE.test(name)) fail('Invalid sandbox name');
  const target = resolve(projectDir, 'sandboxes', name);
  if (existsSync(target)) fail(`Sandbox already exists: ${name}`);
  cpSync(resolve(TEMPLATES, 'sandbox'), target, { recursive: true, errorOnExist: true, force: false });
  writeFileSync(resolve(target, 'open.bat'), `@echo off\r\ncd /d "%~dp0..\\..\\..\\.."\r\nnpx tsx tools/open-viewer.ts /projects/${projectName}/sandboxes/${name}/\r\n`);
  writeFileSync(resolve(target, 'open.sh'), `#!/bin/sh\ncd "$(dirname "$0")/../../../.." || exit 1\nexec npx tsx tools/open-viewer.ts /projects/${projectName}/sandboxes/${name}/\n`);
  console.log(`Created projects/${projectName}/sandboxes/${name}/`);
}

// ---------------------------------------------------------------------------
// list
// ---------------------------------------------------------------------------

function listSources(sourceDir: string): string[] {
  const out: string[] = [];
  if (!existsSync(sourceDir)) return out;
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (['.ts', '.js'].includes(extname(entry.name)) && !entry.name.endsWith('.d.ts')
        && !entry.name.startsWith('_') && !entry.name.startsWith('.') && !entry.name.includes('.test.')) {
        out.push(relative(sourceDir, full).split(sep).join('/').replace(/\.(ts|js)$/, ''));
      }
    }
  };
  walk(sourceDir);
  return out.sort();
}

function listOutputs(dir: string): string[] {
  if (!existsSync(dir)) return [];
  const out: string[] = [];
  const walk = (current: string) => {
    for (const entry of readdirSync(current, { withFileTypes: true })) {
      const full = join(current, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (['.png', '.jpg', '.jpeg', '.json'].includes(extname(entry.name).toLowerCase())) {
        out.push(relative(dir, full).split(sep).join('/'));
      }
    }
  };
  walk(dir);
  return out.sort();
}

function list(positionals: string[], flags: Record<string, string | true>): void {
  const asJson = Boolean(flags['json']);
  const names = positionals[0]
    ? [positionals[0]]
    : (existsSync(PROJECTS) ? readdirSync(PROJECTS).filter(n => statSync(join(PROJECTS, n)).isDirectory()) : []);
  if (positionals[0]) requireProject(positionals[0]);

  const projects = names.map(name => {
    const dir = resolve(PROJECTS, name);
    return {
      project: name,
      sources: listSources(resolve(dir, 'source')),
      assets: listOutputs(resolve(dir, 'assets')),
      mockups: listOutputs(resolve(dir, 'preview-assets')),
      sandbox: existsSync(resolve(dir, 'preview', 'index.html')),
      config: existsSync(resolve(dir, 'forge.config.json')),
    };
  });

  if (asJson) {
    printJson({ projects });
    return;
  }
  for (const p of projects) {
    console.log(pc.bold(p.project));
    console.log(`  sources (${p.sources.length}):  ${p.sources.join(', ') || '-'}`);
    console.log(`  assets (${p.assets.length}):   ${p.assets.join(', ') || '-'}`);
    console.log(`  mockups (${p.mockups.length}): ${p.mockups.join(', ') || '-'}`);
    console.log(`  sandbox: ${p.sandbox ? 'yes' : 'no'}   config: ${p.config ? 'yes' : 'no'}`);
  }
}

// ---------------------------------------------------------------------------
// check
// ---------------------------------------------------------------------------

function check(positionals: string[], flags: Record<string, string | true>): void {
  const projectName = positionals[0];
  requireProject(projectName);
  const asJson = Boolean(flags['json']);
  const tsc = resolve(ROOT, 'node_modules', 'typescript', 'bin', 'tsc');

  let output = '';
  try {
    output = execFileSync(process.execPath, [tsc, '--noEmit', '-p', 'tsconfig.json'], {
      cwd: ROOT,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (err: any) {
    output = String(err.stdout ?? '') + String(err.stderr ?? '');
  }

  const errors = output.split(/\r?\n/).filter(line => /error TS\d+/.test(line));
  const prefix = `projects/${projectName}/`;
  const projectErrors = errors.filter(line => line.replace(/\\/g, '/').startsWith(prefix));
  const engineErrors = errors.filter(line => /^(core|tests|scripts|tools)\//.test(line.replace(/\\/g, '/')));

  if (asJson) {
    printJson({
      project: projectName,
      ok: projectErrors.length === 0,
      projectErrors,
      engineErrors: engineErrors.length,
    });
  } else {
    if (projectErrors.length === 0) console.log(pc.green(`${projectName}: no type errors.`));
    else {
      console.log(pc.red(`${projectName}: ${projectErrors.length} type error(s):`));
      for (const line of projectErrors) console.log(`  ${line}`);
    }
    if (engineErrors.length > 0) {
      console.log(pc.yellow(`Warning: the engine itself has ${engineErrors.length} type error(s) (core/tests/scripts/tools).`));
    }
  }
  process.exit(projectErrors.length === 0 ? 0 : 1);
}

// ---------------------------------------------------------------------------
// inspect (PNG only, 8-bit RGB or RGBA, non-interlaced)
// ---------------------------------------------------------------------------

interface Decoded {
  width: number;
  height: number;
  channels: number;
  pixels: Buffer;
}

function decodePng(buffer: Buffer): Decoded {
  const signature = buffer.subarray(0, 8).toString('hex');
  if (signature !== '89504e470d0a1a0a') fail('inspect only reads PNG files.');

  let offset = 8;
  let width = 0;
  let height = 0;
  let colorType = 0;
  let interlace = 0;
  const idat: Buffer[] = [];

  while (offset < buffer.length) {
    const length = buffer.readUInt32BE(offset);
    const type = buffer.toString('ascii', offset + 4, offset + 8);
    const data = buffer.subarray(offset + 8, offset + 8 + length);
    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      const bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
      if (bitDepth !== 8) fail(`inspect supports 8-bit PNG only (found ${bitDepth}-bit).`);
      if (colorType !== 6 && colorType !== 2) fail(`inspect supports RGB and RGBA PNG only (found color type ${colorType}).`);
      if (interlace !== 0) fail('inspect does not support interlaced PNG.');
    } else if (type === 'IDAT') {
      idat.push(data);
    } else if (type === 'IEND') {
      break;
    }
    offset += 12 + length;
  }

  const channels = colorType === 6 ? 4 : 3;
  const stride = width * channels;
  const raw = inflateSync(Buffer.concat(idat));
  const pixels = Buffer.alloc(height * stride);

  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    const src = y * (stride + 1) + 1;
    for (let x = 0; x < stride; x++) {
      const left = x >= channels ? pixels[y * stride + x - channels] : 0;
      const up = y > 0 ? pixels[(y - 1) * stride + x] : 0;
      const upLeft = y > 0 && x >= channels ? pixels[(y - 1) * stride + x - channels] : 0;
      let value = raw[src + x];
      if (filter === 1) value += left;
      else if (filter === 2) value += up;
      else if (filter === 3) value += (left + up) >> 1;
      else if (filter === 4) {
        const p = left + up - upLeft;
        const pa = Math.abs(p - left);
        const pb = Math.abs(p - up);
        const pc2 = Math.abs(p - upLeft);
        value += pa <= pb && pa <= pc2 ? left : pb <= pc2 ? up : upLeft;
      }
      pixels[y * stride + x] = value & 255;
    }
  }

  return { width, height, channels, pixels };
}

function inspect(positionals: string[], flags: Record<string, string | true>): void {
  const target = positionals[0];
  if (!target) fail('a PNG file is required.');
  const file = resolve(ROOT, target);
  if (!existsSync(file)) fail(`file not found: ${target}`);

  const image = decodePng(readFileSync(file));
  const { width, height, channels, pixels } = image;

  let minX = width, minY = height, maxX = -1, maxY = -1;
  let transparent = 0;
  const alphaValues = new Set<number>();
  const colors = new Set<number>();
  let opaque = 0;

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * channels;
      const a = channels === 4 ? pixels[i + 3] : 255;
      alphaValues.add(a);
      if (a === 0) {
        transparent++;
        continue;
      }
      opaque++;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
      if (colors.size < 200000) {
        colors.add((pixels[i] << 16) | (pixels[i + 1] << 8) | pixels[i + 2]);
      }
    }
  }

  const total = width * height;
  const touches = {
    top: opaque > 0 && minY === 0,
    bottom: opaque > 0 && maxY === height - 1,
    left: opaque > 0 && minX === 0,
    right: opaque > 0 && maxX === width - 1,
  };
  const hardEdges = [...alphaValues].every(a => a === 0 || a === 255);

  const report = {
    file: target.replace(/\\/g, '/'),
    width,
    height,
    opaqueBounds: opaque > 0 ? { x: minX, y: minY, width: maxX - minX + 1, height: maxY - minY + 1 } : null,
    reachesEdges: touches,
    transparentShare: Number((transparent / total).toFixed(4)),
    hardEdges,
    distinctAlphaValues: alphaValues.size,
    distinctOpaqueColors: colors.size,
  };

  if (flags['json']) {
    printJson(report as unknown as Json);
    return;
  }
  console.log(pc.bold(report.file));
  console.log(`  size: ${width}x${height}`);
  console.log(`  content bounds: ${report.opaqueBounds ? `${minX},${minY} ${report.opaqueBounds.width}x${report.opaqueBounds.height}` : 'empty'}`);
  // Reaching an edge is fine for full-bleed backgrounds and a problem for sprites with a margin.
  console.log(`  reaches edges: ${Object.entries(touches).filter(([, v]) => v).map(([k]) => k).join(', ') || 'none'}`);
  console.log(`  transparent: ${(report.transparentShare * 100).toFixed(1)}%`);
  console.log(`  hard edges (alpha only 0/255): ${hardEdges ? 'yes' : 'no'}`);
  console.log(`  distinct opaque colors: ${report.distinctOpaqueColors}${colors.size >= 200000 ? '+' : ''}`);
}

// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// capture: screenshot of a page served by the dev server, after a wait.
// Use it to see animation (the browser pane may not advance frames) or any
// state of a sandbox. Reuses the forge server on 5173 when one identifies itself, else starts its own.
// ---------------------------------------------------------------------------

async function capture(positionals: string[], flags: Record<string, string | true>): Promise<void> {
  const rawPath = positionals[0];
  if (!rawPath) {
    fail('capture needs a path, for example projects/<project>/sandboxes/<sandbox>/');
  }
  // Git Bash on Windows rewrites arguments that start with "/" into system paths.
  // Accept "projects/<p>/..." and "/projects/<p>/..." alike, and keep the part from "projects/".
  const normalized = rawPath.replace(/\\/g, '/');
  const at = normalized.indexOf('projects/');
  const urlPath = at >= 0 ? `/${normalized.slice(at)}` : normalized.startsWith('/') ? normalized : '';
  const match = /^\/projects\/([^/]+)\//.exec(urlPath);
  if (!match) fail('capture needs a path inside projects/, for example projects/<project>/sandboxes/<sandbox>/');
  const projectName = match[1];
  requireProject(projectName);
  const waitMs = flags['at'] !== undefined ? Number(flags['at']) : 500;
  if (!Number.isFinite(waitMs) || waitMs < 0) fail('--at must be a number of milliseconds.');
  const viewportRaw = String(flags['viewport'] ?? '800x600');
  const viewportMatch = /^(\d+)x(\d+)$/.exec(viewportRaw);
  if (!viewportMatch) fail(`--viewport must look like 800x600, got "${viewportRaw}".`);
  const viewport = { width: Number(viewportMatch[1]), height: Number(viewportMatch[2]) };
  const outFile = flags['out']
    ? resolve(ROOT, String(flags['out']))
    : resolve(PROJECTS, projectName, 'temp', `capture-${Date.now()}.png`);
  mkdirSync(resolve(outFile, '..'), { recursive: true });

  const server = await ensureForgeServer(undefined, projectName);
  const origin = server.origin;
  const errors: string[] = [];
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport });
    page.on('pageerror', (err) => errors.push(err.message));
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    await page.goto(origin + urlPath + (urlPath.includes('?') ? '&' : '?') + 'capture=1', { waitUntil: 'load' });
    await page.waitForFunction(() => (window as any).__FORGE_STATUS__?.state === 'ready' || (window as any).__FORGE_STATUS__?.state === 'error');
    const status = await page.evaluate(() => (window as any).__FORGE_STATUS__);
    if (status.state === 'error') throw new Error(status.error);
    await page.waitForTimeout(waitMs);
    await page.screenshot({ path: outFile, fullPage: true });
  } finally {
    await browser.close();
    await server.stop();
  }

  const report = {
    project: projectName,
    url: urlPath,
    file: relative(ROOT, outFile).split(sep).join('/'),
    viewport,
    waitMs,
    errors,
  };
  if (flags['json']) {
    printJson(report as unknown as Json);
  } else {
    console.log(pc.green(`Captured ${report.file} (${viewport.width}x${viewport.height}, after ${waitMs} ms)`));
    for (const message of errors) console.log(pc.red(`  page error: ${message}`));
  }
  process.exit(errors.length === 0 ? 0 : 1);
}

const [command, ...rest] = process.argv.slice(2);
const { positionals, flags } = parseFlags(rest);

const USAGE: Record<string, string> = {
  'new-project': 'npm run new-project -- <project> [--style] [--doc]\n  --style  add STYLE.md (style first, or theme first with a summary)\n  --doc    add PROJECT.md (directs one sandbox only)',
  'new-asset': 'npm run new-asset -- <project> <subpath> [--engine brush|pixel] [--size WxH] [--frames N] [--fps N]\n  --size    logical size of one frame; the export is size × scale\n  --frames  frames in an animation strip (default 1)\n  --fps     playback speed hint (default 6)',
  'new-sandbox': 'npm run new-sandbox -- <project> [name]\n  Creates projects/<project>/sandboxes/<sandbox>/index.html, a blank page.',
  list: 'npm run list -- [project] [--json]',
  check: 'npm run check -- <project> [--json]',
  inspect: 'npm run inspect -- <file.png> [--json]',
  capture: 'npm run capture -- projects/<project>/sandboxes/<sandbox>/ [--at <ms>] [--viewport WxH] [--out <png>] [--json]',
};

if (command && flags['help']) {
  console.log(USAGE[command] ?? 'Usage: npm run <new-project|new-asset|new-sandbox|list|check|inspect|capture> -- ...');
  process.exit(0);
}

switch (command) {
  case 'new-project': newProject(positionals, flags); break;
  case 'capture': capture(positionals, flags).catch(err => fail(String(err?.message ?? err))); break;
  case 'new-asset': newAsset(positionals, flags); break;
  case 'new-sandbox': newSandbox(positionals); break;
  case 'list': list(positionals, flags); break;
  case 'check': check(positionals, flags); break;
  case 'inspect': inspect(positionals, flags); break;
  default:
    console.error('Usage: tools/forge.ts <new-project|new-asset|new-sandbox|list|check|inspect|capture> ...');
    process.exit(1);
}
