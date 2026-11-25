/**
 * ForgeSandbox - Multi-asset Sandbox Runtime for NoctAssetForge3D.
 * Allows arbitrary HTML/CSS/Three.js composition and loading of multiple BBModel and GLB assets.
 */

(function (global) {
    function computeUnifiedBoundingBox(objects) {
        const totalBox = new THREE.Box3();
        for (const obj of objects) {
            if (obj) {
                obj.updateMatrixWorld(true);
                const b = new THREE.Box3().setFromObject(obj);
                if (!b.isEmpty()) {
                    totalBox.union(b);
                }
            }
        }
        if (totalBox.isEmpty()) {
            totalBox.min.set(-2, -2, -2);
            totalBox.max.set(2, 2, 2);
        }
        const center = new THREE.Vector3();
        const size = new THREE.Vector3();
        totalBox.getCenter(center);
        totalBox.getSize(size);
        return {
            box: totalBox,
            center: [center.x, center.y, center.z],
            size: [size.x, size.y, size.z],
            maxDimension: Math.max(size.x, size.y, size.z)
        };
    }

    class ForgeSandbox {
        constructor(container, options = {}) {
            this.container = container;
            this.options = options;
            this.project = null;
            this.sandboxName = null;
            this._catalog = null;
            this._instances = [];
            this.watchedAssets = [];
            this.frameCallbacks = [];
            this.watchTimer = null;
            this.initialView = options.view || null;

            // Extract project and sandbox from URL if available
            const match = typeof window !== 'undefined'
                ? window.location.pathname.match(/\/sandbox\/([^/]+)\/([^/]+)/)
                : null;
            if (match) {
                this.project = decodeURIComponent(match[1]);
                this.sandboxName = decodeURIComponent(match[2]);
            } else {
                this.sandboxName = options.sandbox || null;
                this.project = options.project || null;
            }
        }

        static async create(container = null, options = {}) {
            let containerEl = container;
            if (typeof container === 'string' && typeof document !== 'undefined') {
                containerEl = document.getElementById(container);
            }
            if (!containerEl && typeof document !== 'undefined') {
                containerEl = document.getElementById('app')
                    || document.getElementById('canvas-container')
                    || document.body;
            }

            const sandbox = new ForgeSandbox(containerEl, options);
            if (typeof window !== 'undefined') {
                window.__CURRENT_SANDBOX__ = sandbox;
                if (typeof window.setView !== 'function') {
                    window.setView = (preset) => sandbox.setView(preset);
                }
            }
            await sandbox.init();
            return sandbox;
        }

        async init() {
            // 1. Initialize Scene / SceneSetup
            this.sceneSetup = new SceneSetup(this.container);

            if (this.options.grid === false && this.sceneSetup.gridHelper) {
                this.sceneSetup.gridHelper.visible = false;
            }
            if (this.options.axes === false && this.sceneSetup.axesHelper) {
                this.sceneSetup.axesHelper.visible = false;
            }

            // URL query parameters
            if (typeof window !== 'undefined' && window.location?.search) {
                const params = new URLSearchParams(window.location.search);
                if (params.get('view')) this.initialView = params.get('view');
                if (params.get('transparent') === '1' || this.options.transparent) {
                    this.sceneSetup.scene.background = null;
                    if (typeof document !== 'undefined') {
                        if (document.body) document.body.style.backgroundColor = 'transparent';
                        if (document.documentElement) document.documentElement.style.backgroundColor = 'transparent';
                    }
                }
            }

            // Hook onFrame callbacks into render loop
            const origRender = this.sceneSetup._render.bind(this.sceneSetup);
            this.sceneSetup._render = () => {
                for (const cb of this.frameCallbacks) {
                    try { cb(); } catch (err) { console.error("[ForgeSandbox onFrame]", err); }
                }
                origRender();
            };

            // 2. Fetch Project Catalog
            if (typeof fetch !== 'undefined') {
                try {
                    if (!this.project) throw new Error('Sandbox requires an explicit project');
                    const catalogUrl = `/api/catalog?project=${encodeURIComponent(this.project)}`;
                    const resp = await fetch(catalogUrl, { cache: 'no-store' });
                    if (!resp.ok) throw new Error(`Catálogo: HTTP ${resp.status}`);
                    if (resp.ok) {
                        this._catalog = await resp.json();
                        if (!this.project && this._catalog.id) {
                            this.project = this._catalog.id;
                        }
                    }
                } catch (e) {
                    ForgeSession.status('error', e.message);
                    throw e;
                }
            }

            // 3. Restore camera if saved from hot-reload
            if (this.initialView) {
                this.setView(this.initialView);
            }

            // 4. Start auto-watch hot-reload
            if (this.options.watch !== false && new URLSearchParams(window.location.search).get('capture') !== '1') {
                this.watch();
            }
        }

        get scene() { return this.sceneSetup.scene; }
        get camera() { return this.sceneSetup.camera; }
        get renderer() { return this.sceneSetup.renderer; }
        get controls() { return this.sceneSetup.controls; }
        get THREE() { return THREE; }
        get catalog() { return this._catalog; }
        get instances() { return this._instances; }

        async add(assetIdOrGlb, options = {}) {
            let loadedAsset = null;
            const isGlb = Boolean(options.glb) || (typeof assetIdOrGlb === 'string' && (assetIdOrGlb.endsWith('.glb') || assetIdOrGlb.startsWith('glb:')));

            if (isGlb) {
                const glbRelPath = options.glb || (assetIdOrGlb.startsWith('glb:') ? assetIdOrGlb.substring(4) : assetIdOrGlb);
                const proj = this.project || (this._catalog?.id || '');
                const url = `/api/p/${encodeURIComponent(proj)}/glb?path=${encodeURIComponent(glbRelPath)}`;
                loadedAsset = await loadAssetObject({
                    kind: 'glb',
                    url: url
                }, {
                    wireframe: options.wireframe,
                    shading: options.shading
                });

                const stamp = this._catalog?.glbs?.find(g => g.path === glbRelPath)?.stamp || null;
                this.watchedAssets.push({ type: 'glb', path: glbRelPath, stamp });
            } else {
                const assetId = assetIdOrGlb;
                const assetInfo = this._catalog?.assets?.find(a => a.id === assetId || a.name === assetId);
                if (!assetInfo) {
                    throw new Error(`Asset not found in catalog for project '${this.project}': ${assetId}`);
                }

                const modelResp = await fetch(assetInfo.model_url, { cache: 'no-store' });
                if (!modelResp.ok) {
                    throw new Error(`Failed to load model for asset '${assetId}': HTTP ${modelResp.status}`);
                }
                const modelData = await modelResp.json();

                let textureData = null;
                let variantStamp = null;
                if (options.variant) {
                    const v = assetInfo.variants?.find(item => item.id === options.variant);
                    if (v) {
                        textureData = v.url;
                        variantStamp = v.stamp;
                    }
                }

                loadedAsset = await loadAssetObject({
                    kind: 'bbmodel',
                    modelData: modelData,
                    textureData: textureData
                }, {
                    wireframe: options.wireframe,
                    shading: options.shading
                });

                this.watchedAssets.push({
                    type: 'asset',
                    id: assetId,
                    stamp: assetInfo.stamp,
                    variant: options.variant || null,
                    variantStamp: variantStamp
                });
            }

            const content = loadedAsset.object;
            const obj = new THREE.Group(); obj.add(content);
            loadedAsset.object = obj;
            if (options.name) obj.name = options.name;

            // Apply position
            if (options.position) {
                obj.position.set(options.position[0] || 0, options.position[1] || 0, options.position[2] || 0);
            }

            // Apply rotation (degrees)
            if (options.rotationY !== undefined) {
                obj.rotation.y = THREE.MathUtils.degToRad(options.rotationY);
            } else if (options.rotation) {
                obj.rotation.set(
                    THREE.MathUtils.degToRad(options.rotation[0] || 0),
                    THREE.MathUtils.degToRad(options.rotation[1] || 0),
                    THREE.MathUtils.degToRad(options.rotation[2] || 0)
                );
            }

            // Apply scale
            if (options.scale !== undefined) {
                if (typeof options.scale === 'number') {
                    obj.scale.set(options.scale, options.scale, options.scale);
                } else if (Array.isArray(options.scale)) {
                    obj.scale.set(options.scale[0] || 1, options.scale[1] || 1, options.scale[2] || 1);
                }
            }

            this.sceneSetup.modelGroup.add(obj);
            this._instances.push(loadedAsset);

            // Play clip if requested
            if (options.clip) {
                if (loadedAsset.clips && loadedAsset.clips.names && loadedAsset.clips.names.includes(options.clip)) {
                    loadedAsset.clips.select(options.clip);
                    loadedAsset.clips.play();
                } else {
                    console.warn(`[ForgeSandbox] Clip '${options.clip}' not found for '${assetIdOrGlb}'. Available:`, loadedAsset.clips?.names);
                }
            }

            const watched = this.watchedAssets[this.watchedAssets.length - 1];
            if (watched.type === 'asset') {
                const canonical = this._catalog.assets.find(a => a.id === watched.id || a.name === watched.id);
                watched.id = canonical.id; watched.revision = ForgeSession.assetRevision(canonical, watched.variant);
            } else watched.revision = JSON.stringify(watched.stamp);
            watched.handle = loadedAsset; watched.content = content; watched.options = options;
            return loadedAsset;
        }

        frame() {
            if (this._instances.length === 0) return;
            const bbox = computeUnifiedBoundingBox(this._instances.map(inst => inst.object));
            if (this.initialView) {
                this.setView(this.initialView);
            } else {
                this.sceneSetup.fitToBbox(bbox);
            }
        }

        setView(viewPreset) {
            let bbox = null;
            if (this._instances.length > 0) {
                bbox = computeUnifiedBoundingBox(this._instances.map(inst => inst.object));
            }
            this.sceneSetup.setViewPreset(viewPreset, bbox);
        }

        async ready() {
            const key = 'forge-scene:' + window.location.pathname;
            const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
            if (saved) {
                sessionStorage.removeItem(key);
                ForgeSession.restoreCamera(this.sceneSetup, saved.camera);
                await this.options.restoreState?.(saved.custom);
            }
            if (!saved && this.initialView && this._instances.length > 0) {
                this.setView(this.initialView);
            }
            if (typeof window !== 'undefined') {
                ForgeSession.status('ready');
            }
        }

        onFrame(callback) {
            if (typeof callback === 'function') {
                this.frameCallbacks.push(callback);
            }
        }

        async refreshInstances() {
            const resp = await fetch(`/api/catalog?project=${encodeURIComponent(this.project)}&sandbox=${encodeURIComponent(this.sandboxName || '')}`, { cache: 'no-store' });
            if (!resp.ok) throw new Error(`Catálogo: HTTP ${resp.status}`);
            const next = await resp.json();
            const composition = JSON.stringify(next.compositionRevision);
            if (this.compositionRevision && this.compositionRevision !== composition) {
                sessionStorage.setItem('forge-scene:' + window.location.pathname, JSON.stringify({ camera: ForgeSession.cameraSnapshot(this.sceneSetup), custom: this.options.captureState?.() }));
                this.dispose(); window.location.reload(); return;
            }
            this.compositionRevision = composition;
            for (const watched of this.watchedAssets) {
                const item = watched.type === 'asset' ? next.assets.find(a => a.id === watched.id) : next.glbs.find(g => g.path === watched.path);
                if (!item) { ForgeSession.status('error', 'Asset removido do sandbox: ' + (watched.id || watched.path)); continue; }
                const revision = watched.type === 'asset' ? ForgeSession.assetRevision(item, watched.variant) : JSON.stringify(item.stamp);
                if (revision === watched.revision) continue;
                let source;
                if (watched.type === 'asset') {
                    const response = await fetch(item.model_url, { cache: 'no-store' });
                    if (!response.ok) throw new Error(`Modelo: HTTP ${response.status}`);
                    const variant = watched.variant ? item.variants.find(v => v.id === watched.variant) : null;
                    if (watched.variant && !variant) throw new Error('Variante removida: ' + watched.variant);
                    source = { kind: 'bbmodel', modelData: await response.json(), textureData: variant ? variant.url + '?revision=' + encodeURIComponent(revision) : null };
                } else source = { kind: 'glb', url: `/api/p/${encodeURIComponent(this.project)}/glb?path=${encodeURIComponent(watched.path)}&revision=${encodeURIComponent(revision)}` };
                const candidate = await loadAssetObject(source, { ...watched.options, textureFilter: watched.options.textureFilter || item.texture_filter });
                if (this.disposed) { candidate.dispose(); return; }
                const handle = watched.handle, parent = handle.object;
                const playback = ForgeSession.playbackSnapshot(handle.clips);
                handle.object = watched.content; handle.dispose();
                parent.add(candidate.object); watched.content = candidate.object;
                Object.assign(handle, candidate); handle.object = parent;
                ForgeSession.restorePlayback(handle.clips, playback);
                watched.revision = revision;
                ForgeSession.status('ready', null, revision);
            }
            this._catalog = next;
        }
        watch(intervalMs = 2000) {
            if (this.watchTimer || !this.project) return;
            this.watchTimer = new ForgeSession.Poller(async () => {
                try { await this.refreshInstances(); }
                catch (error) { ForgeSession.status('error', error.message); console.error(error); }
            }, intervalMs);
            this.watchTimer.refresh();
        }

        dispose() {
            this.disposed = true;
            if (this.watchTimer) {
                this.watchTimer.stop();
                this.watchTimer = null;
            }
            for (const inst of this._instances) {
                inst.dispose();
            }
            this._instances = [];
            this.frameCallbacks = [];
            this.sceneSetup.dispose();
        }
    }

    global.ForgeSandbox = ForgeSandbox;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { ForgeSandbox };
    }
})(typeof window !== 'undefined' ? window : globalThis);
