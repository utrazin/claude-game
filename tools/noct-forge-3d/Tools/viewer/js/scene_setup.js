/**
 * Scene Setup for NoctAssetForge3D Model Viewer
 * Manages Three.js scene, renderer, lights, grid, perspective & orthographic cameras.
 */

class SceneSetup {
    constructor(container) {
        this.container = container;
        this.width = container.clientWidth || 800;
        this.height = container.clientHeight || 600;

        // Scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x18181b); // Zinc dark

        // Renderer
        this.renderer = new THREE.WebGLRenderer({
            antialias: true,
            alpha: true,
            preserveDrawingBuffer: true // Required for screenshots/canvas capture
        });
        this.renderer.setSize(this.width, this.height);
        this.renderer.setPixelRatio(window.devicePixelRatio || 1);
        this.renderer.shadowMap.enabled = false;
        container.appendChild(this.renderer.domElement);

        // Cameras
        this.currentCameraType = "perspective"; // "perspective" | "orthographic"
        this._initCameras();

        // Controls
        this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;

        // Lighting
        this._initLighting();

        // Helpers
        this._initHelpers();

        // Model container
        this.modelGroup = new THREE.Group();
        this.scene.add(this.modelGroup);

        // Handle resize
        this.resizeHandler = () => this.onResize();
        window.addEventListener("resize", this.resizeHandler);

        // Animation loop
        this._render = this._render.bind(this);
        this.isAnimating = true;
        this.frameId = requestAnimationFrame(this._render);
    }

    _initCameras() {
        const aspect = this.width / this.height;

        // Perspective Camera
        this.perspCamera = new THREE.PerspectiveCamera(40, aspect, 0.1, 2000);
        this.perspCamera.position.set(24, 20, 32);

        // Orthographic Camera
        const frustumSize = 40;
        this.orthoCamera = new THREE.OrthographicCamera(
            (-frustumSize * aspect) / 2,
            (frustumSize * aspect) / 2,
            frustumSize / 2,
            -frustumSize / 2,
            -1000,
            1000
        );
        this.orthoFrustumSize = frustumSize;

        this.camera = this.perspCamera;
    }

    _initLighting() {
        // Ambient light for general soft illumination
        this.ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
        this.scene.add(this.ambientLight);

        // Key light
        this.dirLight1 = new THREE.DirectionalLight(0xffffff, 0.6);
        this.dirLight1.position.set(20, 40, 30);
        this.scene.add(this.dirLight1);

        // Fill light
        this.dirLight2 = new THREE.DirectionalLight(0xaaccff, 0.3);
        this.dirLight2.position.set(-20, -10, -20);
        this.scene.add(this.dirLight2);
    }

    _initHelpers() {
        // Ground grid
        this.gridHelper = new THREE.GridHelper(64, 64, 0x3f3f46, 0x27272a);
        this.gridHelper.position.y = 0;
        this.scene.add(this.gridHelper);

        // Axes helper (RGB -> XYZ)
        this.axesHelper = new THREE.AxesHelper(16);
        this.scene.add(this.axesHelper);
    }

    setCameraType(type) {
        if (type === this.currentCameraType) return;
        this.currentCameraType = type;

        const target = this.controls.target.clone();
        const pos = this.camera.position.clone();

        if (type === "orthographic") {
            this.camera = this.orthoCamera;
        } else {
            this.camera = this.perspCamera;
        }

        this.camera.position.copy(pos);
        this.controls.object = this.camera;
        this.controls.target.copy(target);
        this.controls.update();
    }

    /**
     * Sets camera to a canonical preset view.
     * @param {"front"|"back"|"left"|"right"|"top"|"bottom"|"iso"} view
     * @param {Object} [bbox] - Model bounding box
     */
    setViewPreset(view, bbox = null) {
        const center = bbox ? new THREE.Vector3(...bbox.center) : new THREE.Vector3(0, 0, 0);
        const maxDim = bbox ? Math.max(...bbox.size, 10) : 30;
        const dist = maxDim * 2.2;

        this.controls.target.copy(center);

        if (typeof view === "string" && view.startsWith("orbit:")) {
            const parts = view.substring(6).split(",");
            const yaw = parseFloat(parts[0]) || 0;
            const pitch = parseFloat(parts[1]) || 0;
            const camType = parts[2] || "perspective";
            this.setOrbit(yaw, pitch, bbox, camType);
            return;
        }

        let pos = new THREE.Vector3();
        let up = new THREE.Vector3(0, 1, 0);

        switch (view) {
            case "front":
                pos.set(center.x, center.y, center.z + dist);
                this.setCameraType("orthographic");
                break;
            case "back":
                pos.set(center.x, center.y, center.z - dist);
                this.setCameraType("orthographic");
                break;
            case "right":
                pos.set(center.x + dist, center.y, center.z);
                this.setCameraType("orthographic");
                break;
            case "left":
                pos.set(center.x - dist, center.y, center.z);
                this.setCameraType("orthographic");
                break;
            case "top":
                pos.set(center.x, center.y + dist, center.z + 0.0001);
                up.set(0, 0, -1);
                this.setCameraType("orthographic");
                break;
            case "bottom":
                pos.set(center.x, center.y - dist, center.z + 0.0001);
                up.set(0, 0, 1);
                this.setCameraType("orthographic");
                break;
            case "iso":
            default:
                pos.set(center.x + dist * 0.7, center.y + dist * 0.6, center.z + dist * 0.7);
                this.setCameraType("perspective");
                break;
        }

        this.camera.up.copy(up);
        this.camera.position.copy(pos);
        this.camera.lookAt(center);

        if (this.currentCameraType === "orthographic" && bbox) {
            this.fitOrthoToBbox(bbox);
        }

        this.controls.update();
    }

    /**
     * Sets camera to arbitrary spherical orbit angles (yaw and pitch in degrees).
     * @param {number} yawDeg - Horizontal azimuth in degrees (0 = front, 90 = right, 180 = back, 270 = left)
     * @param {number} pitchDeg - Vertical elevation in degrees (0 = eye level, 90 = top down)
     * @param {Object} [bbox] - Model bounding box
     * @param {"perspective"|"orthographic"} [camType="perspective"]
     */
    setOrbit(yawDeg, pitchDeg, bbox = null, camType = "perspective") {
        const center = bbox ? new THREE.Vector3(...bbox.center) : new THREE.Vector3(0, 0, 0);
        const maxDim = bbox ? Math.max(...bbox.size, 10) : 30;
        const dist = maxDim * 2.2;

        // the short names of the capture CLI (`ortho`, `persp`) are the same cameras
        this.setCameraType(camType === "ortho" ? "orthographic" : camType === "persp" ? "perspective" : camType);
        this.controls.target.copy(center);

        const yawRad = THREE.MathUtils.degToRad(yawDeg);
        const pitchRad = THREE.MathUtils.degToRad(pitchDeg);

        const x = center.x + dist * Math.sin(yawRad) * Math.cos(pitchRad);
        const y = center.y + dist * Math.sin(pitchRad);
        const z = center.z + dist * Math.cos(yawRad) * Math.cos(pitchRad);

        this.camera.up.set(0, 1, 0);
        this.camera.position.set(x, y, z);
        this.camera.lookAt(center);

        if (this.currentCameraType === "orthographic" && bbox) {
            this.fitOrthoToBbox(bbox);
        }

        this.controls.update();
    }

    fitOrthoToBbox(bbox, margin = 1.3) {
        const aspect = this.width / this.height;
        const maxDim = Math.max(bbox.size[0], bbox.size[1], bbox.size[2], 5);
        const frustum = maxDim * margin;

        this.orthoFrustumSize = frustum;
        this.orthoCamera.left = (-frustum * aspect) / 2;
        this.orthoCamera.right = (frustum * aspect) / 2;
        this.orthoCamera.top = frustum / 2;
        this.orthoCamera.bottom = -frustum / 2;
        this.orthoCamera.updateProjectionMatrix();
    }

    fitToBbox(bbox, margin = 1.3) {
        const center = new THREE.Vector3(...bbox.center);
        this.controls.target.copy(center);

        const maxDim = Math.max(bbox.size[0], bbox.size[1], bbox.size[2], 5);
        const dist = maxDim * margin * 2.0;

        this.perspCamera.position.set(center.x + dist * 0.7, center.y + dist * 0.6, center.z + dist * 0.7);
        this.perspCamera.lookAt(center);

        this.fitOrthoToBbox(bbox, margin);
        this.controls.update();
    }

    onResize() {
        this.width = this.container.clientWidth;
        this.height = this.container.clientHeight;
        const aspect = this.width / this.height;

        this.perspCamera.aspect = aspect;
        this.perspCamera.updateProjectionMatrix();

        this.orthoCamera.left = (-this.orthoFrustumSize * aspect) / 2;
        this.orthoCamera.right = (this.orthoFrustumSize * aspect) / 2;
        this.orthoCamera.top = this.orthoFrustumSize / 2;
        this.orthoCamera.bottom = -this.orthoFrustumSize / 2;
        this.orthoCamera.updateProjectionMatrix();

        this.renderer.setSize(this.width, this.height);
    }

    _render() {
        if (this.isAnimating) {
            this.frameId = requestAnimationFrame(this._render);
        }
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }

    /**
     * Captures current canvas as Base64 data URL.
     * @returns {string}
     */
    captureScreenshot() {
        this.renderer.render(this.scene, this.camera);
        return this.renderer.domElement.toDataURL("image/png");
    }

    dispose() {
        this.isAnimating = false;
        cancelAnimationFrame(this.frameId);
        window.removeEventListener('resize', this.resizeHandler);
        this.controls.dispose();
        this.renderer.dispose();
        this.renderer.domElement.remove();
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { SceneSetup };
}
