export function build({THREE}) {
  const group=new THREE.Group();group.name='fence';
  const material=new THREE.MeshStandardMaterial({color:'#946137',roughness:1});
  function beam(size,pos) {const mesh=new THREE.Mesh(new THREE.BoxGeometry(...size),material);mesh.position.set(...pos);group.add(mesh);}
  beam([.12,1,.12],[-.94,.5,0]);beam([.12,1,.12],[.94,.5,0]);
  for(const y of [.25,.55,.85]) beam([2,.1,.1],[0,y,0]);
  return group;
}
