"""
Engine answers for the strategy questions that used to reach Professor Oak as free text: win condition, leads, the
threats to watch, and the overall game plan. Each is a Verdict built from the Coach Guide (engine/guide.py: Threat
Board one on ones, Speed, synergy engines, ladder lead rates), so Oak only voices a finished answer.

Why: in the 2026 11 14 runs Oak's own advice was right 2 times in 50, and the best free text prompt shape still topped
out at 4 of 12 on these general questions, while an engine sentence plus one voiced "why" was right 18 of 21 times.
"""
import json
import re
from functools import lru_cache

from metamatch import config
from metamatch.engine.guide import team_guide
from metamatch.engine.solvers import Verdict


def _and(names):
    names = list(names)
    if not names:
        return ""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


@lru_cache(maxsize=16)
def _guide_for(team_json, format_id):
    return team_guide(json.loads(team_json), format_id)


def _guide(plan):
    team = plan.team or {}
    return _guide_for(json.dumps(team, sort_keys=True, default=str), plan.format_id or config.team_format(team))


def _sentences(points):
    return [p.rstrip(".") + "." for p in points]


def solve_win(plan, dex, game):
    g = _guide(plan)
    if not g.win:
        return None
    name = g.win["name"]
    facts = [f"{name}: {p}" for p in _sentences(g.win["points"])] + [g.win["keep"]]
    return Verdict("win", name, f"Your {name} is your best route to a win.", facts, persona="strategy")


def _lead_facts(leads):
    return [f"{lead['name']}: {'; '.join(p.rstrip('.') for p in lead['points'])}." for lead in leads]


def solve_lead(plan, dex, game):
    g = _guide(plan)
    if not g.leads:
        return None
    names = [lead["name"] for lead in g.leads]
    statement = f"Lead with your {names[0]}" + (f", or your {names[1]}." if len(names) > 1 else ".")
    return Verdict("lead", names[0], statement, _lead_facts(g.leads), persona="strategy")


def _watch_facts(g):
    return [f"{w['name']} (on {w['usage']:.0f}% of teams): {w['text']}." for w in g.watch]


def solve_threats(plan, dex, game):
    g = _guide(plan)
    if not g.watch:
        statement = f"Every one of the {g.n_threats} most used Pokemon has at least two answers on your team."
        return Verdict("threats", "none", statement, [], persona="strategy")
    names = [w["name"] for w in g.watch]
    verb = "is the threat" if len(names) == 1 else "are the threats"
    statement = f"{_and(names)} {verb} your team answers most thinly."
    return Verdict("threats", ", ".join(names), statement, _watch_facts(g), persona="strategy")


def solve_gameplan(plan, dex, game):
    g = _guide(plan)
    if not g.win and not g.leads:
        return None
    parts, facts = [], []
    if g.leads:
        parts.append(f"lead with your {g.leads[0]['name']}")
        facts += _lead_facts(g.leads[:1])
    if g.win:
        parts.append(f"your {g.win['name']} is the win condition")
        facts += [f"{g.win['name']}: {p}" for p in _sentences(g.win["points"])] + [g.win["keep"]]
    if g.watch:
        names = [w["name"] for w in g.watch[:2]]
        parts.append(f"watch out for {_and(names)}")
        facts += _watch_facts(g)[:2]
    if g.combos:
        pair = g.combos[0]
        facts.append(f"{_and(pair['pair'])} cover each other: {pair['points'][0]}.")
    statement = (parts[0][0].upper() + parts[0][1:] + (", " + ", ".join(parts[1:-1]) if len(parts) > 2 else "")
                 + (f", and {parts[-1]}." if len(parts) > 1 else "."))
    return Verdict("gameplan", g.win["name"] if g.win else g.leads[0]["name"], statement, facts, persona="strategy")


def solve_tera(plan, dex, game):
    """'Who should I Tera': each member's own Tera type, ranked by the weaknesses it removes and adds and whether it
    powers up an attack (Coach Guide Tera plan). SV only: Champions has no Tera."""
    if game == "champions":
        return None
    g = _guide(plan)
    if not g.tera:
        return None
    top = g.tera[0]
    if not top.get("best"):
        statement = "None of your members gains much from its Tera type; it removes no more weaknesses than it adds."
    else:
        statement = f"Your {top['name']} is your best Tera user: Tera {top['tera']}."
    facts = []
    for t in g.tera[:3]:
        parts = []
        if t["removed"]:
            parts.append(f"removes its {_and(t['removed'])} weakness{'es' if len(t['removed']) > 1 else ''}")
        if len(t["added"]) == 1:
            article = "an" if t["added"][0][0] in "AEIOU" else "a"
            parts.append(f"adds {article} {t['added'][0]} weakness")
        elif t["added"]:
            parts.append(f"adds {_and(t['added'])} weaknesses")
        note = t["note"]
        # "Purely defensive..." and "Stellar keeps..." read as a clause; "Headlong Rush goes..." starts with a move name
        parts.append(note[0].lower() + note[1:] if note.startswith(("Purely", "Stellar")) else note)
        facts.append(f"{t['name']}, Tera {t['tera']}: " + "; ".join(parts) + ".")
    return Verdict("tera", top["name"], statement, facts, persona="strategy")


def solve_switchins(plan, dex, game):
    """'Who on my team can switch into Raging Bolt': members ranked by the damage they take from the opponent's
    strongest attack against them. Switching in is taking a hit, not winning the one on one: a member that survives
    at least two of its strongest hits counts."""
    from metamatch.engine.solvers import _stated_set, display_name
    from metamatch.engine.threat_board import row_for_set
    row = row_for_set(plan.team, _stated_set(plan, dex, game), plan.format_id)
    if not row:
        return None
    name = display_name(row.name)
    if any(m.lower() == row.name.lower() for m in row.cells):
        name = f"the opposing {name}"
    ranked = []
    for member, cell in row.cells.items():
        x = cell.exchange or {}
        if not x.get("taken"):
            ranked.append((0.0, member, f"Your {member} takes no damage from {name}'s usual attacks."))
            continue
        move, res = x["taken"]
        lo, hi = res["percent"]
        hits = x.get("to_be_koed")
        ranked.append((hi, member, f"Your {member} takes {move} for {lo:g} to {hi:g}%"
                       + (f" ({hits} hits to KO)." if hits else ".")))
    ranked.sort()
    good = [m for hi, m, _ in ranked if hi < 50 or ((row.cells[m].exchange or {}).get("to_be_koed") or 0) >= 3]
    if good:
        verb = "takes" if len(good) == 1 else "take"
        statement = f"Your {_and(good)} {verb} {name}'s attacks best."
    else:
        statement = f"Nobody on your team takes two of {name}'s strongest hits."
    basis = "its most common set, with the details the question states" if plan.opp_overrides else "its most common set"
    facts = [line for _, _, line in ranked] + [f"{name[0].upper() + name[1:]} assumed on {basis}, at full health; "
                                               "recovery and Regenerator are not counted."]
    return Verdict("switchins", ", ".join(good) or "none", statement, facts, persona="strategy", other=name,
                   members=list(row.cells))


def solve_member(plan, dex, game):
    """'Why is Torkoal on this team', 'how do I use Slowking-Galar': the member's jobs (the cores it sets or uses,
    hazards, removal, pivoting, set up, win condition, lead) and its one on ones against the most used Pokemon."""
    from metamatch.engine.guide import member_facts
    from metamatch.engine import rules
    g = _guide(plan)
    team = plan.team or {}
    name = plan.user["Pokemon"]
    rows = _rows_for(plan)
    m = next((x for x in member_facts(team, plan.format_id, rows) if x.name == name), None)
    if m is None:
        return None
    jobs = []
    for e in g.engines:
        label = getattr(e, "label", None) or e.key
        if any(st["name"] == name for st in e.setters):
            users = [u.name for u in e.users if u.name != name]
            jobs.append(f"sets {label}" + (f" for {_and(users)}" if users else ""))
        elif any(u.name == name for u in e.users):
            jobs.append(f"uses the team's {label}")
    if m.hazards:
        jobs.append(f"sets {_and(m.hazards)}")
    if m.removal:
        jobs.append(f"clears hazards with {_and(m.removal)}")
    if m.pivots:
        jobs.append(f"pivots out with {_and(m.pivots)}")
    if m.setup:
        jobs.append(f"sets up with {_and(m.setup)}")
    if g.win and g.win["name"] == name:
        jobs.append("is your main win condition")
    if any(lead["name"] == name for lead in g.leads):
        jobs.append("is one of your best leads")
    n = g.n_threats
    if jobs:
        statement = f"Your {name} {_and(jobs)}."
    else:
        statement = f"Your {name} beats {len(m.beats)} of the {n} most used Pokemon one on one."
    facts = [f"Beats {len(m.beats)} of the {n} most used Pokemon one on one" + (f": {_and(m.beats[:6])}." if m.beats else "."),
             f"Loses to {_and(m.loses[:6])}." if m.loses else "None of the most used Pokemon beats it one on one.",
             f"Outspeeds {m.outspeeds:.0%} of the top ladder sets."]
    if m.priority:
        facts.append(f"Has {_and(m.priority)} for priority.")
    # A move the question names: Showdown's rule text for it
    asked = plan.query.lower()
    for move in [mv["name"] for mv in plan.user.get("Moves", [])]:
        if re.search(rf"\b{re.escape(move.lower())}\b", asked):
            line = rules.text_line("move", move)
            if line:
                facts.append(line)
    return Verdict("member", name, statement, facts, persona="strategy", subject=name)


@lru_cache(maxsize=16)
def _rows_cached(team_json, format_id):
    from metamatch.engine.guide import board_rows
    return board_rows(json.loads(team_json), format_id)


def _rows_for(plan):
    team = plan.team or {}
    return _rows_cached(json.dumps(team, sort_keys=True, default=str), plan.format_id or config.team_format(team))


SOLVERS = {"win": solve_win, "lead": solve_lead, "threats": solve_threats, "gameplan": solve_gameplan, "tera": solve_tera,
           "switchins": solve_switchins, "member": solve_member}
