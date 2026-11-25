import assert from 'node:assert/strict';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

console.log('🧪 Checking Public/Private Boundary & Internal Imports...\n');

function scanFiles(dir: string, ext = '.ts'): string[] {
  const results: string[] = [];
  try {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      const stat = statSync(full);
      if (stat.isDirectory()) {
        if (entry === 'node_modules' || entry === '.git' || entry === 'dist' || entry === 'temp' || entry === 'scratch') continue;
        results.push(...scanFiles(full, ext));
      } else if (full.endsWith(ext)) {
        results.push(full);
      }
    }
  } catch {
    // Directory might not exist
  }
  return results;
}

// 1. Ensure projects & templates only import from public entrypoints: @core, @core/brush, @core/pixel
const projectFiles = [...scanFiles('projects'), ...scanFiles('templates'), ...scanFiles('tools')];
const forbiddenInternalPattern = /from\s+['"][^'"]*\/internal\/[^'"]*['"]/;
const nonCanonicalCoreImport = /from\s+['"]@core\/(?!brush\b|pixel\b)[^'"]+['"]/;

for (const file of projectFiles) {
  const content = readFileSync(file, 'utf8');
  if (forbiddenInternalPattern.test(content)) {
    assert.fail(`File ${file} is importing from internal/ private implementation!`);
  }
  if (nonCanonicalCoreImport.test(content)) {
    assert.fail(`File ${file} is importing non-canonical subpath from @core! Only @core, @core/brush, @core/pixel are public.`);
  }
}

// 2. Ensure core/brush/index.ts does not export internal paths
const indexContent = readFileSync('core/brush/index.ts', 'utf8');
const lines = indexContent.split('\n');
for (const line of lines) {
  if (line.trim().startsWith('export') && line.includes('/internal/')) {
    assert.fail(`core/brush/index.ts leaks internal implementation: ${line}`);
  }
}

console.log('✔ Public/Private Boundary Verification passed!\n');
