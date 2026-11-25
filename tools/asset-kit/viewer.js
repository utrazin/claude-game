import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {GLTFExporter} from 'three/addons/exporters/GLTFExporter.js';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {loadManifold,manifoldGeometry} from './browser.js';

// Older running preview servers send CSS as application/octet-stream. Loading the
// local text into a style element keeps upgrades compatible without a restart.
const themeResponse=await fetch('/kit/viewer.css');
if(!themeResponse.ok)throw new Error('Nao foi possivel carregar o tema do visualizador.');
const theme=document.createElement('style');
theme.id='asset-viewer-theme';theme.textContent=await themeResponse.text();document.head.append(theme);

const params=new URLSearchParams(location.search);
const menu=document.querySelector('#assets'),mode=document.querySelector('#mode');
const status=document.querySelector('#status'),stats=document.querySelector('#stats');
mode.value=params.has('source')?'source':params.has('file')?'file':'auto';
let config,entry,root,clips=[],canvas=document.querySelector('canvas'),renderer,scene,camera,controls,mixer;
let generation=0,viewKind,revision=0;
const stage=document.querySelector('.stage');
function fitViewport() {
  if(!renderer||!camera)return;
  const {width,height}=stage.getBoundingClientRect();
  if(!width||!height)return;
  renderer.setSize(Math.round(width),Math.round(height),false);
  camera.aspect=width/height;camera.updateProjectionMatrix();
}
new ResizeObserver(fitViewport).observe(stage);
function renderTree() {
  const tree={children:new Map(),files:[]};
  const query=document.querySelector('#asset-search').value.trim().toLowerCase();
  const items=config.assets.filter(a=>(a.output+' '+a.id).toLowerCase().includes(query));
  for(const item of items){const parts=item.output.split('/');let node=tree;for(const folder of parts.slice(0,-1)){if(!node.children.has(folder))node.children.set(folder,{children:new Map(),files:[]});node=node.children.get(folder);}node.files.push(item);}
  function contents(node){const fragment=document.createDocumentFragment();for(const [name,child] of node.children){const details=document.createElement('details');details.className='folder';details.open=true;const summary=document.createElement('summary');const icon=document.createElement('span');icon.className='folder-icon';icon.textContent='▱';summary.append(icon,document.createTextNode(name));const children=document.createElement('div');children.className='folder-children';children.append(contents(child));details.append(summary,children);fragment.append(details);}for(const item of node.files){const button=document.createElement('button');button.type='button';button.className='file';button.dataset.id=item.id;button.dataset.kind=item.kind;button.setAttribute('aria-current',String(item.id===menu.value));button.title=item.output;const icon=document.createElement('span');icon.className='file-icon';icon.textContent=item.kind.toUpperCase();const label=document.createElement('span');label.className='file-name';label.textContent=item.output.split('/').at(-1);button.append(icon,label);button.onclick=()=>{menu.value=item.id;load();};fragment.append(button);}return fragment;}
  document.querySelector('#file-tree').replaceChildren(contents(tree));
  if(!items.length){const empty=document.createElement('p');empty.className='no-files';empty.textContent='Nenhum asset encontrado.';document.querySelector('#file-tree').append(empty);}
  document.querySelector('#asset-count').textContent=config.assets.length;
}
document.querySelector('#asset-search').oninput=renderTree;
function dispose(object) {
  const textures=new Set(),materials=new Set(),geometries=new Set();
  object?.traverse(o=>{if(o.geometry)geometries.add(o.geometry);for(const m of o.material?(Array.isArray(o.material)?o.material:[o.material]):[])materials.add(m);});
  for(const m of materials) {for(const value of Object.values(m))if(value?.isTexture)textures.add(value);m.dispose();}
  for(const t of textures)t.dispose();for(const g of geometries)g.dispose();
}
function newCanvas(kind) {
  if(viewKind===kind)return;
  controls?.dispose();controls=null;renderer?.dispose();renderer=null;
  const next=document.createElement('canvas');canvas.replaceWith(next);canvas=next;
  viewKind=kind;canvas.dataset.kind=kind;scene=camera=null;
}
function show3D(object,animations,preserve) {
  newCanvas('glb');
  renderer??=new THREE.WebGLRenderer({canvas,antialias:true,preserveDrawingBuffer:true});
  renderer.setPixelRatio(1);renderer.setSize(800,600,false);
  const box=new THREE.Box3().setFromObject(object);
  if(box.isEmpty())throw new Error('Empty asset');
  mixer?.stopAllAction();if(mixer&&root)mixer.uncacheRoot(root);
  dispose(root);root=object;clips=animations;
  scene=new THREE.Scene();scene.background=new THREE.Color(getComputedStyle(document.documentElement).getPropertyValue('--stage').trim()||'#1d1d1d');
  scene.add(new THREE.HemisphereLight(0xffffff,0x605545,2));
  const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(4,6,3);scene.add(light,root);
  if(!camera||!preserve) {
    const center=box.getCenter(new THREE.Vector3());
    const radius=Math.max(...box.getSize(new THREE.Vector3()).toArray(),.1);
    camera=new THREE.PerspectiveCamera(40,800/600,radius/100,radius*100);
    camera.position.copy(center).add(new THREE.Vector3(1.7,1.1,2).multiplyScalar(radius));
    controls?.dispose();controls=new OrbitControls(camera,canvas);controls.target.copy(center);controls.update();
  }
  mixer=clips.length?new THREE.AnimationMixer(root):null;
  if(mixer)mixer.clipAction(clips[0]).play();
  fitViewport();
}
async function refreshList() {
  const response=await fetch('/project/asset-workbench/assets.json');
  if(!response.ok)throw new Error('Lista de assets indisponivel');
  const next=await response.json();
  if(!Array.isArray(next.assets))throw new Error('Lista de assets invalida');
  const selected=menu.value||params.get('id');
  config=next;menu.replaceChildren(...config.assets.map(a=>new Option(a.id,a.id)));
  menu.value=config.assets.some(a=>a.id===selected)?selected:config.assets[0]?.id??'';
  renderTree();
}
async function load(preserve=false) {
  const token=++generation;
  const selected=config.assets.find(a=>a.id===menu.value);
  window.assetReady=false;window.assetError=null;
  if(!selected) {dispose(root);root=null;scene?.clear();newCanvas('png');canvas.getContext('2d').clearRect(0,0,canvas.width,canvas.height);entry=null;status.textContent='Nenhum asset listado.';return;}
  status.textContent='Atualizando '+selected.id+'…';
  const stamp=Date.now()+'-'+token;
  try {
    let fromFile=mode.value==='file',object,animations=[],image,paint;
    if(mode.value==='auto')fromFile=(await fetch('/project/'+selected.output,{method:'HEAD'})).ok;
    if(fromFile) {
      if(selected.kind==='glb') {const gltf=await new GLTFLoader().loadAsync('/project/'+selected.output+'?v='+stamp);object=gltf.scene;animations=gltf.animations;}
      else {image=new Image();image.src='/project/'+selected.output+'?v='+stamp;await image.decode();}
    } else {
      const {build}=await import('/project/'+selected.source+'?v='+stamp);
      if(selected.kind==='glb') {const built=await build({THREE,loadManifold,manifoldGeometry});object=built.object??built;animations=built.clips??[];}
      else {paint=document.createElement('canvas');[paint.width,paint.height]=selected.size;await build({canvas:paint,ctx:paint.getContext('2d')});}
    }
    if(token!==generation) {dispose(object);return;}
    if(selected.kind==='glb')show3D(object,animations,preserve&&entry?.id===selected.id);
    else {
      mixer?.stopAllAction();mixer=null;dispose(root);root=null;clips=[];newCanvas('png');
      const source=image??paint;canvas.width=source.width;canvas.height=source.height;canvas.getContext('2d').drawImage(source,0,0);
    }
    entry=selected;
    document.querySelector('#asset-name').textContent=entry.output.split('/').at(-1);
    document.querySelectorAll('.file').forEach(button=>button.setAttribute('aria-current',String(button.dataset.id===entry.id)));
    const url=new URL(location.href);url.searchParams.set('id',entry.id);
    url.searchParams.delete('source');url.searchParams.delete('file');
    if(mode.value==='source')url.searchParams.set('source','1');
    if(mode.value==='file')url.searchParams.set('file','1');
    history.replaceState(null,'',url);
    window.assetReady=true;revision++;
    status.textContent=entry.id+' — '+(fromFile?'arquivo exportado':'fonte')+' — atualizado '+new Date().toLocaleTimeString();
    const measured=await inspect();
    stats.textContent=JSON.stringify(measured,null,2);
    document.querySelector('#asset-kind').textContent=entry.kind.toUpperCase();
    const rows=[['Nome',entry.id],['Formato',entry.kind.toUpperCase()],['Dimensões',measured.size.map(n=>Number(n.toFixed(3))).join(' × ')+(entry.kind==='png'?' px':' un.')],['Arquivo',entry.output]];
    if(entry.kind==='glb')rows.push(['Triângulos',measured.triangles.toLocaleString('pt-BR')],['Animações',measured.clips.length?measured.clips.join(', '):'Nenhuma']);
    else rows.push(['Pixels visíveis',measured.visible.toLocaleString('pt-BR')],['Transparência',measured.transparent?'Sim':'Não']);
    document.querySelector('#properties').replaceChildren(...rows.flatMap(([key,value])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=value;return [dt,dd];}));
  } catch(error) {
    if(token!==generation)return;
    window.assetError=error.stack??String(error);
    status.textContent='Falha ao atualizar; a ultima visualizacao foi mantida. '+error.message;
  }
}
async function inspect() {
  if(entry.kind==='png') {
    const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
    let visible=0,transparent=0;for(let i=3;i<pixels.length;i+=4){if(pixels[i])visible++;if(!pixels[i])transparent++;}
    return {size:[canvas.width,canvas.height],visible,transparent};
  }
  let triangles=0,finite=true;
  root.traverse(o=>{if(o.isMesh){const g=o.geometry;triangles+=(g.index?.count??g.attributes.position.count)/3;for(const a of Object.values(g.attributes))for(const v of a.array)if(!Number.isFinite(v))finite=false;}});
  return {size:new THREE.Box3().setFromObject(root).getSize(new THREE.Vector3()).toArray(),triangles,finite,clips:clips.map(c=>c.name)};
}
window.assetKit={inspect,get revision(){return revision;},get cameraPosition(){return camera?.position.toArray();},
  async export(){
    let blob;
    if(entry.kind==='glb')blob=new Blob([await new GLTFExporter().parseAsync(root,{binary:true,animations:clips})],{type:'model/gltf-binary'});
    else blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
    if(!blob)throw new Error('Export returned no data');
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=entry.output.split('/').at(-1);a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  }
};
menu.onchange=()=>load();mode.onchange=()=>load(true);
document.querySelector('#download').onclick=()=>window.assetKit.export().catch(e=>{status.textContent=e.message;});
let previous=0;
function frame(time){requestAnimationFrame(frame);if(renderer&&scene&&camera){mixer?.update(Math.min((time-previous)/1000,.1));controls?.update();renderer.render(scene,camera);}previous=time;}
requestAnimationFrame(frame);
await refreshList();await load();
const events=new EventSource('/__asset-kit/events');
let timer,connected=false;
events.onmessage=event=>{
  const change=JSON.parse(event.data);
  if(change.connected&&!connected){connected=true;return;}
  clearTimeout(timer);
  timer=setTimeout(async()=>{
    try {
      const old=entry;await refreshList();
      if(change.connected||change.paths.includes('asset-workbench/assets.json')||change.paths.some(p=>p===old?.output||p===old?.source)) {
        await load(true);
        // A download may briefly expose an incomplete file; retry without replacing the page.
        if(window.assetError)setTimeout(()=>load(true),600);
      }
    } catch(e){status.textContent='Aguardando lista de assets valida: '+e.message;}
  },180);
};
window.addEventListener('beforeunload',()=>events.close());
