"""
Engine answers for the strategy questions that used to reach Professor Oak as free text: win condition, leads, the
threats to watch, and the overall game plan. Each is a Verdict built from the Coach Guide (engine/guide.py: Threat
Board one on ones, Speed, synergy engines, ladder lead rates), so Oak only voices a finished answer.

Why: in the 2026 11 14 runs Oak's own advice was right 2 times in 50, and the best free text prompt shape still topped
out at 4 of 12 on these general questions, while an engine sentence plus one voiced "why" was right 18 of 21 times.
"""
import json
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


SOLVERS = {"win": solve_win, "lead": solve_lead, "threats": solve_threats, "gameplan": solve_gameplan}
