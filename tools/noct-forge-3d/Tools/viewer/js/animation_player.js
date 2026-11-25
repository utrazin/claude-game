/** Playback of native numeric Blockbench transform keyframes. */
class AnimationPlayer {
    constructor(parser, animations, onTime) {
        this.parser = parser;
        this.animations = animations || [];
        this.onTime = onTime || (() => {});
        this.clip = null;
        this.time = 0;
        this.playing = false;
        this.speed = 1; this.repeat = 'original';
        this.previousFrame = null;
        this._frame = this._frame.bind(this);
        this.frameId = requestAnimationFrame(this._frame);
    }

    dispose() {
        cancelAnimationFrame(this.frameId);
    }

    select(name) {
        this.clip = this.animations.find(item => item.name === name) || null;
        this.playing = false;
        this.tracks = Object.entries(this.clip?.animators || {}).map(([uuid, animator]) => ({
            control: this.parser.controls.get(uuid),
            channels: ['position', 'rotation', 'scale'].map(channel => ({ channel,
                keys: (animator.keyframes || []).filter(key => key.channel === channel).sort((a, b) => a.time - b.time)
            })).filter(track => track.keys.length)
        })).filter(track => track.control);
        this.seek(0);
    }

    play() {
        if (this.clip) {
            if (this.time >= this.clip.length) this.seek(0);
            this.playing = true;
        }
        this.previousFrame = null;
        this.onTime(this.time);
    }

    pause() { this.playing = false; this.previousFrame = null; this.onTime(this.time); }

    basePose() { this.pause(); this.clip = null; this.time = 0; this.applyPose(); this.onTime(0); }

    seek(time) {
        if (!this.clip) return;
        this.time = Math.max(0, Math.min(Number(time) || 0, this.clip.length || 0));
        this.applyPose();
        this.onTime(this.time);
    }

    _frame(now) {
        if (this.playing && this.clip) {
            if (this.previousFrame !== null) {
                let next = this.time + (now - this.previousFrame) / 1000 * this.speed;
                if (this.clip.length > 0 && next >= this.clip.length) {
                    if (this.repeat === "loop" || (this.repeat === "original" && this.clip.loop === "loop")) next %= this.clip.length;
                    else { next = this.clip.length; this.pause(); }
                }
                this.seek(next);
            }
            this.previousFrame = now;
        } else {
            this.previousFrame = null;
        }
        this.frameId = requestAnimationFrame(this._frame);
    }

    static _value(keyframe) {
        const point = keyframe.data_points && keyframe.data_points[0];
        if (!point) return null;
        const values = [Number(point.x), Number(point.y), Number(point.z)];
        return values.every(Number.isFinite) ? values : null;
    }

    static _sample(keyframes, time, presorted = false) {
        if (!keyframes.length) return null;
        const sorted = presorted ? keyframes : keyframes.slice().sort((a, b) => a.time - b.time);
        if (time <= sorted[0].time) return AnimationPlayer._value(sorted[0]);
        if (time >= sorted[sorted.length - 1].time) return AnimationPlayer._value(sorted[sorted.length - 1]);
        for (let i = 0; i < sorted.length - 1; i++) {
            const a = sorted[i], b = sorted[i + 1];
            if (time < a.time || time > b.time) continue;
            const av = AnimationPlayer._value(a), bv = AnimationPlayer._value(b);
            if (!av || !bv) return null;
            if (a.interpolation === "step") return av;
            const fraction = (time - a.time) / (b.time - a.time);
            if (a.interpolation === "catmullrom") {
                const previous = AnimationPlayer._value(sorted[Math.max(i - 1, 0)]);
                const following = AnimationPlayer._value(sorted[Math.min(i + 2, sorted.length - 1)]);
                const t = fraction, t2 = t*t, t3 = t2*t;
                return av.map((v, axis) => {
                    const p = previous[axis], n = bv[axis], f = following[axis];
                    return .5*(2*v+(-p+n)*t+(2*p-5*v+4*n-f)*t2+(-p+3*v-3*n+f)*t3);
                });
            }
            return av.map((value, axis) => value + (bv[axis] - value) * fraction);
        }
        return null;
    }

    applyPose() {
        for (const control of this.parser.controls.values()) {
            control.object.position.copy(control.position);
            control.object.rotation.copy(control.rotation);
            control.object.scale.copy(control.scale);
        }
        if (this.clip) {
            for (const { control, channels } of this.tracks || []) {
                for (const { channel, keys } of channels) {
                    const value = AnimationPlayer._sample(keys, this.time, true);
                    if (!value) continue;
                    if (channel === "position") {
                        control.object.position.set(control.position.x + value[0],
                            control.position.y + value[1], control.position.z + value[2]);
                    } else if (channel === "rotation") {
                        control.object.rotation.set(control.rotation.x + THREE.MathUtils.degToRad(value[0]),
                            control.rotation.y + THREE.MathUtils.degToRad(value[1]),
                            control.rotation.z + THREE.MathUtils.degToRad(value[2]), "ZYX");
                    } else {
                        control.object.scale.set(control.scale.x * value[0],
                            control.scale.y * value[1], control.scale.z * value[2]);
                    }
                }
            }
        }
        if (this.parser.sceneRoot) this.parser.sceneRoot.updateMatrixWorld(true);
        else for (const control of this.parser.controls.values()) control.object.updateMatrixWorld(true);
        this.parser.updateSkinning();
    }
}

if (typeof module !== "undefined" && module.exports) module.exports = { AnimationPlayer };
