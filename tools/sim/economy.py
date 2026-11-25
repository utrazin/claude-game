"""ASTRARIUM economy simulator.

Reads game/data/balance.json (same file the game reads) and simulates player
profiles with a greedy best-payback purchase policy. Prints a milestone timeline
and flags stagnation (gaps with no purchase longer than a threshold).

  python3 tools/sim/economy.py --profile active --minutes 90
  python3 tools/sim/economy.py --profile idle --minutes 240
"""
import argparse, json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


class Game:
    def __init__(s, bal):
        s.b = bal
        s.ticks = 0.0; s.star = 0.0; s.total_ticks = 0.0; s.total_star = 0.0
        s.levels = [0] * len(bal["stages"]); s.levels[0] = 1
        s.unlocked = [i == 0 for i in range(len(bal["stages"]))]
        s.drive = 0
        s.comps = {c["id"]: 0 for c in bal["complications"]}   # 0 = not built, n = level
        s.stars = 0
        s.offline_lvl = 0
        s.overwind_t = 0.0

    # ---------- derived values
    def ratio(s, i):
        b = s.b; teeth = b["base_teeth"] + b["teeth_per_level"] * (s.levels[i] - 1)
        ms = b["milestone"]["mult"] ** (s.levels[i] // b["milestone"]["every"])
        return teeth / b["pinion_teeth"] * ms if s.levels[i] > 0 else 1.0

    def load(s):
        return sum(st["load"] * s.levels[i] for i, st in enumerate(s.b["stages"]))

    def power(s):
        d = s.b["drive"]; return d["power0"] * d["power_growth"] ** s.drive

    def efficiency(s):
        L = s.load(); P = s.power()
        return 1.0 if L <= P else (P / L) ** s.b["efficiency_exponent"]

    def global_mult(s):
        m = 1.0
        for c in s.b["complications"]:
            if s.comps[c["id"]] and "effect" in c: m *= c["effect"].get("global_mult", 1)
        st = s.b["stars"]
        m *= 1 + st["add_each"] * s.stars
        m *= st["constellation_bonus"] ** (s.stars // st["constellation_size"])
        return m

    def beat_rate(s):
        r = s.b["base_beat_rate"]
        for i in range(len(s.levels)):
            if s.levels[i] > 0: r *= s.ratio(i)
        return r * s.efficiency() * s.global_mult()

    def star_rate(s):
        B = s.beat_rate(); tot = 0.0
        for c in s.b["complications"]:
            lv = s.comps[c["id"]]
            if lv and "starlight_coef" in c:
                tot += c["starlight_coef"] * lv * B ** c["starlight_exp"]
        return tot

    # ---------- purchasable options: (name, currency, cost, apply)
    def options(s):
        b = s.b; out = []
        for i, st in enumerate(b["stages"]):
            if not s.unlocked[i]:
                if s.total_ticks >= st["unlock"] * 0.5:
                    out.append((f"unlock:{st['id']}", "t", st["unlock"], lambda i=i: s._unlock(i)))
            else:
                if s.levels[i] >= b.get("max_level", 10**9): continue
                c = st["cost0"] * st["growth"] ** s.levels[i]
                out.append((f"lvl:{st['id']}", "t", c, lambda i=i: s._lvl(i)))
        d = b["drive"]; out.append(("drive", "t", d["cost0"] * d["growth"] ** s.drive, s._drive))
        for c in b["complications"]:
            lv = s.comps[c["id"]]
            if lv == 0:
                out.append((f"build:{c['id']}", "t", c["cost"], lambda c=c: s._comp(c)))
            elif "level_cost0" in c:
                out.append((f"comp:{c['id']}", "t", c["level_cost0"] * c["level_growth"] ** (lv - 1), lambda c=c: s._comp(c)))
        st = b["stars"]
        if any(s.comps[c["id"]] for c in b["complications"] if "starlight_coef" in c):
            out.append(("star", "s", st["cost0"] * st["growth"] ** s.stars, s._star))
        return out

    def _unlock(s, i): s.unlocked[i] = True; s.levels[i] = 1
    def _lvl(s, i): s.levels[i] += 1
    def _drive(s): s.drive += 1
    def _comp(s, c): s.comps[c["id"]] += 1
    def _star(s): s.stars += 1

    def gain_of(s, apply):
        """Marginal beat-rate gain of an option (simulate on a copy)."""
        import copy
        g = copy.deepcopy(s); before = g.beat_rate() + 50 * g.star_rate()
        apply_name = apply.__name__ if hasattr(apply, "__name__") else ""
        return before, g


def simulate(profile, minutes, verbose):
    bal = json.loads((ROOT / "game/data/balance.json").read_text())
    g = Game(bal)
    clicks_per_s = {"active": 3.0, "casual": 0.6, "idle": 0.0}[profile]
    dt = 1.0; t = 0.0; last_buy = 0.0; log = []; gaps = []
    import copy
    while t < minutes * 60:
        B = g.beat_rate()
        click_gain = clicks_per_s * (bal["click"]["ticks_per_wind"] + B * bal["click"]["wind_seconds_of_production"]) * dt
        if profile == "idle" and t < 120: click_gain = 2.0 * (1 + B)  # even idle players click at the start
        g.ticks += B * dt + click_gain; g.total_ticks += B * dt + click_gain
        sr = g.star_rate() * dt; g.star += sr; g.total_star += sr
        # greedy: buy the affordable option with best (value gain / cost); value = ticks/s + 50*stars/s
        while True:
            best = None
            for name, cur, cost, apply in g.options():
                have = g.ticks if cur == "t" else g.star
                if cost > have: continue
                h = copy.deepcopy(g); 
                # re-bind apply onto copy by name
                for n2, c2, k2, a2 in h.options():
                    if n2 == name: a2(); break
                v0 = g.beat_rate() + 50 * g.star_rate(); v1 = h.beat_rate() + 50 * h.star_rate()
                score = (v1 - v0) / max(cost, 1e-9) if cur == "t" else (v1 - v0) / max(cost * 50, 1e-9)
                if name.startswith(("unlock", "build")): score = max(score, 1e-3)
                if best is None or score > best[0]: best = (score, name, cur, cost, apply)
            if not best or best[0] <= 0: break
            _, name, cur, cost, apply = best
            if cur == "t": g.ticks -= cost
            else: g.star -= cost
            apply()
            if t - last_buy > 60: gaps.append((t - last_buy, last_buy))
            last_buy = t
            if name.startswith(("unlock", "build")) or name == "star" and g.stars % bal["stars"]["constellation_size"] == 0:
                log.append((t, name, g.beat_rate()))
        t += dt
    print(f"== profile={profile} minutes={minutes}")
    for tt, name, B in log:
        print(f"  {tt/60:6.1f} min  {name:22s} beats/s={B:.3g}")
    print(f"  final beats/s={g.beat_rate():.3g} starlight/s={g.star_rate():.3g} stars={g.stars} levels={g.levels} drive={g.drive} eff={g.efficiency():.2f}")
    if gaps:
        worst = sorted(gaps, reverse=True)[:5]
        print("  longest gaps without purchase: " + ", ".join(f"{d/60:.1f}min@{s/60:.0f}" for d, s in worst))
    return g


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--profile", default="active"); ap.add_argument("--minutes", type=float, default=60)
    ap.add_argument("-v", action="store_true"); a = ap.parse_args()
    simulate(a.profile, a.minutes, a.v)
