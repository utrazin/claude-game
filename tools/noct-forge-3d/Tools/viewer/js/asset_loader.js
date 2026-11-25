/**
 * Shared Asset Loader for NoctAssetForge3D.
 * Loads Blockbench .bbmodel files and glTF/GLB files into a unified LoadedAsset interface.
 */

(function (global) {
    function getBBModelParser() {
        if (typeof BBModelParser !== "undefined") return BBModelParser;
        if (global.BBModelParser) return global.BBModelParser;
        if (typeof require === "function") {
            try { return require("./bbmodel_parser.js").BBModelParser; } catch (e) {}
        }
        return null;
    }

    function getAnimationPlayer() {
        if (typeof AnimationPlayer !== "undefined") return AnimationPlayer;
        if (global.AnimationPlayer) return global.AnimationPlayer;
        if (typeof require === "function") {
            try { return require("./animation_player.js").AnimationPlayer; } catch (e) {}
        }
        return null;
    }

    function computeBoundingBox(object) {
        object.updateMatrixWorld(true);
        const box = new THREE.Box3().setFromObject(object);
        if (box.isEmpty()) {
            box.min.set(-1, -1, -1);
            box.max.set(1, 1, 1);
        }
        const center = new THREE.Vector3();
        const size = new THREE.Vector3();
        box.getCenter(center);
        box.getSize(size);
        return {
            box: box,
            min: [box.min.x, box.min.y, box.min.z],
            max: [box.max.x, box.max.y, box.max.z],
            center: [center.x, center.y, center.z],
            size: [size.x, size.y, size.z],
            maxDimension: Math.max(size.x, size.y, size.z)
        };
    }

    class BBModelClipController {
        constructor(parser, animations = [], onTime = null) {
            this.parser = parser;
            this.animations = animations || [];
            this.names = this.animations.map(a => a.name);
            const PlayerClass = getAnimationPlayer();
            if (!PlayerClass) throw new Error("AnimationPlayer is not available");
            this.player = new PlayerClass(parser, this.animations, onTime || (() => {}));
        }

        get speed() { return this.player.speed; }
        set speed(value) { this.player.speed = value; }
        get repeat() { return this.player.repeat; }
        set repeat(value) { this.player.repeat = value; }
        basePose() { this.player.basePose(); }
        get clip() { return this.player.clip; }
        get time() { return this.player.time; }
        get playing() { return this.player.playing; }
        get length() { return this.player.clip ? (this.player.clip.length || 0) : 0; }
        get onTime() { return this.player.onTime; }
        set onTime(fn) { this.player.onTime = fn; }

        select(name) {
            this.player.select(name);
        }

        play() {
            this.player.play();
        }

        pause() {
            this.player.pause();
        }

        seek(time) {
            this.player.seek(time);
        }

        dispose() {
            this.player.dispose();
        }
    }

    class GlbClipController {
        constructor(rootObject, animations = [], onTime = null) {
            this.rootObject = rootObject;
            this.animations = animations || [];
            this.names = this.animations.map(a => a.name);
            this.onTime = onTime || (() => {});
            this.mixer = new THREE.AnimationMixer(rootObject);
            this.currentAction = null;
            this.currentClip = null;
            this.speed = 1; this.repeat = 'original';
            this.playing = false;
            this.time = 0;
            this.previousFrame = null;
            this._frame = this._frame.bind(this);
            this.frameId = requestAnimationFrame(this._frame);
        }

        get length() {
            return this.currentClip ? (this.currentClip.duration || 0) : 0;
        }

        get clip() {
            return this.currentClip;
        }

        select(name) {
            const clip = this.animations.find(a => a.name === name);
            if (!clip) return;
            if (this.currentAction) {
                this.currentAction.stop();
            }
            this.currentClip = clip;
            this.currentAction = this.mixer.clipAction(clip);
            this.currentAction.setLoop(THREE.LoopOnce, 1);
            this.currentAction.clampWhenFinished = true;
            this.currentAction.play();
            this.playing = false;
            this.seek(0);
        }

        play() {
            if (!this.currentClip || !this.currentAction) return;
            if (this.time >= this.length) this.seek(0);
            this.playing = true;
            this.previousFrame = null;
            this.onTime(this.time);
        }

        pause() {
            this.playing = false;
            this.previousFrame = null;
            this.onTime(this.time);
        }
        basePose() {
            this.pause(); this.mixer.stopAllAction();
            this.currentAction = null; this.currentClip = null; this.time = 0; this.onTime(0);
        }

        seek(time) {
            if (!this.currentClip || !this.currentAction) return;
            const dur = this.length || 0;
            this.time = Math.max(0, dur > 0 ? Math.min(Number(time) || 0, dur) : 0);
            this.currentAction.enabled = true;
            this.currentAction.paused = false;
            this.currentAction.time = this.time;
            this.mixer.update(0);
            this.onTime(this.time);
        }

        _frame(now) {
            if (this.playing && this.currentClip && this.currentAction) {
                if (this.previousFrame !== null) {
                    const delta = (now - this.previousFrame) / 1000;
                    let next = this.time + delta * this.speed;
                    const dur = this.length;
                    if (dur > 0 && next >= dur) {
                        if (this.repeat === 'once') { next = dur; this.pause(); }
                        else next %= dur;
                    }
                    this.seek(next);
                }
                this.previousFrame = now;
            } else {
                this.previousFrame = null;
            }
            this.frameId = requestAnimationFrame(this._frame);
        }

        dispose() {
            cancelAnimationFrame(this.frameId);
            if (this.mixer) this.mixer.stopAllAction();
        }
    }

    class LoadedAsset {
        constructor({ kind, object, bbox, clips, parser = null, modelData = null, gltf = null }) {
            this.kind = kind;
            this.object = object;
            this.bbox = bbox;
            this.clips = clips;
            this.parser = parser;
            this.modelData = modelData;
            this.gltf = gltf;

            this.wireframe = false;
            this.shaded = true;
            this.textureFilter = "nearest";
            this.textureVisible = true;
        }

        setTextureVisible(visible) {
            this.textureVisible = visible;
            this.object.traverse(child => {
                const materials = [child.material, child.userData?.originalMaterial].flat().filter(Boolean);
                for (const material of materials) {
                    if (!Object.prototype.hasOwnProperty.call(material.userData, 'forgeTexture')) material.userData.forgeTexture = material.map || null;
                    material.map = visible ? material.userData.forgeTexture : null;
                    material.needsUpdate = true;
                }
            });
        }

        setWireframe(enabled) {
            this.wireframe = Boolean(enabled);
            this.object.traverse(child => {
                if (child.isMesh && child.material) {
                    const mats = Array.isArray(child.material) ? child.material : [child.material];
                    for (const m of mats) {
                        m.wireframe = this.wireframe;
                    }
                }
                if (child.isLineSegments) {
                    child.visible = this.wireframe;
                }
            });
        }

        setShading(shaded) {
            this.shaded = Boolean(shaded);
            if (this.kind === "bbmodel" && this.parser) {
                const hasTexture = Boolean(this.parser.texture);
                const MatClass = this.shaded ? THREE.MeshStandardMaterial : THREE.MeshBasicMaterial;
                const newMaterials = new Map();
                for (let i = 0; i < Math.max(1, this.parser.textureList.length); i++) {
                    const matOpts = {
                        color: hasTexture ? 0xffffff : (this.shaded ? 0xdedede : 0xcccccc),
                        map: this.parser.textureList[i] || this.parser.texture || null,
                        side: this.parser.texturesInfo[i]?.render_sides === 'front' ? THREE.FrontSide : THREE.DoubleSide,
                        transparent: true,
                        alphaTest: 0.05,
                        wireframe: this.wireframe
                    };
                    if (this.shaded) {
                        matOpts.roughness = 0.8;
                        matOpts.metalness = 0.1;
                    }
                    const mat = new MatClass(matOpts);
                    newMaterials.set(i, mat);
                }
                this.parser.materials = newMaterials;
                this.parser.defaultMaterial = newMaterials.get(0);
                const matArray = Array.from(newMaterials.values());
                this.object.traverse(child => {
                    if (child.isMesh && Array.isArray(child.material)) {
                        child.material = matArray;
                    }
                });
            } else if (this.kind === "glb") {
                this.object.traverse(child => {
                    if (child.isMesh && child.userData.originalMaterial) {
                        if (this.shaded) {
                            child.material = child.userData.originalMaterial;
                            const mats = Array.isArray(child.material) ? child.material : [child.material];
                            for (const m of mats) m.wireframe = this.wireframe;
                        } else {
                            const orig = child.userData.originalMaterial;
                            const origArray = Array.isArray(orig) ? orig : [orig];
                            const basicMats = origArray.map(m => new THREE.MeshBasicMaterial({
                                map: m.userData.forgeTexture || m.map || null,
                                color: m.color || 0xffffff,
                                transparent: m.transparent ?? true,
                                alphaTest: m.alphaTest ?? 0.05,
                                side: THREE.DoubleSide,
                                wireframe: this.wireframe
                            }));
                            child.material = Array.isArray(orig) ? basicMats : basicMats[0];
                        }
                    }
                });
            }
        }

        setTextureFilter(filter) {
            this.textureFilter = filter === "linear" ? "linear" : "nearest";
            if (this.kind === "bbmodel" && this.parser) {
                this.parser.setTextureFilter(this.textureFilter);
            } else {
                const linear = this.textureFilter === "linear";
                this.object.traverse(child => {
                    if (child.isMesh && child.material) {
                        const mats = Array.isArray(child.material) ? child.material : [child.material];
                        for (const m of mats) {
                            if (m.map) {
                                m.map.magFilter = linear ? THREE.LinearFilter : THREE.NearestFilter;
                                m.map.minFilter = linear ? THREE.LinearMipmapLinearFilter : THREE.NearestFilter;
                                m.map.generateMipmaps = linear;
                                m.map.needsUpdate = true;
                            }
                        }
                    }
                });
            }
        }

        dispose() {
            if (this.clips) {
                this.clips.dispose();
            }
            const materials = new Set();
            const textures = new Set();
            this.object.traverse(child => {
                if (child.geometry) child.geometry.dispose();
                if (child.material) {
                    const mats = Array.isArray(child.material) ? child.material : [child.material];
                    for (const m of mats) {
                        materials.add(m);
                        if (m.map) textures.add(m.map);
                        if (m.userData.forgeTexture) textures.add(m.userData.forgeTexture);
                    }
                }
                if (child.userData?.originalMaterial) {
                    const orig = Array.isArray(child.userData.originalMaterial) ? child.userData.originalMaterial : [child.userData.originalMaterial];
                    for (const m of orig) {
                        materials.add(m);
                        if (m.map) textures.add(m.map);
                        if (m.userData.forgeTexture) textures.add(m.userData.forgeTexture);
                    }
                }
            });
            for (const mat of materials) mat.dispose();
            for (const tex of textures) tex.dispose();
            if (this.parser && this.parser.textureList) {
                for (const tex of this.parser.textureList) if (tex) tex.dispose();
            }
            if (this.object.parent) {
                this.object.parent.remove(this.object);
            }
        }
    }

    async function loadBBModelAsset(source, options = {}) {
        let modelData = source.modelData;
        if (!modelData && source.modelUrl) {
            const resp = await fetch(source.modelUrl, { cache: "no-store" });
            if (!resp.ok) throw new Error(`BBModel fetch failed: HTTP ${resp.status}`);
            modelData = await resp.json();
        }
        if (!modelData) throw new Error("BBModel source requires modelData or modelUrl");

        const textureInput = source.textureData || source.textureUrl || null;
        const ParserClass = getBBModelParser();
        if (!ParserClass) throw new Error("BBModelParser is not available");
        const parser = new ParserClass(modelData, textureInput);
        if (options.textureFilter) {
            parser.textureFilter = options.textureFilter;
        }
        await parser.loadTexture();

        const rootObject = parser.buildScene({
            wireframe: options.wireframe ?? false,
            shading: options.shading ?? true
        });

        const rawBbox = parser.getBoundingBox ? parser.getBoundingBox() : null;
        let bboxObject;
        if (rawBbox && Array.isArray(rawBbox.min) && Array.isArray(rawBbox.max)) {
            const minVec = new THREE.Vector3(...rawBbox.min);
            const maxVec = new THREE.Vector3(...rawBbox.max);
            bboxObject = {
                min: rawBbox.min,
                max: rawBbox.max,
                center: rawBbox.center,
                size: rawBbox.size,
                maxDimension: Math.max(...rawBbox.size),
                box: new THREE.Box3(minVec, maxVec)
            };
        } else {
            bboxObject = computeBoundingBox(rootObject);
        }

        const animations = modelData.animations || [];
        const clips = new BBModelClipController(parser, animations, options.onTime);

        const asset = new LoadedAsset({
            kind: "bbmodel",
            object: rootObject,
            bbox: bboxObject,
            clips: clips,
            parser: parser,
            modelData: modelData
        });

        if (options.wireframe) asset.setWireframe(true);
        if (options.shading === false) asset.setShading(false);
        if (options.textureFilter) asset.setTextureFilter(options.textureFilter);

        return asset;
    }

    async function loadGLBAsset(source, options = {}) {
        if (typeof THREE.GLTFLoader === "undefined") {
            throw new Error("THREE.GLTFLoader is not available");
        }
        const loader = new THREE.GLTFLoader();

        let gltf;
        if (source.url) {
            gltf = await new Promise((resolve, reject) => {
                loader.load(source.url, resolve, undefined, reject);
            });
        } else if (source.buffer || source.data) {
            const buffer = source.buffer || source.data;
            gltf = await new Promise((resolve, reject) => {
                loader.parse(buffer, "", resolve, reject);
            });
        } else {
            throw new Error("GLB source requires url, buffer or data");
        }

        const rootObject = gltf.scene || (gltf.scenes && gltf.scenes[0]) || new THREE.Group();
        rootObject.name = rootObject.name || "glb_root";

        rootObject.traverse(child => {
            if (child.isBone) {
                child.userData.kind = "bone";
            } else if (child.isSkinnedMesh) {
                child.userData.kind = "mesh";
                child.userData.isSkinned = true;
            } else if (child.isMesh) {
                child.userData.kind = "mesh";
            } else if (child.isGroup) {
                child.userData.kind = "group";
            }
            if (!child.userData.uuid) {
                child.userData.uuid = child.uuid;
            }

            if (child.isMesh && child.material) {
                child.userData.originalMaterial = child.material;
            }
        });

        const bboxObject = computeBoundingBox(rootObject);
        const clips = new GlbClipController(rootObject, gltf.animations || [], options.onTime);

        const asset = new LoadedAsset({
            kind: "glb",
            object: rootObject,
            bbox: bboxObject,
            clips: clips,
            gltf: gltf
        });

        if (options.wireframe) asset.setWireframe(true);
        if (options.shading === false) asset.setShading(false);
        if (options.textureFilter) asset.setTextureFilter(options.textureFilter);

        return asset;
    }

    function loadAssetObject(source, options = {}) {
        if (!source || !source.kind) {
            return Promise.reject(new Error("loadAssetObject requires source with kind ('bbmodel' | 'glb')"));
        }
        if (source.kind === "bbmodel") {
            return loadBBModelAsset(source, options);
        } else if (source.kind === "glb") {
            return loadGLBAsset(source, options);
        } else {
            return Promise.reject(new Error(`Unsupported asset kind: ${source.kind}`));
        }
    }

    global.BBModelClipController = BBModelClipController;
    global.GlbClipController = GlbClipController;
    global.LoadedAsset = LoadedAsset;
    global.loadAssetObject = loadAssetObject;
    global.AssetLoader = {
        computeBoundingBox,
        BBModelClipController,
        GlbClipController,
        LoadedAsset,
        loadAssetObject
    };

    if (typeof module !== "undefined" && module.exports) {
        module.exports = {
            computeBoundingBox,
            BBModelClipController,
            GlbClipController,
            LoadedAsset,
            loadAssetObject,
            AssetLoader: global.AssetLoader
        };
    }
})(typeof window !== "undefined" ? window : globalThis);
