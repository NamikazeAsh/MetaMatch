"""
Coach Guide lead check on real ladder games (local Showdown replays in data/replays/pool, gitignored).

For every side of every replay: rebuild the team from team preview (likely sets, overwritten by whatever the
replay revealed: ability, item, moves), ask the guide for its two leads, and compare with the Pokemon the
player actually led with. Players' leads are not ground truth for the best lead, so this measures agreement.

Reported against baselines:
  * random: any two of the six (2 in 6)
  * lead rate: the two members that lead most often when they are on a team (Smogon leads / usage)
plus an ablation that drops each term of the guide's lead score, and the teams with a weather or terrain setter.

  python bench/guide/leads.py                    # gen9ou
  python bench/guide/leads.py --format gen9uu
"""
import argparse
import collections
import glob
import json
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

WEIGHTS = {"hazards": 3.0, "setter": 2.5, "pivots": 1.5, "beats": 1.0, "outspeeds": 1.0}
STATS_KEY = {"gen9nationaldex": "gen9natdex"}
LOWER = {"gen9ou": "gen9uu", "gen9championsou": "gen9championsuu"}


def wilson(k, n, z=1.96):
    if not n:
        return 0.0, 0.0
    p = k / n
    d = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return mid - half, mid + half


def mcnemar(b, c):
    """Exact two sided McNemar p value from the discordant pair counts."""
    k, m = min(b, c), b + c
    return min(1.0, 2 * sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m) if m else 1.0


def to_id(name):
    return "".join(c for c in (name or "").lower() if c.isalnum())


def games(format_id):
    """(replay id, side, player, [(species, revealed Mon or None)], lead species, rating) per side of every replay."""
    from metamatch.replay.protocol import parse_battle, _same_species
    out = []
    for path in sorted(glob.glob(str(ROOT / "data" / "replays" / "pool" / f"*{format_id}-*.json"))):
        d = json.load(open(path, encoding="utf-8"))
        try:
            b = parse_battle(d["log"], format_id=format_id)
        except Exception:
            continue
        if not b.turns:
            continue
        for side in ("p1", "p2"):
            preview = b.preview.get(side) or []
            start = b.turns[0].start.get(side)
            if len(preview) != 6 or not start:
                continue
            lead = b.mons[side].get(start["ident"])
            seen = list(b.mons[side].values())
            members = []
            for species in preview:
                mon = next((m for m in seen if _same_species(species, m.first_species)), None)
                if mon:
                    seen.remove(mon)
                members.append((mon.first_species if mon else species.replace("-*", ""), mon))
            out.append((d["id"], side, b.players.get(side, side), members, lead.first_species if lead else start["species"],
                        d.get("rating") or 0))
    return out


def rebuild(members, format_id):
    """readTeam shaped team from likely sets plus the replay's revealed ability, item and moves; None if a set is missing."""
    from metamatch.engine.completer import member_from_set
    from metamatch.engine.sets import likely_set
    from metamatch.team import detectRole
    from metamatch.auditor import load_chaos_data
    team, usage, alias, fallbacks = {}, {}, {}, 0
    for i, (species, mon) in enumerate(members):
        known = {}
        if mon:
            known = {"item": mon.item, "ability": mon.ability, "moves": [m for m in mon.moves if m != "Struggle"]}
        names = [species]
        if mon and mon.species != species:
            names.append(mon.species)          # Champions: the Mega it became (stats file Megas by their Mega name)
        megas = sorted((k for k, e in (load_chaos_data(format_id) or {}).items() if k.startswith(species + "-Mega")),
                       key=lambda k: -(load_chaos_data(format_id)[k].get("usage") or 0))
        names += megas[:1]
        s = next((x for x in (likely_set(n, format_id, known) for n in names) if x), None)
        own_tier = bool(s)
        if not s and LOWER.get(format_id):
            s = likely_set(species, LOWER[format_id], known)   # a rare pick: its set from the tier it is common in
            fallbacks += bool(s)
        if not s:
            return None, None, None, 0
        team[i] = dict(member_from_set(s, format_id), Roles=[])
        usage[s["name"]] = (s.get("usage") or 0.0) if own_tier else 0.0
        alias[s["name"]] = species
    detectRole(team)
    return team, usage, alias, fallbacks


def lead_rates(format_id, usage):
    """P(leads | on the team) per member from the latest month of Smogon leads; 0 outside the top leads."""
    from metamatch import meta_trends
    hist = meta_trends.load(meta_trends.LEADS_PATH).get(STATS_KEY.get(format_id, format_id), {})
    if not hist:
        return {}
    table = dict(hist[sorted(hist)[-1]])
    return {name: (table.get(name, 0.0) / 100) / u if u else 0.0 for name, u in usage.items()}


def pick(features, win, weights):
    """The guide's two leads under `weights`, replicating guide._leads."""
    pool = [f for f in features if f["name"] != win] or features
    score = lambda f: sum(weights[k] * f[k] for k in weights)
    return [f["name"] for f in sorted(pool, key=score, reverse=True)[:2]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="gen9ou")
    ap.add_argument("--limit", type=int, default=0, help="games to score (0 = all)")
    args = ap.parse_args()
    fmt = args.format

    from metamatch.engine import synergy
    from metamatch.engine.guide import board_rows, member_facts, team_guide

    rows_out, seen, skipped, fallbacks, t0 = [], set(), 0, 0, time.time()
    all_games = games(fmt)
    for rid, side, player, members, lead, rating in all_games:
        key = (player, tuple(sorted(s for s, _ in members)), to_id(lead))
        if key in seen:            # the same player leading the same team the same way counts once
            continue
        seen.add(key)
        team, usage, alias, fb = rebuild(members, fmt)
        if not team:
            skipped += 1
            continue
        fallbacks += fb
        rows = board_rows(team, fmt)
        g = team_guide(team, fmt, rows=rows)
        facts = member_facts(team, fmt, rows)
        name = lambda x: alias.get(x, x)       # back to the team preview species the lead is named by
        setters = {name(st["name"]) for e in g.engines for st in e.setters if st["ability"]}
        n = max(len(rows), 1)
        features = [{"name": name(m.name), "hazards": float(bool(m.hazards)), "setter": float(name(m.name) in setters),
                     "pivots": float(bool(m.pivots)), "beats": len(m.beats) / n, "outspeeds": m.outspeeds}
                    for m in facts]
        rates = lead_rates(fmt, usage)
        win = name(g.win["name"]) if g.win else None
        rows_out.append({"id": rid, "side": side, "rating": rating, "lead": lead, "win": win,
                         "guide": [name(l["name"]) for l in g.leads], "features": features, "setters": sorted(setters),
                         "rate_pick": [name(x) for x in sorted(rates, key=rates.get, reverse=True)[:2]] if rates else []})
        if args.limit and len(rows_out) >= args.limit:
            break

    n = len(rows_out)
    same = lambda a, b: to_id(a) == to_id(b)
    hit = lambda r, picks: any(same(r["lead"], p) for p in picks)

    def report(label, k):
        lo, hi = wilson(k, n)
        print(f"  {label:44s} {k:4d}/{n}  {k / n:6.1%}  (95% CI {lo:.1%} to {hi:.1%})")

    print(f"{fmt}: {n} games from {len(all_games)} sides ({skipped} skipped: a set missing; {fallbacks} rare members "
          f"took their {LOWER.get(fmt, 'lower tier')} set) in {time.time() - t0:.0f} s\n")
    print("Actual lead among the two picks:")
    report("random two of six (expected)", round(n / 3))
    report("lead rate baseline (Smogon leads / usage)", sum(hit(r, r["rate_pick"]) for r in rows_out))
    report("Coach Guide", sum(hit(r, r["guide"]) for r in rows_out))
    report("Coach Guide first pick only", sum(hit(r, r["guide"][:1]) for r in rows_out))
    replica = sum(pick(r["features"], r["win"], WEIGHTS) == r["guide"] for r in rows_out)
    print(f"  (replica of the guide's score matches on {replica}/{n})")
    only_guide = sum(hit(r, r["guide"]) and not hit(r, r["rate_pick"]) for r in rows_out)
    only_rate = sum(hit(r, r["rate_pick"]) and not hit(r, r["guide"]) for r in rows_out)
    print(f"  paired vs the baseline: guide alone right {only_guide}, baseline alone right {only_rate}, "
          f"exact McNemar p = {mcnemar(only_guide, only_rate):.2f}")
    for label, part in (("rated 1500+", [r for r in rows_out if r["rating"] >= 1500]),
                        ("rated under 1500", [r for r in rows_out if r["rating"] < 1500])):
        if part:
            g_hit, b_hit = sum(hit(r, r["guide"]) for r in part), sum(hit(r, r["rate_pick"]) for r in part)
            print(f"  {label:16s} {len(part):4d} games: guide {g_hit / len(part):.0%}, baseline {b_hit / len(part):.0%}")
    report("player led with the guide's win condition", sum(same(r["lead"], r["win"] or "") for r in rows_out))

    print("\nAblation (drop one term of the lead score):")
    for term in WEIGHTS:
        w = dict(WEIGHTS, **{term: 0.0})
        report(f"without {term}", sum(hit(r, pick(r["features"], r["win"], w)) for r in rows_out))
    report("without the win condition exclusion", sum(hit(r, pick(r["features"], None, WEIGHTS)) for r in rows_out))

    sub = [r for r in rows_out if r["setters"]]
    if sub:
        led = sum(any(same(r["lead"], s) for s in r["setters"]) for r in sub)
        got = sum(hit(r, r["guide"]) for r in sub)
        base = sum(hit(r, r["rate_pick"]) for r in sub)
        print(f"\nTeams with a weather or terrain setter: {len(sub)}")
        print(f"  player led with the setter     {led}/{len(sub)}  {led / len(sub):.0%}")
        print(f"  guide two picks hit            {got}/{len(sub)}  {got / len(sub):.0%}")
        print(f"  lead rate baseline hit         {base}/{len(sub)}  {base / len(sub):.0%}")
        for r in sub[:8]:
            print(f"    {r['id']} {r['side']}: setters {r['setters']}, led {r['lead']}, guide {r['guide']}")

    out = ROOT / "bench" / "results" / f"guide_leads_{fmt}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for r in rows_out:
            f.write(json.dumps(r) + "\n")
    print(f"\nPer game rows: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
