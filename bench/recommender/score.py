"""
Team Completer benchmark on real ladder teams (team previews from local Showdown replays).

For every team and every member: hide that member, ask each method for the next teammate, and record
  * hit@k: the hidden member is in the top k picks (rewards matching what players actually built)
  * coverage gain of the top pick: the share of the five's weak spots it beats one on one (what the
    Team Completer optimises). Every method's top pick is scored the same way.
Methods: popularity (most used Pokemon not on the team), the old usage recommender (summed teammate
counts, recommender.get_recommendations) and the Team Completer (engine/completer.py).

  python bench/recommender/score.py                 # 60 teams from data/replays/pool (gitignored, local only)
  python bench/recommender/score.py --teams 0       # every team
"""
import argparse
import glob
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))


def previews(format_id="gen9ou"):
    """Six Pokemon team previews from local replays of the format, deduplicated."""
    seen, teams = set(), []
    for path in sorted(glob.glob(str(ROOT / "data" / "replays" / "pool" / f"*{format_id}-*.json"))):
        log = json.load(open(path, encoding="utf-8")).get("log", "")
        for side in ("p1", "p2"):
            names = [re.split(r",", line.split("|")[3])[0].strip() for line in log.split("\n")
                     if line.startswith(f"|poke|{side}|")]
            key = tuple(sorted(names))
            if len(names) == 6 and key not in seen:
                seen.add(key)
                teams.append(names)
    return teams


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="gen9ou")
    ap.add_argument("--teams", type=int, default=60, help="teams to sample (0 = all)")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    from metamatch.auditor import load_chaos_data
    from metamatch.engine import completer
    from metamatch.engine.sets import likely_set
    from metamatch.engine.threat_board import top_threats
    from metamatch.recommender import get_recommendations

    data = load_chaos_data(args.format) or {}
    teams = [t for t in previews(args.format) if all(n in data for n in t)]
    if args.teams and len(teams) > args.teams:
        teams = random.Random(args.seed).sample(teams, args.teams)
    print(f"{len(teams)} teams with usage data for every member")

    methods = ("popularity", "usage recommender", "team completer")
    hits = {m: {1: 0, 5: 0, 10: 0} for m in methods}
    gain = {m: 0.0 for m in methods}
    trials, in_pool, t0 = 0, 0, time.time()
    for team in teams:
        sets = {n: likely_set(n, args.format) for n in team}
        if not all(sets.values()):
            continue
        for hidden in team:
            five = [n for n in team if n != hidden]
            members = {f"p{i}": completer.member_from_set(sets[n], args.format) for i, n in enumerate(five)}
            popular = [n for n, _ in top_threats(args.format, exclude=five, n=10)]
            usage_rec = [n for n, _, _ in get_recommendations(five, top_n=10, format_id=args.format)]
            # One ranked list for everything: the completer's own order, plus scores for the baselines' top picks
            scored, _, _ = completer.complete(members, args.format, top_n=200, extra=[popular[0]] + usage_rec[:1])
            completer_rank = [c.name for c in scored]
            gains = {c.name: c.gain for c in scored}
            in_pool += hidden in gains
            for method, ranking in zip(methods, (popular, usage_rec, completer_rank)):
                for k in hits[method]:
                    hits[method][k] += hidden in ranking[:k]
                gain[method] += gains.get(ranking[0], 0.0) if ranking else 0.0
            trials += 1
    print(f"{trials} hide one out trials in {time.time() - t0:.0f} s; the hidden member was in the completer's candidate pool "
          f"{in_pool / trials * 100:.0f}% of the time\n")
    print(f"{'method':20s} {'hit@1':>7s} {'hit@5':>7s} {'hit@10':>7s} {'top pick fixes':>15s}")
    for m in methods:
        h = hits[m]
        print(f"{m:20s} {h[1] / trials * 100:6.1f}% {h[5] / trials * 100:6.1f}% {h[10] / trials * 100:6.1f}% "
              f"{gain[m] / trials * 100:14.1f}%")
    print("\n'top pick fixes' is the average share of the five's weak spots (threats with one answer or none,"
          " weighted by usage) that the method's first pick beats one on one.")


if __name__ == "__main__":
    main()
