import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,cp,readFile,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {chromium} from 'playwright';
import {serve} from './server.mjs';

test('round-trip exports and rejection of invalid deliveries', {timeout:120000}, async()=>{
  const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
  const temp=await mkdtemp(path.join(tmpdir(),'asset-kit-'));
  try {
    await cp(path.join(root,'examples/estudo-kit-assets/asset-workbench'),path.join(temp,'asset-workbench'),{recursive:true});
    const run=(...args)=>spawnSync(process.execPath,[path.join(root,'tools/asset-kit/cli.mjs'),...args,temp],{encoding:'utf8',timeout:90000});
    let result=run('check');assert.equal(result.status,0,result.stdout+result.stderr);
    const configPath=path.join(temp,'asset-workbench/assets.json');
    const original=await readFile(configPath,'utf8'),config=JSON.parse(original);
    config.assets[0].maxTriangles=1;
    config.assets[2].size=[64,64];
    await writeFile(configPath,JSON.stringify(config));
    result=run('verify');assert.equal(result.status,1,result.stdout+result.stderr);
    let report=JSON.parse(await readFile(path.join(temp,'asset-workbench/checks/report.json')));
    assert.match(report.assets.find(a=>a.id==='fence').error,/budget/);
    assert.match(report.assets.find(a=>a.id==='carrot_icon').error,/size/);
    await writeFile(configPath,original);
    await writeFile(path.join(temp,'assets/models/fence.glb'),'broken-glb');
    result=run('verify');assert.equal(result.status,1);
    report=JSON.parse(await readFile(path.join(temp,'asset-workbench/checks/report.json')));
    assert.equal(report.assets.find(a=>a.id==='fence').status,'failed');
    config.assets[0].output='../escape.glb';
    await writeFile(configPath,JSON.stringify(config));
    result=run('verify');assert.equal(result.status,1);assert.match(result.stderr,/escapes root/);
  } finally {await rm(temp,{recursive:true,force:true});}
});

test('one preview per project, live GLB/PNG updates and new entries without navigation', {timeout:120000}, async()=>{
  const repo=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
  const kit=path.join(repo,'tools/asset-kit');
  const temp=await mkdtemp(path.join(tmpdir(),'asset-live-'));
  let browser,server;
  const run=async(...args)=>promisify(execFile)(process.execPath,[path.join(kit,'cli.mjs'),...args],{timeout:60000});
  try {
    await cp(path.join(repo,'examples/estudo-kit-assets/asset-workbench'),path.join(temp,'asset-workbench'),{recursive:true});
    await run('check',temp);
    const first=await serve(temp,kit,{persistent:true});server=first.server;
    const duplicates=await Promise.all([serve(temp,kit,{persistent:true}),serve(temp,kit,{persistent:true})]);
    assert.ok(duplicates.every(d=>d.reused&&d.url===first.url&&d.server===null));
    const second=await run('preview',temp);
    assert.match(second.stdout,/Servidor existente reutilizado/);assert.ok(second.stdout.includes(first.url));
    try {browser=await chromium.launch({channel:'chrome',headless:true});}catch{browser=await chromium.launch({headless:true});}
    const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(first.url+'/?id=fence');await page.waitForFunction(()=>window.assetReady);
    await page.evaluate(()=>{window.noNavigationMarker='same-page';});
    const camera=await page.evaluate(()=>window.assetKit.cameraPosition);
    const oldRevision=await page.evaluate(()=>window.assetKit.revision);
    const source=path.join(temp,'asset-workbench/sources/fence.js');
    await writeFile(source,(await readFile(source,'utf8')).replace('#946137','#267138'));
    await run('export',temp,'fence');
    await page.waitForFunction(revision=>window.assetKit.revision>revision,oldRevision);
    assert.deepEqual(await page.evaluate(()=>window.assetKit.cameraPosition),camera);
    // Wait for the source-change event too, then inspect the final GLB event.
    await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('arquivo exportado'));
    await page.getByRole('button',{name:'carrot_icon.png'}).click();await page.waitForFunction(()=>window.assetReady&&document.querySelector('#status').textContent.startsWith('carrot_icon'));
    const rev=await page.evaluate(()=>window.assetKit.revision);
    const png=await page.evaluate(async()=>{
      const c=document.createElement('canvas');c.width=c.height=128;
      c.getContext('2d').fillRect(0,0,12,12);
      return Array.from(new Uint8Array(await (await new Promise(r=>c.toBlob(r))).arrayBuffer()));
    });
    await writeFile(path.join(temp,'assets/images/carrot_icon.png'),Buffer.from(png));
    await page.waitForFunction(revision=>window.assetKit.revision>revision,rev);
    assert.equal((await page.evaluate(()=>window.assetKit.inspect())).visible,144);
    const configPath=path.join(temp,'asset-workbench/assets.json');
    const config=JSON.parse(await readFile(configPath,'utf8'));
    config.assets.push({...config.assets[2],id:'new_icon',output:'assets/images/new_icon.png'});
    await writeFile(configPath,JSON.stringify(config));
    await page.waitForFunction(()=>document.querySelector('#assets option[value="new_icon"]'));
    await page.getByRole('button',{name:'new_icon.png'}).click();
    await page.waitForFunction(()=>window.assetReady&&document.querySelector('#status').textContent.startsWith('new_icon'));
    const before=await page.evaluate(()=>window.assetKit.revision);
    await writeFile(path.join(temp,'assets/images/new_icon.png'),Buffer.from(png));
    await page.waitForFunction(revision=>window.assetKit.revision>revision,before);
    assert.equal((await page.evaluate(()=>window.assetKit.inspect())).visible,144);
    assert.equal(await page.evaluate(()=>window.noNavigationMarker),'same-page');
    assert.deepEqual(errors,[]);
  } finally {
    await browser?.close();
    if(server){server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
    await rm(temp,{recursive:true,force:true});
  }
});
