"""
Move Search: which Pokemon in a format run, or can learn, every move you pick. Three tiers by evidence:

* smogon: a Smogon Strategy Dex set for this format lists every move,
* ladder: every move is on at least 1% of its ladder sets this month. Usage stats give each move's share but
  not how often they come together, so `together` is the share that must run all of them whatever the overlap
  (the Frechet lower bound, max(0, sum of shares - (n - 1))),
* learn: it learns every move (engine/learnsets.py) but doesn't run them.

Every result is a Pokemon with usage in the format, so each one is legal and seen there. Near misses (runs all
but one move) fill in when the first two tiers come up short.
"""
from metamatch import config
from metamatch.auditor import load_chaos_data
from metamatch.engine.builder import paste_species, smogon_options
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.learnsets import learns

MIN_SHARE = 0.01     # a move on fewer of its sets doesn't count as run
MIN_USAGE = 0.001    # Pokemon below this usage are noise in the stats
NEAR_WHEN = 4        # show near misses when fewer full matches than this
TIERS = ("smogon", "ladder", "learn")


def together(shares):
    """The share of sets that must run every move, from each move's own share (0..1), whatever the overlap."""
    return max(0.0, sum(shares) - (len(shares) - 1))


def _shares(entry):
    """{move id: share of this Pokemon's sets} from a usage stats entry."""
    total = sum((entry.get("Abilities") or {}).values()) or 1
    return {to_id(m): w / total for m, w in (entry.get("Moves") or {}).items()}


def _pool(format_id):
    data = load_chaos_data(format_id) or {}
    return {name: entry for name, entry in data.items() if entry.get("usage", 0) > MIN_USAGE}


def move_options(format_id, strat_data=None):
    """Every move some Pokemon in this format runs or can learn, by its proper name, sorted."""
    dex = dex_for_format(format_id)
    ids = set()
    for name, entry in _pool(format_id).items():
        ids |= set(_shares(entry))
        ids |= learns(name, format_id)
    names = {dex.move_name(i) for i in ids} if dex else set()
    return sorted((n for n in names if n), key=str.lower)


def search(moves, format_id, strat_data=None):
    """One result per Pokemon that runs or learns every move, smogon tier first, then ladder, then learn, each by
    usage: {name, usage (0..1), tier, sets: [Smogon set names], shares: {move: share}, together}. Near misses
    come last with tier 'near' and the move they don't run as `missing`."""
    picked = [m for m in dict.fromkeys(moves) if m]
    if not picked:
        return []
    ids = [to_id(m) for m in picked]
    label = config.format_info(format_id)["label"]
    out, near = [], []
    for name, entry in _pool(format_id).items():
        share = _shares(entry)
        on = {m: share.get(i, 0.0) for m, i in zip(picked, ids)}
        sets = [s for s in smogon_options(name, strat_data, label)
                if set(ids) <= {to_id(x) for x in
                                ((strat_data or {}).get(paste_species(name), {}).get("sets", {}).get(s, {}).get("moves") or [])}]
        result = {"name": name, "usage": entry.get("usage", 0), "sets": sets, "shares": on,
                  "together": together(on.values())}
        if sets:
            out.append({**result, "tier": "smogon"})
        elif all(v >= MIN_SHARE for v in on.values()):
            out.append({**result, "tier": "ladder"})
        elif set(ids) <= learns(name, format_id):
            out.append({**result, "tier": "learn"})
        elif len(picked) > 1:
            missing = [m for m, v in on.items() if v < MIN_SHARE]
            if len(missing) == 1:
                near.append({**result, "tier": "near", "missing": missing[0],
                             "learns_missing": to_id(missing[0]) in learns(name, format_id)})
    out.sort(key=lambda r: (TIERS.index(r["tier"]), -r["usage"]))
    if sum(r["tier"] != "learn" for r in out) < NEAR_WHEN:
        out += sorted(near, key=lambda r: -r["usage"])
    return out


def move_info(move):
    """{type, category, power, short} for a move, from Showdown's data (engine/rules.py)."""
    from metamatch.engine import rules
    e = rules.entry("move", move)
    return {"type": e.get("type"), "category": e.get("category"), "power": e.get("basePower") or 0,
            "short": e.get("short", "")}
