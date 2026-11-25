"""Limestone ashlar texture (albedo + normal + roughness), tileable. Art Bible §4 (pedra #4A4540, cold).
   python3 tools/ui/gen_stone.py game/assets/textures"""
import sys, pathlib
import numpy as np
from PIL import Image

N = 1024
rng = np.random.default_rng(11)


def tile_noise(n, cells, seed):
    g = np.random.default_rng(seed)
    base = g.random((cells, cells))
    base = np.tile(base, (3, 3))                                  # wrap for seamless bicubic
    im = Image.fromarray((base * 255).astype(np.uint8)).resize((n * 3, n * 3), Image.BICUBIC)
    a = np.asarray(im, dtype=float)[n:2 * n, n:2 * n] / 255.0
    return a


def fbm(n, seed):
    return sum(tile_noise(n, c, seed + i) * w for i, (c, w) in enumerate([(4, .45), (16, .25), (64, .18), (256, .12)]))


def main(out):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    rows, cols = 8, 4                       # 1024 px = 2.4 m: blocks 0.6 x 0.3 m, running bond
    bh = N // rows; bw = N // cols
    height = np.zeros((N, N)); tint = np.zeros((N, N, 3)); mortar_mask = np.zeros((N, N))
    yy, xx = np.mgrid[0:N, 0:N]
    for r in range(rows):
        off = (bw // 2) * (r % 2)
        cuts = [0]
        while N - cuts[-1] > bw * 1.4:               # irregular block lengths (0.45..0.8 m)
            cuts.append(cuts[-1] + int(bw * rng.uniform(0.75, 1.3)))
        cuts.append(N)                                 # last joint lands on the tile edge (seamless)
        for c in range(len(cuts) - 1):
            x0 = cuts[c] - off; y0 = r * bh; bwc = cuts[c + 1] - cuts[c]
            # per-block tone: warm grey limestone, some blocks lighter/yellower
            t = rng.uniform(-0.035, 0.035); w = rng.uniform(0, 0.03)
            col = np.array([0.50 + t + w, 0.48 + t + w * 0.7, 0.45 + t])
            xs = (xx - x0) % N
            m = (xs < bwc) & (yy >= y0) & (yy < y0 + bh)
            # bevelled block with a recessed mortar joint
            dx = np.minimum(xs, bwc - 1 - xs); dy = np.minimum(yy - y0, y0 + bh - 1 - yy)
            d = np.minimum(dx, dy).astype(float) - 5.0
            prof = np.clip(d / 14.0, 0, 1) ** 0.5
            height = np.where(m, prof * (0.85 + 0.15 * rng.random()), height)
            tint = np.where(m[..., None], col[None, None, :], tint)
            mortar_mask = np.where(m & (d < 0), 1.0, mortar_mask)
    n1 = fbm(N, 3); n2 = fbm(N, 9)
    pits = (tile_noise(N, 300, 21) > 0.93).astype(float) * 0.25
    chips = np.clip(fbm(N, 40) - 0.62, 0, 1) * 3.0                  # chipped arrises near edges
    h = height * (0.9 + 0.1 * n1) - pits * (height > 0.5) - chips * (height < 0.9) * 0.4
    grain = tile_noise(N, 512, 77) * 0.5 + tile_noise(N, 160, 78) * 0.5        # sandy tooling grain
    weather = np.clip(fbm(N, 90) * 1.6 - 0.55, 0, 1)                           # darker weathered patches
    albedo = tint * (0.74 + 0.30 * n2 + 0.16 * (grain - 0.5))[..., None] * (1 - 0.25 * weather)[..., None]
    albedo = np.where((mortar_mask > 0.5)[..., None], np.array([0.40, 0.38, 0.34])[None, None, :] * (0.7 + 0.4 * n1)[..., None], albedo)
    h = h + 0.06 * (grain - 0.5) * (height > 0.3)
    h = np.clip(h, 0, 1)
    albedo *= (0.80 + 0.20 * h)[..., None]                          # cavity darkening
    Image.fromarray((np.clip(albedo, 0, 1) * 255).astype(np.uint8)).save(out / "limestone_albedo.png")
    # normal from height (wrapped gradients)
    s = 3.0
    gx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * s; gy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * s
    nrm = np.dstack([-gx, gy, np.ones_like(h)]); nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
    Image.fromarray(((nrm * 0.5 + 0.5) * 255).astype(np.uint8)).save(out / "limestone_normal.png")
    rough = 0.82 + 0.15 * (1 - h) + 0.05 * n1
    Image.fromarray((np.clip(rough, 0, 1) * 255).astype(np.uint8)).save(out / "limestone_rough.png")
    print("ok")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "game/assets/textures")
