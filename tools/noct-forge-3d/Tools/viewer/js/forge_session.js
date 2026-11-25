/* Noct Forge Session 2.0.0 — shared browser runtime, canonical source in the 2D repository. */
(function (root) {
    'use strict';
    class LatestRequest {
        constructor() { this.generation = 0; this.controller = null; }
        begin() {
            this.controller?.abort();
            this.controller = new AbortController();
            const generation = ++this.generation;
            return { signal: this.controller.signal, current: () => generation === this.generation };
        }
        cancel() { this.controller?.abort(); this.generation++; }
    }
    class Poller {
        constructor(callback, interval = 2000) {
            this.callback = callback; this.interval = interval; this.running = false; this.pending = false; this.stopped = false;
        }
        async refresh() {
            if (this.stopped) return;
            if (this.running) { this.pending = true; return; }
            clearTimeout(this.timer); this.running = true;
            try { await this.callback(); }
            finally {
                this.running = false;
                if (!this.stopped) {
                    const delay = this.pending ? 0 : this.interval;
                    this.pending = false;
                    this.timer = setTimeout(() => this.refresh(), delay);
                }
            }
        }
        stop() { this.stopped = true; clearTimeout(this.timer); }
    }
    function fingerprint(value) { return JSON.stringify(value); }
    function assetRevision(asset, variant = '') {
        return fingerprint([asset?.stamp, asset?.error, asset?.textures, asset?.texture_filter,
            asset?.variants?.find(item => item.id === variant)]);
    }
    function cameraSnapshot(setup) {
        if (!setup?.camera || !setup.controls) return null;
        return { type: setup.currentCameraType, position: setup.camera.position.toArray(),
            up: setup.camera.up.toArray(), target: setup.controls.target.toArray(),
            zoom: setup.camera.zoom, frustum: setup.orthoFrustumSize };
    }
    function restoreCamera(setup, state) {
        if (!state) return;
        setup.setCameraType(state.type);
        if (state.frustum) setup.orthoFrustumSize = state.frustum;
        setup.onResize();
        setup.camera.position.fromArray(state.position); setup.camera.up.fromArray(state.up);
        setup.camera.zoom = state.zoom; setup.camera.updateProjectionMatrix();
        setup.controls.target.fromArray(state.target); setup.controls.update();
    }
    function playbackSnapshot(player) {
        return player ? { clip: player.clip?.name, time: player.time, playing: player.playing,
            speed: player.speed || 1, repeat: player.repeat || 'original' } : null;
    }
    function restorePlayback(player, state) {
        if (!player || !state) return false;
        if (!state.clip) { player.basePose(); return true; }
        if (!player.names.includes(state.clip)) return false;
        player.select(state.clip); player.speed = state.speed; player.repeat = state.repeat;
        player.seek(Math.min(state.time, player.length));
        if (state.playing) player.play(); else player.pause();
        return true;
    }
    function status(state, error = null, revision = null) {
        root.__FORGE_STATUS__ = { state, error, revision };
        root.__VIEWER_READY__ = state === 'ready';
        if (typeof root.dispatchEvent === 'function' && typeof CustomEvent !== 'undefined') root.dispatchEvent(new CustomEvent('forge:status', { detail: root.__FORGE_STATUS__ }));
    }
    root.ForgeSession = { version: '2.0.0', LatestRequest, Poller, fingerprint, assetRevision,
        cameraSnapshot, restoreCamera, playbackSnapshot, restorePlayback, status };
})(typeof window === 'undefined' ? globalThis : window);
