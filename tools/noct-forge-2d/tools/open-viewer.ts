import { execFile } from 'node:child_process';
import { ensureForgeServer } from './forge-server';
const path = process.argv[2] || '/viewer/';
if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Expected a local viewer path');
const server = await ensureForgeServer();
const url = server.origin + path;
console.log(url);
if (process.platform === 'win32') execFile('cmd', ['/c', 'start', '', url]);
else execFile(process.platform === 'darwin' ? 'open' : 'xdg-open', [url]);
// An adopted server has no owned resources; an owned Vite server keeps the process alive.
