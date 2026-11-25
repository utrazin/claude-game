"""ASTRARIUM UI skin generator (Art Bible §8). Procedural, reproducible, no external images.
   python3 tools/ui/gen_ui.py game/assets/ui
Outputs nine-patch plates (polished / dull / hover / special), walnut rail, brass frame,
odometer roller, engraved icons. Supersampled 4x then downscaled for clean edges."""
import sys, math, pathlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SS = 4
rng = np.random.default_rng(3)
BRASS = np.array([219, 179, 102]) / 255
BRASS_AGED = np.array([140, 107, 58]) / 255
WALNUT = np.array([58, 36, 22]) / 255
BLUED = np.array([43, 63, 107]) / 255
CREAM = np.array([237, 230, 214]) / 255


def to_img(rgb, alpha=None):
    a = np.clip(rgb, 0, 1)
    img = (a * 255).astype(np.uint8)
    if alpha is not None:
        img = np.dstack([img, (np.clip(alpha, 0, 1) * 255).astype(np.uint8)])
        return Image.fromarray(img, "RGBA")
    return Image.fromarray(img, "RGB")


def noise2(h, w, sx, sy, seed):
    g = np.random.default_rng(seed)
    small = g.random((max(2, int(h / sy)) + 2, max(2, int(w / sx)) + 2))
    im = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    return np.asarray(im) / 255.0


def brass_surface(h, w, base, seed, polish=1.0):
    y = np.linspace(0, 1, h)[:, None]
    light = 0.82 + 0.30 * np.exp(-((y - 0.28) ** 2) / 0.02) * polish - 0.18 * y   # soft horizontal highlight band
    brush = noise2(h, w, 60, 1.2, seed) * 0.10 + noise2(h, w, 9, 0.6, seed + 1) * 0.06    # horizontal brushing
    tarn = np.clip(noise2(h, w, 40, 40, seed + 2) - 0.55, 0, 1) * (0.5 if polish < 1 else 0.25)
    col = base[None, None, :] * (light + brush - 0.08)[..., None]
    col = col * (1 - tarn[..., None]) + (base * 0.45)[None, None, :] * tarn[..., None]
    return col


def bevel(col, b, strength=0.35):
    h, w, _ = col.shape
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.minimum.reduce([xx, yy, w - 1 - xx, h - 1 - yy]).astype(float)
    t = np.clip(1 - d / b, 0, 1)
    side = np.where((xx < b) | (yy < b), 1.0, -1.0)          # light from top-left
    side = np.where((xx < b) & (yy > h - 1 - b), 0.0, side)
    side = np.where((yy < b) & (xx > w - 1 - b), 0.0, side)
    return col * (1 + strength * t * side)[..., None]


def screw(draw, cx, cy, r, ang):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(int(c * 255) for c in BLUED * 0.8))
    draw.ellipse([cx - r * 0.75, cy - r * 0.8, cx + r * 0.6, cy + r * 0.45], fill=tuple(int(c * 255) for c in BLUED * 1.35))
    dx, dy = math.cos(ang) * r * 0.85, math.sin(ang) * r * 0.85
    draw.line([cx - dx, cy - dy, cx + dx, cy + dy], fill=(15, 18, 30), width=max(1, int(r * 0.28)))


def fillet(draw, box, col, w):
    x0, y0, x1, y1 = box
    draw.rectangle(box, outline=col, width=w)
    g = w * 3
    draw.rectangle([x0 + g, y0 + g, x1 - g, y1 - g], outline=col, width=max(1, w // 2))


def plate(out, name, base, seed, polish, glow=None, accent=None):
    W, H = 320 * SS, 112 * SS
    col = bevel(brass_surface(H, W, base, seed, polish), 7 * SS, 0.45)
    img = to_img(col).convert("RGBA")
    d = ImageDraw.Draw(img)
    line = tuple(int(c * 255) for c in (accent if accent is not None else base * 0.42)) + (255,)
    fillet(d, [12 * SS, 12 * SS, W - 12 * SS, H - 12 * SS], line, 2 * SS)
    # small central ornament on the top fillet: a lozenge (one motif per piece, Art Bible §7)
    cx = W // 2; cy = 12 * SS
    d.polygon([(cx - 9 * SS, cy), (cx, cy - 4 * SS), (cx + 9 * SS, cy), (cx, cy + 4 * SS)], fill=line)
    for (x, y, a) in ((22, 22, 0.6), (W / SS - 22, 22, 2.1), (22, H / SS - 22, 1.2), (W / SS - 22, H / SS - 22, 2.7)):
        screw(d, x * SS, y * SS, 5 * SS, a)
    img = img.resize((W // SS, H // SS), Image.LANCZOS)
    if glow is not None:
        pad = 18
        g = Image.new("RGBA", (img.width + pad * 2, img.height + pad * 2), (0, 0, 0, 0))
        m = Image.new("L", g.size, 0); ImageDraw.Draw(m).rectangle([pad, pad, pad + img.width, pad + img.height], fill=200)
        m = m.filter(ImageFilter.GaussianBlur(9))
        halo = Image.new("RGBA", g.size, glow + (0,)); halo.putalpha(m)
        g.alpha_composite(halo); g.alpha_composite(img, (pad, pad))
        img = g
    img.save(out / f"{name}.png")


def walnut(out, w=512, h=1024):
    y, x = np.mgrid[0:h, 0:w] / np.array([h, w])[:, None, None]
    warp = noise2(h, w, 80, 300, 21) * 6.0
    grain = np.sin((x * 38 + warp) * math.pi) * 0.5 + 0.5
    fine = noise2(h, w, 2, 40, 22)
    v = 0.78 + 0.22 * grain ** 3 + 0.12 * (fine - 0.5)
    col = WALNUT[None, None, :] * v[..., None]
    col = bevel(col, 10, 0.25)
    to_img(col).save(out / "walnut.png")


def frame(out, name, inner, seed):
    W = H = 160 * SS; b = 16 * SS
    col = brass_surface(H, W, BRASS_AGED * 1.15, seed, 0.6)
    col = bevel(col, 5 * SS, 0.5)
    yy, xx = np.mgrid[0:H, 0:W]
    inside = (xx > b) & (xx < W - b) & (yy > b) & (yy < H - b)
    wood = WALNUT[None, None, :] * (0.75 + 0.15 * noise2(H, W, 30, 3, seed + 5))[..., None]
    if inner == "walnut":
        col = np.where(inside[..., None], wood, col)
    img = to_img(col).convert("RGBA"); d = ImageDraw.Draw(img)
    d.rectangle([b, b, W - b, H - b], outline=(30, 20, 12, 255), width=2 * SS)       # shadow line into the recess
    for (x, y, a) in ((8, 8, 0.5), (W / SS - 8, 8, 2.0), (8, H / SS - 8, 1.1), (W / SS - 8, H / SS - 8, 2.6)):
        screw(d, x * SS, y * SS, 4 * SS, a)
    img.resize((W // SS, H // SS), Image.LANCZOS).save(out / f"{name}.png")


def roller(out):
    W, H = 52 * SS, 76 * SS
    y = np.linspace(-1, 1, H)[:, None]
    shade = np.sqrt(np.clip(1 - y ** 2, 0, 1)) ** 0.7 * np.ones((1, W))   # cylinder
    col = (CREAM * 0.92)[None, None, :] * (0.12 + 0.88 * shade ** 1.6)[..., None]
    col = col * (0.97 + 0.05 * noise2(H, W, 4, 30, 9))[..., None]
    img = to_img(col).convert("RGBA"); d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W - 1, H - 1], outline=(40, 26, 14, 255), width=3 * SS)
    img.resize((W // SS, H // SS), Image.LANCZOS).save(out / "roller.png")


# ---------------------------------------------------------------- engraved icons
def engraved(draw_fn, name, out, size=96):
    S = size * SS
    m = Image.new("L", (S, S), 0); d = ImageDraw.Draw(m)
    draw_fn(d, S)
    dark = Image.new("RGBA", (S, S), (52, 36, 18, 0)); dark.putalpha(m)
    hi = Image.new("RGBA", (S, S), (255, 236, 190, 0)); hi.putalpha(m.point(lambda v: v * 0.55))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.alpha_composite(hi, (int(1.5 * SS), int(1.5 * SS)))           # cut edge catching light
    img.alpha_composite(dark)
    img.resize((size, size), Image.LANCZOS).save(out / f"icon_{name}.png")


def ic_gear(d, S):
    c = S / 2; R = S * 0.40; r = S * 0.31; n = 14
    pts = []
    for i in range(n * 4):
        a = i / (n * 4) * math.tau
        rr = R if (i % 4) in (1, 2) else r
        pts.append((c + rr * math.cos(a), c + rr * math.sin(a)))
    d.polygon(pts, fill=255)
    d.ellipse([c - r * 0.78, c - r * 0.78, c + r * 0.78, c + r * 0.78], fill=0)
    for k in range(5):
        a = k / 5 * math.tau
        d.line([c, c, c + r * 0.8 * math.cos(a), c + r * 0.8 * math.sin(a)], fill=255, width=int(S * 0.05))
    d.ellipse([c - S * 0.08, c - S * 0.08, c + S * 0.08, c + S * 0.08], fill=255)


def ic_pendulum(d, S):
    c = S / 2
    d.rectangle([c - S * 0.12, S * 0.08, c + S * 0.12, S * 0.14], fill=255)
    d.line([c, S * 0.12, c, S * 0.66], fill=255, width=int(S * 0.045))
    d.ellipse([c - S * 0.17, S * 0.62, c + S * 0.17, S * 0.92], fill=255)
    d.ellipse([c - S * 0.07, S * 0.70, c + S * 0.03, S * 0.78], fill=0)


def ic_weight(d, S):
    c = S / 2
    d.ellipse([c - S * 0.09, S * 0.08, c + S * 0.09, S * 0.26], outline=255, width=int(S * 0.04))
    d.polygon([(c - S * 0.20, S * 0.30), (c + S * 0.20, S * 0.30), (c + S * 0.32, S * 0.88), (c - S * 0.32, S * 0.88)], fill=255)
    d.line([c - S * 0.24, S * 0.48, c + S * 0.24, S * 0.48], fill=0, width=int(S * 0.02))


def ic_shaft(d, S):
    c = S / 2
    d.rectangle([c - S * 0.22, S * 0.08, c + S * 0.22, S * 0.92], outline=255, width=int(S * 0.05))
    for k in range(4):
        y = S * (0.25 + 0.17 * k)
        d.line([c - S * 0.22, y, c - S * 0.12, y], fill=255, width=int(S * 0.03))
    d.line([c, S * 0.08, c, S * 0.55], fill=255, width=int(S * 0.025))
    d.rectangle([c - S * 0.08, S * 0.55, c + S * 0.08, S * 0.72], fill=255)


def ic_rotor(d, S):
    c = S / 2
    for k in range(6):
        a = k / 6 * math.tau
        pts = [(c, c)]
        for t in np.linspace(0, 1, 10):
            aa = a + t * 0.9; rr = S * 0.42 * math.sin(t * math.pi * 0.9 + 0.2)
            pts.append((c + rr * math.cos(aa), c + rr * math.sin(aa)))
        d.polygon(pts, fill=255)
    d.ellipse([c - S * 0.07, c - S * 0.07, c + S * 0.07, c + S * 0.07], fill=0)


def ic_moon(d, S):
    c = S / 2
    d.ellipse([c - S * 0.36, c - S * 0.36, c + S * 0.36, c + S * 0.36], fill=255)
    d.ellipse([c - S * 0.20, c - S * 0.44, c + S * 0.48, c + S * 0.30], fill=0)


def ic_planet(d, S):
    c = S / 2
    d.ellipse([c - S * 0.18, c - S * 0.18, c + S * 0.18, c + S * 0.18], fill=255)
    d.ellipse([c - S * 0.42, c - S * 0.12, c + S * 0.42, c + S * 0.12], outline=255, width=int(S * 0.035))


def ic_star(d, S):
    c = S / 2; pts = []
    for i in range(16):
        a = i / 16 * math.tau - math.pi / 2
        rr = S * (0.44 if i % 4 == 0 else (0.2 if i % 2 == 0 else 0.1))
        pts.append((c + rr * math.cos(a), c + rr * math.sin(a)))
    d.polygon(pts, fill=255)


def ic_dial(d, S):
    c = S / 2
    d.ellipse([c - S * 0.40, c - S * 0.40, c + S * 0.40, c + S * 0.40], outline=255, width=int(S * 0.05))
    for k in range(12):
        a = k / 12 * math.tau
        d.line([c + S * 0.30 * math.cos(a), c + S * 0.30 * math.sin(a), c + S * 0.36 * math.cos(a), c + S * 0.36 * math.sin(a)], fill=255, width=int(S * 0.025))
    d.line([c, c, c, c - S * 0.26], fill=255, width=int(S * 0.04))
    d.line([c, c, c + S * 0.18, c + S * 0.06], fill=255, width=int(S * 0.04))


def ic_dome(d, S):
    c = S / 2
    d.pieslice([c - S * 0.36, S * 0.22, c + S * 0.36, S * 0.86], 180, 360, fill=255)
    d.rectangle([c - S * 0.40, S * 0.54, c + S * 0.40, S * 0.62], fill=255)
    d.rectangle([c - S * 0.32, S * 0.62, c + S * 0.32, S * 0.86], fill=255)
    d.rectangle([c - S * 0.05, S * 0.26, c + S * 0.05, S * 0.54], fill=0)                 # the slit
    d.rectangle([c - S * 0.08, S * 0.68, c + S * 0.08, S * 0.86], fill=0)


def ic_key(d, S):
    c = S / 2
    for sx in (-1, 1):
        d.ellipse([c + sx * S * 0.2 - S * 0.17, S * 0.08, c + sx * S * 0.2 + S * 0.17, S * 0.40], outline=255, width=int(S * 0.06))
    d.rectangle([c - S * 0.06, S * 0.30, c + S * 0.06, S * 0.86], fill=255)
    d.rectangle([c - S * 0.12, S * 0.80, c + S * 0.12, S * 0.92], fill=255)


def main(out):
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    plate(out, "plate_polished", BRASS, 1, 1.0)
    plate(out, "plate_dull", BRASS_AGED * 0.85, 2, 0.35)
    plate(out, "plate_hover", BRASS * 1.06, 1, 1.15, glow=(255, 181, 101))
    plate(out, "plate_special", BRASS, 4, 1.0, accent=BLUED)
    walnut(out)
    frame(out, "frame_brass", "walnut", 7)
    roller(out)
    for n, f in (("gear", ic_gear), ("pendulum", ic_pendulum), ("weight", ic_weight), ("shaft", ic_shaft),
                 ("rotor", ic_rotor), ("moon", ic_moon), ("planet", ic_planet), ("star", ic_star),
                 ("dial", ic_dial), ("dome", ic_dome), ("key", ic_key)):
        engraved(f, n, out)
    print("ok", len(list(out.glob("*.png"))))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "game/assets/ui")
