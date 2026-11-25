/**
 * NoctAssetForge - Global Viewer Application
 * 
 * Auto-discovers assets across projects, renders tree hierarchy,
 * single asset inspector, and multi-asset responsive grid.
 */

import './forge-session.js';
declare const ForgeSession: any;

interface AssetFileMeta {
  project: string;
  subpath: string;
  filename: string;
  format: string;
  size: number;
  mtime: number;
  url: string;
}

interface ProjectMeta {
  name: string;
  hasStyle: boolean;
  sandboxes: string[];
  hasProjectMd: boolean;
  assetCount: number;
  sourceCount: number;
}

type Selection =
  | { type: 'asset'; asset: AssetFileMeta }
  | { type: 'folder'; project: string; folderPath: string }
  | { type: 'project'; project: string };

let assets: AssetFileMeta[] = [];
let projects: ProjectMeta[] = [];
let currentSelection: Selection | null = null;
let searchQuery = '';
let bgMode: 'check' | 'dark' | 'light' | 'black' = 'check';
let zoomLevel = 1;
let isFitMode = true;
let filterMode: 'auto' | 'sharp' | 'blur' = 'auto';
let blurIntensity = 1.0;
let cardDensity: 'compact' | 'normal' | 'large' = 'normal';
let inspectorCleanup: (() => void) | null = null;
const collapsedNodes = new Set<string>();
let allFoldersCollapsed = false;

// DOM elements
const treeContainer = document.getElementById('tree-container')!;
const contentArea = document.getElementById('content-area')!;
const filterInput = document.getElementById('filter-input') as HTMLInputElement;
const clearFilterBtn = document.getElementById('clear-filter')!;
const refreshBtn = document.getElementById('refresh-btn')!;
const toggleAllBtn = document.getElementById('toggle-all-btn');
const assetTotalCount = document.getElementById('asset-total-count')!;
const previewLinksContainer = document.getElementById('preview-links')!;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

let catalogRevision = '';
const requests = new ForgeSession.LatestRequest();
let replaceInspectorImage: ((asset: AssetFileMeta) => Promise<void>) | null = null;
function selectionKey(selection: Selection | null): string {
  return selection?.type === 'asset' ? `${selection.asset.project}/${selection.asset.subpath}` : '';
}
function saveSession() {
  try { sessionStorage.setItem('forge-2d-session', JSON.stringify({ selection: currentSelection, searchQuery, bgMode, zoomLevel, isFitMode, filterMode, cardDensity, collapsed: [...collapsedNodes] })); } catch {}
}
try {
  const saved = JSON.parse(sessionStorage.getItem('forge-2d-session') || 'null');
  if (saved) {
    currentSelection = saved.selection; searchQuery = saved.searchQuery || ''; bgMode = saved.bgMode;
    zoomLevel = saved.zoomLevel; isFitMode = saved.isFitMode; filterMode = saved.filterMode; cardDensity = saved.cardDensity;
    for (const key of saved.collapsed || []) collapsedNodes.add(key);
    filterInput.value = searchQuery;
  }
} catch {}
window.addEventListener('pagehide', saveSession);
async function fetchCatalog() {
  const ticket = requests.begin();
  try {
    const response = await fetch('/api/catalog', { cache: 'no-store', signal: ticket.signal });
    if (!response.ok) throw new Error(`Catálogo: HTTP ${response.status}`);
    const data = await response.json();
    if (!ticket.current()) return;
    if (catalogRevision === data.revision) return;
    const previous = currentSelection?.type === 'asset' ? currentSelection.asset : null;
    assets = data.assets; projects = data.projects;
    if (previous) {
      const updated = assets.find(a => a.project === previous.project && a.subpath === previous.subpath);
      if (!updated) {
        inspectorCleanup?.(); inspectorCleanup = null; replaceInspectorImage = null;
        contentArea.replaceChildren(Object.assign(document.createElement('p'), { className: 'removed-message', textContent: 'Asset removido. Selecione outro asset na biblioteca.' }));
      } else {
        currentSelection = { type: 'asset', asset: updated };
        if (replaceInspectorImage && selectionKey(currentSelection) === `${previous.project}/${previous.subpath}`) {
          await replaceInspectorImage(updated);
        } else renderContent();
      }
    } else renderContent();
    if (!ticket.current()) return;
    catalogRevision = data.revision;
    assetTotalCount.textContent = `${assets.length} assets`;
    renderPreviewLinks(); renderTree(); saveSession();
    document.getElementById('connection-status')!.textContent = 'Atualizado';
    ForgeSession.status('ready', null, catalogRevision);
  } catch (error: any) {
    if (error.name === 'AbortError') return;
    document.getElementById('connection-status')!.textContent = 'Falha na atualização · tentar novamente';
    ForgeSession.status('error', error.message);
    console.error(error);
  }
}
function renderPreviewLinks() {
  previewLinksContainer.replaceChildren();
  for (const project of projects) for (const sandbox of project.sandboxes || []) {
    const link = document.createElement('a');
    link.href = `/projects/${encodeURIComponent(project.name)}/sandboxes/${encodeURIComponent(sandbox)}/`;
    link.textContent = `${project.name} / ${sandbox} ↗`; link.target = '_blank'; link.className = 'preview-link-btn';
    previewLinksContainer.appendChild(link);
  }
  document.getElementById('sandbox-links')?.replaceChildren(...Array.from(previewLinksContainer.children).map(node => node.cloneNode(true)));
}

// Tree Node Structure
interface TreeNode {
  name: string;
  fullSubpath: string;
  project: string;
  isFolder: boolean;
  asset?: AssetFileMeta;
  children: Map<string, TreeNode>;
}

function buildTree(): Map<string, TreeNode> {
  const root = new Map<string, TreeNode>();

  // Ensure all projects exist in root
  for (const p of projects) {
    root.set(p.name, {
      name: p.name,
      fullSubpath: '',
      project: p.name,
      isFolder: true,
      children: new Map(),
    });
  }

  // Insert assets into tree
  for (const asset of assets) {
    // Apply search query filter if active
    if (searchQuery) {
      const target = `${asset.project}/${asset.subpath}`.toLowerCase();
      if (!target.includes(searchQuery.toLowerCase())) {
        continue;
      }
    }

    let projectNode = root.get(asset.project);
    if (!projectNode) {
      projectNode = {
        name: asset.project,
        fullSubpath: '',
        project: asset.project,
        isFolder: true,
        children: new Map(),
      };
      root.set(asset.project, projectNode);
    }

    const parts = asset.subpath.replace(/\\/g, '/').split('/');
    let currentNode = projectNode;

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      const subpathSoFar = parts.slice(0, i + 1).join('/');

      if (isLast) {
        // File leaf node
        currentNode.children.set(part, {
          name: part,
          fullSubpath: subpathSoFar,
          project: asset.project,
          isFolder: false,
          asset,
          children: new Map(),
        });
      } else {
        // Folder node
        let folderNode = currentNode.children.get(part);
        if (!folderNode) {
          folderNode = {
            name: part,
            fullSubpath: subpathSoFar,
            project: asset.project,
            isFolder: true,
            children: new Map(),
          };
          currentNode.children.set(part, folderNode);
        }
        currentNode = folderNode;
      }
    }
  }

  return root;
}

function renderTree() {
  const tree = buildTree();
  treeContainer.innerHTML = '';

  if (tree.size === 0) {
    treeContainer.innerHTML = `<div class="tree-loading">No projects or assets found.</div>`;
    return;
  }

  for (const [projectName, projNode] of tree.entries()) {
    const projElem = createTreeNodeElement(projNode, true);
    treeContainer.appendChild(projElem);
  }
}

function getNodeKey(node: TreeNode, isProjectRoot: boolean): string {
  if (isProjectRoot) {
    return `proj:${node.name}`;
  }
  return `folder:${node.project}:${node.fullSubpath}`;
}

function countDescendantAssets(node: TreeNode): number {
  if (!node.isFolder) return 1;
  let count = 0;
  for (const child of node.children.values()) {
    count += countDescendantAssets(child);
  }
  return count;
}

function createTreeNodeElement(node: TreeNode, isProjectRoot = false): HTMLElement {
  const container = document.createElement('div');
  container.className = 'tree-node';

  const row = document.createElement('div');
  row.className = 'tree-row';

  // Highlight if selected
  if (currentSelection) {
    if (currentSelection.type === 'asset' && !node.isFolder && currentSelection.asset.project === node.asset?.project && currentSelection.asset.subpath === node.asset?.subpath) {
      row.classList.add('selected');
    } else if (
      currentSelection.type === 'folder' &&
      node.isFolder &&
      !isProjectRoot &&
      currentSelection.project === node.project &&
      currentSelection.folderPath === node.fullSubpath
    ) {
      row.classList.add('selected');
    } else if (
      currentSelection.type === 'project' &&
      isProjectRoot &&
      currentSelection.project === node.name
    ) {
      row.classList.add('selected');
    }
  }

  const hasChildren = node.isFolder && node.children.size > 0;
  const nodeKey = getNodeKey(node, isProjectRoot);
  // If search query is active, auto-expand so user sees matched assets immediately
  const isCollapsed = searchQuery ? false : collapsedNodes.has(nodeKey);

  // Dropdown chevron button for folders / projects with children
  if (hasChildren) {
    const toggleBtn = document.createElement('button');
    toggleBtn.className = `tree-toggle ${isCollapsed ? 'collapsed' : ''}`;
    toggleBtn.setAttribute('title', isCollapsed ? 'Expandir pasta' : 'Recolher pasta');
    toggleBtn.setAttribute('type', 'button');
    toggleBtn.innerHTML = `
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="6 9 12 15 18 9"></polyline>
      </svg>
    `;

    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (collapsedNodes.has(nodeKey)) {
        collapsedNodes.delete(nodeKey);
      } else {
        collapsedNodes.add(nodeKey);
      }
      renderTree();
    });

    row.appendChild(toggleBtn);
  } else {
    const spacer = document.createElement('div');
    spacer.className = 'tree-toggle-spacer';
    row.appendChild(spacer);
  }

  const icon = document.createElement('div');
  icon.className = 'tree-icon';

  if (isProjectRoot) {
    icon.textContent = '▦';
  } else if (node.isFolder) {
    icon.textContent = isCollapsed ? '□' : '□';
  } else {
    icon.textContent = node.asset?.format === 'jpeg' ? '◇' : '◇';
  }

  const label = document.createElement('span');
  label.className = 'tree-label';
  label.textContent = node.name;

  row.appendChild(icon);
  row.appendChild(label);

  if (node.isFolder) {
    const totalAssets = countDescendantAssets(node);
    const badge = document.createElement('span');
    badge.className = 'tree-badge';
    badge.textContent = String(totalAssets);
    row.appendChild(badge);
  }

  container.appendChild(row);

  let childrenContainer: HTMLElement | null = null;
  if (hasChildren) {
    childrenContainer = document.createElement('div');
    childrenContainer.className = `tree-children ${isCollapsed ? 'collapsed' : ''}`;

    for (const childNode of node.children.values()) {
      childrenContainer.appendChild(createTreeNodeElement(childNode, false));
    }
    container.appendChild(childrenContainer);

    // Double-click row toggles minimize / maximize
    row.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      if (collapsedNodes.has(nodeKey)) {
        collapsedNodes.delete(nodeKey);
      } else {
        collapsedNodes.add(nodeKey);
      }
      renderTree();
    });
  }

  row.addEventListener('click', (e) => {
    e.stopPropagation();

    if (!node.isFolder && node.asset) {
      currentSelection = { type: 'asset', asset: node.asset };
      renderTree();
      renderContent();
    } else if (isProjectRoot) {
      currentSelection = { type: 'project', project: node.name };
      // Auto-expand on click if currently collapsed so user sees contents
      if (collapsedNodes.has(nodeKey)) {
        collapsedNodes.delete(nodeKey);
      }
      renderTree();
      renderContent();
    } else {
      currentSelection = { type: 'folder', project: node.project, folderPath: node.fullSubpath };
      if (collapsedNodes.has(nodeKey)) {
        collapsedNodes.delete(nodeKey);
      }
      renderTree();
      renderContent();
    }
  });

  return container;
}

function renderContent() {
  if (inspectorCleanup) {
    inspectorCleanup();
    inspectorCleanup = null;
  }
  replaceInspectorImage = null;
  contentArea.innerHTML = '';

  // If no selection, select first available asset or first project
  if (!currentSelection) {
    if (assets.length > 0) {
      currentSelection = { type: 'asset', asset: assets[0] };
    } else if (projects.length > 0) {
      currentSelection = { type: 'project', project: projects[0].name };
    }
  }

  if (!currentSelection || assets.length === 0) {
    renderEmptyState();
    return;
  }

  if (currentSelection.type === 'asset') {
    renderSingleInspector(currentSelection.asset);
  } else if (currentSelection.type === 'folder') {
    const folderAssets = assets.filter(
      (a) =>
        a.project === (currentSelection as any).project &&
        a.subpath.startsWith((currentSelection as any).folderPath)
    );
    renderGrid(`${(currentSelection as any).project}/${(currentSelection as any).folderPath}`, folderAssets);
  } else if (currentSelection.type === 'project') {
    const projAssets = assets.filter((a) => a.project === (currentSelection as any).project);
    renderGrid(`Project: ${(currentSelection as any).project}`, projAssets);
  }
}

function renderEmptyState() {
  contentArea.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">🎨</div>
      <h2 class="empty-title">No Assets Generated Yet</h2>
      <p class="empty-desc">
        Visual assets generated by coding agents will appear here automatically.
        You can export your project assets at any time using the command line:
      </p>
      <div class="code-snippet">npm run export -- &lt;project&gt;</div>
    </div>
  `;
}

function renderGrid(title: string, list: AssetFileMeta[]) {
  const container = document.createElement('div');
  container.className = 'grid-view-container';

  container.innerHTML = `
    <div class="grid-header">
      <div class="grid-title-group">
        <h2 class="grid-title">${title}</h2>
        <span class="grid-count">${list.length} asset${list.length === 1 ? '' : 's'}</span>
      </div>
      <div class="grid-density-group">
        <span class="density-label">Visualização:</span>
        <button class="density-btn ${cardDensity === 'compact' ? 'active' : ''}" data-density="compact" title="Grade compacta (miniaturas menores)">Pequeno</button>
        <button class="density-btn ${cardDensity === 'normal' ? 'active' : ''}" data-density="normal" title="Grade padrão">Médio</button>
        <button class="density-btn ${cardDensity === 'large' ? 'active' : ''}" data-density="large" title="Grade ampla (miniaturas maiores)">Grande</button>
      </div>
    </div>
    <div class="grid-cards density-${cardDensity}" id="grid-cards"></div>
  `;

  container.querySelectorAll('.density-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      cardDensity = btn.getAttribute('data-density') as any;
      renderContent();
    });
  });

  const cardsContainer = container.querySelector('#grid-cards')!;

  if (list.length === 0) {
    cardsContainer.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1;">
        <p class="empty-desc">No assets found in this folder. Export them using <code>npm run export</code>.</p>
      </div>
    `;
  } else {
    for (const item of list) {
      const card = document.createElement('div');
      card.className = 'asset-card';

      card.innerHTML = `
        <div class="card-thumbnail-box checkerboard">
          <img class="card-img" src="${item.url}?t=${item.mtime}" alt="${item.filename}" loading="lazy" />
        </div>
        <div class="card-info">
          <div class="card-filename" title="${item.filename}">${item.filename}</div>
          <div class="card-meta">
            <span>${item.format.toUpperCase()}</span>
            <span>${formatBytes(item.size)}</span>
          </div>
        </div>
      `;

      card.addEventListener('click', () => {
        currentSelection = { type: 'asset', asset: item };
        renderTree();
        renderContent();
      });

      cardsContainer.appendChild(card);
    }
  }

  contentArea.appendChild(container);
}

function renderSingleInspector(asset: AssetFileMeta) {
  const container = document.createElement('div');
  container.className = 'inspector-container';

  const folderPath = asset.subpath.split('/').slice(0, -1).join('/');
  const cliSubpath = asset.subpath.replace(/\.[^/.]+$/, '');

  container.innerHTML = `
    <div class="inspector-toolbar">
      <div class="inspector-breadcrumbs">
        <span class="crumb-project">${asset.project}</span>
        <span class="crumb-separator">/</span>
        ${folderPath ? `<span class="crumb-folder">${folderPath}</span><span class="crumb-separator">/</span>` : ''}
        <span class="crumb-file">${asset.filename}</span>
        <span class="meta-pill cyan" id="dim-pill">Detecting...</span>
        <span class="meta-pill">${formatBytes(asset.size)}</span>
        <span class="meta-pill">${asset.format.toUpperCase()}</span>
      </div>

      <div class="inspector-controls">
        <!-- Background Switcher -->
        <div class="bg-switcher" title="Plano de Fundo (Transparência)">
          <button class="bg-btn bg-check ${bgMode === 'check' ? 'active' : ''}" data-bg="check" title="Quadriculado (Transparência)"></button>
          <button class="bg-btn bg-dark ${bgMode === 'dark' ? 'active' : ''}" data-bg="dark" title="Ardósia Escura"></button>
          <button class="bg-btn bg-light ${bgMode === 'light' ? 'active' : ''}" data-bg="light" title="Branco Puro"></button>
          <button class="bg-btn bg-black ${bgMode === 'black' ? 'active' : ''}" data-bg="black" title="Preto Puro"></button>
        </div>

        <div class="control-separator"></div>

        <!-- Filter Mode Controls (Auto / Nítido / Blur) -->
        <div class="filter-group">
          <span class="control-label">Filtro:</span>
          <button class="filter-btn ${filterMode === 'auto' ? 'active' : ''}" data-mode="auto" title="Auto: Desfoque suave ao afastar (< 100%) e nitidez pixel-perfect ao aproximar (>= 100%)">Auto</button>
          <button class="filter-btn ${filterMode === 'sharp' ? 'active' : ''}" data-mode="sharp" title="Nítido: Sempre pixel-perfect sem blur">Nítido</button>
          <button class="filter-btn ${filterMode === 'blur' ? 'active' : ''}" data-mode="blur" title="Blur: Força filtro de suavização/borrão">Blur</button>
          <span class="filter-badge sharp" id="filter-badge" title="Clique para alternar o modo de filtragem">
            <span class="filter-dot" id="filter-dot"></span>
            <span id="filter-badge-text">Nítido</span>
          </span>
        </div>

        <div class="control-separator"></div>

        <!-- Zoom Controls with Step, Slider & Presets -->
        <div class="zoom-group">
          <button class="zoom-step-btn" id="zoom-out-btn" title="Afastar Zoom (Zoom Out) [-]">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>
          <input type="range" class="zoom-slider" id="zoom-slider" min="10" max="800" step="5" value="${Math.round(zoomLevel * 100)}" title="Controle deslizante de zoom (10% a 800%)" />
          <button class="zoom-step-btn" id="zoom-in-btn" title="Aproximar Zoom (Zoom In) [+]">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="12" y1="5" x2="12" y2="19"></line>
              <line x1="5" y1="12" x2="19" y2="12"></line>
            </svg>
          </button>

          <div class="zoom-presets">
            <button class="zoom-btn ${!isFitMode && Math.round(zoomLevel * 100) === 25 ? 'active' : ''}" data-zoom="0.25" title="Afastar 25%">25%</button>
            <button class="zoom-btn ${!isFitMode && Math.round(zoomLevel * 100) === 50 ? 'active' : ''}" data-zoom="0.5" title="Afastar 50%">50%</button>
            <button class="zoom-btn ${isFitMode ? 'active' : ''}" id="zoom-fit" title="Ajustar à tela">Ajustar</button>
            <button class="zoom-btn ${!isFitMode && Math.round(zoomLevel * 100) === 100 ? 'active' : ''}" data-zoom="1.0" title="Tamanho original 100%">100%</button>
            <button class="zoom-btn ${!isFitMode && Math.round(zoomLevel * 100) === 200 ? 'active' : ''}" data-zoom="2.0" title="Aproximar 200%">200%</button>
            <button class="zoom-btn ${!isFitMode && Math.round(zoomLevel * 100) === 400 ? 'active' : ''}" data-zoom="4.0" title="Aproximar 400%">400%</button>
            <button class="zoom-btn" id="pan-reset" title="Centralizar visualização e resetar deslocamento (R)">⌖ Centro</button>
          </div>
          <span class="zoom-val" id="zoom-val">${isFitMode ? 'Fit' : `${Math.round(zoomLevel * 100)}%`}</span>
        </div>
      </div>
    </div>

    <!-- Stage Canvas -->
    <div class="stage-container" id="stage-container" title="Dica: Arraste para mover, use a roda do mouse para zoom">
      <div class="stage-canvas-box bg-mode-${bgMode}" id="stage-box">
        <img class="stage-image" id="stage-img" src="${asset.url}?t=${asset.mtime}" alt="${asset.filename}" draggable="false" />
      </div>
    </div>

    <!-- Footer Toolbar -->
    <div class="inspector-footer">
      <div class="cli-hint">
        <span>Exportar:</span>
        <code class="cli-code">npm run export -- ${asset.project} ${cliSubpath}</code>
      </div>
      <div class="keyboard-hints">
        <span class="hint-item"><kbd>Scroll</kbd> Zoom</span>
        <span class="hint-item"><kbd>Arrastar</kbd> Pan</span>
        <span class="hint-item"><kbd>R</kbd> Centralizar</span>
        <span class="hint-item"><kbd>2x Clique</kbd> 100% / Fit</span>
        <span class="hint-item"><kbd>B</kbd> Alternar Filtro</span>
      </div>
      <div class="footer-actions">
        <button class="action-btn" id="copy-path-btn">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
          </svg>
          Copiar caminho
        </button>
      </div>
    </div>
  `;

  contentArea.appendChild(container);

  const stageImg = container.querySelector('#stage-img') as HTMLImageElement;
  const stageBox = container.querySelector('#stage-box') as HTMLElement;
  const stageContainer = container.querySelector('#stage-container') as HTMLElement;
  const dimPill = container.querySelector('#dim-pill')!;
  const zoomVal = container.querySelector('#zoom-val')!;
  const zoomSlider = container.querySelector('#zoom-slider') as HTMLInputElement;
  const filterBadge = container.querySelector('#filter-badge') as HTMLElement;
  const filterDot = container.querySelector('#filter-dot') as HTMLElement;
  const filterBadgeText = container.querySelector('#filter-badge-text') as HTMLElement;

  function applyZoomAndFilter() {
    if (!stageImg) return;
    const nw = stageImg.naturalWidth || 128;
    const nh = stageImg.naturalHeight || 128;

    let effectiveScale = zoomLevel;

    if (isFitMode) {
      stageImg.style.maxWidth = '100%';
      stageImg.style.maxHeight = '75vh';
      stageImg.style.width = 'auto';
      stageImg.style.height = 'auto';
      stageImg.style.transform = 'none';

      const rect = stageImg.getBoundingClientRect();
      if (rect.width > 0 && nw > 0) {
        effectiveScale = rect.width / nw;
      }
      zoomVal.textContent = `Fit (${Math.round(effectiveScale * 100)}%)`;
      if (zoomSlider && document.activeElement !== zoomSlider) {
        zoomSlider.value = String(Math.round(effectiveScale * 100));
      }
    } else {
      stageImg.style.maxWidth = 'none';
      stageImg.style.maxHeight = 'none';
      const targetW = Math.round(nw * zoomLevel);
      const targetH = Math.round(nh * zoomLevel);
      stageImg.style.width = `${targetW}px`;
      stageImg.style.height = `${targetH}px`;
      zoomVal.textContent = `${Math.round(zoomLevel * 100)}%`;
      if (zoomSlider && document.activeElement !== zoomSlider) {
        zoomSlider.value = String(Math.round(zoomLevel * 100));
      }
      effectiveScale = zoomLevel;
    }

    // Determine visual filter behavior
    let isSharp = false;
    let blurAmount = 0;

    if (filterMode === 'sharp') {
      isSharp = true;
      blurAmount = 0;
    } else if (filterMode === 'blur') {
      isSharp = false;
      blurAmount = Math.max(1.0, 1.2 * blurIntensity);
    } else {
      // AUTO MODE:
      // Clean, unadulterated rendering: no artificial CSS blur!
      // Uses smooth interpolation (imageRendering: 'auto') when scaled or zoomed,
      // and pixel-perfect rendering only when the user explicitly requests Nítido.
      isSharp = false;
      blurAmount = 0;
    }

    if (filterMode === 'sharp') {
      stageImg.style.filter = 'none';
      stageImg.style.imageRendering = 'pixelated';
      filterBadge.className = 'filter-badge sharp';
      filterDot.className = 'filter-dot sharp';
      filterBadgeText.textContent = `Nítido ${effectiveScale > 1.05 ? `(${Math.round(effectiveScale * 100)}%)` : ''}`;
      filterBadge.title = 'Modo Nítido ativo: Renderização pixel-perfect sem interpolação';
    } else if (filterMode === 'blur' && blurAmount > 0.05) {
      stageImg.style.filter = `blur(${blurAmount.toFixed(1)}px)`;
      stageImg.style.imageRendering = 'auto';
      filterBadge.className = 'filter-badge blur';
      filterDot.className = 'filter-dot blur';
      filterBadgeText.textContent = `Blur: ${blurAmount.toFixed(1)}px`;
      filterBadge.title = `Filtro de Borrão ativo: ${blurAmount.toFixed(1)}px`;
    } else {
      stageImg.style.filter = 'none';
      stageImg.style.imageRendering = effectiveScale > 3.0 ? 'pixelated' : 'auto';
      filterBadge.className = 'filter-badge auto';
      filterDot.className = 'filter-dot auto';
      filterBadgeText.textContent = `Auto (${Math.round(effectiveScale * 100)}%)`;
      filterBadge.title = 'Modo Auto: Renderização nativa limpa sem desfoque artificial';
    }
  }

  function setZoom(newZoom: number, fit = false) {
    isFitMode = fit;
    if (!fit) {
      zoomLevel = Math.max(0.1, Math.min(8.0, newZoom));
    }
    applyZoomAndFilter();
    updateControls();
  }

  function updateControls() {
    container.querySelector('#zoom-fit')?.classList.toggle('active', isFitMode);
    container.querySelectorAll('.zoom-presets .zoom-btn[data-zoom]').forEach((btn) => {
      const z = Number(btn.getAttribute('data-zoom'));
      const isCurrent = !isFitMode && Math.abs(zoomLevel - z) < 0.03;
      btn.classList.toggle('active', isCurrent);
    });
    container.querySelectorAll('.filter-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.getAttribute('data-mode') === filterMode);
    });
  }

  // Measure native dimensions on image load
  stageImg.onload = () => {
    const nw = stageImg.naturalWidth;
    const nh = stageImg.naturalHeight;
    dimPill.textContent = `${nw} × ${nh} px`;
    applyZoomAndFilter();
    updateControls();
  };

  // Background buttons
  container.querySelectorAll('.bg-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.bg-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      bgMode = btn.getAttribute('data-bg') as any;
      stageBox.className = `stage-canvas-box bg-mode-${bgMode}`;
    });
  });

  // Filter mode buttons
  container.querySelectorAll('.filter-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      filterMode = btn.getAttribute('data-mode') as any;
      updateControls();
      applyZoomAndFilter();
    });
  });

  // Click on badge cycles filter
  filterBadge.addEventListener('click', () => {
    if (filterMode === 'auto') filterMode = 'sharp';
    else if (filterMode === 'sharp') filterMode = 'blur';
    else filterMode = 'auto';
    updateControls();
    applyZoomAndFilter();
  });

  // Zoom slider
  zoomSlider.addEventListener('input', () => {
    const val = Number(zoomSlider.value);
    setZoom(val / 100, false);
  });

  // Zoom Step [-] and [+]
  const stops = [0.10, 0.25, 0.35, 0.50, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0];

  container.querySelector('#zoom-out-btn')?.addEventListener('click', () => {
    const current = isFitMode ? (stageImg.clientWidth / (stageImg.naturalWidth || 1)) : zoomLevel;
    const nextSmaller = stops.slice().reverse().find((s) => s < current - 0.04);
    const target = nextSmaller !== undefined ? nextSmaller : Math.max(0.1, current * 0.8);
    setZoom(target, false);
  });

  container.querySelector('#zoom-in-btn')?.addEventListener('click', () => {
    const current = isFitMode ? (stageImg.clientWidth / (stageImg.naturalWidth || 1)) : zoomLevel;
    const nextLarger = stops.find((s) => s > current + 0.04);
    const target = nextLarger !== undefined ? nextLarger : Math.min(8.0, current * 1.25);
    setZoom(target, false);
  });

  // Preset buttons
  container.querySelector('#zoom-fit')?.addEventListener('click', () => {
    panX = 0;
    panY = 0;
    updateStageTransform();
    setZoom(1.0, true);
  });

  container.querySelector('#pan-reset')?.addEventListener('click', () => {
    panX = 0;
    panY = 0;
    updateStageTransform();
  });

  container.querySelectorAll('.zoom-presets .zoom-btn[data-zoom]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const z = Number(btn.getAttribute('data-zoom'));
      setZoom(z, false);
    });
  });

  // Mouse wheel zoom
  stageContainer.addEventListener('wheel', (e) => {
    e.preventDefault();
    const current = isFitMode ? (stageImg.clientWidth / (stageImg.naturalWidth || 1)) : zoomLevel;
    const deltaFactor = e.deltaY < 0 ? 1.15 : 0.87;
    setZoom(current * deltaFactor, false);
  }, { passive: false });

  // Double-click toggle
  stageContainer.addEventListener('dblclick', (e) => {
    e.preventDefault();
    panX = 0;
    panY = 0;
    updateStageTransform();
    if (isFitMode) {
      setZoom(1.0, false);
    } else if (Math.abs(zoomLevel - 1.0) < 0.05) {
      setZoom(1.0, true);
    } else {
      setZoom(1.0, false);
    }
  });

  // Drag to pan via CSS transform (translate)
  let isMouseDown = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let panX = 0;
  let panY = 0;

  function updateStageTransform() {
    if (stageBox) {
      stageBox.style.transform = `translate(${panX}px, ${panY}px)`;
    }
  }

  // Prevent browser native image ghost drag
  stageContainer.addEventListener('dragstart', (e) => {
    e.preventDefault();
    return false;
  });

  stageContainer.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    isMouseDown = true;
    stageContainer.classList.add('grabbing');
    dragStartX = e.clientX - panX;
    dragStartY = e.clientY - panY;
  });

  const onMouseMove = (e: MouseEvent) => {
    if (!isMouseDown) return;
    if (!container.isConnected) {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      return;
    }
    e.preventDefault();
    panX = Math.round(e.clientX - dragStartX);
    panY = Math.round(e.clientY - dragStartY);
    updateStageTransform();
  };

  const onMouseUp = () => {
    if (isMouseDown) {
      isMouseDown = false;
      stageContainer.classList.remove('grabbing');
    }
  };

  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);

  // Keyboard shortcuts - strictly guarded against typing in any input/textarea/select
  const onKeyDown = (e: KeyboardEvent) => {
    if (!container.isConnected) {
      window.removeEventListener('keydown', onKeyDown);
      return;
    }
    const activeTag = document.activeElement?.tagName?.toLowerCase();
    if (activeTag === 'input' || activeTag === 'textarea' || activeTag === 'select') return;
    if (currentSelection?.type !== 'asset') return;

    if (e.key === '+' || e.key === '=') {
      e.preventDefault();
      (container.querySelector('#zoom-in-btn') as HTMLElement)?.click();
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault();
      (container.querySelector('#zoom-out-btn') as HTMLElement)?.click();
    } else if (e.key === '0') {
      e.preventDefault();
      setZoom(1.0, false);
    } else if (e.key.toLowerCase() === 'f') {
      e.preventDefault();
      panX = 0;
      panY = 0;
      updateStageTransform();
      setZoom(1.0, true);
    } else if (e.key.toLowerCase() === 'r') {
      e.preventDefault();
      panX = 0;
      panY = 0;
      updateStageTransform();
    } else if (e.key.toLowerCase() === 'b') {
      e.preventDefault();
      filterMode = filterMode === 'auto' ? 'sharp' : filterMode === 'sharp' ? 'blur' : 'auto';
      updateControls();
      applyZoomAndFilter();
    }
  };

  window.addEventListener('keydown', onKeyDown);

  // Register teardown so switching assets or views completely removes window listeners
  inspectorCleanup = () => {
    window.removeEventListener('mousemove', onMouseMove);
    window.removeEventListener('mouseup', onMouseUp);
    window.removeEventListener('keydown', onKeyDown);
  };

  replaceInspectorImage = async (updated) => {
    const key = selectionKey(currentSelection);
    if (stageImg.src === new URL(`${updated.url}?t=${updated.mtime}`, location.href).href) return;
    const image = new Image(); image.src = `${updated.url}?t=${updated.mtime}`;
    await image.decode();
    if (!container.isConnected || key !== selectionKey(currentSelection) || currentSelection?.type !== 'asset' || currentSelection.asset.mtime !== updated.mtime) return;
    stageImg.src = image.src;
    dimPill.textContent = `${image.naturalWidth} × ${image.naturalHeight}`;
    const metadata = container.querySelectorAll('.meta-pill');
    if (metadata[1]) metadata[1].textContent = formatBytes(updated.size);
    applyZoomAndFilter();
  };
  const presets = document.createElement('select'); presets.setAttribute('aria-label', 'Presets de zoom');
  for (const percent of [25, 50, 100, 200, 400, 800]) presets.add(new Option(`${percent}%`, String(percent / 100)));
  presets.value = String(zoomLevel); presets.onchange = () => setZoom(Number(presets.value), false);
  container.querySelector('.zoom-group')?.appendChild(presets);
  // Copy path button
  container.querySelector('#copy-path-btn')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget as HTMLElement;
    await navigator.clipboard.writeText(`projects/${asset.project}/assets/${asset.subpath}`);
    const originalText = btn.innerHTML;
    btn.innerHTML = `✔ Copiado`;
    setTimeout(() => {
      btn.innerHTML = originalText;
    }, 1500);
  });
}

// Event Listeners
filterInput.addEventListener('input', () => {
  searchQuery = filterInput.value.trim();
  clearFilterBtn.style.display = searchQuery ? 'block' : 'none';
  renderTree();
  if (currentSelection?.type !== 'asset') renderContent();
});

filterInput.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    filterInput.value = '';
    searchQuery = '';
    clearFilterBtn.style.display = 'none';
    filterInput.blur();
    renderTree();
    if (currentSelection?.type !== 'asset') renderContent();
  }
});

clearFilterBtn.addEventListener('click', () => {
  filterInput.value = '';
  searchQuery = '';
  clearFilterBtn.style.display = 'none';
  renderTree();
  if (currentSelection?.type !== 'asset') renderContent();
});

function toggleAllFolders() {
  allFoldersCollapsed = !allFoldersCollapsed;
  const tree = buildTree();

  if (allFoldersCollapsed) {
    for (const [_, projNode] of tree.entries()) {
      collapsedNodes.add(getNodeKey(projNode, true));
      function addRecursive(n: TreeNode) {
        if (n.isFolder && n.children.size > 0) {
          collapsedNodes.add(getNodeKey(n, false));
          for (const c of n.children.values()) addRecursive(c);
        }
      }
      for (const c of projNode.children.values()) addRecursive(c);
    }
    toggleAllBtn?.setAttribute('title', 'Expandir todas as pastas');
  } else {
    collapsedNodes.clear();
    toggleAllBtn?.setAttribute('title', 'Recolher todas as pastas');
  }

  renderTree();
}

toggleAllBtn?.addEventListener('click', () => {
  toggleAllFolders();
});

refreshBtn.addEventListener('click', () => {
  fetchCatalog();
});

const poller = new ForgeSession.Poller(fetchCatalog, 1500);
poller.refresh();
window.addEventListener('pagehide', () => poller.stop());
document.getElementById('focus-toggle')?.addEventListener('click', () => document.body.classList.toggle('focus-mode'));

document.getElementById('sidebar-toggle')?.addEventListener('click', () => { document.body.classList.remove('focus-mode'); document.body.classList.toggle('navigation-open'); });
