/**
 * BBModel Three.js Parser
 * Converts Blockbench .bbmodel JSON into Three.js Object3D hierarchies.
 * Supports cubes, free polygonal meshes, nearest or linear texture filtering, and ZYX Euler rotations.
 */

class BBModelParser {
    /**
     * @param {Object} data - Parsed JSON object of the .bbmodel file
     * @param {string|THREE.Texture} [texture] - Texture image URL, base64 data URI, or preloaded THREE.Texture
     */
    constructor(data, texture = null) {
        this.data = data;
        this.meta = data.meta || {};
        this.res = data.resolution || { width: 16, height: 16 };
        this.texWidth = this.res.width || 16;
        this.texHeight = this.res.height || 16;
        this.texture = null;
        this.textureList = [];
        this.textureErrors = [];
        this.textureInput = texture;
        this.textureFilter = 'nearest';

        this.elements = data.elements || [];
        this.groups = data.groups || [];
        this.outliner = data.outliner || [];
        this.texturesInfo = data.textures || [];
        this.controls = new Map();
        this.meshObjects = new Map();
        this.skinnedMeshes = [];
        this.armatureMeshIds = new Set(this.elements
            .filter(item => item.type === "armature")
            .flatMap(item => item.children || [])
            .filter(id => typeof id === "string"));

        // Materials
        this.materials = new Map();
        this.defaultMaterial = null;
        this.wireframeMaterials = [];
    }

    /**
     * Loads the texture if provided as string or discovers it from .bbmodel metadata.
     * @param {string} [baseUrl] - Base path to resolve relative_path if texture not provided
     * @returns {Promise<THREE.Texture|null>}
     */
    async loadTexture(baseUrl = "") {
        const sources = this.textureInput ? [this.textureInput] : this.texturesInfo.map(texture => {
            if (texture.source?.startsWith('data:image')) return texture.source;
            const path = texture.relative_path;
            return path ? (baseUrl && !path.startsWith('/') ? `${baseUrl}/${path}` : path) : null;
        });
        this.textureList = await Promise.all(sources.map(source => {
            if (source instanceof THREE.Texture) {
                this._configureTexture(source);
                return Promise.resolve(source);
            }
            if (!source) return Promise.resolve(null);
            return new Promise(resolve => new THREE.TextureLoader().load(source, texture => {
                this._configureTexture(texture); resolve(texture);
            }, undefined, () => {
                this.textureErrors.push(`Texture could not be loaded: ${source}`); resolve(null);
            }));
        }));
        this.texture = this.textureList[0] || null;
        return this.texture;
    }

    _configureTexture(tex) {
        const linear = this.textureFilter === 'linear';
        tex.magFilter = linear ? THREE.LinearFilter : THREE.NearestFilter;
        tex.minFilter = linear ? THREE.LinearMipmapLinearFilter : THREE.NearestFilter;
        tex.generateMipmaps = linear;
        tex.needsUpdate = true;
    }

    /** 'nearest' keeps texels crisp (pixel art); 'linear' smooths painted textures. */
    setTextureFilter(mode) {
        this.textureFilter = mode === 'linear' ? 'linear' : 'nearest';
        for (const texture of this.textureList) if (texture) this._configureTexture(texture);
    }

    /**
     * Builds the complete Three.js Object3D hierarchy.
     * @param {Object} [options]
     * @param {boolean} [options.wireframe=false]
     * @param {boolean} [options.shading=true]
     * @returns {THREE.Group}
     */
    buildScene(options = {}) {
        this.controls.clear();
        this.meshObjects.clear();
        this.skinnedMeshes = [];
        const rootGroup = new THREE.Group();
        this.sceneRoot = rootGroup;
        rootGroup.name = this.data.name || "bbmodel_root";
        rootGroup.userData.kind = "group";

        const hasTexture = Boolean(this.texture);
        const doubleSide = true;

        // Base material
        let mat;
        if (options.shading === false) {
            mat = new THREE.MeshBasicMaterial({
                map: hasTexture ? this.texture : null,
                color: hasTexture ? 0xffffff : 0xcccccc,
                side: doubleSide ? THREE.DoubleSide : THREE.FrontSide,
                transparent: true,
                alphaTest: 0.05
            });
        } else {
            mat = new THREE.MeshStandardMaterial({
                map: hasTexture ? this.texture : null,
                color: hasTexture ? 0xffffff : 0xdedede,
                roughness: 0.8,
                metalness: 0.1,
                side: doubleSide ? THREE.DoubleSide : THREE.FrontSide,
                transparent: true,
                alphaTest: 0.05
            });
        }
        this.defaultMaterial = mat;
        this.materials.set(0, mat);
        for (let index = 0; index < this.textureList.length; index++) {
            const material = index ? mat.clone() : mat;
            material.map = this.textureList[index];
            material.side = this.texturesInfo[index]?.render_sides === 'front' ? THREE.FrontSide : THREE.DoubleSide;
            this.materials.set(index, material);
        }

        // Map elements by UUID
        const elementsByUuid = new Map();
        for (const elem of this.elements) {
            if (elem.uuid) {
                elementsByUuid.set(elem.uuid, elem);
            }
        }

        // Map groups by UUID
        const groupsByUuid = new Map();
        for (const grp of this.groups) {
            if (grp.uuid) {
                groupsByUuid.set(grp.uuid, grp);
            }
        }

        // Track elements added via outliner
        const handledElementUuids = new Set();

        // Recursively build outliner tree
        const processNode = (node, parentThreeGroup) => {
            if (typeof node === "string") {
                // Node is an element UUID
                const elem = elementsByUuid.get(node);
                if (elem) {
                    const obj = this._buildElement(elem, options);
                    if (obj) {
                        parentThreeGroup.add(obj);
                        handledElementUuids.add(elem.uuid);
                    }
                }
            } else if (typeof node === "object" && node !== null) {
                const uuid = node.uuid;
                const grpData = groupsByUuid.get(uuid) || elementsByUuid.get(uuid) || node;

                // Group node
                const groupObj = new THREE.Group();
                groupObj.name = grpData.name || "group";
                let nodeKind = "group";
                if (grpData.type === "armature") nodeKind = "armature";
                else if (grpData.type === "armature_bone") nodeKind = "bone";
                groupObj.userData.kind = nodeKind;
                groupObj.userData.uuid = uuid;

                const pivot = grpData.origin || [0, 0, 0];
                const rot = grpData.rotation || [0, 0, 0];

                groupObj.position.set(pivot[0], pivot[1], pivot[2]);
                groupObj.rotation.set(
                    THREE.MathUtils.degToRad(rot[0] || 0),
                    THREE.MathUtils.degToRad(rot[1] || 0),
                    THREE.MathUtils.degToRad(rot[2] || 0),
                    "ZYX"
                );

                // Group origins are pivots; armature bone origins are local joint offsets.
                const childrenContainer = new THREE.Group();
                childrenContainer.userData.internal = true;
                if (grpData.type !== "armature_bone" && grpData.type !== "armature") {
                    childrenContainer.position.set(-pivot[0], -pivot[1], -pivot[2]);
                }
                groupObj.add(childrenContainer);
                if (grpData.type === "armature_bone" || (grpData.type !== "armature" && grpData.model_as_code_role !== "folder")) {
                    this.controls.set(uuid, {
                        object: groupObj,
                        position: groupObj.position.clone(),
                        rotation: groupObj.rotation.clone(),
                        scale: groupObj.scale.clone()
                    });
                }

                if (Array.isArray(node.children)) {
                    for (const child of node.children) {
                        processNode(child, childrenContainer);
                    }
                }

                parentThreeGroup.add(groupObj);
            }
        };

        if (Array.isArray(this.outliner) && this.outliner.length > 0) {
            for (const rootNode of this.outliner) {
                processNode(rootNode, rootGroup);
            }
        }

        // Add any remaining unparented elements
        for (const elem of this.elements) {
            if (!handledElementUuids.has(elem.uuid)) {
                const obj = this._buildElement(elem, options);
                if (obj) {
                    rootGroup.add(obj);
                }
            }
        }

        rootGroup.updateMatrixWorld(true);
        this.rootObject = rootGroup;
        this._prepareSkinning(elementsByUuid);
        return rootGroup;
    }

    _buildElement(elem, options) {
        if (elem.visibility === false) {
            return null;
        }
        if (elem.type === "cube" || (!elem.type && elem.from && elem.to)) {
            return this._buildCube(elem, options);
        } else if (elem.type === "mesh") {
            return this._buildMesh(elem, options);
        }
        return null;
    }

    _buildCube(elem, options) {
        const from = elem.from || [0, 0, 0];
        const to = elem.to || [0, 0, 0];
        const inflate = elem.inflate || 0;
        const origin = elem.origin || [0, 0, 0];
        const rot = elem.rotation || [0, 0, 0];

        const minX = Math.min(from[0], to[0]) - inflate;
        const maxX = Math.max(from[0], to[0]) + inflate;
        const minY = Math.min(from[1], to[1]) - inflate;
        const maxY = Math.max(from[1], to[1]) + inflate;
        const minZ = Math.min(from[2], to[2]) - inflate;
        const maxZ = Math.max(from[2], to[2]) + inflate;

        const positions = [];
        const normals = [];
        const uvs = [];
        const materialGroups = [];

        // Definition of the 6 faces in Blockbench order:
        // [name, normalVector, quadCorners(BL, BR, TR, TL)]
        const faceDefs = [
            {
                name: "north", // -Z
                norm: [0, 0, -1],
                corners: [
                    [maxX, minY, minZ], // BL
                    [minX, minY, minZ], // BR
                    [minX, maxY, minZ], // TR
                    [maxX, maxY, minZ]  // TL
                ]
            },
            {
                name: "south", // +Z
                norm: [0, 0, 1],
                corners: [
                    [minX, minY, maxZ],
                    [maxX, minY, maxZ],
                    [maxX, maxY, maxZ],
                    [minX, maxY, maxZ]
                ]
            },
            {
                name: "west", // -X
                norm: [-1, 0, 0],
                corners: [
                    [minX, minY, minZ],
                    [minX, minY, maxZ],
                    [minX, maxY, maxZ],
                    [minX, maxY, minZ]
                ]
            },
            {
                name: "east", // +X
                norm: [1, 0, 0],
                corners: [
                    [maxX, minY, maxZ],
                    [maxX, minY, minZ],
                    [maxX, maxY, minZ],
                    [maxX, maxY, maxZ]
                ]
            },
            {
                name: "up", // +Y
                norm: [0, 1, 0],
                corners: [
                    [minX, maxY, maxZ],
                    [maxX, maxY, maxZ],
                    [maxX, maxY, minZ],
                    [minX, maxY, minZ]
                ]
            },
            {
                name: "down", // -Y
                norm: [0, -1, 0],
                corners: [
                    [minX, minY, minZ],
                    [maxX, minY, minZ],
                    [maxX, minY, maxZ],
                    [minX, minY, maxZ]
                ]
            }
        ];

        const facesData = elem.faces || {};
        // A cube whose UVs are still pending has no face entries yet: draw all six faces untextured.
        const uvPending = Object.keys(facesData).length === 0;

        const linePositions = [];
        for (const fDef of faceDefs) {
            const faceInfo = facesData[fDef.name];
            if (!uvPending && (!faceInfo || faceInfo.texture === null)) continue;

            const c = fDef.corners;
            const norm = fDef.norm;
            const materialIndex = Number(faceInfo?.texture || 0);
            if (!this.materials.has(materialIndex)) throw new Error(`Unknown face texture ${materialIndex}`);
            const info = this.texturesInfo[materialIndex] || {};
            const tw = info.uv_width || info.width || this.texWidth;
            const th = info.uv_height || info.height || this.texHeight;
            const start = positions.length / 3;

            // Two triangles for the quad: (0, 1, 2) and (0, 2, 3)
            const triIndices = [0, 1, 2, 0, 2, 3];

            // Quad boundary lines: (0,1), (1,2), (2,3), (3,0)
            if (options.wireframe) {
                const quadLoop = [c[0], c[1], c[1], c[2], c[2], c[3], c[3], c[0]];
                for (const p of quadLoop) {
                    linePositions.push(p[0], p[1], p[2]);
                }
            }

            // Calculate UVs
            let faceUvs = [
                [0, 0], [1, 0], [1, 1], [0, 1]
            ];

            if (faceInfo && faceInfo.uv && Array.isArray(faceInfo.uv) && faceInfo.uv.length === 4) {
                const u1 = faceInfo.uv[0] / tw;
                const v1 = 1.0 - (faceInfo.uv[1] / th);
                const u2 = faceInfo.uv[2] / tw;
                const v2 = 1.0 - (faceInfo.uv[3] / th);

                let uvCorners = [
                    [u1, v2], // BL
                    [u2, v2], // BR
                    [u2, v1], // TR
                    [u1, v1]  // TL
                ];

                const rotDeg = faceInfo.rotation || 0;
                const steps = Math.floor(rotDeg / 90) % 4;
                if (steps > 0) {
                    uvCorners = uvCorners.slice(steps).concat(uvCorners.slice(0, steps));
                }
                faceUvs = uvCorners;
            }

            for (const idx of triIndices) {
                const pt = c[idx];
                positions.push(pt[0], pt[1], pt[2]);
                normals.push(norm[0], norm[1], norm[2]);
                const uv = faceUvs[idx];
                uvs.push(uv[0], uv[1]);
            }
            materialGroups.push([start, positions.length / 3 - start, materialIndex]);
        }

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
        geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
        for (const group of materialGroups) geometry.addGroup(...group);

        const mesh = new THREE.Mesh(geometry, Array.from(this.materials.values()));
        mesh.name = elem.name || "cube";
        mesh.userData.kind = "cube";
        mesh.userData.uuid = elem.uuid;

        // Group container for pivot
        const pivotGroup = new THREE.Group();
        pivotGroup.name = `${mesh.name}_pivot`;
        pivotGroup.userData.internal = true;
        pivotGroup.position.set(origin[0], origin[1], origin[2]);
        pivotGroup.rotation.set(
            THREE.MathUtils.degToRad(rot[0] || 0),
            THREE.MathUtils.degToRad(rot[1] || 0),
            THREE.MathUtils.degToRad(rot[2] || 0),
            "ZYX"
        );

        // Child geometry offset by -origin
        mesh.position.set(-origin[0], -origin[1], -origin[2]);
        pivotGroup.add(mesh);

        // Add wireframe outline if requested (render true quad perimeter, not triangulated diagonals)
        if (options.wireframe && linePositions.length > 0) {
            const wireGeo = new THREE.BufferGeometry();
            wireGeo.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
            const wireMat = new THREE.LineBasicMaterial({ color: 0x00ffff, linewidth: 1 });
            const wireMesh = new THREE.LineSegments(wireGeo, wireMat);
            wireMesh.position.copy(mesh.position);
            wireMesh.userData.internal = true;
            pivotGroup.add(wireMesh);
        }

        return pivotGroup;
    }

    _buildMesh(elem, options) {
        const origin = elem.origin || [0, 0, 0];
        const rot = elem.rotation || [0, 0, 0];
        const vertsData = elem.vertices || {};
        const facesData = elem.faces || {};

        const positions = [];
        const normals = [];
        const uvs = [];
        const linePositions = [];
        const vertexKeys = [];
        const materialGroups = [];

        for (const [faceId, face] of Object.entries(facesData)) {
            if (face.texture === null) continue;
            const vertKeys = face.vertices || [];
            if (vertKeys.length < 3) continue;
            const materialIndex = Number(face.texture || 0);
            if (!this.materials.has(materialIndex)) throw new Error(`Unknown face texture ${materialIndex}`);
            const info = this.texturesInfo[materialIndex] || {};
            const tw = info.uv_width || info.width || this.texWidth;
            const th = info.uv_height || info.height || this.texHeight;
            const start = positions.length / 3;

            const facePoints = [];
            const faceUvs = [];
            const faceKeys = [];

            for (const vKey of vertKeys) {
                const pt = vertsData[vKey];
                if (!pt) continue;
                // Mesh vertices are relative to element origin
                facePoints.push([origin[0] + pt[0], origin[1] + pt[1], origin[2] + pt[2]]);
                faceKeys.push(vKey);

                let u = 0, v = 0;
                if (face.uv && face.uv[vKey]) {
                    u = face.uv[vKey][0] / tw;
                    v = 1.0 - (face.uv[vKey][1] / th);
                }
                faceUvs.push([u, v]);
            }

            if (facePoints.length < 3) continue;

            // Collect perimeter line segments for the true polygon face
            if (options.wireframe) {
                const numPts = facePoints.length;
                for (let i = 0; i < numPts; i++) {
                    const pA = facePoints[i];
                    const pB = facePoints[(i + 1) % numPts];
                    linePositions.push(pA[0], pA[1], pA[2]);
                    linePositions.push(pB[0], pB[1], pB[2]);
                }
            }

            // Compute face normal via triangle cross product
            const p0 = facePoints[0], p1 = facePoints[1], p2 = facePoints[2];
            const vA = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]];
            const vB = [p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]];
            const nx = vA[1] * vB[2] - vA[2] * vB[1];
            const ny = vA[2] * vB[0] - vA[0] * vB[2];
            const nz = vA[0] * vB[1] - vA[1] * vB[0];
            const len = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1.0;
            const norm = [nx / len, ny / len, nz / len];

            // Triangulate convex face: (0, i, i+1)
            for (let i = 1; i < facePoints.length - 1; i++) {
                const indices = [0, i, i + 1];
                for (const idx of indices) {
                    const pt = facePoints[idx];
                    positions.push(pt[0], pt[1], pt[2]);
                    normals.push(norm[0], norm[1], norm[2]);
                    const uv = faceUvs[idx];
                    uvs.push(uv[0], uv[1]);
                    vertexKeys.push(faceKeys[idx]);
                }
            }
            materialGroups.push([start, positions.length / 3 - start, materialIndex]);
        }

        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        geometry.setAttribute("normal", new THREE.Float32BufferAttribute(normals, 3));
        geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
        for (const group of materialGroups) geometry.addGroup(...group);

        const mesh = new THREE.Mesh(geometry, Array.from(this.materials.values()));
        mesh.name = elem.name || "mesh";
        mesh.userData.kind = "mesh";
        mesh.userData.uuid = elem.uuid;
        mesh.userData.vertexKeys = vertexKeys;
        this.meshObjects.set(elem.uuid, mesh);

        if (this.armatureMeshIds.has(elem.uuid)) {
            // Weighted vertex coordinates are already in armature bind space.
            return mesh;
        }

        const pivotGroup = new THREE.Group();
        pivotGroup.name = `${mesh.name}_pivot`;
        pivotGroup.userData.internal = true;
        pivotGroup.position.set(origin[0], origin[1], origin[2]);
        pivotGroup.rotation.set(
            THREE.MathUtils.degToRad(rot[0] || 0),
            THREE.MathUtils.degToRad(rot[1] || 0),
            THREE.MathUtils.degToRad(rot[2] || 0),
            "ZYX"
        );

        mesh.position.set(-origin[0], -origin[1], -origin[2]);
        pivotGroup.add(mesh);

        // Add wireframe outline if requested (render true polygon perimeter, not triangulated diagonals)
        if (options.wireframe && linePositions.length > 0) {
            const wireGeo = new THREE.BufferGeometry();
            wireGeo.setAttribute("position", new THREE.Float32BufferAttribute(linePositions, 3));
            const wireMat = new THREE.LineBasicMaterial({ color: 0x00ffff, linewidth: 1 });
            const wireMesh = new THREE.LineSegments(wireGeo, wireMat);
            wireMesh.position.copy(mesh.position);
            wireMesh.userData.internal = true;
            pivotGroup.add(wireMesh);
        }

        return pivotGroup;
    }

    _prepareSkinning(elementsByUuid) {
        const bones = this.elements.filter(item => item.type === "armature_bone");
        const bindInverse = new Map();
        for (const bone of bones) {
            const control = this.controls.get(bone.uuid);
            if (control) bindInverse.set(bone.uuid, control.object.matrixWorld.clone().invert());
        }
        for (const meshId of this.armatureMeshIds) {
            const mesh = this.meshObjects.get(meshId);
            if (!mesh) continue;
            const keys = mesh.userData.vertexKeys;
            const prefix = meshId.slice(0, 6) + ":";
            const influences = keys.map(key => bones.flatMap(bone => {
                const weight = (bone.vertex_weights || {})[prefix + key];
                return weight > 0 && bindInverse.has(bone.uuid) ? [{ uuid: bone.uuid, weight }] : [];
            }));
            if (influences.some(items => items.length === 0)) {
                console.warn(`Incomplete armature weights for ${elementsByUuid.get(meshId)?.name || meshId}`);
                continue;
            }
            this.skinnedMeshes.push({ mesh, bindWorld: mesh.matrixWorld.clone(), original: mesh.geometry.attributes.position.array.slice(),
                                      influences, bindInverse });
        }
    }

    updateSkinning() {
        if (!this.skinnedMeshes.length) return;
        this.rootObject.updateMatrixWorld(true);
        for (const binding of this.skinnedMeshes) {
            const transforms = new Map();
            const inverseMesh = binding.mesh.matrixWorld.clone().invert();
            const attribute = binding.mesh.geometry.attributes.position;
            for (let i = 0; i < binding.influences.length; i++) {
                const original = new THREE.Vector3(binding.original[3*i], binding.original[3*i+1], binding.original[3*i+2]);
                const result = new THREE.Vector3();
                for (const influence of binding.influences[i]) {
                    if (!transforms.has(influence.uuid)) {
                        transforms.set(influence.uuid, inverseMesh.clone()
                            .multiply(this.controls.get(influence.uuid).object.matrixWorld)
                            .multiply(binding.bindInverse.get(influence.uuid)).multiply(binding.bindWorld));
                    }
                    result.add(original.clone().applyMatrix4(transforms.get(influence.uuid)).multiplyScalar(influence.weight));
                }
                attribute.setXYZ(i, result.x, result.y, result.z);
            }
            attribute.needsUpdate = true;
            binding.mesh.geometry.computeVertexNormals();
            binding.mesh.geometry.computeBoundingSphere();
        }
    }

    /**
     * Calculates the rest-pose bounding box of the whole model.
     * @returns {{ min: number[], max: number[], size: number[], center: number[] }}
     */
    getBoundingBox() {
        if (this.rootObject) {
            this.rootObject.updateMatrixWorld(true);
            const box = new THREE.Box3().setFromObject(this.rootObject);
            if (!box.isEmpty()) {
                return {min: box.min.toArray(), max: box.max.toArray(),
                        size: box.getSize(new THREE.Vector3()).toArray(), center: box.getCenter(new THREE.Vector3()).toArray()};
            }
        }
        let minX = Infinity, minY = Infinity, minZ = Infinity;
        let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
        let found = false;

        for (const elem of this.elements) {
            if (elem.type === "cube" || (!elem.type && elem.from && elem.to)) {
                const inflate = elem.inflate || 0;
                minX = Math.min(minX, elem.from[0] - inflate, elem.to[0] - inflate);
                maxX = Math.max(maxX, elem.from[0] + inflate, elem.to[0] + inflate);
                minY = Math.min(minY, elem.from[1] - inflate, elem.to[1] - inflate);
                maxY = Math.max(maxY, elem.from[1] + inflate, elem.to[1] + inflate);
                minZ = Math.min(minZ, elem.from[2] - inflate, elem.to[2] - inflate);
                maxZ = Math.max(maxZ, elem.from[2] + inflate, elem.to[2] + inflate);
                found = true;
            } else if (elem.type === "mesh" && elem.vertices) {
                const ox = (elem.origin && elem.origin[0]) || 0;
                const oy = (elem.origin && elem.origin[1]) || 0;
                const oz = (elem.origin && elem.origin[2]) || 0;
                for (const pt of Object.values(elem.vertices)) {
                    minX = Math.min(minX, ox + pt[0]);
                    maxX = Math.max(maxX, ox + pt[0]);
                    minY = Math.min(minY, oy + pt[1]);
                    maxY = Math.max(maxY, oy + pt[1]);
                    minZ = Math.min(minZ, oz + pt[2]);
                    maxZ = Math.max(maxZ, oz + pt[2]);
                    found = true;
                }
            }
        }

        if (!found) {
            return { min: [0, 0, 0], max: [0, 0, 0], size: [0, 0, 0], center: [0, 0, 0] };
        }

        return {
            min: [minX, minY, minZ],
            max: [maxX, maxY, maxZ],
            size: [maxX - minX, maxY - minY, maxZ - minZ],
            center: [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2]
        };
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { BBModelParser };
}
