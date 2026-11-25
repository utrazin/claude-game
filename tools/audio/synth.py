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
    # v2 (playtest: too thin/clicky): lower metal pitch, a wooden case body resonance, softer transient
    for name, base in (("tick", 1720.0), ("tock", 1440.0)):
        for k in range(3):
            d = 1 + 0.015 * (k - 1)
            y = modal(0.26, [(base * d, 0.8, 0.022), (base * 2.76 * d, 0.3, 0.010), (base * 5.4 * d, 0.08, 0.005),
                             (310 * d, 0.7, 0.045), (180 * d, 0.45, 0.06)],
                      noise=0.9, noise_decay=0.002, lp=0.18)
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
    ambience(out)
    print("ok", len(list(out.glob("*.wav"))), "files")


def lowpass(x, a):
    """One-pole low-pass, vectorised via scipy-free recursion in chunks (a in 0..1)."""
    y = np.empty_like(x); acc = 0.0
    for i in range(len(x)):
        acc += a * (x[i] - acc); y[i] = acc
    return y


def write_stereo(path, l, r, gain=0.8):
    m = max(np.max(np.abs(l)), np.max(np.abs(r))) + 1e-9
    st = np.stack([l, r], 1) / m * gain
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype(np.int16).tobytes())


def seamless(y, xf):
    """Crossfade the tail into the head so the loop has no seam."""
    head = y[:xf].copy(); tail = y[-xf:]
    k = np.linspace(0, 1, xf)
    y = y[:-xf].copy(); y[:xf] = head * k + tail * (1 - k)
    return y


def ambience(out):
    """v2 (after playtest: room tone felt synthetic). Wind around the dome, oil-lamp
    crackle, a warm modal pad and celesta motifs for the generative score."""
    dur = 32; n = SR * dur; t = np.arange(n) / SR
    # wind: band-limited noise, slow gusts, different per ear
    chans = []
    for seed in (11, 12):
        g = np.random.default_rng(seed)
        w = g.standard_normal(n)
        lo = lowpass(w, 0.02) - lowpass(w, 0.002)            # band ~ 15..140 Hz region, airy rumble
        hi = lowpass(w, 0.08) - lowpass(w, 0.03)             # whistle band
        gust = 0.55 + 0.45 * np.sin(2 * np.pi * t / dur * 3 + seed) * np.sin(2 * np.pi * t / dur * 5 + 1.3 * seed)
        whistle = np.clip(np.sin(2 * np.pi * t / dur * 2 + seed * 2.1), 0, 1) ** 3
        y = lo * 5.0 * gust + hi * 2.2 * whistle * gust
        # lamp crackle: sparse tiny clicks
        cr = np.zeros(n)
        for _ in range(140):
            i = g.integers(0, n - 400); a = g.uniform(0.05, 0.35)
            cr[i:i + 400] += a * g.standard_normal(400) * np.exp(-np.arange(400) / 40.0)
        y += lowpass(cr, 0.15) * 0.35
        # distant wood/metal creak, twice per loop
        for c in (g.uniform(3, 12), g.uniform(18, 28)):
            i = int(c * SR); m = int(1.2 * SR); tt = np.arange(m) / SR
            f = 95 + 25 * np.sin(2 * np.pi * 1.7 * tt)
            cre = np.sin(2 * np.pi * np.cumsum(f) / SR) * (np.abs(np.sin(2 * np.pi * 23 * tt)) ** 6) * np.exp(-tt / 0.5) * np.minimum(tt / 0.15, 1)
            y[i:i + m] += cre * 0.12
        chans.append(seamless(y, SR * 2))
    write_stereo(out / "room_tone.wav", chans[0], chans[1], 0.5)
    # pad: D dorian chords, detuned soft partials, slow swells (loop 32 s)
    chords = [[146.83, 220.0, 261.63, 349.23], [130.81, 196.0, 261.63, 329.63], [116.54, 174.61, 233.08, 293.66], [130.81, 196.0, 246.94, 329.63]]
    L = np.zeros(n); R = np.zeros(n); seg = n // len(chords)
    for ci, ch in enumerate(chords):
        tt = np.arange(seg * 2) / SR
        sw = np.sin(np.pi * np.clip(tt / (2 * seg / SR), 0, 1)) ** 2
        for k, f in enumerate(ch):
            for det, pan in ((-0.12, 0.8), (0.0, 0.5), (0.13, 0.2)):
                v = sum(np.sin(2 * np.pi * (f * h + det) * tt + k) / h ** 1.6 for h in (1, 2, 3, 4))
                a = sw * 0.25
                s0 = ci * seg; s1 = min(n, s0 + seg * 2); m = s1 - s0
                L[s0:s1] += v[:m] * a[:m] * (1 - pan); R[s0:s1] += v[:m] * a[:m] * pan
                if s0 + seg * 2 > n:  # wrap the swell to the loop start
                    r = s0 + seg * 2 - n
                    L[:r] += v[m:] * a[m:] * (1 - pan); R[:r] += v[m:] * a[m:] * pan
    write_stereo(out / "pad.wav", lowpass(L, 0.08), lowpass(R, 0.08), 0.35)
    # celesta motifs (score layer): D dorian notes
    for i, f in enumerate([293.66, 329.63, 349.23, 392.0, 440.0, 493.88, 523.25, 587.33]):
        y = modal(3.5, [(f, 1.0, 1.4), (f * 2.0, 0.3, 0.6), (f * 3.01, 0.12, 0.3), (f * 4.2, 0.05, 0.12)], noise=0.15, noise_decay=0.002)
        write(out / f"note_{i}.wav", y, 0.35)
    # observatory shot: the dome mechanism — low rumble swell + a run of slow ratchet clacks
    d = 2.8; m = int(SR * d); tt = np.arange(m) / SR
    g = np.random.default_rng(5)
    rum = lowpass(g.standard_normal(m), 0.01) * 6 * np.sin(np.pi * tt / d) ** 2
    rum += 0.3 * np.sin(2 * np.pi * 48 * tt) * np.sin(np.pi * tt / d) ** 2
    for k in range(9):
        i = int((0.25 + k * 0.27) * SR)
        c = modal(0.25, [(820 + 30 * k, 0.6, 0.03), (1730, 0.3, 0.015), (160, 0.5, 0.04)], noise=1.2, noise_decay=0.004, lp=0.3)
        rum[i:i + len(c)] += c[:max(0, min(len(c), m - i))] * 0.35
    write(out / "dome.wav", rum, 0.7)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "game/assets/audio")
