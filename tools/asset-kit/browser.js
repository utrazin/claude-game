import * as THREE from 'three';

export async function loadManifold() {
  const { default: init } = await import('/vendor/manifold-3d/manifold.js');
  const module = await init({ locateFile: name => '/vendor/manifold-3d/' + name });
  module.setup();
  return module;
}

// Position/index only, one material. UVs and material boundaries require explicit mapping.
export function manifoldGeometry(solid) {
  const mesh = solid.getMesh();
  const positions = new Float32Array(mesh.numVert * 3);
  for (let i = 0; i < mesh.numVert; i++) {
    positions.set(mesh.vertProperties.subarray(i * mesh.numProp, i * mesh.numProp + 3), i * 3);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(mesh.triVerts), 1));
  geometry.computeVertexNormals();
  return geometry;
}

