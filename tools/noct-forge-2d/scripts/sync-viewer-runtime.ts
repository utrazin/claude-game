/** Publish byte-identical browser session/theme assets to the Python renderer checkout. */
import { readFile, writeFile, copyFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
const destination = process.argv[2];
if (!destination) throw new Error('Usage: tsx scripts/sync-viewer-runtime.ts <3D-repository>');
const root = resolve(destination, 'Tools/viewer');
const files = { 'forge-session.js': 'js/forge_session.js', 'forge-theme.css': 'forge-theme.css' };
const hashes: Record<string, string> = {};
for (const [source, target] of Object.entries(files)) {
  const bytes = await readFile(resolve('viewer', source));
  hashes[source] = createHash('sha256').update(bytes).digest('hex');
  await copyFile(resolve('viewer', source), resolve(root, target));
}
const manifest = JSON.stringify({ version: '2.0.0', canonicalSource: 'NoctAssetForge2D/viewer', hashes }, null, 2) + '\n';
await writeFile(resolve('viewer/runtime-version.json'), manifest);
await writeFile(resolve(root, 'runtime-version.json'), manifest);
console.log('Published session/theme 2.0.0 to both independent distributions.');
