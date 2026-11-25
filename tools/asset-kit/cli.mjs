import { readFile, writeFile, mkdir, realpath } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFile, execSync } from 'node:child_process';
import {serve,inside} from './server.mjs';

const kit = path.dirname(fileURLToPath(import.meta.url));

function ensureDependencies() {
  const nm = path.join(kit, 'node_modules');
  if (!existsSync(nm)) {
    console.log('[Asset Kit] Dependencias ausentes em tools/asset-kit. Instalando pacotes com npm...');
    execSync('npm install', { cwd: kit, stdio: 'inherit' });
    console.log('[Asset Kit] Dependencias instaladas com sucesso.');
  }
}
async function launcher(project) {
  const relative=path.relative(project,path.join(kit,'cli.mjs')).replaceAll('/', '\\');
  const kitRelative=path.relative(project,kit).replaceAll('/', '\\');
  const text=`@echo off\r\nsetlocal\r\ntitle Visualizador de Assets\r\nwhere node >nul 2>nul\r\nif errorlevel 1 (\r\n  echo [ERRO] Node.js nao encontrado no sistema!\r\n  echo Para instalar, execute no terminal:\r\n  echo   winget install OpenJS.NodeJS.LTS\r\n  echo Ou baixe o instalador em: https://nodejs.org\r\n  pause\r\n  exit /b 1\r\n)\r\nif not exist "%~dp0${kitRelative}\\node_modules" (\r\n  echo [SETUP] Dependencias nao encontradas. Instalando pacotes com npm...\r\n  pushd "%~dp0${kitRelative}"\r\n  call npm install\r\n  popd\r\n)\r\necho Abrindo o visualizador. Se ja estiver ativo, o servidor sera reutilizado.\r\necho Mantenha a primeira janela aberta. Ctrl+C encerra o servidor.\r\nnode "%~dp0${relative}" preview "%~dp0." --open\r\nif errorlevel 1 pause\r\nendlocal\r\n`;
  await writeFile(path.join(project,'Abrir Visualizador.bat'),text);
}

async function main() {
  const args=process.argv.slice(2);
  const openBrowser=args.includes('--open');
  const [command, projectArg, onlyId]=args.filter(arg=>arg!=='--open');
  if(!['launcher','preview','export','verify','check'].includes(command)||!projectArg) throw new Error('Usage: node tools/asset-kit/cli.mjs launcher|preview|export|verify|check <project-path> [asset-id] [--open]');
  const project=await realpath(path.resolve(projectArg));
  if(command==='launcher') {await launcher(project);console.log('Abrir Visualizador.bat criado.');return;}
  ensureDependencies();
  const config=JSON.parse(await readFile(path.join(project,'asset-workbench/assets.json'),'utf8'));
  if(!Array.isArray(config.assets)||!config.assets.length) throw new Error('assets must be a nonempty array');
  const ids=new Set(),outputs=new Set();
  for(const a of config.assets) {
    if(!/^[a-z][a-z0-9_]*$/.test(a.id)||ids.has(a.id)) throw new Error('Invalid/duplicate id: '+a.id);
    ids.add(a.id);
    if(!['glb','png'].includes(a.kind)||!a.output?.endsWith('.'+a.kind)) throw new Error('Invalid kind/output: '+a.id);
    const dest=inside(project,a.output);inside(project,a.source);
    if(outputs.has(dest)) throw new Error('Duplicate output: '+a.output);outputs.add(dest);
    if(a.kind==='png'&&(!Array.isArray(a.size)||a.size.length!==2||!a.size.every(n=>Number.isInteger(n)&&n>0))) throw new Error('PNG requires size: '+a.id);
  }
  const entries=onlyId?config.assets.filter(a=>a.id===onlyId):config.assets;
  if(!entries.length) throw new Error('Unknown asset: '+onlyId);
  if(command==='preview') {
    try {await readFile(path.join(project,'Abrir Visualizador.bat'));} catch {await launcher(project);}
  }
  const {server,url,reused}=await serve(project,kit,{persistent:command==='preview'});
  if(command==='preview') {
    console.log(url);
    if(reused)console.log('Servidor existente reutilizado.');
    if(openBrowser) {
      const [app,params]=process.platform==='win32'
        ? ['rundll32.exe',['url.dll,FileProtocolHandler',url]]
        : process.platform==='darwin' ? ['open',[url]] : ['xdg-open',[url]];
      execFile(app,params,{windowsHide:true},error=>{
        if(error) console.error('Abra o endereco acima no navegador: '+error.message);
      });
    }
    return;
  }
  let browser;
  const reports=[];
  try {
    const [{ chromium }, { default: validator }] = await Promise.all([
      import('playwright'),
      import('gltf-validator')
    ]);
    try {browser=await chromium.launch({channel:'chrome',headless:true});}
    catch {browser=await chromium.launch({headless:true});}
    for(const entry of entries) {
      const page=await browser.newPage({viewport:{width:1000,height:850},deviceScaleFactor:1});
      const errors=[];page.on('pageerror',e=>errors.push(e.message));
      try {
        const load=async exported=>{
          await page.goto(url+'/?id='+encodeURIComponent(entry.id)+(exported?'&file=1':'&source=1'));
          await page.waitForFunction(()=>window.assetReady||window.assetError,{},{timeout:120000});
          const error=await page.evaluate(()=>window.assetError); if(error) throw new Error(error);
        };
        if(command!=='verify') {
          await load(false);
          const pending=page.waitForEvent('download');
          await page.evaluate(()=>window.assetKit.export());
          const download=await pending;
          const destination=inside(project,entry.output);
          await mkdir(path.dirname(destination),{recursive:true});
          await download.saveAs(destination);
        }
        const bytes=await readFile(inside(project,entry.output));
        let gltf;
        if(entry.kind==='glb') {
          gltf=await validator.validateBytes(new Uint8Array(bytes),{uri:entry.output});
          if(gltf.issues.numErrors) throw new Error(JSON.stringify(gltf.issues));
        }
        await load(true);
        const stats=await page.evaluate(()=>window.assetKit.inspect());
        if(errors.length) throw new Error(errors.join('\n'));
        if(entry.kind==='png') {
          if(JSON.stringify(stats.size)!==JSON.stringify(entry.size)||stats.visible===0) throw new Error('Wrong size or empty PNG');
          if(entry.transparent&&!stats.transparent) throw new Error('PNG needs transparent pixels');
        } else {
          if(!stats.finite||!stats.triangles||!stats.size.every(Number.isFinite)) throw new Error('Invalid geometry');
          if(entry.maxTriangles&&stats.triangles>entry.maxTriangles) throw new Error('Triangle budget exceeded');
          if(entry.size&&stats.size.some((v,i)=>Math.abs(v-entry.size[i])>(entry.tolerance??.01))) throw new Error('Size mismatch: '+JSON.stringify(stats.size));
          for(const clip of entry.clips??[]) if(!stats.clips.includes(clip)) throw new Error('Missing clip: '+clip);
        }
        const checks=path.join(project,'asset-workbench/checks');await mkdir(checks,{recursive:true});
        await page.locator('canvas').screenshot({path:path.join(checks,entry.id+'.png')});
        if(gltf) await writeFile(path.join(checks,entry.id+'.gltf.json'),JSON.stringify(gltf,null,2));
        reports.push({id:entry.id,output:entry.output,status:'passed',stats,warnings:gltf?.issues.numWarnings??0,visualReview:'pending'});
        console.log(entry.id+': passed '+JSON.stringify(stats));
      } catch(error) {reports.push({id:entry.id,status:'failed',error:error.message});console.error(entry.id+': '+error.message);}
      finally {await page.close();}
    }
    const checks=path.join(project,'asset-workbench/checks');await mkdir(checks,{recursive:true});
    await writeFile(path.join(checks,'report.json'),JSON.stringify({assets:reports},null,2));
    if(reports.some(r=>r.status==='failed')) process.exitCode=1;
  } finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
}
main().catch(e=>{console.error(e);process.exitCode=1;});
