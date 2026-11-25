"""Procedural sound design for ASTRARIUM (no third-party samples, no licensing issues).

Modal synthesis: each sound is a sum of exponentially decaying partials (metal is
inharmonic) plus a short filtered-noise transient. Writes 16-bit mono WAVs.
  python3 tools/audio/synth.py game/assets/audio
"""
import sys, wave, pathlib
import numpy as np

SR = 44100
rng = np.random.default_rng(7)


def env(n, attack, decay):
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / decay)


def modal(dur, partials, noise=0.0, noise_decay=0.004, lp=0.25):
    n = int(SR * dur); t = np.arange(n) / SR; y = np.zeros(n)
    for f, amp, dec in partials:
        y += amp * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t / dec)
    if noise:
        w = rng.standard_normal(n)
        # one-pole low-pass for a softer transient
        out = np.zeros(n); acc = 0.0
        for i in range(min(n, int(SR * 0.05))):
            acc += lp * (w[i] - acc); out[i] = acc
        y += noise * out * np.exp(-t / noise_decay)
    y *= env(n, 0.0008, dur)
    return y


def write(path, y, gain=0.8):
    y = y / (np.max(np.abs(y)) + 1e-9) * gain
    fade = int(SR * 0.01); y[-fade:] *= np.linspace(1, 0, fade)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y * 32767).astype(np.int16).tobytes())


def main(out):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    # escapement tick/tock: soft wooden-brass knock, two variants (tick and tock)
    for name, base in (("tick", 2350.0), ("tock", 1980.0)):
        for k in range(3):
            d = 1 + 0.015 * (k - 1)
            y = modal(0.18, [(base * d, 1.0, 0.018), (base * 2.76 * d, 0.45, 0.010), (base * 5.4 * d, 0.2, 0.006), (620 * d, 0.35, 0.03)],
                      noise=1.2, noise_decay=0.0025, lp=0.35)
            write(out / f"{name}_{k}.wav", y, 0.55)
    # ratchet click while winding
    for k in range(3):
        y = modal(0.09, [(3100 + 120 * k, 0.6, 0.008), (5200, 0.3, 0.004)], noise=1.6, noise_decay=0.0018, lp=0.6)
        write(out / f"ratchet_{k}.wav", y, 0.5)
    # stopwork: heavier clunk when fully wound
    write(out / "stopwork.wav", modal(0.35, [(410, 1.0, 0.06), (1130, 0.4, 0.03), (2400, 0.2, 0.02)], noise=1.0, noise_decay=0.006, lp=0.2), 0.7)
    # gear engage (purchase of a wheel): metallic clank with a ring
    write(out / "engage.wav", modal(0.9, [(523, 0.8, 0.25), (1442, 0.5, 0.12), (2911, 0.3, 0.07), (180, 0.6, 0.05)], noise=1.4, noise_decay=0.01, lp=0.25), 0.75)
    # small bell chime (complication built): bell partial ratios 0.5, 1, 1.2, 1.5, 2, 2.5, 3
    f0 = 784.0
    bell = [(f0 * r, a, d) for r, a, d in [(0.5, 0.5, 2.2), (1.0, 1.0, 1.6), (1.19, 0.6, 1.2), (1.5, 0.4, 0.9), (2.0, 0.35, 0.7), (2.52, 0.2, 0.5), (3.0, 0.15, 0.4)]]
    write(out / "chime.wav", modal(3.0, bell, noise=0.3, noise_decay=0.003), 0.6)
    # star lit: celesta-like pluck, pentatonic set
    for i, f in enumerate([1046.5, 1174.7, 1318.5, 1568.0, 1760.0, 2093.0, 2349.3]):
        write(out / f"star_{i}.wav", modal(2.2, [(f, 1.0, 0.9), (f * 2, 0.25, 0.4), (f * 4.01, 0.08, 0.15)], noise=0.2, noise_decay=0.002), 0.45)
    # room tone: low drone with slow beating, loopable 8 s
    n = SR * 8; t = np.arange(n) / SR
    y = sum(a * np.sin(2 * np.pi * f * t) for f, a in [(55, 0.5), (55.25, 0.5), (82.5, 0.25), (110.125, 0.15)])
    w = rng.standard_normal(n); acc = 0.0; air = np.zeros(n)
    for i in range(n):
        acc += 0.01 * (w[i] - acc); air[i] = acc
    y = y * 0.6 + air * 4.0
    y = y / np.max(np.abs(y)) * 0.25
    with wave.open(str(out / "room_tone.wav"), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(SR); f.writeframes((y * 32767).astype(np.int16).tobytes())
    print("ok", len(list(out.glob("*.wav"))), "files")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "game/assets/audio")
