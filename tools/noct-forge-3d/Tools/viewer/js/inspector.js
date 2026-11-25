/**
 * Inspector & Hierarchy Outliner for NoctAssetForge3D.
 * Generates an interactive outliner, handles node selection, and manages inspection overlays (bones, pivots).
 */

(function (global) {
    function getKindIcon(kind) { return kind === 'bone' ? '┆' : ['mesh', 'skinned_mesh', 'cube'].includes(kind) ? '◇' : '▱'; }

    function collectOutlinerChildren(threeNode) {
        const list = [];
        if (!threeNode || !threeNode.children) return list;
        for (const child of threeNode.children) {
            if (child.userData && child.userData.internal) {
                list.push(...collectOutlinerChildren(child));
            } else {
                list.push(child);
            }
        }
        return list;
    }

    class ModelInspector {
        constructor({ container, sceneSetup }) {
            this.container = typeof container === 'string' ? document.getElementById(container) : container;
            this.sceneSetup = sceneSetup;
            this.loadedAsset = null;
            this.selectedObject = null;
            this.selectedRow = null;
            this.boxHelper = null;
            this.selectedPivot = null;
            this.bonesHelper = null;
            this.bbmodelBonesHelper = null;
            this.showBones = false;
            this.showPivots = false;
        }

        setTarget(loadedAsset) {
            this.clearSelection();
            this.loadedAsset = loadedAsset;
            this.refreshOverlays();
            this.renderTree();
        }

        clearSelection() {
            if (this.selectedRow) {
                this.selectedRow.classList.remove('selected');
                this.selectedRow = null;
            }
            if (this.boxHelper) {
                if (this.boxHelper.parent) this.boxHelper.parent.remove(this.boxHelper);
                if (this.boxHelper.geometry) this.boxHelper.geometry.dispose();
                if (this.boxHelper.material) this.boxHelper.material.dispose();
                this.boxHelper = null;
            }
            if (this.selectedPivot) {
                if (this.selectedPivot.parent) this.selectedPivot.parent.remove(this.selectedPivot);
                if (this.selectedPivot.geometry) this.selectedPivot.geometry.dispose();
                if (this.selectedPivot.material) this.selectedPivot.material.dispose();
                this.selectedPivot = null;
            }
            this.selectedObject = null;
        }

        selectNode(threeNode, rowElement) {
            this.clearSelection();
            if (!threeNode) return;

            this.selectedObject = threeNode;
            this.selectedRow = rowElement;
            if (rowElement) rowElement.classList.add('selected');

            this.boxHelper = new THREE.BoxHelper(threeNode, 0x3b82f6);
            this.boxHelper.material.depthTest = false;
            this.boxHelper.material.transparent = true;
            this.boxHelper.renderOrder = 999;
            this.sceneSetup.scene.add(this.boxHelper);

            if (this.showPivots && !threeNode.getObjectByName("pivot_axes_helper")) {
                const axes = new THREE.AxesHelper(3.5);
                axes.name = "selected_pivot_axes_helper";
                axes.userData = { internal: true };
                axes.material.depthTest = false;
                axes.renderOrder = 1000;
                threeNode.add(axes);
                this.selectedPivot = axes;
            }

            this.updateSelectionInfo(threeNode);
        }

        updateSelectionInfo(threeNode) {
            if (!threeNode) return;
            const kind = threeNode.userData?.kind || (threeNode.isBone ? 'bone' : threeNode.isMesh ? 'mesh' : 'group');
            const pos = threeNode.position;
            const rot = threeNode.rotation;
            const degX = (THREE.MathUtils.radToDeg(rot.x)).toFixed(1);
            const degY = (THREE.MathUtils.radToDeg(rot.y)).toFixed(1);
            const degZ = (THREE.MathUtils.radToDeg(rot.z)).toFixed(1);

            const badgeName = document.getElementById('selection-name');
            const badgeMeta = document.getElementById('selection-transform');
            if (badgeName) badgeName.textContent = `${threeNode.name || kind} (${kind})`;
            if (badgeMeta) {
                badgeMeta.textContent = `Pos: [${pos.x.toFixed(1)}, ${pos.y.toFixed(1)}, ${pos.z.toFixed(1)}] | Rot: [${degX}°, ${degY}°, ${degZ}°]`;
            }
        }

        renderTree() {
            if (!this.container) return;
            this.container.replaceChildren();

            if (!this.loadedAsset || !this.loadedAsset.object) {
                const empty = document.createElement('div');
                empty.className = 'outliner-empty';
                empty.textContent = 'Abra um modelo para visualizar sua estrutura.';
                this.container.appendChild(empty);
                return;
            }

            const root = this.loadedAsset.object;
            const query = (this.query || '').toLocaleLowerCase().trim();
            this.searchMatches = null;
            if (query) {
                this.searchMatches = new Set();
                root.traverse(node => {
                    if ((node.name || '').toLocaleLowerCase().includes(query)) {
                        for (let parent = node; parent; parent = parent.parent) { this.searchMatches.add(parent); if (parent === root) break; }
                    }
                });
            }
            const treeFrag = document.createDocumentFragment();
            this._buildNodeDom(root, treeFrag, 0);
            this.container.appendChild(treeFrag);
        }

        filterTree(query) { this.query = query; this.renderTree(); }

        _buildNodeDom(threeNode, parentDom, depth) {
            if (this.searchMatches && !this.searchMatches.has(threeNode)) return;
            const kind = threeNode.userData?.kind || (threeNode.isBone ? 'bone' : threeNode.isMesh ? 'mesh' : 'group');
            const visibleChildren = collectOutlinerChildren(threeNode);

            const row = document.createElement('div');
            row.className = 'outliner-node';
            row.style.paddingLeft = `${depth * 12 + 4}px`;

            // Expand/collapse chevron
            const chevron = document.createElement('span');
            chevron.className = 'outliner-chevron';
            chevron.textContent = visibleChildren.length ? (depth === 0 || this.searchMatches ? '▾' : '▸') : ' ';
            chevron.style.visibility = visibleChildren.length ? 'visible' : 'hidden';

            // Eye button (visibility toggle)
            const eyeBtn = document.createElement('span');
            eyeBtn.className = 'outliner-eye';
            eyeBtn.textContent = threeNode.visible !== false ? '◉' : '○';
            eyeBtn.title = 'Mostrar ou ocultar elemento';
            eyeBtn.onclick = (e) => {
                e.stopPropagation();
                threeNode.visible = !(threeNode.visible !== false);
                eyeBtn.textContent = threeNode.visible ? '◉' : '○';
                row.classList.toggle('node-hidden', !threeNode.visible);
            };

            // Kind icon
            const icon = document.createElement('span');
            icon.className = 'outliner-icon';
            icon.textContent = getKindIcon(kind);

            // Name label
            const label = document.createElement('span');
            label.className = 'outliner-label';
            label.textContent = threeNode.name || kind;
            label.title = `${threeNode.name || kind} (${kind})`;

            row.appendChild(chevron);
            row.appendChild(eyeBtn);
            row.appendChild(icon);
            row.appendChild(label);

            row.tabIndex = 0; row.setAttribute('role', 'treeitem');
            row.onclick = () => this.selectNode(threeNode, row);
            row.onkeydown = event => { if (event.key === 'Enter') this.selectNode(threeNode, row); };

            parentDom.appendChild(row);

            // Children container
            if (visibleChildren.length > 0) {
                const childrenContainer = document.createElement('div');
                childrenContainer.className = 'outliner-children';

                let cursor = 0;
                const children = this.searchMatches ? visibleChildren.filter(child => this.searchMatches.has(child)) : visibleChildren;
                const populate = () => {
                    const end = Math.min(cursor + 75, children.length);
                    for (; cursor < end; cursor++) this._buildNodeDom(children[cursor], childrenContainer, depth + 1);
                    if (cursor < children.length) {
                        const more = document.createElement('button'); more.className = 'outliner-more'; more.textContent = `Mostrar mais (${children.length - cursor})`;
                        more.onclick = () => { more.remove(); populate(); }; childrenContainer.appendChild(more);
                    }
                };
                const expanded = depth === 0 || !!this.searchMatches;
                childrenContainer.hidden = !expanded;
                row.setAttribute('aria-expanded', String(expanded));
                if (expanded) populate();
                chevron.onclick = (event) => {
                    event.stopPropagation();
                    childrenContainer.hidden = !childrenContainer.hidden;
                    if (!childrenContainer.hidden && !cursor) populate();
                    chevron.textContent = childrenContainer.hidden ? '▸' : '▾';
                    row.setAttribute('aria-expanded', String(!childrenContainer.hidden));
                };
                row.ondblclick = chevron.onclick;
                row.onkeydown = event => {
                    if (event.key === 'Enter') this.selectNode(threeNode, row);
                    if ((event.key === 'ArrowRight' && childrenContainer.hidden) || (event.key === 'ArrowLeft' && !childrenContainer.hidden)) {
                        event.preventDefault(); chevron.onclick(event);
                    }
                };
                parentDom.appendChild(childrenContainer);
            }
        }

        setBonesVisible(enabled) {
            this.showBones = Boolean(enabled);
            this.refreshOverlays();
        }

        setPivotsVisible(enabled) {
            this.showPivots = Boolean(enabled);
            this.refreshOverlays();
        }

        refreshOverlays() {
            // Clean up existing bone helpers
            if (this.bonesHelper) {
                if (this.bonesHelper.parent) this.bonesHelper.parent.remove(this.bonesHelper);
                if (this.bonesHelper.geometry) this.bonesHelper.geometry.dispose();
                this.bonesHelper = null;
            }
            if (this.bbmodelBonesHelper) {
                if (this.bbmodelBonesHelper.parent) this.bbmodelBonesHelper.parent.remove(this.bbmodelBonesHelper);
                if (this.bbmodelBonesHelper.geometry) this.bbmodelBonesHelper.geometry.dispose();
                if (this.bbmodelBonesHelper.material) this.bbmodelBonesHelper.material.dispose();
                this.bbmodelBonesHelper = null;
            }
            // Clean up existing pivots
            if (this.loadedAsset && this.loadedAsset.object) {
                const toRemove = [];
                this.loadedAsset.object.traverse(node => {
                    if (node.name === "pivot_axes_helper" || node.name === "selected_pivot_axes_helper") {
                        toRemove.push(node);
                    }
                });
                for (const axes of toRemove) {
                    if (axes.parent) axes.parent.remove(axes);
                    if (axes.geometry) axes.geometry.dispose();
                    if (axes.material) axes.material.dispose();
                }
            }
            this.selectedPivot = null;

            if (!this.loadedAsset || !this.loadedAsset.object) return;

            // 1. Bones Overlay
            if (this.showBones) {
                if (this.loadedAsset.kind === 'glb') {
                    let hasBone = false;
                    this.loadedAsset.object.traverse(c => {
                        if (c.isBone || c.isSkinnedMesh) hasBone = true;
                    });
                    if (hasBone) {
                        this.bonesHelper = new THREE.SkeletonHelper(this.loadedAsset.object);
                        this.bonesHelper.material.linewidth = 2;
                        this.bonesHelper.material.depthTest = false;
                        this.bonesHelper.renderOrder = 998;
                        this.sceneSetup.scene.add(this.bonesHelper);
                    }
                } else if (this.loadedAsset.kind === 'bbmodel') {
                    this._createBBModelBonesHelper();
                }
            }

            // 2. Pivots Overlay
            if (this.showPivots) {
                this.loadedAsset.object.traverse(node => {
                    const kind = node.userData?.kind;
                    if ((kind === 'group' || kind === 'bone' || kind === 'armature') && !node.userData?.internal) {
                        const axes = new THREE.AxesHelper(3.0);
                        axes.name = "pivot_axes_helper";
                        axes.userData = { internal: true };
                        axes.material.depthTest = false;
                        axes.renderOrder = 997;
                        node.add(axes);
                    }
                });
            }
        }

        _createBBModelBonesHelper() {
            const parser = this.loadedAsset?.parser;
            if (!parser || !parser.controls || parser.controls.size === 0) return;

            this.loadedAsset.object.updateMatrixWorld(true);
            const linePositions = [];
            for (const [uuid, control] of parser.controls) {
                const obj = control.object;
                const parent = obj.parent;
                if (parent) {
                    const objPos = new THREE.Vector3().setFromMatrixPosition(obj.matrixWorld);
                    const parentPos = new THREE.Vector3().setFromMatrixPosition(parent.matrixWorld);
                    linePositions.push(parentPos.x, parentPos.y, parentPos.z);
                    linePositions.push(objPos.x, objPos.y, objPos.z);
                }
            }

            if (linePositions.length > 0) {
                const geo = new THREE.BufferGeometry();
                geo.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
                const mat = new THREE.LineBasicMaterial({
                    color: 0xff0055,
                    linewidth: 2,
                    depthTest: false,
                    transparent: true
                });
                this.bbmodelBonesHelper = new THREE.LineSegments(geo, mat);
                this.bbmodelBonesHelper.renderOrder = 998;
                this.sceneSetup.scene.add(this.bbmodelBonesHelper);
            }
        }

        update() {
            if (this.boxHelper && this.selectedObject) {
                this.boxHelper.update();
                this.updateSelectionInfo(this.selectedObject);
            }
            if (this.showBones) {
                if (this.bonesHelper) {
                    this.bonesHelper.update();
                } else if (this.bbmodelBonesHelper && this.loadedAsset?.parser?.controls) {
                    this.loadedAsset.object.updateMatrixWorld(true);
                    const positions = this.bbmodelBonesHelper.geometry.attributes.position;
                    let idx = 0;
                    for (const [uuid, control] of this.loadedAsset.parser.controls) {
                        const obj = control.object;
                        const parent = obj.parent;
                        if (parent && idx + 6 <= positions.count * 3) {
                            const objPos = new THREE.Vector3().setFromMatrixPosition(obj.matrixWorld);
                            const parentPos = new THREE.Vector3().setFromMatrixPosition(parent.matrixWorld);
                            positions.array[idx++] = parentPos.x;
                            positions.array[idx++] = parentPos.y;
                            positions.array[idx++] = parentPos.z;
                            positions.array[idx++] = objPos.x;
                            positions.array[idx++] = objPos.y;
                            positions.array[idx++] = objPos.z;
                        }
                    }
                    positions.needsUpdate = true;
                }
            }
        }

        dispose() {
            this.clearSelection();
            this.setBonesVisible(false);
            this.setPivotsVisible(false);
            if (this.container) this.container.replaceChildren();
        }
    }

    global.ModelInspector = ModelInspector;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { ModelInspector };
    }
})(typeof window !== 'undefined' ? window : globalThis);
