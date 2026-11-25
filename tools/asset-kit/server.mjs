import {createServer} from 'node:http';
import {readFile,realpath,stat} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';

export function inside(base, relative) {
  const target=path.resolve(base,relative);
  if(target!==base && !target.startsWith(base+path.sep)) throw new Error('Path escapes root: '+relative);
  return target;
}

export async function serve(project,kit,{persistent=false}={}) {
  const key=process.platform==='win32'?project.toLowerCase():project;
  const clients=new Set();
  let revision=0;
  const types={'.js':'text/javascript','.mjs':'text/javascript','.html':'text/html','.css':'text/css','.json':'application/json','.wasm':'application/wasm','.png':'image/png','.glb':'model/gltf-binary'};
  const server=createServer(async(req,res)=>{try {
    const url=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
    if(url==='/__asset-kit/health') {
      res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});
      return res.end(JSON.stringify({service:'asset-kit-preview-v2',project:key,pid:process.pid}));
    }
    if(url==='/__asset-kit/events') {
      res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','Connection':'keep-alive'});
      res.write(`data: ${JSON.stringify({revision,paths:[],connected:true})}\n\n`);
      clients.add(res);req.on('close',()=>clients.delete(res));return;
    }
    const routes=[['/project/',project],['/vendor/',path.join(kit,'node_modules')],['/kit/',kit]];
    const route=routes.find(([prefix])=>url.startsWith(prefix));
    const base=route?.[1]??kit;
    const file=inside(base,route?url.slice(route[0].length):'index.html');
    inside(await realpath(base),path.relative(await realpath(base),await realpath(file)));
    const data=await readFile(file);
    res.writeHead(200,{'Content-Type':types[path.extname(file)]??'application/octet-stream','Cache-Control':'no-store'});res.end(data);
  } catch {res.writeHead(404);res.end('Not found');}});
  const firstPort=persistent?20000+createHash('sha256').update(key).digest().readUInt32LE(0)%30000:0;
  for(let i=0;i<32;i++) {
    const port=firstPort?firstPort+i:0;
    try {
      await new Promise((resolve,reject)=>{
        server.once('error',reject);server.listen(port,'127.0.0.1',()=>{server.removeListener('error',reject);resolve();});
      });break;
    } catch(error) {
      if(error.code!=='EADDRINUSE') throw error;
      const url=`http://127.0.0.1:${port}`;
      try {
        const health=await (await fetch(url+'/__asset-kit/health',{signal:AbortSignal.timeout(1500)})).json();
        if(health.service==='asset-kit-preview-v2'&&health.project===key) return {server:null,url,reused:true};
      } catch { /* A different service occupies this port. Never terminate it. */ }
      if(i===31) throw new Error('No available asset preview port');
    }
  }
  let previous=new Map(),polling=false;
  async function snapshot() {
    const configPath='asset-workbench/assets.json';
    const text=await readFile(inside(project,configPath),'utf8');
    const config=JSON.parse(text), next=new Map([[configPath,text]]);
    for(const a of config.assets??[]) for(const file of [a.source,a.output].filter(Boolean)) {
      let signature='missing';
      try {const s=await stat(inside(project,file));signature=`${s.mtimeMs}:${s.size}`;} catch {}
      next.set(file,signature);
    }
    return next;
  }
  if(persistent) previous=await snapshot();
  const timer=persistent?setInterval(async()=>{
    if(polling)return;polling=true;
    try {
      const next=await snapshot();
      const paths=[...new Set([...previous.keys(),...next.keys()])].filter(p=>previous.get(p)!==next.get(p));
      previous=next;
      if(paths.length) {
        revision++;
        for(const client of clients)client.write(`data: ${JSON.stringify({revision,paths})}\n\n`);
      }
    } catch { /* Keep the last valid list while an editor is saving JSON. */ }
    finally {polling=false;}
  },650):null;
  const heartbeat=persistent?setInterval(()=>{for(const client of clients)client.write(': heartbeat\n\n');},15000):null;
  server.on('close',()=>{clearInterval(timer);clearInterval(heartbeat);for(const client of clients)client.end();});
  return {server,url:`http://127.0.0.1:${server.address().port}`,reused:false};
}
