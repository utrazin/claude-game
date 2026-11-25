/** One-shot conversion, never a runtime fallback. Dry run by default. */
import { existsSync, readdirSync, readFileSync, mkdirSync, renameSync, writeFileSync, unlinkSync } from 'node:fs';
import { resolve, relative, sep } from 'node:path';
const root = resolve('projects');
const targets = readdirSync(root, { withFileTypes: true }).filter(item => item.isDirectory())
  .map(item => ({ project: item.name, source: resolve(root, item.name, 'preview'), target: resolve(root, item.name, 'sandboxes/main') }))
  .filter(item => existsSync(item.source));
for (const item of targets) {
  if (!item.source.startsWith(root + sep) || !item.target.startsWith(root + sep)) throw new Error('Migration leaves projects root');
  if (existsSync(item.target)) throw new Error(`Migration collision: ${item.target}`);
}
console.log(JSON.stringify(targets, null, 2));
if (!process.argv.includes('--apply')) { console.log('Dry run. Pass --apply to convert.'); }
else for (const item of targets) {
  mkdirSync(resolve(item.target, '..'), { recursive: true });
  renameSync(item.source, item.target);
  const walk = (directory: string) => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const file = resolve(directory, entry.name);
      if (entry.isDirectory()) { walk(file); continue; }
      if (!/\.(html|css|[tj]s)$/.test(file)) continue;
      let text = readFileSync(file, 'utf8').replace(/(['"`(])(?=\.\.\/)/g, '$1../');
      text = text.replaceAll(`/projects/${item.project}/preview/`, `/projects/${item.project}/sandboxes/main/`);
      if (entry.name === 'index.html' && !text.includes('/viewer/forge-sandbox.js')) text = text.replace('</body>', '<script src="/viewer/forge-session.js"></script><script src="/viewer/forge-sandbox.js"></script></body>');
      writeFileSync(file, text);
    }
  };
  walk(item.target);
  for (const name of ['preview.bat', 'preview.sh']) if (existsSync(resolve(item.target, name))) unlinkSync(resolve(item.target, name));
  writeFileSync(resolve(item.target, 'open.bat'), `@echo off\r\ncd /d "%~dp0..\\..\\..\\.."\r\nnpx tsx tools/open-viewer.ts /projects/${item.project}/sandboxes/main/\r\n`);
  writeFileSync(resolve(item.target, 'open.sh'), `#!/bin/sh\ncd "$(dirname "$0")/../../../.." || exit 1\nexec npx tsx tools/open-viewer.ts /projects/${item.project}/sandboxes/main/\n`);
  console.log(`Migrated ${relative(root, item.source)} → ${relative(root, item.target)}`);
}
