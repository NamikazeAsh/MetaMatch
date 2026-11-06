"""
Team Completer: picks the next team member by what it adds, not by how popular it is.

* Coverage: the format's top threats are scored against the team (engine/threat_board.py). Threats with no
  answer count fully, threats with a single answer count half. A candidate's gain is the usage weighted
  share of those holes it beats one on one on its most common set.
* Pairing: lift from Smogon teammate data, P(candidate | member) / P(candidate). Above 1 means players pair
  them on purpose; about 1 means the candidate is just popular.
The two are reported separately; the ranking sorts by coverage gain first and pairing second.
"""
import math
from dataclasses import dataclass, field

from metamatch import config
from metamatch.auditor import load_chaos_data
from metamatch.engine.briefing import _verdict, exchange
from metamatch.engine.dex import dex_for_format, to_id
from metamatch.engine.sets import likely_set
from metamatch.engine.threat_board import threat_board, top_threats
from metamatch.recommender import ROLE_FILL_MOVES, base_species, holds_mega_stone, is_mega

SINGLE_ANSWER_WEIGHT = 0.5
PAIRING_WEIGHT = 0.25
ROLE_WEIGHT = 0.1   # per missing core role (hazard setter, hazard remover, pivot) the candidate fills


@dataclass
class Candidate:
    name: str
    usage: float                                   # share of teams, 0 to 100
    gain: float = 0.0                              # share of the team's hole weight it fills, 0..1
    covers: list = field(default_factory=list)     # threats it beats that the team struggles with
    lift: float | None = None                      # mean pairing lift with the team
    best_pair: tuple | None = None                 # (member, lift) with the strongest pairing
    roles: list = field(default_factory=list)      # missing core roles it fills

    @property
    def score(self):
        pairing = math.log2(self.lift) if self.lift else 0.0
        return self.gain + PAIRING_WEIGHT * max(-1.0, min(1.0, pairing)) + ROLE_WEIGHT * len(self.roles)


def _weight(entry):
    return sum((entry or {}).get("Abilities", {}).values()) or 1


def lift(data, a, b):
    """P(b on the team | a on the team) / P(b on a team), from the month's teammate data. None without data."""
    ea, eb = data.get(a), data.get(b)
    if not ea or not eb or not eb.get("usage"):
        return None
    share = ea.get("Teammates", {}).get(b, 0) / _weight(ea)
    return share / eb["usage"]


def member_from_set(s, format_id):
    """A likely_set result shaped like a readTeam member, so engine code written for teams can score it."""
    dex = dex_for_format(format_id)
    labels = {"hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"}
    spread = {labels[k]: v for k, v in (s.get("evs") or {}).items()}
    champions = config.format_game(format_id) == "champions"
    moves = []
    for m, _ in s.get("moves", []):
        data = dex.move(m) if dex else None
        moves.append({"name": m, "category": (data or {}).get("category"), "type": (data or {}).get("type")})
    return {"Pokemon": s["name"], "Item": s.get("item") or "", "Ability": s.get("ability") or "",
            "Nature": s.get("nature"), ("SP" if champions else "EVs"): spread, "EVs" if champions else "SP": {},
            "Moves": moves, "Format": format_id, "Speed": (s.get("speeds") or [(0, 0)])[0][0]}


def _missing_roles(team):
    covered = set()
    for p in team.values():
        covered.update(p.get("Roles", []))
    return set(ROLE_FILL_MOVES) - covered


def _candidate_roles(s):
    moves = {to_id(m) for m, share in s.get("moves", []) if share > 0.05}
    return {role for role, sig in ROLE_FILL_MOVES.items() if moves & sig}


def candidate_pool(team, format_id, n_usage=30, n_pairs=15):
    """Top Pokemon by usage plus the strongest teammates of the team, minus the team (species clause, one Mega)."""
    data = load_chaos_data(format_id) or {}
    names = [p["Pokemon"] for p in team.values()]
    species = {base_species(n) for n in names} | {base_species(p.get("Forme") or "") for p in team.values()}
    has_mega = any(is_mega(n) for n in names) or any(holds_mega_stone(p.get("Item", "")) for p in team.values())
    pool = [n for n, _ in top_threats(format_id, exclude=names, n=n_usage)]
    pairs = {}
    for m in names:
        for mate, w in (data.get(m, {}).get("Teammates") or {}).items():
            pairs[mate] = pairs.get(mate, 0) + w / _weight(data.get(m))
    pool += [m for m, _ in sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)[:n_pairs]]
    out = []
    for c in dict.fromkeys(pool):
        if c not in data or base_species(c) in species or (has_mega and is_mega(c)):
            continue
        out.append(c)
    return out


def complete(team, format_id=None, n_threats=15, top_n=6, extra=()):
    """(ranked candidates, popular but redundant candidates, the board used) for the team's next slot.
    `extra`: more names to score alongside the pool (for comparisons); they are ranked like any other."""
    format_id = format_id or config.team_format(team)
    data = load_chaos_data(format_id) or {}
    dex = dex_for_format(format_id)
    game = config.format_game(format_id)
    board = threat_board(team, n=n_threats, format_id=format_id)
    holes = {r.name: r.usage * (1.0 if not r.answers else SINGLE_ANSWER_WEIGHT if len(r.answers) == 1 else 0.0) for r in board}
    total_hole = sum(holes.values())
    threat_sets = {r.name: likely_set(r.name, format_id) for r in board if holes[r.name] > 0}
    names = [p["Pokemon"] for p in team.values()]
    missing = _missing_roles(team)

    ranked = []
    pool = candidate_pool(team, format_id)
    for c in dict.fromkeys(pool + [x for x in extra if x in data and x not in names]):
        s = likely_set(c, format_id)
        if not s or not dex:
            continue
        member = member_from_set(s, format_id)
        cand = Candidate(s["name"], round(data.get(c, {}).get("usage", 0) * 100, 1))
        for t, opp in threat_sets.items():
            x = exchange(member, opp, game, dex) if opp else None
            if x and _verdict(x) == "win":
                cand.covers.append(t)
        cand.gain = (sum(holes[t] for t in cand.covers) / total_hole) if total_hole else 0.0
        lifts = [(m, lift(data, m, c)) for m in names]
        lifts = [(m, v) for m, v in lifts if v]
        if lifts:
            cand.lift = sum(v for _, v in lifts) / len(lifts)
            cand.best_pair = max(lifts, key=lambda mv: mv[1])
        cand.roles = sorted(_candidate_roles(s) & missing)
        ranked.append(cand)

    ranked.sort(key=lambda c: (c.score, c.usage), reverse=True)
    picks = ranked[:top_n]
    # Popular picks that add nothing new: what a usage only recommender would have suggested
    redundant = sorted((c for c in ranked if c.gain == 0 and c not in picks), key=lambda c: c.usage, reverse=True)[:2]
    return picks, redundant, board
