/**
 * Reference Plane for NoctAssetForge3D Model Viewer
 * Manages reference image loading, orientation, opacity and alignment.
 */

class ReferencePlane {
    /**
     * @param {THREE.Scene} scene
     */
    constructor(scene) {
        this.scene = scene;
        this.mesh = null;
        this.texture = null;
        this.aspectRatio = 1.0;

        // Current parameters
        this.visible = false;
        this.opacity = 0.5;
        this.mode = "backdrop"; // "backdrop" | "overlay"
        this.view = "front";    // "front" | "side" | "top"
        this.scale = 1.0;
        this.offset = [0, 0, 0];
        this.bbox = null;
    }

    /**
     * Loads a reference image from URL or data URI.
     * @param {string} src
     * @returns {Promise<boolean>}
     */
    async load(src) {
        return new Promise((resolve) => {
            if (!src) {
                this.remove();
                resolve(false);
                return;
            }

            const loader = new THREE.TextureLoader();
            loader.load(
                src,
                (texture) => {
                    this.texture = texture;
                    this.texture.minFilter = THREE.LinearFilter;
                    this.texture.magFilter = THREE.LinearFilter;

                    const img = texture.image;
                    this.aspectRatio = img.width && img.height ? img.width / img.height : 1.0;
                    this.visible = true;
                    this.update();
                    resolve(true);
                },
                undefined,
                (err) => {
                    console.warn("Failed to load reference image:", err);
                    resolve(false);
                }
            );
        });
    }

    /**
     * Updates reference plane geometry and placement based on model bounds and settings.
     * @param {Object} [bbox]
     */
    update(bbox = null) {
        if (bbox) this.bbox = bbox;
        if (!this.texture || !this.visible) {
            if (this.mesh) this.mesh.visible = false;
            return;
        }

        const modelHeight = this.bbox ? this.bbox.size[1] : 20;
        const center = this.bbox ? this.bbox.center : [0, 10, 0];

        // Reference plane height matches model height * scale
        const planeH = Math.max(modelHeight * this.scale, 1);
        const planeW = planeH * this.aspectRatio;

        if (this.mesh) {
            this.scene.remove(this.mesh);
            if (this.mesh.geometry) this.mesh.geometry.dispose();
            if (this.mesh.material) this.mesh.material.dispose();
            this.mesh = null;
        }

        const geometry = new THREE.PlaneGeometry(planeW, planeH);
        const material = new THREE.MeshBasicMaterial({
            map: this.texture,
            transparent: true,
            opacity: this.opacity,
            side: THREE.DoubleSide,
            depthWrite: false,
            depthTest: this.mode === "backdrop"
        });

        this.mesh = new THREE.Mesh(geometry, material);
        this.mesh.renderOrder = this.mode === "overlay" ? 999 : -1;

        // Position according to view and mode
        let posX = center[0] + this.offset[0];
        let posY = center[1] + this.offset[1];
        let posZ = center[2] + this.offset[2];

        if (this.view === "left") {
            this.mesh.rotation.set(0, Math.PI / 2, 0);
            if (this.mode === "backdrop") {
                posX = this.bbox ? this.bbox.max[0] + 0.2 : 10;
            }
        } else if (this.view === "side" || this.view === "right") {
            this.mesh.rotation.set(0, Math.PI / 2, 0);
            if (this.mode === "backdrop") {
                posX = this.bbox ? this.bbox.min[0] - 0.2 : -10;
            }
        } else if (this.view === "top") {
            this.mesh.rotation.set(-Math.PI / 2, 0, 0);
            if (this.mode === "backdrop") {
                posY = this.bbox ? this.bbox.min[1] - 0.2 : -0.2;
            }
        } else if (this.view === "bottom") {
            this.mesh.rotation.set(Math.PI / 2, 0, 0);
            if (this.mode === "backdrop") {
                posY = this.bbox ? this.bbox.max[1] + 0.2 : 20;
            }
        } else if (this.view === "back") {
            this.mesh.rotation.set(0, 0, 0);
            if (this.mode === "backdrop") {
                posZ = this.bbox ? this.bbox.max[2] + 0.2 : 10;
            }
        } else {
            // "front" or default
            this.mesh.rotation.set(0, 0, 0);
            if (this.mode === "backdrop") {
                posZ = this.bbox ? this.bbox.min[2] - 0.2 : -10;
            }
        }

        posX += this.offset[0];
        posY += this.offset[1];
        posZ += this.offset[2];

        this.mesh.position.set(posX, posY, posZ);
        this.mesh.visible = this.visible;
        this.scene.add(this.mesh);
    }

    setOpacity(val) {
        this.opacity = Math.max(0, Math.min(1, val));
        if (this.mesh && this.mesh.material) {
            this.mesh.material.opacity = this.opacity;
            this.mesh.material.needsUpdate = true;
        }
    }

    setMode(mode) {
        this.mode = mode; // "backdrop" | "overlay"
        this.update();
    }

    setView(view) {
        this.view = view;
        this.update();
    }

    setScale(scale) {
        this.scale = scale;
        this.update();
    }

    setOffset(offset) {
        this.offset = offset;
        this.update();
    }

    setVisible(visible) {
        this.visible = visible;
        if (this.mesh) this.mesh.visible = visible;
    }

    remove() {
        if (this.mesh) {
            this.scene.remove(this.mesh);
            if (this.mesh.geometry) this.mesh.geometry.dispose();
            if (this.mesh.material) this.mesh.material.dispose();
            this.mesh = null;
        }
        this.visible = false;
        this.texture = null;
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { ReferencePlane };
}
