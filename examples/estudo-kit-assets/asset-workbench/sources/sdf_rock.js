export async function build({THREE,loadManifold,manifoldGeometry}) {
  const {Manifold}=await loadManifold();
  // Manifold uses POSITIVE inside. Common SDF formulas use the opposite sign.
  const field=([x,y,z])=>.65-Math.hypot(x,y/.75,z/.85)+.045*Math.sin(x*12)*Math.cos(z*9);
  const solid=Manifold.levelSet(field,{min:[-1,-1,-1],max:[1,1,1]},.075);
  try {
    const geometry=manifoldGeometry(solid);
    geometry.computeBoundingBox();geometry.translate(0,-geometry.boundingBox.min.y,0);
    const mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:'#747d70',roughness:1}));
    mesh.name='sdf_rock';return mesh;
  } finally {solid.delete();}
}
