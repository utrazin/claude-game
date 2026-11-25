/* NoctAssetForge3D - Global Viewer & Single Asset Inspector */
let sceneSetup, parser, refPlane, animationPlayer, currentLoadedAsset = null, inspector = null;
let currentBbox = null, currentModelData = null, currentTextureInput = null;
let isWireframe = false, isShaded = true, showTexture = true, textureFilter = null;
let catalog = null, activeAsset = null, activeVariant = '', fingerprint = null;
let generation = 0, requestedCamera = null;
let isLoading = false;
let isGlobalMode = false, projectsList = [], activeProject = null, activeFormat = 'bbmodel';
let searchQuery = '';
let projectsSignature = '';
let catalogSequence = 0, mountedKey = null, initializing = true;
let navigationPending = false, inspectorTab = 'hierarchy', userChoseInspectorTab = false;
let navigationStarted = 0, lastIndexRefresh = 0;
let navigationSerial = 0;
const modelRequests = new ForgeSession.LatestRequest();
const refreshPoller = new ForgeSession.Poller(() => refreshAll(false), 3000);
const catalogRequests = new ForgeSession.LatestRequest();

const params = new URLSearchParams(window.location.search);
window.__VIEWER_READY__ = false;

function finishLoading() {
    document.body.classList.remove('is-loading');
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.style.display = 'none';
    window.__VIEWER_READY__ = !initializing && window.__FORGE_STATUS__?.state !== 'error';
    isLoading = false;
    if (!initializing && window.__FORGE_STATUS__?.state !== 'error') ForgeSession.status('ready', null, fingerprint);
    syncAnimationUI();
}

function startLoading(text = 'Loading 3D Model...') {
    isLoading = true;
    document.body.classList.add('is-loading');
    if (sceneSetup?.modelGroup) sceneSetup.modelGroup.visible = false;
    const empty = document.getElementById('stage-empty'); if (empty) empty.hidden = true;
    document.getElementById('asset-message').textContent = '';
    ForgeSession.status('loading');
    const overlay = document.getElementById('loading-overlay');
    const loadingText = document.getElementById('loading-text');
    const spinner = document.querySelector('.spinner');
    if (loadingText) loadingText.textContent = text;
    if (spinner) spinner.style.display = 'block';
    if (overlay) overlay.style.display = 'flex';
}

function showError(message) {
    const loadingText = document.getElementById('loading-text');
    const assetMessage = document.getElementById('asset-message');
    const spinner = document.querySelector('.spinner');
    if (loadingText) loadingText.textContent = message;
    if (assetMessage) assetMessage.textContent = message;
    if (spinner) spinner.style.display = 'none';
    ForgeSession.status('error', message);
    console.error(message);
}

function disposeModel() {
    if (inspector) inspector.clearSelection();
    if (currentLoadedAsset) {
        currentLoadedAsset.dispose();
        currentLoadedAsset = null;
        window.currentLoadedAsset = null;
    } else if (animationPlayer) {
        animationPlayer.dispose();
        animationPlayer = null;
    }
    if (sceneSetup?.modelGroup) sceneSetup.modelGroup.clear();
    parser = null;
    currentModelData = null;
    currentBbox = null;
    const animPanel = document.getElementById('animation-panel');
    if (animPanel) animPanel.hidden = true;
    if (inspector) inspector.renderTree();
}

function currentMountKey() {
    return `${activeProject || catalog?.id || 'direct'}:${activeAsset || activeFormat}`;
}
async function installLoaded(loaded, modelData, textureData, ticket) {
    if (ticket !== generation) { loaded.dispose(); return false; }
    const same = mountedKey === currentMountKey();
    const camera = same ? ForgeSession.cameraSnapshot(sceneSetup) : null;
    const playback = same ? ForgeSession.playbackSnapshot(animationPlayer) : null;
    const selectedId = same ? inspector?.selectedObject?.userData?.uuid : null;
    disposeModel();
    sceneSetup.modelGroup.visible = true;
    currentLoadedAsset = loaded; window.currentLoadedAsset = loaded;
    parser = loaded.parser; currentModelData = modelData; currentTextureInput = textureData;
    animationPlayer = loaded.clips;
    sceneSetup.modelGroup.add(loaded.object); currentBbox = loaded.bbox;
    mountedKey = currentMountKey();
    if (camera) ForgeSession.restoreCamera(sceneSetup, camera);
    else { sceneSetup.fitToBbox(currentBbox); setView(params.get('view') || 'iso'); }
    const clips = loaded.clips.names || [];
    const select = document.getElementById('animation-select');
    if (select) select.replaceChildren(...clips.map(name => new Option(name, name)));
    if (!ForgeSession.restorePlayback(animationPlayer, playback) && clips.length && !playback?.clip) loaded.clips.select(clips[0]);
    const panel = document.getElementById('animation-panel');
    if (panel) panel.hidden = !clips.length;
    if (playback?.clip && !clips.includes(playback.clip)) document.getElementById('asset-message').textContent = 'O clip anterior não existe nesta versão.';
    document.getElementById('badge-name').textContent = modelData.name || activeAsset || 'Modelo';
    document.getElementById('badge-meta').textContent = `${loaded.kind.toUpperCase()} · ${currentBbox.size.map(v => v.toFixed(1)).join(' × ')}`;
    toggleTexture(showTexture);
    if (refPlane) refPlane.update(currentBbox);
    if (inspector) {
        inspector.setTarget(loaded);
        if (selectedId) loaded.object.traverse(node => { if (node.userData?.uuid === selectedId) inspector.selectNode(node, null); });
    }
    if (parser?.textureErrors?.length) document.getElementById('asset-message').textContent = parser.textureErrors.join('; ');
    updateFormatSelector(); renderClipList(); syncAnimationUI();
    document.getElementById('stage-empty').hidden = true;
    document.getElementById('selection-name').textContent = 'Nenhum elemento selecionado';
    document.getElementById('selection-transform').textContent = 'Selecione um item na hierarquia para inspecioná-lo.';
    if (!userChoseInspectorTab) setInspectorTab(clips.length ? 'clips' : 'hierarchy', false);
    const warning = parser?.textureErrors?.length;
    if (warning) document.getElementById('asset-message').textContent = 'Modelo aberto sem algumas texturas. ' + parser.textureErrors.length + ' textura(s) indisponível(is).';
    window.__VIEWER_LOAD_MS__ = Math.round(performance.now() - navigationStarted);
    return true;
}
async function loadModel(modelData, textureData, options = {}) {
    const ticket = options.ticket ?? ++generation;
    let loaded;
    try {
        loaded = await loadAssetObject({ kind: 'bbmodel', modelData, textureData }, {
            wireframe: options.wireframe ?? isWireframe, shading: options.shading ?? isShaded,
            textureFilter: currentTextureFilter(), onTime: () => syncAnimationUI()
        });
        return await installLoaded(loaded, modelData, textureData, ticket);
    } catch (error) {
        if (loaded && loaded !== currentLoadedAsset) loaded.dispose();
        if (ticket !== generation) return false;
        showStageMessage('Não foi possível abrir este modelo', error.message, true);
        ForgeSession.status('error', error.message); return false;
    } finally { if (ticket === generation) finishLoading(); }
}
async function loadGlb(url, options = {}) {
    startLoading('Carregando GLB…');
    const ticket = options.ticket ?? ++generation;
    let loaded;
    try {
        loaded = await loadAssetObject({ kind: 'glb', url }, {
            wireframe: isWireframe, shading: isShaded, textureFilter: currentTextureFilter(), onTime: () => syncAnimationUI()
        });
        const path = new URL(url, location.href).searchParams.get('path') || params.get('glb') || url;
        const name = activeAsset || decodeURIComponent(path.split('/').pop().split('?')[0]);
        return await installLoaded(loaded, { name, elements: [] }, null, ticket);
    } catch (error) {
        if (ticket !== generation) { loaded?.dispose(); return false; }
        showStageMessage('Não foi possível abrir este modelo', error.message, true);
        ForgeSession.status('error', error.message); return false;
    } finally { if (ticket === generation) finishLoading(); }
}

/** Explicit choice (URL or toggle), else the asset's registered filter, else nearest. */
function currentTextureFilter() {
    const asset = catalog?.assets.find(item => item.id === activeAsset);
    return textureFilter || asset?.texture_filter || 'nearest';
}

function setTextureFilter(smooth) {
    textureFilter = smooth ? 'linear' : 'nearest';
    if (currentLoadedAsset) currentLoadedAsset.setTextureFilter(textureFilter);
    else if (parser) parser.setTextureFilter(textureFilter);
    const smoothChk = document.getElementById('chk-smooth');
    if (smoothChk) smoothChk.checked = smooth;
}

function assetFingerprint(asset) { return ForgeSession.assetRevision(asset, activeVariant); }

function variantOptions(asset) {
    const select = document.getElementById('texture-select');
    if (!select || !asset) return;
    if (!asset.variants.some(variant => variant.id === activeVariant)) activeVariant = '';
    select.replaceChildren(new Option('BBModel texture', ''), ...asset.variants.map(variant =>
        new Option(variant.id + (variant.stamp ? '' : ' (not generated)'), variant.id)));
    select.value = activeVariant;
    document.getElementById('variant-panel').hidden = !asset.variants.length || activeFormat !== 'bbmodel';
}

function updateFormatSelector() {
    const formatPanel = document.getElementById('format-panel');
    const formatSelect = document.getElementById('format-select');
    if (!formatPanel || !formatSelect || !catalog) return;

    if (!activeAsset) {
        formatPanel.hidden = true;
        return;
    }

    const matchingGlbs = (catalog.glbs || []).filter(g => g.asset === activeAsset);
    if (matchingGlbs.length === 0) {
        formatPanel.hidden = true;
        return;
    }

    formatPanel.hidden = false;
    formatSelect.replaceChildren(
        new Option('BBModel', 'bbmodel'),
        ...matchingGlbs.map(g => new Option(`GLB (${g.path.split('/').pop()})`, `glb:${g.path}`))
    );
    formatSelect.value = activeFormat;
}

async function switchFormat(value) {
    const navigation = beginNavigation('Abrindo versão…'); activeFormat = value; fingerprint = null;
    updateUrlParams(); try { await refreshCatalog(true); } finally { endNavigation(navigation); } renderExplorerTree();
}
async function selectGlb(relPath, projectId = null) {
    const navigation = beginNavigation('Abrindo GLB…');
    if (projectId) activeProject = projectId;
    activeFormat = `glb:${relPath}`;
    activeAsset = catalog?.id === activeProject ? catalog.glbs?.find(g => g.path === relPath)?.asset || null : null;
    fingerprint = null; showViewportView(); updateUrlParams();
    try { await refreshCatalog(true); } finally { endNavigation(navigation); } renderExplorerTree();
}

function updateUrlParams() {
    const url = new URL(window.location.href);
    if (isGlobalMode && activeProject) {
        url.searchParams.set('project', activeProject);
    } else {
        url.searchParams.delete('project');
    }

    if (activeFormat && activeFormat.startsWith('glb:')) {
        url.searchParams.set('glb', activeFormat.substring(4));
        url.searchParams.delete('asset');
        url.searchParams.delete('variant');
    } else if (activeAsset) {
        url.searchParams.set('asset', activeAsset);
        url.searchParams.delete('glb');
        if (activeVariant) url.searchParams.set('variant', activeVariant);
        else url.searchParams.delete('variant');
    } else {
        url.searchParams.delete('asset'); url.searchParams.delete('glb'); url.searchParams.delete('variant');
    }
    history.replaceState({}, '', url);
}

async function loadAsset(asset) {
    const ticket = ++generation;
    startLoading(`Carregando ${asset.name || asset.id}…`);
    window.__VIEWER_ASSET__ = activeAsset; window.__VIEWER_VARIANT__ = activeVariant;
    const message = document.getElementById('asset-message');
    message.textContent = '';
    const variant = asset.variants.find(item => item.id === activeVariant);
    if (!asset.stamp || (variant && !variant.stamp)) {
        showStageMessage('Modelo ainda não gerado', !asset.stamp ? 'Este asset ainda não possui um BBModel disponível.' : 'A variante selecionada ainda não foi gerada.');
        message.textContent = !asset.stamp ? 'BBModel ainda não gerado.' : 'Variante ainda não gerada.';
        finishLoading(); return false;
    }
    try {
        const request = modelRequests.begin();
        const response = await fetch(asset.model_url, { cache: 'no-store', signal: request.signal });
        if (!response.ok) throw new Error(`BBModel: HTTP ${response.status}`);
        const data = await response.json();
        if (ticket !== generation) return false;
        const override = !activeVariant && activeAsset === params.get('asset') ? params.get('texture') : null;
        const success = await loadModel(data, variant ? `${variant.url}?revision=${encodeURIComponent(JSON.stringify(variant.stamp))}` : override, { ticket });
        if (success && ticket === generation) fingerprint = assetFingerprint(asset);
        return success;
    } catch (error) {
        if (ticket !== generation || error.name === 'AbortError') return false;
        showStageMessage('Não foi possível abrir este modelo', error.message, true);
        message.textContent = error.message; ForgeSession.status('error', error.message); return false;
    } finally { if (ticket === generation) finishLoading(); }
}

// ==========================================================================
// Views Switching: 3D Viewport vs Project Overview Grid
// ==========================================================================

function showViewportView() {
    const viewportView = document.getElementById('viewport-view');
    const overviewView = document.getElementById('project-overview-view');
    if (viewportView) { viewportView.hidden = false; viewportView.style.display = ''; }
    if (overviewView) overviewView.style.display = 'none';
    if (sceneSetup) sceneSetup.onResize();
}

function showStageMessage(title, description, retry = false) {
    const empty = document.getElementById('stage-empty');
    if (!empty) return;
    empty.hidden = false;
    document.getElementById('stage-empty-title').textContent = title;
    document.getElementById('stage-empty-description').textContent = description;
    document.getElementById('stage-retry').hidden = !retry;
    sceneSetup.modelGroup.visible = false;
    inspector?.setTarget(null);
    document.getElementById('clip-list').replaceChildren();
    document.getElementById('clip-count').textContent = '0';
    if (document.getElementById('animation-panel')) document.getElementById('animation-panel').hidden = true;
}
async function refreshProjects() {
    const resp = await fetch('/api/catalog', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`Projetos: HTTP ${resp.status}`);
    const { projects: data } = await resp.json();
    lastIndexRefresh = performance.now();
    const signature = JSON.stringify(data);
    if (signature === projectsSignature) return;
    projectsSignature = signature; projectsList = data;
    renderExplorerTree();
}
function renderExplorerTree() {
    const tree = document.getElementById('explorer-tree');
    const projectSelect = document.getElementById('project-select');
    if (!tree) return;
    const previousProject = projectSelect.value;
    const signature = JSON.stringify(projectsList.map(p => [p.id, p.name]));
    if (projectSelect.dataset.signature !== signature) {
        projectSelect.replaceChildren(...projectsList.map(p => new Option(p.name || p.id, p.id)));
        projectSelect.dataset.signature = signature;
    }
    projectSelect.value = activeProject || previousProject || projectsList[0]?.id || '';
    projectSelect.disabled = !isGlobalMode;
    const project = projectsList.find(p => p.id === activeProject) || projectsList[0];
    const assets = project?.assets || catalog?.assets?.map(a => ({ ...a, has_model: !!a.stamp })) || [];
    const query = searchQuery.toLocaleLowerCase().trim();
    const signatureList = JSON.stringify([activeProject, activeAsset, activeFormat, query, assets, catalog?.id, catalog?.glbs]);
    if (tree.dataset.signature === signatureList) return;
    tree.dataset.signature = signatureList;
    tree.replaceChildren();
    document.getElementById('asset-total-count').textContent = `${assets.length} assets`;
    document.getElementById('project-name').textContent = project?.name || catalog?.name || 'Arquivo local';
    for (const asset of assets) {
        if (query && !`${asset.name || asset.id} ${asset.id}`.toLocaleLowerCase().includes(query)) continue;
        const row = document.createElement('button'); row.type = 'button';
        row.className = 'asset-item'; row.dataset.asset = asset.id; row.dataset.project = project?.id || activeProject || '';
        row.classList.toggle('selected', activeAsset === asset.id && activeFormat === 'bbmodel');
        row.setAttribute('aria-pressed', String(activeAsset === asset.id && activeFormat === 'bbmodel'));
        const icon = document.createElement('span'); icon.className = 'asset-symbol'; icon.textContent = '◇';
        const label = document.createElement('span'); label.className = 'asset-label'; label.textContent = asset.name || asset.id; label.title = asset.name || asset.id;
        const state = document.createElement('span'); state.className = 'asset-kind'; state.textContent = asset.has_model === false ? 'Não gerado' : '3D';
        row.append(icon, label, state); row.onclick = () => selectAsset(asset.id, project?.id || activeProject);
        tree.appendChild(row);
    }
    const glbs = catalog?.id === activeProject ? catalog.glbs || [] : [];
    for (const glb of glbs.filter(g => !g.asset)) {
        if (query && !glb.path.toLocaleLowerCase().includes(query)) continue;
        const row = document.createElement('button'); row.className = 'asset-item'; row.dataset.glb = glb.path;
        row.textContent = glb.path.split('/').pop(); row.title = glb.path;
        row.classList.toggle('selected', activeFormat === `glb:${glb.path}`);
        row.onclick = () => selectGlb(glb.path, activeProject); tree.appendChild(row);
    }
    if (!tree.childElementCount) {
        const empty = document.createElement('p'); empty.className = 'list-empty';
        empty.textContent = query ? 'Nenhum asset encontrado.' : 'Nenhum asset neste projeto.'; tree.appendChild(empty);
    }
    const sandboxList = document.getElementById('sandbox-list'); sandboxList.replaceChildren();
    for (const name of project?.sandboxes || []) {
        const link = document.createElement('a'); link.textContent = name + ' ↗'; link.target = '_blank';
        link.href = `/sandbox/${encodeURIComponent(project.id)}/${encodeURIComponent(name)}/`; sandboxList.appendChild(link);
    }
    document.getElementById('sandbox-section').hidden = !sandboxList.childElementCount;
}
function setInspectorTab(tab, byUser = true) {
    inspectorTab = tab; if (byUser) userChoseInspectorTab = true;
    document.querySelectorAll('[data-inspector-tab]').forEach(button => { const selected = button.dataset.inspectorTab === tab; button.classList.toggle('active', selected); button.setAttribute('aria-selected', String(selected)); });
    document.querySelectorAll('[data-inspector-pane]').forEach(pane => pane.hidden = pane.dataset.inspectorPane !== tab);
}

function handleSearch(val) {
    searchQuery = val;
    const clearBtn = document.getElementById('clear-filter');
    if (clearBtn) clearBtn.style.display = val ? 'block' : 'none';
    renderExplorerTree();
}

function clearSearch() {
    const input = document.getElementById('filter-input');
    if (input) input.value = '';
    handleSearch('');
}

function manualRefresh() {
    refreshAll(true);
}

// ==========================================================================
// Project and Asset Selection
// ==========================================================================

async function selectProject(projectId) {
    const project = projectsList.find(p => p.id === projectId);
    const first = project?.assets.find(a => a.has_model) || project?.assets[0];
    if (first) return selectAsset(first.id, projectId);
    const navigation = beginNavigation('Abrindo projeto…');
    activeProject = projectId; activeAsset = null; activeFormat = 'bbmodel'; fingerprint = null;
    updateUrlParams(); renderExplorerTree();
    try { await refreshCatalog(false); }
    finally { endNavigation(navigation); finishLoading(); }
}
async function selectAsset(assetId, projectId = null) {
    const navigation = beginNavigation('Abrindo modelo…');
    if (projectId) activeProject = projectId;
    activeAsset = assetId; activeVariant = ''; activeFormat = 'bbmodel'; fingerprint = null;
    document.getElementById('badge-name').textContent = projectsList.find(p => p.id === activeProject)?.assets.find(a => a.id === assetId)?.name || assetId;
    document.getElementById('badge-meta').textContent = 'Abrindo modelo…';
    showViewportView(); updateUrlParams(); renderExplorerTree();
    try { await refreshCatalog(true); }
    finally { endNavigation(navigation); }
}
async function selectTextureVariant(id) {
    const navigation = beginNavigation('Abrindo variante…'); activeVariant = id; fingerprint = null;
    updateUrlParams(); try { await refreshCatalog(true); } finally { endNavigation(navigation); }
}
function beginNavigation(label) {
    generation++; catalogSequence++; catalogRequests.cancel(); modelRequests.cancel();
    navigationPending = true; navigationStarted = performance.now(); startLoading(label);
    return ++navigationSerial;
}
function endNavigation(navigation) { if (navigation === navigationSerial) navigationPending = false; }
async function refreshCatalog(force = false) {
    const sequence = ++catalogSequence, intent = generation, project = activeProject;
    const request = catalogRequests.begin();
    try {
        const detail = activeAsset || (isGlobalMode ? '__none__' : '');
        const url = isGlobalMode && project ? `/api/catalog?project=${encodeURIComponent(project)}&asset=${encodeURIComponent(detail)}` : `/api/catalog?asset=${encodeURIComponent(detail)}`;
        const response = await fetch(url, { cache: 'no-store', signal: request.signal });
        if (!response.ok) throw new Error(`Catálogo: HTTP ${response.status}`);
        const next = await response.json();
        if (!request.current() || sequence !== catalogSequence || intent !== generation || project !== activeProject) return;
        if (!force && next.revision === catalog?.revision && fingerprint !== null && window.__FORGE_STATUS__?.state !== 'error') return;
        catalog = next;
        const summary = projectsList.find(p => p.id === catalog.id);
        if (summary) {
            summary.assets = catalog.assets.map(a => ({ id: a.id, name: a.name, has_model: !!a.stamp, variant_count: a.variants.length }));
            summary.sandboxes = catalog.sandboxes;
        } else if (!isGlobalMode && next.projects) projectsList = next.projects;
        document.getElementById('project-name').textContent = catalog.name || catalog.id;
        document.title = `${catalog.name || catalog.id} · Noct Forge`;
        const select = document.getElementById('asset-select');
        if (select) select.replaceChildren(...catalog.assets.map(a => new Option(a.name || a.id, a.id)));
        const glbPath = activeFormat.startsWith('glb:') ? activeFormat.slice(4) : null;
        if (glbPath) {
            const glb = catalog.glbs?.find(g => g.path === glbPath);
            if (!glb) { document.getElementById('asset-message').textContent = 'GLB removido.'; finishLoading(); return; }
            activeAsset = glb.asset || null;
            const revision = JSON.stringify([project, glb.path, glb.stamp]);
            if (force || fingerprint !== revision) {
                const success = await loadGlb(`/api/p/${encodeURIComponent(project || catalog.id)}/glb?path=${encodeURIComponent(glbPath)}&revision=${encodeURIComponent(JSON.stringify(glb.stamp))}`);
                if (success && sequence === catalogSequence && project === activeProject) { fingerprint = revision; if (!initializing) ForgeSession.status('ready', null, fingerprint); }
            }
        } else {
            if (!activeAsset && !mountedKey && !isGlobalMode) activeAsset = catalog.assets[0]?.id || null;
            const asset = catalog.assets.find(a => a.id === activeAsset);
            if (!asset) {
                if (activeAsset) showStageMessage('Asset removido', 'O asset selecionado não está mais disponível neste projeto.');
                else showStageMessage(catalog.glbs?.length ? 'Escolha um arquivo GLB' : 'Escolha um asset', 'Selecione um modelo na biblioteca à esquerda.');
                renderExplorerTree(); finishLoading(); return;
            }
            if (activeVariant && !asset.variants.some(variant => variant.id === activeVariant)) {
                document.getElementById('asset-message').textContent = 'A variante selecionada foi removida.';
                ForgeSession.status('error', 'Variante removida'); finishLoading(); return;
            }
            if (select) select.value = activeAsset;
            variantOptions(asset);
            if (force || fingerprint !== assetFingerprint(asset)) await loadAsset(asset);
        }
        updateFormatSelector(); updateUrlParams();
        document.getElementById('texture-select').disabled = !!glbPath;
        if (glbPath) document.getElementById('variant-panel').hidden = true;
        renderExplorerTree();
    } catch (error) {
        if (error.name === 'AbortError') return;
        if (sequence !== catalogSequence || project !== activeProject) return;
        showStageMessage('Não foi possível abrir este asset', error.message, true);
        document.getElementById('asset-message').textContent = error.message;
        ForgeSession.status('error', error.message); finishLoading();
    }
}

async function refreshAll(force = false) {
    if (isLoading || navigationPending) return;
    const intent = generation;
    try {
        if (isGlobalMode && (force || performance.now() - lastIndexRefresh > 15000)) await refreshProjects();
        if (intent !== generation || isLoading || navigationPending) return;
        await refreshCatalog(force);
    } catch (error) { if (!navigationPending) console.error(error); }
}

// ==========================================================================
// Initialization
// ==========================================================================

async function init() {
    try {
        navigationStarted = performance.now();
        sceneSetup = new SceneSetup(document.getElementById('canvas-container'));
        refPlane = new ReferencePlane(sceneSetup.scene);
        inspector = new ModelInspector({ container: 'outliner-tree', sceneSetup });
        window.inspector = inspector;

        // Connect inspector update to scene render loop
        const origRender = sceneSetup._render.bind(sceneSetup);
        sceneSetup._render = function () {
            origRender();
            if (inspector) inspector.update();
        };

        const defaults = window.__VIEWER_OPTIONS__ || {};
        isWireframe = params.get('wireframe') === '1' || Boolean(defaults.wireframe);
        isShaded = params.get('shading') !== '0' && defaults.shading !== false;
        requestedCamera = params.get('cam_type');
        const requestedFilter = params.get('filter') || defaults.filter;
        textureFilter = ['nearest', 'linear'].includes(requestedFilter) ? requestedFilter : null;
        const wireChk = document.getElementById('chk-wireframe');
        const shadeChk = document.getElementById('chk-shading');
        if (wireChk) wireChk.checked = isWireframe;
        if (shadeChk) shadeChk.checked = isShaded;
        if (params.get('transparent') === '1') {
            sceneSetup.scene.background = null;
            document.body.style.backgroundColor = document.documentElement.style.backgroundColor = 'transparent';
        }

        // Detect global mode
        const healthResp = window.__EMBEDDED_BBMODEL__ ? null : await fetch('/api/health', { cache: 'no-store' }).catch(() => null);
        if (healthResp && healthResp.ok) {
            const healthData = await healthResp.json();
            isGlobalMode = (healthData.mode === 'global');
        }

        const glbUrl = params.get('glb');
        const modelUrl = params.get('model');
        const targetProj = params.get('project');
        const targetAsset = params.get('asset');
        activeAsset = targetAsset; activeVariant = params.get('variant') || '';

        if (isGlobalMode) {
            document.body.classList.add('global-mode');
            const projPanel = document.getElementById('project-panel');
            if (projPanel) projPanel.style.display = 'block';
            const toolbar = document.getElementById('toolbar');
            if (toolbar) toolbar.classList.add('global-mode');
            const expSidebar = document.getElementById('explorer-sidebar');
            if (expSidebar) expSidebar.hidden = false;

            await refreshProjects();

            if (targetProj && projectsList.some(p => p.id === targetProj)) {
                activeProject = targetProj;
            } else if (projectsList.length > 0) {
                // Pick first project
                activeProject = projectsList[0].id;
            }

            if (!targetAsset && glbUrl) activeFormat = `glb:${glbUrl}`;

            if (targetAsset || glbUrl) await refreshCatalog(true);
            else {
                renderExplorerTree();
                showStageMessage('Escolha um asset', 'Selecione um modelo na biblioteca à esquerda para começar a inspeção.');
            }
            showViewportView();

            // Periodic non-blocking background refresh
            if (params.get('capture') !== '1') refreshPoller.refresh();
        } else {
            document.body.classList.remove('global-mode');
            const expSidebar = document.getElementById('explorer-sidebar');
            if (expSidebar) expSidebar.hidden = false;
            if (!window.__EMBEDDED_BBMODEL__ && !modelUrl && !glbUrl) await refreshProjects();
            const toolbar = document.getElementById('toolbar');
            if (toolbar) toolbar.classList.remove('global-mode');

            if (glbUrl) {
                if (sceneSetup) sceneSetup.onResize();
                await loadGlb(glbUrl);
                setView(params.get('orbit') ? `orbit:${params.get('orbit')}` : params.get('view') || defaults.view || 'iso');
            } else if (window.__EMBEDDED_BBMODEL__ || modelUrl) {
                let data = window.__EMBEDDED_BBMODEL__;
                if (!data) {
                    const response = await fetch(modelUrl, {cache: 'no-store'});
                    if (!response.ok) throw new Error(`Model request failed: HTTP ${response.status}`);
                    data = await response.json();
                }
                if (sceneSetup) sceneSetup.onResize();
                await loadModel(data, window.__EMBEDDED_TEXTURE__ || params.get('texture'));
                setView(params.get('orbit') ? `orbit:${params.get('orbit')}` : params.get('view') || defaults.view || 'iso');
            } else {
                // Scoped project mode (single project)
                const projPanel = document.getElementById('project-panel');
                if (projPanel) projPanel.style.display = 'block';
                activeVariant = params.get('variant') || '';
                await refreshCatalog(true);
                showViewportView();
                if (params.get('capture') !== '1') refreshPoller.refresh();
            }
        }

        const reference = window.__EMBEDDED_REFERENCE__ || params.get('reference');
        if (reference) {
            const refPanel = document.getElementById('reference-panel');
            if (refPanel) refPanel.hidden = false;
            await refPlane.load(reference);
            refPlane.setScale(Number(params.get('ref_scale') || 1));
            refPlane.setOffset((params.get('ref_offset') || '0,0,0').split(',').map(Number));
            setRefMode(params.get('ref_mode') || 'backdrop');
            setRefOpacity(Number(params.get('ref_opacity') || .5)*100);
            if (currentBbox) refPlane.update(currentBbox);
        }
    } catch (error) {
        showError(error.message);
    } finally { initializing = false; finishLoading(); }
}

// ==========================================================================
// 3D Viewport Controls (Camera, Shading, Wireframe, Animation)
// ==========================================================================

function setView(view) {
    const targetId = (view === 'right' || view === 'side') ? 'btn-view-side' : `btn-view-${view}`;
    document.querySelectorAll('[id^="btn-view-"]').forEach(button => button.classList.toggle('active', button.id === targetId));
    if (sceneSetup) sceneSetup.setViewPreset(view === 'side' ? 'right' : view, currentBbox);
    if (requestedCamera && sceneSetup) sceneSetup.setCameraType(requestedCamera === 'ortho' ? 'orthographic' : requestedCamera === 'persp' ? 'perspective' : requestedCamera);
    const projBtn = document.getElementById('btn-cam-proj');
    if (projBtn && sceneSetup) projBtn.textContent = sceneSetup.currentCameraType === 'perspective' ? 'Persp' : 'Ortho';
    if (refPlane) refPlane.setView(view);
}

function toggleCameraProjection() {
    if (!sceneSetup) return;
    const next = sceneSetup.currentCameraType === 'perspective' ? 'orthographic' : 'perspective';
    sceneSetup.setCameraType(next);
    const projBtn = document.getElementById('btn-cam-proj');
    if (projBtn) projBtn.textContent = next === 'perspective' ? 'Persp' : 'Ortho';
    if (currentBbox && next === 'orthographic') {
        sceneSetup.fitOrthoToBbox(currentBbox);
    }
}

async function toggleWireframe(value) {
    isWireframe = value;
    if (currentLoadedAsset) {
        currentLoadedAsset.setWireframe(value);
    } else if (currentModelData) {
        const data = currentModelData, texture = currentTextureInput;
        await loadModel(data, texture, {wireframe: value});
        setView(params.get('view') || 'iso');
    }
}

async function toggleShading(value) {
    isShaded = value;
    if (currentLoadedAsset) {
        currentLoadedAsset.setShading(value);
        currentLoadedAsset.setTextureVisible(showTexture);
    } else if (currentModelData) {
        const data = currentModelData, texture = currentTextureInput;
        await loadModel(data, texture, {shading: value});
        setView(params.get('view') || 'iso');
    }
}

function toggleGrid(value) {
    if (sceneSetup?.gridHelper) sceneSetup.gridHelper.visible = sceneSetup.axesHelper.visible = value;
}

function toggleTexture(value) {
    showTexture = value;
    if (currentLoadedAsset) { currentLoadedAsset.setTextureVisible(value); return; }
    if (!parser) return;
    for (const [index, material] of parser.materials) {
        material.map = value ? parser.textureList?.[index] || parser.texture : null;
        material.needsUpdate = true;
    }
}

function toggleBones(value) {
    if (inspector) inspector.setBonesVisible(value);
}

function togglePivots(value) {
    if (inspector) inspector.setPivotsVisible(value);
}

let lastAnimationPaint = 0, lastAnimationState = '';
function syncAnimationUI(force = false) {
    const player = animationPlayer, panel = document.getElementById('animation-panel');
    if (!panel) return;
    const visible = !!sceneSetup?.modelGroup.visible;
    panel.hidden = !player?.names?.length || !visible;
    document.getElementById('clip-count').textContent = String(visible ? player?.names?.length || 0 : 0);
    if (!player || !visible) return;
    const signature = JSON.stringify([player.clip?.name, player.playing, player.speed, player.repeat, player.length]);
    const changed = force || signature !== lastAnimationState;
    const now = performance.now();
    if (!changed && now - lastAnimationPaint < 66) return;
    lastAnimationPaint = now;
    const duration = player.length || 0;
    const scrub = document.getElementById('animation-scrub');
    scrub.max = String(duration); scrub.value = String(player.time);
    document.getElementById('animation-time').textContent = `${player.time.toFixed(2)} s / ${duration.toFixed(2)} s`;
    const input = document.getElementById('animation-position');
    if (document.activeElement !== input) { input.max = duration; input.value = player.time.toFixed(2); }
    if (!changed) return;
    lastAnimationState = signature;
    document.getElementById('active-clip-name').textContent = player.clip?.name || 'Pose base';
    document.getElementById('timeline-end').textContent = `${duration.toFixed(2)} s`;
    const play = document.getElementById('animation-play');
    play.textContent = player.playing ? 'Ⅱ Pausar' : '▶ Reproduzir';
    play.disabled = !player.clip;
    document.getElementById('animation-state').textContent = !player.clip ? 'Pose base' : player.playing ? 'Reproduzindo' : player.time >= duration && duration > 0 ? 'Concluído' : 'Pausado';
    document.querySelectorAll('[data-clip]').forEach(button => { const selected = button.dataset.clip === player.clip?.name; button.classList.toggle('active', selected); button.setAttribute('aria-pressed', String(selected)); });
    document.getElementById('animation-speed').value = String(player.speed || 1);
    document.getElementById('animation-repeat').value = player.repeat || 'original';
}
function renderClipList(query = '') {
    const list = document.getElementById('clip-list');
    if (!list) return;
    list.replaceChildren();
    if (!animationPlayer?.names.length) {
        const empty = document.createElement('p'); empty.className = 'list-empty'; empty.textContent = 'Este modelo não contém animações.'; list.appendChild(empty);
    }
    for (const name of animationPlayer?.names || []) {
        if (!name.toLowerCase().includes(query.toLowerCase())) continue;
        const clip = animationPlayer.animations?.find(clip => clip.name === name);
        const duration = Number(clip?.length ?? clip?.duration ?? 0);
        const row = document.createElement('div'); row.className = 'clip-item';
        const button = document.createElement('button'); button.dataset.clip = name;
        const title = document.createElement('span'); title.textContent = name;
        const length = document.createElement('small'); length.textContent = `${duration.toFixed(2)} s`;
        button.append(title, length); button.title = name; button.onclick = () => selectAnimation(name);
        const play = document.createElement('button'); play.className = 'clip-play'; play.textContent = '▶'; play.title = `Reproduzir ${name}`; play.setAttribute('aria-label', `Reproduzir ${name}`);
        play.onclick = () => { selectAnimation(name); animationPlayer.play(); syncAnimationUI(); };
        row.append(button, play); list.appendChild(row);
    }
    syncAnimationUI(true);
}
function selectAnimation(name) { if (animationPlayer) { const playing = animationPlayer.playing; animationPlayer.select(name); if (playing) animationPlayer.play(); syncAnimationUI(); } }
function toggleAnimation() { if (animationPlayer) { if (animationPlayer.playing) animationPlayer.pause(); else animationPlayer.play(); syncAnimationUI(); } }
function seekAnimation(time) { animationPlayer?.seek(Number(time)); syncAnimationUI(true); }
function animationStart() { animationPlayer?.pause(); seekAnimation(0); }
function animationStep(delta) { animationPlayer?.pause(); seekAnimation((animationPlayer?.time || 0) + delta); }
function animationBase() { animationPlayer?.basePose(); syncAnimationUI(); }
let scrubWasPlaying = false;
window.addEventListener('DOMContentLoaded', () => {
    const scrub = document.getElementById('animation-scrub');
    scrub.addEventListener('pointerdown', () => { scrubWasPlaying = !!animationPlayer?.playing; animationPlayer?.pause(); });
    const end = () => { if (scrubWasPlaying) animationPlayer?.play(); scrubWasPlaying = false; syncAnimationUI(true); };
    window.addEventListener('pointerup', end); scrub.addEventListener('pointercancel', end);
    document.getElementById('animation-speed').onchange = event => { if (animationPlayer) animationPlayer.speed = Number(event.target.value); syncAnimationUI(); };
    document.getElementById('animation-repeat').onchange = event => { if (animationPlayer) animationPlayer.repeat = event.target.value; syncAnimationUI(); };
    document.getElementById('clip-search').oninput = event => renderClipList(event.target.value);
    document.getElementById('properties-toggle').onclick = () => {
        document.body.classList.remove('focus-mode');
        document.body.classList.remove(innerWidth <= 900 ? 'properties-hidden' : 'properties-open');
        document.body.classList.toggle(innerWidth <= 900 ? 'properties-open' : 'properties-hidden');
        document.getElementById('focus-toggle').textContent = 'Foco'; sceneSetup?.onResize();
    };
    document.getElementById('focus-toggle').onclick = () => {
        const focused = document.body.classList.toggle('focus-mode');
        document.getElementById('focus-toggle').textContent = focused ? 'Sair do foco' : 'Foco'; sceneSetup?.onResize();
    };
    new ResizeObserver(() => sceneSetup?.onResize()).observe(document.getElementById('canvas-container'));
    document.getElementById('animation-panel').addEventListener('keydown', event => {
        if (event.target === scrub && ['ArrowLeft', 'ArrowRight'].includes(event.key)) { event.preventDefault(); animationStep(event.key === 'ArrowLeft' ? -0.05 : 0.05); return; }
        if (event.target.matches('input,select,textarea,[contenteditable]')) return;
        if (event.code === 'Space') { event.preventDefault(); toggleAnimation(); }
    });
});
window.addEventListener('pagehide', () => refreshPoller.stop());

function toggleRefVisible(value) {
    if (refPlane) refPlane.setVisible(value);
}

function setRefMode(mode) {
    if (refPlane) refPlane.setMode(mode);
    const backBtn = document.getElementById('btn-ref-backdrop');
    const overBtn = document.getElementById('btn-ref-overlay');
    if (backBtn) backBtn.classList.toggle('active', mode === 'backdrop');
    if (overBtn) overBtn.classList.toggle('active', mode === 'overlay');
}

function setRefOpacity(value) {
    if (refPlane) refPlane.setOpacity(Number(value)/100);
    const rng = document.getElementById('rng-ref-opacity');
    const lbl = document.getElementById('lbl-ref-opacity');
    if (rng) rng.value = String(value);
    if (lbl) lbl.textContent = `${Math.round(value)}%`;
}

function capturePng() {
    if (!sceneSetup) return;
    const anchor = document.createElement('a');
    anchor.href = sceneSetup.captureScreenshot();
    anchor.download = `${currentModelData?.name || 'model'}_render.png`;
    anchor.click();
}

window.addEventListener('DOMContentLoaded', init);

window.addEventListener('DOMContentLoaded', () => document.getElementById('sidebar-toggle')?.addEventListener('click', () => {
    document.body.classList.remove('focus-mode'); document.getElementById('focus-toggle').textContent = 'Foco';
    document.body.classList.remove(innerWidth <= 900 ? 'library-hidden' : 'navigation-open');
    document.body.classList.toggle(innerWidth <= 900 ? 'navigation-open' : 'library-hidden');
    sceneSetup?.onResize();
}));

window.addEventListener('forge:status', event => {
    const label = document.getElementById('connection-status');
    if (label) label.textContent = event.detail.state === 'ready' ? 'Atualizado' : event.detail.state === 'error' ? 'Falha na atualização' : 'Atualizando…';
});

window.addEventListener('DOMContentLoaded', () => { document.getElementById('project-select').onchange = e => selectProject(e.target.value); });

window.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.code !== 'Space' || !animationPlayer?.clip || !sceneSetup?.modelGroup.visible) return;
    if (event.target.matches('input,select,textarea,button,summary,[contenteditable]')) return;
    event.preventDefault(); toggleAnimation();
});
