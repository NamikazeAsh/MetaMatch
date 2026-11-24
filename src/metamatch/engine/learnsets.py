"""
Which moves a Pokemon can learn in a format, from data/json/learnsets.json (scripts/build_learnsets.py, built from
Pokemon Showdown's data). Follows the same rules Showdown's team validator does:
* an evolution also learns its pre-evolution's moves (Samurott-Hisui gets Dewott's),
* a forme like Rotom-Wash or Ogerpon-Wellspring also learns its base form's,
* a forme with no entry of its own, like a Mega, uses its base species',
* National Dex adds the moves only earlier generations teach, and Champions uses its own movepools.
"""
import json
from functools import lru_cache

from metamatch import config
from metamatch.engine.dex import to_id

PATH = config.JSON_DIR / "learnsets.json"


@lru_cache(maxsize=1)
def _data():
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _table(game):
    return {sid: set(moves.split()) for sid, moves in (_data().get(game) or {}).items()}


@lru_cache(maxsize=4)
def _tables():
    return {"sv": _table("sv"), "past": _table("past"), "champions": _table("champions"), "dex": _data().get("dex") or {}}


def _walk(sid, own, dex, seen):
    """Moves for `sid` from table `own`, adding its pre-evolution's and (for a changing forme) its base form's."""
    if sid in seen:
        return set()
    seen.add(sid)
    info = dex.get(sid, {})
    if sid not in own and info.get("baseSpecies"):
        return _walk(info["baseSpecies"], own, dex, seen)
    moves = set(own.get(sid, ()))
    for parent in (info.get("prevo"), info.get("changesFrom")):
        if parent:
            moves |= _walk(parent, own, dex, seen)
    return moves


@lru_cache(maxsize=4096)
def learns(name, format_id):
    """Every move id `name` can learn in `format_id` (frozenset), empty when there's no data for it."""
    t = _tables()
    sid = to_id(name)
    if config.format_game(format_id) == "champions":
        # Champions' own movepools; a Pokemon it doesn't list keeps its Scarlet and Violet one
        moves = _walk(sid, t["champions"], t["dex"], set())
        if moves:
            return frozenset(moves)
    moves = _walk(sid, t["sv"], t["dex"], set())
    if format_id == "gen9natdex":
        moves |= _walk(sid, t["past"], t["dex"], set())
    return frozenset(moves)
