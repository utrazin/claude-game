const assert = require("assert");
global.THREE = require("../Tools/viewer/vendor/three.min.js");
global.requestAnimationFrame = (fn) => 1;
global.cancelAnimationFrame = (id) => {};
require("../Tools/viewer/vendor/GLTFLoader.js");

const { BBModelParser } = require("../Tools/viewer/js/bbmodel_parser.js");
const { AnimationPlayer } = require("../Tools/viewer/js/animation_player.js");
const {
    loadAssetObject,
    LoadedAsset,
    BBModelClipController,
    GlbClipController
} = require("../Tools/viewer/js/asset_loader.js");

// 1. Verify GLTFLoader is registered on THREE
assert(typeof THREE.GLTFLoader === "function", "GLTFLoader must be on THREE");

// 2. Test BBModelParser tagging in buildScene
const testData = {
    name: "test_model",
    resolution: { width: 16, height: 16 },
    groups: [
        { uuid: "grp-1", name: "head_group", origin: [0, 4, 0], rotation: [0, 0, 0] }
    ],
    elements: [
        {
            type: "cube",
            uuid: "cube-1",
            name: "head_cube",
            from: [0, 0, 0],
            to: [4, 4, 4],
            origin: [0, 0, 0],
            faces: {
                north: { uv: [0, 0, 4, 4], texture: null }
            }
        },
        {
            type: "armature_bone",
            uuid: "bone-1",
            name: "neck_bone",
            origin: [0, 2, 0],
            rotation: [0, 0, 0]
        }
    ],
    outliner: [
        {
            uuid: "grp-1",
            children: [
                "cube-1",
                { uuid: "bone-1", children: [] }
            ]
        }
    ],
    animations: [
        {
            name: "idle",
            length: 1.5,
            loop: "loop",
            animators: {
                "bone-1": {
                    keyframes: [
                        { time: 0, channel: "rotation", data_points: [{ x: 0, y: 0, z: 0 }] },
                        { time: 1.5, channel: "rotation", data_points: [{ x: 0, y: 0, z: 45 }] }
                    ]
                }
            }
        }
    ]
};

const parser = new BBModelParser(testData);
const scene = parser.buildScene();

// Check rootGroup tagging
assert.strictEqual(scene.userData.kind, "group");

// Find group, bone, cube, and internal pivot containers
let foundGroup = null;
let foundBone = null;
let foundCube = null;
let foundInternal = 0;

scene.traverse(node => {
    if (node.userData.kind === "group" && node.userData.uuid === "grp-1") {
        foundGroup = node;
    }
    if (node.userData.kind === "bone" && node.userData.uuid === "bone-1") {
        foundBone = node;
    }
    if (node.userData.kind === "cube" && node.userData.uuid === "cube-1") {
        foundCube = node;
    }
    if (node.userData.internal === true) {
        foundInternal++;
    }
});

assert(foundGroup, "Outliner group must be tagged with kind: 'group' and uuid");
assert(foundBone, "Armature bone must be tagged with kind: 'bone' and uuid");
assert(foundCube, "Cube mesh must be tagged with kind: 'cube' and uuid");
assert(foundInternal >= 2, "childrenContainer and pivotGroup must have internal: true");

// 3. Test loadAssetObject for bbmodel
async function runAsyncTests() {
    const asset = await loadAssetObject({
        kind: "bbmodel",
        modelData: testData
    });

    assert(asset instanceof LoadedAsset);
    assert.strictEqual(asset.kind, "bbmodel");
    assert(asset.object instanceof THREE.Object3D);
    assert(asset.bbox && typeof asset.bbox.maxDimension === "number");
    assert(Array.isArray(asset.bbox.center));
    assert(Array.isArray(asset.bbox.size));

    // Test clips
    assert.deepStrictEqual(asset.clips.names, ["idle"]);
    assert.strictEqual(asset.clips.length, 0);
    asset.clips.select("idle");
    assert.strictEqual(asset.clips.length, 1.5);
    assert.strictEqual(asset.clips.playing, false);
    asset.clips.seek(0.75);
    assert.strictEqual(asset.clips.time, 0.75);
    asset.clips.play();
    assert.strictEqual(asset.clips.playing, true);
    asset.clips.pause();
    assert.strictEqual(asset.clips.playing, false);

    // Test setWireframe
    asset.setWireframe(true);
    let wireframeOn = false;
    asset.object.traverse(child => {
        if (child.isMesh && child.material) {
            const mats = Array.isArray(child.material) ? child.material : [child.material];
            if (mats.some(m => m.wireframe)) wireframeOn = true;
        }
    });
    assert(wireframeOn, "setWireframe(true) must set material.wireframe");

    asset.setWireframe(false);
    let wireframeOff = true;
    asset.object.traverse(child => {
        if (child.isMesh && child.material) {
            const mats = Array.isArray(child.material) ? child.material : [child.material];
            if (mats.some(m => m.wireframe)) wireframeOff = false;
        }
    });
    assert(wireframeOff, "setWireframe(false) must clear material.wireframe");

    // Test setShading
    asset.setShading(false);
    let hasBasic = false;
    asset.object.traverse(child => {
        if (child.isMesh && child.material) {
            const mats = Array.isArray(child.material) ? child.material : [child.material];
            if (mats.some(m => m.type === "MeshBasicMaterial")) hasBasic = true;
        }
    });
    assert(hasBasic, "setShading(false) must switch to MeshBasicMaterial");

    asset.setShading(true);
    let hasStandard = false;
    asset.object.traverse(child => {
        if (child.isMesh && child.material) {
            const mats = Array.isArray(child.material) ? child.material : [child.material];
            if (mats.some(m => m.type === "MeshStandardMaterial")) hasStandard = true;
        }
    });
    assert(hasStandard, "setShading(true) must switch to MeshStandardMaterial");

    // Test setTextureFilter
    asset.setTextureFilter("linear");
    assert.strictEqual(asset.textureFilter, "linear");
    asset.setTextureFilter("nearest");
    assert.strictEqual(asset.textureFilter, "nearest");

    // Test dispose
    asset.dispose();

    // 4. Test GlbClipController
    const glbRoot = new THREE.Group();
    const clip1 = new THREE.AnimationClip("walk", 2.0, []);
    const glbClips = new GlbClipController(glbRoot, [clip1]);
    assert.deepStrictEqual(glbClips.names, ["walk"]);
    assert.strictEqual(glbClips.length, 0); // No clip selected yet
    glbClips.select("walk");
    assert.strictEqual(glbClips.length, 2.0);
    glbClips.seek(1.0);
    assert.strictEqual(glbClips.time, 1.0);
    glbClips.play();
    assert.strictEqual(glbClips.playing, true);
    glbClips.pause();
    assert.strictEqual(glbClips.playing, false);
    glbClips.dispose();

    console.log("All asset_loader_check tests PASSED!");
}

runAsyncTests().catch(err => {
    console.error(err);
    process.exit(1);
});
