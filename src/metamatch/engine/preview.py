"""
Matchup Preview: your team against one specific opposing team, one matchup at a time, from the damage calc.
The opponent can be a full Showdown paste (its sets are used as written) or just names (each gets its most
common ladder set). For Champions' bring 3 of 6, it also picks the three that hold up best against any
three the opponent could bring: the worst case over all 20 of their trios, never a guess of their picks.
"""
import re
from itertools import combinations

from metamatch import config
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.names import find_pokemon
from metamatch.engine.sets import likely_set
from metamatch.engine.threat_board import row_for_set
from metamatch.team import readTeam

LABELS = {"HP": "hp", "Atk": "atk", "Def": "def", "SpA": "spa", "SpD": "spd", "Spe": "spe"}


def _set_from_member(p, format_id):
    """A parsed team member shaped like a likely_set, so it can be used as an opponent."""
    champions = config.format_game(format_id) == "champions"
    spread = p.get("SP") if champions else p.get("EVs")
    return {"name": p.get("Forme") or p["Pokemon"], "nature": p.get("Nature") or "Serious",
            "evs": {LABELS[k]: v for k, v in (spread or {}).items() if k in LABELS},
            "item": p.get("Item") or None, "ability": p.get("Mega Ability") or p.get("Ability") or None,
            "moves": [(m["name"], 1.0) for m in p.get("Moves", [])],
            "speeds": [(p.get("Speed", 0), 1.0)], "scarf_share": 0.0, "usage": 0.0, "stated": True}


def opponent_sets(text, format_id):
    """(sets, unknown names) from a pasted team: full Showdown sets as written, or bare names on ladder sets."""
    text = (text or "").strip()
    if not text:
        return [], []
    if re.search(r"^\s*-\s+\S", text, re.M) or "Ability:" in text:
        team, _ = readTeam(text, format_id)
        return [_set_from_member(p, format_id) for p in team.values()][:6], []
    sets, unknown = [], []
    for name in find_pokemon(text)[:6]:
        s = likely_set(name, format_id)
        (sets.append(s) if s else unknown.append(name))
    return sets, unknown


def preview(team, sets, format_id):
    """Board rows, one per opposing Pokemon, in the order given."""
    return [r for r in (row_for_set(team, s, format_id) for s in sets) if r]


def bring_three(rows, members, k=3):
    """
    Trios of `members` ranked by the worst case over every trio the opponent could bring: how many of their
    three have at least one answer among yours. Ties go to the higher average, then to more total wins.
    Returns [(trio, worst, average)] best first.
    """
    if len(members) < k or len(rows) < k:
        return []
    beats = {m: {r.name for r in rows if r.cells.get(m) and r.cells[m].verdict == "win"} for m in members}
    theirs = list(combinations([r.name for r in rows], k))
    ranked = []
    for trio in combinations(members, k):
        covered = set().union(*(beats[m] for m in trio))
        counts = [sum(t in covered for t in their) for their in theirs]
        ranked.append((trio, min(counts), sum(counts) / len(counts), sum(len(beats[m]) for m in trio)))
    ranked.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)
    return [(trio, worst, avg) for trio, worst, avg, _ in ranked]


def is_bring_three(format_id):
    """Champions ranked singles brings 3 of 6."""
    return config.format_game(format_id) == "champions"
