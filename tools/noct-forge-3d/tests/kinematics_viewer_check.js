// Prints the viewer's world matrix of every animation control at the given clip times, as JSON:
// { "<time>": { "<uuid>": [16 column-major numbers] } }. Used to check lib.kinematics against the viewer.
// Usage: node kinematics_viewer_check.js model.bbmodel clipName 0,0.5,1
global.THREE = require("../Tools/viewer/vendor/three.min.js");
global.requestAnimationFrame = () => 1;
global.cancelAnimationFrame = () => {};
const fs = require("fs");
const { BBModelParser } = require("../Tools/viewer/js/bbmodel_parser.js");
const { AnimationPlayer } = require("../Tools/viewer/js/animation_player.js");

const [file, clipName, timesArg] = process.argv.slice(2);
const document = JSON.parse(fs.readFileSync(file, "utf8"));
const parser = new BBModelParser(document);
const root = parser.buildScene();
const player = new AnimationPlayer(parser, document.animations || []);
player.select(clipName);
const toModel = root.matrixWorld.clone().invert();
const out = {};
for (const time of (timesArg || "0").split(",").map(Number)) {
    player.seek(time);
    root.updateMatrixWorld(true);
    const frames = {};
    for (const [uuid, control] of parser.controls) {
        frames[uuid] = Array.from(control.object.matrixWorld.clone().premultiply(toModel).elements);
    }
    out[String(time)] = frames;
}
player.dispose();
process.stdout.write(JSON.stringify(out));
