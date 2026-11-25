/**
 * Dev server discovery shared by the export and capture commands.
 *
 * A server on the default port is only adopted when it identifies itself as the forge through
 * /api/health with matching protocol, workspace and scope. Any other program
 * listening there is ignored and the forge starts its own server on a free port.
 */

import { createServer, type ViteDevServer } from 'vite';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { readFile, mkdir, writeFile, rm } from 'node:fs/promises';

export const FORGE_APP_ID = 'noct2d-forge';
export const FORGE_HEALTH_PATH = '/api/health';
export const workspaceId = (root: string) => createHash('sha256').update(process.platform === 'win32' ? resolve(root).toLowerCase() : resolve(root)).digest('hex');
export const DEFAULT_PORT = 5173;
const PROBE_ORIGINS = [`http://127.0.0.1:${DEFAULT_PORT}`, `http://localhost:${DEFAULT_PORT}`];

export interface ForgeServer {
  origin: string;
  stop: () => Promise<void>;
}

async function isForgeServer(origin: string, scope: string | null = null): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 600);
  try {
    const res = await fetch(origin + FORGE_HEALTH_PATH, { signal: controller.signal });
    if (res.status !== 200) return false;
    const data = (await res.json()) as { app?: unknown; protocolVersion?: number; workspaceId?: string; scope?: string | null };
    return data?.app === FORGE_APP_ID && data.protocolVersion === 2 && data.workspaceId === workspaceId(process.cwd()) && data.scope === scope;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export async function ensureForgeServer(preferredUrl?: string, scope: string | null = null): Promise<ForgeServer> {
  if (preferredUrl) {
    if (!await isForgeServer(preferredUrl, scope)) throw new Error('Server does not match this workspace, scope and protocol');
    return { origin: preferredUrl.replace(/\/$/, ''), stop: async () => {} };
  }

  for (const origin of PROBE_ORIGINS) {
    if (await isForgeServer(origin, scope)) return { origin, stop: async () => {} };
  }

  const registry = resolve(process.cwd(), '.runtime', 'viewer-server.json');
  if (!scope) {
    try {
      const saved = JSON.parse(await readFile(registry, 'utf8'));
      if (await isForgeServer(saved.origin)) return { origin: saved.origin, stop: async () => {} };
    } catch { /* A missing/stale registry is rediscovered by starting a server. */ }
  }

  const server: ViteDevServer = await createServer({
    root: resolve(process.cwd()),
    define: { __FORGE_SCOPE__: JSON.stringify(scope) },
    server: { port: scope ? 5199 : DEFAULT_PORT, host: '127.0.0.1', strictPort: false,
      ...(scope ? { fs: { strict: true, allow: ['core', 'viewer', 'tools', 'stamps', 'node_modules', `projects/${scope}`].map(path => resolve(process.cwd(), path)) } } : {}) },
    logLevel: 'silent',
  });
  await server.listen();
  const address = server.httpServer?.address();
  const port = typeof address === 'object' && address ? address.port : 5199;
  const origin = `http://127.0.0.1:${port}`;
  if (!scope) { await mkdir(resolve(registry, '..'), { recursive: true }); await writeFile(registry, JSON.stringify({ origin })); }
  return {
    origin,
    stop: async () => {
      await server.close();
      if (!scope) {
        try { if (JSON.parse(await readFile(registry, 'utf8')).origin === origin) await rm(registry); } catch {}
      }
    },
  };
}
