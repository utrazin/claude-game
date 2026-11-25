const fs = require('fs');
const validator = require('gltf-validator');
(async () => {
    const report = await validator.validateBytes(new Uint8Array(fs.readFileSync(process.argv[2])));
    process.stdout.write(JSON.stringify(report.issues));
    process.exitCode = report.issues.numErrors ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode = 2; });
