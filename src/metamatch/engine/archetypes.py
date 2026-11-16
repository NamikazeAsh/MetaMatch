"""
"How do I play against rain / sun / sand / stall / hazard stacking": the user's own one on ones against the real
archetype roster (data/json/archetypes.json, built from ladder teammate data by scripts/build_archetypes.py), never
general type advice. Weather rosters are scored with the weather up, and again after the user's own weather setter
replaces it. Stall is judged by whether a member's first hit takes over half of each wall (walls heal half), and
Unaware walls are flagged for setup sweepers. Hazard stacking has no stable roster, so it is answered from the team's
own removal, Heavy-Duty Boots and Stealth Rock weaknesses, plus how the team does against the top hazard setters.
"""
import json
import re
from functools import lru_cache

from metamatch import config
from metamatch.engine.packet import Fact, cap, join, mon
from metamatch.engine.sets import chaos_entry, likely_set
from metamatch.engine.solvers import Verdict

FILE = config.DATA_DIR / "json" / "archetypes.json"
ARCHETYPE_WORDS = {"rain": "rain", "sun": "sun", "sand": "sand", "sandstorm": "sand", "stall": "stall",
                   "hazard stack": "hazards", "hazard stacking": "hazards", "hazard stacks": "hazards",
                   "spikes stacking": "hazards", "hazards teams": "hazards", "hazard teams": "hazards"}
WEATHER_SETTER = {"Drizzle": "Rain", "Drought": "Sun", "Sand Stream": "Sand", "Snow Warning": "Snow"}
WEATHER_WORD = {"Rain": "rain", "Sun": "sun", "Sand": "sand", "Snow": "snow"}
ROSTER_SIZE = 6


@lru_cache(maxsize=1)
def _data():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def archetype_of(text):
    low = text.lower()
    for words, key in sorted(ARCHETYPE_WORDS.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"\b{re.escape(words)}\b", low):
            return key
    return None


def available(key, format_id):
    data = _data().get(format_id, {})
    return key == "hazards" or key in data


def _own_weather(team):
    for p in team.values():
        w = WEATHER_SETTER.get(p.get("Ability") or "")
        if w:
            return p["Pokemon"], w
    return None, None


def solve_archetype(plan, dex, game):
    key = plan.archetype
    if key == "hazards":
        return _hazards(plan, dex)
    data = _data().get(plan.format_id, {}).get(key)
    if not data:
        return None
    if key == "stall":
        return _stall(plan, data)
    return _weather(plan, key, data)


def _rows(team, names, format_id, field=None):
    from metamatch.engine.threat_board import row_for_set
    out = []
    for n in names:
        s = likely_set(n, format_id)
        row = row_for_set(team, s, format_id, field=field) if s else None
        if row:
            out.append(row)
    return out


def _weather(plan, key, data):
    team, fmt = plan.team or {}, plan.format_id
    weather = data["weather"]
    roster = [s[0] for s in data["setters"][:2]] + [p[0] for p in data["partners"]]
    roster = list(dict.fromkeys(roster))[:ROSTER_SIZE]
    rows = _rows(team, roster, fmt, {"weather": weather})
    if not rows:
        return None
    setter, own = _own_weather(team)
    reset = _rows(team, roster, fmt, {"weather": own}) if own and own != weather else []
    typed = []
    lead = data["setters"][0]
    partners = ", ".join(f"{p[0]} ({round(p[1] * 100)}% of its teams)" for p in data["partners"][:4])
    typed.append(Fact("usage", f"{lead[0]} sets {key} on {lead[1]:g}% of ladder teams; its usual partners are {partners}.",
                      {"setter": lead[0], "usage": lead[1]}))
    unanswered, answered = [], 0
    for r in rows:
        if r.answers:
            answered += 1
            typed.append(Fact("matchup", f"With {key} up, {join(mon(a, True) for a in r.answers)} "
                                         f"{'beats' if len(r.answers) == 1 else 'beat'} {mon(r.name, False)} one on one.",
                              {"opponent": r.name, "answers": r.answers, "weather": weather}, role="why"))
        else:
            unanswered.append(r.name)
            typed.append(Fact("matchup", f"With {key} up, nobody on your team beats {mon(r.name, False)} one on one.",
                              {"opponent": r.name, "answers": [], "weather": weather}, role="why"))
    fixed = []
    for r in reset:
        if r.name in unanswered and r.answers:
            fixed.append(r.name)
            typed.append(Fact("matchup", f"Once your {setter} brings {WEATHER_WORD[own]} back, {join(mon(a, True) for a in r.answers)} "
                                         f"{'beats' if len(r.answers) == 1 else 'beat'} {mon(r.name, False)} one on one.",
                              {"opponent": r.name, "answers": r.answers, "weather": own}, role="why"))
    if setter and own and own != weather:
        typed.append(Fact("rule", f"Your {setter}'s ability replaces {key} with {WEATHER_WORD[own]} whenever it switches in.",
                          {"setter": setter}))
    said = (f"With {key} up, your team beats {answered} of the {len(rows)} usual {key} Pokemon one on one"
            + (f"; nobody beats {join(mon(n, False) for n in unanswered)}" if unanswered else "") + ".")
    if fixed:
        said += f" Once your {setter} brings {WEATHER_WORD[own]} back, you also beat {join(mon(n, False) for n in fixed)}."
    # Keep the why facts to the unanswered and fixed matchups when there are any
    for f in typed:
        if f.role == "why" and unanswered and f.data.get("opponent") not in unanswered:
            f.role = "context"
    facts = [f.text for f in typed]
    return Verdict("archetype", f"{answered}/{len(rows)}", said, facts, persona="strategy", plain=said, typed=typed)


def _stall(plan, data):
    team, fmt = plan.team or {}, plan.format_id
    walls = [w[0] for w in data["walls"]][:ROSTER_SIZE + 1]
    rows = _rows(team, walls, fmt)
    if not rows:
        return None
    typed, unbroken, breakers = [], [], set()
    for r in rows:
        heavy = []
        for m, c in r.cells.items():
            x = c.exchange or {}
            if x.get("dealt") and not x["dealt"][1].get("half_hp") and x["dealt"][1]["percent"][0] > 50:
                heavy.append((m, x["dealt"][0], x["dealt"][1]["percent"]))
        if heavy:
            breakers |= {m for m, _, _ in heavy}
            m, move, (lo, hi) = max(heavy, key=lambda h: h[2][0])
            typed.append(Fact("damage", f"Your {m}'s {move} does {round(lo)} to {round(hi)}% of {mon(r.name, False)}'s HP, "
                                        "more than its recovery heals in one turn.", {"wall": r.name, "member": m}, role="why"))
        else:
            unbroken.append(r.name)
            typed.append(Fact("damage", f"Nothing on your team does over half of {mon(r.name, False)}'s HP in one hit, so "
                                        "it can heal off your attacks.", {"wall": r.name}, role="why"))
        s = likely_set(r.name, fmt)
        if s and s.get("ability") == "Unaware":
            typed.append(Fact("rule", f"{cap(mon(r.name, False))} has Unaware, so it ignores your stat boosts from moves "
                                      "like Swords Dance.", {"wall": r.name}))
    said = (f"Against stall, {join(mon(b, True) for b in sorted(breakers))} {'breaks' if len(breakers) == 1 else 'break'} "
            f"through {len(rows) - len(unbroken)} of the {len(rows)} common walls with one hit over half their HP"
            if breakers else f"Against stall, nothing on your team does over half of any common wall's HP in one hit")
    said += (f"; nothing does that to {join(mon(n, False) for n in unbroken)}." if unbroken and breakers else ".")
    for f in typed:
        if f.role == "why" and unbroken and f.data.get("wall") not in unbroken:
            f.role = "context"
    return Verdict("archetype", f"{len(rows) - len(unbroken)}/{len(rows)}", said, [f.text for f in typed],
                   persona="strategy", plain=said, typed=typed)


ROCK_WEAK = {2: 25, 4: 50}


def _hazards(plan, dex):
    """Hazard stacking: the team's own removal, Boots and Stealth Rock damage, and the top hazard setters' matchups."""
    team, fmt = plan.team or {}, plan.format_id
    removal_moves = {"Rapid Spin", "Defog", "Mortal Spin", "Court Change", "Tidy Up"}
    removers = [p["Pokemon"] for p in team.values() if {m["name"] for m in p.get("Moves", [])} & removal_moves]
    boots = [p["Pokemon"] for p in team.values() if p.get("Item") == "Heavy-Duty Boots"]
    typed = [Fact("set", f"Hazard removal on your team: {join(mon(n, True) for n in removers) or 'none'}.",
                  {"removers": removers}, role="why"),
             Fact("set", f"Holding Heavy-Duty Boots: {join(mon(n, True) for n in boots) or 'none'}.", {"boots": boots})]
    for p in team.values():
        mult = (p.get("Damage From") or {}).get("rock", 1.0)
        if mult >= 2 and p["Pokemon"] not in boots:
            typed.append(Fact("damage", f"Stealth Rock takes {ROCK_WEAK.get(int(mult), 25)}% of your {p['Pokemon']}'s HP "
                                        "each time it switches in.", {"member": p["Pokemon"]}, role="why"))
    from metamatch.engine.threat_board import top_threats
    setters = []
    for name, _ in top_threats(fmt, n=30):
        _, entry = chaos_entry(name, fmt)
        total = sum((entry or {}).get("Abilities", {}).values()) or 1
        if entry and (entry["Moves"].get("stealthrock", 0) + entry["Moves"].get("spikes", 0)) / total >= 0.5:
            setters.append(name)
        if len(setters) == 4:
            break
    for r in _rows(team, setters, fmt):
        typed.append(Fact("matchup", f"{cap(join(mon(a, True) for a in r.answers))} "
                                     f"{'beats' if len(r.answers) == 1 else 'beat'} {mon(r.name, False)}, a common hazard "
                                     "setter, one on one." if r.answers else
                                     f"Nobody on your team beats {mon(r.name, False)}, a common hazard setter, one on one.",
                          {"opponent": r.name, "answers": r.answers}))
    said = (f"Against hazard stacking, your hazard removal is {join(mon(n, True) for n in removers)}" if removers
            else "Against hazard stacking, your team has no hazard removal")
    said += f", and {len(boots)} of your Pokemon hold Heavy-Duty Boots."
    return Verdict("archetype", "hazards", said, [f.text for f in typed], persona="strategy", plain=said, typed=typed)


SOLVERS = {"archetype": solve_archetype}
