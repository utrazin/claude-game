/* Managed 2D compositions. State and updates use the same session runtime as the viewer. */
(async function () {
    const match = location.pathname.match(/^\/projects\/([^/]+)\/sandboxes\/([^/]+)\//);
    if (!match) throw new Error('Sandbox requires a canonical project/sandbox URL');
    const project = decodeURIComponent(match[1]), sandbox = decodeURIComponent(match[2]);
    const url = `/api/catalog?project=${encodeURIComponent(project)}&sandbox=${encodeURIComponent(sandbox)}`;
    let composition = null, revision = null;
    const hooks = window.ForgeSandboxHooks || {};
    const poller = new ForgeSession.Poller(async () => {
        try {
            const response = await fetch(url, { cache: 'no-store' });
            if (!response.ok) throw new Error(`Catálogo: HTTP ${response.status}`);
            const data = await response.json();
            if (composition !== null && composition !== data.compositionRevision) {
                sessionStorage.setItem('forge-composition:' + location.pathname, JSON.stringify({ scroll: [scrollX, scrollY], custom: hooks.captureState?.() }));
                location.reload(); return;
            }
            if (revision !== data.revision) {
                for (const image of document.images) {
                    const path = new URL(image.src).pathname;
                    const asset = data.assets.find(item => new URL(item.url, location.origin).pathname === path);
                    if (!asset || new URL(image.src).searchParams.get('revision') === String(asset.mtime)) continue;
                    const candidate = new Image(); candidate.src = asset.url + '?revision=' + asset.mtime;
                    await candidate.decode(); image.src = candidate.src;
                }
                await hooks.updateAssets?.(data);
                revision = data.revision;
            }
            composition = data.compositionRevision;
            ForgeSession.status('ready', null, revision);
        } catch (error) { ForgeSession.status('error', error.message); }
    });
    window.ForgeSandbox = { ready: async () => {
        await Promise.all(Array.from(document.images).map(image => image.decode()));
        const key = 'forge-composition:' + location.pathname;
        const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
        if (saved) { sessionStorage.removeItem(key); await hooks.restoreState?.(saved.custom); scrollTo(...saved.scroll); }
        await poller.refresh();
        if (new URLSearchParams(location.search).get('capture') === '1') poller.stop();
    }, dispose: () => poller.stop() };
    if (document.readyState === 'complete') await window.ForgeSandbox.ready();
    else window.addEventListener('load', () => window.ForgeSandbox.ready());
    window.addEventListener('pagehide', () => poller.stop());
})();
