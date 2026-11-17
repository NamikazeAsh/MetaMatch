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
from metamatch.engine.packet import Fact, mon, plainify
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
    said = f"Your {name} is your best route to a win."
    return Verdict("win", name, said, facts, persona="strategy", plain=said, typed=_win_facts(g))


CONDITION_START = re.compile(r"^(?:With|After|Once|Under|When|If|Against|Behind)\b")


def _about(name, point):
    """'Your Kingambit beats ...' for a point about a member; a point that opens with its condition ("With 3
    teammates down, ...") reads 'For your Kingambit, with 3 teammates down, ...' instead of 'Your Kingambit: With'."""
    p = plainify(point.rstrip("."))
    if CONDITION_START.match(p):
        return f"For your {name}, {p[:1].lower()}{p[1:]}."
    return f"Your {name}: {p}."


def _win_facts(g):
    name = g.win["name"]
    out = [Fact("role", _about(name, p), {"member": name}, role="why" if i < 2 else "context")
           for i, p in enumerate(g.win["points"])]
    if g.win.get("threats"):
        out.append(Fact("matchup", f"Keep your {name} healthy until these are worn down: "
                                   f"{_and(mon(t, False) for t in g.win['threats'])}.", {"threats": g.win["threats"]}))
    return out


def _lead_typed(leads, why=True):
    out = []
    for i, lead in enumerate(leads):
        for j, p in enumerate(lead["points"]):
            out.append(Fact("role", _about(lead["name"], p), {"member": lead["name"]},
                            role="why" if why and i == 0 and j < 2 else "context"))
    return out


def _lead_facts(leads):
    return [f"{lead['name']}: {'; '.join(p.rstrip('.') for p in lead['points'])}." for lead in leads]


def solve_lead(plan, dex, game):
    g = _guide(plan)
    if not g.leads:
        return None
    names = [lead["name"] for lead in g.leads]
    statement = f"Lead with your {names[0]}" + (f", or your {names[1]}." if len(names) > 1 else ".")
    return Verdict("lead", names[0], statement, _lead_facts(g.leads), persona="strategy", plain=statement,
                   typed=_lead_typed(g.leads))


def _watch_facts(g):
    return [f"{w['name']} (on {w['usage']:.0f}% of teams): {w['text']}." for w in g.watch]


def _watch_typed(g, why=True):
    out = []
    for i, w in enumerate(g.watch):
        opp = mon(w["name"], False)
        answers = w.get("answers") or []
        tail = (f"only {mon(answers[0], True)} beats it one on one" if len(answers) == 1 else
                "nobody on your team beats it one on one" if not answers else
                f"{_and(mon(a, True) for a in answers)} beat it one on one")
        out.append(Fact("matchup", f"{opp[0].upper() + opp[1:]} is on {w['usage']:.0f}% of ladder teams, and {tail}.",
                        {"threat": w["name"], "usage": w["usage"], "answers": answers}, role="why" if why and i < 2 else "context"))
    return out


def solve_threats(plan, dex, game):
    g = _guide(plan)
    if not g.watch:
        statement = f"Every one of the {g.n_threats} most used Pokemon has at least two answers on your team."
        return Verdict("threats", "none", statement, [], persona="strategy", plain=statement)
    names = [w["name"] for w in g.watch]
    verb = "is the threat" if len(names) == 1 else "are the threats"
    statement = f"{_and(names)} {verb} your team answers most thinly."
    said = f"{_and(mon(n, False) for n in names)} {verb} your team answers most thinly."
    said = said[0].upper() + said[1:]
    return Verdict("threats", ", ".join(names), statement, _watch_facts(g), persona="strategy", plain=said,
                   typed=_watch_typed(g))


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
    typed = (_lead_typed(g.leads[:1], why=False) + (_win_facts(g) if g.win else []) + _watch_typed(g, why=False)[:2])
    if g.combos:
        pair = g.combos[0]
        typed.append(Fact("role", f"Your {pair['pair'][0]} and your {pair['pair'][1]} cover each other's one on one "
                                  "losses.", {"pair": pair["pair"]}, detail=pair["points"][0]))
    return Verdict("gameplan", g.win["name"] if g.win else g.leads[0]["name"], statement, facts, persona="strategy",
                   plain=statement, typed=typed)


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
    typed = [Fact("type", plainify(f"Your {f}"), {"member": t["name"], "tera": t["tera"]}, role="why" if i == 0 else "context")
             for i, (f, t) in enumerate(zip(facts, g.tera[:3]))]
    return Verdict("tera", top["name"], statement, facts, persona="strategy", plain=statement, typed=typed)


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
    from metamatch.engine.packet import hits as hits_text, pct
    opp = name if name.startswith("the opposing") else mon(name, False)
    ranked, typed_by = [], {}
    for member, cell in row.cells.items():
        x = cell.exchange or {}
        if not x.get("taken"):
            ranked.append((0.0, member, f"Your {member} takes no damage from {name}'s usual attacks."))
            typed_by[member] = Fact("damage", f"{opp[0].upper() + opp[1:]}'s usual attacks do no damage to your {member}.",
                                    {"member": member, "pct": [0, 0]})
            continue
        move, res = x["taken"]
        lo, hi = res["percent"]
        hits = x.get("to_be_koed")
        ranked.append((hi, member, f"Your {member} takes {move} for {lo:g} to {hi:g}%"
                       + (f" ({hits} hits to KO)." if hits else ".")))
        count = hits_text(hits, x.get("to_be_koed_best"))
        typed_by[member] = Fact("damage", f"{opp[0].upper() + opp[1:]}'s {move} does {pct(lo, hi)} of your {member}'s HP"
                                          + (f", knocking it out {count}." if count else "."),
                                {"member": member, "move": move, "pct": [lo, hi], "hits": hits}, detail=res.get("desc", ""))
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
    typed = []
    for i, (_, member, _) in enumerate(ranked):
        f = typed_by[member]
        f.role = "why" if i < 2 and member in good else "context"
        typed.append(f)
    typed.append(Fact("stated", f"{opp[0].upper() + opp[1:]} is assumed on {basis}, at full health; recovery and "
                                "Regenerator are not counted.", {"basis": basis}))
    said = (f"Your {_and(good)} {'takes' if len(good) == 1 else 'take'} {opp}'s attacks best." if good else
            f"Nobody on your team takes two of {opp}'s strongest hits.")
    return Verdict("switchins", ", ".join(good) or "none", statement, facts, persona="strategy", other=name,
                   members=list(row.cells), plain=said, typed=typed)


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
    typed = [Fact("role", f"Your {name} beats {len(m.beats)} of the {n} most used Pokemon one on one"
                          + (f": {_and(mon(b, False) for b in m.beats[:5])}." if m.beats else "."),
                  {"beats": m.beats}, role="why"),
             Fact("role", f"Your {name} loses one on one to {_and(mon(b, False) for b in m.loses[:5])}." if m.loses else
                          f"None of the most used Pokemon beats your {name} one on one.", {"loses": m.loses}, role="why"),
             Fact("speed", f"Your {name} outspeeds {m.outspeeds:.0%} of the top ladder sets.", {"outspeeds": m.outspeeds})]
    if m.priority:
        typed.append(Fact("speed", f"Your {name} has {_and(m.priority)} for priority.", {"priority": m.priority}))
    # Rule text lines come after the three one on one lines and the priority line
    typed += [Fact("rule", f, {"source": "Showdown"}) for f in facts[3 + bool(m.priority):]]
    return Verdict("member", name, statement, facts, persona="strategy", subject=name, plain=statement, typed=typed)


def solve_score(plan, dex, game):
    """'Is my team good', 'rate my team': the broken down team score (engine/team_score.py) with its ladder percentile.
    Each part is a fact with its evidence; the weakest two lead the answer."""
    from metamatch.engine.team_score import LABELS, WEIGHTS, score_team
    from metamatch.engine.threat_board import threat_board
    team = plan.team or {}
    s = score_team(team, plan.format_id, rows=threat_board(team, n=12, format_id=plan.format_id))
    names = sorted((p["Pokemon"] for p in team.values()), key=len, reverse=True)

    def owned(text):
        for n in names:
            text = re.sub(rf"(?<!your )\b{re.escape(n)}\b", f"your {n}", text)
        return text
    # Weakest by points lost, not percentage; the engines part is a bonus most teams lack, so it never leads
    weakest = sorted((p for p in s.parts if p.key != "cores"), key=lambda p: p.points - WEIGHTS[p.key])[:2]
    said = f"Your team scores {s.total:g} out of 100 on MetaMatch's checklist"
    if s.percentile is not None:
        said += f", better covered than {round(s.percentile * 100)}% of the {s.sample} ladder teams in our sample"
    said += f". Its weakest parts are {LABELS[weakest[0].key].lower()} and {LABELS[weakest[1].key].lower()}."
    typed = [Fact("score", owned(f"{LABELS[p.key]}: {p.points:g} of {WEIGHTS[p.key]} points. {p.evidence}"),
                  {"part": p.key, "points": p.points, "weight": WEIGHTS[p.key]},
                  role="why" if p in weakest else "context") for p in s.parts]
    typed += [Fact("score", n, {}) for n in s.notes]
    facts = [f"{LABELS[p.key]}: {p.points:g} / {WEIGHTS[p.key]}. {p.evidence}" for p in s.parts] + s.notes
    return Verdict("score", f"{s.total:g}", said, facts, persona="strategy", plain=said, typed=typed)


def solve_speed_tiers(plan, dex, game):
    """'Walk me through my speed tiers': each member's Speed and how much of the top ladder it outspeeds (Speed Tiers
    tab, same functions)."""
    from metamatch.engine.guide import N_SPEED
    from metamatch.engine import speed_board
    team = plan.team or {}
    names = [p["Pokemon"] for p in team.values()]
    speeds = speed_board.member_speeds(team, plan.format_id)
    meta = speed_board.meta_speeds(plan.format_id, n=N_SPEED, exclude=names)
    if not speeds or not meta:
        return None
    share = {n: sum(speed_board.outspeed_share(s, m) for m in meta) / len(meta) for n, s in speeds.items()}
    order = sorted(speeds, key=speeds.get, reverse=True)
    typed = [Fact("speed", f"Your {n} has {speeds[n]} Speed and outspeeds {round(share[n] * 100)}% of the top {N_SPEED} "
                           "ladder Pokemon's sets.", {"member": n, "speed": speeds[n], "share": round(share[n], 3)},
                  role="why" if i in (0, len(order) - 1) else "context") for i, n in enumerate(order)]
    fast, slow = order[0], order[-1]
    said = (f"Your fastest is your {fast} at {speeds[fast]} Speed, outspeeding {round(share[fast] * 100)}% of the top "
            f"{N_SPEED} ladder sets; your slowest is your {slow} at {speeds[slow]}.")
    return Verdict("speed_tiers", fast, said, [f.text for f in typed], persona="mechanics", plain=said, typed=typed)


def solve_audit(plan, dex, game):
    """'What did the audit flag': set choices few ladder players make (usage audit) and legality problems (Team
    Check), the same functions as the Audit tab."""
    from metamatch import auditor
    from metamatch.engine.team_check import check
    team = plan.team or {}
    typed = []
    for w in auditor.audit_team(team).get("warnings", []):
        common = f"; the most common is {w['suggestion']}" if w.get("suggestion") else ""
        typed.append(Fact("usage", f"Your {w['pokemon']} runs {w['current']} ({w['category'].lower()}), which only "
                                   f"{w['usage']:.0f}% of ladder {w['pokemon']} sets use{common}.",
                          {"member": w["pokemon"], "usage": w["usage"]}, role="why" if len(typed) < 2 else "context"))
    problems = [(lvl, msg) for lvl, msg in check(team, plan.format_id) if lvl == "fix"]
    for _, msg in problems:
        typed.append(Fact("rule", msg, {"legality": True}, role="why"))
    if not typed:
        said = "The audit found nothing unusual: every item, ability and move is one ladder players commonly run, and the team is legal."
        return Verdict("audit", "clean", said, [], persona="builder", plain=said, typed=[])
    said = (f"The audit flags {len(typed) - len(problems)} uncommon set choice{'s' if len(typed) - len(problems) != 1 else ''}"
            + (f" and {len(problems)} legality problem{'s' if len(problems) != 1 else ''}" if problems else "") + ".")
    return Verdict("audit", str(len(typed)), said, [f.text for f in typed], persona="builder", plain=said, typed=typed)


@lru_cache(maxsize=16)
def _rows_cached(team_json, format_id):
    from metamatch.engine.guide import board_rows
    return board_rows(json.loads(team_json), format_id)


def _rows_for(plan):
    team = plan.team or {}
    return _rows_cached(json.dumps(team, sort_keys=True, default=str), plan.format_id or config.team_format(team))


SOLVERS = {"win": solve_win, "lead": solve_lead, "threats": solve_threats, "gameplan": solve_gameplan, "tera": solve_tera,
           "switchins": solve_switchins, "member": solve_member, "score": solve_score,
           "speed_tiers": solve_speed_tiers, "audit": solve_audit}
