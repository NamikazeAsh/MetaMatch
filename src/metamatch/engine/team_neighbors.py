"""
Teams like yours: case based retrieval over real ladder teams (data/json/ladder_teams.json, built from public
Showdown replays by scripts/fetch_ladder_teams.py). The closest teams to yours share the most of your members,
rare members counting for more (IDF weights: two teams that both run a niche pick are more alike than two that
both run Great Tusk). A member you have and they don't still counts a little when they run a near substitute,
judged by a Pokemon embedding learned from who players pair each Pokemon with (an SVD of the ladder's teammate
PPMI matrix: Iron Treads and Great Tusk share teammates, so they sit close together).

From the closest teams, `substitutions` reads what they run in your other slots: "of your 20 closest teams, 9
don't run Weavile, and 5 of those run Toxapex". Facts only: these are real teams with links to their replays,
never win rates.
"""
import json
import math
from collections import Counter
from functools import lru_cache

from metamatch import config
from metamatch.auditor import load_chaos_data

PATH = config.JSON_DIR / "ladder_teams.json"
DIMS = 24          # size of the Pokemon embedding
SOFT = 0.5         # most a near substitute can count for, against 1 for the same Pokemon
MIN_SHARED = 3     # a neighbour shares at least this many of your members


def base(name):
    """Megas compare as their base species: a preview never shows the Mega, and a team that never Mega Evolved
    still ran the stone."""
    return (name or "").split("-Mega")[0]


@lru_cache(maxsize=1)
def _corpus_file():
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=8)
def corpus(format_id):
    """Distinct teams for a format: {team (frozenset of base names): {records: [...newest first], rating, time}}.
    The same six from different games is one team, with every game kept for precedents."""
    rows = (_corpus_file().get("formats") or {}).get(format_id) or []
    teams = {}
    for r in rows:
        key = frozenset(base(n) for n in r["team"])
        t = teams.setdefault(key, {"team": key, "records": [], "rating": 0, "time": 0})
        t["records"].append(r)
        t["rating"] = max(t["rating"], r.get("rating") or 0)
        t["time"] = max(t["time"], r.get("time") or 0)
    return teams


@lru_cache(maxsize=8)
def _idf(format_id):
    teams = corpus(format_id)
    df = Counter(n for key in teams for n in key)
    total = len(teams) or 1
    return {n: math.log(1 + total / (1 + k)) for n, k in df.items()}, math.log(1 + total)


@lru_cache(maxsize=8)
def embedding(format_id):
    """{base name: unit vector} from the ladder's teammate stats: PPMI of 'X is on a team with Y', reduced by SVD."""
    import numpy as np
    data = load_chaos_data(format_id) or {}
    names = sorted({base(n) for n, e in data.items() if e.get("usage", 0) > 0.001})
    if len(names) < 3:
        return {}
    index = {n: i for i, n in enumerate(names)}
    usage = np.zeros(len(names))
    mat = np.zeros((len(names), len(names)))
    for name, entry in data.items():
        i = index.get(base(name))
        if i is None:
            continue
        usage[i] += entry.get("usage", 0)
        mates = entry.get("Teammates") or {}
        total = sum(v for v in mates.values() if v > 0) or 1
        for mate, w in mates.items():
            j = index.get(base(mate))
            if j is not None and j != i and w > 0:
                mat[i, j] += w / total
    usage = usage / (usage.sum() or 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log(mat / (usage[None, :] + 1e-12))
    ppmi = np.nan_to_num(np.maximum(pmi, 0), nan=0.0, posinf=0.0, neginf=0.0)
    u, s, _ = np.linalg.svd(ppmi, full_matrices=False)
    k = min(DIMS, len(s))
    vecs = u[:, :k] * np.sqrt(s[:k])
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs = vecs / np.where(norms == 0, 1, norms)
    return {n: vecs[i] for n, i in index.items()}


def _closeness(a, b, emb):
    va, vb = emb.get(a), emb.get(b)
    return max(0.0, float(va @ vb)) if va is not None and vb is not None else 0.0


def similarity(mine, theirs, format_id):
    """0..1: the IDF weighted share of your members they run, a near substitute counting up to SOFT."""
    idf, default = _idf(format_id)
    emb = embedding(format_id)
    spare = [n for n in theirs if n not in mine]
    got = total = 0.0
    for n in mine:
        w = idf.get(n, default)
        total += w
        if n in theirs:
            got += w
        elif spare:
            got += w * SOFT * max(_closeness(n, s, emb) for s in spare)
    return got / total if total else 0.0


def neighbors(team_names, format_id, k=20, min_shared=MIN_SHARED):
    """The k real ladder teams closest to yours, best first: {team (their six), shared, missing (yours they don't
    run), extra (theirs you don't), similarity, rating, time, games, replays (newest ids)}."""
    mine = frozenset(base(n) for n in team_names if n)
    out = []
    for key, t in corpus(format_id).items():
        shared = mine & key
        if len(shared) < min_shared:
            continue
        newest = t["records"][0]
        out.append({"team": [base(n) for n in newest["team"]], "shared": sorted(shared), "missing": sorted(mine - key),
                    "extra": sorted(key - mine), "similarity": similarity(mine, key, format_id),
                    "rating": t["rating"], "time": t["time"], "games": len(t["records"]),
                    "replays": [r["id"] for r in t["records"][:3]]})
    out.sort(key=lambda r: (-r["similarity"], -len(r["shared"]), -r["rating"]))
    return out[:k]


def substitutions(team_names, near):
    """For each member of yours, what your closest teams run instead when they don't run it:
    {member: {"without": how many neighbours lack it, "instead": [(pokemon, count), ...]}}."""
    out = {}
    for name in dict.fromkeys(base(n) for n in team_names if n):
        lacking = [r for r in near if name in r["missing"]]
        if not lacking:
            continue
        counts = Counter(x for r in lacking for x in r["extra"])
        out[name] = {"without": len(lacking), "instead": counts.most_common(3)}
    return out


def reorder(core, format_id, partners, k=20):
    """Quick Match's partner cards (completer.core_partners, best first) reordered by fusing their order with what
    the closest real teams run (reciprocal rank fusion, k=10). On held out ladder teams with one member hidden
    (bench/recommender/neighbors.py, 2026 11 27) this put the hidden member in the top 5 more often than the pairing
    order alone: OU 34% to 38%, Champions OU 25% to 27%, National Dex 16% to 17% (paired tests, p 0.05 or less)."""
    near = neighbors(core, format_id, k=k, min_shared=min(MIN_SHARED, max(1, len(core))))
    if not near:
        return partners
    by_teams = [x for x, _, _ in additions(core, near, limit=30)]
    score = {}
    for ranking in ([base(p["name"]) for p in partners], by_teams):
        for rank, name in enumerate(ranking):
            score[name] = score.get(name, 0) + 1 / (10 + rank + 1)
    return sorted(partners, key=lambda p: -score.get(base(p["name"]), 0))


def additions(team_names, near, limit=5):
    """Pokemon your closest teams run that you don't, weighted by how close each team is: [(pokemon, score, teams)]."""
    mine = {base(n) for n in team_names}
    score, count = Counter(), Counter()
    for r in near:
        for x in r["extra"]:
            if x not in mine:
                score[x] += r["similarity"]
                count[x] += 1
    return [(x, round(s, 3), count[x]) for x, s in score.most_common(limit)]
