"""
A transparent team score for "is my team good": eight parts, each worked out from engine facts and shown with its
evidence, plus where the total sits among real ladder teams. It describes how well a team is covered and built; it
does not predict wins (games come down to the player).

Parts (weights out of 100): coverage of the format's most used Pokemon 25, switch ins 15, hazards 15, mutual cover 10,
shared weaknesses 10, Speed 10, roles 10, cores 5. Known blind spots, printed with the score: one on ones ignore
recovery, status and Trick Room, so full stall and Trick Room teams score lower than they play.
Design and the ladder check: docs/research/chat_plan_v2_2026_11_15.md (Team score).
"""
import json
from dataclasses import dataclass, field

from metamatch import config
from metamatch.engine import speed_board, synergy
from metamatch.engine.dex import dex_for_format
from metamatch.engine.guide import HAZARDS, N_SPEED, N_THREATS, PIVOTS, REMOVAL, SETUP
from metamatch.engine.threat_board import cell_numbers, safe_switch, threat_board

WEIGHTS = {"coverage": 25, "switchins": 15, "hazards": 15, "mutual_cover": 10, "weaknesses": 10, "speed": 10,
           "roles": 10, "cores": 5}
LABELS = {"coverage": "Coverage of top threats", "switchins": "Switch ins", "hazards": "Hazards",
          "mutual_cover": "Teammates covering each other", "weaknesses": "Shared weaknesses", "speed": "Speed",
          "roles": "Core roles", "cores": "Team engines"}
RECOVERY = {"Recover", "Roost", "Slack Off", "Soft-Boiled", "Shore Up", "Synthesis", "Moonlight", "Morning Sun",
            "Strength Sap", "Wish", "Milk Drink", "Rest", "Life Dew", "Lunar Blessing", "Jungle Healing"}
TABLE = config.DATA_DIR / "json" / "team_score_ladder.json"


@dataclass
class Part:
    key: str
    value: float          # 0..1
    evidence: str

    @property
    def points(self):
        return round(WEIGHTS[self.key] * self.value, 1)


@dataclass
class Score:
    total: float
    parts: list = field(default_factory=list)
    percentile: float | None = None   # share of the sample's ladder teams this total beats
    sample: int = 0
    notes: list = field(default_factory=list)


def _moves(p):
    return {m["name"] for m in p.get("Moves", [])}


def _join(xs):
    xs = list(xs)
    return "none" if not xs else xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def score_team(team, format_id=None, rows=None):
    """Score for a team (readTeam output). rows: Threat Board rows to reuse (threat_board output)."""
    format_id = format_id or config.team_format(team)
    dex = dex_for_format(format_id)
    rows = rows if rows is not None else threat_board(team, n=N_THREATS, format_id=format_id)
    names = [p["Pokemon"] for p in team.values()]
    usage = {r.name: r.usage for r in rows}
    total_usage = sum(usage.values()) or 1
    parts = []

    # Coverage: usage weighted; two or more members that win one on one is full credit, one is 0.6
    got, thin = 0.0, []
    for r in rows:
        n = len(r.answers)
        got += r.usage * (1.0 if n >= 2 else 0.6 if n == 1 else 0.0)
        if n <= 1:
            thin.append(f"{r.name} ({'only ' + r.answers[0] if n == 1 else 'no answer'})")
    parts.append(Part("coverage", got / total_usage,
                      f"Of the {len(rows)} most used Pokemon, answered thinly: {_join(thin)}."))

    # Switch ins: the one switch in rule (threat_board.safe_switch), shared with the guide and the chat
    got, none_in = 0.0, []
    for r in rows:
        ins = [m for m, c in r.cells.items() if safe_switch(cell_numbers(c.exchange))]
        got += r.usage * (1.0 if len(ins) >= 2 else 0.6 if ins else 0.0)
        if not ins:
            none_in.append(r.name)
    parts.append(Part("switchins", got / total_usage,
                      f"No member takes the strongest hit for under half its HP, or three of them, from: {_join(none_in)}."))

    # Hazards: setting them and removing them (three or more Heavy-Duty Boots count as half the removal)
    setters = [p["Pokemon"] for p in team.values() if _moves(p) & set(HAZARDS)]
    removers = [p["Pokemon"] for p in team.values() if _moves(p) & set(REMOVAL)]
    boots = sum(1 for p in team.values() if p.get("Item") == "Heavy-Duty Boots")
    parts.append(Part("hazards", 0.5 * bool(setters) + (0.5 if removers else 0.25 if boots >= 3 else 0.0),
                      f"Hazard setters: {_join(setters)}. Hazard removal: {_join(removers)}. Heavy-Duty Boots: {boots}."))

    # Mutual cover: of each member's one on one losses, how many a teammate wins
    losses = [(m, r) for r in rows for m in r.losses]
    covered = [(m, r) for m, r in losses if any(a != m for a in r.answers)]
    parts.append(Part("mutual_cover", len(covered) / len(losses) if losses else 1.0,
                      f"{len(covered)} of {len(losses)} one on one losses have a teammate that wins that matchup."))

    # Shared weaknesses: types two or more members are weak to with more weak than resisting; 4x weaknesses too
    shared, quad = [], []
    for t in list(dex.type_chart if dex else {}):
        weak = [p["Pokemon"] for p in team.values() if _taken(p, t, dex) >= 2]
        resist = [p["Pokemon"] for p in team.values() if _taken(p, t, dex) < 1]
        if len(weak) >= 2 and len(weak) > len(resist):
            shared.append(f"{t} ({len(weak)} weak, {len(resist)} resist)")
        quad += [f"{p['Pokemon']} (4x {t})" for p in team.values() if _taken(p, t, dex) >= 4]
    parts.append(Part("weaknesses", max(0.0, 1 - 0.2 * len(shared) - 0.05 * len(quad)),
                      f"Shared weaknesses: {_join(shared)}. Quadruple weaknesses: {_join(quad)}."))

    # Speed: how much of the top ladder the fastest member outspeeds, plus priority or Choice Scarf
    speeds = speed_board.member_speeds(team, format_id)
    meta = speed_board.meta_speeds(format_id, n=N_SPEED, exclude=names)
    share = {n: (sum(speed_board.outspeed_share(s, m) for m in meta) / len(meta) if meta else 0.0) for n, s in speeds.items()}
    fastest = max(share, key=share.get) if share else None
    priority = [p["Pokemon"] for p in team.values()
                if any((dex.move(m) or {}).get("priority", 0) > 0 and (dex.move(m) or {}).get("category") != "Status"
                       for m in _moves(p))] if dex else []
    scarf = [p["Pokemon"] for p in team.values() if p.get("Item") == "Choice Scarf"]
    parts.append(Part("speed", 0.5 * (share.get(fastest, 0.0)) + 0.5 * bool(priority or scarf),
                      f"Fastest: {fastest or 'none'}, outspeeding {round(100 * share.get(fastest, 0))}% of the top "
                      f"{N_SPEED} ladder sets. Priority: {_join(priority)}. Choice Scarf: {_join(scarf)}."))

    # Roles: a pivot, a setup win condition, and reliable recovery or Regenerator
    pivots = [p["Pokemon"] for p in team.values() if _moves(p) & set(PIVOTS)]
    setup = [p["Pokemon"] for p in team.values() if _moves(p) & set(SETUP)]
    recovery = [p["Pokemon"] for p in team.values() if _moves(p) & RECOVERY or p.get("Ability") == "Regenerator"]
    parts.append(Part("roles", (bool(pivots) + bool(setup) + bool(recovery)) / 3,
                      f"Pivots: {_join(pivots)}. Setup: {_join(setup)}. Recovery or Regenerator: {_join(recovery)}."))

    # Cores: a complete weather, terrain, Trick Room, Tailwind or screens core (a bonus; most balance teams have none)
    try:
        cores = [e.label for e in synergy.team_engines(team, format_id, measure=False) if e.complete]
    except Exception:
        cores = []
    parts.append(Part("cores", 1.0 if cores else 0.0, f"Complete team engines: {_join(cores)}."))

    total = round(sum(p.points for p in parts), 1)
    result = Score(total, parts)
    table = ladder_table(format_id)
    if table:
        result.percentile = sum(1 for x in table if x < total) / len(table)
        result.sample = len(table)
    walls = sum(1 for p in team.values() if _moves(p) & RECOVERY)
    trick_room = any("Trick Room" in _moves(p) for p in team.values())
    if walls >= 4 or trick_room:
        result.notes.append("This score does not capture stall or Trick Room plans: one on ones ignore recovery, "
                            "status and Trick Room.")
    result.notes.append("The score describes how the team is covered and built; it does not predict results.")
    return result


def _taken(p, t, dex):
    """Damage multiplier member `p` takes from type `t`: its Damage From table (abilities included) when it has one,
    else the type chart (sample ladder teams are built from likely sets without the table)."""
    table = p.get("Damage From")
    if table:
        return table.get(t.lower(), 1.0)
    x = 1.0
    for d in p.get("Type") or []:
        x *= dex.type_chart.get(t, {}).get(d, 1.0)
    return x


def ladder_table(format_id):
    """Sorted totals of the sample ladder teams for this format (scripts/build_team_score_table.py), or []."""
    try:
        return sorted(json.loads(TABLE.read_text(encoding="utf-8")).get(format_id, []))
    except (OSError, ValueError):
        return []

