"""
Can MetaMatch finish a team from a few names? Keep k members of a real ladder team (k = 1 to 5), fill the rest
with each method in engine/team_fill.py, and count how many of the hidden members come back.

  python bench/recommender/fill.py                       # gen9ou
  python bench/recommender/fill.py --format gen9natdex
  python bench/recommender/fill.py --sound 100           # also check filled teams for unanswered threats

Split by player like neighbors.py: the 80% of players seen first are what the neighbour search can see, the
newest 20% are the test teams. Metrics per k: slot recall (share of hidden members recovered) and full hit
(every hidden member recovered). A paired permutation test compares the best method with the others.
"""
import argparse
import random
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from metamatch.engine import team_fill  # noqa: E402
from metamatch.engine import team_neighbors as tn  # noqa: E402


def split(fmt):
    """(train rows, test rows): distinct teams, the newest 20% of players held out."""
    rows = (tn._corpus_file().get("formats") or {}).get(fmt) or []
    teams = {}
    for r in sorted(rows, key=lambda r: r["time"]):
        teams.setdefault(frozenset(tn.base(n) for n in r["team"]), r)
    ordered = sorted(teams.values(), key=lambda r: r["time"])
    first_seen = {}
    for r in ordered:
        first_seen.setdefault(r.get("p"), r["time"])
    players = sorted(first_seen, key=first_seen.get)
    held = set(players[int(len(players) * 0.8):])
    return [r for r in ordered if r.get("p") not in held], [r for r in ordered if r.get("p") in held]


def permutation_p(a, b, rounds=5000):
    diffs = [x - y for x, y in zip(a, b)]
    observed, rng = abs(sum(diffs)), random.Random(0)
    hits = sum(abs(sum(d if rng.random() < 0.5 else -d for d in diffs)) >= observed for _ in range(rounds))
    return sum(diffs) / len(diffs), (hits + 1) / (rounds + 1)


def unanswered(names, fmt):
    """Top 15 threats nothing on the team beats one on one, with every member on its usual set."""
    from metamatch.engine.completer import member_from_set
    from metamatch.engine.sets import likely_set
    from metamatch.engine.threat_board import threat_board
    team = {i: member_from_set(s, fmt) for i, s in enumerate(likely_set(n, fmt) for n in names) if s}
    return sum(1 for r in threat_board(team, n=15, format_id=fmt) if not r.answers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--format", default="gen9ou")
    ap.add_argument("--limit", type=int, default=0, help="test teams to use (0: all)")
    ap.add_argument("--sound", type=int, default=0, help="test teams to check for unanswered threats")
    args = ap.parse_args()
    fmt = args.format
    train, test = split(fmt)
    rng = random.Random(7)
    trials = []
    for r in test:
        six = [tn.base(n) for n in r["team"]]
        if len(set(six)) < 6:
            continue
        for k in range(1, 6):
            trials.append((k, six, rng.sample(six, k)))
    if args.limit:
        keep = {tuple(t[1]) for t in trials[:args.limit * 5]}
        trials = [t for t in trials if tuple(t[1]) in keep]

    recall = {m: [] for m in team_fill.METHODS}
    full = {m: [] for m in team_fill.METHODS}
    filled_teams = {m: [] for m in team_fill.METHODS}
    with mock.patch.object(tn, "_corpus_file", lambda: {"formats": {fmt: train}}):
        for f in (tn.corpus, tn._idf):
            f.cache_clear()
        known = team_fill._known(fmt)
        for k, six, kept in trials:
            # The corpus lists Megas by base name; the fill works on the names the stats list
            core = [team_fill._as_listed(n, fmt, known) or n for n in kept]
            hidden = set(six) - set(kept)
            for m in team_fill.METHODS:
                team, _ = team_fill.fill(core, fmt, method=m)
                got = len(hidden & {tn.base(n) for n in team})
                recall[m].append(got / len(hidden))
                full[m].append(float(got == len(hidden)))
                filled_teams[m].append((k, six, team))

    print(f"{fmt}: {len(train)} teams to search, {len(trials) // 5} test teams, {len(trials)} trials")
    print("  method       " + "  ".join(f"k={k}  " for k in range(1, 6)) + "  all    full")
    for m in team_fill.METHODS:
        by_k = [sum(v for (k, _, _), v in zip(trials, recall[m]) if k == kk) / max(1, sum(t[0] == kk for t in trials))
                for kk in range(1, 6)]
        print(f"  {m:11} " + "  ".join(f"{v:.3f}" for v in by_k)
              + f"  {sum(recall[m]) / len(recall[m]):.3f}  {sum(full[m]) / len(full[m]):.3f}")
    best = max(team_fill.METHODS, key=lambda m: sum(recall[m]))
    for m in team_fill.METHODS:
        if m != best:
            diff, p = permutation_p(recall[best], recall[m])
            print(f"  {best} vs {m}: slot recall {diff:+.3f} (p = {p:.4f})")

    if args.sound:
        # Seeded sample of trials: unanswered top threats for the real team and each method's filled team
        sample = random.Random(11).sample(range(len(trials)), min(args.sound, len(trials)))
        known = team_fill._known(fmt)
        real = [unanswered([team_fill._as_listed(n, fmt, known) or n for n in trials[i][1]], fmt) for i in sample]
        print(f"  unanswered top 15 threats over {len(sample)} trials: real teams {sum(real) / len(real):.2f}")
        for m in team_fill.METHODS:
            got = [unanswered(filled_teams[m][i][2], fmt) for i in sample]
            diff, p = permutation_p(got, real)
            print(f"    {m:11} {sum(got) / len(got):.2f}  (vs real {diff:+.2f}, p = {p:.3f})")


if __name__ == "__main__":
    main()
