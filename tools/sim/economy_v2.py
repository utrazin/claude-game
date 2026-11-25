"""ASTRARIUM economy v0.4 simulator (model D10: regulator + train + weight energy).

State integrates the weight height h. Production = f_eff * Y where
  R      = product of stage ratios
  amp    = torque / (R * impulse(f))            (amplitude; <1 the regulator slows)
  f_amp  = f_reg * min(1, amp)^2
  v      = f * cord / R                          (weight fall speed)
  if h > 0: f_eff = f_amp, else f_eff = min(f_amp, supply * R / cord)
Policies: greedy on steady-state value (production when weight empty, i.e. sustainable),
plus active/casual/idle winding behaviour.
  python3 tools/sim/economy_v2.py --profile idle --minutes 120
"""
import argparse, json, math, pathlib, copy
ROOT = pathlib.Path(__file__).resolve().parents[2]


class G:
    def __init__(s, b):
        s.b = b; s.ticks = 0.0; s.star = 0.0; s.tot = 0.0; s.tot_star = 0.0
        s.lv = [1] + [0] * (len(b["stages"]) - 1)
        s.reg = 0; s.wt = 0; s.shaft = 0; s.rotor = -1
        s.comps = {c["id"]: 0 for c in b["complications"]}; s.stars = 0
        s.h = s.H()

    def teeth(s, i): return s.b["base_teeth"] + s.b["teeth_per_level"] * (s.lv[i] - 1)
    def R(s):
        r = 1.0
        for i, l in enumerate(s.lv):
            if l: r *= s.teeth(i) / s.b["pinion_teeth"]
        return r
    def f_reg(s): return s.b["regulator"]["f0"] * s.b["regulator"]["growth"] ** s.reg
    def torque(s): return s.b["weight"]["m0"] * s.b["weight"]["growth"] ** s.wt
    def H(s): return s.b["shaft"]["h0"] + s.b["shaft"]["per_level"] * s.shaft
    def impulse(s):
        e = s.b["impulse"]["e_per_hz"] * s.f_reg()
        for c in s.b["complications"]:
            if s.comps[c["id"]]: e += c["load"] * (1 + 0.5 * (s.comps[c["id"]] - 1))
        return e
    def amp(s): return s.torque() / (s.R() * s.impulse())
    def f_amp(s): return s.f_reg() * min(1.0, s.amp()) ** 2
    def rotor_rate(s):
        r = s.b["rotor"]; return 0.0 if s.rotor < 0 else r["w0"] * r["growth"] ** s.rotor
    def Y(s):
        y = s.b["yield0"]
        for c in s.b["complications"]:
            lv = s.comps[c["id"]]
            if lv: y *= c["yield_mult"] * (1 + c.get("level_yield", 0) * (lv - 1))
        st = s.b["stars"]
        y *= (1 + st["yield_add"] * s.stars) * st["constellation_mult"] ** (s.stars // st["constellation_size"])
        return y
    def f_eff(s, supply):
        fa = s.f_amp()
        if s.h > 1e-9: return fa
        return min(fa, supply * s.R() / s.b["cord_per_beat"])
    def sustained(s, supply):   # production with empty weight (long-run value)
        return min(s.f_amp(), supply * s.R() / s.b["cord_per_beat"]) * s.Y()
    def star_rate(s, prod):
        t = 0.0
        for c in s.b["complications"]:
            if s.comps[c["id"]] and "starlight" in c: t += c["starlight"] * s.comps[c["id"]] * prod ** s.b["starlight_exp"]
        return t

    def step(s, dt, hand):
        supply = s.rotor_rate() + hand
        f = s.f_eff(supply)
        v = f * s.b["cord_per_beat"] / s.R()
        s.h = min(s.H(), max(0.0, s.h + (supply - v) * dt))
        p = f * s.Y()
        s.ticks += p * dt; s.tot += p * dt
        sr = s.star_rate(p); s.star += sr * dt; s.tot_star += sr * dt
        return p

    def options(s):
        b = s.b; out = []
        for i, st in enumerate(b["stages"]):
            if s.lv[i] == 0:
                if i > 0 and s.lv[i - 1] and s.tot >= st["unlock"] * 0.3:
                    out.append(("unlock:" + st["id"], "t", st["unlock"], ("lv", i)))
                break
            if s.lv[i] < b["max_level"]:
                out.append(("lvl:" + st["id"], "t", st["cost0"] * st["cost_growth"] ** (s.lv[i] - 1), ("lv", i)))
        out.append(("regulator", "t", b["regulator"]["cost0"] * b["regulator"]["cost_growth"] ** s.reg, ("reg",)))
        out.append(("weight", "t", b["weight"]["cost0"] * b["weight"]["cost_growth"] ** s.wt, ("wt",)))
        out.append(("shaft", "t", b["shaft"]["cost0"] * b["shaft"]["cost_growth"] ** s.shaft, ("shaft",)))
        r = b["rotor"]
        out.append(("rotor", "t", r["unlock"] if s.rotor < 0 else r["cost0"] * r["cost_growth"] ** s.rotor, ("rotor",)))
        for c in b["complications"]:
            lv = s.comps[c["id"]]
            if lv == 0 and s.tot >= c["cost"] * 0.3: out.append(("build:" + c["id"], "t", c["cost"], ("comp", c["id"])))
            elif lv and "level_cost0" in c: out.append(("comp:" + c["id"], "t", c["level_cost0"] * c["level_growth"] ** (lv - 1), ("comp", c["id"])))
        if any(s.comps[c["id"]] for c in b["complications"] if "starlight" in c):
            st = b["stars"]; out.append(("star", "s", st["cost0"] * st["growth"] ** s.stars, ("star",)))
        return out

    def apply(s, a):
        k = a[0]
        if k == "lv": s.lv[a[1]] += 1
        elif k == "reg": s.reg += 1
        elif k == "wt": s.wt += 1
        elif k == "shaft": s.shaft += 1; s.h += s.b["shaft"]["per_level"] * 0  # new depth starts empty
        elif k == "rotor": s.rotor += 1
        elif k == "comp": s.comps[a[1]] += 1
        elif k == "star": s.stars += 1


def value(g, hand):
    p = g.sustained(g.rotor_rate() + hand)
    return p + 20 * g.star_rate(p)


def run(profile, minutes, quiet=False):
    b = json.loads((ROOT / "game/data/balance_v2.json").read_text()); g = G(b)
    cps = {"active": 3.0, "casual": 0.5, "idle": 0.0}[profile]
    t = 0.0; dt = 0.5; log = []; last = 0.0; gaps = []; clicks = 0
    while t < minutes * 60:
        c = cps if profile != "idle" or t > 90 else 0.0
        if profile == "idle" and t <= 90: c = 1.5    # everyone clicks at the very start
        if profile != "active" and t > 90 and g.rotor >= 0: c = min(c, 0.2) if profile == "casual" else 0.0
        hand = c * b["winding"]["per_click"]; clicks += c * dt
        g.step(dt, hand)
        while True:
            best = None; v0 = value(g, hand)
            for name, cur, cost, act in g.options():
                if (g.ticks if cur == "t" else g.star) < cost: continue
                h = copy.deepcopy(g); h.apply(act)
                gain = value(h, hand) - v0
                if name == "shaft": gain = max(gain, v0 * 0.02)   # autonomy has value offline
                score = gain / cost
                if name.startswith(("unlock", "build")): score = max(score, 1e-9)
                if best is None or score > best[0]: best = (score, name, cur, cost, act)
            if not best or best[0] <= 0: break
            _, name, cur, cost, act = best
            if cur == "t": g.ticks -= cost
            else: g.star -= cost
            g.apply(act)
            if t - last > 90: gaps.append((t - last, last))
            last = t
            if name.startswith(("unlock", "build", "rotor")) and (name != "rotor" or g.rotor == 0) or (name == "star" and g.stars % 7 == 0):
                log.append((t, name))
        t += dt
    if not quiet:
        print(f"== v0.4 profile={profile} minutes={minutes} clicks≈{clicks:.0f}")
        for tt, n in log: print(f"  {tt/60:6.1f} min  {n}")
        print(f"  prod/s={g.sustained(g.rotor_rate()):.3g} R={g.R():.3g} amp={g.amp():.2f} f_reg={g.f_reg():.2f} rotor={g.rotor_rate():.3g} H={g.H():.0f} stars={g.stars} lv={g.lv} reg={g.reg} wt={g.wt} shaft={g.shaft}")
        autonomy = g.H() / max(1e-9, g.f_amp() * b['cord_per_beat'] / g.R() - g.rotor_rate())
        print(f"  autonomy at full speed (no hand)={autonomy/60:.1f} min" if autonomy > 0 else "  sustainable forever")
        if gaps: print("  gaps>1.5min: " + ", ".join(f"{d/60:.1f}@{s/60:.0f}" for d, s in sorted(gaps, reverse=True)[:5]))
    return g, log


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--profile", default="active"); ap.add_argument("--minutes", type=float, default=60)
    a = ap.parse_args(); run(a.profile, a.minutes)
