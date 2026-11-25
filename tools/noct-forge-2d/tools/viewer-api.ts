import type { Plugin } from 'vite';
import { resolve, relative, extname } from 'node:path';
import { readdir, stat } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { createHash, randomUUID } from 'node:crypto';
import { FORGE_APP_ID, FORGE_HEALTH_PATH, workspaceId } from './forge-server';

async function scan(dir: string): Promise<string[]> {
  if (!existsSync(dir)) return [];
  const files: string[] = [];
  for (const item of await readdir(dir, { withFileTypes: true })) {
    const path = resolve(dir, item.name);
    if (item.isDirectory()) files.push(...await scan(path));
    else if (item.isFile()) files.push(path);
  }
  return files.sort();
}
export function forgeApi(): Plugin {
  return { name: 'forge-session-api', configureServer(server) {
    const root = server.config.root, instanceId = randomUUID();
    const configuredScope = JSON.parse(String(server.config.define?.__FORGE_SCOPE__ || 'null')) as string | null;
    server.middlewares.use(async (req, res, next) => {
      const url = new URL(req.url || '/', 'http://localhost');
      const decoded = decodeURIComponent(url.pathname).replace(/\\/g, '/');
      const projectPath = decoded.match(/\/projects\/([^/]+)/);
      if (configuredScope && projectPath && projectPath[1] !== configuredScope) {
        res.statusCode = 403; res.end('Project is outside the session scope'); return;
      }
      if (!url.pathname.startsWith('/api/')) return next();
      const send = (value: unknown, code = 200) => {
        res.statusCode = code; res.setHeader('Content-Type', 'application/json');
        res.setHeader('Cache-Control', 'no-store'); res.end(JSON.stringify(value));
      };
      if (url.pathname === FORGE_HEALTH_PATH) return send({ app: FORGE_APP_ID, protocolVersion: 2,
        runtimeVersion: '2.0.0', workspaceId: workspaceId(root), instanceId, mode: configuredScope ? 'project' : 'global', scope: configuredScope });
      if (url.pathname !== '/api/catalog') return send({ error: 'Unknown API route' }, 404);
      try {
        const projectRoot = resolve(root, 'projects');
        const assets: any[] = [], projects: any[] = [];
        const requestedScope = url.searchParams.get('project');
        if (configuredScope && requestedScope && requestedScope !== configuredScope) return send({ error: 'Project is outside the session scope' }, 403);
        const scope = configuredScope || requestedScope;
        if (scope && !/^[a-zA-Z0-9_-]+$/.test(scope)) return send({ error: 'Invalid project' }, 403);
        const entries = existsSync(projectRoot) ? await readdir(projectRoot, { withFileTypes: true }) : [];
        for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
          if (!entry.isDirectory() || (scope && entry.name !== scope)) continue;
          const dir = resolve(projectRoot, entry.name);
          const sandboxDir = resolve(dir, 'sandboxes');
          const sandboxes = existsSync(sandboxDir) ? (await readdir(sandboxDir, { withFileTypes: true }))
            .filter(sb => sb.isDirectory() && existsSync(resolve(sandboxDir, sb.name, 'index.html'))).map(sb => sb.name).sort() : [];
          for (const file of await scan(resolve(dir, 'assets'))) {
            const format = extname(file).slice(1).toLowerCase();
            if (!['png', 'jpg', 'jpeg', 'webp', 'svg'].includes(format)) continue;
            const info = await stat(file);
            const subpath = relative(resolve(dir, 'assets'), file).replace(/\\/g, '/');
            assets.push({ project: entry.name, subpath, filename: subpath.split('/').pop(), format,
              size: info.size, mtime: info.mtimeMs, url: '/projects/' + [entry.name, 'assets', ...subpath.split('/')].map(encodeURIComponent).join('/') });
          }
          projects.push({ name: entry.name, sandboxes, assetCount: assets.filter(a => a.project === entry.name).length,
            sourceCount: (await scan(resolve(dir, 'source'))).filter(f => /\.[tj]s$/.test(f)).length });
        }
        const sandbox = url.searchParams.get('sandbox');
        let compositionRevision = '';
        if (sandbox && scope) {
          if (!/^[a-zA-Z0-9_-]+$/.test(sandbox)) return send({ error: 'Invalid sandbox' }, 403);
          const files = [...await scan(resolve(projectRoot, scope, 'sandboxes', sandbox)), ...await scan(resolve(projectRoot, scope, 'source')), ...await scan(resolve(root, 'core'))].filter(f => /\.(html|css|[tj]s)$/.test(f));
          compositionRevision = JSON.stringify(await Promise.all(files.map(async path => {
            const info = await stat(path); return [relative(root, path), info.mtimeMs, info.size];
          })));
        }
        send({ schemaVersion: 2, revision: createHash('sha256').update(JSON.stringify([assets, projects])).digest('hex'), assets, projects, compositionRevision });
      } catch (error: any) { send({ error: error.message }, 500); }
    });
  }};
}
