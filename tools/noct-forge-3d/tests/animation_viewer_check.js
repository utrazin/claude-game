const assert = require("assert");
global.THREE = require("../Tools/viewer/vendor/three.min.js");
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
const { BBModelParser } = require("../Tools/viewer/js/bbmodel_parser.js");
const { AnimationPlayer } = require("../Tools/viewer/js/animation_player.js");

if (process.argv[2]) {
    const document = JSON.parse(require("fs").readFileSync(process.argv[2], "utf8"));
    const actualParser = new BBModelParser(document);
    actualParser.buildScene();
    assert(actualParser.skinnedMeshes.length > 0);
    const actualPlayer = new AnimationPlayer(actualParser, document.animations);
    actualPlayer.select(document.animations[0].name);
    const position = actualParser.skinnedMeshes[0].mesh.geometry.attributes.position;
    const before = Array.from(position.array);
    actualPlayer.seek(1);
    assert(Array.from(position.array).some((value, index) => Math.abs(value - before[index]) > 1e-5));
    actualPlayer.dispose();
    process.exit(0);
}

const meshId = "abcdef00-0000-4000-8000-000000000000";
const prefix = meshId.slice(0, 6) + ":";
const weights = Object.fromEntries(["v0", "v1", "v2", "v3"].map(key => [prefix + key, 0.5]));
const data = {
    name: "animated",
    resolution: { width: 16, height: 16 },
    groups: [
        { uuid: "folder", name: "root", origin: [0, 0, 0], rotation: [0, 0, 0], model_as_code_role: "folder" },
        { uuid: "joint", name: "jaw", origin: [0, 2, 0], rotation: [0, 0, 0], model_as_code_role: "transform" }
    ],
    elements: [
        { type: "armature", uuid: "rig", name: "rig", children: ["b0", "b1", meshId] },
        { type: "armature_bone", uuid: "b0", name: "base", origin: [0, 0, 0], rotation: [0, 0, 0], vertex_weights: weights },
        { type: "armature_bone", uuid: "b1", name: "tip", origin: [0, 2, 0], rotation: [0, 0, 0], vertex_weights: weights },
        { type: "mesh", uuid: meshId, name: "skin", origin: [0, 0, 0], vertices: {
            v0: [0, 0, 0], v1: [1, 0, 0], v2: [1, 2, 0], v3: [0, 2, 0]
        }, faces: { f0: { vertices: ["v0", "v1", "v2", "v3"] } } }
    ],
    outliner: [
        { uuid: "folder", children: [{ uuid: "joint", children: [] },
            { uuid: "rig", children: [{ uuid: "b0", children: [{ uuid: "b1", children: [] }] }, meshId] }] }
    ],
    animations: [{ name: "pose", length: 1, loop: "loop", animators: {
        joint: { type: "bone", keyframes: [
            { time: 0, channel: "rotation", data_points: [{ x: 0, y: 0, z: 0 }] },
            { time: 1, channel: "rotation", data_points: [{ x: 0, y: 0, z: 90 }] }
        ] },
        b1: { type: "armature_bone", keyframes: [
            { time: 0, channel: "rotation", data_points: [{ x: 0, y: 0, z: 0 }] },
            { time: 1, channel: "rotation", data_points: [{ x: 0, y: 0, z: 90 }] }
        ] }
    } }]
};

const parser = new BBModelParser(data);
parser.buildScene();
assert.strictEqual(parser.skinnedMeshes.length, 1);
const player = new AnimationPlayer(parser, data.animations);
player.select("pose");
player.seek(0.5);
assert(Math.abs(parser.controls.get("joint").object.rotation.z - Math.PI / 4) < 1e-6);
player.seek(1);
const positions = parser.skinnedMeshes[0].mesh.geometry.attributes.position;
assert(Math.abs(positions.getX(2) - 0.5) < 1e-5);
assert(Math.abs(positions.getY(2) - 2.5) < 1e-5);
player.seek(0);
assert(Math.abs(positions.getX(2) - 1) < 1e-5);
assert(Math.abs(positions.getY(2) - 2) < 1e-5);
player.play();
player._frame(0);
player._frame(1500);
assert(Math.abs(player.time - 0.5) < 1e-6);
player.pause();
assert.deepStrictEqual(AnimationPlayer._sample([
    { time: 0, interpolation: "step", data_points: [{ x: 0, y: 0, z: 0 }] },
    { time: 1, data_points: [{ x: 3, y: 0, z: 0 }] }
], 0.5), [0, 0, 0]);
player.dispose();

// A transformed mesh must not receive its parent transform twice during skinning.
const transformed = JSON.parse(JSON.stringify(data));
transformed.groups[0].rotation = [0, 0, 30];
transformed.groups[0].origin = [3, 1, 0];
const transformedParser = new BBModelParser(transformed);
transformedParser.buildScene();
const binding = transformedParser.skinnedMeshes[0];
const rest = Array.from(binding.mesh.geometry.attributes.position.array);
transformedParser.updateSkinning();
assert(Array.from(binding.mesh.geometry.attributes.position.array).every((value, index) => Math.abs(value-rest[index]) < 1e-5));
const transformedPlayer = new AnimationPlayer(transformedParser, transformed.animations);
transformedPlayer.select('pose');
transformedPlayer.seek(1);
const deformed = binding.mesh.geometry.attributes.position;
assert(Math.abs(deformed.getX(2)-.5) < 1e-5);
assert(Math.abs(deformed.getY(2)-2.5) < 1e-5);
transformedPlayer.seek(0);
assert(Array.from(deformed.array).every((value, index) => Math.abs(value-rest[index]) < 1e-5));
transformedPlayer.dispose();
