"""
Build a team from a few names: read the names out of free text ("gholdengo, great tusk, kingambit"), then fill
the open slots one at a time with what real teams around them run.

Fill methods (bench/recommender/fill.py compares them on held out ladder teams):
  * popularity: the format's most used Pokemon not already taken
  * pairing: Quick Match's partner ranking for the team so far (completer.core_partners)
  * blend: those partners reordered by the closest real ladder teams (team_neighbors.reorder), what Quick Match shows
  * nearest: the rest of the closest real team that runs every named member, then blend for any gap
Every method keeps Species Clause and one Mega, and refills after each pick, so later slots see earlier ones.
"""
import re

from metamatch.auditor import load_all_ratings, load_chaos_data
from metamatch.engine import team_neighbors as tn
from metamatch.engine.completer import core_partners
from metamatch.engine.names import find_pokemon
from metamatch.recommender import is_mega

TEAM_SIZE = 6
METHODS = ("popularity", "pairing", "blend", "nearest")
# Best slot recall in every format on held out ladder teams (bench/recommender/fill.py, 2026 11 28): OU 0.185 against
# 0.108 for popularity, Champions OU 0.164 against 0.139, National Dex 0.099 against 0.069 (p 0.0002 each), and its
# filled teams leave no more top threats unanswered than the real teams did
BEST = "blend"
PASTE_RE = re.compile(r"^\s*-\s+\S|Ability:|EVs:|@", re.M)


def looks_like_names(text):
    """True for a list of names rather than a Showdown paste or a pokepast.es link."""
    from metamatch.utils import is_pokepaste_url
    text = (text or "").strip()
    if not text or is_pokepaste_url(text) or PASTE_RE.search(text):
        return False
    return bool(find_pokemon(text))


def species(name, format_id):
    """The species a Pokemon counts as under Species Clause: Sceptile-Mega and Rotom-Heat count as Sceptile and Rotom."""
    from metamatch.engine.dex import dex_for_format
    dex = dex_for_format(format_id)
    s = dex.species(name) if dex else None
    return (s.get("baseSpecies") or s["name"]) if s else name.split("-")[0]


def _known(format_id):
    """{name: usage} for every Pokemon with a set on record in the format, rare picks included."""
    data = load_chaos_data(format_id) or {}
    rare = load_all_ratings(format_id)
    return {n: e.get("usage", 0) for n, e in {**rare, **data}.items()}


def _as_listed(name, format_id, known):
    """The name as the format's stats list it: as is, or its most used forme when only that is listed
    (Charizard in National Dex is Charizard-Mega-Y). None when the format has no record of it."""
    if name in known:
        return name
    base = species(name, format_id)
    formes = [n for n in known if species(n, format_id) == base]
    return max(formes, key=known.get) if formes else None


def parse_names(text, format_id):
    """(names, unknown): the Pokemon named in `text` as the format lists them, one per species, one Mega, at most
    six; `unknown` are the ones the format has no record of."""
    known = _known(format_id)
    names, unknown = [], []
    for raw in find_pokemon(text):
        name = _as_listed(raw, format_id, known)
        if not name:
            unknown.append(raw)
        elif len(names) < TEAM_SIZE and _allowed(name, names, format_id):
            names.append(name)
    return names, unknown


def _allowed(name, team, format_id):
    if name in team or species(name, format_id) in {species(t, format_id) for t in team}:
        return False
    return not (is_mega(name) and any(is_mega(t) for t in team))


def _popular(format_id):
    data = load_chaos_data(format_id) or {}
    return [n for n, _ in sorted(data.items(), key=lambda kv: -kv[1].get("usage", 0))]


def _ranked(team, format_id, method):
    """Candidates for the next slot, best first."""
    if method == "popularity":
        return _popular(format_id)
    partners = core_partners(team, format_id, n=40, min_usage=0.005)
    if method == "pairing":
        return [p["name"] for p in partners]
    return [p["name"] for p in tn.reorder(team, format_id, partners)]


def _nearest(core, format_id, known):
    """The rest of the closest real ladder team that runs every named member, as the format lists them."""
    near = tn.neighbors(core, format_id, k=1, min_shared=len({tn.base(n) for n in core}))
    if not near:
        return []
    return [n for n in (_as_listed(x, format_id, known) for x in near[0]["extra"]) if n]


def fill(core, format_id, method=BEST, has_set=None):
    """(six names, filled names): `core` kept in order, the open slots filled by `method`. `has_set(name)` can veto
    a pick (the app passes one so every member gets a set); fewer than six only when nothing is left to add."""
    team = list(dict.fromkeys(core))[:TEAM_SIZE]
    known = _known(format_id)
    ok = lambda n: _allowed(n, team, format_id) and (has_set is None or has_set(n))
    if method == "nearest" and team:
        for name in _nearest(team, format_id, known):
            if len(team) < TEAM_SIZE and ok(name):
                team.append(name)
        method = "blend"
    while len(team) < TEAM_SIZE:
        ranked = _ranked(team, format_id, method) if team else []
        pick = next((n for n in ranked if ok(n)), None) or next((n for n in _popular(format_id) if ok(n)), None)
        if not pick:
            break
        team.append(pick)
    return team, [n for n in team if n not in core]
