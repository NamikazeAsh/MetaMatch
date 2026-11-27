"""
Does "Teams like yours" know what a team is missing? Hide one member of a real ladder team and see where each
method ranks it, on teams it has never seen.

  python bench/recommender/neighbors.py            # gen9ou
  python bench/recommender/neighbors.py --format gen9natdex

The ladder corpus (data/json/ladder_teams.json) is split by player: the 80% of players seen first are what the
neighbour search can see, the rest are the test teams, so no player is on both sides. For each test team and each of its six members, the
member is hidden and three methods rank candidates for the open slot:
  * neighbours: what the closest older teams run that the five don't (engine/team_neighbors.additions)
  * pairing: Quick Match's ranking of partners for the five from the ladder's teammate stats (completer.core_partners)
  * blend: the two above fused by reciprocal rank
  * reorder: what Quick Match shows, the pairing candidates reordered by the blend
  * popularity: the format's most used Pokemon not already on the team
Metrics: hit@1, hit@5 (the hidden member is in the top k) and MRR, over every hidden member.
"""
import argparse
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from metamatch.auditor import load_chaos_data  # noqa: E402
from metamatch.engine import team_neighbors as tn  # noqa: E402
from metamatch.engine.completer import core_partners  # noqa: E402


def _score(ranked, hidden, stats):
    names = [tn.base(n) for n in ranked]
    rank = names.index(hidden) + 1 if hidden in names else None
    stats.setdefault("rr", []).append(1 / rank if rank else 0.0)
    stats.setdefault("in5", []).append(1.0 if rank and rank <= 5 else 0.0)
    stats["n"] += 1
    stats["h1"] += rank == 1
    stats["h5"] += bool(rank) and rank <= 5
    stats["mrr"] += 1 / rank if rank else 0


def blend(*rankings, k=10):
    """Reciprocal rank fusion of several rankings (k=10: the top few picks of each list dominate)."""
    score = {}
    for ranking in rankings:
        for rank, name in enumerate(ranking):
            score[name] = score.get(name, 0) + 1 / (k + rank + 1)
    return sorted(score, key=score.get, reverse=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="gen9ou")
    ap.add_argument("--k", type=int, default=20, help="neighbours to read additions from")
    args = ap.parse_args()
    fmt = args.format
    rows = (tn._corpus_file().get("formats") or {}).get(fmt) or []
    teams = {}
    for r in sorted(rows, key=lambda r: r["time"]):
        teams.setdefault(frozenset(tn.base(n) for n in r["team"]), r)
    ordered = sorted(teams.values(), key=lambda r: r["time"])
    # Split by player, not by team: the newest 20% of players are tested, and none of their teams are searchable,
    # so a player's near identical second team can't hand the neighbour search the answer
    first_seen = {}
    for r in ordered:
        first_seen.setdefault(r.get("p"), r["time"])
    players = sorted(first_seen, key=first_seen.get)
    held = set(players[int(len(players) * 0.8):])
    train = [r for r in ordered if r.get("p") not in held]
    test = [r for r in ordered if r.get("p") in held]
    data = load_chaos_data(fmt) or {}
    popular = [tn.base(n) for n, e in sorted(data.items(), key=lambda kv: -kv[1].get("usage", 0))]
    methods = {m: {"n": 0, "h1": 0, "h5": 0, "mrr": 0.0} for m in ("neighbours", "pairing", "blend", "reorder", "popularity")}
    with mock.patch.object(tn, "_corpus_file", lambda: {"formats": {fmt: train}}):
        for f in (tn.corpus, tn._idf):
            f.cache_clear()
        for r in test:
            six = [tn.base(n) for n in r["team"]]
            if len(set(six)) < 6:
                continue
            for hidden in six:
                five = [n for n in six if n != hidden]
                near = tn.neighbors(five, fmt, k=args.k)
                by_neighbours = [x for x, _, _ in tn.additions(five, near, limit=20)]
                by_pairing = [tn.base(p["name"]) for p in core_partners(five, fmt, n=20)]
                _score(by_neighbours, hidden, methods["neighbours"])
                _score(by_pairing, hidden, methods["pairing"])
                _score(blend(by_pairing, by_neighbours), hidden, methods["blend"])
                # What Quick Match can show: the pairing candidates (cards need their pairing data), reordered
                pool = [tn.base(p["name"]) for p in core_partners(five, fmt, n=30)]
                _score([x for x in blend(pool, by_neighbours) if x in pool][:20], hidden, methods["reorder"])
                _score([n for n in popular if n not in five][:20], hidden, methods["popularity"])
    print(f"{fmt}: {len(train)} teams to search, {len(test)} test teams, {methods['neighbours']['n']} hidden members")
    for m, s in methods.items():
        n = s["n"] or 1
        print(f"  {m:11} hit@1 {s['h1'] / n:.2f}  hit@5 {s['h5'] / n:.2f}  MRR {s['mrr'] / n:.3f}")
    # Is the blend really better than pairing alone? Paired permutation test, hidden member by hidden member
    import random
    for metric in ("rr", "in5"):
        a, b = methods["pairing"][metric], methods["reorder"][metric]
        diffs = [x - y for x, y in zip(b, a)]
        observed, rng = abs(sum(diffs)), random.Random(0)
        hits = sum(abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed for _ in range(5000))
        print(f"  reorder vs pairing, {metric}: {sum(diffs) / len(diffs):+.3f} (p = {(hits + 1) / 5001:.3f})")


if __name__ == "__main__":
    main()
