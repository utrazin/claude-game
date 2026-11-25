/**
 * Environment check for NoctAssetForge.
 *
 * Verifies what the export pipeline and the test suite need, and prints the command
 * that fixes each failure. Exits with code 1 if any check fails.
 *
 *   npm run doctor
 */

import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

interface Check {
  label: string;
  ok: boolean;
  fix?: string;
}

const checks: Check[] = [];
const add = (label: string, ok: boolean, fix?: string) => checks.push({ label, ok, fix });

// 1. Node version (package.json "engines" is >=20).
const [major] = process.versions.node.split('.').map(Number);
add(`Node.js ${process.versions.node} (requires >= 20)`, major >= 20, 'Install Node.js 20 or newer from https://nodejs.org');

// 2. Dependencies declared in package.json are installed.
const pkg = JSON.parse(readFileSync(resolve('package.json'), 'utf8')) as {
  dependencies?: Record<string, string>;
  devDependencies?: Record<string, string>;
};
const declared = [...Object.keys(pkg.dependencies ?? {}), ...Object.keys(pkg.devDependencies ?? {})];
const missing = declared.filter(name => !existsSync(resolve('node_modules', name, 'package.json')));
add(`Dependencies installed (${declared.length} declared)`, missing.length === 0, missing.length ? 'Run: npm install' : undefined);

// 3. Headless Chromium used by the export pipeline.
let chromiumPath = '';
try {
  chromiumPath = chromium.executablePath();
} catch {
  chromiumPath = '';
}
add(
  `Playwright Chromium${chromiumPath ? `: ${chromiumPath}` : ' not resolved'}`,
  chromiumPath !== '' && existsSync(chromiumPath),
  'Run: npx playwright install chromium',
);

// 4. TypeScript configuration present.
add('tsconfig.json present', existsSync(resolve('tsconfig.json')), 'The repository is incomplete: restore tsconfig.json');

let failed = 0;
for (const check of checks) {
  if (check.ok) {
    console.log(`  ok    ${check.label}`);
  } else {
    failed++;
    console.log(`  FAIL  ${check.label}`);
    if (check.fix) console.log(`        -> ${check.fix}`);
  }
}

console.log(failed === 0 ? '\nEnvironment is ready.' : `\n${failed} check(s) failed.`);
process.exit(failed === 0 ? 0 : 1);
