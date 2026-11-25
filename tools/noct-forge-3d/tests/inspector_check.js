const assert = require("assert");
global.THREE = require("../Tools/viewer/vendor/three.min.js");
global.requestAnimationFrame = (fn) => 1;
global.cancelAnimationFrame = (id) => {};
require("../Tools/viewer/vendor/GLTFLoader.js");

const { BBModelParser } = require("../Tools/viewer/js/bbmodel_parser.js");
const { AnimationPlayer } = require("../Tools/viewer/js/animation_player.js");
const { loadAssetObject } = require("../Tools/viewer/js/asset_loader.js");
const { ModelInspector } = require("../Tools/viewer/js/inspector.js");

// Mock Minimal DOM
function createMockElement(tag) {
    const el = {
        tagName: tag.toUpperCase(),
        className: "",
        style: {},
        textContent: "",
        innerHTML: "",
        title: "",
        onclick: null,
        children: [],
        attributes: {},
        setAttribute(name, value) { this.attributes[name] = String(value); },
        classList: {
            classes: new Set(),
            add(c) { this.classes.add(c); el.className = Array.from(this.classes).join(" "); },
            remove(c) { this.classes.delete(c); el.className = Array.from(this.classes).join(" "); },
            toggle(c, force) {
                const has = (force !== undefined) ? force : !this.classes.has(c);
                if (has) this.add(c); else this.remove(c);
                return has;
            },
            contains(c) { return this.classes.has(c); }
        },
        appendChild(child) {
            this.children.push(child);
            return child;
        },
        replaceChildren(...nodes) {
            this.children = [...nodes];
        }
    };
    return el;
}

const mockDoc = {
    badgeName: createMockElement("div"),
    badgeMeta: createMockElement("div"),
    selectionName: createMockElement("div"),
    selectionTransform: createMockElement("div"),
    createElement: createMockElement,
    createDocumentFragment: () => {
        const frag = {
            children: [],
            appendChild(child) {
                this.children.push(child);
                return child;
            }
        };
        return frag;
    },
    getElementById(id) {
        if (id === "badge-name") return this.badgeName;
        if (id === "badge-meta") return this.badgeMeta;
        if (id === "selection-name") return this.selectionName;
        if (id === "selection-transform") return this.selectionTransform;
        return null;
    }
};
global.document = mockDoc;

async function runTests() {
    const testData = {
        name: "inspector_test",
        resolution: { width: 16, height: 16 },
        groups: [
            { uuid: "grp-root", name: "root_group", origin: [0, 4, 0], rotation: [0, 0, 0] }
        ],
        elements: [
            {
                type: "cube",
                uuid: "cube-1",
                name: "torso",
                from: [0, 0, 0],
                to: [4, 4, 4],
                origin: [0, 0, 0],
                faces: {
                    north: { uv: [0, 0, 4, 4], texture: null }
                }
            },
            {
                type: "armature_bone",
                uuid: "bone-arm",
                name: "arm",
                origin: [0, 2, 0],
                rotation: [0, 0, 0]
            }
        ],
        outliner: [
            {
                uuid: "grp-root",
                children: [
                    "cube-1",
                    { uuid: "bone-arm", children: [] }
                ]
            }
        ],
        animations: [
            {
                name: "wave",
                length: 1.0,
                loop: "loop",
                animators: {
                    "bone-arm": {
                        keyframes: [
                            { time: 0, channel: "rotation", data_points: [{ x: 0, y: 0, z: 0 }] },
                            { time: 1.0, channel: "rotation", data_points: [{ x: 0, y: 0, z: 90 }] }
                        ]
                    }
                }
            }
        ]
    };

    const loaded = await loadAssetObject({
        kind: "bbmodel",
        modelData: testData
    });

    assert(loaded && loaded.object, "Asset must load successfully");

    const mockScene = new THREE.Scene();
    mockScene.add(loaded.object);
    const mockSceneSetup = { scene: mockScene };
    const container = createMockElement("div");

    const inspector = new ModelInspector({ container, sceneSetup: mockSceneSetup });

    // 1. Initial State
    assert.strictEqual(inspector.loadedAsset, null);
    assert.strictEqual(inspector.selectedObject, null);

    // 2. Set Target & Outliner Generation
    inspector.setTarget(loaded);
    assert.strictEqual(inspector.loadedAsset, loaded);
    assert(container.children.length > 0, "Container should contain outliner nodes");

    // Check that internal nodes were skipped in outliner
    function collectLabels(mockEl) {
        const labels = [];
        for (const child of mockEl.children) {
            if (child.className && child.className.includes("outliner-label")) {
                labels.push(child.textContent);
            }
            labels.push(...collectLabels(child));
        }
        return labels;
    }
    let labels = collectLabels(container);
    assert(labels.includes("root_group"), "Should include root_group");
    assert(!labels.includes("torso"), "Nested geometry is lazy until its group is opened");
    const findRow = element => {
        if (element.children.some(child => child.className === 'outliner-label' && child.textContent === 'root_group')) return element;
        return element.children.map(findRow).find(Boolean);
    };
    findRow(container).children[0].onclick({ stopPropagation() {} });
    labels = collectLabels(container);
    assert(labels.includes("torso"), "Should include torso cube");
    assert(labels.includes("arm"), "Should include arm bone");

    // 3. Selection
    const torsoMesh = loaded.object.getObjectByName("torso") || loaded.object.getObjectByProperty("name", "torso");
    assert(torsoMesh, "Must find torso mesh in scene");
    inspector.selectNode(torsoMesh, null);
    assert.strictEqual(inspector.selectedObject, torsoMesh);
    assert(inspector.boxHelper, "BoxHelper should be created on selection");
    assert.strictEqual(mockDoc.selectionName.textContent, "torso (cube)");
    assert.strictEqual(mockDoc.badgeName.textContent, "", "Selecting an element must not rename the asset header");

    // 4. Overlays: Bones
    inspector.setBonesVisible(true);
    assert.strictEqual(inspector.showBones, true);
    assert(inspector.bbmodelBonesHelper, "BBModel bones helper should be created");
    assert(mockScene.children.includes(inspector.bbmodelBonesHelper), "Bones helper in scene");

    // 5. Overlays: Pivots
    inspector.setPivotsVisible(true);
    assert.strictEqual(inspector.showPivots, true);
    let pivotCount = 0;
    loaded.object.traverse(node => {
        if (node.name === "pivot_axes_helper") pivotCount++;
    });
    assert(pivotCount > 0, "Pivots should be attached to groups/bones");

    // 6. Update Loop
    inspector.update();

    // 7. Toggle overlays off
    inspector.setBonesVisible(false);
    assert.strictEqual(inspector.showBones, false);
    assert.strictEqual(inspector.bbmodelBonesHelper, null);

    inspector.setPivotsVisible(false);
    assert.strictEqual(inspector.showPivots, false);
    pivotCount = 0;
    loaded.object.traverse(node => {
        if (node.name === "pivot_axes_helper") pivotCount++;
    });
    assert.strictEqual(pivotCount, 0, "Pivots should be cleaned up");

    // 8. Disposal
    inspector.dispose();
    assert.strictEqual(inspector.selectedObject, null);
    assert.strictEqual(inspector.boxHelper, null);

    loaded.dispose();
    console.log("All inspector_check tests passed successfully.");
}

runTests().catch(err => {
    console.error("Test failed:", err);
    process.exit(1);
});
